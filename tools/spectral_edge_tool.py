"""Standalone SpectralEdge tools exposed to AVA."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping

from tools.registry import registry, tool_error, tool_result


DEFAULT_SPECTRAL_EDGE_ROOT = Path("/Users/stephenwells/Documents/DevOps/spectral-edge")
DEFAULT_SPECTRAL_EDGE_DATA_ROOT = DEFAULT_SPECTRAL_EDGE_ROOT / "data"
DATA_SUFFIXES = (".h5", ".hdf5", ".csv", ".tsv", ".txt", ".dxd", ".dxz", ".sto", ".zip")
SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".venv",
    "venv",
    "node_modules",
    "logs",
}


def spectral_edge_find_data_handler(args, **kwargs) -> str:
    """Find likely SpectralEdge data files under configured roots."""
    try:
        params = _normalize_args(args)
        label = str(params.get("label") or params.get("name") or params.get("flight") or "").strip()
        explicit_path = _first_param(params, ("file_path", "path", "data_path", "file"))
        roots = _data_roots(params)
        max_matches = int(_coerce_float(params.get("max_matches"), 20.0))
        suffixes = _suffixes(params.get("extensions") or params.get("suffixes"))

        if explicit_path:
            candidate = Path(explicit_path).expanduser().resolve()
            if candidate.is_file():
                match = _file_match(candidate, label=label, roots=roots, suffixes=suffixes)
                return tool_result(_find_result(label, roots, [match] if match else []))
            if candidate.is_dir():
                roots = [candidate]
            else:
                raise FileNotFoundError(candidate)

        if not label and not explicit_path:
            raise ValueError("Expected a data label such as AR02, or a file_path/path.")

        matches: list[dict[str, Any]] = []
        for root in roots:
            matches.extend(_search_root(root, label=label, suffixes=suffixes, max_matches=max_matches))
            if len(matches) >= max_matches:
                break

        matches = sorted(matches, key=lambda item: (-int(item["score"]), item["path"]))[:max_matches]
        return tool_result(_find_result(label, roots, matches))
    except Exception as exc:
        return tool_error(str(exc))


def spectral_edge_list_channels_handler(args, **kwargs) -> str:
    """List HDF5 flight channels and identify likely accelerometer channels."""
    try:
        params = _normalize_args(args)
        file_path = _required_file_path(params)
        accelerometer_only = _coerce_bool(params.get("accelerometer_only"), default=False)
        channel_query = str(params.get("channel_query") or params.get("query") or "").strip()
        flights = _scan_hdf5_channels(file_path, spectral_edge_root=_spectral_edge_root(params))

        all_channels: list[dict[str, Any]] = []
        for flight in flights:
            for channel in flight["channels"]:
                keep = True
                if accelerometer_only and not channel["is_accelerometer"]:
                    keep = False
                if channel_query and channel_query.lower() not in json.dumps(channel, default=str).lower():
                    keep = False
                if keep:
                    all_channels.append({**channel, "flight_key": flight["flight_key"]})

        result = {
            "tool": "spectral_edge_list_channels",
            "status": "ok",
            "llm_exposure": "summary_only",
            "summary": {
                "file_path": str(file_path),
                "flight_count": len(flights),
                "total_channel_count": sum(len(flight["channels"]) for flight in flights),
                "matched_channel_count": len(all_channels),
                "accelerometer_only": accelerometer_only,
                "channel_query": channel_query or None,
                "channels": all_channels[:100],
            },
            "agent_guidance": (
                "If exactly one suitable channel is returned, open it with spectral_edge_open_spectrogram. "
                "If multiple accelerometer channels are returned, ask the user which channel to use before opening the viewer."
            ),
        }
        return tool_result(result)
    except Exception as exc:
        return tool_error(str(exc))


def spectral_edge_open_spectrogram_handler(args, **kwargs) -> str:
    """Launch SpectralEdge segmented spectrogram viewer with a preselected channel."""
    try:
        params = _normalize_args(args)
        file_path = _required_file_path(params)
        flight_key = str(params.get("flight_key") or params.get("flight") or "").strip()
        channel_key = str(params.get("channel_key") or params.get("channel") or "").strip()
        if not flight_key or not channel_key:
            raise ValueError("Expected flight_key and channel_key. Use spectral_edge_list_channels first if needed.")

        root = _spectral_edge_root(params)
        settings = _launch_settings(params)
        generate = _coerce_bool(params.get("generate"), default=True)
        output_dir = _output_dir(params, file_path)
        output_dir.mkdir(parents=True, exist_ok=True)

        manifest = {
            "tool": "segmented_spectrogram",
            "file_path": str(file_path),
            "flight_key": flight_key,
            "channel_key": channel_key,
            "settings": settings,
            "generate": generate,
        }
        manifest_path = output_dir / "spectral_edge_launch.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        stdout_path = output_dir / "spectral_edge_stdout.log"
        stderr_path = output_dir / "spectral_edge_stderr.log"
        process = _launch_spectral_edge(root, manifest_path, stdout_path, stderr_path)

        result = {
            "tool": "spectral_edge_open_spectrogram",
            "status": "ok",
            "llm_exposure": "summary_only",
            "summary": {
                "viewer_backend": "spectral_edge",
                "window": "launched",
                "spectral_edge_root": str(root),
                "file_path": str(file_path),
                "flight_key": flight_key,
                "channel_key": channel_key,
                "manifest_path": str(manifest_path),
                "stdout_log": str(stdout_path),
                "stderr_log": str(stderr_path),
                "process_id": process.pid,
                "generate": generate,
                "settings": settings,
            },
            "artifacts": [str(manifest_path), str(stdout_path), str(stderr_path)],
            "agent_guidance": (
                "SpectralEdge has already been launched in a desktop window. "
                "Do not call terminal/open/curl/pgrep after this successful viewer result. "
                "Reply with the data path, flight, channel, and manifest path."
            ),
        }
        return tool_result(result)
    except Exception as exc:
        return tool_error(str(exc))


def _normalize_args(args: Mapping[str, Any] | None) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if not isinstance(args, Mapping):
        return params
    raw_params = args.get("params")
    if isinstance(raw_params, Mapping):
        params.update(raw_params)
    for key, value in args.items():
        if key != "params" and key not in params:
            params[key] = value
    return params


def _load_config_value(*keys: str, default: Any = None) -> Any:
    try:
        from hermes_cli.config import cfg_get, load_config

        return cfg_get(load_config(), *keys, default=default)
    except Exception:
        return default


def _spectral_edge_root(params: Mapping[str, Any] | None = None) -> Path:
    explicit = _first_param(params or {}, ("spectral_edge_root", "root"))
    configured = _load_config_value("spectral_edge", "root", default=None)
    raw = explicit or os.environ.get("SPECTRAL_EDGE_ROOT") or configured or str(DEFAULT_SPECTRAL_EDGE_ROOT)
    root = Path(str(raw)).expanduser().resolve()
    if not (root / "spectral_edge" / "main.py").exists():
        raise FileNotFoundError(f"SpectralEdge root is not valid: {root}")
    return root


def _data_roots(params: Mapping[str, Any]) -> list[Path]:
    raw_roots = params.get("data_roots")
    if raw_roots is None:
        raw_roots = _load_config_value("spectral_edge", "data_roots", default=None)
    if raw_roots is None:
        raw_roots = [str(DEFAULT_SPECTRAL_EDGE_DATA_ROOT)]
    if isinstance(raw_roots, (str, os.PathLike)):
        raw_values = [raw_roots]
    else:
        raw_values = list(raw_roots)

    roots: list[Path] = []
    for raw in raw_values:
        path = Path(str(raw)).expanduser().resolve()
        if path.exists() and path.is_dir() and path not in roots:
            roots.append(path)
    if not roots:
        raise FileNotFoundError("No SpectralEdge data roots exist. Configure spectral_edge.data_roots.")
    return roots


def _required_file_path(params: Mapping[str, Any]) -> Path:
    raw = _first_param(params, ("file_path", "path", "data_path", "file"))
    if raw:
        path = Path(raw).expanduser().resolve()
        if path.exists() and path.is_file():
            return path
        raise FileNotFoundError(path)

    label = str(params.get("label") or params.get("name") or params.get("flight") or "").strip()
    if not label:
        raise ValueError("Expected file_path/path or a data label.")
    roots = _data_roots(params)
    matches: list[dict[str, Any]] = []
    for root in roots:
        matches.extend(_search_root(root, label=label, suffixes=DATA_SUFFIXES, max_matches=2))
    if len(matches) == 1:
        return Path(matches[0]["path"])
    if not matches:
        raise FileNotFoundError(f"No SpectralEdge data file found for label '{label}'.")
    raise ValueError(f"Multiple SpectralEdge data files match '{label}'. Use spectral_edge_find_data first.")


def _suffixes(raw: Any) -> tuple[str, ...]:
    if raw is None:
        return DATA_SUFFIXES
    if isinstance(raw, str):
        values = [item.strip() for item in raw.split(",")]
    else:
        values = [str(item).strip() for item in raw]
    suffixes = tuple(item if item.startswith(".") else f".{item}" for item in values if item)
    return suffixes or DATA_SUFFIXES


def _search_root(root: Path, *, label: str, suffixes: Iterable[str], max_matches: int) -> list[dict[str, Any]]:
    label_lower = label.lower()
    suffix_set = {suffix.lower() for suffix in suffixes}
    matches: list[dict[str, Any]] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in SKIP_DIRS and not name.startswith(".")]
        for filename in filenames:
            path = Path(dirpath) / filename
            if path.suffix.lower() not in suffix_set:
                continue
            if label_lower and label_lower not in filename.lower() and label_lower not in str(path).lower():
                continue
            match = _file_match(path, label=label, roots=[root], suffixes=suffix_set)
            if match:
                matches.append(match)
                if len(matches) >= max_matches:
                    return matches
    return matches


def _file_match(path: Path, *, label: str, roots: Iterable[Path], suffixes: Iterable[str]) -> dict[str, Any] | None:
    if path.suffix.lower() not in {suffix.lower() for suffix in suffixes}:
        return None
    label_lower = label.lower()
    stem_lower = path.stem.lower()
    path_lower = str(path).lower()
    score = 10
    if label_lower:
        if stem_lower == label_lower:
            score += 100
        elif label_lower in stem_lower:
            score += 70
        elif label_lower in path_lower:
            score += 35
    if path.suffix.lower() in {".h5", ".hdf5"}:
        score += 30
    try:
        size_bytes = path.stat().st_size
    except OSError:
        size_bytes = None

    root_value = None
    for root in roots:
        try:
            path.relative_to(root)
            root_value = str(root)
            break
        except ValueError:
            continue
    return {
        "path": str(path.resolve()),
        "name": path.name,
        "stem": path.stem,
        "extension": path.suffix.lower(),
        "size_bytes": size_bytes,
        "root": root_value,
        "score": score,
    }


def _find_result(label: str, roots: Iterable[Path], matches: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "tool": "spectral_edge_find_data",
        "status": "ok",
        "llm_exposure": "summary_only",
        "summary": {
            "label": label or None,
            "data_roots": [str(root) for root in roots],
            "match_count": len(matches),
            "matches": matches,
        },
        "agent_guidance": (
            "Use spectral_edge_list_channels on the selected HDF5 file before opening a spectrogram. "
            "If multiple matches are returned, ask the user which data file to use."
        ),
    }


def _scan_hdf5_channels(file_path: Path, *, spectral_edge_root: Path | None = None) -> list[dict[str, Any]]:
    try:
        import h5py
    except Exception:
        if spectral_edge_root is None:
            spectral_edge_root = _spectral_edge_root({})
        return _scan_hdf5_channels_external(file_path, spectral_edge_root)

    flights: list[dict[str, Any]] = []
    with h5py.File(file_path, "r") as handle:
        for flight_key, flight_group in handle.items():
            if not isinstance(flight_group, h5py.Group) or "channels" not in flight_group:
                continue
            channels_group = flight_group["channels"]
            if not isinstance(channels_group, h5py.Group):
                continue
            channels = []
            for channel_key, channel_group in channels_group.items():
                if not isinstance(channel_group, h5py.Group) or "data" not in channel_group:
                    continue
                attrs = {str(key): _json_scalar(value) for key, value in dict(channel_group.attrs).items()}
                sample_count = int(len(channel_group["data"]))
                sample_rate = _coerce_float(attrs.get("sample_rate"), 0.0)
                duration_seconds = sample_count / sample_rate if sample_rate > 0 else None
                channel = {
                    "channel_key": str(channel_key),
                    "full_path": f"{flight_key}/channels/{channel_key}",
                    "sample_rate_hz": sample_rate or None,
                    "sample_count": sample_count,
                    "duration_seconds": duration_seconds,
                    "units": attrs.get("units") or "",
                    "description": attrs.get("description") or "",
                    "sensor_id": attrs.get("sensor_id") or "",
                    "location": attrs.get("location") or "",
                    "is_accelerometer": _looks_like_accelerometer(str(channel_key), attrs),
                }
                channels.append(channel)
            flights.append({"flight_key": str(flight_key), "channels": channels})
    return flights


def _scan_hdf5_channels_external(file_path: Path, root: Path) -> list[dict[str, Any]]:
    """Scan HDF5 channels with SpectralEdge's Python when Ava lacks h5py."""
    script = r"""
import json
import sys

import h5py


def scalar(value):
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def as_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def looks_like_accelerometer(channel_key, attrs):
    units = str(attrs.get("units") or "").strip().lower()
    text = " ".join([
        channel_key,
        str(attrs.get("description") or ""),
        str(attrs.get("sensor_id") or ""),
        str(attrs.get("location") or ""),
    ]).lower()
    if units in {"g", "gs", "m/s^2", "m/s2", "m/sec^2", "m/sec2"}:
        return True
    return any(token in text for token in ("accelerometer", "accel", "acc_", "acc-", "acc "))


flights = []
with h5py.File(sys.argv[1], "r") as handle:
    for flight_key, flight_group in handle.items():
        if not isinstance(flight_group, h5py.Group) or "channels" not in flight_group:
            continue
        channels_group = flight_group["channels"]
        if not isinstance(channels_group, h5py.Group):
            continue
        channels = []
        for channel_key, channel_group in channels_group.items():
            if not isinstance(channel_group, h5py.Group) or "data" not in channel_group:
                continue
            attrs = {str(key): scalar(value) for key, value in dict(channel_group.attrs).items()}
            sample_count = int(len(channel_group["data"]))
            sample_rate = as_float(attrs.get("sample_rate"), 0.0)
            duration_seconds = sample_count / sample_rate if sample_rate > 0 else None
            channels.append({
                "channel_key": str(channel_key),
                "full_path": f"{flight_key}/channels/{channel_key}",
                "sample_rate_hz": sample_rate or None,
                "sample_count": sample_count,
                "duration_seconds": duration_seconds,
                "units": attrs.get("units") or "",
                "description": attrs.get("description") or "",
                "sensor_id": attrs.get("sensor_id") or "",
                "location": attrs.get("location") or "",
                "is_accelerometer": looks_like_accelerometer(str(channel_key), attrs),
            })
        flights.append({"flight_key": str(flight_key), "channels": channels})

print(json.dumps(flights))
"""
    process = subprocess.run(
        [str(_spectral_edge_python(root)), "-c", script, str(file_path)],
        cwd=str(root),
        text=True,
        capture_output=True,
        check=False,
    )
    if process.returncode != 0:
        raise RuntimeError(
            "SpectralEdge HDF5 channel scan failed: "
            f"{(process.stderr or process.stdout or '').strip()}"
        )
    return json.loads(process.stdout or "[]")


