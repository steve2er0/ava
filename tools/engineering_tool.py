"""Approved engineering tools exposed to the AVA agent."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from ava_runtime.engineering_tools import list_approved_tools, run_engineering_tool
from tools.registry import registry, tool_error, tool_result


BDF_INPUT_TOOLS = {
    "bdf_3d_viewer_build",
    "nastran_geometry_summary",
    "nastran_mass_summary",
    "nastran_model_check",
    "op2_mode_shape_viewer_build",
}
VIEWER_TOOLS = {"bdf_3d_viewer_build", "op2_mode_shape_viewer_build"}
BDF_PATH_KEYS = (
    "bdf",
    "bdf_path",
    "model_path",
    "file_path",
    "path",
    "file",
    "model",
    "source",
)
BDF_NAME_KEYS = ("model_name", "name", "filename", "file_name", "stem")
BDF_LOCATION_KEYS = (
    "directory",
    "dir",
    "folder",
    "location",
    "located_here",
    "root",
    "parent",
)
BDF_SUFFIXES = (".bdf", ".dat", ".nas", ".fem")


def engineering_tool_catalog_handler(args, **kwargs) -> str:
    """Return approved engineering tool metadata."""

    return tool_result({"tools": list_approved_tools()})


def engineering_tool_run_handler(args, **kwargs) -> str:
    """Run one approved engineering tool."""

    try:
        tool_name, params = _normalize_run_args(args)
        result = run_engineering_tool(tool_name, params)
        _add_agent_guidance(tool_name, result)
        return tool_result(result)
    except Exception as exc:
        return tool_error(str(exc))


def _add_agent_guidance(tool_name: str, result: dict[str, Any]) -> None:
    if tool_name not in VIEWER_TOOLS or result.get("status") != "ok":
        return
    summary = result.get("summary")
    if not isinstance(summary, dict) or summary.get("viewer_backend") != "fem_explorer":
        return
    result["agent_guidance"] = (
        "FEM Explorer has already been launched in a desktop window. "
        "Do not call terminal/open/curl/pgrep after this successful viewer result. "
        "Reply with the BDF path, launch mode, viewer URL, and note that OP2 modes were not loaded unless op2_path is set."
    )


def _normalize_run_args(args: Mapping[str, Any] | None) -> tuple[str, dict[str, Any]]:
    if not isinstance(args, Mapping):
        return "", {}

    tool_name = str(args.get("tool_name") or args.get("tool") or args.get("name") or "")
    raw_params = args.get("params")
    params: dict[str, Any] = dict(raw_params) if isinstance(raw_params, Mapping) else {}
    for key, value in args.items():
        if key not in {"tool_name", "tool", "name", "params"} and key not in params:
            params[key] = value

    _normalize_bdf_input(tool_name, params)
    return tool_name, params


def _normalize_bdf_input(tool_name: str, params: dict[str, Any]) -> None:
    if tool_name not in BDF_INPUT_TOOLS or params.get("bdf"):
        if params.get("bdf"):
            params["bdf"] = _resolve_bdf_reference(params["bdf"], params)
        return

    for key in BDF_PATH_KEYS:
        value = params.get(key)
        if value is not None and str(value).strip():
            resolved = _resolve_bdf_reference(value, params)
            if resolved:
                params["bdf"] = resolved
            return

    name = _first_param(params, BDF_NAME_KEYS)
    location = _first_param(params, BDF_LOCATION_KEYS)
    if name and location:
        resolved = _resolve_bdf_reference(name, params)
        if resolved:
            params["bdf"] = resolved


def _resolve_bdf_reference(value: Any, params: Mapping[str, Any]) -> str:
    raw = str(value).strip()
    if not raw:
        return raw

    candidate = Path(raw).expanduser()
    location = _first_param(params, BDF_LOCATION_KEYS)
    name = _first_param(params, BDF_NAME_KEYS)
    if location and not candidate.is_absolute():
        candidate = Path(str(location)).expanduser() / candidate
    if candidate.is_dir() and name:
        candidate = candidate / str(name)

    resolved = _existing_bdf_path(candidate)
    if resolved is not None:
        return str(resolved)
    return str(candidate)


def _existing_bdf_path(candidate: Path) -> Path | None:
    direct = _case_insensitive_existing(candidate)
    if direct is not None and direct.is_file():
        return direct

    parent = candidate.parent
    if not parent.exists() or not parent.is_dir():
        return None

    if candidate.suffix:
        return None

    for suffix in BDF_SUFFIXES:
        direct = _case_insensitive_existing(candidate.with_suffix(suffix))
        if direct is not None and direct.is_file():
            return direct

    stem = candidate.name.lower()
    for child in sorted(parent.iterdir(), key=lambda path: path.name.lower()):
        if child.is_file() and child.stem.lower() == stem and child.suffix.lower() in BDF_SUFFIXES:
            return child
    return None


def _case_insensitive_existing(path: Path) -> Path | None:
    if path.exists():
        return path.resolve()
    parent = path.parent
    if not parent.exists() or not parent.is_dir():
        return None
    target = path.name.lower()
    for child in parent.iterdir():
        if child.name.lower() == target:
            return child.resolve()
    return None


def _first_param(params: Mapping[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = params.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


registry.register(
    name="engineering_tool_catalog",
    toolset="engineering",
    schema={
        "name": "engineering_tool_catalog",
        "description": "List approved AVA engineering tools, including risk level and default LLM exposure.",
        "parameters": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    handler=engineering_tool_catalog_handler,
    requires_env=[],
)

registry.register(
    name="engineering_tool_run",
    toolset="engineering",
    schema={
        "name": "engineering_tool_run",
        "description": (
            "Run one approved AVA engineering tool. Inputs are file paths or compact config values; "
            "raw engineering files are processed locally and only summaries/artifact paths are returned by default. "
            "For FEM Explorer viewer tools, a successful result with window='launched' means the desktop window is already open; "
            "do not run terminal/open/curl/pgrep afterward."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "tool_name": {
                    "type": "string",
                    "enum": [
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
                    ],
                },
                "params": {
                    "type": "object",
                    "description": "Tool-specific parameters. Use paths/configs for engineering inputs and an optional out/output_dir for artifacts.",
                    "additionalProperties": True,
                },
            },
            "required": ["tool_name", "params"],
            "additionalProperties": False,
        },
    },
    handler=engineering_tool_run_handler,
    requires_env=[],
)
