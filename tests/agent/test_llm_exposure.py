import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from agent.llm_exposure import (
    APPROVED_PROTECTED_READ_FIELD,
    clear_protected_outputs,
    protect_tool_result_for_model,
    register_protected_output,
)
from model_tools import handle_function_call
from run_agent import AIAgent


@pytest.fixture(autouse=True)
def _clear_protected_registry():
    clear_protected_outputs()
    yield
    clear_protected_outputs()


def _make_tool_defs(*names: str) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": f"{name} tool",
                "parameters": {"type": "object", "properties": {}},
            },
        }
        for name in names
    ]


def _tool_call(name: str, args: dict, call_id: str = "call_privacy"):
    return SimpleNamespace(
        id=call_id,
        type="function",
        function=SimpleNamespace(name=name, arguments=json.dumps(args)),
    )


def _agent(llm_exposure: str) -> AIAgent:
    with (
        patch("run_agent.get_tool_definitions", return_value=_make_tool_defs("web_search")),
        patch("run_agent.check_toolset_requirements", return_value={}),
        patch("run_agent.OpenAI"),
    ):
        agent = AIAgent(
            api_key="test-key",
            base_url="https://openrouter.ai/api/v1",
            quiet_mode=True,
            skip_context_files=True,
            skip_memory=True,
            llm_exposure=llm_exposure,
        )
    agent.client = MagicMock()
    agent.tool_delay = 0
    return agent


def test_full_exposure_keeps_tool_result_inline():
    agent = _agent("full")
    messages = []
    assistant = SimpleNamespace(tool_calls=[_tool_call("web_search", {"q": "x"}, "call_full")])

    with patch("run_agent.handle_function_call", return_value="RAW_SEARCH_RESULT"):
        agent._execute_tool_calls_sequential(assistant, messages, "task-full")

    assert len(messages) == 1
    assert "RAW_SEARCH_RESULT" in messages[0]["content"]


def test_minimal_exposure_replaces_tool_result_with_protected_envelope(tmp_path, monkeypatch):
    clear_protected_outputs()
    monkeypatch.setattr("tools.tool_result_storage.STORAGE_DIR", str(tmp_path))
    agent = _agent("minimal")
    messages = []
    assistant = SimpleNamespace(tool_calls=[_tool_call("web_search", {"q": "x"}, "call_min")])

    with patch("run_agent.handle_function_call", return_value="RAW_SEARCH_RESULT"):
        agent._execute_tool_calls_sequential(assistant, messages, "task-min")

    content = messages[0]["content"]
    assert "RAW_SEARCH_RESULT" not in content
    envelope = json.loads(content)
    assert envelope["status"] == "protected_output"
    assert envelope["llm_exposure"] == "minimal"
    assert envelope["content_returned"] is False
    saved_path = envelope["saved_output_path"]
    assert saved_path
    assert (tmp_path / "call_min.txt").read_text(encoding="utf-8") == "RAW_SEARCH_RESULT"


def test_minimal_exposure_keeps_clarify_answer_visible():
    agent = _agent("minimal")
    agent.clarify_callback = lambda question, choices: "user approved option"
    messages = []
    assistant = SimpleNamespace(
        tool_calls=[
            _tool_call(
                "clarify",
                {"question": "Choose?", "choices": ["A", "B"]},
                "call_clarify",
            )
        ]
    )

    agent._execute_tool_calls_sequential(assistant, messages, "task-clarify")

    assert len(messages) == 1
    assert "user approved option" in messages[0]["content"]
    assert "protected_output" not in messages[0]["content"]


def test_minimal_exposure_keeps_engineering_viewer_summary_visible(tmp_path, monkeypatch):
    clear_protected_outputs()
    monkeypatch.setattr("tools.tool_result_storage.STORAGE_DIR", str(tmp_path))
    result = json.dumps(
        {
            "tool": "bdf_3d_viewer_build",
            "status": "ok",
            "summary": {
                "viewer_backend": "fem_explorer",
                "window": "launched",
                "launch_mode": "production",
                "viewer_url": "http://127.0.0.1:62000",
                "bdf_path": "/models/test.bdf",
                "op2_path": None,
                "auto_animate": False,
            },
            "artifacts": ["/models/viewer/fem_explorer_launch.json"],
            "agent_guidance": "FEM Explorer has already been launched in a desktop window.",
        }
    )

    envelope = json.loads(
        protect_tool_result_for_model(
            tool_name="engineering_tool_run",
            result=result,
            tool_call_id="call_engineering",
        )
    )

    assert envelope["status"] == "protected_output"
    assert envelope["content_returned"] is False
    assert envelope["engineering_tool"] == "bdf_3d_viewer_build"
    assert envelope["engineering_status"] == "ok"
    assert envelope["engineering_summary"]["viewer_backend"] == "fem_explorer"
    assert envelope["engineering_summary"]["window"] == "launched"
    assert envelope["engineering_summary"]["viewer_url"] == "http://127.0.0.1:62000"
    assert envelope["engineering_summary"]["bdf_path"] == "/models/test.bdf"
    assert envelope["engineering_summary"]["op2_path"] is None
    assert "already been launched" in envelope["engineering_agent_guidance"]
    assert "summary" not in envelope


