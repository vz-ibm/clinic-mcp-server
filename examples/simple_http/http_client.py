import asyncio
import os
import httpx
from mcp.client.streamable_http import streamable_http_client
from mcp.client.session import ClientSession

TOKEN = os.environ["TOKEN"]
URL = "http://127.0.0.1:8080/mcp"

async def main():
    async with httpx.AsyncClient(
        timeout=10.0,
        headers={"Authorization": f"Bearer {TOKEN}"},
    ) as http_client:
        async with streamable_http_client(URL, http_client=http_client) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                print(tools)

asyncio.run(main())

