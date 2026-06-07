from __future__ import annotations

import json
from pathlib import Path

from tools import engineering_tool


def test_engineering_tool_run_accepts_bdf_path_alias(monkeypatch, tmp_path):
    bdf = tmp_path / "model.bdf"
    bdf.write_text("CEND\nBEGIN BULK\nENDDATA\n", encoding="utf-8")
    captured = {}

    def fake_run_engineering_tool(tool_name, params):
        captured["tool_name"] = tool_name
        captured["params"] = params
        return {"tool": tool_name, "status": "ok", "summary": {}, "artifacts": []}

    monkeypatch.setattr(engineering_tool, "run_engineering_tool", fake_run_engineering_tool)

    payload = json.loads(
        engineering_tool.engineering_tool_run_handler(
            {
                "tool_name": "bdf_3d_viewer_build",
                "params": {"bdf_path": str(bdf)},
            }
        )
    )

    assert payload["status"] == "ok"
    assert captured["tool_name"] == "bdf_3d_viewer_build"
    assert captured["params"]["bdf"].lower() == str(bdf.resolve()).lower()


def test_engineering_tool_run_resolves_model_name_located_here(monkeypatch, tmp_path):
    bdf = tmp_path / "modalFEM_SIunits_011317.bdf"
    bdf.write_text("CEND\nBEGIN BULK\nENDDATA\n", encoding="utf-8")
    captured = {}

    def fake_run_engineering_tool(tool_name, params):
        captured["tool_name"] = tool_name
        captured["params"] = params
        return {"tool": tool_name, "status": "ok", "summary": {}, "artifacts": []}

    monkeypatch.setattr(engineering_tool, "run_engineering_tool", fake_run_engineering_tool)

    payload = json.loads(
        engineering_tool.engineering_tool_run_handler(
            {
                "tool_name": "bdf_3d_viewer_build",
                "params": {
                    "model_name": "modalFEM_SIunits_011317",
                    "directory": str(tmp_path),
                },
            }
        )
    )

    assert payload["status"] == "ok"
    assert captured["params"]["bdf"].lower() == str(bdf.resolve()).lower()


def test_engineering_tool_run_merges_top_level_path_alias(monkeypatch, tmp_path):
    bdf = tmp_path / "demo.BDF"
    bdf.write_text("CEND\nBEGIN BULK\nENDDATA\n", encoding="utf-8")
    captured = {}

    def fake_run_engineering_tool(tool_name, params):
        captured["tool_name"] = tool_name
        captured["params"] = params
        return {"tool": tool_name, "status": "ok", "summary": {}, "artifacts": []}

    monkeypatch.setattr(engineering_tool, "run_engineering_tool", fake_run_engineering_tool)

    payload = json.loads(
        engineering_tool.engineering_tool_run_handler(
            {
                "tool_name": "bdf_3d_viewer_build",
                "path": str(tmp_path / "demo.bdf"),
            }
        )
    )

    assert payload["status"] == "ok"
    assert captured["params"]["bdf"].lower() == str(bdf.resolve()).lower()


def test_engineering_tool_run_adds_viewer_completion_guidance(monkeypatch, tmp_path):
    bdf = tmp_path / "demo.bdf"
    bdf.write_text("CEND\nBEGIN BULK\nENDDATA\n", encoding="utf-8")

    def fake_run_engineering_tool(tool_name, params):
        return {
            "tool": tool_name,
            "status": "ok",
            "summary": {
                "viewer_backend": "fem_explorer",
                "window": "launched",
                "viewer_url": "http://127.0.0.1:62000",
                "op2_path": None,
            },
            "artifacts": [],
        }

    monkeypatch.setattr(engineering_tool, "run_engineering_tool", fake_run_engineering_tool)

    payload = json.loads(
        engineering_tool.engineering_tool_run_handler(
            {
                "tool_name": "bdf_3d_viewer_build",
                "params": {"bdf": str(bdf)},
            }
        )
    )

    assert payload["status"] == "ok"
    assert "already been launched" in payload["agent_guidance"]
    assert "Do not call terminal" in payload["agent_guidance"]
