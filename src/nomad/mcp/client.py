"""MCP client implementation with JSON-RPC 2.0 protocol."""

import json
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional


class MCPClient:
    """
    Client for communicating with MCP servers via JSON-RPC 2.0 over stdio.
    
    Handles process lifecycle, timeout management, and zombie process prevention.
    """
    
    def __init__(self, server_path: Path, args: list[str], timeout: int = 60, init_timeout: int = 180):
        """
        Initialize MCP client.
        
        Args:
            server_path: Working directory for the server process
            args: Command arguments to start the server (e.g., ['node', 'index.js'])
            timeout: Default timeout in seconds for tool calls
            init_timeout: Timeout for the initial handshake (servers with many tools need more time)
        """
        self.server_path = server_path
        self.args = args
        self.timeout = timeout
        self.init_timeout = init_timeout
        self.process: Optional[subprocess.Popen] = None
        self._request_id = 0
        self._initialized = False
    
    def start(self) -> None:
        """
        Start the MCP server process.
        
        Raises:
            RuntimeError: If process fails to start
        """
        try:
            self.process = subprocess.Popen(
                self.args,
                cwd=str(self.server_path),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,  # Line buffered
            )
            # Send initialize request
            self._initialize()
        except Exception as e:
            raise RuntimeError(f"Failed to start MCP server: {e}")
    
    def _initialize(self) -> None:
        """Send initialize request to MCP server."""
        if not self.process or self.process.poll() is not None:
            raise RuntimeError("MCP server process not running")
        
        # Build initialize request
        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "nomad-mcp-client",
                    "version": "1.0.0"
                }
            },
            "id": self._request_id
        }
        
        # Send request
        try:
            request_json = json.dumps(request) + "\n"
            self.process.stdin.write(request_json)
            self.process.stdin.flush()
        except Exception as e:
            raise RuntimeError(f"Failed to send initialize request: {e}")
        
        # Read response with timeout
        response_data = {}
        response_ready = threading.Event()
        
        def read_response():
            try:
                line = self.process.stdout.readline()
                if line:
                    response_data["raw"] = line.strip()
                    response_ready.set()
            except Exception as e:
                response_data["error"] = str(e)
                response_ready.set()
        
        reader_thread = threading.Thread(target=read_response, daemon=True)
        reader_thread.start()
        
        # Wait for response or timeout (init_timeout is longer for servers with many tools)
        if not response_ready.wait(timeout=self.init_timeout):
            # Timeout - kill process to prevent zombies
            self.stop()
            raise TimeoutError(f"Initialize timed out after {self.init_timeout}s")
        
        # Parse response
        if "error" in response_data:
            raise RuntimeError(f"Failed to read initialize response: {response_data['error']}")
        
        try:
            response = json.loads(response_data["raw"])
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Invalid JSON response: {e}")
        
        # Check for JSON-RPC errors
        if "error" in response:
            error_msg = response["error"].get("message", "Unknown error")
            raise RuntimeError(f"MCP server initialize error: {error_msg}")
        
        # Send initialized notification
        self._send_notification("notifications/initialized", {})
        self._initialized = True
    
    def _send_notification(self, method: str, params: Dict[str, Any]) -> None:
        """Send a notification to the MCP server."""
        if not self.process or self.process.poll() is not None:
            return
        
        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params
        }
        
        try:
            notification_json = json.dumps(notification) + "\n"
            self.process.stdin.write(notification_json)
            self.process.stdin.flush()
        except Exception:
            pass
    
    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Call a tool on the MCP server using JSON-RPC 2.0.
        
        Args:
            tool_name: Name of the tool to call
            arguments: Dictionary of arguments to pass to the tool
        
        Returns:
            Dictionary containing the tool's response
        
        Raises:
            RuntimeError: If process not started or communication fails
            TimeoutError: If call exceeds timeout
        
        Example:
            >>> client.call_tool("get_breaking_news", {"limit": 10})
            {"articles": [...]}
        """
        if not self._initialized:
            raise RuntimeError("MCP client not initialized")
        
        if not self.process or self.process.poll() is not None:
            raise RuntimeError("MCP server process not running")
        
        # Build JSON-RPC 2.0 request
        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
            "id": self._request_id,
        }
        
        # Send request
        try:
            request_json = json.dumps(request) + "\n"
            self.process.stdin.write(request_json)
            self.process.stdin.flush()
        except Exception as e:
            raise RuntimeError(f"Failed to send request: {e}")
        
        # Read response with timeout
        response_data = {}
        response_ready = threading.Event()
        
        def read_response():
            try:
                line = self.process.stdout.readline()
                if line:
                    response_data["raw"] = line.strip()
                    response_ready.set()
            except Exception as e:
                response_data["error"] = str(e)
                response_ready.set()
        
        reader_thread = threading.Thread(target=read_response, daemon=True)
        reader_thread.start()
        
        # Wait for response or timeout
        if not response_ready.wait(timeout=self.timeout):
            # Timeout - kill process to prevent zombies
            self.stop()
            raise TimeoutError(f"Tool call '{tool_name}' timed out after {self.timeout}s")
        
        # Parse response
        if "error" in response_data:
            raise RuntimeError(f"Failed to read response: {response_data['error']}")
        
        try:
            response = json.loads(response_data["raw"])
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Invalid JSON response: {e}")
        
        # Check for JSON-RPC errors
        if "error" in response:
            error_msg = response["error"].get("message", "Unknown error")
            raise RuntimeError(f"MCP server error: {error_msg}")
        
        return response.get("result", {})
    
    def stop(self) -> None:
        """
        Gracefully stop the MCP server process.
        
        Attempts terminate() first, then kill() if process doesn't exit within 5s.
        """
        if not self.process:
            return
        
        try:
            # Try graceful termination
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                # Force kill if terminate didn't work
                self.process.kill()
                self.process.wait(timeout=2)
        except Exception:
            # Last resort - kill immediately
            try:
                self.process.kill()
            except Exception:
                pass
        finally:
            self.process = None
            self._initialized = False
    
    def __enter__(self):
        """Context manager entry - start server."""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - stop server."""
        self.stop()
