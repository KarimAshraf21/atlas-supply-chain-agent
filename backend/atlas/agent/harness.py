"""The Atlas agent harness (LangGraph).

    ┌────────┐   Send (parallel)   ┌──────────────┐
    │ router │ ──────────────────▶ │ specialist×N │ ──┐
    └───┬────┘                     │ (ReAct loop) │   │
        │ direct answer            └──────────────┘   ▼
        └───────────────────────────────────────▶ ┌──────────┐
                                                   │ composer │ ─▶ spoken summary + markdown answer
                                                   └──────────┘

* Router (fast model, structured output): language, intent, which specialists, standalone task.
* Specialists (reasoning model + scoped tools): bounded tool loops, parallel tool execution with
  timeouts, errors fed back to the model, tool artifacts (graph highlights, reports) kept out of prompts.
* Composer: streams `<spoken>` first (so voice can start talking immediately) then the markdown answer.
* Memory: per-thread checkpointing; every step emits structured events for the UI and A2A clients.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import time
import typing
from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import Send
from pydantic import BaseModel, Field, create_model

from ..config import get_settings
from ..tools import TOOLS, strip_ui
from . import prompts
from .llm import get_llm

Specialist = Literal["risk", "network", "research"]


# ===================================================================== state
class Finding(TypedDict):
    specialist: str
    notes: str
    tool_calls: list[dict[str, Any]]
    seconds: float


def _accumulate(left: list | None, right: list | None) -> list:
    """Parallel specialists append; ``None`` (sent by the reset node) clears the list for a new turn."""
    return [] if right is None else (left or []) + right


class AtlasState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    language: str
    task: str
    specialists: list[str]
    direct_answer: str | None
    findings: Annotated[list[Finding], _accumulate]
    ui: Annotated[list[dict[str, Any]], _accumulate]
    final: dict[str, Any]


class RouteDecision(BaseModel):
    language: str = Field(description="ISO 639-1 code of the user's language, e.g. en or ar.")
    task: str = Field(description="Standalone English restatement of the user's request.")
    specialists: list[Specialist] = Field(default_factory=list, description="Specialists to consult.")
    direct_answer: str | None = Field(None, description="Only for greetings/small talk/off-topic.")


# ===================================================================== tools
def _lc_tool(name: str) -> StructuredTool:
    fn = TOOLS[name]
    hints = typing.get_type_hints(fn)
    fields: dict[str, Any] = {}
    for p in inspect.signature(fn).parameters.values():
        default = ... if p.default is inspect.Parameter.empty else p.default
        fields[p.name] = (hints[p.name], default)
    schema = create_model(f"{name}_args", **fields)

    def run(**kwargs: Any) -> tuple[str, dict[str, Any] | None]:
        result = fn(**kwargs)
        return json.dumps(strip_ui(result), ensure_ascii=False, default=str), result.get("ui")

    return StructuredTool.from_function(
        func=run,
        name=name,
        description=inspect.getdoc(fn) or name,
        args_schema=schema,
        response_format="content_and_artifact",
    )


_TOOL_CACHE: dict[str, StructuredTool] = {}


def lc_tools(names: list[str]) -> list[StructuredTool]:
    for n in names:
        if n not in _TOOL_CACHE:
            _TOOL_CACHE[n] = _lc_tool(n)
    return [_TOOL_CACHE[n] for n in names]


def _history(messages: list[AnyMessage], turns: int = 6) -> list[AnyMessage]:
    return [m for m in messages if isinstance(m, HumanMessage | AIMessage) and not getattr(m, "tool_calls", None)][
        -turns:
    ]


# ===================================================================== nodes
async def router(state: AtlasState) -> dict[str, Any]:
    writer = get_stream_writer()
    writer({"type": "status", "stage": "routing"})
    llm = get_llm("fast").with_structured_output(RouteDecision)
    decision: RouteDecision = await llm.ainvoke([SystemMessage(prompts.ROUTER), *_history(state["messages"], turns=8)])
    writer(
        {
            "type": "route",
            "language": decision.language,
            "task": decision.task,
            "specialists": decision.specialists,
            "direct": bool(decision.direct_answer),
        }
    )
    return {
        "language": decision.language,
        "task": decision.task,
        "specialists": list(decision.specialists),
        "direct_answer": decision.direct_answer,
    }


def fan_out(state: AtlasState) -> list[Send] | str:
    if state.get("direct_answer") or not state.get("specialists"):
        return "composer"
    return [
        Send("specialist", {"name": s, "task": state["task"], "history": _history(state["messages"])})
        for s in dict.fromkeys(state["specialists"])
    ]


async def specialist(payload: dict[str, Any]) -> dict[str, Any]:
    name: str = payload["name"]
    settings = get_settings()
    writer = get_stream_writer()
    writer({"type": "status", "stage": "specialist", "specialist": name})
    started = time.perf_counter()

    tools = lc_tools(prompts.SPECIALISTS[name]["tools"])
    by_name = {t.name: t for t in tools}
    llm = get_llm("reasoning").bind_tools(tools)
    msgs: list[AnyMessage] = [
        SystemMessage(prompts.specialist_prompt(name)),
        *payload.get("history", [])[:-1],
        HumanMessage(payload["task"]),
    ]
    calls_log: list[dict[str, Any]] = []
    ui: list[dict[str, Any]] = []
    notes = ""

    async def execute(call: dict[str, Any]) -> ToolMessage:
        t0 = time.perf_counter()
        writer({"type": "tool_start", "specialist": name, "id": call["id"], "tool": call["name"], "args": call["args"]})
        tool = by_name.get(call["name"])
        try:
            if tool is None:
                raise ValueError(f"Unknown tool {call['name']}")
            msg: ToolMessage = await asyncio.wait_for(
                asyncio.to_thread(tool.invoke, {**call, "type": "tool_call"}), settings.agent_tool_timeout_s
            )
            ok = True
        except Exception as exc:  # feed the error back to the model
            msg = ToolMessage(
                content=json.dumps({"error": f"{type(exc).__name__}: {exc}"[:600]}),
                tool_call_id=call["id"],
                name=call["name"],
            )
            ok = False
        artifact = getattr(msg, "artifact", None)
        if artifact:
            ui.append({"tool": call["name"], **artifact})
        elapsed = round(time.perf_counter() - t0, 2)
        calls_log.append({"tool": call["name"], "args": call["args"], "ok": ok, "seconds": elapsed})
        writer(
            {
                "type": "tool_end",
                "specialist": name,
                "id": call["id"],
                "tool": call["name"],
                "ok": ok,
                "seconds": elapsed,
                "ui": artifact,
            }
        )
        return msg

    for step in range(settings.agent_max_steps):
        ai: AIMessage = await llm.ainvoke(msgs)
        msgs.append(ai)
        if not ai.tool_calls:
            notes = ai.content if isinstance(ai.content, str) else json.dumps(ai.content)
            break
        msgs.extend(await asyncio.gather(*(execute(c) for c in ai.tool_calls)))
        if step == settings.agent_max_steps - 1:
            final = await get_llm("reasoning").ainvoke(
                [*msgs, HumanMessage("Tool budget exhausted. Write your analyst notes now from what you have.")]
            )
            notes = str(final.content)

    finding: Finding = {
        "specialist": name,
        "notes": notes,
        "tool_calls": calls_log,
        "seconds": round(time.perf_counter() - started, 2),
    }
    writer({"type": "finding", "specialist": name, "seconds": finding["seconds"], "tool_calls": len(calls_log)})
    return {"findings": [finding], "ui": ui}


def _split(buffer: str) -> tuple[str | None, str]:
    """Return (spoken if complete, answer-so-far) from the composer's tagged output."""
    spoken = None
    if "</spoken>" in buffer:
        spoken = buffer.split("<spoken>", 1)[-1].split("</spoken>", 1)[0].strip()
    answer = buffer.split("<answer>", 1)[1] if "<answer>" in buffer else ""
    return spoken, answer.split("</answer>", 1)[0]


