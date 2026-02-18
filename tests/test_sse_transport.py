from __future__ import annotations

import pytest

@pytest.mark.asyncio
async def test_sse_connection_and_tool_call(sse_session):
    async with sse_session as session:
        result = await session.call_tool("get_available_dr_specialties", {})
        specs = result.content[0].text
        assert "family" in specs.lower()

