"""Disruption impact propagation — the core of Atlas' reasoning layer.

Given one or more disruptions (from real risk events or a what-if scenario),
propagate their effect through the supply network, day by day:

    disruption ─▶ lanes (reroute or block) ─▶ supplier flows (tier N … tier 1)
               ─▶ factory component inventory (days of cover) ─▶ production shortfall
               ─▶ products ─▶ open sales orders ─▶ customers, contracts & penalties

Every number is computed from the graph; nothing is estimated by an LLM.
Every result carries the path of node ids that produced it.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel, Field

from ..seed.generator import AS_OF
from .snapshot import Snapshot

HORIZON_DAYS = 150
UPSTREAM_BUFFER_DAYS = 30  # inventory held by suppliers of their own inputs
SURGE_SHARE = 0.15  # extra share an unaffected active supplier can absorb
OPEN_STATUSES = {"open", "in_production"}

Impact = Literal["closure", "delay", "capacity_reduction", "price_increase", "insolvency"]


# =============================================================== input models
class Disruption(BaseModel):
    target: str = Field(description="Id of the disrupted entity (chokepoint, port, lane, supplier, facility…).")
    impact: Impact = "closure"
    magnitude: float = Field(1.0, ge=0, le=1, description="Share of flow or capacity lost.")
    added_days: int | None = Field(None, description="Extra transit days for delays.")
    duration_days: int = Field(30, ge=1)
    start_in_days: int = Field(0, ge=0)
    probability: float = Field(1.0, ge=0, le=1)
    source_event: str | None = None


def disruptions_from_events(
    snap: Snapshot, event_ids: list[str], duration_override: int | None = None
) -> list[Disruption]:
    out: list[Disruption] = []
    for ev in event_ids:
        p = snap.props.get(ev)
        if not p:
            raise KeyError(f"Unknown risk event: {ev}")
        start = date.fromisoformat(p["start_date"]) if p.get("start_date") else AS_OF
        total = duration_override or p.get("expected_duration_days") or 30
        elapsed = max(0, (AS_OF - start).days)
        remaining = max(1, total - elapsed) if duration_override is None else total
        for target, props in snap.targets(ev, "AFFECTS"):
            out.append(
                Disruption(
                    target=target,
                    impact=props["impact"],
                    magnitude=props.get("magnitude", 1.0),
                    added_days=props.get("added_days"),
                    duration_days=remaining,
                    start_in_days=max(0, (start - AS_OF).days),
                    probability=p.get("probability", 1.0),
                    source_event=ev,
                )
            )
    return out


# ============================================================== output models
class LaneEffect(BaseModel):
    lane: str
    name: str
    delay_days: int
    blocked: bool
    rerouted_via: str | None = None
    extra_cost_pct: float = 0.0
    cause: list[str]


class ComponentShortfall(BaseModel):
    factory: str
    component: str
    component_name: str
    days_of_cover: float
    stockout_day: int | None
    shortage_days: int
    peak_shortage_pct: float
    mitigated_stockout_day: int | None
    mitigated_shortage_days: int
    drivers: list[list[str]]


class ProductImpact(BaseModel):
    product: str
    name: str
    factory: str
    first_impact_day: int
    lost_units: int
    lost_revenue_usd: float
    mitigated_lost_units: int
    mitigated_lost_revenue_usd: float
    bottlenecks: list[str]


class OrderRisk(BaseModel):
    order: str
    customer: str
    customer_name: str
    product: str
    due_date: str
    value_usd: float
    expected_slip_days: int
    reason: Literal["supply_shortfall", "outbound_delay"]
    penalty_usd: float
    force_majeure_protected: bool


class Mitigation(BaseModel):
    action: str
    detail: str
    targets: list[str]
    cost_note: str | None = None


class ImpactReport(BaseModel):
    as_of: str
    disruptions: list[Disruption]
    lanes: list[LaneEffect]
    shortfalls: list[ComponentShortfall]
    products: list[ProductImpact]
    orders: list[OrderRisk]
    mitigations: list[Mitigation]
    market_signals: list[str]
    totals: dict[str, float]
    highlight: dict[str, list[str]]
    assumptions: list[str]


# ============================================================ internal types
@dataclass
class Hit:
    """A supply flow `supplier → item → buyer` losing `fraction` of volume in [start, end)."""

    supplier: str
    item: str
    buyer: str
    fraction: float
    start: int
    end: int
    path: list[str] = field(default_factory=list)


# ================================================================== engine
class ImpactEngine:
    def __init__(self, snap: Snapshot, as_of: date = AS_OF) -> None:
        self.s = snap
        self.as_of = as_of
        self.company = next(iter(snap.of("Company")))
        self.our_facilities = set(snap.target_ids(self.company, "OPERATES"))

    # --------------------------------------------------------------- lanes
    def _lanes_touching(self, target: str) -> list[str]:
        s = self.s
        if s.is_a(target, "Chokepoint"):
            lanes = s.source_ids(target, "TRANSITS")
        elif s.is_a(target, "Port"):
            lanes = s.source_ids(target, "ORIGIN") + s.source_ids(target, "DESTINATION")
        elif s.is_a(target, "ShippingLane"):
            lanes = [target]
        else:
            return []
        return [lane for lane in lanes if not s.props[lane].get("is_contingency")]

    def _lane_disrupted(self, lane: str, closed: set[str]) -> bool:
        s = self.s
        touched = set(s.target_ids(lane, "TRANSITS")) | set(s.target_ids(lane, "ORIGIN"))
        touched |= set(s.target_ids(lane, "DESTINATION"))
        return bool(touched & closed) or lane in closed

    def _dynamic_reroute(self, lane: str, closed: set[str]) -> tuple[int, float, str] | None:
        """Re-plan a sea lane around closed chokepoints: (extra days, extra cost %, chokepoints on new route)."""
        from ..seed.catalog import CHOKEPOINTS, PORTS
        from ..seed.routing import chokepoints_on, sea_days, sea_route

        s = self.s
        p = s.props[lane]
        origin, dest = s.one(lane, "ORIGIN"), s.one(lane, "DESTINATION")
        if p.get("mode") != "sea" or origin not in PORTS or dest not in PORTS or {origin, dest} & closed:
            return None
        route = sea_route(origin, dest, frozenset(c for c in closed if c in CHOKEPOINTS))
        if route is None:
            return None
        path, km = route
        extra_days = max(1, sea_days(km) - p["transit_days"])
        new_cost = 600 + km * 0.16 + 450
        extra_cost = round(100 * (new_cost - p["cost_per_teu_usd"]) / p["cost_per_teu_usd"], 1)
        via = ", ".join(CHOKEPOINTS[c][0] for c in chokepoints_on(path)) or "open sea"
        return extra_days, extra_cost, via

    def lane_effects(self, ds: list[Disruption]) -> dict[str, LaneEffect]:
        s = self.s
        closed = {d.target for d in ds if d.impact == "closure" and d.magnitude >= 0.5}
        effects: dict[str, LaneEffect] = {}
        for d in ds:
            for lane in self._lanes_touching(d.target):
                cause = [x for x in (d.source_event, d.target, lane) if x]
                if d.impact == "closure" and d.magnitude >= 0.5:
                    alts = [
                        (alt, p)
                        for alt, p in s.sources(lane, "ALTERNATIVE_TO")
                        if s.props[alt]["mode"] != "air" and not self._lane_disrupted(alt, closed)
                    ]
                    dynamic = None if alts else self._dynamic_reroute(lane, closed)
                    if alts:
                        alt, p = min(alts, key=lambda a: a[1].get("extra_days", 0))
                        eff = LaneEffect(
                            lane=lane,
                            name=s.name(lane),
                            delay_days=max(1, p.get("extra_days", 0)),
                            blocked=False,
                            rerouted_via=alt,
                            extra_cost_pct=p.get("extra_cost_pct", 0.0),
                            cause=cause,
                        )
                    elif dynamic:
                        extra_days, extra_cost, via = dynamic
                        eff = LaneEffect(
                            lane=lane,
                            name=s.name(lane),
                            delay_days=extra_days,
                            blocked=False,
                            rerouted_via=f"via {via}",
                            extra_cost_pct=extra_cost,
                            cause=cause,
                        )
                    else:
                        eff = LaneEffect(
                            lane=lane, name=s.name(lane), delay_days=d.duration_days, blocked=True, cause=cause
                        )
                else:
                    delay = d.added_days or max(1, round(10 * d.magnitude))
                    eff = LaneEffect(lane=lane, name=s.name(lane), delay_days=delay, blocked=False, cause=cause)
                prev = effects.get(lane)
                if prev is None:
                    effects[lane] = eff
                else:  # several disruptions on one lane: keep the worst, remember every cause
                    worst = eff if eff.delay_days > prev.delay_days else prev
                    worst.cause = list(dict.fromkeys(prev.cause + eff.cause))
                    effects[lane] = worst
        return effects

    # -------------------------------------------------------- supply graph
    def _buyers_at(self, port: str, supplier: str) -> list[str]:
        """Buyers of `supplier` whose site is served by `port` (our factories or downstream suppliers)."""
        s = self.s
        facilities = set(s.source_ids(port, "SERVED_BY"))
        buyers = []
        for b in s.target_ids(supplier, "SUPPLIES_TO"):
            if s.is_a(b, "Company"):
                buyers += [f for f in facilities if f in self.our_facilities and s.is_a(f, "Factory")]
            elif set(s.target_ids(b, "OPERATES")) & facilities:
                buyers.append(b)
        return buyers

    def _items_flowing(self, supplier: str, buyer: str) -> list[tuple[str, float]]:
        """Items (with supplier share) that `supplier` sells and `buyer` consumes."""
        s = self.s
        supplied = {item: p.get("share_pct", 100.0) / 100 for item, p in s.targets(supplier, "SUPPLIES")}
        if s.is_a(buyer, "Facility"):
            consumed = set(s.target_ids(buyer, "STOCKS"))
        else:
            consumed = {m for x in s.target_ids(buyer, "SUPPLIES") for m in s.target_ids(x, "REQUIRES")}
        return [(i, share) for i, share in supplied.items() if i in consumed]

    def _all_buyers(self, supplier: str) -> list[str]:
        s = self.s
        buyers = []
        for b in s.target_ids(supplier, "SUPPLIES_TO"):
            if s.is_a(b, "Company"):
                buyers += [f for f in self.our_facilities if s.is_a(f, "Factory")]
            else:
                buyers.append(b)
        return buyers

    def initial_hits(self, ds: list[Disruption], lanes: dict[str, LaneEffect]) -> tuple[list[Hit], list[str]]:
        s = self.s
        hits: list[Hit] = []
        signals: list[str] = []
        by_lane_start = {d.target: d.start_in_days for d in ds}

        for lane, eff in lanes.items():
            dest = s.one(lane, "DESTINATION")
            start = next((by_lane_start[c] for c in eff.cause if c in by_lane_start), 0)
            for sup in s.source_ids(lane, "SHIPS_VIA"):
                if not s.is_a(sup, "Supplier") or dest is None:
                    continue
                for buyer in self._buyers_at(dest, sup):
                    for item, share in self._items_flowing(sup, buyer):
                        hits.append(
                            Hit(sup, item, buyer, share, start, start + eff.delay_days, [*eff.cause, sup, item, buyer])
                        )

        for d in ds:
            t = d.target
            if d.impact in ("capacity_reduction", "insolvency"):
                supplier = t if s.is_a(t, "Supplier") else None
                if supplier is None and s.is_a(t, "Facility"):
                    supplier = next((o for o in s.source_ids(t, "OPERATES") if s.is_a(o, "Supplier")), None)
                if supplier:
                    for buyer in self._all_buyers(supplier):
                        for item, share in self._items_flowing(supplier, buyer):
                            hits.append(
                                Hit(
                                    supplier,
                                    item,
                                    buyer,
                                    share * d.magnitude,
                                    d.start_in_days,
                                    d.start_in_days + d.duration_days,
                                    [x for x in (d.source_event, t, supplier, item, buyer) if x],
                                )
                            )
            if d.impact == "price_increase" or (s.is_a(t, "Item") and d.impact == "capacity_reduction"):
                signals.append(
                    f"{s.name(t)}: {d.impact.replace('_', ' ')} ~{round(d.magnitude * 100)}%"
                    + (f" ({s.name(d.source_event)})" if d.source_event else "")
                )
        return hits, signals

    def propagate(self, hits: list[Hit]) -> list[Hit]:
        """Push tier-N hits downstream until they reach our factories."""
        s = self.s
        final: list[Hit] = []
        queue = list(hits)
        guard = 0
        while queue and guard < 10_000:
            guard += 1
            h = queue.pop()
            if s.is_a(h.buyer, "Facility"):
                final.append(h)
                continue
            # the buyer is a supplier: its upstream buffer absorbs part of the gap
            width = h.end - h.start
            if h.fraction * width <= UPSTREAM_BUFFER_DAYS or h.fraction <= 0:
                continue
            start = h.start + math.ceil(UPSTREAM_BUFFER_DAYS / h.fraction)
            produced = [x for x in s.target_ids(h.buyer, "SUPPLIES") if h.item in s.target_ids(x, "REQUIRES")]
            for x in produced:
                for nxt in self._all_buyers(h.buyer):
                    for item, share in self._items_flowing(h.buyer, nxt):
                        if item == x:
                            queue.append(Hit(h.buyer, x, nxt, h.fraction * share, start, h.end, [*h.path, x, nxt]))
        return final

    # -------------------------------------------------- inventory simulation
    def _mitigation_capacity(self, component: str, hit_suppliers: set[str]) -> list[tuple[int, float]]:
        """(available_from_day, share) for qualified alternates and unaffected active suppliers."""
        s = self.s
        caps: list[tuple[int, float]] = []
        for sup, p in s.sources(component, "QUALIFIED_FOR"):
            if sup not in hit_suppliers:
                caps.append((p.get("ramp_up_days", 60), p.get("max_share_pct", 30) / 100))
        for sup, _ in s.sources(component, "SUPPLIES"):
            if sup not in hit_suppliers:
                caps.append((14, SURGE_SHARE))
        return caps

    @staticmethod
    def _simulate(cover: float, missing: list[float]) -> tuple[list[float], int | None]:
        inv, short, stockout = cover, [], None
        for t, miss in enumerate(missing):
            if inv >= miss:
                inv -= miss
                short.append(0.0)
            else:
                short.append(miss - inv)
                inv = 0.0
                if stockout is None:
                    stockout = t
        return short, stockout

    def shortfalls(
        self, hits: list[Hit]
    ) -> tuple[list[ComponentShortfall], dict[tuple[str, str], tuple[list[float], list[float]]]]:
        s = self.s
        grouped: dict[tuple[str, str], list[Hit]] = defaultdict(list)
        for h in hits:
            grouped[(h.buyer, h.item)].append(h)

        results, series = [], {}
        for (fac, comp), hs in grouped.items():
            missing = [0.0] * HORIZON_DAYS
            for h in hs:
                for t in range(max(0, h.start), min(HORIZON_DAYS, h.end)):
                    missing[t] += h.fraction
            missing = [min(1.0, m) for m in missing]
            cover = next((p.get("days_of_cover", 0.0) for c, p in s.targets(fac, "STOCKS") if c == comp), 0.0)

            caps = self._mitigation_capacity(comp, {h.supplier for h in hs})
            mitigated = [max(0.0, m - sum(sh for day, sh in caps if t >= day)) for t, m in enumerate(missing)]

            short, stockout = self._simulate(cover, missing)
            m_short, m_stockout = self._simulate(cover, mitigated)
            series[(fac, comp)] = (short, m_short)
            if stockout is None:
                continue
            drivers = sorted({tuple(h.path) for h in hs}, key=len)[:6]
            results.append(
                ComponentShortfall(
                    factory=fac,
                    component=comp,
                    component_name=s.name(comp),
                    days_of_cover=cover,
                    stockout_day=stockout,
                    shortage_days=sum(1 for x in short if x > 0),
                    peak_shortage_pct=round(100 * max(short), 1),
                    mitigated_stockout_day=m_stockout,
                    mitigated_shortage_days=sum(1 for x in m_short if x > 0),
                    drivers=[list(p) for p in drivers],
                )
            )
        results.sort(key=lambda r: (r.stockout_day, -r.peak_shortage_pct))
        return results, series

    # ----------------------------------------------------------- products
    def products(self, series, ds: list[Disruption]) -> list[ProductImpact]:
        s = self.s
        factory_cuts: dict[str, list[float]] = defaultdict(lambda: [0.0] * HORIZON_DAYS)
        for d in ds:
            if d.target in self.our_facilities and d.impact == "capacity_reduction":
                for t in range(d.start_in_days, min(HORIZON_DAYS, d.start_in_days + d.duration_days)):
                    factory_cuts[d.target][t] = max(factory_cuts[d.target][t], d.magnitude)

        out = []
        for p in s.of("Product"):
            fac, prod = next(iter(s.sources(p, "PRODUCES")), (None, {}))
            if fac is None:
                continue
            daily = prod.get("capacity_units_per_month", 0) / 1.25 / 30
            comps = s.target_ids(p, "REQUIRES")
            raw, mit = [0.0] * HORIZON_DAYS, [0.0] * HORIZON_DAYS
            bottlenecks = set()
            for c in comps:
                if (fac, c) in series:
                    short, m_short = series[(fac, c)]
                    if any(short):
                        bottlenecks.add(c)
                    raw = [max(a, b) for a, b in zip(raw, short, strict=True)]
                    mit = [max(a, b) for a, b in zip(mit, m_short, strict=True)]
            cut = factory_cuts.get(fac)
            if cut:
                raw = [min(1.0, a + b) for a, b in zip(raw, cut, strict=True)]
                mit = [min(1.0, a + b) for a, b in zip(mit, cut, strict=True)]
                bottlenecks.add(fac)
            if not any(raw):
                continue
            price = s.props[p].get("unit_price_usd", 0.0)
            lost, m_lost = sum(raw) * daily, sum(mit) * daily
            out.append(
                ProductImpact(
                    product=p,
                    name=s.name(p),
                    factory=fac,
                    first_impact_day=next(i for i, x in enumerate(raw) if x),
                    lost_units=round(lost),
                    lost_revenue_usd=round(lost * price, 2),
                    mitigated_lost_units=round(m_lost),
                    mitigated_lost_revenue_usd=round(m_lost * price, 2),
                    bottlenecks=sorted(bottlenecks),
                )
            )
        out.sort(key=lambda x: -x.lost_revenue_usd)
        return out

    # ------------------------------------------------------------- orders
    def _penalty(self, customer: str, order_value: float, slip_days: int) -> tuple[float, bool]:
        """Liquidated damages for one delayed order and whether force majeure protects us."""
        s = self.s
        for ctr in s.target_ids(customer, "PARTY_TO"):
            p = s.props[ctr]
            if p.get("kind") == "sales":
                rate = p.get("ld_pct_per_day", 0.0) / 100
                cap = p.get("ld_cap_pct", 10.0) / 100
                return round(order_value * min(rate * slip_days, cap), 2), bool(p.get("force_majeure", True))
        return 0.0, True

    def _daily_output(self, product: str) -> float:
        return next(
            (pr.get("capacity_units_per_month", 0) / 1.25 / 30 for _, pr in self.s.sources(product, "PRODUCES")), 1.0
        )

    def _order_rows(self, product: str | None = None):
        s = self.s
        orders = s.source_ids(product, "FOR_PRODUCT") if product else s.of("SalesOrder")
        for o in orders:
            p = s.props[o]
            if p["status"] not in OPEN_STATUSES:
                continue
            due = date.fromisoformat(p["due_date"])
            if due < self.as_of:
                continue
            customer = s.source_ids(o, "PLACED")[0]
            yield o, p, due, customer

    def orders(self, products: list[ProductImpact], lanes: dict[str, LaneEffect]) -> list[OrderRisk]:
        s = self.s
        risks: dict[str, OrderRisk] = {}

        for pi in products:
            daily = max(1e-9, self._daily_output(pi.product))
            slip = math.ceil(pi.lost_units / daily) if pi.lost_units else 0
            remaining = pi.lost_units
            window_start = self.as_of + timedelta(days=pi.first_impact_day)
            rows = sorted(self._order_rows(pi.product), key=lambda r: r[2])
            for o, p, due, customer in rows:
                if remaining <= 0:
                    break
                if due < window_start:
                    continue
                remaining -= p["quantity"]
                penalty, fm = self._penalty(customer, p["value_usd"], max(1, slip))
                risks[o] = OrderRisk(
                    order=o,
                    customer=customer,
                    customer_name=s.name(customer),
                    product=pi.product,
                    due_date=p["due_date"],
                    value_usd=p["value_usd"],
                    expected_slip_days=max(1, slip),
                    reason="supply_shortfall",
                    penalty_usd=penalty,
                    force_majeure_protected=fm,
                )

        # outbound: factory → customer lanes
        for lane, eff in lanes.items():
            dest = s.one(lane, "DESTINATION")
            factories = [f for f in s.source_ids(lane, "SHIPS_VIA") if f in self.our_facilities]
            if not factories or not dest:
                continue
            transit = s.props[lane]["transit_days"]
            customers = s.source_ids(dest, "RECEIVES_AT")
            for c in customers:
                for o in s.target_ids(c, "PLACED"):
                    if o in risks or s.props[o]["status"] not in OPEN_STATUSES | {"shipped"}:
                        continue
                    if s.one(o, "FULFILLED_BY") not in factories:
                        continue
                    due = date.fromisoformat(s.props[o]["due_date"])
                    days_left = (due - self.as_of).days
                    if days_left < 0 or days_left > transit + eff.delay_days + 45:
                        continue
                    value = s.props[o]["value_usd"]
                    penalty, fm = self._penalty(c, value, eff.delay_days)
                    risks[o] = OrderRisk(
                        order=o,
                        customer=c,
                        customer_name=s.name(c),
                        product=s.one(o, "FOR_PRODUCT") or "",
                        due_date=s.props[o]["due_date"],
                        value_usd=value,
                        expected_slip_days=eff.delay_days,
                        reason="outbound_delay",
                        penalty_usd=penalty,
                        force_majeure_protected=fm,
                    )
        return sorted(risks.values(), key=lambda r: -r.value_usd)

    # -------------------------------------------------------- mitigations
    def mitigations(
        self, lanes, shortfalls: list[ComponentShortfall], products: list[ProductImpact], orders: list[OrderRisk]
    ) -> list[Mitigation]:
        s = self.s
        out: list[Mitigation] = []
        rerouted = [e for e in lanes.values() if e.rerouted_via]
        if rerouted:
            avg_days = sum(e.delay_days for e in rerouted) / len(rerouted)
            avg_cost = sum(e.extra_cost_pct for e in rerouted) / len(rerouted)
            out.append(
                Mitigation(
                    action="Reroute inbound and outbound sea freight",
                    detail=f"{len(rerouted)} lanes switch to contingency routes (avg +{avg_days:.0f} days).",
                    targets=[e.rerouted_via for e in rerouted if e.rerouted_via in s.labels][:20]
                    or [e.lane for e in rerouted][:20],
                    cost_note=f"~+{avg_cost:.0f}% freight cost per TEU on affected lanes",
                )
            )
        for sf in shortfalls[:8]:
            comp = sf.component
            for sup, p in s.sources(comp, "QUALIFIED_FOR"):
                out.append(
                    Mitigation(
                        action=f"Activate qualified alternate for {sf.component_name}",
                        detail=f"{s.name(sup)} can supply up to {p.get('max_share_pct')}% after "
                        f"{p.get('ramp_up_days')} days of ramp-up.",
                        targets=[sup, comp],
                        cost_note=f"unit cost ${p.get('unit_cost_usd')}",
                    )
                )
            primary_lanes = {lane for sup in s.source_ids(comp, "SUPPLIES") for lane in s.target_ids(sup, "SHIPS_VIA")}
            air = [
                a for lane in primary_lanes for a, _ in s.sources(lane, "ALTERNATIVE_TO") if s.props[a]["mode"] == "air"
            ]
            if air:
                out.append(
                    Mitigation(
                        action=f"Air-freight {sf.component_name} to bridge the gap",
                        detail=f"Stock-out at {s.name(sf.factory)} on day {sf.stockout_day}; air transit is 3 days.",
                        targets=sorted(set(air))[:3] + [comp],
                        cost_note="~$48k per TEU-equivalent",
                    )
                )
            if not any(s.sources(comp, "QUALIFIED_FOR")) and len(s.sources(comp, "SUPPLIES")) == 1:
                out.append(
                    Mitigation(
                        action=f"Start emergency second-source qualification for {sf.component_name}",
                        detail="Single-source component with no qualified alternative.",
                        targets=[comp],
                    )
                )
        unprotected = [o for o in orders if not o.force_majeure_protected]
        if unprotected:
            custs = sorted({o.customer for o in unprotected})
            out.append(
                Mitigation(
                    action="Prioritise allocation to orders without force-majeure protection",
                    detail=f"{len(unprotected)} at-risk orders from {len(custs)} customers carry liquidated damages "
                    f"with no force-majeure relief.",
                    targets=custs,
                    cost_note=f"${sum(o.penalty_usd for o in unprotected):,.0f} potential penalties",
                )
            )
        for pi in products[:5]:
            stock = [(wh, p.get("units", 0)) for wh, p in s.sources(pi.product, "STOCKS") if p.get("units")]
            if stock:
                total = sum(u for _, u in stock)
                out.append(
                    Mitigation(
                        action=f"Release finished-goods stock of {pi.name}",
                        detail=f"{total:,} units held in {', '.join(s.name(w) for w, _ in stock)}.",
                        targets=[w for w, _ in stock] + [pi.product],
                    )
                )
        return out

    # ---------------------------------------------------------------- run
    def assess(self, ds: list[Disruption]) -> ImpactReport:
        lanes = self.lane_effects(ds)
        hits, signals = self.initial_hits(ds, lanes)
        final_hits = self.propagate(hits)
        shortfalls, series = self.shortfalls(final_hits)
        products = self.products(series, ds)
        orders = self.orders(products, lanes)
        mitigations = self.mitigations(lanes, shortfalls, products, orders)

        nodes: set[str] = set()
        for d in ds:
            nodes.update(x for x in (d.source_event, d.target) if x)
        for e in lanes.values():
            nodes.update(e.cause)
        for sf in shortfalls:
            for path in sf.drivers:
                nodes.update(path)
        for pi in products:
            nodes.add(pi.product)
        for o in orders[:40]:
            nodes.update((o.order, o.customer))

        totals = {
            "lanes_affected": len(lanes),
            "lanes_blocked": sum(1 for e in lanes.values() if e.blocked),
            "components_short": len(shortfalls),
            "products_affected": len(products),
            "lost_revenue_usd": round(sum(p.lost_revenue_usd for p in products), 2),
            "mitigated_lost_revenue_usd": round(sum(p.mitigated_lost_revenue_usd for p in products), 2),
            "orders_at_risk": len(orders),
            "order_value_at_risk_usd": round(sum(o.value_usd for o in orders), 2),
            "penalty_exposure_usd": round(sum(o.penalty_usd for o in orders), 2),
            "unprotected_penalty_usd": round(sum(o.penalty_usd for o in orders if not o.force_majeure_protected), 2),
            "probability": round(math.prod({d.source_event or d.target: d.probability for d in ds}.values()), 3),
        }
        return ImpactReport(
            as_of=self.as_of.isoformat(),
            disruptions=ds,
            lanes=sorted(lanes.values(), key=lambda e: -e.delay_days),
            shortfalls=shortfalls,
            products=products,
            orders=orders,
            mitigations=mitigations,
            market_signals=signals,
            totals=totals,
            highlight={"nodes": sorted(nodes)},
            assumptions=[
                f"Horizon {HORIZON_DAYS} days from {self.as_of.isoformat()}.",
                f"Suppliers hold ~{UPSTREAM_BUFFER_DAYS} days of their own inputs.",
                f"Unaffected active suppliers can surge by {int(SURGE_SHARE * 100)}% of volume after 14 days.",
                "Planned output is 80% of nameplate factory capacity.",
                "Delayed flows create a supply gap equal to the added transit time.",
            ],
        )


def assess(snap: Snapshot, disruptions: list[Disruption]) -> ImpactReport:
    return ImpactEngine(snap).assess(disruptions)


def assess_events(snap: Snapshot, event_ids: list[str], duration_override: int | None = None) -> ImpactReport:
    return assess(snap, disruptions_from_events(snap, event_ids, duration_override))
