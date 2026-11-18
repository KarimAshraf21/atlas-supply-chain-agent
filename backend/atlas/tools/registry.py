"""The Atlas tool layer.

One set of typed, documented functions, exposed three ways:
* to the LangGraph agents (as LangChain tools),
* to any MCP client (``atlas mcp`` / ``/mcp``),
* to the web app (REST).

Every tool returns a JSON-serialisable dict. A ``ui`` key, when present, carries
data meant for the interface (graph highlights, full reports) and is stripped
before the result is shown to a language model, keeping prompts small.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

from pydantic import BaseModel, Field

from ..reasoning import Disruption, ImpactReport, assess, assess_events, get_snapshot
from ..reasoning import queries as Q
from ..reasoning.spof import concentrations, hidden_dependencies, single_points

ToolFn = Callable[..., dict[str, Any]]
TOOLS: dict[str, ToolFn] = {}


def tool(fn: ToolFn) -> ToolFn:
    TOOLS[fn.__name__] = fn
    return fn


def _money(x: float) -> str:
    return f"${x / 1e6:,.1f}M" if abs(x) >= 1e5 else f"${x:,.0f}"


def summarise_impact(r: ImpactReport, top: int = 6) -> dict[str, Any]:
    snap = get_snapshot()
    names = snap.name
    t = r.totals
    return {
        "as_of": r.as_of,
        "headline": {
            "lost_revenue": _money(t["lost_revenue_usd"]),
            "lost_revenue_after_mitigation": _money(t["mitigated_lost_revenue_usd"]),
            "orders_at_risk": int(t["orders_at_risk"]),
            "order_value_at_risk": _money(t["order_value_at_risk_usd"]),
            "penalty_exposure": _money(t["penalty_exposure_usd"]),
            "penalties_without_force_majeure": _money(t["unprotected_penalty_usd"]),
            "lanes_affected": int(t["lanes_affected"]),
            "lanes_blocked": int(t["lanes_blocked"]),
            "scenario_probability": t["probability"],
        },
        "lanes": [
            {
                "lane": e.name,
                "added_days": e.delay_days,
                "blocked": e.blocked,
                "rerouted_via": names(e.rerouted_via) if e.rerouted_via in snap.labels else e.rerouted_via,
                "extra_cost_pct": e.extra_cost_pct,
            }
            for e in r.lanes[:top]
        ],
        "component_stockouts": [
            {
                "component": sf.component_name,
                "factory": names(sf.factory),
                "days_of_cover": sf.days_of_cover,
                "stockout_in_days": sf.stockout_day,
                "shortage_days": sf.shortage_days,
                "with_mitigation_stockout_in_days": sf.mitigated_stockout_day,
                "why": " → ".join(names(x) for x in sf.drivers[0]) if sf.drivers else "",
            }
            for sf in r.shortfalls[:top]
        ],
        "products": [
            {
                "product": p.name,
                "first_impact_in_days": p.first_impact_day,
                "lost_units": p.lost_units,
                "lost_revenue": _money(p.lost_revenue_usd),
                "after_mitigation": _money(p.mitigated_lost_revenue_usd),
            }
            for p in r.products[:top]
        ],
        "top_orders_at_risk": [
            {
                "order": o.order,
                "customer": o.customer_name,
                "product": names(o.product),
                "due": o.due_date,
                "value": _money(o.value_usd),
                "slip_days": o.expected_slip_days,
                "reason": o.reason,
                "penalty": _money(o.penalty_usd),
                "force_majeure": o.force_majeure_protected,
            }
            for o in r.orders[:top]
        ],
        "mitigations": [
            {"action": m.action, "detail": m.detail, "cost": m.cost_note} for m in r.mitigations[: top + 2]
        ],
        "market_signals": r.market_signals,
        "assumptions": r.assumptions,
        "ui": {"type": "impact", "report": r.model_dump(mode="json"), "highlight": r.highlight["nodes"]},
    }


# ===================================================================== tools
@tool
def search_entities(query: str, entity_type: str | None = None) -> dict[str, Any]:
    """Find graph entities by name in English or Arabic (fuzzy). Use this first to turn names the user
    mentions (suppliers, ports, products, customers, chokepoints, events) into entity ids.
    entity_type optionally restricts results, e.g. "Supplier", "Port", "Chokepoint", "Product", "Customer"."""
    rows = Q.search_entities(query, labels=[entity_type] if entity_type else None)
    return {"results": rows, "ui": {"type": "entities", "highlight": [r["id"] for r in rows[:5]]}}


@tool
def get_entity(entity_id: str) -> dict[str, Any]:
    """Get an entity's properties and its direct relationships (neighbours) by id."""
    p = Q.profile(entity_id)
    return {**p, "ui": {"type": "entity", "highlight": [entity_id] + [n["id"] for n in p.get("neighbours", [])][:25]}}


