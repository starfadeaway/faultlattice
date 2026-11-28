"""第四轮审查回归：Harness 失败也必须保留可审计的原始事件。"""

from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("langgraph")

from faultlattice.adapters.langgraph import LanggraphHost  # noqa: E402
from faultlattice.canonical import sha256_hex  # noqa: E402
from faultlattice.errors import ReplayError  # noqa: E402
from faultlattice.model import ModelResponse, ModelToolCall  # noqa: E402
from faultlattice.runner import execute_run, load_manifest, load_task  # noqa: E402
from faultlattice.trace import read_jsonl  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PREFIX = [
    {
        "tool_call": {
            "name": "write_file",
            "args": {"path": "output/hello.txt", "content": "hello m3\n"},
        }
    }
]


class BlockedToolProvider:
    model_id = "fake-blocked-tool-model"
    sampling_params = {"temperature": 0.0}

    def __init__(self) -> None:
        self.calls = 0

    def generate(
        self, messages: list[dict[str, Any]], *, tools: list[dict[str, Any]]
    ) -> ModelResponse:
        del messages, tools
        self.calls += 1
        if self.calls == 1:
            target = PREFIX[0]["tool_call"]
            return ModelResponse(
                content="",
                tool_calls=[ModelToolCall(id="prefix-1", **target)],
                reasoning_content="前缀",
            )
        return ModelResponse(
            content="尝试额外探测",
            tool_calls=[
                ModelToolCall(
                    id="blocked-probe",
                    name="write_file",
                    args={"path": "output/probe.txt", "content": "不得写入"},
                )
            ],
            reasoning_content="续跑",
        )


def test_blocked_tool_call_survives_harness_exception(tmp_path: Path) -> None:
    task = load_task(REPO_ROOT / "tasks" / "langgraph_m3.yaml")
    provider = BlockedToolProvider()

    with pytest.raises(ReplayError, match="已在执行前阻断") as caught:
        execute_run(
            task,
            LanggraphHost(),
            runs_root=tmp_path / "runs",
            repo_root=tmp_path,
            run_id="blocked-run",
            script_override=PREFIX,
            model_provider=provider,
        )

    assert caught.value.run_id == "blocked-run"
    run_dir = tmp_path / "runs" / "blocked-run"
    manifest = load_manifest(run_dir)
    assert manifest.execution_status == "harness_failed"
    assert manifest.harness_error == {
        "type": "ReplayError",
        "message": str(caught.value),
    }
    assert manifest.model_invoked is True
    assert manifest.injection_applied is True
    assert manifest.observation_status.value == "unknown"
    assert manifest.oracle_sha256 is None
    assert manifest.steps_sha256 == sha256_hex((run_dir / "steps.jsonl").read_bytes())

    events = read_jsonl(run_dir / "steps.jsonl")
    blocked = next(event for event in events if event.get("blocked_tool_calls"))
    assert blocked["m3_phase"] == "continuation"
    assert blocked["continuation_tool_policy"] == "final_answer_only"
    assert blocked["blocked_tool_calls"][0]["args"]["path"] == "output/probe.txt"
    assert events[-1]["event_type"] == "run_end"
    assert events[-1]["framework_outcome"] == "failed"
    assert events[-1]["harness_error_type"] == "ReplayError"
    assert not (run_dir / "oracle.jsonl").exists()
    assert not (run_dir / "report.md").exists()
    assert (run_dir / "sandbox" / "output" / "hello.txt").is_file()
    assert not (run_dir / "sandbox" / "output" / "probe.txt").exists()

    # 同一宿主下一次在预检即失败时，不得误带上一次运行的事件缓存。
    from faultlattice.errors import AdapterCapabilityError

    stale_host = LanggraphHost()
    stale_host.last_events = events
    assert task.fault is not None
    early_task = task.model_copy(
        update={"fault": task.fault.model_copy(update={"params": {"timeout_mode": "process"}})}
    )
    with pytest.raises(AdapterCapabilityError, match="尚不支持进程隔离硬超时"):
        execute_run(
            early_task,
            stale_host,
            runs_root=tmp_path / "runs",
            repo_root=tmp_path,
            run_id="preflight-failed",
            script_override=PREFIX,
            model_provider=provider,
        )
    early_events = read_jsonl(tmp_path / "runs" / "preflight-failed" / "steps.jsonl")
    assert [event["event_type"] for event in early_events] == ["task_start", "run_end"]
    assert load_manifest(tmp_path / "runs" / "preflight-failed").model_invoked is False
