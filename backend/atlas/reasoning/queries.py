"""Graph look-ups used by agent tools: entity search, entity profiles, safe read-only Cypher."""

from __future__ import annotations

import re
from typing import Any

from ..config import get_settings
from ..graph.client import get_driver, run

_WRITE = re.compile(
    r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|LOAD\s+CSV|CALL\s+db\.(?!index\.fulltext\.queryNodes)|CALL\s+apoc\.(?!meta))\b",
    re.I,
)


def search_entities(text: str, limit: int = 8, labels: list[str] | None = None) -> list[dict[str, Any]]:
    """Multilingual fuzzy search over names (English and Arabic) using the full-text index."""
    cleaned = re.sub(r"[^\w\s؀-ۿ-]", " ", text).strip()
    if not cleaned:
        return []
    terms = " ".join(f"{t}~" if t.isascii() and len(t) > 3 else t for t in cleaned.split())
    rows = run(
        """
        CALL db.index.fulltext.queryNodes('entity_names', $q) YIELD node, score
        WITH node, score WHERE $labels IS NULL OR any(l IN labels(node) WHERE l IN $labels)
        RETURN node.id AS id, [l IN labels(node) WHERE l <> 'Organization' AND l <> 'Item' AND l <> 'Facility'][0]
               AS label, coalesce(node.name, node.title) AS name, node.name_ar AS name_ar, score
        ORDER BY score DESC LIMIT $limit
        """,
        q=terms,
        labels=labels,
        limit=limit,
    )
    return rows


def profile(entity_id: str, max_neighbours: int = 40) -> dict[str, Any]:
    """An entity's properties plus a summary of its neighbourhood grouped by relationship."""
    rows = run(
        """
        MATCH (n {id: $id})
        OPTIONAL MATCH (n)-[r]-(m) WHERE r.rule IS NULL OR type(r) IN ['EXPOSED_TO', 'SINGLE_SOURCE']
        WITH n, r, m LIMIT $limit
        RETURN properties(n) AS props, labels(n) AS labels,
               collect(CASE WHEN r IS NULL THEN NULL ELSE {
                   rel: type(r), direction: CASE WHEN startNode(r) = n THEN 'out' ELSE 'in' END,
                   id: m.id, name: coalesce(m.name, m.title), props: properties(r)} END) AS neighbours
        """,
        id=entity_id,
        limit=max_neighbours,
    )
    if not rows:
        return {"error": f"No entity with id {entity_id}"}
    row = rows[0]
    props = {k: v for k, v in row["props"].items() if k != "text"}
    if "text" in row["props"]:
        props["text_excerpt"] = row["props"]["text"][:1500]
    return {"labels": row["labels"], "properties": props, "neighbours": row["neighbours"]}


def read_cypher(query: str, params: dict[str, Any] | None = None, limit: int = 100) -> list[dict[str, Any]]:
    """Execute a *read-only* Cypher query (guarded twice: lexical check + read transaction)."""
    if _WRITE.search(query):
        raise ValueError("Only read-only Cypher is allowed.")
    if not re.search(r"\bLIMIT\b", query, re.I):
        query = f"{query.rstrip().rstrip(';')} LIMIT {limit}"
    with get_driver().session(database=get_settings().neo4j_database, default_access_mode="READ") as sess:
        result = sess.execute_read(lambda tx: [r.data() for r in tx.run(query, params or {})])
    return result[:limit]
