from __future__ import annotations

import json
import math
import sys
import types
from pathlib import Path

import pytest

from ava_runtime.engineering_tools import list_approved_tools, run_engineering_tool
from ava_runtime.parsers.hdf5_summary import HDF5_SIGNATURE
from ava_runtime.visualization.fem_viewer import shutdown_viewer_servers


EXPECTED_TOOLS = {
    "nastran_model_check",
    "nastran_mass_summary",
    "nastran_geometry_summary",
    "op2_modal_summary",
    "bdf_3d_viewer_build",
    "op2_mode_shape_viewer_build",
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


@pytest.fixture(autouse=True)
def _stop_fem_viewer_servers():
    yield
    shutdown_viewer_servers()


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
                "PBAR,20,2,0.1",
                "CQUAD4,100,10,1,2,3,4",
                "CBAR,101,20,2,6,0.,0.,1.",
                "CONM2,200,2,,5.0",
                "ENDDATA",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _write_mode_shape_export(path: Path, *, extra_node: bool = False) -> Path:
    node_ids = [1, 2, 3, 4]
    translations = [
        [0.0, 0.0, 0.0],
        [0.1, 0.0, 0.0],
        [0.1, 0.1, 0.0],
        [0.0, 0.1, 0.0],
    ]
    if extra_node:
        node_ids.append(999)
        translations.append([0.0, 0.0, 0.2])
    path.write_text(
        json.dumps(
            {
                "modes": [
                    {
                        "mode_id": "s1_m1",
                        "case_key": "1",
                        "mode_number": 1,
                        "frequency_hz": 12.5,
                        "node_ids": node_ids,
                        "translations": translations,
                    },
                    {
                        "mode_id": "s1_m2",
                        "case_key": "1",
                        "mode_number": 2,
                        "frequency_hz": 28.0,
                        "node_ids": node_ids,
                        "translations": [[0.0, value[1], value[0]] for value in translations],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    return path


def test_catalog_contains_exact_build_plan_tools():
    names = {item["name"] for item in list_approved_tools()}

    assert names == EXPECTED_TOOLS
    assert len(names) == 17


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
    assert geometry["summary"]["elements"] == 2
    assert geometry["summary"]["bounding_box"]["span"] == [2.0, 1.0, 0.0]

    mass = run_engineering_tool(
        "nastran_mass_summary",
        {"bdf": str(bdf), "out": str(tmp_path / "mass")},
    )
    assert math.isclose(mass["summary"]["estimated_structural_mass"], 1.3)
    assert math.isclose(mass["summary"]["concentrated_mass"], 5.0)
    assert math.isclose(mass["summary"]["total_mass"], 6.3)


def test_bdf_and_op2_html_viewer_tools(tmp_path):
    bdf = _write_demo_bdf(tmp_path / "demo.bdf")

    bdf_viewer = run_engineering_tool(
        "bdf_3d_viewer_build",
        {
            "bdf": str(bdf),
            "out": str(tmp_path / "bdf_viewer"),
            "title": "Demo BDF",
            "viewer_backend": "static",
            "allow_static_viewer": True,
        },
    )
    assert bdf_viewer["status"] == "ok"
    assert bdf_viewer["llm_exposure"] == "summary_only"
    assert bdf_viewer["summary"]["viewer_url"].startswith("http://127.0.0.1:")
    assert bdf_viewer["summary"]["node_count"] == 6
    assert bdf_viewer["summary"]["element_count"] == 2
    assert all(Path(path).exists() for path in bdf_viewer["artifacts"])
    assert "GRID,1" not in json.dumps(bdf_viewer["summary"])

    geometry_payload = json.loads(Path(bdf_viewer["summary"]["geometry_json"]).read_text(encoding="utf-8"))
    assert geometry_payload["schema"] == "ava_fem_geometry_v1"
    assert geometry_payload["stats"]["duplicate_node_group_count"] == 1
    assert geometry_payload["stats"]["free_edge_count"] == 4
    assert geometry_payload["stats"]["line_element_count"] == 1
    assert geometry_payload["stats"]["mass_element_count"] == 1
    assert geometry_payload["elements"][0]["node_ids"] == [1, 2, 3, 4]
    assert {element["type"] for element in geometry_payload["elements"]} == {"CQUAD4", "CBAR"}
    assert {property_card["id"] for property_card in geometry_payload["properties"]} >= {10, 20}
    assert {material["id"] for material in geometry_payload["materials"]} >= {1, 2}
    assert geometry_payload["mass_elements"][0]["type"] == "CONM2"
    viewer_config = json.loads(Path(bdf_viewer["summary"]["viewer_config"]).read_text(encoding="utf-8"))
    assert viewer_config["geometry_url"] == "data/geometry.json"
    viewer_html = Path(bdf_viewer["summary"]["index_html"]).read_text(encoding="utf-8")
    viewer_dir = Path(bdf_viewer["summary"]["index_html"]).parent
    viewer_js = (viewer_dir / "fem_viewer.js").read_text(encoding="utf-8")
    assert 'id="model-tree"' in viewer_html
    assert 'id="export-gif"' in viewer_html
    assert '"gifenc": "./assets/gifenc.esm.js"' in viewer_html
    assert (viewer_dir / "assets" / "gifenc.esm.js").exists()
    assert (viewer_dir / "assets" / "GIFENC_LICENSE.md").exists()
    assert 'data-tree-expand="${escapeAttr(section)}"' in viewer_js
    assert 'data-tree-section="${escapeAttr(section)}"' in viewer_js
    assert 'data-tree-select="render-style"' in viewer_js
    assert 'data-tree-select="color-mode"' in viewer_js
    assert 'data-tree-toggle="${key}"' in viewer_js
    assert 'data-tree-command="fit-model"' in viewer_js
    assert "showMassElements" in viewer_js
    assert "exportModeGif" in viewer_js

    modal_export = _write_mode_shape_export(tmp_path / "modes.json")
    op2_viewer = run_engineering_tool(
        "op2_mode_shape_viewer_build",
        {
            "bdf": str(bdf),
            "op2": str(modal_export),
            "out": str(tmp_path / "op2_viewer"),
            "title": "Demo Modes",
            "viewer_backend": "static",
            "allow_static_viewer": True,
        },
    )
    assert op2_viewer["status"] == "ok"
    assert op2_viewer["summary"]["viewer_url"].startswith("http://127.0.0.1:")
    assert op2_viewer["summary"]["mode_count"] == 2
    assert op2_viewer["summary"]["frequency_min_hz"] == 12.5
    assert op2_viewer["summary"]["frequency_max_hz"] == 28.0
    assert "translations" not in json.dumps(op2_viewer["summary"])

    manifest_path = Path(op2_viewer["summary"]["op2_manifest_json"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema"] == "ava_fem_modes_v1"
    assert manifest["modes"][0]["shape_url"] == "s1_m1.json"
    assert (manifest_path.parent / "s1_m1.json").exists()
    assert all(Path(path).exists() for path in op2_viewer["artifacts"])
    modal_config = json.loads(Path(op2_viewer["summary"]["viewer_config"]).read_text(encoding="utf-8"))
    assert modal_config["modes_url"] == "data/modes/manifest.json"
    assert modal_config["initial_mode_id"] == "s1_m1"
    assert modal_config["auto_animate"] is True

    discovered_modal_export = _write_mode_shape_export(tmp_path / "demo.json")
    discovered = run_engineering_tool(
        "op2_mode_shape_viewer_build",
        {
            "bdf": str(bdf),
            "out": str(tmp_path / "discovered_op2_viewer"),
            "mode_number": 1,
            "viewer_backend": "static",
            "allow_static_viewer": True,
        },
    )
    assert discovered["status"] == "ok"
    assert discovered["summary"]["op2_parser"] == "op2_json_export"
    assert discovered["summary"]["mode_count"] == 2
    discovered_config = json.loads(Path(discovered["summary"]["viewer_config"]).read_text(encoding="utf-8"))
    assert discovered_config["initial_mode_id"] == "s1_m1"
    assert discovered_config["auto_animate"] is True
    assert Path(discovered_modal_export).exists()

    bdf_geometry_only = run_engineering_tool(
        "bdf_3d_viewer_build",
        {
            "bdf": str(bdf),
            "out": str(tmp_path / "bdf_modal_viewer"),
            "first_mode": True,
            "viewer_backend": "static",
            "allow_static_viewer": True,
        },
    )
    assert bdf_geometry_only["status"] == "ok"
    assert "mode_count" not in bdf_geometry_only["summary"]
    bdf_geometry_config = json.loads(Path(bdf_geometry_only["summary"]["viewer_config"]).read_text(encoding="utf-8"))
    assert bdf_geometry_config["modes_url"] is None

    mismatched_export = _write_mode_shape_export(tmp_path / "mismatched_modes.json", extra_node=True)
    mismatched = run_engineering_tool(
        "op2_mode_shape_viewer_build",
        {
            "bdf": str(bdf),
            "op2": str(mismatched_export),
            "out": str(tmp_path / "mismatched_viewer"),
            "viewer_backend": "static",
            "allow_static_viewer": True,
        },
    )
    mismatched_manifest = json.loads(Path(mismatched["summary"]["op2_manifest_json"]).read_text(encoding="utf-8"))
    assert mismatched_manifest["modes"][0]["node_count"] == 5


def test_op2_viewer_defaults_to_fem_explorer_launcher(tmp_path, monkeypatch):
    import ava_runtime.engineering_tools as engineering_tools

    bdf = _write_demo_bdf(tmp_path / "demo.bdf")
    op2 = tmp_path / "demo.op2"
    op2.write_bytes(b"op2")
    captured = {}

    def fake_launch_fem_explorer_viewer(bdf_arg, output_dir, **kwargs):
        captured["bdf"] = bdf_arg
        captured["output_dir"] = output_dir
        captured.update(kwargs)
        manifest = Path(output_dir) / "fem_explorer_launch.json"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text("{}", encoding="utf-8")
        return {
            "summary": {
                "viewer_backend": "fem_explorer",
                "frontend_url": "http://127.0.0.1:5173",
                "launch_manifest": str(manifest),
                "initial_mode": kwargs.get("initial_mode"),
                "auto_animate": kwargs.get("auto_animate"),
            },
            "artifacts": (str(manifest),),
        }

    monkeypatch.setattr(engineering_tools, "launch_fem_explorer_viewer", fake_launch_fem_explorer_viewer)

    result = run_engineering_tool(
        "op2_mode_shape_viewer_build",
        {
            "bdf": str(bdf),
            "op2": str(op2),
            "out": str(tmp_path / "fem_explorer"),
            "first_mode": True,
        },
    )

    assert result["status"] == "ok"
    assert result["summary"]["viewer_backend"] == "fem_explorer"
    assert result["summary"]["viewer_url"] == "http://127.0.0.1:5173"
    assert captured["bdf"] == str(bdf)
    assert captured["op2"] == op2
    assert captured["initial_mode"] == 1
    assert captured["auto_animate"] is True


def test_mode_result_discovery_is_case_insensitive_for_modal_fem_example(tmp_path, monkeypatch):
    import ava_runtime.engineering_tools as engineering_tools

    bdf = _write_demo_bdf(tmp_path / "modalFEM_SIunits_011317.bdf")
    op2 = tmp_path / "modalfem_siunits_011317-001.op2"
    op2.write_bytes(b"op2")
    captured = {}

    def fake_launch_fem_explorer_viewer(bdf_arg, output_dir, **kwargs):
        captured["bdf"] = bdf_arg
        captured["output_dir"] = output_dir
        captured.update(kwargs)
        manifest = Path(output_dir) / "fem_explorer_launch.json"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text("{}", encoding="utf-8")
        return {
            "summary": {
                "viewer_backend": "fem_explorer",
                "frontend_url": "http://127.0.0.1:5173",
                "launch_manifest": str(manifest),
            },
            "artifacts": (str(manifest),),
        }

    monkeypatch.setattr(engineering_tools, "launch_fem_explorer_viewer", fake_launch_fem_explorer_viewer)

    result = run_engineering_tool(
        "op2_mode_shape_viewer_build",
        {
            "bdf": str(bdf),
            "out": str(tmp_path / "fem_explorer"),
            "first_mode": True,
        },
    )

    assert result["status"] == "ok"
    assert captured["op2"] == op2
    assert captured["initial_mode"] == 1
    assert captured["auto_animate"] is True


def test_plain_bdf_visualization_does_not_auto_load_discovered_op2(tmp_path, monkeypatch):
    import ava_runtime.engineering_tools as engineering_tools

    bdf = _write_demo_bdf(tmp_path / "modalFEM_SIunits_011317.bdf")
    (tmp_path / "modalfem_siunits_011317-001.op2").write_bytes(b"op2")
    captured = {}

    def fake_launch_fem_explorer_viewer(bdf_arg, output_dir, **kwargs):
        captured["bdf"] = bdf_arg
        captured["output_dir"] = output_dir
        captured.update(kwargs)
        manifest = Path(output_dir) / "fem_explorer_launch.json"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text("{}", encoding="utf-8")
        return {
            "summary": {
                "viewer_backend": "fem_explorer",
                "frontend_url": "http://127.0.0.1:5173",
                "launch_manifest": str(manifest),
            },
            "artifacts": (str(manifest),),
        }

    monkeypatch.setattr(engineering_tools, "launch_fem_explorer_viewer", fake_launch_fem_explorer_viewer)

    result = run_engineering_tool(
        "bdf_3d_viewer_build",
        {
            "bdf": str(bdf),
            "out": str(tmp_path / "fem_explorer"),
        },
    )

    assert result["status"] == "ok"
    assert captured["bdf"] == str(bdf)
    assert captured["op2"] is None
    assert captured["initial_mode"] is None
    assert captured["auto_animate"] is False


def test_plain_bdf_visualization_ignores_accidental_static_backend(tmp_path, monkeypatch):
    import ava_runtime.engineering_tools as engineering_tools

    bdf = _write_demo_bdf(tmp_path / "modalFEM_SIunits_011317.bdf")
    captured = {}

    def fake_launch_fem_explorer_viewer(bdf_arg, output_dir, **kwargs):
        captured["bdf"] = bdf_arg
        captured["output_dir"] = output_dir
        captured.update(kwargs)
        manifest = Path(output_dir) / "fem_explorer_launch.json"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text("{}", encoding="utf-8")
        return {
            "summary": {
                "viewer_backend": "fem_explorer",
                "frontend_url": "http://127.0.0.1:5173",
                "launch_manifest": str(manifest),
            },
            "artifacts": (str(manifest),),
        }

    monkeypatch.setattr(engineering_tools, "launch_fem_explorer_viewer", fake_launch_fem_explorer_viewer)

    result = run_engineering_tool(
        "bdf_3d_viewer_build",
        {
            "bdf": str(bdf),
            "out": str(tmp_path / "fem_explorer"),
            "viewer_backend": "static",
        },
    )

    assert result["status"] == "ok"
    assert result["summary"]["viewer_backend"] == "fem_explorer"
    assert result["summary"]["viewer_url"] == "http://127.0.0.1:5173"
    assert captured["bdf"] == str(bdf)
    assert captured["op2"] is None


def test_op2_viewer_without_mode_intent_downgrades_to_plain_bdf(tmp_path, monkeypatch):
    import ava_runtime.engineering_tools as engineering_tools

    bdf = _write_demo_bdf(tmp_path / "modalFEM_SIunits_011317.bdf")
    (tmp_path / "modalfem_siunits_011317-001.op2").write_bytes(b"op2")
    captured = {}

    def fake_launch_fem_explorer_viewer(bdf_arg, output_dir, **kwargs):
        captured["bdf"] = bdf_arg
        captured["output_dir"] = output_dir
        captured.update(kwargs)
        manifest = Path(output_dir) / "fem_explorer_launch.json"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text("{}", encoding="utf-8")
        return {
            "summary": {
                "viewer_backend": "fem_explorer",
                "frontend_url": "http://127.0.0.1:5173",
                "launch_manifest": str(manifest),
            },
            "artifacts": (str(manifest),),
        }

    monkeypatch.setattr(engineering_tools, "launch_fem_explorer_viewer", fake_launch_fem_explorer_viewer)

    result = run_engineering_tool(
        "op2_mode_shape_viewer_build",
        {
            "bdf": str(bdf),
            "out": str(tmp_path / "fem_explorer"),
        },
    )

    assert result["status"] == "ok"
    assert result["summary"]["viewer_backend"] == "fem_explorer"
    assert captured["bdf"] == str(bdf)
    assert captured["op2"] is None
    assert captured["initial_mode"] is None
    assert captured["auto_animate"] is False


def test_fem_viewer_tools_fail_for_missing_inputs(tmp_path):
    missing_bdf = tmp_path / "missing.bdf"
    with pytest.raises(FileNotFoundError):
        run_engineering_tool(
            "bdf_3d_viewer_build",
            {"bdf": str(missing_bdf), "out": str(tmp_path / "missing_bdf_viewer")},
        )

    bdf = _write_demo_bdf(tmp_path / "demo.bdf")
    with pytest.raises(FileNotFoundError):
        run_engineering_tool(
            "op2_mode_shape_viewer_build",
            {
                "bdf": str(bdf),
                "op2": str(tmp_path / "missing.op2"),
                "out": str(tmp_path / "missing_op2_viewer"),
            },
        )


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
