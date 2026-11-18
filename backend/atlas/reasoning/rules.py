"""Declarative inference rules, materialised into Neo4j with provenance.

Each rule is a Cypher pattern producing an ``inferred`` relationship defined in
the ontology. Inferred edges carry ``rule`` so they can be explained, filtered
and recomputed at any time (``atlas reason``).
"""

from __future__ import annotations

from dataclasses import dataclass

from ..graph.client import run


@dataclass(frozen=True)
class Rule:
    name: str
    produces: str
    description: str
    cypher: str


RULES: list[Rule] = [
    Rule(
        "single_source",
        "SINGLE_SOURCE",
        "An item supplied by exactly one supplier with no qualified alternative is single-sourced.",
        """
        MATCH (s:Supplier)-[:SUPPLIES]->(i:Item)
        WITH i, collect(s) AS suppliers WHERE size(suppliers) = 1
        AND NOT EXISTS { MATCH (:Supplier)-[:QUALIFIED_FOR]->(i) }
        WITH i, suppliers[0] AS s
        MERGE (s)-[r:SINGLE_SOURCE]->(i) SET r.rule = 'single_source'
        RETURN count(r) AS n
        """,
    ),
    Rule(
        "routed_through",
        "ROUTED_THROUGH",
        "A supplier whose default lane transits a chokepoint is routed through it.",
        """
        MATCH (s:Supplier)-[:SHIPS_VIA]->(l:ShippingLane)-[:TRANSITS]->(c:Chokepoint)
        WHERE NOT coalesce(l.is_contingency, false)
        MERGE (s)-[r:ROUTED_THROUGH]->(c) SET r.rule = 'routed_through', r.lane = l.id
        RETURN count(r) AS n
        """,
    ),
    Rule(
        "depends_on",
        "DEPENDS_ON",
        "A product depends on every supplier of every item in its bill of materials, at any depth.",
        """
        MATCH path = (p:Product)-[:REQUIRES*1..4]->(i:Item)<-[:SUPPLIES]-(s:Supplier)
        WITH p, s, min(length(path)) AS depth, collect([n IN nodes(path) | n.id])[0] AS via
        MERGE (p)-[r:DEPENDS_ON]->(s) SET r.rule = 'depends_on', r.tier = s.tier, r.via = via
        RETURN count(r) AS n
        """,
    ),
    Rule(
        "supplier_exposed",
        "EXPOSED_TO",
        "A supplier is exposed to an active or forecast risk event that affects it, its site, its port, "
        "its chokepoints, its country or an item it supplies.",
        """
        MATCH (e:RiskEvent) WHERE e.status <> 'resolved'
        MATCH (e)-[a:AFFECTS]->(t)
        MATCH (s:Supplier)
        WHERE t = s
           OR EXISTS { (s)-[:OPERATES]->(t) }
           OR EXISTS { (s)-[:OPERATES]->(:Facility)-[:SERVED_BY]->(t) }
           OR EXISTS { (s)-[:ROUTED_THROUGH]->(t) }
           OR EXISTS { (s)-[:LOCATED_IN]->(t) }
           OR EXISTS { (s)-[:SUPPLIES]->(t) }
        WITH s, e, max(e.severity * coalesce(e.probability, 1) * coalesce(a.magnitude, 1)) AS score,
             collect(DISTINCT t.id) AS via
        MERGE (s)-[r:EXPOSED_TO]->(e) SET r.rule = 'supplier_exposed', r.score = round(score, 2), r.path = via
        RETURN count(r) AS n
        """,
    ),
    Rule(
        "product_exposed",
        "EXPOSED_TO",
        "A product is exposed to a risk event through any supplier it depends on.",
        """
        MATCH (p:Product)-[d:DEPENDS_ON]->(s:Supplier)-[x:EXPOSED_TO]->(e:RiskEvent)
        WITH p, e, max(x.score / d.tier) AS score, collect(DISTINCT s.id) AS via
        MERGE (p)-[r:EXPOSED_TO]->(e) SET r.rule = 'product_exposed', r.score = round(score, 2), r.path = via
        RETURN count(r) AS n
        """,
    ),
    Rule(
        "customer_exposed",
        "EXPOSED_TO",
        "A customer with open orders for an exposed product is exposed to the same event.",
        """
        MATCH (c:Customer)-[:PLACED]->(o:SalesOrder)-[:FOR_PRODUCT]->(p:Product)-[x:EXPOSED_TO]->(e:RiskEvent)
        WHERE o.status IN ['open', 'in_production']
        WITH c, e, max(x.score) AS score, collect(DISTINCT p.id) AS via, sum(o.value_usd) AS value
        MERGE (c)-[r:EXPOSED_TO]->(e)
        SET r.rule = 'customer_exposed', r.score = round(score, 2), r.path = via, r.open_value_usd = value
        RETURN count(r) AS n
        """,
    ),
]


def clear_inferred() -> None:
    run("MATCH ()-[r]->() WHERE r.rule IS NOT NULL DELETE r")


def materialise() -> dict[str, int]:
    """Recompute every inferred relationship. Rules run in order (later rules build on earlier ones)."""
    clear_inferred()
    return {rule.name: run(rule.cypher)[0]["n"] for rule in RULES}
