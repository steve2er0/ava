from __future__ import annotations

from unittest.mock import patch

import pytest

from tools.external_tool_config import (
    ExternalToolConfigError,
    build_external_tool_command,
    missing_tool_message,
    remove_tool_path,
    resolve_external_tool,
    set_tool_path,
    validate_executable_path,
)


def _make_executable(tmp_path, name="tool.exe"):
    exe = tmp_path / name
    exe.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    exe.chmod(0o755)
    return exe


def test_set_and_resolve_configured_tool_path(tmp_path):
    exe = _make_executable(tmp_path, "EXCEL.EXE")
    config = {}

    key = set_tool_path(config, "excel", str(exe))
    resolved = resolve_external_tool("excel", config=config)

    assert key == "excel"
    assert resolved.executable_path == str(exe)
    assert resolved.display_name == "Excel"
    assert config["external_tools"]["excel"]["enabled"] is True


def test_rejects_relative_path():
    config = {}

    with pytest.raises(ExternalToolConfigError) as exc:
        set_tool_path(config, "matlab", "matlab.exe")

    assert "Path must be absolute" in str(exc.value)


def test_windows_path_must_look_executable():
    result = validate_executable_path(
        r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.txt",
        require_exists=False,
    )

    assert result.ok is False
    assert "Windows tool paths must end" in result.errors[0]


def test_resolver_never_scans_or_uses_path_lookup(tmp_path):
    exe = _make_executable(tmp_path, "matlab.exe")
    config = {}
    set_tool_path(config, "matlab", str(exe))

    with patch("os.walk", side_effect=AssertionError("must not scan")), patch(
        "shutil.which", side_effect=AssertionError("must not use PATH")
    ):
        resolved = resolve_external_tool("matlab", config=config)

    assert resolved.executable_path == str(exe)


def test_missing_tool_message_tells_user_to_configure_path():
    message = missing_tool_message("chrome")

    assert "will not search the PC" in message
    assert "/pc-tool-config set chrome" in message


def test_remove_resets_tool_entry(tmp_path):
    exe = _make_executable(tmp_path, "chrome.exe")
    config = {}
    set_tool_path(config, "chrome", str(exe))

    remove_tool_path(config, "chrome")

    entry = config["external_tools"]["chrome"]
    assert entry["enabled"] is False
    assert entry["executable_path"] == ""


def test_build_command_quotes_configured_path(tmp_path):
    tool_dir = tmp_path / "Program Files" / "MATLAB"
    tool_dir.mkdir(parents=True)
    exe = _make_executable(tool_dir, "matlab.exe")
    config = {}
    set_tool_path(config, "matlab", str(exe))

    command = build_external_tool_command("matlab", ["-batch", "disp(1)"], config=config)

    assert str(exe) in command
    assert "-batch" in command
