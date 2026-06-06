from __future__ import annotations

import os
from unittest.mock import patch

import yaml

from hermes_cli.config import load_config
from hermes_cli.tool_config import (
    format_tool_config_list,
    handle_tool_config_text,
)


def _make_executable(tmp_path, name="EXCEL.EXE"):
    exe = tmp_path / name
    exe.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    exe.chmod(0o755)
    return exe


def test_handle_tool_config_set_persists_path_with_spaces(tmp_path):
    home = tmp_path / "home"
    tool_dir = tmp_path / "Program Files" / "Office"
    tool_dir.mkdir(parents=True)
    exe = _make_executable(tool_dir, "EXCEL.EXE")

    with patch.dict(os.environ, {"HERMES_HOME": str(home)}):
        response = handle_tool_config_text(f"set excel {exe}")

        assert "Configured Excel" in response
        saved = yaml.safe_load((home / "config.yaml").read_text(encoding="utf-8"))
        assert saved["external_tools"]["excel"]["executable_path"] == str(exe)
        assert saved["external_tools"]["excel"]["enabled"] is True


def test_handle_tool_config_list_mentions_no_search_policy(tmp_path):
    with patch.dict(os.environ, {"HERMES_HOME": str(tmp_path)}):
        response = handle_tool_config_text("list")

    assert "will not search the PC" in response
    assert "matlab" in response
    assert "/tool_config set" in response


def test_handle_tool_config_remove_resets_path(tmp_path):
    exe = _make_executable(tmp_path, "chrome.exe")
    with patch.dict(os.environ, {"HERMES_HOME": str(tmp_path / "home")}):
        handle_tool_config_text(f"set chrome {exe}")
        response = handle_tool_config_text("remove chrome")
        config = load_config()

    assert "Removed configuration for Chrome" in response
    assert config["external_tools"]["chrome"]["enabled"] is False
    assert config["external_tools"]["chrome"]["executable_path"] == ""


def test_format_tool_config_list_shows_examples_for_missing_tools():
    response = format_tool_config_list({})

    assert "nastran" in response
    assert "example:" in response