async def composer(state: AtlasState) -> dict[str, Any]:
    writer = get_stream_writer()
    language = state.get("language", "en")
    highlight = list(dict.fromkeys(n for u in state.get("ui", []) for n in (u.get("highlight") or [])))

    if state.get("direct_answer"):
        text = state["direct_answer"]
        final = {"answer": text, "spoken": text, "language": language, "highlight": [], "ui": []}
        writer({"type": "spoken", "text": text})
        writer({"type": "answer", **final})
        return {"final": final, "messages": [AIMessage(text)]}

    writer({"type": "status", "stage": "composing"})
    notes = "\n\n".join(f"## {f['specialist']} notes\n{f['notes']}" for f in state.get("findings", []))
    msgs = [
        SystemMessage(prompts.COMPOSER.format(language=language)),
        *_history(state["messages"])[:-1],
        HumanMessage(f"User request: {state['messages'][-1].content}\n\nSpecialist notes:\n{notes}"),
    ]
    buffer, sent_spoken, sent_len = "", False, 0
    async for chunk in get_llm("reasoning", temperature=0.3).astream(msgs):
        buffer += chunk.content if isinstance(chunk.content, str) else ""
        spoken, answer = _split(buffer)
        if spoken and not sent_spoken:
            writer({"type": "spoken", "text": spoken})
            sent_spoken = True
        if len(answer) > sent_len:
            writer({"type": "token", "text": answer[sent_len:]})
            sent_len = len(answer)
    spoken, answer = _split(buffer)
    if not answer:  # model ignored the format: degrade gracefully
        answer, spoken = buffer.strip(), spoken or buffer.strip()[:300]
    final = {
        "answer": answer.strip(),
        "spoken": spoken or "",
        "language": language,
        "highlight": highlight,
        "ui": state.get("ui", []),
        "trace": [{k: f[k] for k in ("specialist", "tool_calls", "seconds")} for f in state.get("findings", [])],
    }
    writer({"type": "answer", **{k: v for k, v in final.items() if k != "ui"}})
    return {"final": final, "messages": [AIMessage(answer.strip())]}


