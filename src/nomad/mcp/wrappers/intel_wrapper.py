"""Wrapper for world intelligence MCP server."""

from typing import Dict, Any
from ..client import MCPClient
from ..servers import get_server_command, get_server_path


class IntelWrapper:
    """
    Wrapper for the world intelligence MCP server.
    
    Provides access to geopolitical data, global events, and intelligence reports.
    """
    
    def __init__(self, timeout: int = 30):
        """
        Initialize intel wrapper.
        
        Args:
            timeout: Timeout in seconds for each tool call
        """
        self.timeout = timeout
        self.server_name = "world_intel"
    
    def fetch(self) -> Dict[str, Any]:
        """
        Fetch data from world intelligence MCP server.
        
        Makes multiple tool calls to get:
        - Global risk assessments
        - Geopolitical events
        - Regional stability indices
        
        Returns:
            Dictionary with consolidated intelligence data
        
        Raises:
            RuntimeError: If server fails to start or all calls fail
        """
        command = get_server_command(self.server_name)
        server_path = get_server_path(self.server_name)
        
        if not command or not server_path:
            raise RuntimeError(f"Server '{self.server_name}' not configured or not found")
        
        client = MCPClient(server_path, command, timeout=self.timeout)
        
        try:
            client.start()
            
            result = {
                "source": self.server_name,
                "risk_assessments": [],
                "geopolitical_events": [],
                "stability_indices": {},
            }
            
            # Call 1: Get global risk assessments
            try:
                risks = client.call_tool(
                    "get_risk_assessments",
                    {"regions": ["americas", "europe", "asia"], "level": "high"}
                )
                result["risk_assessments"] = risks.get("assessments", [])
            except Exception as e:
                result["risk_assessments_error"] = str(e)
            
            # Call 2: Get recent geopolitical events
            try:
                events = client.call_tool(
                    "get_geopolitical_events",
                    {"days": 7, "impact": "significant"}
                )
                result["geopolitical_events"] = events.get("events", [])
            except Exception as e:
                result["geopolitical_events_error"] = str(e)
            
            # Call 3: Get regional stability indices
            try:
                stability = client.call_tool(
                    "get_stability_indices",
                    {"countries": ["USA", "CHN", "DEU", "BRA"]}
                )
                result["stability_indices"] = stability.get("indices", {})
            except Exception as e:
                result["stability_indices_error"] = str(e)
            
            return result
            
        finally:
            client.stop()
