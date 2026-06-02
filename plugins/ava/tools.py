"""Hermes tool handlers for the AVA vibroacoustic runtime."""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from ava_runtime.analysis.frf import ModalTerm, compute_modal_frf
from ava_runtime.analysis.srs import compute_srs
from ava_runtime.parsers.bdf_parser import summarize_bdf
from ava_runtime.parsers.op2_parser import inspect_op2_stream
from ava_runtime.pipelines.shock_delta import ShockDeltaCase, run_shock_delta
from ava_runtime.solvers.deck_builder import ModalDeckRequest, build_modal_deck, write_deck
from tools.registry import tool_error, tool_result


_NUMBER = {"type": "number"}
_STRING = {"type": "string"}
_FLOAT_ARRAY = {"type": "array", "items": _NUMBER}
_MODAL_TERM_SCHEMA = {
    "type": "object",
    "properties": {
        "natural_frequency_hz": _NUMBER,
        "damping_ratio": _NUMBER,
        "modal_constant": _NUMBER,
    },
    "required": ["natural_frequency_hz", "damping_ratio", "modal_constant"],
}


AVA_COMPUTE_MODAL_FRF_SCHEMA = {
    "name": "ava_compute_modal_frf",
    "description": "Compute a modal frequency-response function from modal terms and a frequency grid.",
    "parameters": {
        "type": "object",
        "properties": {
            "modes": {"type": "array", "items": _MODAL_TERM_SCHEMA},
            "frequencies_hz": _FLOAT_ARRAY,
            "response_type": {
                "type": "string",
                "enum": ["displacement", "velocity", "acceleration"],
                "default": "displacement",
            },
        },
        "required": ["modes", "frequencies_hz"],
    },
}


AVA_COMPUTE_SRS_SCHEMA = {
    "name": "ava_compute_srs",
    "description": "Compute a pseudo-acceleration shock response spectrum from a base-acceleration history.",
    "parameters": {
        "type": "object",
        "properties": {
            "time_s": _FLOAT_ARRAY,
            "base_acceleration_g": _FLOAT_ARRAY,
            "natural_frequencies_hz": _FLOAT_ARRAY,
            "damping_ratio": {"type": "number", "default": 0.05},
        },
        "required": ["time_s", "base_acceleration_g", "natural_frequencies_hz"],
    },
}


AVA_SUMMARIZE_BDF_SCHEMA = {
    "name": "ava_summarize_bdf",
    "description": "Summarize a NASTRAN BDF model: GRID count, element mix, concentrated masses, and bounds.",
    "parameters": {
        "type": "object",
        "properties": {
            "bdf_path": _STRING,
        },
        "required": ["bdf_path"],
    },
}


AVA_INSPECT_OP2_SCHEMA = {
    "name": "ava_inspect_op2",
    "description": "Inspect an OP2-like Fortran binary stream and report coarse metadata.",
    "parameters": {
        "type": "object",
        "properties": {
            "op2_path": _STRING,
        },
        "required": ["op2_path"],
    },
}


AVA_BUILD_MODAL_DECK_SCHEMA = {
    "name": "ava_build_modal_deck",
    "description": "Build a basic NASTRAN SOL 103 modal deck and optionally write it to disk.",
    "parameters": {
        "type": "object",
        "properties": {
            "title": _STRING,
            "spc_id": {"type": "integer"},
            "method_id": {"type": "integer"},
            "mode_count": {"type": "integer"},
            "frequency_upper_hz": _NUMBER,
            "bulk_data_lines": {"type": "array", "items": _STRING},
            "case_control_overrides": {"type": "array", "items": _STRING},
            "output_path": _STRING,
        },
        "required": ["title", "spc_id", "method_id", "mode_count", "frequency_upper_hz"],
    },
}


