import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from contextlib import AsyncExitStack
import sys
import os
class MCPConnection:
    def __init__(self, script_path: str):
        self.server_params = StdioServerParameters(
            command=sys.executable,
            args=[script_path],
            env=os.environ.copy()
        )
        self.session = None
        self.exit_stack = AsyncExitStack()

    async def connect(self):
        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(self.server_params))
        self.read, self.write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(ClientSession(self.read, self.write))
        await self.session.initialize()

    async def get_tools(self):
        if not self.session:
            await self.connect()
        response = await self.session.list_tools()
        tools = []
        for t in response.tools:
            tools.append({
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.inputSchema
                }
            })
        return tools

    async def call_tool(self, name: str, args: dict):
        if not self.session:
            await self.connect()
        result = await self.session.call_tool(name, arguments=args)
        return "\n".join(item.text for item in result.content if item.type == "text")

    async def close(self):
        await self.exit_stack.aclose()