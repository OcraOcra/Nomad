"""Wrapper for IMF MCP server."""

from typing import Dict, Any
from ..client import MCPClient
from ..servers import get_server_command, get_server_path


class IMFWrapper:
    """
    Wrapper for the IMF MCP server.
    
    Provides access to IMF economic indicators, forecasts, and policy data.
    """
    
    def __init__(self, timeout: int = 30):
        """
        Initialize IMF wrapper.
        
        Args:
            timeout: Timeout in seconds for each tool call
        """
        self.timeout = timeout
        self.server_name = "imf"
    
    def fetch(self) -> Dict[str, Any]:
        """
        Fetch data from IMF MCP server.
        
        Makes multiple tool calls to get:
        - GDP growth rates
        - Inflation data
        - Fiscal indicators
        
        Returns:
            Dictionary with consolidated IMF economic data
        
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
                "gdp_data": {},
                "inflation_data": {},
                "fiscal_indicators": {},
            }
            
            # Call 1: Get GDP data
            try:
                gdp = client.call_tool(
                    "get_gdp",
                    {"countries": ["CRI", "USA", "MEX"], "years": [2023, 2024, 2025]}
                )
                result["gdp_data"] = gdp.get("data", {})
            except Exception as e:
                result["gdp_data_error"] = str(e)
            
            # Call 2: Get inflation data
            try:
                inflation = client.call_tool(
                    "get_inflation",
                    {"countries": ["CRI", "USA", "MEX"], "indicator": "CPI"}
                )
                result["inflation_data"] = inflation.get("data", {})
            except Exception as e:
                result["inflation_data_error"] = str(e)
            
            # Call 3: Get fiscal indicators
            try:
                fiscal = client.call_tool(
                    "get_fiscal_indicators",
                    {"countries": ["CRI"], "indicators": ["debt_to_gdp", "fiscal_balance"]}
                )
                result["fiscal_indicators"] = fiscal.get("data", {})
            except Exception as e:
                result["fiscal_indicators_error"] = str(e)
            
            return result
            
        finally:
            client.stop()
