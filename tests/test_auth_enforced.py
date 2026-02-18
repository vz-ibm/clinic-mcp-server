from __future__ import annotations
import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


@pytest.mark.asyncio
async def test_http_rejects_without_jwt(http_server):
    async with httpx.AsyncClient(timeout=10.0) as client:
        with pytest.raises(Exception):
            async with streamable_http_client(f"{http_server}/mcp", http_client=client) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
