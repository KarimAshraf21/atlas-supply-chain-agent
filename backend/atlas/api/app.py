"""Atlas API gateway: chat (SSE), graph/map data, scenarios, A2A and MCP — one FastAPI app."""

from __future__ import annotations

import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from typing import Any

from a2a.server.routes import add_a2a_routes_to_fastapi
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .. import __version__
from ..config import get_settings
from ..reasoning import Disruption, assess, assess_events, get_snapshot
from ..seed.catalog import PORTS
from ..seed.routing import route_coords
from ..tools import TOOLS, strip_ui, summarise_impact
from ..tools.mcp_server import build_server
from .a2a_server import a2a_routes

BASE_URL = "http://localhost:8000"
RED_SEA = frozenset({"BAB_EL_MANDEB", "SUEZ"})
mcp_app = build_server().streamable_http_app(streamable_http_path="/")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await asyncio.to_thread(get_snapshot)  # warm the reasoning snapshot
    async with mcp_app.router.lifespan_context(mcp_app):
        yield


app = FastAPI(title="Atlas API", version=__version__, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)
card_routes, rpc_routes = a2a_routes(BASE_URL)
add_a2a_routes_to_fastapi(app, agent_card_routes=card_routes, jsonrpc_routes=rpc_routes)
app.mount("/mcp", mcp_app)


# ====================================================================== meta
@app.get("/api/health")
def health() -> dict[str, Any]:
    s = get_settings()
    try:
        snap = get_snapshot()
        graph = {"ok": True, "nodes": len(snap.labels)}
    except Exception as exc:  # pragma: no cover - surfaced to the UI
        graph = {"ok": False, "error": str(exc)}
    return {
        "version": __version__,
        "graph": graph,
        "llm": {
            "provider": "groq",
            "configured": bool(s.groq_api_key and s.groq_api_key.get_secret_value()),
            "reasoning": s.llm_reasoning_model,
            "fast": s.llm_fast_model,
        },
    }


# ====================================================================== chat
class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    thread_id: str | None = None


def _sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"


