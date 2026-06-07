"""LLM exposure policy helpers.

The ``minimal`` exposure mode keeps raw tool output local by replacing the
model-visible tool result with a small metadata envelope.  The raw result is
persisted into the active tool environment, registered as protected, and can be
read back only after an explicit privacy approval callback allows it.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

LLM_EXPOSURE_FULL = "full"
LLM_EXPOSURE_MINIMAL = "minimal"
LLM_EXPOSURE_VALUES = frozenset({LLM_EXPOSURE_FULL, LLM_EXPOSURE_MINIMAL})
APPROVED_PROTECTED_READ_FIELD = "_llm_exposure_approved"

_privacy_approval_callback: ContextVar[Callable[[str, dict[str, Any]], str] | None] = ContextVar(
    "_privacy_approval_callback",
    default=None,
)


@dataclass
class ProtectedOutput:
    path: str
    tool_name: str
    tool_call_id: str
    content_length: int
    content_type: str = "text"
    is_error: bool = False
    approved_for_session: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


_protected_outputs: dict[str, ProtectedOutput] = {}
_protected_outputs_lock = threading.RLock()


def normalize_llm_exposure(value: Any) -> str:
    """Return a supported LLM exposure mode, defaulting invalid values to full."""
    if isinstance(value, str):
        normalized = value.strip().lower().replace("-", "_")
        if normalized in {"limited", "limit", "minimal", "minimized"}:
            return LLM_EXPOSURE_MINIMAL
        if normalized in {"full", "default", "normal", ""}:
            return LLM_EXPOSURE_FULL
    return LLM_EXPOSURE_FULL


def is_minimal_exposure(value: Any) -> bool:
    return normalize_llm_exposure(value) == LLM_EXPOSURE_MINIMAL


@contextmanager
def privacy_approval_context(callback: Callable[[str, dict[str, Any]], str] | None):
    """Bind the current thread/task's protected-output approval callback."""
    token = _privacy_approval_callback.set(callback)
    try:
        yield
    finally:
        _privacy_approval_callback.reset(token)


def _path_keys(path: str) -> set[str]:
    keys = {str(path or "")}
    try:
        expanded = os.path.expanduser(str(path or ""))
        keys.add(expanded)
        keys.add(os.path.abspath(expanded))
    except Exception:
        pass
    return {k for k in keys if k}


