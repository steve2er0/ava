"""Approved engineering tool catalog and dispatcher for AVA."""

from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from ava_runtime.analysis.fds import compute_fds, fds_result_dict
from ava_runtime.analysis.frf import ModalTerm, compute_modal_frf
from ava_runtime.analysis.psd import calculate_psd_maximax, calculate_psd_welch, psd_result_dict
from ava_runtime.analysis.srs import compute_srs
from ava_runtime.parsers.bdf_parser import geometry_summary, mass_summary, model_diagnostics
from ava_runtime.parsers.hdf5_summary import summarize_hdf5_channels
from ava_runtime.parsers.op2_parser import (
    modal_summary_dict,
    modes_to_modal_terms,
    summarize_op2_modal,
)
from ava_runtime.parsers.pch_parser import pch_summary_dict, parse_pch_records, summarize_pch
from ava_runtime.solvers.deck_builder import build_sol103_deck_from_config, build_sol111_deck_from_config, write_deck
from ava_runtime.solvers.f06_scan import scan_f06
from ava_runtime.solvers.nastran_runner import NastranRunRequest, NastranRunner
from ava_runtime.visualization.fem_explorer_launcher import launch_fem_explorer_viewer
from ava_runtime.visualization.fem_viewer import build_bdf_3d_viewer, build_op2_mode_shape_viewer


@dataclass(frozen=True)
class ApprovedTool:
    """Catalog metadata for one approved AVA engineering tool."""

    name: str
    category: str
    purpose: str
    risk_level: str
    default_llm_exposure: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]


@dataclass(frozen=True)
class ToolRunResult:
    """Standard result envelope returned by all approved engineering tools."""

    tool: str
    status: str
    llm_exposure: str
    summary: Mapping[str, Any]
    artifacts: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "tool": self.tool,
            "status": self.status,
            "llm_exposure": self.llm_exposure,
            "summary": dict(self.summary),
            "artifacts": list(self.artifacts),
        }


