"""Wrapper for IMF MCP server."""

import json
import re
from typing import Dict, Any, List
from ..client import MCPClient
from ..servers import get_server_command, get_server_path


def _extract_mcp_result(response: dict) -> Any:
    """Extrae el resultado real de una respuesta MCP."""
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


def _parse_imf_table(text: str) -> List[Dict[str, Any]]:
    """Parsea la tabla markdown que devuelve IMF a lista de dicts."""
    records = []
    for line in text.split("\n"):
        line = line.strip()
        if not line.startswith("|") or "---" in line or "Series Key" in line:
            continue
        parts = [p.strip() for p in line.split("|")[1:-1]]
        if len(parts) >= 3:
            try:
                records.append({
                    "series": parts[0],
                    "period": parts[1],
                    "value": float(parts[2]) if parts[2] else None,
                })
            except (ValueError, IndexError):
                continue
    return records


class IMFWrapper:
    """
    Wrapper for the IMF MCP server.
    
    Provides access to IMF economic indicators via SDMX 3.0.
    """
    
    def __init__(self, timeout: int = 60):
        self.timeout = timeout
        self.server_name = "imf"
    
    def fetch(self) -> Dict[str, Any]:
        """
        Fetch data from IMF MCP server.
        
        Queries:
        - CPI (Consumer Price Index) for Costa Rica
        - NGDP_RPCH (Real GDP growth) for Costa Rica
        - List available databases
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
                "cpi_data": [],
                "gdp_data": [],
                "available_databases": [],
            }
            
            # Call 1: CPI data for Costa Rica
            try:
                raw = client.call_tool(
                    "imf_query_dataset",
                    {
                        "dataflow_id": "CPI",
                        "key": "CRI.CPI._T.IX.M",
                        "start_period": "2024-01",
                        "end_period": "2025-12",
                    }
                )
                data = _extract_mcp_result(raw)
                if isinstance(data, str) and "|" in data:
                    result["cpi_data"] = _parse_imf_table(data)
                elif isinstance(data, dict) and "data" in data:
                    result["cpi_data"] = data["data"]
            except Exception as e:
                result["cpi_data_error"] = str(e)
            
            # Call 2: GDP data for Costa Rica (World Economic Outlook)
            try:
                raw = client.call_tool(
                    "imf_query_dataset",
                    {
                        "dataflow_id": "WEO",
                        "key": "CRI.NGDP_RPCH.A",
                        "start_period": "2020",
                        "end_period": "2026",
                    }
                )
                data = _extract_mcp_result(raw)
                if isinstance(data, str) and "|" in data:
                    result["gdp_data"] = _parse_imf_table(data)
                elif isinstance(data, dict) and "data" in data:
                    result["gdp_data"] = data["data"]
            except Exception as e:
                result["gdp_data_error"] = str(e)
            
            # Call 3: List available databases
            try:
                raw = client.call_tool("imf_list_databases", {})
                data = _extract_mcp_result(raw)
                if isinstance(data, str):
                    # Extraer nombres de dataflows del markdown
                    flows = re.findall(r"###\s+(\w+)\n\*\*Name:\*\*\s+(.+?)(?:\n|$)", data)
                    result["available_databases"] = [
                        {"id": f[0], "name": f[1]} for f in flows[:20]
                    ]
                elif isinstance(data, list):
                    result["available_databases"] = data[:20]
            except Exception as e:
                result["available_databases_error"] = str(e)
            
            return result
            
        finally:
            client.stop()
