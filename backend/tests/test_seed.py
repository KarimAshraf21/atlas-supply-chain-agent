from collections import Counter

import pytest

from atlas.ontology import ONTOLOGY
from atlas.ontology.exporters import neo4j_constraints, to_owl, to_prompt
from atlas.seed import generate
from atlas.seed.routing import chokepoints_on, sea_route


@pytest.fixture(scope="module")
def graph():
    return generate()


def test_generated_graph_conforms_to_ontology(graph):
    assert graph.validate() == []


def test_generation_is_deterministic(graph):
    again = generate()
    assert again.stats() == graph.stats()
    assert [e["source"] for e in again.edges[:200]] == [e["source"] for e in graph.edges[:200]]


def test_every_product_has_a_bom_and_a_factory(graph):
    products = [n for n, v in graph.nodes.items() if v["label"] == "Product"]
    requires = {e["source"] for e in graph.edges if e["type"] == "REQUIRES"}
    produced = {e["target"] for e in graph.edges if e["type"] == "PRODUCES"}
    assert set(products) <= requires
    assert set(products) <= produced


def test_supplier_shares_sum_to_100_per_item(graph):
    shares = Counter()
    for e in graph.edges:
        if e["type"] == "SUPPLIES":
            shares[e["target"]] += e["props"]["share_pct"]
    assert all(abs(total - 100) < 1e-6 for total in shares.values()), shares


def test_designed_single_points_of_failure_exist(graph):
    sic = [e for e in graph.edges if e["type"] == "SUPPLIES" and e["target"] == "CMP-SICMOS"]
    alts = [e for e in graph.edges if e["type"] == "QUALIFIED_FOR" and e["target"] == "CMP-SICMOS"]
    assert len(sic) == 1 and not alts


def test_red_sea_lanes_have_cape_contingency(graph):
    alt = [e for e in graph.edges if e["type"] == "ALTERNATIVE_TO" and e["source"] == "LANE-CNNGB-EGPSD-ALT"]
    assert alt and alt[0]["target"] == "LANE-CNNGB-EGSOK-SEA"
    assert 10 <= alt[0]["props"]["extra_days"] <= 25


def test_routing_respects_geography():
    path, _ = sea_route("CNSHA", "NLRTM")
    assert chokepoints_on(path) == ["MALACCA", "BAB_EL_MANDEB", "SUEZ", "GIBRALTAR"]
    path, _ = sea_route("CNSHA", "NLRTM", frozenset({"BAB_EL_MANDEB", "SUEZ"}))
    assert "CAPE" in chokepoints_on(path)
    assert sea_route("CNSHA", "SAJED", frozenset({"BAB_EL_MANDEB", "SUEZ"})) is None


def test_ontology_exports():
    assert len(neo4j_constraints(ONTOLOGY)) > len([c for c in ONTOLOGY.classes if c.parent is None])
    assert len(to_owl(ONTOLOGY)) > 300
    assert "SUPPLIES" in to_prompt(ONTOLOGY)
    assert ONTOLOGY.ancestors("Supplier") == ["Supplier", "Organization"]