APPROVED_TOOLS: dict[str, ApprovedTool] = {
    "nastran_model_check": ApprovedTool(
        name="nastran_model_check",
        category="nastran",
        purpose="Run duplicate-node, free-edge, unused-card, missing-node, and connectivity checks on a BDF.",
        risk_level="read_only",
        default_llm_exposure="summary_only",
        inputs=("bdf",),
        outputs=("model_check_summary.json", "duplicate_nodes.csv", "free_edges.csv"),
    ),
    "nastran_mass_summary": ApprovedTool(
        name="nastran_mass_summary",
        category="nastran",
        purpose="Summarize supported shell, line, and concentrated mass contributions from a BDF.",
        risk_level="read_only",
        default_llm_exposure="summary_only",
        inputs=("bdf",),
        outputs=("mass_summary.json", "mass_by_property.csv", "mass_by_material.csv"),
    ),
    "nastran_geometry_summary": ApprovedTool(
        name="nastran_geometry_summary",
        category="nastran",
        purpose="Summarize BDF nodes, elements, properties, materials, coordinate systems, and bounds.",
        risk_level="read_only",
        default_llm_exposure="summary_only",
        inputs=("bdf",),
        outputs=("geometry_summary.json",),
    ),
    "op2_modal_summary": ApprovedTool(
        name="op2_modal_summary",
        category="nastran",
        purpose="Summarize OP2 modal metadata or a solver-neutral modal CSV/JSON export.",
        risk_level="read_only",
        default_llm_exposure="summary_only",
        inputs=("op2",),
        outputs=("modal_summary.json", "modes.csv"),
    ),
    "bdf_3d_viewer_build": ApprovedTool(
        name="bdf_3d_viewer_build",
        category="visualization",
        purpose=(
            "Open FEM Explorer in a new local desktop window for BDF geometry. "
            "Use this for plain requests to view or visualize a model. "
            "Only load OP2 modes when an OP2/result path is explicitly supplied; "
            "otherwise let the user import modes from FEM Explorer. "
            "Use viewer_backend='static' for the lightweight static HTML fallback."
        ),
        risk_level="read_only",
        default_llm_exposure="summary_only",
        inputs=("bdf", "op2_optional", "mode_optional"),
        outputs=("viewer_window", "viewer_url", "launch_manifest"),
    ),
    "op2_mode_shape_viewer_build": ApprovedTool(
        name="op2_mode_shape_viewer_build",
        category="visualization",
        purpose=(
            "Open FEM Explorer in a new local desktop window for BDF geometry plus "
            "referenced OP2 mode shapes. "
            "Use this when a user asks to view/animate a mode, including requests "
            "like 'view the first mode'; "
            "the OP2 path is optional when a matching .op2 file sits beside the BDF. "
            "Use viewer_backend='static' for modal JSON exports."
        ),
        risk_level="derived_data",
        default_llm_exposure="summary_only",
        inputs=("bdf", "op2_optional", "mode_optional"),
        outputs=(
            "viewer_window",
            "viewer_url",
            "launch_manifest",
            "gif_export_button",
        ),
    ),
    "modal_frf_compute": ApprovedTool(
        name="modal_frf_compute",
        category="dynamics",
        purpose="Compute displacement, velocity, or acceleration FRFs from modal terms.",
        risk_level="derived_data",
        default_llm_exposure="summary_only",
        inputs=("modal_terms", "frequencies_hz"),
        outputs=("frf_summary.json", "frf.csv"),
    ),
    "sol103_deck_build": ApprovedTool(
        name="sol103_deck_build",
        category="nastran",
        purpose="Generate a SOL103 modal deck from a typed config mapping or JSON/YAML config path.",
        risk_level="file_generation",
        default_llm_exposure="no_ingest",
        inputs=("config",),
        outputs=("run.dat", "sol103_build_summary.json"),
    ),
    "sol111_deck_build": ApprovedTool(
        name="sol111_deck_build",
        category="nastran",
        purpose="Generate a SOL111 deck from a typed config mapping or JSON/YAML config path.",
        risk_level="file_generation",
        default_llm_exposure="no_ingest",
        inputs=("config",),
        outputs=("run.dat", "sol111_build_summary.json"),
    ),
    "nastran_run_job": ApprovedTool(
        name="nastran_run_job",
        category="nastran",
        purpose="Run a NASTRAN-compatible command, capture process metadata, and collect output files.",
        risk_level="execution",
        default_llm_exposure="no_ingest",
        inputs=("deck",),
        outputs=("job_summary.json",),
    ),
    "nastran_f06_scan": ApprovedTool(
        name="nastran_f06_scan",
        category="nastran",
        purpose="Scan F06 text for fatal, error, and warning findings.",
        risk_level="read_only",
        default_llm_exposure="findings_only",
        inputs=("f06",),
        outputs=("f06_scan_summary.json", "f06_findings.csv"),
    ),
    "pch_parse_summary": ApprovedTool(
        name="pch_parse_summary",
        category="nastran",
        purpose="Parse PCH response blocks and return response/entity counts with optional row artifact.",
        risk_level="read_only",
        default_llm_exposure="summary_only",
        inputs=("pch",),
        outputs=("pch_summary.json", "pch_records.csv"),
    ),
    "psd_welch": ApprovedTool(
        name="psd_welch",
        category="signals",
        purpose="Compute a one-sided Welch PSD and integrated RMS from time-history samples.",
        risk_level="derived_data",
        default_llm_exposure="summary_only",
        inputs=("samples", "sample_rate_hz"),
        outputs=("psd_summary.json", "psd.csv"),
    ),
    "psd_maximax": ApprovedTool(
        name="psd_maximax",
        category="signals",
        purpose="Compute a maximax PSD envelope across channels.",
        risk_level="derived_data",
        default_llm_exposure="summary_only",
        inputs=("channels", "sample_rate_hz"),
        outputs=("maximax_psd_summary.json", "maximax_psd.csv"),
    ),
    "srs_compute": ApprovedTool(
        name="srs_compute",
        category="signals",
        purpose="Compute a pseudo-acceleration SRS from a base-acceleration time history.",
        risk_level="derived_data",
        default_llm_exposure="summary_only",
        inputs=("time_s", "acceleration_g", "frequencies_hz"),
        outputs=("srs_summary.json", "srs.csv"),
    ),
    "fds_compute": ApprovedTool(
        name="fds_compute",
        category="signals",
        purpose="Compute a relative fatigue damage spectrum and equivalent PSD estimate.",
        risk_level="derived_data",
        default_llm_exposure="summary_only",
        inputs=("time_s", "acceleration_g", "frequencies_hz"),
        outputs=("fds_summary.json", "fds.csv"),
    ),
    "hdf5_channel_summary": ApprovedTool(
        name="hdf5_channel_summary",
        category="data",
        purpose="Summarize HDF5 channels, sample rates, units, and simple statistics.",
        risk_level="read_only",
        default_llm_exposure="summary_only",
        inputs=("hdf5",),
        outputs=("hdf5_summary.json", "hdf5_channels.csv"),
    ),
}


def list_approved_tools() -> list[dict]:
    """Return the approved engineering tool catalog as JSON-safe dicts."""

    return [asdict(APPROVED_TOOLS[name]) for name in sorted(APPROVED_TOOLS)]


