"""MCP (Model Context Protocol) integration for external data sources."""

from .client import MCPClient
from .servers import MCP_SERVER_CONFIG, get_server_command
from .ingestor import ingest_mcp_sources

__all__ = [
    "MCPClient",
    "MCP_SERVER_CONFIG",
    "get_server_command",
    "ingest_mcp_sources",
]
