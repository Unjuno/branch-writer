"""E2E browser test using @playwright/mcp via stdio transport.

Requires:
  - Streamlit app running on http://localhost:8502
  - @playwright/mcp installed (npx -y @playwright/mcp)
  - Playwright Chromium browser installed

Usage:
  python -m pytest tests/test_e2e_browser.py -v --asyncio-mode=auto
"""

from __future__ import annotations

import contextlib

import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

STREAMLIT_URL = "http://localhost:8502"

pytestmark = pytest.mark.skip(
    reason="Requires Streamlit on :8502 and @playwright/mcp. Run manually."
)


@contextlib.asynccontextmanager
async def _playwright_session():
    params = StdioServerParameters(command="npx", args=["-y", "@playwright/mcp"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


@pytest.mark.asyncio
async def test_page_loads() -> None:
    async with _playwright_session() as session:
        nav = await session.call_tool("browser_navigate", {"url": STREAMLIT_URL})
        assert not nav.isError

        snap = await session.call_tool("browser_snapshot")
        assert not snap.isError
        text = "".join(c.text for c in (snap.content or []) if hasattr(c, "text"))
        assert "Branch Writer" in text


@pytest.mark.asyncio
async def test_sidebar_has_llm_settings() -> None:
    async with _playwright_session() as session:
        await session.call_tool("browser_navigate", {"url": STREAMLIT_URL})

        snap = await session.call_tool("browser_snapshot")
        assert not snap.isError
        text = "".join(c.text for c in (snap.content or []) if hasattr(c, "text"))
        assert "API Base URL" in text
        assert "Model" in text
        assert "Temperature" in text


@pytest.mark.asyncio
async def test_sidebar_has_refresh_button() -> None:
    async with _playwright_session() as session:
        await session.call_tool("browser_navigate", {"url": STREAMLIT_URL})

        snap = await session.call_tool("browser_snapshot")
        assert not snap.isError
        text = "".join(c.text for c in (snap.content or []) if hasattr(c, "text"))
        assert "モデル一覧" in text


@pytest.mark.asyncio
async def test_chat_input_present() -> None:
    async with _playwright_session() as session:
        await session.call_tool("browser_navigate", {"url": STREAMLIT_URL})

        snap = await session.call_tool("browser_snapshot")
        assert not snap.isError
        text = "".join(c.text for c in (snap.content or []) if hasattr(c, "text"))
        assert "メッセージを入力" in text


@pytest.mark.asyncio
async def test_screenshot() -> None:
    async with _playwright_session() as session:
        await session.call_tool("browser_navigate", {"url": STREAMLIT_URL})

        snap = await session.call_tool("browser_take_screenshot")
        assert not snap.isError
        text = "".join(c.text for c in (snap.content or []) if hasattr(c, "text"))
        assert text, "Screenshot returned empty data"