def _artifact_dir(params: Mapping[str, Any], tool_name: str) -> Path:
    out = Path(str(params.get("out") or params.get("output_dir") or Path.cwd() / "ava_tool_outputs" / tool_name))
    out.mkdir(parents=True, exist_ok=True)
    return out


def _write_json(path: Path, payload: Mapping[str, Any]) -> Path:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]], fieldnames: Sequence[str] | None = None) -> Path:
    if fieldnames is None:
        keys: list[str] = []
        for row in rows:
            for key in row:
                if key not in keys:
                    keys.append(key)
        fieldnames = keys
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames))
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: json.dumps(value) if isinstance(value, (list, dict, tuple)) else value
                    for key, value in row.items()
                }
            )
    return path


def _load_params(params: Mapping[str, Any] | str | Path | None) -> dict[str, Any]:
    if params is None:
        return {}
    if isinstance(params, Mapping):
        return dict(params)
    text_or_path = str(params)
    candidate = Path(text_or_path)
    if not text_or_path.lstrip().startswith(("{", "[")) and candidate.exists():
        return json.loads(candidate.read_text(encoding="utf-8"))
    loaded = json.loads(text_or_path)
    if not isinstance(loaded, dict):
        raise ValueError("Tool params must decode to a JSON object")
    return loaded


def _read_numeric_csv(path: str | Path) -> dict[str, list[float]]:
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("CSV input must have a header row")
        data = {field: [] for field in reader.fieldnames}
        for row in reader:
            for field in reader.fieldnames:
                value = row.get(field)
                if value is None or value == "":
                    continue
                try:
                    data[field].append(float(value))
                except ValueError:
                    pass
    return data


def _samples_from_params(params: Mapping[str, Any], *, key: str = "samples", column_key: str = "column") -> list[float]:
    if key in params:
        return [float(value) for value in params[key]]
    csv_path = params.get("csv") or params.get("csv_path")
    if not csv_path:
        raise ValueError(f"Expected '{key}' or 'csv_path'")
    data = _read_numeric_csv(csv_path)
    column = params.get(column_key)
    if column:
        return data[str(column)]
    for values in data.values():
        if values:
            return values
    raise ValueError("CSV input contains no numeric samples")


def _time_history_from_params(params: Mapping[str, Any]) -> tuple[list[float], list[float]]:
    if "time_s" in params and "acceleration_g" in params:
        return (
            [float(value) for value in params["time_s"]],
            [float(value) for value in params["acceleration_g"]],
        )
    csv_path = params.get("csv") or params.get("csv_path")
    if not csv_path:
        raise ValueError("Expected time_s/acceleration_g arrays or csv_path")
    data = _read_numeric_csv(csv_path)
    time_column = str(params.get("time_column", "time_s"))
    accel_column = str(params.get("acceleration_column", "acceleration_g"))
    return data[time_column], data[accel_column]


def _frequencies_from_params(params: Mapping[str, Any]) -> list[float]:
    if "frequencies_hz" in params:
        return [float(value) for value in params["frequencies_hz"]]
    start = float(params.get("frequency_start_hz", 1.0))
    stop = float(params.get("frequency_stop_hz", start))
    count = int(params.get("frequency_count", 1))
    if count <= 1:
        return [start]
    step = (stop - start) / (count - 1)
    return [start + index * step for index in range(count)]


def _status_from_summary(payload: Mapping[str, Any]) -> str:
    return str(payload.get("status") or payload.get("summary", {}).get("status") or "ok")


def _run_nastran_model_check(params: Mapping[str, Any], tool: ApprovedTool) -> ToolRunResult:
    out = _artifact_dir(params, tool.name)
    payload = model_diagnostics(params["bdf"], duplicate_tolerance=float(params.get("duplicate_tolerance", 1.0e-9)))
    artifacts = [
        _write_json(out / "model_check_summary.json", payload),
        _write_csv(out / "duplicate_nodes.csv", payload["duplicate_nodes"]),
        _write_csv(out / "free_edges.csv", payload["free_edges"]),
        _write_csv(out / "unused_properties.csv", [{"property_id": value} for value in payload["unused_properties"]]),
        _write_csv(out / "unused_materials.csv", [{"material_id": value} for value in payload["unused_materials"]]),
    ]
    return ToolRunResult(tool.name, "ok", tool.default_llm_exposure, payload["summary"], tuple(str(path) for path in artifacts))


