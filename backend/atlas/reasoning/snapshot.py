"""In-memory, indexed snapshot of the knowledge graph.

The reasoning layer runs deterministic algorithms over this snapshot rather
than issuing hundreds of small Cypher queries. The graph is small (thousands of
elements), so a snapshot loads in well under a second and makes reasoning fast,
pure and unit-testable without a database.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from typing import TYPE_CHECKING, Any

from ..ontology import ONTOLOGY

if TYPE_CHECKING:
    from ..seed.generator import GraphData


@dataclass
class Snapshot:
    labels: dict[str, str] = field(default_factory=dict)  # id -> most specific label
    props: dict[str, dict[str, Any]] = field(default_factory=dict)
    out: dict[tuple[str, str], list[tuple[str, dict]]] = field(default_factory=lambda: defaultdict(list))
    inc: dict[tuple[str, str], list[tuple[str, dict]]] = field(default_factory=lambda: defaultdict(list))

    # --------------------------------------------------------------- build
    def add_node(self, id_: str, label: str, props: dict[str, Any]) -> None:
        self.labels[id_] = label
        self.props[id_] = props

    def add_edge(self, type_: str, source: str, target: str, props: dict[str, Any]) -> None:
        self.out[(source, type_)].append((target, props))
        self.inc[(target, type_)].append((source, props))

    @classmethod
    def from_graphdata(cls, g: GraphData) -> Snapshot:
        s = cls()
        for id_, n in g.nodes.items():
            s.add_node(id_, n["label"], n["props"])
        for e in g.edges:
            s.add_edge(e["type"], e["source"], e["target"], e["props"])
        return s

    @classmethod
    def from_neo4j(cls) -> Snapshot:
        from ..graph.client import run

        s = cls()
        known = {c.label for c in ONTOLOGY.classes}
        for row in run("MATCH (n) RETURN n.id AS id, labels(n) AS labels, properties(n) AS props"):
            specific = max((lbl for lbl in row["labels"] if lbl in known), key=lambda lbl: len(ONTOLOGY.ancestors(lbl)))
            props = {k: v for k, v in row["props"].items() if k != "text"}
            s.add_node(row["id"], specific, props)
        for row in run(
            "MATCH (a)-[r]->(b) WHERE r.rule IS NULL RETURN a.id AS s, type(r) AS t, b.id AS o, properties(r) AS p"
        ):
            s.add_edge(row["t"], row["s"], row["o"], row["p"])
        return s

    # -------------------------------------------------------------- access
    def is_a(self, id_: str, label: str) -> bool:
        return id_ in self.labels and ONTOLOGY.is_a(self.labels[id_], label)

    def of(self, label: str) -> list[str]:
        return [i for i in self.labels if self.is_a(i, label)]

    def name(self, id_: str) -> str:
        p = self.props.get(id_, {})
        return p.get("name") or p.get("title") or id_

    def targets(self, id_: str, rel: str) -> list[tuple[str, dict]]:
        return self.out.get((id_, rel), [])

    def sources(self, id_: str, rel: str) -> list[tuple[str, dict]]:
        return self.inc.get((id_, rel), [])

    def target_ids(self, id_: str, rel: str) -> list[str]:
        return [t for t, _ in self.targets(id_, rel)]

    def source_ids(self, id_: str, rel: str) -> list[str]:
        return [s for s, _ in self.sources(id_, rel)]

    def one(self, id_: str, rel: str) -> str | None:
        t = self.target_ids(id_, rel)
        return t[0] if t else None


@lru_cache(maxsize=1)
def _cached() -> Snapshot:
    return Snapshot.from_neo4j()


def get_snapshot(refresh: bool = False) -> Snapshot:
    if refresh:
        _cached.cache_clear()
    return _cached()
