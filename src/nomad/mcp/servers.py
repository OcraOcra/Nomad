"""MCP server configuration and command builder."""

from pathlib import Path
from typing import List, Optional

# Base path for MCP servers (relative to project root)
MCP_BASE_PATH = Path("./mcp-servers")

# Server configurations
MCP_SERVER_CONFIG = {
    "news": {
        "path": MCP_BASE_PATH / "news-server",
        "command": "node",
        "args": ["index.js"],
        "enabled": True,
        "description": "News and market data server (Node.js)",
    },
    "world_intel": {
        "path": MCP_BASE_PATH / "world-intel-server",
        "command": "node",
        "args": ["index.js"],
        "enabled": True,
        "description": "World intelligence and geopolitical data (Node.js)",
    },
    "imf": {
        "path": MCP_BASE_PATH / "imf-server",
        "command": "python",
        "args": ["server.py"],
        "enabled": True,
        "description": "IMF economic indicators (Python)",
    },
}


def get_server_command(server_name: str) -> Optional[List[str]]:
    """
    Build the command to start an MCP server.
    
    Args:
        server_name: Name of the server (e.g., "news", "world_intel", "imf")
    
    Returns:
        List of command arguments for subprocess.Popen, or None if server not found/disabled
    
    Example:
        >>> get_server_command("news")
        ['node', 'index.js']
    """
    config = MCP_SERVER_CONFIG.get(server_name)
    
    if not config or not config.get("enabled", False):
        return None
    
    server_path = config["path"]
    if not server_path.exists():
        return None
    
    command = [config["command"]] + config["args"]
    return command


def get_server_path(server_name: str) -> Optional[Path]:
    """Get the working directory path for a server."""
    config = MCP_SERVER_CONFIG.get(server_name)
    if not config:
        return None
    return config["path"]


def list_enabled_servers() -> List[str]:
    """Return list of enabled server names."""
    return [
        name for name, config in MCP_SERVER_CONFIG.items()
        if config.get("enabled", False)
    ]
