from __future__ import annotations

import json
from pathlib import Path

from tools import fem_explorer_tool


def _write_bdf(path: Path) -> Path:
    path.write_text("CEND\nBEGIN BULK\nENDDATA\n", encoding="utf-8")
    return path


def test_fem_explorer_open_resolves_model_name_located_here(monkeypatch, tmp_path):
    bdf = _write_bdf(tmp_path / "modalFEM_SIunits_011317.bdf")
    captured = {}

    def fake_launch_fem_explorer_viewer(bdf_arg, output_dir, **kwargs):
        captured["bdf"] = bdf_arg
        captured["output_dir"] = output_dir
        captured.update(kwargs)
        return {
            "summary": {
                "viewer_backend": "fem_explorer",
                "window": "launched",
                "launch_mode": "production",
                "frontend_url": "http://127.0.0.1:62000",
                "bdf_path": str(bdf),
                "op2_path": None,
                "auto_animate": False,
            },
            "artifacts": [str(tmp_path / "viewer" / "fem_explorer_launch.json")],
        }

    monkeypatch.setattr(fem_explorer_tool, "launch_fem_explorer_viewer", fake_launch_fem_explorer_viewer)

    payload = json.loads(
        fem_explorer_tool.fem_explorer_open_handler(
            {
                "model_name": "modalFEM_SIunits_011317",
                "directory": str(tmp_path),
            }
        )
    )

    assert payload["status"] == "ok"
    assert payload["tool"] == "fem_explorer_open"
    assert captured["bdf"] == bdf.resolve()
    assert captured["op2"] is None
    assert captured["initial_mode"] is None
    assert captured["auto_animate"] is False
    assert Path(captured["output_dir"]) == bdf.parent / "_ava_viewers" / "modalFEM_SIunits_011317_geometry"
    assert payload["summary"]["viewer_url"] == "http://127.0.0.1:62000"
    assert "already been launched" in payload["agent_guidance"]


def test_fem_explorer_open_plain_visualization_does_not_discover_op2(monkeypatch, tmp_path):
    bdf = _write_bdf(tmp_path / "model.bdf")
    (tmp_path / "model.op2").write_bytes(b"op2")
    captured = {}

    def fake_launch_fem_explorer_viewer(bdf_arg, output_dir, **kwargs):
        captured.update(kwargs)
        return {
            "summary": {
                "viewer_backend": "fem_explorer",
                "window": "launched",
                "launch_mode": "production",
                "frontend_url": "http://127.0.0.1:62001",
                "bdf_path": str(bdf),
                "op2_path": None,
                "auto_animate": False,
            },
            "artifacts": [],
        }

    monkeypatch.setattr(fem_explorer_tool, "launch_fem_explorer_viewer", fake_launch_fem_explorer_viewer)

    payload = json.loads(fem_explorer_tool.fem_explorer_open_handler({"bdf_path": str(bdf)}))

    assert payload["status"] == "ok"
    assert captured["op2"] is None
    assert captured["initial_mode"] is None


def test_fem_explorer_open_mode_intent_discovers_op2(monkeypatch, tmp_path):
    bdf = _write_bdf(tmp_path / "model.bdf")
    op2 = tmp_path / "model-001.op2"
    op2.write_bytes(b"op2")
    captured = {}

    def fake_launch_fem_explorer_viewer(bdf_arg, output_dir, **kwargs):
        captured["output_dir"] = output_dir
        captured.update(kwargs)
        return {
            "summary": {
                "viewer_backend": "fem_explorer",
                "window": "launched",
                "launch_mode": "production",
                "frontend_url": "http://127.0.0.1:62002",
                "bdf_path": str(bdf),
                "op2_path": str(op2),
                "initial_mode": "first",
                "auto_animate": True,
            },
            "artifacts": [],
        }

    monkeypatch.setattr(fem_explorer_tool, "launch_fem_explorer_viewer", fake_launch_fem_explorer_viewer)

    payload = json.loads(fem_explorer_tool.fem_explorer_open_handler({"bdf": str(bdf), "first_mode": True}))

    assert payload["status"] == "ok"
    assert captured["op2"] == op2.resolve()
    assert captured["initial_mode"] == "first"
    assert captured["auto_animate"] is True
    assert Path(captured["output_dir"]) == bdf.parent / "_ava_viewers" / "model_mode_shape"


def test_fem_explorer_toolset_resolves():
    from toolsets import resolve_toolset, validate_toolset

    assert validate_toolset("fem_explorer") is True
    assert "fem_explorer_open" in resolve_toolset("fem_explorer")
