"""Deterministic generator for the Nilewave Energy knowledge graph.

Produces a ``GraphData`` (nodes + edges, already shaped by the ontology) and a
set of unstructured documents (news, contract text, reports).
"""

from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from ..ontology import ONTOLOGY
from . import catalog as C
from .documents import build_documents
from .network import CARRIERS, CUSTOMERS, NW, SUPPLIERS
from .routing import chokepoints_on, road_days, sea_days, sea_route

AS_OF = date(2026, 11, 18)
SEED = 2026


@dataclass
class GraphData:
    nodes: dict[str, dict[str, Any]] = field(default_factory=dict)  # id -> {"label", "props"}
    edges: list[dict[str, Any]] = field(default_factory=list)
    documents: list[dict[str, Any]] = field(default_factory=list)  # file artifacts
    _edge_keys: set[tuple[str, str, str]] = field(default_factory=set, repr=False)

    def node(self, label: str, id_: str, **props: Any) -> str:
        clean = {k: v for k, v in props.items() if v is not None}
        if id_ in self.nodes:
            self.nodes[id_]["props"].update(clean)
        else:
            self.nodes[id_] = {"label": label, "props": {"id": id_, **clean}}
        return id_

    def edge(self, type_: str, source: str, target: str, **props: Any) -> None:
        key = (type_, source, target)
        if key in self._edge_keys:
            return
        self._edge_keys.add(key)
        self.edges.append(
            {
                "type": type_,
                "source": source,
                "target": target,
                "props": {k: v for k, v in props.items() if v is not None},
            }
        )

    def label_of(self, id_: str) -> str:
        return self.nodes[id_]["label"]

    def validate(self) -> list[str]:
        errors: list[str] = []
        for node in self.nodes.values():
            errors += ONTOLOGY.validate_node(node["label"], node["props"])
        for e in self.edges:
            if e["source"] not in self.nodes or e["target"] not in self.nodes:
                errors.append(f"{e['type']}: dangling edge {e['source']} -> {e['target']}")
                continue
            errors += ONTOLOGY.validate_edge(e["type"], self.label_of(e["source"]), self.label_of(e["target"]))
        return errors

    def stats(self) -> dict[str, dict[str, int]]:
        nodes: dict[str, int] = defaultdict(int)
        edges: dict[str, int] = defaultdict(int)
        for n in self.nodes.values():
            nodes[n["label"]] += 1
        for e in self.edges:
            edges[e["type"]] += 1
        return {"nodes": dict(sorted(nodes.items())), "edges": dict(sorted(edges.items()))}


