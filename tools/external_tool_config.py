"""Configured enterprise executable paths.

This module is intentionally path-explicit. It never searches the host
filesystem for installed applications and never falls back to PATH for the
enterprise tools listed here. Callers either get a configured absolute path or
an actionable message asking the user to provide one.
"""

from __future__ import annotations

import ntpath
import os
import re
import shlex
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


CONFIG_KEY = "external_tools"
WINDOWS_EXECUTABLE_SUFFIXES = {".exe", ".bat", ".cmd", ".com"}


@dataclass(frozen=True)
class ExternalToolDefinition:
    key: str
    display_name: str
    example_windows_path: str
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class ValidationResult:
    tool: str
    path: str
    ok: bool
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ResolvedExternalTool:
    key: str
    display_name: str
    executable_path: str
    working_dir: str
    default_args: tuple[str, ...]
    env: dict[str, str]


class ExternalToolConfigError(ValueError):
    """Raised when a configured enterprise tool cannot be resolved."""


ENTERPRISE_TOOL_DEFINITIONS: dict[str, ExternalToolDefinition] = {
    "nastran": ExternalToolDefinition(
        key="nastran",
        display_name="Nastran",
        example_windows_path=r"C:\Program Files\MSC.Software\MSC_Nastran\bin\nastran.exe",
        aliases=("msc_nastran", "msc-nastran"),
    ),
    "matlab": ExternalToolDefinition(
        key="matlab",
        display_name="MATLAB",
        example_windows_path=r"C:\Program Files\MATLAB\R2025b\bin\matlab.exe",
    ),
    "excel": ExternalToolDefinition(
        key="excel",
        display_name="Excel",
        example_windows_path=r"C:\Program Files\Microsoft Office\root\Office16\EXCEL.EXE",
    ),
    "powerpoint": ExternalToolDefinition(
        key="powerpoint",
        display_name="PowerPoint",
        example_windows_path=r"C:\Program Files\Microsoft Office\root\Office16\POWERPNT.EXE",
        aliases=("powerpnt", "power-point"),
    ),
    "word": ExternalToolDefinition(
        key="word",
        display_name="Word",
        example_windows_path=r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE",
        aliases=("winword",),
    ),
    "vaone": ExternalToolDefinition(
        key="vaone",
        display_name="VA One",
        example_windows_path=r"C:\Program Files\ESI Group\VA One\VAOne.exe",
        aliases=("va-one", "va one"),
    ),
    "wave6": ExternalToolDefinition(
        key="wave6",
        display_name="Wave6",
        example_windows_path=r"C:\Program Files\Dassault Systemes\Wave6\Wave6.exe",
        aliases=("wave-6", "wave 6"),
    ),
    "chrome": ExternalToolDefinition(
        key="chrome",
        display_name="Chrome",
        example_windows_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        aliases=("google-chrome", "chromium"),
    ),
}


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


_ALIASES: dict[str, str] = {}
for _key, _definition in ENTERPRISE_TOOL_DEFINITIONS.items():
    _ALIASES[_slug(_key)] = _key
    _ALIASES[_slug(_definition.display_name)] = _key
    for _alias in _definition.aliases:
        _ALIASES[_slug(_alias)] = _key


def supported_tool_keys() -> tuple[str, ...]:
    return tuple(ENTERPRISE_TOOL_DEFINITIONS.keys())


def normalize_tool_name(name: str) -> str:
    canonical = _ALIASES.get(_slug(str(name or "")))
    if canonical:
        return canonical
    valid = ", ".join(supported_tool_keys())
    raise ExternalToolConfigError(f"Unknown enterprise tool '{name}'. Valid tools: {valid}")


def default_tool_entry() -> dict[str, Any]:
    return {
        "enabled": False,
        "executable_path": "",
        "working_dir": "",
        "default_args": [],
        "env": {},
        "last_validated_at": "",
    }


def default_external_tools_config() -> dict[str, dict[str, Any]]:
    return {key: default_tool_entry() for key in supported_tool_keys()}