def _run_nastran_mass_summary(params: Mapping[str, Any], tool: ApprovedTool) -> ToolRunResult:
    out = _artifact_dir(params, tool.name)
    payload = mass_summary(params["bdf"])
    artifacts = [
        _write_json(out / "mass_summary.json", payload),
        _write_csv(out / "mass_by_property.csv", [{"property_id": key, "mass": value} for key, value in payload["mass_by_property"].items()]),
        _write_csv(out / "mass_by_material.csv", [{"material_id": key, "mass": value} for key, value in payload["mass_by_material"].items()]),
    ]
    return ToolRunResult(tool.name, "ok", tool.default_llm_exposure, payload["summary"], tuple(str(path) for path in artifacts))


def _run_nastran_geometry_summary(params: Mapping[str, Any], tool: ApprovedTool) -> ToolRunResult:
    out = _artifact_dir(params, tool.name)
    payload = geometry_summary(params["bdf"])
    artifact = _write_json(out / "geometry_summary.json", payload)
    summary = {
        "nodes": payload["nodes"],
        "elements": payload["elements"],
        "properties": payload["properties"],
        "materials": payload["materials"],
        "mass_elements": payload["mass_elements"],
        "structural_components": len(payload["structural_components"]),
        "bounding_box": payload["bounding_box"],
    }
    return ToolRunResult(tool.name, "ok", tool.default_llm_exposure, summary, (str(artifact),))


def _run_op2_modal_summary(params: Mapping[str, Any], tool: ApprovedTool) -> ToolRunResult:
    out = _artifact_dir(params, tool.name)
    summary = summarize_op2_modal(params.get("op2") or params.get("path"))
    payload = modal_summary_dict(summary)
    artifacts = [_write_json(out / "modal_summary.json", payload)]
    if payload["modes"]:
        artifacts.append(_write_csv(out / "modes.csv", payload["modes"]))
    return ToolRunResult(
        tool.name,
        "ok",
        tool.default_llm_exposure,
        {
            "source": payload["source"],
            "mode_count": payload["mode_count"],
            "frequency_min_hz": payload["frequency_min_hz"],
            "frequency_max_hz": payload["frequency_max_hz"],
        },
        tuple(str(path) for path in artifacts),
    )


def _optional_int(value: object) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    return int(value)


def _optional_bool(value: object, *, default: bool = False) -> bool:
    if value is None or str(value).strip() == "":
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on", "animate", "animated"}


def _initial_mode_from_params(params: Mapping[str, Any]) -> str | int | None:
    for key in ("initial_mode", "initial_mode_id", "mode_id", "mode_number", "mode", "mode_index"):
        value = params.get(key)
        if value is not None and str(value).strip() != "":
            return value
    if _optional_bool(params.get("first_mode"), default=False):
        return 1
    return None


def _mode_result_path_from_params(params: Mapping[str, Any]) -> Path | None:
    for key in ("op2", "modes", "modes_path", "modal_result", "modal_result_path", "result"):
        value = params.get(key)
        if value is not None and str(value).strip():
            return Path(str(value))
    return None


def _discover_mode_result_for_bdf(bdf: str | Path) -> Path | None:
    bdf_path = Path(str(bdf)).expanduser()
    parent = bdf_path.parent
    stem = bdf_path.stem
    if not parent.exists():
        return None

    exact_candidates = [
        parent / f"{stem}.op2",
        parent / f"{stem}.OP2",
        parent / f"{stem}.json",
        parent / f"{stem}_modes.json",
        parent / f"{stem}-modes.json",
        parent / f"{stem}_modal.json",
        parent / f"{stem}-modal.json",
    ]
    for candidate in exact_candidates:
        if candidate.exists():
            return candidate

    stem_lower = stem.lower()
    exact_names = {candidate.name.lower() for candidate in exact_candidates}
    files = [candidate for candidate in parent.iterdir() if candidate.is_file()]
    for candidate in files:
        if candidate.name.lower() in exact_names:
            return candidate

    matches = sorted(
        [
            candidate
            for candidate in files
            if candidate.name.lower().startswith(stem_lower)
            and (
                candidate.suffix.lower() == ".op2"
                or (
                    candidate.suffix.lower() == ".json"
                    and ("mode" in candidate.name.lower() or "modal" in candidate.name.lower())
                )
            )
        ],
        key=lambda path: (path.suffix.lower() != ".op2", path.name.lower()),
    )
    return matches[0] if matches else None


def _resolve_mode_result_for_viewer(params: Mapping[str, Any], *, required: bool) -> Path | None:
    explicit = _mode_result_path_from_params(params)
    if explicit is not None:
        return explicit
    discovered = _discover_mode_result_for_bdf(params["bdf"])
    if discovered is not None:
        return discovered
    if required:
        bdf = Path(str(params["bdf"]))
        raise FileNotFoundError(
            f"No modal result was supplied and no matching .op2 or modal JSON was found beside {bdf}"
        )
    return None


