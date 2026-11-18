"""Structural risk analysis: single points of failure and hidden concentration.

Finds what a supply-chain manager most needs to know before anything breaks:
* single-sourced items with no qualified alternative,
* chokepoint and country concentration of inbound supply,
* *hidden* tier-2 dependencies — several tier-1 suppliers secretly relying on the
  same upstream source (diversification that isn't).
"""

from __future__ import annotations

from collections import defaultdict

from pydantic import BaseModel

from .snapshot import Snapshot


class SinglePoint(BaseModel):
    item: str
    item_name: str
    supplier: str
    supplier_name: str
    tier: int
    country: str
    used_in_products: list[str]
    revenue_dependent_usd: float
    has_qualified_alternative: bool


class Concentration(BaseModel):
    dimension: str  # chokepoint | country
    key: str
    name: str
    share_of_inbound_lanes_pct: float
    suppliers: list[str]
    critical_items: list[str]


class HiddenDependency(BaseModel):
    upstream_supplier: str
    upstream_name: str
    material: str
    tier1_suppliers: list[str]
    items: list[str]
    financial_health: str | None
    explanation: str


class StructuralRisk(BaseModel):
    single_points: list[SinglePoint]
    concentrations: list[Concentration]
    hidden_dependencies: list[HiddenDependency]


def _products_using(snap: Snapshot, item: str) -> set[str]:
    """Products whose BOM contains `item` at any depth."""
    seen, frontier, products = {item}, [item], set()
    while frontier:
        x = frontier.pop()
        for parent in snap.source_ids(x, "REQUIRES"):
            if parent in seen:
                continue
            seen.add(parent)
            if snap.is_a(parent, "Product"):
                products.add(parent)
            frontier.append(parent)
    return products


def _annual_revenue(snap: Snapshot, product: str) -> float:
    vol = next((p.get("capacity_units_per_month", 0) / 1.25 for _, p in snap.sources(product, "PRODUCES")), 0)
    return vol * 12 * snap.props[product].get("unit_price_usd", 0.0)


def single_points(snap: Snapshot) -> list[SinglePoint]:
    out = []
    for item in snap.of("Item"):
        sources = snap.sources(item, "SUPPLIES")
        if len(sources) != 1:
            continue
        supplier, _ = sources[0]
        qualified = bool(snap.sources(item, "QUALIFIED_FOR"))
        products = _products_using(snap, item)
        if not products:
            continue
        out.append(
            SinglePoint(
                item=item,
                item_name=snap.name(item),
                supplier=supplier,
                supplier_name=snap.name(supplier),
                tier=snap.props[supplier].get("tier", 1),
                country=snap.props[supplier].get("country_code", ""),
                used_in_products=sorted(products),
                revenue_dependent_usd=round(sum(_annual_revenue(snap, p) for p in products), -3),
                has_qualified_alternative=qualified,
            )
        )
    return sorted(out, key=lambda x: (x.has_qualified_alternative, x.tier, -x.revenue_dependent_usd))


def concentrations(snap: Snapshot) -> list[Concentration]:
    tier1 = [s for s in snap.of("Supplier") if snap.props[s].get("tier") == 1]
    lanes = {lane: s for s in tier1 for lane in snap.target_ids(s, "SHIPS_VIA")}
    total = max(1, len(lanes))
    by_choke: dict[str, set[str]] = defaultdict(set)
    for lane in lanes:
        for ck in snap.target_ids(lane, "TRANSITS"):
            by_choke[ck].add(lane)
    out = []
    for ck, ls in by_choke.items():
        sups = sorted({lanes[lane] for lane in ls})
        crit = sorted({i for s in sups for i, p in snap.targets(s, "SUPPLIES") if p.get("share_pct", 0) >= 50})
        out.append(
            Concentration(
                dimension="chokepoint",
                key=ck,
                name=snap.name(ck),
                share_of_inbound_lanes_pct=round(100 * len(ls) / total, 1),
                suppliers=sups,
                critical_items=crit,
            )
        )
    by_country: dict[str, list[str]] = defaultdict(list)
    for s in tier1:
        by_country[snap.props[s].get("country_code", "")].append(s)
    for c, sups in by_country.items():
        n_lanes = sum(len(snap.target_ids(s, "SHIPS_VIA")) for s in sups)
        crit = sorted({i for s in sups for i, p in snap.targets(s, "SUPPLIES") if p.get("share_pct", 0) >= 50})
        out.append(
            Concentration(
                dimension="country",
                key=c,
                name=snap.name(c),
                share_of_inbound_lanes_pct=round(100 * n_lanes / total, 1),
                suppliers=sorted(sups),
                critical_items=crit,
            )
        )
    return sorted(out, key=lambda x: -x.share_of_inbound_lanes_pct)


def hidden_dependencies(snap: Snapshot) -> list[HiddenDependency]:
    out = []
    for up in snap.of("Supplier"):
        if snap.props[up].get("tier", 1) < 2:
            continue
        buyers = [b for b in snap.target_ids(up, "SUPPLIES_TO") if snap.is_a(b, "Supplier")]
        tier1 = [b for b in buyers if snap.props[b].get("tier") == 1]
        if len(tier1) < 2:
            continue
        for material, p in snap.targets(up, "SUPPLIES"):
            if p.get("share_pct", 0) < 60:
                continue
            items = sorted(
                {x for b in tier1 for x in snap.target_ids(b, "SUPPLIES") if material in snap.target_ids(x, "REQUIRES")}
            )
            if not items:
                continue
            health = snap.props[up].get("financial_health")
            out.append(
                HiddenDependency(
                    upstream_supplier=up,
                    upstream_name=snap.name(up),
                    material=material,
                    tier1_suppliers=sorted(tier1),
                    items=items,
                    financial_health=health,
                    explanation=(
                        f"{', '.join(snap.name(b) for b in tier1)} look like independent sources of "
                        f"{', '.join(snap.name(i) for i in items)}, but all depend on {snap.name(up)} "
                        f"({p.get('share_pct'):.0f}% of {snap.name(material)})."
                        + (f" {snap.name(up)} is rated '{health}'." if health in ("watch", "distressed") else "")
                    ),
                )
            )
    return sorted(out, key=lambda x: (x.financial_health != "distressed", -len(x.tier1_suppliers)))


def structural_risk(snap: Snapshot) -> StructuralRisk:
    return StructuralRisk(
        single_points=single_points(snap),
        concentrations=concentrations(snap)[:12],
        hidden_dependencies=hidden_dependencies(snap),
    )
