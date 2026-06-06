from __future__ import annotations

import os
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gateway.config import GatewayConfig, Platform, PlatformConfig
from gateway.platforms.base import MessageEvent
from gateway.session import SessionEntry, SessionSource


def _make_source(user_id: str = "user1") -> SessionSource:
    return SessionSource(
        platform=Platform.DISCORD,
        user_id=user_id,
        chat_id="c1",
        user_name=f"name-{user_id}",
        chat_type="dm",
    )


def _make_event(text: str, source: SessionSource) -> MessageEvent:
    return MessageEvent(text=text, source=source, message_id="m1")


def _make_runner(platform_extra: dict | None = None):
    from gateway.run import GatewayRunner

    runner = object.__new__(GatewayRunner)
    runner.config = GatewayConfig(
        platforms={
            Platform.DISCORD: PlatformConfig(
                enabled=True,
                token="***",
                extra=platform_extra or {},
            )
        }
    )
    adapter = MagicMock()
    adapter.send = AsyncMock()
    runner.adapters = {Platform.DISCORD: adapter}
    runner._voice_mode = {}
    runner.hooks = SimpleNamespace(
        emit=AsyncMock(),
        emit_collect=AsyncMock(return_value=[]),
        loaded_hooks=False,
    )
    runner.session_store = MagicMock()
    runner.session_store.get_or_create_session.return_value = SessionEntry(
        session_key="agent:main:discord:dm:c1",
        session_id="sess-1",
        created_at=datetime.now(),
        updated_at=datetime.now(),
        platform=Platform.DISCORD,
        chat_type="dm",
        total_tokens=0,
    )
    runner.session_store.load_transcript.return_value = []
    runner.session_store.has_any_sessions.return_value = True
    runner.session_store.append_to_transcript = MagicMock()
    runner.session_store.rewrite_transcript = MagicMock()
    runner.session_store.update_session = MagicMock()
    runner._running_agents = {}
    runner._running_agents_ts = {}
    runner._session_run_generation = {}
    runner._pending_messages = {}
    runner._pending_approvals = {}
    runner._session_sources = {}
    runner._session_db = MagicMock()
    runner._session_db.get_session_title.return_value = None
    runner._session_db.get_session.return_value = None
    runner._reasoning_config = None
    runner._provider_routing = {}
    runner._fallback_model = None
    runner._show_reasoning = False
    runner._is_user_authorized = lambda _source: True
    runner._set_session_env = lambda _context: None
    runner._should_send_voice_reply = lambda *_args, **_kwargs: False
    runner._send_voice_reply = AsyncMock()
    runner._capture_gateway_honcho_if_configured = lambda *args, **kwargs: None
    runner._emit_gateway_run_progress = AsyncMock()
    runner._draining = False
    return runner


@pytest.mark.asyncio
async def test_tool_config_dispatch_lists_tools(tmp_path):
    runner = _make_runner()
    with patch.dict(os.environ, {"HERMES_HOME": str(tmp_path)}):
        result = await runner._handle_message(_make_event("/tool_config list", _make_source()))

    assert "Enterprise tool configuration" in result
    assert "will not search the PC" in result


@pytest.mark.asyncio
async def test_tool_config_admin_only_when_slash_policy_enabled(tmp_path):
    runner = _make_runner(
        {
            "allow_admin_from": ["admin"],
            "user_allowed_commands": ["tool_config"],
        }
    )
    with patch.dict(os.environ, {"HERMES_HOME": str(tmp_path)}):
        result = await runner._handle_message(_make_event("/tool_config list", _make_source("user")))

    assert "admin-only" in result