def _viewer_backend(params: Mapping[str, Any]) -> str:
    backend = str(params.get("viewer_backend") or params.get("backend") or "fem_explorer").strip().lower()
    if backend in {"fem_explorer", "fem-explorer", "fem explorer", "electron", "desktop"}:
        return "fem_explorer"
    if backend in {"static", "ava_static", "html"}:
        return "static"
    raise ValueError("viewer_backend must be 'fem_explorer' or 'static'")


def _run_fem_explorer_viewer(
    params: Mapping[str, Any],
    tool: ApprovedTool,
    out: Path,
    *,
    mode_result: Path | None,
    required_mode: bool,
) -> ToolRunResult:
    if required_mode and mode_result is None:
        bdf = Path(str(params["bdf"]))
        raise FileNotFoundError(f"No .op2 modal result was supplied or discovered beside {bdf}")

    auto_animate = _optional_bool(
        params.get("auto_animate"),
        default=_optional_bool(params.get("animate"), default=mode_result is not None),
    )
    payload = launch_fem_explorer_viewer(
        params["bdf"],
        out,
        op2=mode_result,
        initial_mode=_initial_mode_from_params(params) or ("first" if mode_result is not None else None),
        auto_animate=auto_animate,
        fem_explorer_root=params.get("fem_explorer_root"),
    )
    summary = dict(payload["summary"])
    summary["viewer_url"] = summary.get("frontend_url")
    return ToolRunResult(tool.name, "ok", tool.default_llm_exposure, summary, tuple(payload["artifacts"]))


def _run_bdf_3d_viewer_build(params: Mapping[str, Any], tool: ApprovedTool) -> ToolRunResult:
    out = _artifact_dir(params, tool.name)
    explicit_mode_result = _mode_result_path_from_params(params)
    mode_result = explicit_mode_result if explicit_mode_result is not None else None
    if _viewer_backend(params) == "fem_explorer":
        return _run_fem_explorer_viewer(
            params,
            tool,
            out,
            mode_result=mode_result,
            required_mode=False,
        )

    if mode_result is not None:
        auto_animate = _optional_bool(
            params.get("auto_animate"),
            default=_optional_bool(params.get("animate"), default=True),
        )
        payload = build_op2_mode_shape_viewer(
            params["bdf"],
            mode_result,
            out,
            title=str(params["title"]) if params.get("title") else None,
            port=_optional_int(params.get("port")),
            mode_limit=_optional_int(params.get("mode_limit")),
            initial_mode=_initial_mode_from_params(params) or 1,
            auto_animate=auto_animate,
        )
    else:
        payload = build_bdf_3d_viewer(
            params["bdf"],
            out,
            title=str(params["title"]) if params.get("title") else None,
            port=_optional_int(params.get("port")),
        )
    return ToolRunResult(tool.name, "ok", tool.default_llm_exposure, payload["summary"], tuple(payload["artifacts"]))


def _run_op2_mode_shape_viewer_build(params: Mapping[str, Any], tool: ApprovedTool) -> ToolRunResult:
    out = _artifact_dir(params, tool.name)
    mode_result = _resolve_mode_result_for_viewer(params, required=True)
    if _viewer_backend(params) == "fem_explorer":
        return _run_fem_explorer_viewer(
            params,
            tool,
            out,
            mode_result=mode_result,
            required_mode=True,
        )

    auto_animate = _optional_bool(
        params.get("auto_animate"),
        default=_optional_bool(params.get("animate"), default=True),
    )
    payload = build_op2_mode_shape_viewer(
        params["bdf"],
        mode_result,
        out,
        title=str(params["title"]) if params.get("title") else None,
        port=_optional_int(params.get("port")),
        mode_limit=_optional_int(params.get("mode_limit")),
        initial_mode=_initial_mode_from_params(params) or 1,
        auto_animate=auto_animate,
    )
    return ToolRunResult(tool.name, "ok", tool.default_llm_exposure, payload["summary"], tuple(payload["artifacts"]))