@tool
def list_risk_events(status: Literal["active", "forecast", "resolved", "all"] = "all") -> dict[str, Any]:
    """List known risk events (conflicts, weather, strikes, export controls, insolvencies…) with their
    status, severity (1-5), probability and what they affect."""
    snap = get_snapshot()
    out = []
    for ev in snap.of("RiskEvent"):
        p = snap.props[ev]
        if status != "all" and p["status"] != status:
            continue
        out.append(
            {
                "id": ev,
                "title": p["title"],
                "title_ar": p.get("title_ar"),
                "type": p["type"],
                "status": p["status"],
                "severity": p["severity"],
                "probability": p.get("probability"),
                "start_date": p.get("start_date"),
                "expected_duration_days": p.get("expected_duration_days"),
                "affects": [snap.name(t) for t in snap.target_ids(ev, "AFFECTS")],
            }
        )
    out.sort(key=lambda e: (-e["severity"] * (e["probability"] or 1), e["id"]))
    return {"events": out, "ui": {"type": "events", "highlight": [e["id"] for e in out[:8]]}}


@tool
def assess_risk_events(event_ids: list[str], duration_days: int | None = None) -> dict[str, Any]:
    """Quantify the business impact of one or more risk events (by id, e.g. RE-REDSEA): rerouted or blocked
    lanes, component stock-outs by factory, lost production and revenue, sales orders and customers at risk,
    contractual penalties (and whether force majeure protects us) and ranked mitigations.
    duration_days optionally overrides how long the events last (what-if)."""
    return summarise_impact(assess_events(get_snapshot(), event_ids, duration_days))


class DisruptionInput(BaseModel):
    target: str = Field(description="Entity id to disrupt: chokepoint, port, lane, supplier or facility.")
    impact: Literal["closure", "delay", "capacity_reduction", "insolvency"] = "closure"
    duration_days: int = 30
    magnitude: float = Field(1.0, description="0-1 share of capacity/flow lost (capacity_reduction).")
    added_days: int | None = Field(None, description="Extra transit days (delay).")
    start_in_days: int = 0


@tool
def simulate_scenario(disruptions: list[DisruptionInput]) -> dict[str, Any]:
    """Run a what-if scenario that is NOT a known event, e.g. "close the Suez Canal for 45 days" or
    "FormoSiC loses 50% capacity for 2 months". Resolve names to ids with search_entities first.
    Returns the same impact analysis as assess_risk_events."""
    ds = [Disruption(**(d.model_dump() if isinstance(d, BaseModel) else d)) for d in disruptions]
    return summarise_impact(assess(get_snapshot(), ds))


@tool
def structural_risks(focus: Literal["single_points", "hidden_dependencies", "concentration", "all"] = "all") -> dict:
    """Find structural weaknesses before anything breaks: single-sourced items with no qualified alternative,
    hidden tier-2 dependencies (several suppliers secretly relying on one upstream source) and
    concentration of inbound supply by chokepoint and country."""
    snap = get_snapshot()
    out: dict[str, Any] = {}
    hl: list[str] = []
    if focus in ("single_points", "all"):
        sp = single_points(snap)[:10]
        out["single_points"] = [
            {
                "item": x.item_name,
                "supplier": x.supplier_name,
                "tier": x.tier,
                "country": x.country,
                "qualified_alternative": x.has_qualified_alternative,
                "revenue_dependent": _money(x.revenue_dependent_usd),
                "products": len(x.used_in_products),
            }
            for x in sp
        ]
        hl += [x.supplier for x in sp[:6]] + [x.item for x in sp[:6]]
    if focus in ("hidden_dependencies", "all"):
        hd = hidden_dependencies(snap)[:5]
        out["hidden_dependencies"] = [
            {"upstream": h.upstream_name, "health": h.financial_health, "explanation": h.explanation} for h in hd
        ]
        hl += [h.upstream_supplier for h in hd] + [t for h in hd[:2] for t in h.tier1_suppliers]
    if focus in ("concentration", "all"):
        cc = concentrations(snap)[:8]
        out["concentration"] = [
            {
                "dimension": c.dimension,
                "name": c.name,
                "share_of_inbound_lanes_pct": c.share_of_inbound_lanes_pct,
                "suppliers": len(c.suppliers),
            }
            for c in cc
        ]
        hl += [c.key for c in cc if c.dimension == "chokepoint"][:4]
    out["ui"] = {"type": "structural", "highlight": hl}
    return out


