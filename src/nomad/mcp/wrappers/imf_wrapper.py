"""Wrapper for IMF MCP server."""

import json
from typing import Dict, Any
from ..client import MCPClient
from ..servers import get_server_command, get_server_path


def _extract_mcp_result(response: dict) -> Any:
    """
    Extrae el resultado real de una respuesta MCP.
    
    MCP devuelve: {"content": [{"type": "text", "text": "JSON string"}], "isError": false}
    """
    if not isinstance(response, dict):
        return response
    
    if "content" in response:
        content = response["content"]
        if isinstance(content, list) and len(content) > 0:
            text = content[0].get("text", "")
            try:
                return json.loads(text)
            except (json.JSONDecodeError, TypeError):
                return text
    
    return response


class IMFWrapper:
    """
    Wrapper for the IMF MCP server.
    
    Provides access to IMF economic indicators, forecasts, and policy data.
    """
    
    def __init__(self, timeout: int = 60):
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
                raw = client.call_tool(
                    "imf_query_dataset",
                    {"dataflow": "PGI", "key": "CRI+USA+MXN..NGDP_RPCH", "start": "2022", "end": "2025"}
                )
                gdp = _extract_mcp_result(raw)
                if isinstance(gdp, dict):
                    result["gdp_data"] = gdp.get("data", gdp.get("series", gdp))
                elif isinstance(gdp, list):
                    result["gdp_data"] = {"records": gdp}
            except Exception as e:
                result["gdp_data_error"] = str(e)
            
            # Call 2: Get inflation data
            try:
                raw = client.call_tool(
                    "imf_query_dataset",
                    {"dataflow": "CPI", "key": "CRI+USA+MXN.PCPI_IX", "start": "2022", "end": "2025"}
                )
                inflation = _extract_mcp_result(raw)
                if isinstance(inflation, dict):
                    result["inflation_data"] = inflation.get("data", inflation.get("series", inflation))
                elif isinstance(inflation, list):
                    result["inflation_data"] = {"records": inflation}
            except Exception as e:
                result["inflation_data_error"] = str(e)
            
            # Call 3: List databases (más simple, menos likely de fallar)
            try:
                raw = client.call_tool(
                    "imf_list_databases",
                    {}
                )
                databases = _extract_mcp_result(raw)
                if isinstance(databases, list):
                    result["fiscal_indicators"] = {"databases": databases[:10]}
                elif isinstance(databases, dict):
                    result["fiscal_indicators"] = databases
            except Exception as e:
                result["fiscal_indicators_error"] = str(e)
            
            return result
            
        finally:
            client.stop()