def _looks_like_accelerometer(channel_key: str, attrs: Mapping[str, Any]) -> bool:
    units = str(attrs.get("units") or "").strip().lower()
    text = " ".join(
        [
            channel_key,
            str(attrs.get("description") or ""),
            str(attrs.get("sensor_id") or ""),
            str(attrs.get("location") or ""),
        ]
    ).lower()
    if units in {"g", "gs", "m/s^2", "m/s2", "m/sec^2", "m/sec2"}:
        return True
    return any(token in text for token in ("accelerometer", "accel", "acc_", "acc-", "acc "))


def _launch_settings(params: Mapping[str, Any]) -> dict[str, Any]:
    raw_settings = params.get("settings")
    settings = dict(raw_settings) if isinstance(raw_settings, Mapping) else {}
    passthrough = {
        "segment_duration_seconds",
        "segment_overlap_percent",
        "time_start_seconds",
        "time_end_seconds",
        "window",
        "df_hz",
        "fft_size",
        "efficient_fft",
        "spectrogram_overlap_percent",
        "freq_min_hz",
        "freq_max_hz",
        "filter_enabled",
        "filter_type",
        "low_cutoff_hz",
        "high_cutoff_hz",
        "remove_mean",
        "show_colorbar",
        "colormap",
        "snr_db",
        "db_reference_mode",
        "db_reference_value",
    }
    for key in passthrough:
        if key in params and params[key] is not None and key not in settings:
            settings[key] = params[key]
    return settings