@tool
def find_alternatives(entity_id: str) -> dict[str, Any]:
    """Alternatives for a component, material or supplier: other active suppliers (with share), qualified
    but unused suppliers (with ramp-up time and max share) and contingency shipping lanes."""
    snap = get_snapshot()
    items = [entity_id] if snap.is_a(entity_id, "Item") else snap.target_ids(entity_id, "SUPPLIES")
    out = []
    for item in items:
        active = [
            {
                "supplier": snap.name(s),
                "id": s,
                "share_pct": p.get("share_pct"),
                "lead_time_days": p.get("lead_time_days"),
                "country": snap.props[s].get("country_code"),
            }
            for s, p in snap.sources(item, "SUPPLIES")
            if s != entity_id
        ]
        qualified = [
            {
                "supplier": snap.name(s),
                "id": s,
                "max_share_pct": p.get("max_share_pct"),
                "ramp_up_days": p.get("ramp_up_days"),
                "unit_cost_usd": p.get("unit_cost_usd"),
            }
            for s, p in snap.sources(item, "QUALIFIED_FOR")
        ]
        out.append(
            {"item": snap.name(item), "id": item, "other_active_suppliers": active, "qualified_alternatives": qualified}
        )
    lanes = []
    sups = [entity_id] if snap.is_a(entity_id, "Supplier") else snap.source_ids(entity_id, "SUPPLIES")
    for s in sups:
        for lane in snap.target_ids(s, "SHIPS_VIA"):
            for alt, p in snap.sources(lane, "ALTERNATIVE_TO"):
                lanes.append({"for_lane": snap.name(lane), "alternative": snap.name(alt), **p})
    hl = [entity_id] + [a["id"] for o in out for a in o["other_active_suppliers"] + o["qualified_alternatives"]]
    return {"items": out, "contingency_lanes": lanes[:8], "ui": {"type": "alternatives", "highlight": hl}}


@tool
def trace_dependencies(product_id: str) -> dict[str, Any]:
    """Trace a product's full multi-tier supply chain: bill of materials, every supplier by tier, their
    countries and the chokepoints their goods pass through."""
    snap = get_snapshot()
    rows, hl, seen = [], [product_id], set()

    def walk(item: str, depth: int) -> None:
        for child, p in snap.targets(item, "REQUIRES"):
            for sup, sp in snap.sources(child, "SUPPLIES"):
                key = (child, sup)
                if key in seen:
                    continue
                seen.add(key)
                chokes = sorted(
                    {
                        snap.name(c)
                        for lane in snap.target_ids(sup, "SHIPS_VIA")
                        if not snap.props[lane].get("is_contingency")
                        for c in snap.target_ids(lane, "TRANSITS")
                    }
                )
                rows.append(
                    {
                        "depth": depth,
                        "item": snap.name(child),
                        "qty": p.get("quantity"),
                        "supplier": snap.name(sup),
                        "tier": snap.props[sup].get("tier"),
                        "country": snap.props[sup].get("country_code"),
                        "share_pct": sp.get("share_pct"),
                        "health": snap.props[sup].get("financial_health"),
                        "chokepoints": chokes,
                    }
                )
                hl.extend([child, sup])
            walk(child, depth + 1)

    walk(product_id, 1)
    return {"product": snap.name(product_id), "supply_chain": rows, "ui": {"type": "trace", "highlight": hl}}


@tool
def search_documents(query: str, kind: Literal["news", "contract", "report", "email", "any"] = "any") -> dict:
    """Full-text search over news (English and Arabic), contract texts and internal reports. Returns excerpts
    with document ids so answers can cite sources. Use for questions about clauses, force majeure,
    penalties, what the news says or what internal reports recommend."""
    rows = Q.read_cypher(
        """
        CALL db.index.fulltext.queryNodes('document_text', $q) YIELD node, score
        WHERE $kind = 'any' OR node.kind = $kind
        OPTIONAL MATCH (node)-[:MENTIONS|EVIDENCES]->(m)
        RETURN node.id AS id, node.title AS title, node.kind AS kind, node.language AS language,
               node.published_date AS published, node.source AS source, substring(node.text, 0, 900) AS excerpt,
               collect(DISTINCT m.id)[0..8] AS mentions, score
        ORDER BY score DESC LIMIT 5
        """,
        {"q": query, "kind": kind},
    )
    return {"documents": rows, "ui": {"type": "documents", "highlight": [r["id"] for r in rows]}}


@tool
def query_graph(cypher: str) -> dict[str, Any]:
    """Run a read-only Cypher query against the knowledge graph for questions no other tool answers
    (aggregations, rankings, custom filters). Follow the ontology schema exactly. Max 100 rows."""
    try:
        return {"rows": Q.read_cypher(cypher)}
    except Exception as exc:  # surface the error so the model can fix its query
        return {"error": str(exc)[:500]}


def strip_ui(result: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in result.items() if k != "ui"}
