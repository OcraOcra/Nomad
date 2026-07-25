"""Wrapper for news MCP server."""

import json
from typing import Dict, Any, List
from ..client import MCPClient
from ..servers import get_server_command, get_server_path


def _extract_mcp_result(response: dict) -> Any:
    """
    Extrae el resultado real de una respuesta MCP.
    
    MCP devuelve: {"content": [{"type": "text", "text": "JSON string"}], "isError": false}
    Esta función parsea el JSON string y devuelve el contenido.
    """
    if not isinstance(response, dict):
        return response
    
    # Si tiene "content", extraer el texto JSON
    if "content" in response:
        content = response["content"]
        if isinstance(content, list) and len(content) > 0:
            text = content[0].get("text", "")
            try:
                return json.loads(text)
            except (json.JSONDecodeError, TypeError):
                return text
    
    return response


class NewsWrapper:
    """
    Wrapper for the news MCP server.
    
    Provides access to breaking news, market data, and financial news.
    """
    
    def __init__(self, timeout: int = 60):
        """
        Initialize news wrapper.
        
        Args:
            timeout: Timeout in seconds for each tool call
        """
        self.timeout = timeout
        self.server_name = "news"
    
    def fetch(self) -> Dict[str, Any]:
        """
        Fetch data from news MCP server.
        
        Makes multiple tool calls to get:
        - Breaking news (search_news)
        - Market data (yfinance_chart)
        - Trending topics (get_trending_topics)
        
        Returns:
            Dictionary with consolidated news data
        
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
                "breaking_news": [],
                "market_data": {},
                "trending_topics": [],
            }
            
            # Call 1: Search breaking news
            try:
                raw = client.call_tool(
                    "search_news",
                    {"query": "breaking news", "limit": 5}
                )
                news = _extract_mcp_result(raw)
                if isinstance(news, list):
                    result["breaking_news"] = news
                elif isinstance(news, dict):
                    result["breaking_news"] = news.get("articles", news.get("results", []))
            except Exception as e:
                result["breaking_news_error"] = str(e)
            
            # Call 2: Get market data
            try:
                raw = client.call_tool(
                    "yfinance_chart",
                    {"symbol": "SPY", "period": "1d"}
                )
                market = _extract_mcp_result(raw)
                if isinstance(market, dict):
                    result["market_data"] = market
                elif isinstance(market, str):
                    result["market_data"] = {"raw": market}
            except Exception as e:
                result["market_data_error"] = str(e)
            
            # Call 3: Get trending topics
            try:
                raw = client.call_tool(
                    "get_trending_topics",
                    {"country": "US", "limit": 5}
                )
                trending = _extract_mcp_result(raw)
                if isinstance(trending, list):
                    result["trending_topics"] = trending
                elif isinstance(trending, dict):
                    result["trending_topics"] = trending.get("topics", trending.get("results", []))
            except Exception as e:
                result["trending_topics_error"] = str(e)
            
            return result
            
        finally:
            client.stop()