def test_minimal_exposure_keeps_fem_explorer_summary_visible(tmp_path, monkeypatch):
    clear_protected_outputs()
    monkeypatch.setattr("tools.tool_result_storage.STORAGE_DIR", str(tmp_path))
    result = json.dumps(
        {
            "tool": "fem_explorer_open",
            "status": "ok",
            "summary": {
                "viewer_backend": "fem_explorer",
                "window": "launched",
                "launch_mode": "production",
                "viewer_url": "http://127.0.0.1:62000",
                "bdf_path": "/models/test.bdf",
                "op2_path": None,
                "auto_animate": False,
            },
            "artifacts": ["/models/viewer/fem_explorer_launch.json"],
            "agent_guidance": "FEM Explorer has already been launched in a desktop window.",
        }
    )

    envelope = json.loads(
        protect_tool_result_for_model(
            tool_name="fem_explorer_open",
            result=result,
            tool_call_id="call_fem_explorer",
        )
    )

    assert envelope["status"] == "protected_output"
    assert envelope["content_returned"] is False
    assert envelope["fem_explorer_tool"] == "fem_explorer_open"
    assert envelope["fem_explorer_status"] == "ok"
    assert envelope["fem_explorer_summary"]["viewer_backend"] == "fem_explorer"
    assert envelope["fem_explorer_summary"]["window"] == "launched"
    assert envelope["fem_explorer_summary"]["viewer_url"] == "http://127.0.0.1:62000"
    assert envelope["fem_explorer_summary"]["bdf_path"] == "/models/test.bdf"
    assert envelope["fem_explorer_summary"]["op2_path"] is None
    assert "already been launched" in envelope["fem_explorer_agent_guidance"]
    assert "summary" not in envelope


def test_minimal_exposure_keeps_spectral_edge_summary_visible(tmp_path, monkeypatch):
    clear_protected_outputs()
    monkeypatch.setattr("tools.tool_result_storage.STORAGE_DIR", str(tmp_path))
    result = json.dumps(
        {
            "tool": "spectral_edge_open_spectrogram",
            "status": "ok",
            "summary": {
                "viewer_backend": "spectral_edge",
                "window": "launched",
                "file_path": "/data/AR02.h5",
                "flight_key": "AR02",
                "channel_key": "Accel_X",
                "manifest_path": "/data/_ava_spectral_edge/AR02_spectrogram/spectral_edge_launch.json",
            },
            "artifacts": ["/data/_ava_spectral_edge/AR02_spectrogram/spectral_edge_launch.json"],
            "agent_guidance": "SpectralEdge has already been launched in a desktop window.",
        }
    )

    envelope = json.loads(
        protect_tool_result_for_model(
            tool_name="spectral_edge_open_spectrogram",
            result=result,
            tool_call_id="call_spectral_edge",
        )
    )

    assert envelope["status"] == "protected_output"
    assert envelope["content_returned"] is False
    assert envelope["spectral_edge_tool"] == "spectral_edge_open_spectrogram"
    assert envelope["spectral_edge_status"] == "ok"
    assert envelope["spectral_edge_summary"]["viewer_backend"] == "spectral_edge"
    assert envelope["spectral_edge_summary"]["window"] == "launched"
    assert envelope["spectral_edge_summary"]["file_path"] == "/data/AR02.h5"
    assert envelope["spectral_edge_summary"]["channel_key"] == "Accel_X"
    assert "already been launched" in envelope["spectral_edge_agent_guidance"]
    assert "summary" not in envelope


def test_protected_output_read_requires_approval(tmp_path):
    clear_protected_outputs()
    protected = tmp_path / "protected.txt"
    protected.write_text("raw protected content\n", encoding="utf-8")
    register_protected_output(
        str(protected),
        tool_name="terminal",
        tool_call_id="call_saved",
        content_length=22,
    )

    denied = json.loads(handle_function_call("read_file", {"path": str(protected)}, task_id="privacy-read"))
    assert denied["protected_output"] is True
    assert "raw protected content" not in json.dumps(denied)

    approved = json.loads(
        handle_function_call(
            "read_file",
            {"path": str(protected), "limit": 20},
            task_id="privacy-read-approved",
            privacy_approval_callback=lambda _path, _metadata: "Approve once",
        )
    )
    assert "raw protected content" in approved["content"]
    assert approved[APPROVED_PROTECTED_READ_FIELD] is True
