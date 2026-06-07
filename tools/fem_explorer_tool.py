"""Standalone FEM Explorer tools exposed to AVA."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from ava_runtime.visualization.fem_explorer_launcher import launch_fem_explorer_viewer
from tools.registry import registry, tool_error, tool_result


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
OP2_PATH_KEYS = ("op2", "op2_path", "modes", "modes_path", "modal_result", "modal_result_path", "result")


def fem_explorer_open_handler(args, **kwargs) -> str:
    """Launch FEM Explorer in a new desktop window for a referenced BDF."""

    try:
        params = _normalize_open_args(args)
        bdf = _required_bdf(params)
        mode_requested = _mode_view_intent_requested(params)
        op2 = _resolve_op2_for_request(params, bdf, required=mode_requested)
        out = _viewer_output_dir(params, bdf, mode_requested=mode_requested, op2=op2)
        auto_animate = _optional_bool(
            params.get("auto_animate"),
            default=_optional_bool(params.get("animate"), default=op2 is not None),
        )
        initial_mode = _initial_mode_from_params(params)
        if op2 is None:
            initial_mode = None

        payload = launch_fem_explorer_viewer(
            bdf,
            out,
            op2=op2,
            initial_mode=initial_mode or ("first" if op2 is not None else None),
            auto_animate=auto_animate,
            fem_explorer_root=params.get("fem_explorer_root"),
        )
        summary = dict(payload["summary"])
        summary["viewer_url"] = summary.get("frontend_url")
        result = {
            "tool": "fem_explorer_open",
            "status": "ok",
            "llm_exposure": "summary_only",
            "summary": summary,
            "artifacts": list(payload["artifacts"]),
            "agent_guidance": (
                "FEM Explorer has already been launched in a desktop window. "
                "Do not call terminal/open/curl/pgrep after this successful viewer result. "
                "Reply with the BDF path, launch mode, viewer URL, and OP2 status."
            ),
        }
        return tool_result(result)
    except Exception as exc:
        return tool_error(str(exc))


def _normalize_open_args(args: Mapping[str, Any] | None) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if not isinstance(args, Mapping):
        return params

    raw_params = args.get("params")
    if isinstance(raw_params, Mapping):
        params.update(raw_params)
    for key, value in args.items():
        if key != "params" and key not in params:
            params[key] = value

    _normalize_bdf_input(params)
    return params


def _normalize_bdf_input(params: dict[str, Any]) -> None:
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


def _required_bdf(params: Mapping[str, Any]) -> Path:
    bdf = params.get("bdf")
    if bdf is None or not str(bdf).strip():
        raise ValueError("Expected a BDF path, or model_name plus directory/location.")
    path = Path(str(bdf)).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(path)
    return path


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


def _resolve_op2_for_request(params: Mapping[str, Any], bdf: Path, *, required: bool) -> Path | None:
    explicit = _op2_path_from_params(params)
    if explicit is not None:
        return _validate_op2(explicit)
    if not required:
        return None
    discovered = _discover_op2_for_bdf(bdf)
    if discovered is not None:
        return discovered
    raise FileNotFoundError(f"No .op2 modal result was supplied or discovered beside {bdf}")


def _op2_path_from_params(params: Mapping[str, Any]) -> Path | None:
    for key in OP2_PATH_KEYS:
        value = params.get(key)
        if value is not None and str(value).strip():
            return Path(str(value)).expanduser()
    return None


def _validate_op2(path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.exists():
        raise FileNotFoundError(resolved)
    if resolved.suffix.lower() != ".op2":
        raise ValueError("FEM Explorer mode visualization requires an .op2 result file.")
    return resolved


def _discover_op2_for_bdf(bdf: Path) -> Path | None:
    parent = bdf.parent
    stem = bdf.stem
    exact_candidates = [parent / f"{stem}.op2", parent / f"{stem}.OP2"]
    for candidate in exact_candidates:
        if candidate.exists():
            return candidate.resolve()

    stem_lower = stem.lower()
    matches = sorted(
        [
            candidate
            for candidate in parent.iterdir()
            if candidate.is_file()
            and candidate.suffix.lower() == ".op2"
            and candidate.stem.lower().startswith(stem_lower)
        ],
        key=lambda path: path.name.lower(),
    )
    return matches[0].resolve() if matches else None


def _viewer_output_dir(params: Mapping[str, Any], bdf: Path, *, mode_requested: bool, op2: Path | None) -> Path:
    explicit = params.get("out") or params.get("output_dir") or params.get("viewer_dir")
    if explicit is not None and str(explicit).strip():
        return Path(str(explicit)).expanduser()
    suffix = "mode_shape" if mode_requested or op2 is not None else "geometry"
    return bdf.parent / "_ava_viewers" / f"{bdf.stem}_{suffix}"


def _mode_view_intent_requested(params: Mapping[str, Any]) -> bool:
    if _op2_path_from_params(params) is not None:
        return True
    if _initial_mode_from_params(params) is not None:
        return True
    for key in ("view_mode", "mode_requested", "load_modes", "include_modes"):
        if _optional_bool(params.get(key), default=False):
            return True
    return _optional_bool(params.get("animate"), default=False) or _optional_bool(
        params.get("auto_animate"),
        default=False,
    )


def _initial_mode_from_params(params: Mapping[str, Any]) -> str | int | None:
    for key in ("initial_mode", "initial_mode_id", "mode_id", "mode_number", "mode", "mode_index"):
        value = params.get(key)
        if value is not None and str(value).strip() != "":
            return value
    if _optional_bool(params.get("first_mode"), default=False):
        return "first"
    return None


def _optional_bool(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "y", "on"}:
            return True
        if lowered in {"0", "false", "no", "n", "off"}:
            return False
    return default


def _first_param(params: Mapping[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = params.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


registry.register(
    name="fem_explorer_open",
    toolset="fem_explorer",
    schema={
        "name": "fem_explorer_open",
        "description": (
            "Open FEM Explorer in a new desktop window for BDF geometry or explicit OP2 mode visualization. "
            "Use this directly for requests to view or visualize FEM/BDF/NASTRAN models. "
            "Plain visualize/view requests should pass only the BDF; do not load OP2 modes unless the user asks for modes, animation, or supplies an OP2 path."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "bdf": {"type": "string", "description": "BDF/DAT/NAS/FEM path."},
                "bdf_path": {"type": "string", "description": "Alias for bdf."},
                "path": {"type": "string", "description": "Alias for bdf."},
                "model_name": {"type": "string", "description": "Model stem or filename when used with directory/location."},
                "directory": {"type": "string", "description": "Directory containing model_name."},
                "location": {"type": "string", "description": "Alias for directory."},
                "op2_path": {"type": "string", "description": "Optional OP2 path. Only use when the user asks for modes or supplies OP2."},
                "initial_mode": {"type": "string", "description": "Initial mode number/id, or 'first'."},
                "mode_number": {"type": "string", "description": "Alias for initial_mode."},
                "first_mode": {"type": "boolean", "description": "Start on the first mode and discover/load a matching OP2 if needed."},
                "animate": {"type": "boolean", "description": "Animate modes. This implies OP2 mode visualization."},
                "auto_animate": {"type": "boolean", "description": "Start mode animation automatically when OP2 is loaded."},
                "output_dir": {"type": "string", "description": "Optional launch artifact directory."},
                "fem_explorer_root": {"type": "string", "description": "Optional FEM Explorer repo root override."},
            },
            "additionalProperties": True,
        },
    },
    handler=fem_explorer_open_handler,
    requires_env=[],
)
