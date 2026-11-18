"""Expose the Atlas tool layer as an MCP server (stdio or streamable HTTP)."""

from __future__ import annotations

import functools
import inspect
import json
import typing
from typing import Any

from mcp.server.mcpserver import MCPServer

from ..ontology import ONTOLOGY
from ..ontology.exporters import to_prompt
from .registry import TOOLS, strip_ui

INSTRUCTIONS = (
    "Atlas answers supply-chain risk questions for Nilewave Energy (fictional) from a knowledge graph. "
    "Resolve names with search_entities, then use assess_risk_events / simulate_scenario for impact, "
    "structural_risks / find_alternatives / trace_dependencies for network analysis, search_documents for "
    "sources, and query_graph for anything else. Numbers come from the graph; cite entity and document ids."
)


def _wrap(fn):
    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> str:
        return json.dumps(strip_ui(fn(*args, **kwargs)), ensure_ascii=False, default=str)

    hints = typing.get_type_hints(fn)
    sig = inspect.signature(fn)
    params = [p.replace(annotation=hints.get(p.name, p.annotation)) for p in sig.parameters.values()]
    wrapper.__signature__ = sig.replace(parameters=params, return_annotation=str)  # type: ignore[attr-defined]
    wrapper.__annotations__ = {**{p.name: p.annotation for p in params}, "return": str}
    return wrapper


def build_server() -> MCPServer:
    server = MCPServer(name="atlas", title="Atlas Supply-Chain Graph", instructions=INSTRUCTIONS, version="0.2.0")
    for name, fn in TOOLS.items():
        server.tool(name=name, structured_output=False)(_wrap(fn))

    @server.resource("atlas://ontology", name="ontology", description="The Atlas ontology schema (text).")
    def ontology() -> str:
        return to_prompt(ONTOLOGY)

    return server
