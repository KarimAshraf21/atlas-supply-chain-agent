# Atlas — talk to your supply chain

**A multilingual voice agent that reasons over an ontology-driven knowledge graph.**
Ask, in English or Arabic, *"What happens to our Q1 revenue if the Red Sea stays closed for three more weeks?"*
and Atlas walks the graph from the disrupted chokepoint to lanes, suppliers, components, products, orders and
contracts, then answers with numbers, a reasoning path you can see, and the sources behind it.

> Built end to end as a reference architecture for production agentic systems: ontology-first data modelling,
> a knowledge graph, an explainable reasoning layer, a multi-agent harness exposed over **A2A** with tools over
> **MCP**, real-time voice, and a polished web app.

## Status

| Layer | State |
|---|---|
| Ontology (21 classes, 31 relations, OWL export) | ✅ |
| Synthetic company dataset (~1,500 nodes, ~4,600 edges, 61 documents in EN/AR) | ✅ |
| Neo4j knowledge graph + loader | ✅ |
| Reasoning layer (impact propagation, SPOF detection, inference rules, what-if) | 🚧 next |
| Agent harness (LangGraph supervisor + specialists, A2A server, MCP tools) | 🚧 |
| Multilingual voice (streaming STT/TTS) | 🚧 |
| Web app (voice orb, graph explorer, world map, scenario simulator) | 🚧 |

## The demo company

**Nilewave Energy** (fictional) makes inverters, home and grid-scale batteries, EV chargers and solar kits in
three plants: the Sokhna Gigafactory and 10th of Ramadan plant in Egypt, and a plant in Tangier, Morocco.

The dataset is designed to have the structure real supply chains have, so the reasoning has something to find:

- **Multi-tier suppliers** (49 across 3 tiers): lithium miners in Chile and Australia → refiners → cathode makers
  → cell makers → Nilewave.
- **Real geography**: 31 real ports and 8 maritime chokepoints (Suez, Bab el-Mandeb, Hormuz, Malacca, Taiwan
  Strait, Gibraltar, Cape of Good Hope, Panama). Lanes are routed over a sea graph, and Red Sea lanes have
  Cape-of-Good-Hope contingency lanes (+~17 days).
- **Deliberate weak spots**: single-source SiC power modules from Taiwan, 70% of battery cells from one Chinese
  supplier, a financially distressed tier-2 copper-foil maker, graphite and gallium export controls.
- **Commercial exposure**: 878 sales orders, 40 contracts (some strategic customers have liquidated damages
  *without* force-majeure relief), 5 tariffs.
- **17 risk events** (active, forecast and resolved) and **61 documents**: news in English and Arabic, full
  contract texts and internal reports, all linked to graph entities for GraphRAG.

All organizations, people, orders and events are fictional; the geography is real.

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). In short:

```
Web app ─▶ API gateway ─▶ Voice pipeline ─▶ Agent harness (LangGraph, A2A, MCP)
                                              └─▶ Reasoning layer ─▶ Neo4j knowledge graph ◀─ Ontology
```

## Quick start

Requires Docker and Python 3.12+.

```bash
cp .env.example .env
docker compose up -d neo4j
cd backend && python -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/atlas generate   # build and validate the synthetic dataset
.venv/bin/atlas load       # load it into Neo4j
.venv/bin/atlas ontology   # export OWL/Turtle, JSON and the LLM prompt schema
.venv/bin/pytest
```

Open the Neo4j browser at http://localhost:7474 and try:

```cypher
// Which products and open orders are exposed to the Red Sea closure?
MATCH (:RiskEvent {id:"RE-REDSEA"})-[:AFFECTS]->(:Chokepoint)<-[:TRANSITS]-(l:ShippingLane)
      <-[:SHIPS_VIA]-(s:Supplier)-[:SUPPLIES]->(:Component)<-[:REQUIRES]-(p:Product)
WHERE NOT l.is_contingency
WITH DISTINCT p
MATCH (p)<-[:FOR_PRODUCT]-(o:SalesOrder) WHERE o.status IN ["open", "in_production"]
RETURN p.name, count(o) AS orders, round(sum(o.value_usd)) AS value_usd ORDER BY value_usd DESC
```

## Repository layout

```
backend/atlas/ontology   ontology meta-model, the supply-chain ontology, exporters (Neo4j, OWL, prompt)
backend/atlas/seed       deterministic dataset generator (catalog, network, routing, events, documents)
backend/atlas/graph      Neo4j client and loader
data/seed                generated dataset: graph JSONL, per-class CSV "ERP exports", Markdown documents
ontology/                exported ontology (Turtle, JSON, prompt schema)
docs/                    architecture notes
```

## License

MIT