def _modal_terms_from_params(params: Mapping[str, Any]) -> list[ModalTerm]:
    raw_terms = params.get("modal_terms")
    if raw_terms is None and params.get("modes_path"):
        modes = summarize_op2_modal(params["modes_path"]).modes
        raw_terms = modes_to_modal_terms(
            modes,
            damping_ratio=float(params.get("damping_ratio", 0.02)),
            modal_constant=float(params.get("modal_constant", 1.0)),
        )
    if raw_terms is None:
        raise ValueError("Expected modal_terms or modes_path")
    return [
        ModalTerm(
            natural_frequency_hz=float(term["natural_frequency_hz"]),
            damping_ratio=float(term.get("damping_ratio", params.get("damping_ratio", 0.02))),
            modal_constant=float(term.get("modal_constant", 1.0)),
        )
        for term in raw_terms
    ]


def _run_modal_frf_compute(params: Mapping[str, Any], tool: ApprovedTool) -> ToolRunResult:
    out = _artifact_dir(params, tool.name)
    result = compute_modal_frf(
        _modal_terms_from_params(params),
        _frequencies_from_params(params),
        response_type=str(params.get("response_type", "displacement")),
    )
    rows = [
        {
            "frequency_hz": point.frequency_hz,
            "real": point.complex_response.real,
            "imag": point.complex_response.imag,
            "magnitude": point.magnitude,
            "phase_degrees": point.phase_degrees,
        }
        for point in result.points
    ]
    peak = max(rows, key=lambda row: row["magnitude"]) if rows else None
    summary = {
        "response_type": result.response_type,
        "point_count": len(rows),
        "peak_frequency_hz": peak["frequency_hz"] if peak else None,
        "peak_magnitude": peak["magnitude"] if peak else None,
    }
    artifacts = [
        _write_json(out / "frf_summary.json", {"summary": summary, "points": rows}),
        _write_csv(out / "frf.csv", rows),
    ]
    return ToolRunResult(tool.name, "ok", tool.default_llm_exposure, summary, tuple(str(path) for path in artifacts))


def _run_sol103_deck_build(params: Mapping[str, Any], tool: ApprovedTool) -> ToolRunResult:
    out = _artifact_dir(params, tool.name)
    config = params.get("config") or params.get("config_path") or params
    deck_text = build_sol103_deck_from_config(config)
    deck_path = write_deck(out / str(params.get("deck_name", "run.dat")), deck_text)
    summary = {
        "deck_path": str(deck_path),
        "line_count": len(deck_text.splitlines()),
        "solution": 103,
    }
    summary_path = _write_json(out / "sol103_build_summary.json", summary)
    return ToolRunResult(tool.name, "ok", tool.default_llm_exposure, summary, (str(deck_path), str(summary_path)))


def _run_sol111_deck_build(params: Mapping[str, Any], tool: ApprovedTool) -> ToolRunResult:
    out = _artifact_dir(params, tool.name)
    config = params.get("config") or params.get("config_path") or params
    deck_text = build_sol111_deck_from_config(config)
    deck_path = write_deck(out / str(params.get("deck_name", "run.dat")), deck_text)
    summary = {
        "deck_path": str(deck_path),
        "line_count": len(deck_text.splitlines()),
        "solution": 111,
    }
    summary_path = _write_json(out / "sol111_build_summary.json", summary)
    return ToolRunResult(tool.name, "ok", tool.default_llm_exposure, summary, (str(deck_path), str(summary_path)))


def _run_nastran_run_job(params: Mapping[str, Any], tool: ApprovedTool) -> ToolRunResult:
    out = _artifact_dir(params, tool.name)
    deck_path = Path(str(params["deck"]))
    workdir = Path(str(params.get("working_directory") or params.get("workdir") or deck_path.parent))
    executable = str(params.get("executable", "nastran"))
    keywords = {str(key): str(value) for key, value in dict(params.get("keywords", {})).items()}
    runner = NastranRunner()
    request = NastranRunRequest(deck_path=deck_path, working_directory=workdir, executable=executable, keywords=keywords)
    command = runner.build_command(request)
    if params.get("dry_run", False):
        payload = {
            "status": "dry_run",
            "command": list(command),
            "return_code": None,
            "duration_seconds": 0.0,
            "output_files": {},
        }
    else:
        result = runner.run(request, timeout_seconds=params.get("timeout_seconds"))
        payload = {
            "status": "ok" if result.succeeded else "failed",
            "command": list(result.command),
            "return_code": result.return_code,
            "duration_seconds": result.duration_seconds,
            "stdout_chars": len(result.stdout),
            "stderr_chars": len(result.stderr),
            "output_files": {key: str(value) for key, value in result.output_files.items()},
        }
    artifact = _write_json(out / "job_summary.json", payload)
    return ToolRunResult(tool.name, payload["status"], tool.default_llm_exposure, payload, (str(artifact),))


