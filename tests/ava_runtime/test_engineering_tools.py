from __future__ import annotations

import json
import math
import sys
import types
from pathlib import Path

import pytest

from ava_runtime.engineering_tools import list_approved_tools, run_engineering_tool
from ava_runtime.parsers.hdf5_summary import HDF5_SIGNATURE


EXPECTED_TOOLS = {
    "nastran_model_check",
    "nastran_mass_summary",
    "nastran_geometry_summary",
    "op2_modal_summary",
    "modal_frf_compute",
    "sol103_deck_build",
    "sol111_deck_build",
    "nastran_run_job",
    "nastran_f06_scan",
    "pch_parse_summary",
    "psd_welch",
    "psd_maximax",
    "srs_compute",
    "fds_compute",
    "hdf5_channel_summary",
}


def _write_demo_bdf(path: Path) -> Path:
    path.write_text(
        "\n".join(
            [
                "CEND",
                "BEGIN BULK",
                "GRID,1,,0.,0.,0.",
                "GRID,2,,1.,0.,0.",
                "GRID,3,,1.,1.,0.",
                "GRID,4,,0.,1.,0.",
                "GRID,5,,0.,0.,0.",
                "GRID,6,,2.,0.,0.",
                "MAT1,1,1.0E7,,0.3,2.0",
                "MAT1,2,1.0E7,,0.3,3.0",
                "PSHELL,10,1,0.5",
                "PSHELL,11,1,0.25",
                "CQUAD4,100,10,1,2,3,4",
                "CONM2,200,2,,5.0",
                "ENDDATA",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def test_catalog_contains_exact_build_plan_tools():
    names = {item["name"] for item in list_approved_tools()}

    assert names == EXPECTED_TOOLS
    assert len(names) == 15


def test_bdf_geometry_check_and_mass_tools(tmp_path):
    bdf = _write_demo_bdf(tmp_path / "demo.bdf")

    checks = run_engineering_tool(
        "nastran_model_check",
        {"bdf": str(bdf), "out": str(tmp_path / "checks")},
    )
    assert checks["status"] == "ok"
    assert checks["summary"]["duplicate_node_groups"] == 1
    assert checks["summary"]["free_edges"] == 4
    assert checks["summary"]["unused_properties"] == 1
    assert all(Path(path).exists() for path in checks["artifacts"])

    geometry = run_engineering_tool(
        "nastran_geometry_summary",
        {"bdf": str(bdf), "out": str(tmp_path / "geometry")},
    )
    assert geometry["summary"]["nodes"] == 6
    assert geometry["summary"]["elements"] == 1
    assert geometry["summary"]["bounding_box"]["span"] == [2.0, 1.0, 0.0]

    mass = run_engineering_tool(
        "nastran_mass_summary",
        {"bdf": str(bdf), "out": str(tmp_path / "mass")},
    )
    assert math.isclose(mass["summary"]["estimated_structural_mass"], 1.0)
    assert math.isclose(mass["summary"]["concentrated_mass"], 5.0)
    assert math.isclose(mass["summary"]["total_mass"], 6.0)


def test_op2_modal_summary_and_modal_frf_tool(tmp_path):
    modal_csv = tmp_path / "modes.csv"
    modal_csv.write_text(
        "mode,frequency_hz,generalized_mass\n"
        "1,10.0,1.0\n"
        "2,25.0,1.0\n",
        encoding="utf-8",
    )

    modal = run_engineering_tool(
        "op2_modal_summary",
        {"op2": str(modal_csv), "out": str(tmp_path / "modal")},
    )
    assert modal["summary"]["mode_count"] == 2
    assert modal["summary"]["frequency_max_hz"] == 25.0

    frf = run_engineering_tool(
        "modal_frf_compute",
        {
            "modes_path": str(modal_csv),
            "frequencies_hz": [5.0, 10.0, 20.0],
            "damping_ratio": 0.05,
            "modal_constant": 1.0,
            "response_type": "acceleration",
            "out": str(tmp_path / "frf"),
        },
    )
    assert frf["summary"]["response_type"] == "acceleration"
    assert frf["summary"]["point_count"] == 3
    assert frf["summary"]["peak_magnitude"] > 0.0


def test_sol103_sol111_runner_f06_and_pch_tools(tmp_path):
    sol103 = run_engineering_tool(
        "sol103_deck_build",
        {
            "title": "Demo SOL103",
            "spc_id": 1,
            "method_id": 42,
            "mode_count": 12,
            "frequency_upper_hz": 500.0,
            "bulk_data_lines": ["GRID,1,,0.,0.,0."],
            "out": str(tmp_path / "modal_deck"),
        },
    )
    sol103_path = Path(sol103["summary"]["deck_path"])
    assert sol103["summary"]["solution"] == 103
    assert sol103["llm_exposure"] == "no_ingest"
    assert sol103_path.exists()
    sol103_text = sol103_path.read_text(encoding="utf-8")
    assert "SOL 103" in sol103_text
    assert "EIGRL,42,,500.000,12" in sol103_text

    sol111 = run_engineering_tool(
        "sol111_deck_build",
        {
            "title": "Demo SOL111",
            "spc_id": 1,
            "method_id": 42,
            "frequency_set_id": 9,
            "load_set_id": 7,
            "frequencies_hz": [10.0, 20.0, 30.0],
            "bulk_data_lines": ["GRID,1,,0.,0.,0."],
            "out": str(tmp_path / "deck"),
        },
    )
    deck_path = Path(sol111["summary"]["deck_path"])
    assert deck_path.exists()
    assert "SOL 111" in deck_path.read_text(encoding="utf-8")

    job = run_engineering_tool(
        "nastran_run_job",
        {"deck": str(deck_path), "dry_run": True, "out": str(tmp_path / "job")},
    )
    assert job["status"] == "dry_run"
    assert job["summary"]["command"][0] == "nastran"

    f06 = tmp_path / "run.f06"
    f06.write_text(
        "NORMAL LINE\n"
        "USER WARNING MESSAGE 1234\n"
        "USER FATAL MESSAGE 9050\n",
        encoding="utf-8",
    )
    scan = run_engineering_tool(
        "nastran_f06_scan",
        {"f06": str(f06), "out": str(tmp_path / "f06")},
    )
    assert scan["status"] == "failed"
    assert scan["summary"]["severity_counts"]["fatal"] == 1
    assert scan["summary"]["severity_counts"]["warning"] == 1

    pch = tmp_path / "run.pch"
    pch.write_text(
        "$TITLE = DEMO\n"
        "$SUBCASE ID = 1\n"
        "$ACCELERATION\n"
        "1001 10.0 1.0 0.0 2.0 0.0\n"
        "1001 20.0 0.5 0.0 1.0 0.0\n",
        encoding="utf-8",
    )
    parsed = run_engineering_tool(
        "pch_parse_summary",
        {"pch": str(pch), "out": str(tmp_path / "pch")},
    )
    assert parsed["summary"]["record_count"] == 2
    assert parsed["summary"]["response_counts"]["ACCELERATION"] == 2
    assert parsed["summary"]["entity_ids"] == [1001]


def test_psd_srs_and_fds_tools(tmp_path):
    sample_rate = 100.0
    samples = [math.sin(2.0 * math.pi * 12.5 * index / sample_rate) for index in range(64)]

    psd = run_engineering_tool(
        "psd_welch",
        {
            "samples": samples,
            "sample_rate_hz": sample_rate,
            "segment_size": 64,
            "overlap": 0.0,
            "out": str(tmp_path / "psd"),
        },
    )
    assert psd["summary"]["method"] == "welch"
    assert abs(psd["summary"]["peak_frequency_hz"] - 12.5) < 1.6
    assert psd["summary"]["rms"] > 0.0

    maximax = run_engineering_tool(
        "psd_maximax",
        {
            "channels": [samples, [2.0 * value for value in samples]],
            "sample_rate_hz": sample_rate,
            "segment_size": 64,
            "overlap": 0.0,
            "out": str(tmp_path / "maximax"),
        },
    )
    assert maximax["summary"]["method"] == "maximax"
    assert maximax["summary"]["peak_psd"] > psd["summary"]["peak_psd"]

    time_s = [index / sample_rate for index in range(64)]
    impulse = [0.0] * 64
    impulse[3] = 1.0
    srs = run_engineering_tool(
        "srs_compute",
        {
            "time_s": time_s,
            "acceleration_g": impulse,
            "frequencies_hz": [5.0, 10.0, 20.0],
            "out": str(tmp_path / "srs"),
        },
    )
    assert srs["summary"]["point_count"] == 3
    assert srs["summary"]["peak_pseudo_acceleration_g"] >= 0.0

    fds = run_engineering_tool(
        "fds_compute",
        {
            "time_s": time_s,
            "acceleration_g": impulse,
            "frequencies_hz": [5.0, 10.0, 20.0],
            "fatigue_exponent": 4.0,
            "out": str(tmp_path / "fds"),
        },
    )
    assert fds["summary"]["point_count"] == 3
    assert fds["summary"]["peak_damage_index"] >= 0.0


def test_hdf5_channel_summary_with_fake_h5py(tmp_path, monkeypatch):
    hdf5_path = tmp_path / "flight.h5"
    hdf5_path.write_bytes(HDF5_SIGNATURE + b"demo")

    class FakeDataset:
        shape = (4,)
        dtype = "float64"
        attrs = {"units": "g", "sample_rate_hz": 200.0}

        def __getitem__(self, key):
            assert key == ()
            return [0.0, 1.0, -1.0, 2.0]

    class FakeFile:
        def __init__(self, path, mode):
            self.path = path
            self.mode = mode

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def visititems(self, callback):
            callback("flight/ch1", FakeDataset())

    fake_h5py = types.SimpleNamespace(File=FakeFile)
    monkeypatch.setitem(sys.modules, "h5py", fake_h5py)

    summary = run_engineering_tool(
        "hdf5_channel_summary",
        {"hdf5": str(hdf5_path), "out": str(tmp_path / "hdf5")},
    )
    assert summary["status"] == "ok"
    assert summary["summary"]["channel_count"] == 1

    payload = json.loads(Path(summary["artifacts"][0]).read_text(encoding="utf-8"))
    assert payload["channels"][0]["path"] == "/flight/ch1"
    assert payload["channels"][0]["units"] == "g"
    assert math.isclose(payload["channels"][0]["rms"], math.sqrt(1.5))


def test_hdf5_channel_summary_with_installed_h5py(tmp_path):
    h5py = pytest.importorskip("h5py")

    hdf5_path = tmp_path / "real_flight.h5"
    with h5py.File(hdf5_path, "w") as handle:
        dataset = handle.create_dataset("flight/ch1", data=[0.0, 1.0, -1.0, 2.0])
        dataset.attrs["units"] = "g"
        dataset.attrs["sample_rate_hz"] = 200.0

    summary = run_engineering_tool(
        "hdf5_channel_summary",
        {"hdf5": str(hdf5_path), "out": str(tmp_path / "real_hdf5")},
    )
    assert summary["status"] == "ok"
    assert summary["summary"]["channel_count"] == 1

    payload = json.loads(Path(summary["artifacts"][0]).read_text(encoding="utf-8"))
    channel = payload["channels"][0]
    assert channel["path"] == "/flight/ch1"
    assert channel["shape"] == [4]
    assert channel["dtype"].startswith("float")
    assert channel["units"] == "g"
    assert channel["sample_rate_hz"] == 200.0
    assert math.isclose(channel["rms"], math.sqrt(1.5))
