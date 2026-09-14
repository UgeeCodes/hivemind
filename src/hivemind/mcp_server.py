from __future__ import annotations
import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
    HAS_MCP = True
except ImportError:
    HAS_MCP = False

from hivemind.sdk.client import mac, configure

def create_server() -> Server:
    """Create and configure the MCP server with hivemind tools."""
    server = Server("hivemind")
    
    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="run",
                description="Execute a shell command on a remote Mac.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "Shell command to execute"},
                        "machine_id": {"type": "string", "description": "Target machine ID (optional)"},
                        "timeout": {"type": "number", "description": "Timeout in seconds (optional)"},
                    },
                    "required": ["command"],
                },
            ),
            Tool(
                name="read_file",
                description="Read a file from a remote Mac.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path to read"},
                        "machine_id": {"type": "string", "description": "Target machine ID (optional)"},
                    },
                    "required": ["path"],
                },
            ),
            Tool(
                name="write_file",
                description="Write content to a file on a remote Mac.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path to write"},
                        "content": {"type": "string", "description": "File content"},
                        "machine_id": {"type": "string", "description": "Target machine ID (optional)"},
                    },
                    "required": ["path", "content"],
                },
            ),
            Tool(
                name="list_dir",
                description="List directory contents on a remote Mac.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Directory path to list"},
                        "machine_id": {"type": "string", "description": "Target machine ID (optional)"},
                    },
                    "required": ["path"],
                },
            ),
            Tool(
                name="screenshot",
                description="Take a screenshot on a remote Mac.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "machine_id": {"type": "string", "description": "Target machine ID (optional)"},
                        "path": {"type": "string", "description": "Where to save the screenshot (optional, defaults to /tmp/screenshot.png)"},
                    },
                },
            ),
            Tool(
                name="machines",
                description="List all online machines in the fleet.",
                inputSchema={"type": "object", "properties": {}},
            ),
        ]
    
    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        # Configure from env
        url = os.environ.get('HIVEMIND_CONTROL_PLANE')
        token = os.environ.get('HIVEMIND_API_KEY')
        if url or token:
            configure(url=url, token=token)
        
        machine_id = arguments.get('machine_id')
        m = mac(machine_id=machine_id)
        
        if name == 'run':
            result = m.run(
                arguments['command'],
                timeout=arguments.get('timeout'),
            )
            output = result.stdout
            if result.stderr:
                output += f'\n--- stderr ---\n{result.stderr}'
            output += f'\n--- exit code: {result.exit_code} ({result.duration_s:.2f}s) ---'
            return [TextContent(type='text', text=output)]
        
        elif name == 'read_file':
            result = m.run(f'cat {_quote(arguments["path"])}')
            return [TextContent(type='text', text=result.stdout if result.exit_code == 0 else f'Error: {result.stderr}')]
        
        elif name == 'write_file':
            import shlex
            content = arguments['content']
            path = arguments['path']
            # Use heredoc to handle multi-line content safely
            cmd = f'cat > {_quote(path)} << \'HIVEMIND_EOF\'\n{content}\nHIVEMIND_EOF'
            result = m.run(cmd)
            if result.exit_code == 0:
                return [TextContent(type='text', text=f'Written to {path}')]
            return [TextContent(type='text', text=f'Error: {result.stderr}')]
        
        elif name == 'list_dir':
            result = m.run(f'ls -la {_quote(arguments["path"])}')
            return [TextContent(type='text', text=result.stdout if result.exit_code == 0 else f'Error: {result.stderr}')]
        
        elif name == 'screenshot':
            path = arguments.get('path', '/tmp/screenshot.png')
            result = m.run(f'screencapture -x {_quote(path)}')
            if result.exit_code == 0:
                return [TextContent(type='text', text=f'Screenshot saved to {path}')]
            return [TextContent(type='text', text=f'Error: {result.stderr}')]
        
        elif name == 'machines':
            from hivemind.sdk.client import fleet
            macs = fleet()
            lines = [f'- {m.machine_id}' for m in macs]
            return [TextContent(type='text', text=f'{len(macs)} machine(s) online:\n' + '\n'.join(lines) if lines else 'No machines online.')]
        
        return [TextContent(type='text', text=f'Unknown tool: {name}')]
    
    return server

def _quote(s: str) -> str:
    import shlex
    return shlex.quote(s)

async def run_server():
    """Run the MCP server over stdio."""
    if not HAS_MCP:
        raise ImportError(
            'MCP support requires the mcp package. '
            'Install with: pip install "hivemind[mcp]"'
        )
    server = create_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())