AVA_RUN_SHOCK_DELTA_SCHEMA = {
    "name": "ava_run_shock_delta",
    "description": "Run the AVA shock-delta workflow and emit review artifacts under an output directory.",
    "parameters": {
        "type": "object",
        "properties": {
            "case_name": _STRING,
            "bdf_path": _STRING,
            "output_directory": _STRING,
            "response_metric": {
                "type": "string",
                "enum": ["global_displacement", "interface_load", "local_acceleration", "local_stress"],
            },
            "event_duration_seconds": _NUMBER,
            "first_mode_hz": _NUMBER,
            "cumulative_effective_mass_percent": _NUMBER,
            "damping_basis_documented": {"type": "boolean"},
            "op2_path": _STRING,
            "convergence_delta_percent": _NUMBER,
            "time_seconds": _FLOAT_ARRAY,
            "base_acceleration_g": _FLOAT_ARRAY,
            "srs_frequencies_hz": _FLOAT_ARRAY,
            "frf_frequencies_hz": _FLOAT_ARRAY,
            "modal_terms": {"type": "array", "items": _MODAL_TERM_SCHEMA},
            "frf_response_type": {
                "type": "string",
                "enum": ["displacement", "velocity", "acceleration"],
                "default": "acceleration",
            },
            "knowledge_root": _STRING,
        },
        "required": [
            "case_name",
            "bdf_path",
            "response_metric",
            "event_duration_seconds",
            "first_mode_hz",
            "cumulative_effective_mass_percent",
            "damping_basis_documented",
        ],
    },
}


def _as_float_list(raw: Any, field: str) -> list[float]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError(f"{field} must be an array")
    return [float(item) for item in raw]


def _as_string_list(raw: Any, field: str) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError(f"{field} must be an array")
    return [str(item) for item in raw]


def _as_bool(raw: Any, field: str) -> bool:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        cleaned = raw.strip().lower()
        if cleaned in {"1", "true", "yes", "on"}:
            return True
        if cleaned in {"0", "false", "no", "off"}:
            return False
    raise ValueError(f"{field} must be a boolean")


def _modal_terms(raw: Any, field: str = "modes") -> list[ModalTerm]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError(f"{field} must be an array")
    terms = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"{field}[{index}] must be an object")
        terms.append(
            ModalTerm(
                natural_frequency_hz=float(item["natural_frequency_hz"]),
                damping_ratio=float(item["damping_ratio"]),
                modal_constant=float(item["modal_constant"]),
            )
        )
    return terms


def _path(value: Any, field: str) -> Path:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} is required")
    return Path(text).expanduser()


def _optional_path(value: Any) -> Path | None:
    text = str(value or "").strip()
    return Path(text).expanduser() if text else None


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value


def _frf_payload(result) -> dict[str, Any]:
    return {
        "response_type": result.response_type,
        "points": [
            {
                "frequency_hz": point.frequency_hz,
                "real": point.complex_response.real,
                "imag": point.complex_response.imag,
                "magnitude": point.magnitude,
                "phase_degrees": point.phase_degrees,
            }
            for point in result.points
        ],
    }


def _srs_payload(result) -> dict[str, Any]:
    return {
        "damping_ratio": result.damping_ratio,
        "points": [asdict(point) for point in result.points],
    }


def _bdf_payload(summary) -> dict[str, Any]:
    bounding_box = asdict(summary.bounding_box) if summary.bounding_box else None
    if bounding_box:
        bounding_box["span"] = list(summary.bounding_box.span)
    return {
        "path": str(summary.path),
        "grid_count": summary.grid_count,
        "element_counts": summary.element_counts,
        "mass_element_count": summary.mass_element_count,
        "bounding_box": bounding_box,
    }


def _default_shock_delta_output(case_name: str) -> Path:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", case_name.strip().lower()).strip("_")
    slug = slug[:48] or "case"
    date_prefix = datetime.now().strftime("%Y-%m-%d")
    return Path.cwd() / "ava_workspace" / "runs" / f"{date_prefix}_shock_delta_{slug}"


def handle_compute_modal_frf(args: dict, **_: Any) -> str:
    try:
        result = compute_modal_frf(
            modes=_modal_terms(args.get("modes")),
            frequencies_hz=_as_float_list(args.get("frequencies_hz"), "frequencies_hz"),
            response_type=str(args.get("response_type") or "displacement"),
        )
        return tool_result(_frf_payload(result))
    except Exception as exc:
        return tool_error(f"AVA FRF calculation failed: {type(exc).__name__}: {exc}")


