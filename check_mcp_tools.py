import asyncio
import os

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


async def main():
    token = os.environ["RECRUITER_FINANCE_MCP_TOKEN"]
    async with streamablehttp_client(
        "http://localhost:8765/mcp",
        headers={"Authorization": f"Bearer {token}"},
    ) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            for tool in tools.tools:
                print(tool.name)


asyncio.run(main())
