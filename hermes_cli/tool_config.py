"""CLI and gateway formatting for enterprise tool path configuration."""

from __future__ import annotations

from argparse import Namespace
from typing import Any

from hermes_cli.cli_output import (
    print_error,
    print_info,
    print_success,
    prompt,
)
from hermes_cli.colors import Colors, color
from hermes_cli.config import load_config, save_config
from tools.external_tool_config import (
    ENTERPRISE_TOOL_DEFINITIONS,
    ExternalToolConfigError,
    iter_tool_statuses,
    remove_tool_path,
    set_tool_path,
    supported_tool_keys,
    validate_tool_entry,
)


USAGE = (
    "Usage:\n"
    "  /tool_config list\n"
    "  /tool_config set <tool> <absolute executable path>\n"
    "  /tool_config remove <tool>\n"
    "  /tool_config validate [tool]\n\n"
    "Tools: "
    + ", ".join(supported_tool_keys())
)


def _status_label(entry: dict[str, Any], validation_ok: bool) -> str:
    if validation_ok and entry.get("enabled"):
        return "configured"
    if validation_ok and not entry.get("enabled"):
        return "disabled"
    if entry.get("executable_path"):
        return "invalid"
    return "missing"


def format_tool_config_list(config: dict[str, Any]) -> str:
    lines = [
        "Enterprise tool configuration",
        "Ava uses only these explicit paths and will not search the PC.",
        "",
    ]
    for key, entry, validation in iter_tool_statuses(config):
        definition = ENTERPRISE_TOOL_DEFINITIONS[key]
        status = _status_label(entry, validation.ok)
        path = str(entry.get("executable_path") or "")
        if path:
            lines.append(f"{key:11} {status:10} {path}")
        else:
            lines.append(f"{key:11} {status:10} example: {definition.example_windows_path}")
    lines.extend(["", USAGE])
    return "\n".join(lines)


def _format_validation(validation) -> list[str]:
    definition = ENTERPRISE_TOOL_DEFINITIONS[validation.tool]
    if validation.ok:
        path = validation.path or "(not configured)"
        return [f"{validation.tool}: OK - {definition.display_name} -> {path}"]
    lines = [f"{validation.tool}: INVALID - {definition.display_name}"]
    for err in validation.errors:
        lines.append(f"  - {err}")
    for warning in validation.warnings:
        lines.append(f"  - Warning: {warning}")
    return lines


def format_tool_validation(config: dict[str, Any], tool_name: str | None = None) -> str:
    keys = [tool_name] if tool_name else list(supported_tool_keys())
    lines: list[str] = []
    for key in keys:
        validation = validate_tool_entry(config, key)
        lines.extend(_format_validation(validation))
    return "\n".join(lines)


def _parse_gateway_args(raw_args: str) -> tuple[str, str | None, str | None]:
    text = (raw_args or "").strip()
    if not text:
        return ("list", None, None)
    parts = text.split(maxsplit=2)
    action = parts[0].lower().replace("-", "_")
    tool = parts[1] if len(parts) >= 2 else None
    value = parts[2] if len(parts) >= 3 else None
    return (action, tool, value)


def handle_tool_config_text(raw_args: str) -> str:
    action, tool, value = _parse_gateway_args(raw_args)
    if action in {"help", "h", "?"}:
        return USAGE

    config = load_config()

    try:
        if action == "list":
            return format_tool_config_list(config)

        if action == "set":
            if not tool or not value:
                return "Missing tool or path.\n\n" + USAGE
            key = set_tool_path(config, tool, value)
            save_config(config)
            path = config["external_tools"][key]["executable_path"]
            display = ENTERPRISE_TOOL_DEFINITIONS[key].display_name
            return f"Configured {display}: {path}"

        if action in {"remove", "unset", "delete"}:
            if not tool:
                return "Missing tool name.\n\n" + USAGE
            key = remove_tool_path(config, tool)
            save_config(config)
            return f"Removed configuration for {ENTERPRISE_TOOL_DEFINITIONS[key].display_name}."

        if action == "validate":
            return format_tool_validation(config, tool)

        return f"Unknown tool_config action: {action}\n\n{USAGE}"
    except ExternalToolConfigError as exc:
        return f"Tool configuration error: {exc}"


def _interactive_setup() -> None:
    config = load_config()
    changed = False

    print_info("Configure enterprise tool executable paths.")
    print_info("Ava will not search the PC. Leave a value blank to skip it.")
    print()

    for key in supported_tool_keys():
        definition = ENTERPRISE_TOOL_DEFINITIONS[key]
        current = (
            config.get("external_tools", {})
            .get(key, {})
            .get("executable_path", "")
        )
        default_text = current or ""
        value = prompt(
            f"{definition.display_name} path",
            default=default_text,
        ).strip()
        if not value:
            continue
        try:
            set_tool_path(config, key, value)
        except ExternalToolConfigError as exc:
            print_error(f"{definition.display_name}: {exc}")
            print_info(f"Example: {definition.example_windows_path}")
            continue
        changed = True

    if changed:
        save_config(config)
        print_success("Enterprise tool configuration saved.")
    else:
        print_info("No changes.")


def tool_config_command(args: Namespace | None = None) -> None:
    action = getattr(args, "tool_config_action", None) if args is not None else None

    if action is None:
        _interactive_setup()
        return

    config = load_config()
    try:
        if action == "list":
            print(format_tool_config_list(config))
            return

        if action == "set":
            tool = getattr(args, "tool", "")
            path_parts = getattr(args, "path", []) or []
            path = " ".join(str(part) for part in path_parts).strip()
            key = set_tool_path(config, tool, path)
            save_config(config)
            display = ENTERPRISE_TOOL_DEFINITIONS[key].display_name
            print_success(f"Configured {display}: {config['external_tools'][key]['executable_path']}")
            return

        if action == "remove":
            key = remove_tool_path(config, getattr(args, "tool", ""))
            save_config(config)
            print_success(f"Removed configuration for {ENTERPRISE_TOOL_DEFINITIONS[key].display_name}.")
            return

        if action == "validate":
            print(format_tool_validation(config, getattr(args, "tool", None)))
            return

        print_error(f"Unknown action: {action}")
    except ExternalToolConfigError as exc:
        print_error(str(exc))
        raise SystemExit(2) from exc


def colored_tool_config_summary(config: dict[str, Any]) -> str:
    """Short status summary for future setup/status surfaces."""
    configured = []
    missing = []
    for key, entry, validation in iter_tool_statuses(config):
        if validation.ok and entry.get("enabled"):
            configured.append(key)
        else:
            missing.append(key)
    return (
        color(f"{len(configured)} configured", Colors.GREEN)
        + color(f", {len(missing)} missing", Colors.DIM)
    )

