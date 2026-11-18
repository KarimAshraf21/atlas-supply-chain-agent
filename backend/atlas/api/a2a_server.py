"""Expose the Atlas agent over the A2A protocol (agent card + JSON-RPC, streaming task updates)."""

from __future__ import annotations

from a2a.helpers.proto_helpers import new_data_part, new_task_from_user_message, new_text_part
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events.event_queue_v2 import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentProvider, AgentSkill, TaskState

from ..agent import stream_turn

TOOL_LABELS = {
    "assess_risk_events": "Quantifying impact",
    "simulate_scenario": "Simulating scenario",
    "structural_risks": "Scanning for single points of failure",
    "trace_dependencies": "Tracing multi-tier dependencies",
    "find_alternatives": "Looking for alternatives",
    "search_documents": "Searching documents",
    "search_entities": "Resolving entities",
    "get_entity": "Reading entity",
    "list_risk_events": "Listing risk events",
    "query_graph": "Querying the knowledge graph",
}


def agent_card(base_url: str) -> AgentCard:
    return AgentCard(
        name="Atlas Supply-Chain Analyst",
        description=(
            "Answers supply-chain risk questions over an ontology-driven knowledge graph: disruption impact, "
            "what-if scenarios, single points of failure, alternatives and contract exposure. English and Arabic."
        ),
        version="0.2.0",
        provider=AgentProvider(organization="Atlas (portfolio project)", url="https://github.com/KarimAshraf21"),
        supported_interfaces=[
            AgentInterface(url=f"{base_url}/a2a", protocol_binding="JSONRPC", protocol_version="1.0")
        ],
        capabilities=AgentCapabilities(streaming=True, push_notifications=False),
        default_input_modes=["text/plain"],
        default_output_modes=["text/markdown", "application/json"],
        skills=[
            AgentSkill(
                id="impact-assessment",
                name="Disruption impact assessment",
                description="Quantify revenue, orders, customers and penalties affected by a risk event.",
                tags=["risk", "supply-chain", "impact"],
                examples=["What does the Red Sea closure mean for Q1 revenue?"],
            ),
            AgentSkill(
                id="scenario-simulation",
                name="What-if simulation",
                description="Simulate closures, delays, supplier outages or insolvencies.",
                tags=["scenario", "what-if"],
                examples=["Close the Suez Canal for 45 days."],
            ),
            AgentSkill(
                id="network-risk",
                name="Network risk analysis",
                description="Single points of failure, hidden tier-2 dependencies, concentration, alternatives.",
                tags=["resilience", "dependencies"],
                examples=["Where are we single-sourced?"],
            ),
            AgentSkill(
                id="document-research",
                name="Contract & news research",
                description="Find force-majeure, penalty and exclusivity clauses; summarise news (EN/AR).",
                tags=["contracts", "news", "graphrag"],
                examples=["Which customer contracts have no force majeure?"],
            ),
        ],
    )


class AtlasAgentExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        text = context.get_user_input()
        task = context.current_task
        if task is None:
            task = new_task_from_user_message(context.message)
            await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue, task.id, task.context_id)
        await updater.start_work()

        final: dict = {}
        async for event in stream_turn(text, thread_id=f"a2a-{task.context_id}"):
            kind = event.get("type")
            if kind == "tool_start":
                label = TOOL_LABELS.get(event["tool"], event["tool"])
                await updater.update_status(
                    TaskState.TASK_STATE_WORKING, message=updater.new_agent_message([new_text_part(f"{label}…")])
                )
            elif kind == "answer":
                final = event

        await updater.add_artifact(
            [
                new_text_part(final.get("answer", ""), media_type="text/markdown"),
                new_data_part({k: final.get(k) for k in ("spoken", "language", "highlight", "trace")}),
            ],
            name="atlas-answer",
        )
        await updater.complete()

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        if context.current_task:
            await TaskUpdater(event_queue, context.current_task.id, context.current_task.context_id).cancel()


def a2a_routes(base_url: str):
    card = agent_card(base_url)
    handler = DefaultRequestHandler(
        agent_executor=AtlasAgentExecutor(), task_store=InMemoryTaskStore(), agent_card=card
    )
    return create_agent_card_routes(card), create_jsonrpc_routes(handler, rpc_url="/a2a")
