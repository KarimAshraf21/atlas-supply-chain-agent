"""Load seed data into Neo4j, shaped and validated by the ontology."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from ..ontology import ONTOLOGY
from ..ontology.exporters import neo4j_constraints
from .client import run, session

BATCH = 500


def _root(label: str) -> str:
    return ONTOLOGY.ancestors(label)[-1]


def _batches(rows: list[Any], size: int = BATCH):
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


def read_seed(seed_dir: Path, documents: bool = True) -> tuple[list[dict], list[dict]]:
    nodes = [json.loads(line) for line in (seed_dir / "graph" / "nodes.jsonl").open(encoding="utf-8")]
    edges = [json.loads(line) for line in (seed_dir / "graph" / "edges.jsonl").open(encoding="utf-8")]
    if documents:
        for n in nodes:
            if n["label"] == "Document" and n.get("path"):
                raw = (seed_dir / n["path"]).read_text(encoding="utf-8")
                n["text"] = raw.split("---", 2)[2].strip() if raw.startswith("---") else raw
    return nodes, edges


def reset() -> None:
    # CALL ... IN TRANSACTIONS needs an auto-commit (implicit) transaction.
    with session() as sess:
        sess.run("MATCH (n) CALL (n) { DETACH DELETE n } IN TRANSACTIONS OF 5000 ROWS").consume()


def apply_schema() -> int:
    stmts = neo4j_constraints(ONTOLOGY)
    for stmt in stmts:
        run(stmt)
    return len(stmts)


def load(seed_dir: Path, wipe: bool = True) -> dict[str, int]:
    nodes, edges = read_seed(seed_dir)
    if wipe:
        reset()
    apply_schema()

    label_of: dict[str, str] = {}
    by_label: dict[str, list[dict]] = defaultdict(list)
    for n in nodes:
        label = n.pop("label")
        label_of[n["id"]] = label
        by_label[label].append(n)

    for label, rows in by_label.items():
        labels = ":".join(ONTOLOGY.ancestors(label))
        root = _root(label)
        for batch in _batches(rows):
            run(
                f"UNWIND $rows AS row MERGE (n:{root} {{id: row.id}}) SET n += row, n:{labels}",
                rows=batch,
            )

    grouped: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for e in edges:
        key = (e["type"], _root(label_of[e["source"]]), _root(label_of[e["target"]]))
        grouped[key].append({"s": e["source"], "t": e["target"], "p": e.get("props", {})})

    for (rel, s_root, t_root), rows in grouped.items():
        for batch in _batches(rows):
            run(
                f"UNWIND $rows AS row MATCH (a:{s_root} {{id: row.s}}) MATCH (b:{t_root} {{id: row.t}}) "
                f"MERGE (a)-[r:{rel}]->(b) SET r += row.p",
                rows=batch,
            )

    return {"nodes": len(nodes), "edges": len(edges)}


def counts() -> dict[str, Any]:
    labels = run("MATCH (n) UNWIND labels(n) AS l RETURN l AS label, count(*) AS n ORDER BY label")
    rels = run("MATCH ()-[r]->() RETURN type(r) AS type, count(*) AS n ORDER BY type")
    return {"labels": {r["label"]: r["n"] for r in labels}, "relationships": {r["type"]: r["n"] for r in rels}}