def register_protected_output(
    path: str,
    *,
    tool_name: str,
    tool_call_id: str,
    content_length: int,
    content_type: str = "text",
    is_error: bool = False,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Record that ``path`` contains raw output withheld from the LLM."""
    if not path:
        return
    protected = ProtectedOutput(
        path=path,
        tool_name=tool_name,
        tool_call_id=tool_call_id,
        content_length=max(0, int(content_length or 0)),
        content_type=content_type or "text",
        is_error=bool(is_error),
        metadata=dict(metadata or {}),
    )
    with _protected_outputs_lock:
        for key in _path_keys(path):
            _protected_outputs[key] = protected


def get_protected_output(path: str) -> ProtectedOutput | None:
    with _protected_outputs_lock:
        for key in _path_keys(path):
            protected = _protected_outputs.get(key)
            if protected is not None:
                return protected
    return None


def clear_protected_outputs() -> None:
    """Test helper: clear process-local protected output registry."""
    with _protected_outputs_lock:
        _protected_outputs.clear()


def approve_or_block_protected_read(path: str) -> tuple[bool, str | None]:
    """Return ``(allowed, error_json)`` for a read of a protected output path."""
    protected = get_protected_output(path)
    if protected is None:
        return True, None
    if protected.approved_for_session:
        return True, None

    callback = _privacy_approval_callback.get()
    metadata = {
        "path": protected.path,
        "tool_name": protected.tool_name,
        "tool_call_id": protected.tool_call_id,
        "content_length": protected.content_length,
        "content_type": protected.content_type,
        "is_error": protected.is_error,
        **protected.metadata,
    }
    if callback is None:
        return False, _protected_read_denied(metadata, reason="no_approval_callback")

    try:
        decision = str(callback(protected.path, metadata) or "").strip().lower()
    except Exception as exc:
        logger.warning("Protected-output approval callback failed: %s", exc)
        return False, _protected_read_denied(metadata, reason="approval_callback_failed")

    if decision in {"approve once", "once", "approve_once", "yes", "y", "allow"}:
        return True, None
    if decision in {"approve for session", "session", "approve_session", "always"}:
        protected.approved_for_session = True
        return True, None

    return False, _protected_read_denied(metadata, reason="denied")


def mark_read_result_approved(result_json: str, path: str) -> str:
    """Annotate a read_file JSON result so minimal mode may expose it."""
    try:
        data = json.loads(result_json)
    except Exception:
        return result_json
    if not isinstance(data, dict) or data.get("error"):
        return result_json
    data[APPROVED_PROTECTED_READ_FIELD] = True
    data["_llm_exposure_source_path"] = path
    return json.dumps(data, ensure_ascii=False)


def result_is_approved_protected_read(tool_name: str, result: Any) -> bool:
    if tool_name != "read_file" or not isinstance(result, str):
        return False
    try:
        data = json.loads(result)
    except Exception:
        return False
    return isinstance(data, dict) and data.get(APPROVED_PROTECTED_READ_FIELD) is True


def protect_tool_result_for_model(
    *,
    tool_name: str,
    result: Any,
    tool_call_id: str,
    env: Any = None,
    duration: float | None = None,
    is_error: bool = False,
) -> Any:
    """Return a model-visible protected-output envelope for ``result``."""
    content_text, content_type = _storage_text(result)
    from tools.tool_result_storage import persist_tool_result_content

    path, storage = persist_tool_result_content(
        content=content_text,
        tool_name=tool_name,
        tool_use_id=tool_call_id,
        env=env,
    )
    if path:
        register_protected_output(
            path,
            tool_name=tool_name,
            tool_call_id=tool_call_id,
            content_length=len(content_text),
            content_type=content_type,
            is_error=is_error,
            metadata={"storage": storage},
        )

    envelope: dict[str, Any] = {
        "status": "protected_output",
        "llm_exposure": LLM_EXPOSURE_MINIMAL,
        "tool_name": tool_name,
        "tool_call_id": tool_call_id,
        "result_status": "error" if is_error else "ok",
        "content_type": content_type,
        "content_length": len(content_text),
        "content_returned": False,
        "message": (
            "Raw tool output was kept local because security.llm_exposure is "
            "minimal. Ask the user before reading saved_output_path; read_file "
            "will enforce that approval gate."
        ),
    }
    if duration is not None:
        envelope["duration_seconds"] = round(max(0.0, float(duration)), 3)
    if path:
        envelope["saved_output_path"] = path
        envelope["storage"] = storage
    else:
        envelope["saved_output_path"] = None
        envelope["storage"] = "unavailable"
        envelope["message"] += " The raw output could not be saved for later read-back."

    envelope.update(_safe_tool_metadata(tool_name, result))
    return json.dumps(envelope, ensure_ascii=False)


def _protected_read_denied(metadata: dict[str, Any], *, reason: str) -> str:
    return json.dumps(
        {
            "error": (
                "Protected tool output was not exposed to the LLM. "
                "The user must explicitly approve reading this saved output."
            ),
            "llm_exposure": LLM_EXPOSURE_MINIMAL,
            "protected_output": True,
            "reason": reason,
            "path": metadata.get("path"),
            "tool_name": metadata.get("tool_name"),
            "tool_call_id": metadata.get("tool_call_id"),
            "content_length": metadata.get("content_length"),
        },
        ensure_ascii=False,
    )


def _storage_text(result: Any) -> tuple[str, str]:
    if isinstance(result, str):
        return result, "text"
    try:
        return json.dumps(result, ensure_ascii=False, default=str), "json"
    except Exception:
        return str(result), "text"


def _safe_tool_metadata(tool_name: str, result: Any) -> dict[str, Any]:
    """Extract non-content status metadata from known structured tool results."""
    if not isinstance(result, str):
        return {}
    try:
        data = json.loads(result)
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}

    metadata: dict[str, Any] = {}
    if tool_name == "terminal":
        for source_key, dest_key in (
            ("exit_code", "exit_code"),
            ("returncode", "exit_code"),
            ("timed_out", "timed_out"),
        ):
            if source_key in data:
                metadata[dest_key] = data[source_key]
        stdout = data.get("stdout")
        stderr = data.get("stderr")
        if isinstance(stdout, str):
            metadata["stdout_length"] = len(stdout)
        if isinstance(stderr, str):
            metadata["stderr_length"] = len(stderr)
    elif tool_name in {"write_file", "patch"}:
        for key in ("success", "bytes_written", "path"):
            if key in data and not isinstance(data.get(key), (dict, list)):
                metadata[key] = data[key]
    elif tool_name == "engineering_tool_run":
        metadata.update(_safe_engineering_tool_metadata(data))
    return metadata


def _safe_engineering_tool_metadata(data: dict[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for source_key, dest_key in (
        ("tool", "engineering_tool"),
        ("status", "engineering_status"),
        ("llm_exposure", "engineering_llm_exposure"),
    ):
        value = data.get(source_key)
        if _is_safe_metadata_scalar(value):
            metadata[dest_key] = value

    summary = data.get("summary")
    if isinstance(summary, dict):
        safe_summary = {
            str(key): value
            for key, value in summary.items()
            if _is_safe_metadata_scalar(value)
        }
        if safe_summary:
            metadata["engineering_summary"] = safe_summary

    artifacts = data.get("artifacts")
    if isinstance(artifacts, list):
        safe_artifacts = [
            item
            for item in artifacts
            if _is_safe_metadata_scalar(item)
        ][:10]
        if safe_artifacts:
            metadata["engineering_artifacts"] = safe_artifacts

    guidance = data.get("agent_guidance")
    if isinstance(guidance, str) and guidance.strip():
        metadata["engineering_agent_guidance"] = guidance.strip()[:1000]
    return metadata


def _is_safe_metadata_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def local_write_fallback(path: str, content: str) -> bool:
    """Write a protected output locally when no tool environment exists."""
    try:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return True
    except Exception as exc:
        logger.warning("Local protected-output write failed for %s: %s", path, exc)
        return False
