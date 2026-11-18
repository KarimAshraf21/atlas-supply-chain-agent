# Atlas — Architecture

> **Talk to your supply chain.** A multilingual voice agent that reasons over an
> ontology-driven knowledge graph to answer questions like *"What happens to our
> Q1 revenue if the Red Sea stays closed for three more weeks?"* — and shows its work.

## System overview

```
                ┌────────────────────────── Web app (Next.js) ──────────────────────────┐
                │  Voice orb · Chat · Graph explorer · World map · Scenario simulator     │
                └───────────────▲───────────────────────────────▲────────────────────────┘
                                │ WebSocket (audio + events)    │ REST / SSE
                ┌───────────────┴───────────────────────────────┴────────────────────────┐
                │                         API gateway (FastAPI)                          │
                └───────▲──────────────────────▲──────────────────────────▲──────────────┘
                        │                      │                          │
          ┌─────────────┴──────┐   ┌───────────┴───────────┐   ┌──────────┴───────────┐
          │   Voice pipeline   │   │   Agent harness        │   │  A2A server          │
          │ STT → agent → TTS  │   │  (LangGraph supervisor │   │  (Agent Card, tasks, │
          │ language detection │   │   + specialist agents) │   │   streaming)         │
          └────────────────────┘   └───────────▲───────────┘   └──────────────────────┘
                                               │ tools (MCP)
                ┌──────────────────────────────┴───────────────────────────────────────┐
                │                     Reasoning layer (Python)                          │
                │  disruption propagation · SPOF detection · rule-based inference ·     │
                │  alternative sourcing · what-if scenarios · explanation paths         │
                └──────────────────────────────▲───────────────────────────────────────┘
                                               │ Cypher
                ┌──────────────────────────────┴───────────────────────────────────────┐
                │           Knowledge graph (Neo4j) — shaped by the Ontology            │
                └──────────────────────────────▲───────────────────────────────────────┘
                                               │ ingest
                ┌──────────────────────────────┴───────────────────────────────────────┐
                │  Seed data: ERP exports (CSV) · contracts & news (Markdown documents) │
                └──────────────────────────────────────────────────────────────────────┘
```

## Layers

| Layer | Responsibility | Key tech |
|---|---|---|
| **Ontology** | Single source of truth for classes, properties, relationships and constraints. Exported to OWL/Turtle, Neo4j constraints and JSON Schema for LLM tools. | Pydantic, rdflib |
| **Seed data** | Deterministic synthetic company (*Nilewave Energy*): multi-tier suppliers, BOMs, ports, shipping lanes through real chokepoints, orders, contracts, risk events, news. | Python generator |
| **Knowledge graph** | Typed property graph validated against the ontology. | Neo4j 5 Community |
| **Reasoning** | Deterministic, explainable algorithms over the graph. Every answer carries the paths it used. | Cypher + Python |
| **Agent harness** | Supervisor + specialist agents with typed tools, memory, guardrails and tracing. Exposed over A2A and its tools over MCP. | LangGraph, a2a-sdk, mcp |
| **Voice** | Streaming speech-to-text, language detection (Arabic/English/…), spoken answers. | Groq Whisper, TTS |
| **Web** | Production-grade UI with graph and map visualisation of reasoning paths. | Next.js, React |

## Design principles

1. **Ontology first.** The graph, the tools and the prompts are generated from one schema, so they never drift.
2. **Explainable by construction.** The LLM plans and narrates; the reasoning layer computes. Numbers come from the graph, never from the model.
3. **Provenance everywhere.** Inferred facts are tagged with the rule that produced them; answers cite nodes, documents and paths.
4. **Interoperable.** A2A for agent-to-agent, MCP for tools, OpenAI-compatible model providers (Groq by default).
5. **One command.** `docker compose up` brings up the whole stack.