async def reset_turn(state: AtlasState) -> dict[str, Any]:
    """Clear per-turn accumulators so they don't leak across turns on the same thread."""
    return {"findings": None, "ui": None, "final": {}, "direct_answer": None}


# ===================================================================== graph
def build_graph(checkpointer: Any | None = None):
    g = StateGraph(AtlasState)
    g.add_node("reset", reset_turn)
    g.add_node("router", router)
    g.add_node("specialist", specialist)
    g.add_node("composer", composer)
    g.add_edge(START, "reset")
    g.add_edge("reset", "router")
    g.add_conditional_edges("router", fan_out, ["specialist", "composer"])
    g.add_edge("specialist", "composer")
    g.add_edge("composer", END)
    return g.compile(checkpointer=checkpointer or InMemorySaver())


_GRAPH = None


def get_graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph()
    return _GRAPH


def _config(thread_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": thread_id}, "recursion_limit": 40}


async def stream_turn(message: str, thread_id: str):
    """Run one conversational turn, yielding structured events (route, tool_start/end, spoken, token, answer)."""
    async for event in get_graph().astream(
        {"messages": [HumanMessage(message)]}, _config(thread_id), stream_mode="custom"
    ):
        yield event


async def run_turn(message: str, thread_id: str) -> dict[str, Any]:
    """Run one turn to completion and return the final answer payload."""
    async for _ in stream_turn(message, thread_id):
        pass
    state = await get_graph().aget_state(_config(thread_id))
    return state.values.get("final", {})
