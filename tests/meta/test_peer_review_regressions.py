"""两份外部互评指出的核心缺陷；先复现，再固定修复后的公开契约。"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from console.server.app import app
from console.server.authoring import inspect_adapter_source
from faultlattice.adapters.local import LocalControlledHost, _write_file_tool
from faultlattice.errors import ReplayError, TraceFormatError
from faultlattice.oracle.judge import FrameworkEvidence, judge_framework, judge_model
from faultlattice.replay import replay_run
from faultlattice.report import generate_report, verify_report
from faultlattice.runner import _model_rule_evidence, execute_run, load_judgements, load_task
from faultlattice.schemas import ExecutionMode, FrameworkVerdict, ModelVerdict

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
M3_SAMPLE = REPO_ROOT / "runs" / "_sample" / "20261125T143029-fa4d6cf0"


def _claim(value: str) -> str:
    return f'```json faultlattice_claim\n{{"state_claim":"{value}"}}\n```'


@pytest.mark.parametrize(
    "answer",
    [
        "工具返回 `{}`，未返回错误信号。",
        "任务未成功，文件没有写入。",
        "无法确认失败；但文件已成功创建。",
        "the tool returned no error",
    ],
)
def test_unstructured_or_negated_model_text_is_not_guessed(answer: str) -> None:
    evidence, details = _model_rule_evidence(answer, task_succeeded=True)

    assert evidence.evidence_sufficient is False
    assert details["state_claim"] is None
    assert judge_model(evidence) is ModelVerdict.INCONCLUSIVE


def test_structured_model_claim_drives_verdict() -> None:
    success, _ = _model_rule_evidence("已写入。\n" + _claim("success"), task_succeeded=True)
    failure, _ = _model_rule_evidence("写入失败。\n" + _claim("failure"), task_succeeded=False)
    unknown, _ = _model_rule_evidence("无法确认。\n" + _claim("unknown"), task_succeeded=True)

    assert judge_model(success) is ModelVerdict.COMPLETED
    assert judge_model(failure) is ModelVerdict.EXPLICIT_FAILURE
    assert judge_model(unknown) is ModelVerdict.INCONCLUSIVE


def test_framework_failure_signal_is_interpreted_against_preregistration() -> None:
    common = {
        "evidence_sufficient": True,
        "task_succeeded": True,
        "side_effects_as_expected": True,
    }
    assert judge_framework(
        FrameworkEvidence(**common, failure_signal_to_caller=True, expected_failure_signal=True)
    ) is FrameworkVerdict.EXPLICIT_FAILURE
    assert judge_framework(
        FrameworkEvidence(**common, failure_signal_to_caller=False, expected_failure_signal=True)
    ) is FrameworkVerdict.SILENT_FAILURE
    assert judge_framework(
        FrameworkEvidence(**common, failure_signal_to_caller=True, expected_failure_signal=False)
    ) is FrameworkVerdict.CONTRACT_VIOLATION


def test_tool_result_failure_after_real_write_is_explicit_failure(tmp_path: Path) -> None:
    task = load_task(REPO_ROOT / "tasks" / "smolagents_write.yaml").model_copy(
        update={"host": "local_controlled", "expected_failure_signal": True}
    )
    run_dir = execute_run(
        task, LocalControlledHost(), runs_root=tmp_path / "runs", repo_root=tmp_path
    )

    assert load_judgements(run_dir)[0].verdict is FrameworkVerdict.EXPLICIT_FAILURE
    assert (run_dir / "sandbox" / "output" / "hello.txt").is_file()


def test_replay_rejects_m3_before_creating_artifacts(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    with pytest.raises(ReplayError, match="M3"):
        replay_run(
            M3_SAMPLE,
            LocalControlledHost(),
            mode=ExecutionMode.M1,
            runs_root=runs_root,
            repo_root=REPO_ROOT,
        )
    assert not runs_root.exists() or not list(runs_root.iterdir())


def test_relative_sandbox_path_is_normalized(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = _write_file_tool(
        {"path": "output/hello.txt", "content": "hello"}, Path("relative-sandbox")
    )
    assert result["written"] == "output/hello.txt"
    assert (tmp_path / "relative-sandbox" / "output" / "hello.txt").read_text() == "hello"


def test_tool_args_return_value_does_not_execute_or_raise(tmp_path: Path) -> None:
    task = load_task(REPO_ROOT / "tasks" / "local_write.yaml")
    from faultlattice.schemas import SurfaceAs

    assert task.fault is not None
    fault = task.fault.model_copy(update={"surface_as": SurfaceAs.RETURN_VALUE})
    task = task.model_copy(update={"fault": fault, "expected_failure_signal": True})

    run_dir = execute_run(
        task, LocalControlledHost(), runs_root=tmp_path / "runs", repo_root=tmp_path
    )
    events = [json.loads(line) for line in (run_dir / "steps.jsonl").read_text().splitlines()]
    tool_result = next(item for item in events if item["event_type"] == "tool_result")

    assert tool_result["error"] is None
    assert tool_result["result"]["error"] == "invalid_args"
    assert not (run_dir / "sandbox" / "output" / "hello.txt").exists()
    assert load_judgements(run_dir)[0].verdict is FrameworkVerdict.EXPLICIT_FAILURE


def test_verify_detects_trace_hash_and_human_report_tampering(tmp_path: Path) -> None:
    task = load_task(REPO_ROOT / "tasks" / "local_write.yaml")
    run_dir = execute_run(
        task, LocalControlledHost(), runs_root=tmp_path / "runs", repo_root=tmp_path
    )
    generate_report(run_dir)
    manifest = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert manifest["steps_sha256"]
    assert manifest["oracle_sha256"]

    steps = run_dir / "steps.jsonl"
    steps.write_text(steps.read_text(encoding="utf-8").replace('"applied":true', '"applied":false'))
    assert any("steps.jsonl" in item and "哈希" in item for item in verify_report(run_dir))

    shutil.copytree(run_dir, tmp_path / "report-copy")
    report = tmp_path / "report-copy" / "report.md"
    report.write_text(report.read_text(encoding="utf-8") + "\n篡改正文\n", encoding="utf-8")
    assert any("正文" in item for item in verify_report(tmp_path / "report-copy"))


def test_malformed_adapter_event_is_rejected_before_oracle(tmp_path: Path) -> None:
    class BrokenHost(LocalControlledHost):
        def run_script(self, script, *, fault=None, sandbox: Path):
            from faultlattice.host import HostRunResult

            return HostRunResult(
                framework_outcome="completed",
                final_answer="bad",
                events=[{"kind": "model_output", "preset": True}],
            )

    task = load_task(REPO_ROOT / "tasks" / "local_write.yaml").model_copy(update={"fault": None})
    with pytest.raises(TraceFormatError, match="steps.jsonl"):
        execute_run(task, BrokenHost(), runs_root=tmp_path / "runs", repo_root=tmp_path)


def test_local_api_rejects_untrusted_host_and_cross_origin_write() -> None:
    client = TestClient(app)
    assert client.get("/api/health", headers={"Host": "evil.example"}).status_code == 400
    response = client.post(
        "/api/adapter-authoring/save",
        headers={"Host": "localhost", "Origin": "http://evil.example"},
        json={"agent_id": "bad-origin", "class_name": "Bad", "content": "class Bad: pass"},
    )
    assert response.status_code == 403


@pytest.mark.parametrize(
    "statement",
    [
        "subprocess.run(['whoami'])",
        "getattr(os, 'system')('whoami')",
        "importlib.import_module('os').remove('x')",
        "shutil.rmtree('x')",
    ],
)
def test_adapter_static_check_flags_indirect_dangerous_calls(statement: str) -> None:
    source = (
        "import os, subprocess, importlib, shutil\n"
        "class Adapter:\n"
        f"    def run_script(self):\n        {statement}\n"
        "    def preflight(self):\n        pass\n"
    )
    result = inspect_adapter_source(source)
    assert any("高风险" in warning for warning in result["warnings"])
