import asyncio
import httpx
from mcp.client.streamable_http import streamable_http_client
from mcp.client.session import ClientSession

TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJkZW1vLXVzZXIiLCJyb2xlIjoiZGVtbyIsImlhdCI6MTc3MTQwMDM1MSwiZXhwIjoxNzcxNDg2NzUxfQ.tEFnmWpDZhX8gP6fsRPvySNImLfot4tC9XxpXHjQn0s"  # your JWT
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