class Generator:
    def __init__(self, seed: int = SEED) -> None:
        self.rng = random.Random(seed)
        self.g = GraphData()
        self.product_factory = {pid: p[6] for pid, p in C.PRODUCTS.items()}
        self.lane_carrier: dict[str, str] = {}

    # ------------------------------------------------------------------ api
    def build(self) -> GraphData:
        self._geography()
        self._company_and_facilities()
        self._items_and_bom()
        self._carriers()
        self._suppliers()
        self._inventory()
        self._customers_and_orders()
        self._contracts()
        self._tariffs()
        self._risk_events()
        build_documents(self.g, self.rng, AS_OF)
        return self.g

    # ------------------------------------------------------------ geography
    def _geography(self) -> None:
        g = self.g
        for iso, (name, name_ar, region, risk) in C.COUNTRIES.items():
            g.node("Country", iso, name=name, name_ar=name_ar, region=region, political_risk=risk)
        for code, (name, name_ar, country, lat, lon, _zone, congestion) in C.PORTS.items():
            g.node("Port", code, name=name, name_ar=name_ar, lat=lat, lon=lon, kind="sea", congestion_index=congestion)
            g.edge("LOCATED_IN", code, country)
        for cid, (name, name_ar, lat, lon, share) in C.CHOKEPOINTS.items():
            g.node("Chokepoint", cid, name=name, name_ar=name_ar, lat=lat, lon=lon, share_of_global_trade_pct=share)

    def _company_and_facilities(self) -> None:
        g = self.g
        g.node("Company", NW, **{k: v for k, v in C.COMPANY.items() if k != "id"})
        g.edge("LOCATED_IN", NW, "EG")
        for fid, (name, kind, city, country, lat, lon, port, cap) in C.FACILITIES.items():
            extra = {"capacity_units_per_month": cap} if kind == "Factory" else {"capacity_pallets": cap}
            g.node(kind, fid, name=name, city=city, lat=lat, lon=lon, **extra)
            g.edge("OPERATES", NW, fid)
            g.edge("LOCATED_IN", fid, country)
            g.edge("SERVED_BY", fid, port, distance_km=round(self.rng.uniform(4, 140), 1))

    def _items_and_bom(self) -> None:
        g = self.g
        for mid, (name, name_ar, cat, hs, unit, cost, critical) in C.MATERIALS.items():
            g.node(
                "Material",
                mid,
                name=name,
                name_ar=name_ar,
                category=cat,
                hs_code=hs,
                unit=unit,
                unit_cost_usd=cost,
                critical=critical,
            )
        for cid, (name, name_ar, cat, hs, unit, cost, lt) in C.COMPONENTS.items():
            g.node(
                "Component",
                cid,
                name=name,
                name_ar=name_ar,
                category=cat,
                hs_code=hs,
                unit=unit,
                unit_cost_usd=cost,
                lead_time_days=lt,
            )
        for pid, (sku, name, name_ar, fam, price, margin, factory, vol) in C.PRODUCTS.items():
            bom_cost = sum(C.COMPONENTS[c][5] * q for c, q in C.BOM[pid])
            g.node(
                "Product",
                pid,
                sku=sku,
                name=name,
                name_ar=name_ar,
                category=fam,
                family=fam,
                unit="pcs",
                unit_price_usd=float(price),
                gross_margin_pct=float(margin),
                unit_cost_usd=round(bom_cost, 2),
            )
            g.edge("PRODUCES", factory, pid, capacity_units_per_month=int(vol * 1.25))
        for parent, children in C.BOM.items():
            for child, qty in children:
                g.edge("REQUIRES", parent, child, quantity=qty)

    def _carriers(self) -> None:
        for lid, (name, mode) in CARRIERS.items():
            self.g.node("LogisticsProvider", lid, name=name, mode=mode)

    # ---------------------------------------------------------------- lanes
    def _lane(
        self,
        origin_port: str,
        dest_port: str,
        *,
        avoid: frozenset[str] = frozenset(),
        contingency: bool = False,
        mode: str | None = None,
    ) -> str | None:
        """Create (or reuse) a lane between two ports and return its id."""
        g = self.g
        o_country, d_country = C.PORTS[origin_port][2], C.PORTS[dest_port][2]
        if mode is None:
            mode = "road" if o_country == d_country else "sea"
        suffix = {"road": "RD", "air": "AIR"}.get(mode, "ALT" if contingency else "SEA")
        lane_id = f"LANE-{origin_port}-{dest_port}-{suffix}"
        if lane_id in g.nodes:
            return lane_id

        o_ll, d_ll = C.PORTS[origin_port][3:5], C.PORTS[dest_port][3:5]
        chokes: list[str] = []
        if mode == "road":
            days, cost, co2, carrier = road_days(o_ll, d_ll), 950.0, 180.0, "LP-NILEROAD"
        elif mode == "air":
            days, cost, co2, carrier = 3, 48000.0, 9800.0, "LP-FALCON"
        else:
            route = sea_route(origin_port, dest_port, avoid)
            if route is None:
                return None
            path, km = route
            chokes = chokepoints_on(path)
            days = sea_days(km)
            cost = round(600 + km * 0.16 + (450 if contingency else 0), -1)
            co2 = round(km * 0.06, 1)
            carrier = "LP-CAPEEX" if contingency else ("LP-LEVANT" if km < 6000 else "LP-ORIENT")

        name = f"{C.PORTS[origin_port][0]} → {C.PORTS[dest_port][0]} ({mode}{', contingency' if contingency else ''})"
        g.node(
            "ShippingLane",
            lane_id,
            name=name,
            mode=mode,
            transit_days=int(days),
            cost_per_teu_usd=cost,
            co2_kg_per_teu=co2,
            is_contingency=contingency,
        )
        g.edge("ORIGIN", lane_id, origin_port)
        g.edge("DESTINATION", lane_id, dest_port)
        g.edge("OPERATED_BY", lane_id, carrier)
        for i, ck in enumerate(chokes, start=1):
            g.edge("TRANSITS", lane_id, ck, sequence=i)
        return lane_id

    def _lane_with_contingency(self, origin_port: str, dest_port: str, semis: bool = False) -> str:
        primary = self._lane(origin_port, dest_port)
        assert primary is not None
        chokes = {e["target"] for e in self.g.edges if e["type"] == "TRANSITS" and e["source"] == primary}
        base_days = self.g.nodes[primary]["props"]["transit_days"]
        base_cost = self.g.nodes[primary]["props"]["cost_per_teu_usd"]
        red_sea = {"BAB_EL_MANDEB", "SUEZ"}
        if chokes & red_sea:
            alt_dest = dest_port
            if C.PORTS[dest_port][5] == "RED_SEA" and C.PORTS[dest_port][2] == "EG":
                alt_dest = "EGPSD"  # discharge in the Med, truck to the Red Sea coast
            alt = self._lane(origin_port, alt_dest, avoid=frozenset(red_sea), contingency=True)
            if alt:
                alt_days = self.g.nodes[alt]["props"]["transit_days"] + (2 if alt_dest != dest_port else 0)
                self.g.nodes[alt]["props"]["transit_days"] = alt_days
                alt_cost = self.g.nodes[alt]["props"]["cost_per_teu_usd"]
                self.g.edge(
                    "ALTERNATIVE_TO",
                    alt,
                    primary,
                    extra_days=max(0, alt_days - base_days),
                    extra_cost_pct=round(100 * (alt_cost - base_cost) / base_cost, 1),
                )
        if semis and self.g.nodes[primary]["props"]["mode"] == "sea":
            air = self._lane(origin_port, dest_port, mode="air", contingency=True)
            assert air is not None
            self.g.edge(
                "ALTERNATIVE_TO",
                air,
                primary,
                extra_days=3 - base_days,
                extra_cost_pct=round(100 * (48000 - base_cost) / base_cost, 1),
            )
        return primary

    # ------------------------------------------------------------ suppliers
    def _component_factories(self) -> dict[str, set[str]]:
        usage: dict[str, set[str]] = defaultdict(set)
        for pid, children in C.BOM.items():
            if pid in C.PRODUCTS:
                for child, _ in children:
                    usage[child].add(self.product_factory[pid])
        return usage

    def _suppliers(self) -> None:
        g, rng = self.g, self.rng
        usage = self._component_factories()
        spec_by_id = {s.id: s for s in SUPPLIERS}
        for s in SUPPLIERS:
            g.node(
                "Supplier",
                s.id,
                name=s.name,
                country_code=s.country,
                tier=s.tier,
                category=s.category,
                esg_score=float(s.esg),
                financial_health=s.health,
                on_time_delivery_pct=s.otd,
                website=f"https://{s.id.removeprefix('SUP-').lower()}.example",
            )
            g.edge("LOCATED_IN", s.id, s.country)
            site = f"FAC-{s.id.removeprefix('SUP-')}"
            g.node("Factory", site, name=f"{s.name} — {s.city}", city=s.city, lat=s.lat, lon=s.lon)
            g.edge("OPERATES", s.id, site)
            g.edge("LOCATED_IN", site, s.country)
            g.edge("SERVED_BY", site, s.port, distance_km=round(rng.uniform(10, 900), 0))

            for sup in s.supplies:
                base = (C.COMPONENTS.get(sup.item) or C.MATERIALS[sup.item])[5]
                lead = C.COMPONENTS[sup.item][6] if sup.item in C.COMPONENTS else rng.randint(30, 90)
                g.edge(
                    "SUPPLIES",
                    s.id,
                    sup.item,
                    share_pct=float(sup.share_pct),
                    unit_cost_usd=round(base * rng.uniform(0.92, 1.08), 2),
                    lead_time_days=lead,
                    capacity_units_per_month=None,
                )
            for q in s.qualified:
                base = C.COMPONENTS[q.item][5]
                g.edge(
                    "QUALIFIED_FOR",
                    s.id,
                    q.item,
                    ramp_up_days=q.ramp_up_days,
                    max_share_pct=q.max_share_pct,
                    unit_cost_usd=round(base * rng.uniform(1.04, 1.18), 2),
                )

            # supply edges + lanes
            semis = s.category == "Semiconductors"
            if s.tier == 1:
                spend = 0.0
                for sup in s.supplies:
                    for fac in usage.get(sup.item, set()):
                        lane = self._lane_with_contingency(s.port, C.FACILITIES[fac][6], semis=semis)
                        g.edge("SHIPS_VIA", s.id, lane, annual_teu=rng.randint(20, 900))
                    spend += C.COMPONENTS[sup.item][5] * rng.uniform(40_000, 400_000) * sup.share_pct / 100
                if s.supplies:
                    g.edge("SUPPLIES_TO", s.id, NW, annual_spend_usd=round(spend, -3))
            else:
                for buyer in s.customers:
                    g.edge("SUPPLIES_TO", s.id, buyer, annual_spend_usd=round(rng.uniform(2e6, 6e7), -4))
                    dest = spec_by_id[buyer].port
                    if dest != s.port:
                        lane = self._lane_with_contingency(s.port, dest)
                        g.edge("SHIPS_VIA", s.id, lane, annual_teu=rng.randint(10, 400))

    # ------------------------------------------------------------ inventory
    COVER_OVERRIDES = {
        ("FAC-10RAM", "CMP-SICMOS"): 16.0,
        ("FAC-SOKHNA", "CMP-SICMOS"): 21.0,
        ("FAC-TANGIER", "CMP-SICMOS"): 12.0,
        ("FAC-SOKHNA", "CMP-LFPCELL"): 19.0,
        ("FAC-10RAM", "CMP-DSP"): 26.0,
        ("FAC-SOKHNA", "CMP-CONTAINER"): 34.0,
        ("FAC-SOKHNA", "CMP-TRAFO"): 41.0,
        ("FAC-10RAM", "CMP-INDUCTOR"): 14.0,
        ("FAC-TANGIER", "CMP-CCS2"): 23.0,
        ("FAC-10RAM", "CMP-PVPANEL"): 11.0,
    }

    def _inventory(self) -> None:
        g, rng = self.g, self.rng
        daily: dict[tuple[str, str], float] = defaultdict(float)
        for pid, p in C.PRODUCTS.items():
            for comp, qty in C.BOM[pid]:
                daily[(p[6], comp)] += qty * p[7] / 30
        for (fac, comp), per_day in sorted(daily.items()):
            cover = self.COVER_OVERRIDES.get((fac, comp), round(rng.uniform(18, 55), 1))
            g.edge("STOCKS", fac, comp, units=int(per_day * cover), days_of_cover=cover)
        for wh in ("WH-ROTTERDAM", "WH-JEBELALI", "WH-HOUSTON"):
            for pid, p in C.PRODUCTS.items():
                if p[3] == "Grid Storage":
                    continue
                cover = round(rng.uniform(6, 40), 1)
                g.edge("STOCKS", wh, pid, units=int(p[7] / 30 * cover * 0.3), days_of_cover=cover)

    # ------------------------------------------------- customers and orders
    QTY = {
        "Inverters": (40, 600),
        "Home Storage": (20, 320),
        "Grid Storage": (1, 4),
        "EV Charging": (30, 450),
        "Controls": (4, 40),
        "Solar Kits": (20, 160),
    }
    QTY_BY_PRODUCT = {"PRD-EVC150": (2, 24), "PRD-INV100": (5, 60)}

    def _customers_and_orders(self) -> None:
        g, rng = self.g, self.rng
        products_by_family: dict[str, list[str]] = defaultdict(list)
        for pid, p in C.PRODUCTS.items():
            products_by_family[p[3]].append(pid)

        n = 0
        for cid, (name, country, segment, region, strategic, port, families) in CUSTOMERS.items():
            g.node(
                "Customer",
                cid,
                name=name,
                country_code=country,
                segment=segment,
                region=region,
                strategic=strategic,
                website=f"https://{cid.removeprefix('CUS-').lower()}.example",
            )
            g.edge("LOCATED_IN", cid, country)
            g.edge("RECEIVES_AT", cid, port)

            n_orders = rng.randint(28, 60) if strategic else rng.randint(12, 34)
            for _ in range(n_orders):
                fam = rng.choice(families)
                pid = rng.choice(products_by_family[fam])
                factory = self.product_factory[pid]
                lo, hi = self.QTY_BY_PRODUCT.get(pid, self.QTY[fam])
                qty = rng.randint(lo, hi)
                price = C.PRODUCTS[pid][4]
                order_date = AS_OF - timedelta(days=rng.randint(1, 200))
                due = order_date + timedelta(
                    days=rng.randint(45, 150) if fam == "Grid Storage" else rng.randint(30, 95)
                )
                if due < AS_OF:
                    status = "late" if rng.random() < 0.09 else "delivered"
                elif (due - AS_OF).days < 12:
                    status = "shipped"
                elif (AS_OF - order_date).days > 14:
                    status = "in_production"
                else:
                    status = "open"
                pr = rng.random()
                priority = "critical" if strategic and pr < 0.25 else ("high" if pr < 0.45 else "standard")
                n += 1
                oid = f"SO-{26000 + n}"
                g.node(
                    "SalesOrder",
                    oid,
                    quantity=qty,
                    value_usd=round(qty * price * rng.uniform(0.9, 1.04), 2),
                    order_date=order_date.isoformat(),
                    due_date=due.isoformat(),
                    status=status,
                    priority=priority,
                )
                g.edge("PLACED", cid, oid)
                g.edge("FOR_PRODUCT", oid, pid)
                g.edge("FULFILLED_BY", oid, factory)

                fac_port = C.FACILITIES[factory][6]
                lane = self._lane_with_contingency(fac_port, port)
                g.edge("SHIPS_VIA", factory, lane, annual_teu=rng.randint(30, 600))

    # ------------------------------------------------------------ contracts
    def _contracts(self) -> None:
        g, rng = self.g, self.rng
        n = 0

        def contract(kind: str, counterparty: str, title: str, covers: list[str], **props: Any) -> str:
            nonlocal n
            n += 1
            cid = f"CTR-{kind[:3].upper()}-{n:03d}"
            g.node("Contract", cid, title=title, kind=kind, **props)
            g.edge("PARTY_TO", NW, cid)
            g.edge("PARTY_TO", counterparty, cid)
            for item in covers:
                g.edge("COVERS", cid, item)
            return cid

        renew_soon = {"SUP-FORMOSIC": date(2027, 1, 31), "SUP-ZHENGYUAN": date(2026, 12, 31)}
        for s in SUPPLIERS:
            if s.tier != 1 or not s.supplies:
                continue
            items = [x.item for x in s.supplies]
            start = date(2024, 1, 1) + timedelta(days=rng.randint(0, 600))
            end = renew_soon.get(s.id, start + timedelta(days=rng.choice([730, 1095])))
            single = any(x.share_pct == 100 for x in s.supplies)
            value = sum(C.COMPONENTS[i][5] for i in items) * rng.uniform(80_000, 600_000)
            contract(
                "supply",
                s.id,
                f"Master Supply Agreement — {s.name}",
                items,
                start_date=start.isoformat(),
                end_date=end.isoformat(),
                value_usd=round(value, -3),
                penalty_per_day_usd=round(value * 0.0004, -1),
                ld_pct_per_day=0.1,
                ld_cap_pct=5.0,
                force_majeure=True,
                exclusivity=single,
                min_volume_units=rng.randint(5, 60) * 1000,
            )

        no_fm = {"CUS-REDSEACOAST", "CUS-LONESTAR"}
        for cid, cust in CUSTOMERS.items():
            if not cust[4]:
                continue
            open_value = 0.0
            products: set[str] = set()
            for e in g.edges:
                if e["type"] == "PLACED" and e["source"] == cid:
                    order = g.nodes[e["target"]]["props"]
                    if order["status"] not in ("delivered",):
                        open_value += order["value_usd"]
            for e in g.edges:
                if e["type"] == "FOR_PRODUCT":
                    placed_by = (cid, e["source"])
                    if ("PLACED", *placed_by) in g._edge_keys:
                        products.add(e["target"])
            value = max(open_value * 1.6, 2e6)
            start = date(2025, 1, 1) + timedelta(days=rng.randint(0, 420))
            contract(
                "sales",
                cid,
                f"Framework Supply & Delivery Agreement — {cust[0]}",
                sorted(products),
                start_date=start.isoformat(),
                end_date=(start + timedelta(days=1095)).isoformat(),
                value_usd=round(value, -3),
                penalty_per_day_usd=round(value * 0.0005, -2),
                ld_pct_per_day=0.3 if cid in no_fm else 0.2,
                ld_cap_pct=10.0,
                force_majeure=cid not in no_fm,
                exclusivity=False,
            )

        for lp in ("LP-ORIENT", "LP-LEVANT", "LP-CAPEEX"):
            lanes = [e["source"] for e in g.edges if e["type"] == "OPERATED_BY" and e["target"] == lp][:12]
            contract(
                "logistics",
                lp,
                f"Ocean Freight Agreement — {CARRIERS[lp][0]}",
                lanes,
                start_date="2026-01-01",
                end_date="2026-12-31",
                value_usd=round(rng.uniform(4e6, 1.8e7), -3),
                penalty_per_day_usd=0.0,
                force_majeure=True,
                exclusivity=False,
            )

    # -------------------------------------------------------------- tariffs
    def _tariffs(self) -> None:
        g = self.g
        egypt_products = [p for p, v in C.PRODUCTS.items() if v[6] != "FAC-TANGIER"]
        morocco_products = [p for p, v in C.PRODUCTS.items() if v[6] == "FAC-TANGIER"]
        rows = [
            (
                "TAR-US-EG",
                "US reciprocal tariff on Egyptian goods",
                10.0,
                "2025-04-05",
                "in_force",
                "US",
                "EG",
                egypt_products,
            ),
            (
                "TAR-US-MA",
                "US reciprocal tariff on Moroccan goods",
                10.0,
                "2025-04-05",
                "in_force",
                "US",
                "MA",
                morocco_products,
            ),
            (
                "TAR-US-FEOC",
                "US duty on storage systems with Chinese-made cells",
                25.0,
                "2027-01-01",
                "proposed",
                "US",
                "CN",
                ["PRD-HB10", "PRD-HB15", "PRD-GRID25", "PRD-GRID5", "CMP-LFPCELL"],
            ),
            (
                "TAR-EU-CBAM",
                "EU CBAM levy on embedded steel & aluminium",
                4.0,
                "2026-01-01",
                "in_force",
                "NL",
                "EG",
                ["PRD-GRID25", "PRD-GRID5", "CMP-CONTAINER", "CMP-ENCL"],
            ),
            (
                "TAR-ZA-INV",
                "South Africa import duty on inverters",
                15.0,
                "2026-12-01",
                "announced",
                "ZA",
                "EG",
                ["PRD-INV5", "PRD-INV10", "PRD-INV100"],
            ),
        ]
        for tid, name, rate, eff, status, by, origin, targets in rows:
            g.node("Tariff", tid, name=name, rate_pct=rate, effective_date=eff, status=status)
            g.edge("IMPOSED_BY", tid, by)
            g.edge("ON_ORIGIN", tid, origin)
            for t in targets:
                g.edge("TARGETS", tid, t)

    # ---------------------------------------------------------- risk events
    def _risk_events(self) -> None:
        g = self.g
        from .events import RISK_EVENTS

        for ev in RISK_EVENTS:
            start = (AS_OF + timedelta(days=ev.start_offset)).isoformat()
            g.node(
                "RiskEvent",
                ev.id,
                title=ev.title,
                title_ar=ev.title_ar,
                type=ev.type,
                severity=ev.severity,
                probability=ev.probability,
                status=ev.status,
                start_date=start,
                expected_duration_days=ev.duration_days,
                summary=ev.summary,
            )
            for target, impact, magnitude, added in ev.affects:
                g.edge("AFFECTS", ev.id, target, impact=impact, magnitude=magnitude, added_days=added)


def generate(seed: int = SEED) -> GraphData:
    return Generator(seed).build()