def handle_compute_srs(args: dict, **_: Any) -> str:
    try:
        result = compute_srs(
            time_s=_as_float_list(args.get("time_s"), "time_s"),
            base_acceleration_g=_as_float_list(args.get("base_acceleration_g"), "base_acceleration_g"),
            natural_frequencies_hz=_as_float_list(args.get("natural_frequencies_hz"), "natural_frequencies_hz"),
            damping_ratio=float(args.get("damping_ratio", 0.05)),
        )
        return tool_result(_srs_payload(result))
    except Exception as exc:
        return tool_error(f"AVA SRS calculation failed: {type(exc).__name__}: {exc}")


def handle_summarize_bdf(args: dict, **_: Any) -> str:
    try:
        return tool_result(_bdf_payload(summarize_bdf(_path(args.get("bdf_path"), "bdf_path"))))
    except Exception as exc:
        return tool_error(f"AVA BDF summary failed: {type(exc).__name__}: {exc}")


def handle_inspect_op2(args: dict, **_: Any) -> str:
    try:
        return tool_result(_jsonable(asdict(inspect_op2_stream(_path(args.get("op2_path"), "op2_path")))))
    except Exception as exc:
        return tool_error(f"AVA OP2 inspection failed: {type(exc).__name__}: {exc}")


def handle_build_modal_deck(args: dict, **_: Any) -> str:
    try:
        request = ModalDeckRequest(
            title=str(args["title"]),
            spc_id=int(args["spc_id"]),
            method_id=int(args["method_id"]),
            mode_count=int(args["mode_count"]),
            frequency_upper_hz=float(args["frequency_upper_hz"]),
            bulk_data_lines=tuple(_as_string_list(args.get("bulk_data_lines"), "bulk_data_lines")),
            case_control_overrides=tuple(
                _as_string_list(args.get("case_control_overrides"), "case_control_overrides")
            ),
        )
        deck_text = build_modal_deck(request)
        output_path = _optional_path(args.get("output_path"))
        payload = {"deck_text": deck_text}
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            payload["output_path"] = str(write_deck(output_path, deck_text))
        return tool_result(payload)
    except Exception as exc:
        return tool_error(f"AVA modal deck build failed: {type(exc).__name__}: {exc}")


def handle_run_shock_delta(args: dict, **_: Any) -> str:
    try:
        case_name = str(args["case_name"]).strip()
        output_directory = _optional_path(args.get("output_directory")) or _default_shock_delta_output(case_name)
        case = ShockDeltaCase(
            case_name=case_name,
            bdf_path=_path(args.get("bdf_path"), "bdf_path"),
            output_directory=output_directory,
            response_metric=str(args["response_metric"]),
            event_duration_seconds=float(args["event_duration_seconds"]),
            first_mode_hz=float(args["first_mode_hz"]),
            cumulative_effective_mass_percent=float(args["cumulative_effective_mass_percent"]),
            damping_basis_documented=_as_bool(args["damping_basis_documented"], "damping_basis_documented"),
            op2_path=_optional_path(args.get("op2_path")),
            convergence_delta_percent=(
                float(args["convergence_delta_percent"])
                if args.get("convergence_delta_percent") is not None
                else None
            ),
            time_seconds=tuple(_as_float_list(args.get("time_seconds"), "time_seconds")),
            base_acceleration_g=tuple(_as_float_list(args.get("base_acceleration_g"), "base_acceleration_g")),
            srs_frequencies_hz=tuple(_as_float_list(args.get("srs_frequencies_hz"), "srs_frequencies_hz")),
            frf_frequencies_hz=tuple(_as_float_list(args.get("frf_frequencies_hz"), "frf_frequencies_hz")),
            modal_terms=tuple(_modal_terms(args.get("modal_terms"), "modal_terms")),
            frf_response_type=str(args.get("frf_response_type") or "acceleration"),
        )
        knowledge_root = args.get("knowledge_root") or _packaged_knowledge_root()
        result = run_shock_delta(case, knowledge_root=knowledge_root)
        summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
        return tool_result(
            {
                "summary": summary,
                "summary_path": str(result.summary_path),
                "response_table_path": str(result.response_table_path),
                "figure_path": str(result.figure_path) if result.figure_path else None,
            }
        )
    except Exception as exc:
        return tool_error(f"AVA shock-delta workflow failed: {type(exc).__name__}: {exc}")


def _packaged_knowledge_root() -> Path:
    import ava_knowledge

    return Path(ava_knowledge.__file__).resolve().parent
