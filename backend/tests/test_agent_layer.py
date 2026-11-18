"""Agent-layer tests that need no LLM: tool schemas, routing fan-out, output parsing, MCP and A2A wiring."""

import asyncio

from atlas.agent.harness import RouteDecision, _accumulate, _split, fan_out, lc_tools
from atlas.agent.prompts import SPECIALISTS
from atlas.tools import TOOLS


def test_every_specialist_tool_exists_and_has_a_schema():
    for spec in SPECIALISTS.values():
        for tool in lc_tools(spec["tools"]):
            assert tool.name in TOOLS
            assert tool.description and len(tool.description) > 40
            assert tool.args_schema.model_json_schema()["type"] == "object"


def test_fan_out_sends_one_task_per_specialist():
    state = {"messages": [], "task": "t", "specialists": ["risk", "research", "risk"], "direct_answer": None}
    sends = fan_out(state)
    assert [s.arg["name"] for s in sends] == ["risk", "research"]
    assert fan_out({**state, "direct_answer": "hello"}) == "composer"


def test_route_decision_defaults():
    d = RouteDecision(language="ar", task="greet")
    assert d.specialists == [] and d.direct_answer is None


def test_composer_output_parsing_streams_spoken_first():
    spoken, answer = _split("<spoken>About 7.7 million dollars at risk.</spoken>\n<answer>**Verdict**")
    assert spoken == "About 7.7 million dollars at risk." and answer == "**Verdict**"
    assert _split("<spoken>partial")[0] is None


def test_accumulator_resets_on_none_and_appends_lists():
    assert _accumulate([1], [2]) == [1, 2]
    assert _accumulate([1], []) == [1]
    assert _accumulate([1], None) == []


def test_mcp_server_lists_all_tools():
    from atlas.tools.mcp_server import build_server

    tools = asyncio.run(build_server().list_tools())
    assert {t.name for t in tools} == set(TOOLS)


def test_a2a_agent_card():
    from atlas.api.a2a_server import agent_card

    card = agent_card("http://localhost:8000")
    assert card.capabilities.streaming
    assert {s.id for s in card.skills} >= {"impact-assessment", "scenario-simulation"}
