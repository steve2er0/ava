from __future__ import annotations

import json
from pathlib import Path

from ava_runtime.visualization.fem_explorer_launcher import launch_fem_explorer_viewer


def test_fem_explorer_launcher_writes_manifest_and_starts_electron(tmp_path, monkeypatch):
    bdf = tmp_path / "model.bdf"
    op2 = tmp_path / "model.op2"
    bdf.write_text("CEND\nBEGIN BULK\nENDDATA\n", encoding="utf-8")
    op2.write_bytes(b"op2")
    root = tmp_path / "fem-explorer"
    (root / "electron").mkdir(parents=True)
    (root / "package.json").write_text("{}", encoding="utf-8")
    (root / "electron" / "main.js").write_text("", encoding="utf-8")
    captured = {}

    class FakeProcess:
        pid = 4321

    def fake_popen(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return FakeProcess()

    monkeypatch.setattr(
        "ava_runtime.visualization.fem_explorer_launcher._free_loopback_ports",
        lambda count: (42001, 42002),
    )
    monkeypatch.setattr(
        "ava_runtime.visualization.fem_explorer_launcher.subprocess.Popen",
        fake_popen,
    )

    result = launch_fem_explorer_viewer(
        bdf,
        tmp_path / "viewer",
        op2=op2,
        initial_mode=1,
        fem_explorer_root=root,
    )

    manifest_path = Path(result["summary"]["launch_manifest"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["bdf_path"] == str(bdf.resolve())
    assert manifest["op2_path"] == str(op2.resolve())
    assert manifest["initial_mode"] == 1
    assert manifest["auto_animate"] is True
    assert result["summary"]["viewer_backend"] == "fem_explorer"
    assert result["summary"]["frontend_url"] == "http://127.0.0.1:42002"
    assert captured["command"][-1] == f"--launch-manifest={manifest_path}"
    assert captured["kwargs"]["cwd"] == str(root.resolve())
    assert captured["kwargs"]["env"]["FEM_EXPLORER_BACKEND_PORT"] == "42001"
    assert captured["kwargs"]["env"]["FEM_EXPLORER_FRONTEND_PORT"] == "42002"
    assert captured["kwargs"]["env"]["FEM_EXPLORER_LAUNCH_MANIFEST"] == str(manifest_path)
    assert captured["kwargs"]["env"]["FEM_EXPLORER_REFERENCE_TOKEN"]
