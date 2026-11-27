"""EquiPop's MCP server - the fourth door, on the person's own
computer (BACKLOG 522, R-63). `python -m equipop.mcp` or `equipop mcp`
starts it on stdio; `pip install "equipop[mcp]"` brings the mcp
package it needs. The tools are in equipop/mcp/server.py."""
from .server import SERVER_NAME, build_server, main

__all__ = ["SERVER_NAME", "build_server", "main"]
