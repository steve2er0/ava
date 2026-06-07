from __future__ import annotations

from plugins.ava import register


class FakePluginContext:
    def __init__(self) -> None:
        self.tools: list[dict] = []

    def register_tool(self, **kwargs) -> None:
        self.tools.append(kwargs)


def test_ava_plugin_registers_no_legacy_tools() -> None:
    ctx = FakePluginContext()

    register(ctx)

    assert ctx.tools == []