@app.post("/api/chat")
async def chat(req: ChatRequest) -> StreamingResponse:
    from ..agent import stream_turn

    thread = req.thread_id or uuid.uuid4().hex

    async def events():
        yield _sse({"type": "thread", "thread_id": thread})
        try:
            async for event in stream_turn(req.message, thread):
                yield _sse(event)
        except Exception as exc:
            yield _sse({"type": "error", "message": f"{type(exc).__name__}: {exc}"[:500]})
        yield _sse({"type": "done"})

    return StreamingResponse(
        events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


# ===================================================================== graph
_MAP_LABELS = ("Factory", "Warehouse", "Port", "Chokepoint")


@app.get("/api/overview")
def overview() -> dict[str, Any]:
    """Everything the map and dashboard need, in one call."""
    s = get_snapshot()
    company = next(iter(s.of("Company")))
    ours = set(s.target_ids(company, "OPERATES"))

    def site(fid: str) -> dict[str, Any]:
        p = s.props[fid]
        owner = next(iter(s.source_ids(fid, "OPERATES")), None)
        return {
            "id": fid,
            "kind": s.labels[fid],
            "name": p.get("name"),
            "lat": p.get("lat"),
            "lon": p.get("lon"),
            "ours": fid in ours,
            "owner": owner,
            "tier": s.props.get(owner, {}).get("tier") if owner else None,
        }

    lanes = []
    for lane in s.of("ShippingLane"):
        o, d = s.one(lane, "ORIGIN"), s.one(lane, "DESTINATION")
        p = s.props[lane]
        path = (
            route_coords(o, d, RED_SEA if p.get("is_contingency") else frozenset())
            if p["mode"] == "sea" and o in PORTS and d in PORTS
            else [(s.props[o]["lon"], s.props[o]["lat"]), (s.props[d]["lon"], s.props[d]["lat"])]
        )
        lanes.append(
            {
                "id": lane,
                "name": p["name"],
                "mode": p["mode"],
                "contingency": p.get("is_contingency", False),
                "path": path,
                "transit_days": p["transit_days"],
                "from": o,
                "to": d,
                "via": [c for c, _ in sorted(s.targets(lane, "TRANSITS"), key=lambda x: x[1].get("sequence", 0))],
                "shippers": s.source_ids(lane, "SHIPS_VIA"),
            }
        )
    suppliers = [
        {
            "id": x,
            "name": s.name(x),
            "tier": s.props[x].get("tier"),
            "country": s.props[x].get("country_code"),
            "health": s.props[x].get("financial_health"),
            "category": s.props[x].get("category"),
            "site": next(iter(s.target_ids(x, "OPERATES")), None),
        }
        for x in s.of("Supplier")
    ]
    customers = [
        {
            "id": c,
            "name": s.name(c),
            "country": s.props[c].get("country_code"),
            "region": s.props[c]["region"],
            "strategic": s.props[c].get("strategic"),
            "port": s.one(c, "RECEIVES_AT"),
        }
        for c in s.of("Customer")
    ]
    orders = [s.props[o] for o in s.of("SalesOrder")]
    open_orders = [o for o in orders if o["status"] in ("open", "in_production")]
    return {
        "company": {"id": company, **s.props[company]},
        "sites": [site(f) for f in s.of("Facility")],
        "ports": [
            {
                "id": p,
                "name": s.name(p),
                "name_ar": s.props[p].get("name_ar"),
                "lat": s.props[p]["lat"],
                "lon": s.props[p]["lon"],
                "congestion": s.props[p].get("congestion_index"),
            }
            for p in s.of("Port")
        ],
        "chokepoints": [
            {"id": c, **{k: s.props[c][k] for k in ("name", "name_ar", "lat", "lon", "share_of_global_trade_pct")}}
            for c in s.of("Chokepoint")
        ],
        "lanes": lanes,
        "suppliers": suppliers,
        "customers": customers,
        "products": [
            {"id": p, "name": s.name(p), "family": s.props[p]["family"], "price": s.props[p].get("unit_price_usd")}
            for p in s.of("Product")
        ],
        "kpis": {
            "suppliers": len(suppliers),
            "customers": len(customers),
            "lanes": len(lanes),
            "open_orders": len(open_orders),
            "open_order_value_usd": round(sum(o["value_usd"] for o in open_orders), 2),
            "active_risks": sum(1 for e in s.of("RiskEvent") if s.props[e]["status"] == "active"),
        },
    }


@app.get("/api/graph")
def graph(ids: str = Query(..., description="Comma-separated entity ids"), hops: int = Query(1, ge=0, le=2)):
    """A subgraph around the given entities, for the graph explorer."""
    s = get_snapshot()
    frontier = {i for i in ids.split(",") if i in s.labels}
    if not frontier:
        raise HTTPException(404, "No known ids")
    nodes = set(frontier)
    skip = {"FOR_PRODUCT", "PLACED", "FULFILLED_BY", "MENTIONS"} if hops > 1 else set()
    for _ in range(hops):
        nxt = set()
        for (src, rel), targets in list(s.out.items()):
            if rel in skip:
                continue
            for tgt, _p in targets:
                if src in frontier and tgt not in nodes:
                    nxt.add(tgt)
                elif tgt in frontier and src not in nodes:
                    nxt.add(src)
        nodes |= set(list(nxt)[:250])
        frontier = nxt
    edges = [
        {"source": src, "target": tgt, "type": rel}
        for (src, rel), targets in s.out.items()
        for tgt, _ in targets
        if src in nodes and tgt in nodes
    ]
    return {"nodes": [{"id": n, "label": s.labels[n], "name": s.name(n)} for n in nodes], "edges": edges}


@app.get("/api/entity/{entity_id}")
def entity(entity_id: str) -> dict[str, Any]:
    return strip_ui(TOOLS["get_entity"](entity_id))


@app.get("/api/search")
def search(q: str = Query(..., min_length=1)) -> dict[str, Any]:
    return strip_ui(TOOLS["search_entities"](q))


@app.get("/api/risks")
def risks() -> dict[str, Any]:
    return strip_ui(TOOLS["list_risk_events"]("all"))


@app.get("/api/structural")
def structural() -> dict[str, Any]:
    return TOOLS["structural_risks"]("all")


class ScenarioRequest(BaseModel):
    event_ids: list[str] = Field(default_factory=list)
    disruptions: list[Disruption] = Field(default_factory=list)
    duration_days: int | None = None


@app.post("/api/scenario")
def scenario(req: ScenarioRequest) -> dict[str, Any]:
    """Run the reasoning engine directly (no LLM) — powers the scenario simulator."""
    snap = get_snapshot()
    if req.event_ids:
        report = assess_events(snap, req.event_ids, req.duration_days)
        if req.disruptions:
            report = assess(snap, report.disruptions + req.disruptions)
    elif req.disruptions:
        report = assess(snap, req.disruptions)
    else:
        raise HTTPException(422, "Provide event_ids or disruptions")
    return summarise_impact(report)


# ===================================================================== voice
@app.post("/api/transcribe")
async def transcribe(file: UploadFile = File(...), language: str | None = Form(None)) -> dict[str, Any]:
    """Speech-to-text with Whisper on Groq (fallback for browsers without built-in speech recognition)."""
    s = get_settings()
    if not (s.groq_api_key and s.groq_api_key.get_secret_value()):
        raise HTTPException(503, "GROQ_API_KEY is not configured")
    from groq import AsyncGroq

    audio = await file.read()
    if len(audio) > 20 * 1024 * 1024:
        raise HTTPException(413, "Audio too large")
    client = AsyncGroq(api_key=s.groq_api_key.get_secret_value())
    result = await client.audio.transcriptions.create(
        file=(file.filename or "speech.webm", audio),
        model=s.stt_model,
        language=language or None,
        response_format="verbose_json",
    )
    return {"text": result.text, "language": getattr(result, "language", language)}
