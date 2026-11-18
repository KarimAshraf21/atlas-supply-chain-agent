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
| Reasoning layer (impact propagation, SPOF & hidden-dependency detection, inference rules, what-if) | ✅ |
| Tool layer (10 typed tools) exposed to agents, **MCP** (stdio + HTTP) and REST | ✅ |
| Agent harness (LangGraph router → parallel specialists → streaming composer) + **A2A** server | ✅ |
| Web app: copilot with voice (EN/AR), world map, scenario lab, risk radar, graph explorer | ✅ |
| One-command Docker stack (Neo4j + API + web) | ✅ |

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

**Everything in Docker:**

```bash
cp .env.example .env          # add GROQ_API_KEY for chat/voice (map, scenarios and risk radar work without it)
docker compose --profile app up --build
# web: http://localhost:3000 · API: http://localhost:8000/docs · Neo4j: http://localhost:7474
```

**Local development** (Docker for Neo4j, Python 3.12+, Node 22+):

```bash
cp .env.example .env
docker compose up -d neo4j
cd backend && python -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/atlas generate   # build and validate the synthetic dataset
.venv/bin/atlas load       # load it into Neo4j
.venv/bin/atlas reason     # materialise inferred relationships
.venv/bin/atlas ontology   # export OWL/Turtle, JSON and the LLM prompt schema
.venv/bin/pytest
.venv/bin/atlas serve      # API on :8000
cd ../web && npm install && npm run dev   # web app on :3000
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

## The reasoning layer

The LLM plans and narrates; **the numbers come from deterministic graph algorithms**, and every result carries
the path that produced it.

- **Impact propagation** (`reasoning/impact.py`): disruption → lanes (prebuilt contingency or dynamic sea
  re-routing around closed chokepoints) → supplier flows, tier N → tier 1 (with upstream buffers) → day-by-day
  factory inventory simulation (days of cover) → production shortfall → products → open orders → contracts
  (liquidated damages, force-majeure protection). Mitigations (qualified alternates with ramp-up, supplier surge,
  air freight, finished-goods stock) are simulated, not just listed.
- **Structural risk** (`reasoning/spof.py`): single points of failure, chokepoint/country concentration and
  *hidden* tier-2 dependencies, e.g. both battery-cell suppliers secretly rely on one distressed copper-foil maker.
- **Inference rules** (`reasoning/rules.py`): declarative Cypher rules materialise `SINGLE_SOURCE`,
  `ROUTED_THROUGH`, `DEPENDS_ON` and `EXPOSED_TO` relationships with provenance.

| Scenario | Lost revenue | After mitigation | Orders at risk |
|---|---|---|---|
| Red Sea closure (active event) | $7.7M | $7.7M | 96 ($75M) |
| Daegu Copper Foil insolvency (tier 2) | $31.0M | $11.3M | 13 |
| FormoSiC outage, 60 days (single source) | $43.0M | $43.0M | 58 |

## Agents, MCP and A2A

```
router (fast model, structured output: language, intent, specialists, standalone task)
  ├─▶ risk specialist      ─┐  bounded ReAct loops, parallel tool calls with timeouts,
  ├─▶ network specialist   ─┼▶ errors fed back to the model, UI artifacts kept out of prompts
  └─▶ research specialist  ─┘
composer ─▶ streams <spoken> summary first (for voice), then the markdown answer
```

```bash
atlas ask "What does the Red Sea closure mean for our revenue?"   # agent in the terminal
atlas ask "ما هي أكبر نقاط الضعف في سلسلة التوريد لدينا؟"            # Arabic works too
atlas serve        # API on :8000 — chat (SSE), map data, scenarios, A2A, MCP
atlas mcp          # MCP over stdio for Claude Desktop / Claude Code
```

- **A2A**: agent card at `/.well-known/agent-card.json`, JSON-RPC at `/a2a`, streaming task status updates.
- **MCP**: streamable HTTP at `/mcp` or stdio via `atlas mcp`; 10 tools plus the ontology as a resource.

## Repository layout

```
backend/atlas/ontology   ontology meta-model, the supply-chain ontology, exporters (Neo4j, OWL, prompt)
backend/atlas/seed       deterministic dataset generator (catalog, network, routing, events, documents)
backend/atlas/graph      Neo4j client and loader
backend/atlas/reasoning  graph snapshot, impact engine, structural risk, inference rules, safe queries
backend/atlas/tools      the tool layer + MCP server
backend/atlas/agent      LangGraph harness, prompts, model factory
backend/atlas/api        FastAPI gateway + A2A server
data/seed                generated dataset: graph JSONL, per-class CSV "ERP exports", Markdown documents
ontology/                exported ontology (Turtle, JSON, prompt schema)
docs/                    architecture notes
```

## License

MIT
