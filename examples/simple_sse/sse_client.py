import asyncio
import os
from mcp import ClientSession
from mcp.client.sse import sse_client

TOKEN = os.environ["TOKEN"]
URL = "http://127.0.0.1:8081/sse"


async def main() -> None:
    headers = {"Authorization": f"Bearer {TOKEN}"}

    async with sse_client(url=URL, headers=headers, timeout=10.0) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print(tools)

asyncio.run(main())

