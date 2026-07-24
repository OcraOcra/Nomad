"""MCP server configuration and command builder."""

import sys
from pathlib import Path
from typing import List, Optional

# Base path for MCP servers (relative to project root)
MCP_BASE_PATH = Path("./mcp-servers")

# Python executable path (use the same as the current interpreter)
PYTHON_EXECUTABLE = sys.executable

# Server configurations
MCP_SERVER_CONFIG = {
    "news": {
        "path": MCP_BASE_PATH / "mcp-news",
        "command": "cargo",
        "args": ["run", "--release"],
        "enabled": True,
        "description": "News and market data server (Rust/GDELT)",
    },
    "world_intel": {
        "path": MCP_BASE_PATH / "world-intel-mcp",
        "command": PYTHON_EXECUTABLE,
        "args": ["-m", "world_intel_mcp.server"],
        "enabled": True,
        "description": "World intelligence and geopolitical data (Python)",
    },
    "imf": {
        "path": MCP_BASE_PATH / "imf-mcp-server",
        "command": "npx",
        "args": ["-y", "@cyanheads/imf-mcp-server"],
        "enabled": True,
        "description": "IMF economic indicators (Node.js)",
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
        ['cargo', 'run', '--release']
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
