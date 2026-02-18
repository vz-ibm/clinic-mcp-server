from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_stdio_connection_and_tool_call(stdio_session):
    async with stdio_session as session:
        result = await session.call_tool("get_available_dr_specialties", {})
        # MCP returns tool output in content
        specs = result.content[0].text
        assert isinstance(specs, str)  # usually JSON text
        # loose smoke assertion:
        assert "family" in specs.lower()