def _output_dir(params: Mapping[str, Any], file_path: Path) -> Path:
    raw = _first_param(params, ("output_dir", "out", "viewer_dir", "artifact_dir"))
    if raw:
        return Path(raw).expanduser().resolve()
    return file_path.parent / "_ava_spectral_edge" / f"{file_path.stem}_spectrogram"


def _launch_spectral_edge(root: Path, manifest_path: Path, stdout_path: Path, stderr_path: Path) -> subprocess.Popen:
    python_exe = _spectral_edge_python(root)
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{root}{os.pathsep}{env.get('PYTHONPATH', '')}" if env.get("PYTHONPATH") else str(root)
    stdout_handle = stdout_path.open("a", encoding="utf-8")
    stderr_handle = stderr_path.open("a", encoding="utf-8")
    try:
        return subprocess.Popen(
            [str(python_exe), "-m", "spectral_edge.main", "--launch-manifest", str(manifest_path)],
            cwd=str(root),
            env=env,
            stdout=stdout_handle,
            stderr=stderr_handle,
            start_new_session=True,
        )
    finally:
        stdout_handle.close()
        stderr_handle.close()


def _spectral_edge_python(root: Path) -> Path:
    for candidate in (
        root / "venv" / "bin" / "python",
        root / ".venv" / "bin" / "python",
    ):
        if candidate.exists():
            return candidate
    return Path(sys.executable)


