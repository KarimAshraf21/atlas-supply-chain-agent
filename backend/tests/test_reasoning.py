import pytest

from atlas.reasoning import Disruption, Snapshot, assess, assess_events
from atlas.reasoning.spof import structural_risk
from atlas.seed import generate


@pytest.fixture(scope="module")
def snap():
    return Snapshot.from_graphdata(generate())


def test_red_sea_reroutes_lanes_and_causes_stockouts(snap):
    r = assess_events(snap, ["RE-REDSEA"])
    assert r.totals["lanes_affected"] > 20
    rerouted = [lane for lane in r.lanes if lane.rerouted_via]
    assert rerouted and all(1 <= lane.delay_days <= 40 for lane in rerouted)
    assert any(sf.component == "CMP-SICMOS" for sf in r.shortfalls)
    # every shortfall explains itself with a path starting at the event
    assert all(path[0] == "RE-REDSEA" for sf in r.shortfalls for path in sf.drivers)


def test_tier2_insolvency_propagates_to_finished_products(snap):
    r = assess_events(snap, ["RE-DAEGU"])
    assert [sf.component for sf in r.shortfalls] == ["CMP-LFPCELL"]
    driver = r.shortfalls[0].drivers[0]
    assert driver[:3] == ["RE-DAEGU", "SUP-DAEGU", "SUP-DAEGU"] or "SUP-DAEGU" in driver
    assert {"PRD-HB10", "PRD-GRID5"} <= {p.product for p in r.products}
    # qualified alternate (Hanseong) mitigates part of the loss
    assert r.totals["mitigated_lost_revenue_usd"] < r.totals["lost_revenue_usd"]


def test_single_source_outage_has_no_mitigation(snap):
    r = assess(snap, [Disruption(target="SUP-FORMOSIC", impact="capacity_reduction", duration_days=60)])
    assert r.totals["lost_revenue_usd"] > 1e7
    assert r.totals["mitigated_lost_revenue_usd"] == r.totals["lost_revenue_usd"]
    assert any("second-source" in m.action for m in r.mitigations)


def test_dynamic_reroute_for_unplanned_closure(snap):
    r = assess(snap, [Disruption(target="TAIWAN_STRAIT", duration_days=30)])
    assert r.lanes and all(lane.rerouted_via and lane.rerouted_via.startswith("via") for lane in r.lanes)


def test_unaffected_scenario_is_empty(snap):
    r = assess(snap, [Disruption(target="PANAMA", impact="delay", added_days=1, duration_days=5)])
    assert r.totals["products_affected"] == 0


def test_structural_risk_finds_designed_weak_spots(snap):
    risk = structural_risk(snap)
    sic = next(sp for sp in risk.single_points if sp.item == "CMP-SICMOS")
    assert sic.supplier == "SUP-FORMOSIC" and not sic.has_qualified_alternative
    daegu = next(h for h in risk.hidden_dependencies if h.upstream_supplier == "SUP-DAEGU")
    assert set(daegu.tier1_suppliers) == {"SUP-ZHENGYUAN", "SUP-MEKONG"}
    assert risk.concentrations[0].key == "BAB_EL_MANDEB"
