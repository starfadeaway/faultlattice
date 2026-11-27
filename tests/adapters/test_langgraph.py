"""真实 LangGraph 适配器测试：验证真实状态变化和宿主校验，而非包装器假绿。"""

import json
from pathlib import Path
from typing import Any

import pytest

langgraph = pytest.importorskip("langgraph")

from faultlattice.adapters import langgraph as langgraph_adapter  # noqa: E402
from faultlattice.adapters.langgraph import (  # noqa: E402
    SUPPORTED_LANGGRAPH_VERSION,
    LanggraphHost,
)
from faultlattice.errors import AdapterCapabilityError  # noqa: E402
from faultlattice.schemas import FaultSpec  # noqa: E402

SCRIPT = [
    {
        "tool_call": {
            "name": "write_file",
            "args": {"path": "output/hello.txt", "content": "hello langgraph\n"},
        }
    },
    {"final_answer": "已写入 output/hello.txt。"},
]


def _events(result: Any, kind: str) -> list[dict[str, Any]]:
    return [event for event in result.events if event["kind"] == kind]


def test_real_state_graph_baseline_writes_file(tmp_path: Path) -> None:
    host = LanggraphHost()
    assert host.package_version == SUPPORTED_LANGGRAPH_VERSION
    result = host.run_script(SCRIPT, sandbox=tmp_path)
    assert result.framework_outcome == "completed"
    assert result.final_answer == "已写入 output/hello.txt。"
    assert (tmp_path / "output" / "hello.txt").read_text(encoding="utf-8") == "hello langgraph\n"
    assert _events(result, "tool_result")[0]["result"]["written"] == "output/hello.txt"


def test_tool_result_return_value_is_actually_replaced(tmp_path: Path) -> None:
    fault = FaultSpec.model_validate(
        {
            "injection_point": "tool_result",
            "fault_type": "error_response",
            "surface_as": "return_value",
            "params": {"message": "actual replacement"},
        }
    )
    result = LanggraphHost().run_script(SCRIPT, fault=fault, sandbox=tmp_path)
    injection = _events(result, "injection")[0]
    tool_result = _events(result, "tool_result")[0]
    assert injection["original"]["written"] == "output/hello.txt"
    assert injection["replacement"] == {
        "error": "error_response",
        "message": "actual replacement",
    }
    assert injection["applied"] is True
    assert tool_result["result"] == injection["replacement"]
    assert (tmp_path / "output" / "hello.txt").is_file()


def test_tool_result_exception_reaches_real_graph(tmp_path: Path) -> None:
    fault = FaultSpec.model_validate(
        {
            "injection_point": "tool_result",
            "fault_type": "timeout",
            "surface_as": "raise_exception",
            "params": {"message": "actual timeout"},
        }
    )
    result = LanggraphHost().run_script(SCRIPT, fault=fault, sandbox=tmp_path)
    assert result.framework_outcome == "failed"
    assert _events(result, "injection")[0]["raised"] == "TimeoutError"
    assert _events(result, "tool_result")[0]["error"] == "TimeoutError"
    assert (tmp_path / "output" / "hello.txt").is_file()


def test_process_timeout_is_rejected_instead_of_simulated() -> None:
    fault = FaultSpec.model_validate({
        "injection_point": "tool_result",
        "fault_type": "timeout",
        "surface_as": "raise_exception",
        "params": {"timeout_mode": "process"},
    })
    with pytest.raises(AdapterCapabilityError, match="不能退回模拟超时"):
        LanggraphHost().preflight(fault)


def test_tool_args_are_changed_before_tool_node_validation(tmp_path: Path) -> None:
    fault = FaultSpec.model_validate(
        {
            "injection_point": "tool_args",
            "fault_type": "invalid_args",
            "surface_as": "raise_exception",
            "params": {"corrupt_args": {"path": 123}},
        }
    )
    result = LanggraphHost().run_script(SCRIPT, fault=fault, sandbox=tmp_path)
    injection = _events(result, "injection")[0]
    assert injection["original"]["path"] == "output/hello.txt"
    assert injection["replacement"]["path"] == 123
    assert injection["applied"] is True
    assert injection["raised"] == "ValidationError"
    assert _events(result, "tool_result")[0]["error"] == "ValidationError"
    assert result.framework_outcome == "failed"
    assert not (tmp_path / "output" / "hello.txt").exists()


def test_tool_args_validation_error_can_surface_as_return_value(tmp_path: Path) -> None:
    fault = FaultSpec.model_validate(
        {
            "injection_point": "tool_args",
            "fault_type": "invalid_args",
            "surface_as": "return_value",
            "params": {"corrupt_args": {"path": 123}},
        }
    )
    host = LanggraphHost()
    result = host.run_script(SCRIPT, fault=fault, sandbox=tmp_path)
    injection = _events(result, "injection")[0]
    tool_result = _events(result, "tool_result")[0]
    assert injection["raised"] == "ValidationError"
    assert tool_result["result"]["error"] == "invalid_args"
    assert result.framework_outcome == "completed"
    actual_observation = host.last_model_inputs[1][-1].content
    assert json.loads(str(actual_observation)) == tool_result["result"]
    assert not (tmp_path / "output" / "hello.txt").exists()


def test_observation_changes_next_real_model_input_but_not_tool_result(tmp_path: Path) -> None:
    fault = FaultSpec.model_validate(
        {
            "injection_point": "observation",
            "fault_type": "truncated",
            "surface_as": "not_applicable",
            "params": {"keep": 4},
        }
    )
    host = LanggraphHost()
    result = host.run_script(SCRIPT, fault=fault, sandbox=tmp_path)
    injection = _events(result, "injection")[0]
    assert "output/hello.txt" in injection["original"]
    assert injection["replacement"] == injection["original"][:4]
    assert injection["applied"] is True
    tool_result = _events(result, "tool_result")[0]
    assert tool_result["result"]["written"] == "output/hello.txt"
    assert tool_result["injected"] is False
    actual_observation = host.last_model_inputs[1][-1].content
    assert actual_observation == injection["replacement"]
    assert injection["original"] != actual_observation


def test_unchanged_tool_args_cannot_claim_injection_applied(tmp_path: Path) -> None:
    fault = FaultSpec.model_validate(
        {
            "injection_point": "tool_args",
            "fault_type": "invalid_args",
            "surface_as": "raise_exception",
            "params": {"corrupt_args": {"path": "output/hello.txt"}},
        }
    )
    result = LanggraphHost().run_script(SCRIPT, fault=fault, sandbox=tmp_path)
    assert _events(result, "injection")[0]["applied"] is False
    assert (tmp_path / "output" / "hello.txt").is_file()


def test_preflight_rejects_unverified_host_version(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(langgraph_adapter, "INSTALLED_LANGGRAPH_VERSION", "0.0.0")
    with pytest.raises(AdapterCapabilityError, match=SUPPORTED_LANGGRAPH_VERSION):
        LanggraphHost().preflight(None)