def _json_scalar(value: Any) -> Any:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _first_param(params: Mapping[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = params.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _coerce_bool(value: Any, *, default: bool = False) -> bool:
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


def _coerce_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def check_spectral_edge_requirements() -> bool:
    try:
        _spectral_edge_root({})
        return True
    except Exception:
        return False


registry.register(
    name="spectral_edge_find_data",
    toolset="spectral_edge",
    schema={
        "name": "spectral_edge_find_data",
        "description": (
            "Find SpectralEdge data files by label/path, such as AR02, under configured data roots. "
            "Use this first when the user asks to view a spectrogram from a named data set."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "label": {"type": "string", "description": "Flight/data label to search for, e.g. AR02."},
                "file_path": {"type": "string", "description": "Optional exact data file path."},
                "data_roots": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional directories to search instead of configured roots.",
                },
                "extensions": {"type": "string", "description": "Optional comma-separated extension filter."},
                "max_matches": {"type": "integer", "description": "Maximum matches to return."},
            },
            "additionalProperties": True,
        },
    },
    handler=spectral_edge_find_data_handler,
    check_fn=check_spectral_edge_requirements,
    requires_env=[],
)


registry.register(
    name="spectral_edge_list_channels",
    toolset="spectral_edge",
    schema={
        "name": "spectral_edge_list_channels",
        "description": (
            "List channels in a SpectralEdge HDF5 data file. "
            "Use accelerometer_only=true when the user asks to choose an accelerometer channel."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "HDF5 data file path."},
                "accelerometer_only": {"type": "boolean", "description": "Return only likely accelerometer channels."},
                "channel_query": {"type": "string", "description": "Optional channel-name/metadata filter."},
            },
            "required": ["file_path"],
            "additionalProperties": True,
        },
    },
    handler=spectral_edge_list_channels_handler,
    check_fn=check_spectral_edge_requirements,
    requires_env=[],
)


registry.register(
    name="spectral_edge_open_spectrogram",
    toolset="spectral_edge",
    schema={
        "name": "spectral_edge_open_spectrogram",
        "description": (
            "Open SpectralEdge in a desktop window with the segmented spectrogram viewer preloaded on a selected HDF5 flight/channel. "
            "Use only after a file, flight_key, and channel_key are known."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "HDF5 data file path."},
                "flight_key": {"type": "string", "description": "HDF5 flight group key."},
                "channel_key": {"type": "string", "description": "HDF5 channel key."},
                "settings": {"type": "object", "description": "Optional viewer settings such as time_start_seconds, df_hz, fft_size, colormap."},
                "generate": {"type": "boolean", "description": "Generate the first spectrogram immediately after opening. Defaults true."},
                "output_dir": {"type": "string", "description": "Optional launch artifact directory."},
                "spectral_edge_root": {"type": "string", "description": "Optional SpectralEdge repo root override."},
            },
            "required": ["file_path", "flight_key", "channel_key"],
            "additionalProperties": True,
        },
    },
    handler=spectral_edge_open_spectrogram_handler,
    check_fn=check_spectral_edge_requirements,
    requires_env=[],
)
