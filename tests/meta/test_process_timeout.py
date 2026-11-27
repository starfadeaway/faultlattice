"""真实进程超时：必须终止执行体，而不只是返回一个同名异常。"""

import time
from pathlib import Path

import pytest

from faultlattice.adapters.local import LocalControlledHost
from faultlattice.errors import ConfigurationError
from faultlattice.schemas import FaultSpec


def _fault(surface_as: str = "raise_exception", **overrides: object) -> FaultSpec:
    params: dict[str, object] = {
        "timeout_mode": "process",
        "timeout_seconds": 0.15,
        "tool_delay_seconds": 1.0,
    }
    params.update(overrides)
    return FaultSpec.model_validate(
        {
            "injection_point": "tool_result",
            "fault_type": "timeout",
            "surface_as": surface_as,
            "params": params,
        }
    )


def _script() -> list[dict[str, object]]:
    return [
        {
            "tool_call": {
                "name": "write_file",
                "args": {"path": "output/late.txt", "content": "not allowed\n"},
            }
        },
        {"final_answer": "不应执行到这里"},
    ]


def test_process_timeout_terminates_before_late_write(tmp_path: Path) -> None:
    started = time.monotonic()
    result = LocalControlledHost().run_script(
        _script(), fault=_fault(), sandbox=tmp_path / "sandbox"
    )
    elapsed = time.monotonic() - started

    assert elapsed < 1.0
    assert result.framework_outcome == "failed"
    assert result.final_answer is None
    injection = next(event for event in result.events if event["kind"] == "injection")
    assert injection["applied"] is True
    assert injection["timeout_mode"] == "process"
    assert injection["process_terminated"] is True
    assert isinstance(injection["worker_pid"], int)
    assert injection["elapsed_seconds"] >= 0.1
    assert result.events[-1]["error"] == "TimeoutError"

    # 等到原工具本可完成写入之后；文件仍不存在才证明 worker 没有继续运行。
    time.sleep(1.1)
    assert not (tmp_path / "sandbox" / "output" / "late.txt").exists()


def test_process_timeout_can_surface_as_return_value(tmp_path: Path) -> None:
    result = LocalControlledHost().run_script(
        _script(), fault=_fault("return_value"), sandbox=tmp_path / "sandbox"
    )

    assert result.framework_outcome == "failed"
    tool_result = next(event for event in result.events if event["kind"] == "tool_result")
    assert tool_result["result"]["error"] == "timeout"
    assert tool_result["error"] is None
    assert tool_result["injected"] is True


def test_process_completion_is_not_misreported_as_timeout(tmp_path: Path) -> None:
    result = LocalControlledHost().run_script(
        _script(),
        fault=_fault(timeout_seconds=2.0, tool_delay_seconds=0.0),
        sandbox=tmp_path / "sandbox",
    )

    injection = next(event for event in result.events if event["kind"] == "injection")
    assert injection["applied"] is False
    assert injection["reason"] == "timeout_not_reached"
    assert (tmp_path / "sandbox" / "output" / "late.txt").is_file()


def test_process_timeout_rejects_invalid_clock_configuration(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="timeout_seconds"):
        LocalControlledHost().run_script(
            _script(),
            fault=_fault(timeout_seconds=0.0),
            sandbox=tmp_path / "sandbox",
        )