def _run_nastran_f06_scan(params: Mapping[str, Any], tool: ApprovedTool) -> ToolRunResult:
    out = _artifact_dir(params, tool.name)
    payload = scan_f06(params["f06"])
    artifacts = [
        _write_json(out / "f06_scan_summary.json", payload),
        _write_csv(out / "f06_findings.csv", payload["findings"]),
    ]
    summary = {
        "status": payload["status"],
        "finding_count": payload["finding_count"],
        "severity_counts": payload["severity_counts"],
    }
    return ToolRunResult(tool.name, payload["status"], tool.default_llm_exposure, summary, tuple(str(path) for path in artifacts))


def _run_pch_parse_summary(params: Mapping[str, Any], tool: ApprovedTool) -> ToolRunResult:
    out = _artifact_dir(params, tool.name)
    summary = summarize_pch(params["pch"])
    payload = pch_summary_dict(summary)
    records = parse_pch_records(params["pch"])
    artifacts = [
        _write_json(out / "pch_summary.json", payload),
        _write_csv(
            out / "pch_records.csv",
            [
                {
                    "response_type": record.response_type,
                    "entity_id": record.entity_id,
                    "abscissa": record.abscissa,
                    "values": list(record.values),
                }
                for record in records
            ],
        ),
    ]
    return ToolRunResult(tool.name, "ok", tool.default_llm_exposure, payload, tuple(str(path) for path in artifacts))


def _run_psd_welch(params: Mapping[str, Any], tool: ApprovedTool) -> ToolRunResult:
    out = _artifact_dir(params, tool.name)
    result = calculate_psd_welch(
        _samples_from_params(params),
        float(params["sample_rate_hz"]),
        segment_size=int(params["segment_size"]) if params.get("segment_size") else None,
        overlap=float(params.get("overlap", 0.5)),
        window=str(params.get("window", "hann")),
    )
    payload = psd_result_dict(result)
    artifacts = [
        _write_json(out / "psd_summary.json", payload),
        _write_csv(out / "psd.csv", payload["points"]),
    ]
    summary = {key: payload[key] for key in ("method", "point_count", "rms", "peak_frequency_hz", "peak_psd")}
    return ToolRunResult(tool.name, "ok", tool.default_llm_exposure, summary, tuple(str(path) for path in artifacts))


def _channels_from_params(params: Mapping[str, Any]) -> list[list[float]]:
    if "channels" in params:
        return [[float(value) for value in channel] for channel in params["channels"]]
    csv_path = params.get("csv") or params.get("csv_path")
    if not csv_path:
        return [_samples_from_params(params)]
    data = _read_numeric_csv(csv_path)
    columns = params.get("columns")
    if columns:
        return [data[str(column)] for column in columns]
    return [values for values in data.values() if values]


def _run_psd_maximax(params: Mapping[str, Any], tool: ApprovedTool) -> ToolRunResult:
    out = _artifact_dir(params, tool.name)
    result = calculate_psd_maximax(
        _channels_from_params(params),
        float(params["sample_rate_hz"]),
        segment_size=int(params["segment_size"]) if params.get("segment_size") else None,
        overlap=float(params.get("overlap", 0.5)),
        window=str(params.get("window", "hann")),
    )
    payload = psd_result_dict(result)
    artifacts = [
        _write_json(out / "maximax_psd_summary.json", payload),
        _write_csv(out / "maximax_psd.csv", payload["points"]),
    ]
    summary = {key: payload[key] for key in ("method", "point_count", "rms", "peak_frequency_hz", "peak_psd")}
    return ToolRunResult(tool.name, "ok", tool.default_llm_exposure, summary, tuple(str(path) for path in artifacts))


def _srs_payload_from_params(params: Mapping[str, Any]) -> dict:
    time_s, acceleration_g = _time_history_from_params(params)
    result = compute_srs(
        time_s,
        acceleration_g,
        _frequencies_from_params(params),
        damping_ratio=float(params.get("damping_ratio", 0.05)),
    )
    points = [
        {
            "frequency_hz": point.natural_frequency_hz,
            "pseudo_acceleration_g": point.pseudo_acceleration_g,
            "relative_displacement_mm": point.relative_displacement_mm,
        }
        for point in result.points
    ]
    peak = max(points, key=lambda row: row["pseudo_acceleration_g"]) if points else None
    return {
        "damping_ratio": result.damping_ratio,
        "point_count": len(points),
        "peak_frequency_hz": peak["frequency_hz"] if peak else None,
        "peak_pseudo_acceleration_g": peak["pseudo_acceleration_g"] if peak else None,
        "points": points,
    }


