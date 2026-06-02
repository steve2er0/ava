from __future__ import annotations

import json
from pathlib import Path

from plugins.ava import register
from plugins.ava.tools import (
    handle_compute_modal_frf,
    handle_run_shock_delta,
    handle_summarize_bdf,
)


class FakePluginContext:
    def __init__(self) -> None:
        self.tools: list[dict] = []

    def register_tool(self, **kwargs) -> None:
        self.tools.append(kwargs)


def _write_basic_bdf(path: Path) -> Path:
    path.write_text(
        "\n".join(
            [
                "CEND",
                "BEGIN BULK",
                "GRID,1,,0.0,0.0,0.0",
                "GRID,2,,1.0,0.0,0.0",
                "GRID,3,,1.0,1.0,0.0",
                "CQUAD4,10,1,1,2,3,1",
                "CONM2,20,2,,1.0",
                "ENDDATA",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def test_ava_plugin_registers_expected_tools() -> None:
    ctx = FakePluginContext()

    register(ctx)

    assert {tool["name"] for tool in ctx.tools} == {
        "ava_compute_modal_frf",
        "ava_compute_srs",
        "ava_summarize_bdf",
        "ava_inspect_op2",
        "ava_build_modal_deck",
        "ava_run_shock_delta",
    }
    assert {tool["toolset"] for tool in ctx.tools} == {"ava"}


def test_compute_modal_frf_handler_returns_response_points() -> None:
    payload = json.loads(
        handle_compute_modal_frf(
            {
                "modes": [
                    {
                        "natural_frequency_hz": 100.0,
                        "damping_ratio": 0.02,
                        "modal_constant": 1.0,
                    }
                ],
                "frequencies_hz": [10.0, 100.0, 200.0],
                "response_type": "acceleration",
            }
        )
    )

    assert payload["response_type"] == "acceleration"
    assert [point["frequency_hz"] for point in payload["points"]] == [10.0, 100.0, 200.0]
    assert all(point["magnitude"] >= 0.0 for point in payload["points"])


def test_summarize_bdf_handler_reports_model_metadata(tmp_path: Path) -> None:
    bdf_path = _write_basic_bdf(tmp_path / "model.bdf")

    payload = json.loads(handle_summarize_bdf({"bdf_path": str(bdf_path)}))

    assert payload["grid_count"] == 3
    assert payload["element_counts"]["CQUAD4"] == 1
    assert payload["mass_element_count"] == 1
    assert payload["bounding_box"]["span"] == [1.0, 1.0, 0.0]


def test_run_shock_delta_handler_writes_review_artifacts(tmp_path: Path) -> None:
    bdf_path = _write_basic_bdf(tmp_path / "shock_model.bdf")
    output_dir = tmp_path / "shock_delta_run"

    payload = json.loads(
        handle_run_shock_delta(
            {
                "case_name": "short local acceleration",
                "bdf_path": str(bdf_path),
                "output_directory": str(output_dir),
                "response_metric": "local_acceleration",
                "event_duration_seconds": 0.001,
                "first_mode_hz": 100.0,
                "cumulative_effective_mass_percent": 75.0,
                "damping_basis_documented": True,
                "convergence_delta_percent": 5.0,
                "modal_terms": [
                    {
                        "natural_frequency_hz": 100.0,
                        "damping_ratio": 0.03,
                        "modal_constant": 1.0,
                    }
                ],
                "frf_frequencies_hz": [25.0, 100.0, 250.0],
                "frf_response_type": "acceleration",
            }
        )
    )

    summary = payload["summary"]
    assert summary["rule_outcome"]["primary_rule_id"] == "SHOCK-HF-001"
    assert summary["rule_outcome"]["primary_decision"] == "retain_high_frequency_modes"
    assert summary["rule_outcome"]["release_blocked"] is False
    assert Path(payload["summary_path"]).exists()
    assert Path(payload["response_table_path"]).exists()
    assert Path(payload["figure_path"]).exists()