def _clean_path(path: str) -> str:
    cleaned = str(path or "").strip()
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {"'", '"'}:
        cleaned = cleaned[1:-1].strip()
    cleaned = ntpath.expandvars(os.path.expandvars(os.path.expanduser(cleaned)))
    return cleaned


def _is_windows_absolute(path: str) -> bool:
    return ntpath.isabs(path)


def _is_absolute(path: str) -> bool:
    return os.path.isabs(path) or _is_windows_absolute(path)


def _looks_windows_path(path: str) -> bool:
    return _is_windows_absolute(path) or bool(re.match(r"^[A-Za-z]:[\\/]", path))


def _path_suffix(path: str) -> str:
    if _looks_windows_path(path):
        return ntpath.splitext(path)[1].lower()
    return Path(path).suffix.lower()


def validate_executable_path(path: str, *, require_exists: bool = True) -> ValidationResult:
    cleaned = _clean_path(path)
    errors: list[str] = []
    warnings: list[str] = []

    if not cleaned:
        errors.append("Path is required.")
    elif not _is_absolute(cleaned):
        errors.append("Path must be absolute. Ava will not search the PC for this executable.")

    if cleaned and _looks_windows_path(cleaned):
        suffix = _path_suffix(cleaned)
        if suffix not in WINDOWS_EXECUTABLE_SUFFIXES:
            allowed = ", ".join(sorted(WINDOWS_EXECUTABLE_SUFFIXES))
            errors.append(f"Windows tool paths must end in one of: {allowed}.")

    if require_exists and cleaned:
        if not os.path.isfile(cleaned):
            errors.append(f"Path does not exist or is not a file: {cleaned}")
        elif not _looks_windows_path(cleaned) and not os.access(cleaned, os.X_OK):
            errors.append(f"Path is not executable: {cleaned}")

    return ValidationResult(
        tool="",
        path=cleaned,
        ok=not errors,
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


def _coerce_entry(raw: Any) -> dict[str, Any]:
    entry = default_tool_entry()
    if isinstance(raw, str):
        entry["enabled"] = bool(raw.strip())
        entry["executable_path"] = raw.strip()
        return entry
    if not isinstance(raw, dict):
        return entry

    if "enabled" in raw:
        entry["enabled"] = bool(raw.get("enabled"))
    if "executable_path" in raw:
        entry["executable_path"] = str(raw.get("executable_path") or "").strip()
    if "working_dir" in raw:
        entry["working_dir"] = str(raw.get("working_dir") or "").strip()
    if isinstance(raw.get("default_args"), list):
        entry["default_args"] = [str(arg) for arg in raw.get("default_args") or []]
    if isinstance(raw.get("env"), dict):
        entry["env"] = {str(k): str(v) for k, v in (raw.get("env") or {}).items()}
    if "last_validated_at" in raw:
        entry["last_validated_at"] = str(raw.get("last_validated_at") or "")
    return entry


def get_external_tools_config(config: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    raw = (config or {}).get(CONFIG_KEY)
    merged = default_external_tools_config()
    if not isinstance(raw, dict):
        return merged
    for raw_key, raw_entry in raw.items():
        try:
            key = normalize_tool_name(str(raw_key))
        except ExternalToolConfigError:
            continue
        merged[key] = _coerce_entry(raw_entry)
    return merged


def _ensure_external_tools_section(config: dict[str, Any]) -> dict[str, Any]:
    section = config.setdefault(CONFIG_KEY, {})
    if not isinstance(section, dict):
        section = {}
        config[CONFIG_KEY] = section
    return section


def set_tool_path(
    config: dict[str, Any],
    tool_name: str,
    path: str,
    *,
    require_exists: bool = True,
) -> str:
    key = normalize_tool_name(tool_name)
    validation = validate_executable_path(path, require_exists=require_exists)
    if not validation.ok:
        raise ExternalToolConfigError("; ".join(validation.errors))

    section = _ensure_external_tools_section(config)
    entry = _coerce_entry(section.get(key))
    entry["enabled"] = True
    entry["executable_path"] = validation.path
    entry["last_validated_at"] = datetime.now(timezone.utc).isoformat()
    section[key] = entry
    return key


def remove_tool_path(config: dict[str, Any], tool_name: str) -> str:
    key = normalize_tool_name(tool_name)
    section = _ensure_external_tools_section(config)
    section[key] = default_tool_entry()
    return key


def validate_tool_entry(
    config: dict[str, Any] | None,
    tool_name: str,
    *,
    require_exists: bool = True,
) -> ValidationResult:
    key = normalize_tool_name(tool_name)
    entry = get_external_tools_config(config).get(key, default_tool_entry())
    path = str(entry.get("executable_path") or "")
    validation = validate_executable_path(path, require_exists=require_exists)

    errors = list(validation.errors)
    warnings = list(validation.warnings)
    if not entry.get("enabled") and path:
        warnings.append("Tool has a path but is disabled.")
    if not path:
        definition = ENTERPRISE_TOOL_DEFINITIONS[key]
        errors = [
            (
                f"{definition.display_name} is not configured. Provide an exact path, "
                f"for example: /pc-tool-config set {key} {definition.example_windows_path}"
            )
        ]

    return ValidationResult(
        tool=key,
        path=validation.path,
        ok=not errors,
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


def iter_tool_statuses(config: dict[str, Any] | None) -> Iterable[tuple[str, dict[str, Any], ValidationResult]]:
    merged = get_external_tools_config(config)
    for key in supported_tool_keys():
        yield key, merged[key], validate_tool_entry(config, key)


def missing_tool_message(tool_name: str) -> str:
    key = normalize_tool_name(tool_name)
    definition = ENTERPRISE_TOOL_DEFINITIONS[key]
    return (
        f"{definition.display_name} is not configured. Ava will not search the PC "
        f"for executables. Provide the exact path with: /pc-tool-config set {key} "
        f"{definition.example_windows_path}"
    )


def resolve_external_tool(
    tool_name: str,
    *,
    config: dict[str, Any] | None = None,
    require_enabled: bool = True,
) -> ResolvedExternalTool:
    if config is None:
        from hermes_cli.config import load_config

        config = load_config()

    key = normalize_tool_name(tool_name)
    entry = get_external_tools_config(config).get(key, default_tool_entry())
    definition = ENTERPRISE_TOOL_DEFINITIONS[key]

    if require_enabled and not entry.get("enabled"):
        raise ExternalToolConfigError(missing_tool_message(key))

    validation = validate_tool_entry(config, key)
    if not validation.ok:
        raise ExternalToolConfigError("; ".join(validation.errors))

    working_dir = _clean_path(str(entry.get("working_dir") or ""))
    if working_dir and not _is_absolute(working_dir):
        raise ExternalToolConfigError(f"Working directory for {key} must be absolute.")

    return ResolvedExternalTool(
        key=key,
        display_name=definition.display_name,
        executable_path=validation.path,
        working_dir=working_dir,
        default_args=tuple(str(arg) for arg in entry.get("default_args") or []),
        env={str(k): str(v) for k, v in (entry.get("env") or {}).items()},
    )


def build_external_tool_command(
    tool_name: str,
    args: Iterable[str] | None = None,
    *,
    config: dict[str, Any] | None = None,
) -> str:
    resolved = resolve_external_tool(tool_name, config=config)
    parts = [resolved.executable_path, *resolved.default_args, *(str(arg) for arg in (args or []))]
    if os.name == "nt":
        return subprocess.list2cmdline(parts)
    return " ".join(shlex.quote(part) for part in parts)


def run_external_tool(
    tool_name: str,
    args: Iterable[str] | None = None,
    *,
    config: dict[str, Any] | None = None,
    timeout: int | None = None,
    background: bool = False,
    workdir: str | None = None,
):
    """Run a configured external tool through the terminal tool.

    The terminal tool owns dangerous-command approval and process tracking, so
    integrations should prefer this helper over direct subprocess calls.
    """
    resolved = resolve_external_tool(tool_name, config=config)
    command = build_external_tool_command(tool_name, args=args, config=config)

    from tools.terminal_tool import terminal_tool

    return terminal_tool(
        command=command,
        timeout=timeout,
        background=background,
        workdir=workdir or resolved.working_dir or None,
    )
