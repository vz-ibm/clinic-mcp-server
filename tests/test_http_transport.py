from __future__ import annotations

import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


@pytest.mark.asyncio
async def test_http_connection_and_tool_call(http_session):
    async with http_session as session:
        result = await session.call_tool("get_available_dr_specialties", {})
        specs = result.content[0].text
        assert "family" in specs.lower()