def _run_srs_compute(params: Mapping[str, Any], tool: ApprovedTool) -> ToolRunResult:
    out = _artifact_dir(params, tool.name)
    payload = _srs_payload_from_params(params)
    artifacts = [
        _write_json(out / "srs_summary.json", payload),
        _write_csv(out / "srs.csv", payload["points"]),
    ]
    summary = {key: payload[key] for key in ("damping_ratio", "point_count", "peak_frequency_hz", "peak_pseudo_acceleration_g")}
    return ToolRunResult(tool.name, "ok", tool.default_llm_exposure, summary, tuple(str(path) for path in artifacts))


def _run_fds_compute(params: Mapping[str, Any], tool: ApprovedTool) -> ToolRunResult:
    out = _artifact_dir(params, tool.name)
    time_s, acceleration_g = _time_history_from_params(params)
    result = compute_fds(
        time_s,
        acceleration_g,
        _frequencies_from_params(params),
        damping_ratio=float(params.get("damping_ratio", 0.05)),
        fatigue_exponent=float(params.get("fatigue_exponent", 6.0)),
    )
    payload = fds_result_dict(result)
    artifacts = [
        _write_json(out / "fds_summary.json", payload),
        _write_csv(out / "fds.csv", payload["points"]),
    ]
    summary = {
        key: payload[key]
        for key in ("damping_ratio", "fatigue_exponent", "point_count", "peak_damage_frequency_hz", "peak_damage_index")
    }
    return ToolRunResult(tool.name, "ok", tool.default_llm_exposure, summary, tuple(str(path) for path in artifacts))


def _run_hdf5_channel_summary(params: Mapping[str, Any], tool: ApprovedTool) -> ToolRunResult:
    out = _artifact_dir(params, tool.name)
    payload = summarize_hdf5_channels(params.get("hdf5") or params.get("path"))
    artifacts = [
        _write_json(out / "hdf5_summary.json", payload),
        _write_csv(out / "hdf5_channels.csv", payload.get("channels", [])),
    ]
    summary = {
        "status": payload["status"],
        "hdf5_signature": payload["hdf5_signature"],
        "channel_count": payload["channel_count"],
        "file_size_bytes": payload["file_size_bytes"],
    }
    if "reason" in payload:
        summary["reason"] = payload["reason"]
    return ToolRunResult(tool.name, payload["status"], tool.default_llm_exposure, summary, tuple(str(path) for path in artifacts))


_RUNNERS: dict[str, Callable[[Mapping[str, Any], ApprovedTool], ToolRunResult]] = {
    "nastran_model_check": _run_nastran_model_check,
    "nastran_mass_summary": _run_nastran_mass_summary,
    "nastran_geometry_summary": _run_nastran_geometry_summary,
    "op2_modal_summary": _run_op2_modal_summary,
    "bdf_3d_viewer_build": _run_bdf_3d_viewer_build,
    "op2_mode_shape_viewer_build": _run_op2_mode_shape_viewer_build,
    "modal_frf_compute": _run_modal_frf_compute,
    "sol103_deck_build": _run_sol103_deck_build,
    "sol111_deck_build": _run_sol111_deck_build,
    "nastran_run_job": _run_nastran_run_job,
    "nastran_f06_scan": _run_nastran_f06_scan,
    "pch_parse_summary": _run_pch_parse_summary,
    "psd_welch": _run_psd_welch,
    "psd_maximax": _run_psd_maximax,
    "srs_compute": _run_srs_compute,
    "fds_compute": _run_fds_compute,
    "hdf5_channel_summary": _run_hdf5_channel_summary,
}


def run_engineering_tool(name: str, params: Mapping[str, Any] | str | Path | None = None) -> dict:
    """Run one approved engineering tool and return the standard envelope."""

    if name not in APPROVED_TOOLS:
        valid = ", ".join(sorted(APPROVED_TOOLS))
        raise ValueError(f"Unknown approved engineering tool {name!r}. Valid tools: {valid}")
    tool_params = _load_params(params)
    tool = APPROVED_TOOLS[name]
    result = _RUNNERS[name](tool_params, tool)
    return result.to_dict()


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint for local approved engineering tools."""

    parser = argparse.ArgumentParser(prog="ava-tool")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("catalog")
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("tool_name")
    run_parser.add_argument("--params", default="{}")
    args = parser.parse_args(argv)

    if args.command == "catalog":
        print(json.dumps(list_approved_tools(), indent=2, sort_keys=True))
        return 0
    if args.command == "run":
        print(json.dumps(run_engineering_tool(args.tool_name, args.params), indent=2, sort_keys=True))
        return 0
    raise AssertionError(f"Unhandled command {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
