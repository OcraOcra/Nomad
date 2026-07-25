"""Wrapper for world intelligence MCP server."""

from typing import Dict, Any
from ..client import MCPClient
from ..servers import get_server_command, get_server_path


class IntelWrapper:
    """
    Wrapper for the world intelligence MCP server.
    
    Provides access to geopolitical data, global events, and intelligence reports.
    """
    
    def __init__(self, timeout: int = 60):
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
        - Market quotes (S&P 500, Dow, Nasdaq)
        - Forex rates
        
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
                "market_quotes": {},
                "forex_rates": {},
            }
            
            # Call 1: Get market quotes
            try:
                market = client.call_tool(
                    "intel_market_quotes",
                    {"symbols": ["SPX", "DJI", "IXIC"]}
                )
                result["market_quotes"] = market.get("quotes", [])
            except Exception as e:
                result["market_quotes_error"] = str(e)
            
            # Call 2: Get forex rates
            try:
                forex = client.call_tool(
                    "intel_forex_rates",
                    {"base": "USD", "symbols": ["EUR", "CRC", "MXN"]}
                )
                result["forex_rates"] = forex.get("data", {})
            except Exception as e:
                result["forex_rates_error"] = str(e)
            
            return result
            
        finally:
            client.stop()
