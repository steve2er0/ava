"""Approved engineering tools exposed to the AVA agent."""

from __future__ import annotations

from ava_runtime.engineering_tools import list_approved_tools, run_engineering_tool
from tools.registry import registry, tool_error, tool_result


def engineering_tool_catalog_handler(args, **kwargs) -> str:
    """Return approved engineering tool metadata."""

    return tool_result({"tools": list_approved_tools()})


def engineering_tool_run_handler(args, **kwargs) -> str:
    """Run one approved engineering tool."""

    try:
        tool_name = str(args.get("tool_name", ""))
        params = args.get("params") or {}
        return tool_result(run_engineering_tool(tool_name, params))
    except Exception as exc:
        return tool_error(str(exc))


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
        "description": "Run one approved AVA engineering tool. Inputs are file paths or compact config values; raw engineering files are processed locally and only summaries/artifact paths are returned by default.",
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
