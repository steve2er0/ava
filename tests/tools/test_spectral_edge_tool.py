from __future__ import annotations

import json
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
h5py = pytest.importorskip("h5py")

from tools import spectral_edge_tool


def _write_hdf5(path: Path) -> Path:
    with h5py.File(path, "w") as handle:
        flight = handle.create_group("AR02")
        metadata = flight.create_group("metadata")
        metadata.attrs["flight_id"] = "AR02"
        channels = flight.create_group("channels")

        accel = channels.create_group("Accel_X")
        sample_rate = 100.0
        time = np.arange(1000, dtype=float) / sample_rate
        accel.create_dataset("time", data=time)
        accel.create_dataset("data", data=np.sin(2.0 * np.pi * 5.0 * time))
        accel.attrs["sample_rate"] = sample_rate
        accel.attrs["units"] = "g"
        accel.attrs["description"] = "Accelerometer X"

        temp = channels.create_group("Temperature")
        temp.create_dataset("time", data=time)
        temp.create_dataset("data", data=np.linspace(20.0, 21.0, len(time)))
        temp.attrs["sample_rate"] = sample_rate
        temp.attrs["units"] = "degC"
    return path


def test_spectral_edge_find_data_finds_label_under_root(tmp_path):
    hdf5_path = _write_hdf5(tmp_path / "AR02.h5")

    payload = json.loads(
        spectral_edge_tool.spectral_edge_find_data_handler(
            {"label": "AR02", "data_roots": [str(tmp_path)]}
        )
    )

    assert payload["status"] == "ok"
    assert payload["summary"]["match_count"] == 1
    assert payload["summary"]["matches"][0]["path"] == str(hdf5_path.resolve())
    assert payload["summary"]["matches"][0]["extension"] == ".h5"


def test_spectral_edge_list_channels_marks_accelerometers(tmp_path):
    hdf5_path = _write_hdf5(tmp_path / "AR02.h5")

    payload = json.loads(
        spectral_edge_tool.spectral_edge_list_channels_handler(
            {"file_path": str(hdf5_path), "accelerometer_only": True}
        )
    )

    assert payload["status"] == "ok"
    assert payload["summary"]["flight_count"] == 1
    assert payload["summary"]["total_channel_count"] == 2
    assert payload["summary"]["matched_channel_count"] == 1
    channel = payload["summary"]["channels"][0]
    assert channel["flight_key"] == "AR02"
    assert channel["channel_key"] == "Accel_X"
    assert channel["is_accelerometer"] is True


def test_spectral_edge_open_spectrogram_writes_manifest_and_launches(monkeypatch, tmp_path):
    hdf5_path = _write_hdf5(tmp_path / "AR02.h5")
    root = tmp_path / "spectral-edge"
    (root / "spectral_edge").mkdir(parents=True)
    (root / "spectral_edge" / "main.py").write_text("", encoding="utf-8")
    (root / "venv" / "bin").mkdir(parents=True)
    python_path = root / "venv" / "bin" / "python"
    python_path.write_text("", encoding="utf-8")
    captured = {}

    class FakeProcess:
        pid = 4242

    def fake_popen(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return FakeProcess()

    monkeypatch.setattr(spectral_edge_tool.subprocess, "Popen", fake_popen)

    payload = json.loads(
        spectral_edge_tool.spectral_edge_open_spectrogram_handler(
            {
                "file_path": str(hdf5_path),
                "flight_key": "AR02",
                "channel_key": "Accel_X",
                "spectral_edge_root": str(root),
                "settings": {"time_start_seconds": 1.0, "fft_size": 256},
                "generate": True,
            }
        )
    )

    assert payload["status"] == "ok"
    summary = payload["summary"]
    manifest_path = Path(summary["manifest_path"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["tool"] == "segmented_spectrogram"
    assert manifest["file_path"] == str(hdf5_path.resolve())
    assert manifest["flight_key"] == "AR02"
    assert manifest["channel_key"] == "Accel_X"
    assert manifest["settings"]["time_start_seconds"] == 1.0
    assert manifest["settings"]["fft_size"] == 256
    assert manifest["generate"] is True
    assert captured["command"] == [
        str(python_path),
        "-m",
        "spectral_edge.main",
        "--launch-manifest",
        str(manifest_path),
    ]
    assert captured["kwargs"]["cwd"] == str(root.resolve())
    assert captured["kwargs"]["start_new_session"] is True
    assert payload["summary"]["process_id"] == 4242
    assert "already been launched" in payload["agent_guidance"]


def test_spectral_edge_toolset_resolves():
    from toolsets import resolve_toolset, validate_toolset

    assert validate_toolset("spectral_edge") is True
    resolved = resolve_toolset("spectral_edge")
    assert "spectral_edge_find_data" in resolved
    assert "spectral_edge_list_channels" in resolved
    assert "spectral_edge_open_spectrogram" in resolved
