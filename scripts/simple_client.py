import asyncio
import httpx
from mcp.client.streamable_http import streamable_http_client
from mcp.client.session import ClientSession
from mcp.types import ListToolsResult

TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJkZW1vLXVzZXIiLCJyb2xlIjoiZGVtbyIsImlhdCI6MTc3MTQ5NzU0MiwiZXhwIjoxNzcxNTgzOTQyfQ.-G04-_llHc9l2xqldw-J0m03QoBLYwNGPLC9Y2UVS_E"  # your JWT
URL = "http://127.0.0.1:8080/mcp"

async def main():
    async with httpx.AsyncClient(
        timeout=10.0,
        headers={"Authorization": f"Bearer {TOKEN}"},
    ) as http_client:
        async with streamable_http_client(URL, http_client=http_client) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools: ListToolsResult = await session.list_tools()
                print(tools.model_dump_json(indent=2))

asyncio.run(main())

