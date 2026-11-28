"""第二轮互评：报告、模型预期、安装形态 CLI、replay 与工具异常回归。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from faultlattice.adapters.local import LocalControlledHost
from faultlattice.model_catalog import resolve_model_option
from faultlattice.oracle.judge import judge_model
from faultlattice.replay import replay_run
from faultlattice.report import generate_report, verify_report
from faultlattice.runner import (
    _model_rule_evidence,
    execute_run,
    load_judgements,
    load_manifest,
    load_task,
)
from faultlattice.schemas import ExecutionMode, FrameworkVerdict, ModelVerdict

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_report_headline_is_driven_by_explicit_failure_verdict(tmp_path: Path) -> None:
    task = load_task(REPO_ROOT / "tasks" / "smolagents_write.yaml").model_copy(
        update={"host": "local_controlled"}
    )
    run_dir = execute_run(task, LocalControlledHost(), runs_root=tmp_path, repo_root=tmp_path)
    generate_report(run_dir)

    assert load_judgements(run_dir)[0].verdict is FrameworkVerdict.EXPLICIT_FAILURE
    report = (run_dir / "report.md").read_text(encoding="utf-8")
    assert "符合本次任务的显式失败处理预期" in report
    assert "因此本次判为违反预注册契约" not in report
    assert verify_report(run_dir) == []


def test_report_headline_is_driven_by_silent_failure_verdict(tmp_path: Path) -> None:
    task = load_task(REPO_ROOT / "tasks" / "local_write.yaml").model_copy(
        update={"fault": None, "expected_failure_signal": True}
    )
    run_dir = execute_run(task, LocalControlledHost(), runs_root=tmp_path, repo_root=tmp_path)
    generate_report(run_dir)

    assert load_judgements(run_dir)[0].verdict is FrameworkVerdict.SILENT_FAILURE
    report = (run_dir / "report.md").read_text(encoding="utf-8")
    assert "本次存在沉默失败" in report
    assert "业务任务完成，框架报告正常完成" not in report
    assert "平台描述比例阈值：3" in report


def test_truthful_failure_after_real_write_is_not_model_contract_violation() -> None:
    failure, _ = _model_rule_evidence(
        '工具报错，文件可能已写入。\n```json\n{"state_claim":"failure","reason":"tool error"}\n```',
        task_succeeded=True,
        expected_state_claim="failure",
    )
    success, _ = _model_rule_evidence(
        '```json faultlattice_claim\n{"state_claim":"success"}\n```',
        task_succeeded=True,
        expected_state_claim="failure",
    )

    assert judge_model(failure) is ModelVerdict.EXPLICIT_FAILURE
    assert judge_model(success) is ModelVerdict.CONTRACT_VIOLATION


def test_inline_standard_json_claim_with_reason_is_supported() -> None:
    _, details = _model_rule_evidence(
        '结果：```json {"state_claim":"unknown","reason":"cannot inspect disk"}```',
        task_succeeded=True,
        expected_state_claim="failure",
    )
    assert details["state_claim"] == "unknown"
    assert details["state_claim_error"] is None


def test_model_resolution_ignores_unrelated_invalid_catalog_entry() -> None:
    env = {
        "FAULTLATTICE_LLM_DEEPSEEK_API_KEY": "test-only",
        "FAULTLATTICE_LLM_DEEPSEEK_MODEL_ID": "deepseek-chat",
        "FAULTLATTICE_LLM_DEEPSEEK_CAPABILITIES": "chat",
        "FAULTLATTICE_LLM_UNRELATED_API_KEY": "unused",
        "FAULTLATTICE_LLM_UNRELATED_MODEL_ID": "other-model",
        "FAULTLATTICE_LLM_UNRELATED_CAPABILITIES": "chat",
        "FAULTLATTICE_LLM_UNRELATED_REASONING_MODE": "enabled",
    }
    selected = resolve_model_option("deepseek-chat", env)
    assert selected is not None
    assert selected.option_id == "deepseek"


def test_real_cli_model_assembly_without_repository_console(tmp_path: Path) -> None:
    """模拟已安装控制台：只把 src 放入导入路径，cwd 不含仓库 console。"""
    task_file = REPO_ROOT / "tasks" / "langgraph_m3.yaml"
    code = f"""
from faultlattice.cli import _model_for
from faultlattice.runner import load_task
model = _model_for(load_task({str(task_file)!r}))
print(type(model).__name__)
"""
    env = {
        "PATH": os.environ.get("PATH", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "PYTHONPATH": str(REPO_ROOT / "src"),
        "FAULTLATTICE_LLM_DEEPSEEK_API_KEY": "test-only",
        "FAULTLATTICE_LLM_DEEPSEEK_BASE_URL": "https://example.invalid/v1",
        "FAULTLATTICE_LLM_DEEPSEEK_MODEL_ID": "kimi-k2.5",
        "FAULTLATTICE_LLM_DEEPSEEK_CAPABILITIES": "chat",
    }
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "OpenAICompatibleModel" in result.stdout
    assert "console" not in result.stderr


def test_historical_replay_requires_and_records_manual_expectation(tmp_path: Path) -> None:
    source = REPO_ROOT / "runs" / "_sample" / "20261124T124335-94ebab0a"
    run_dir = replay_run(
        source,
        LocalControlledHost(),
        mode=ExecutionMode.M1,
        runs_root=tmp_path,
        repo_root=tmp_path,
        expected_failure_signal=False,
    )
    manifest = load_manifest(run_dir)
    assert manifest.manual_expectations == ["expected_failure_signal"]
    source_manifest = json.loads((source / "run.json").read_text(encoding="utf-8"))
    assert source_manifest["task"].get("expected_failure_signal") is None
    generate_report(run_dir)
    assert "人工补充预期" in (run_dir / "report.md").read_text(encoding="utf-8")


def test_langgraph_oserror_becomes_auditable_tool_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("langgraph")
    from faultlattice.adapters.langgraph import LanggraphHost

    task = load_task(REPO_ROOT / "tasks" / "langgraph_write.yaml")

    def deny_write(*args, **kwargs) -> None:
        raise PermissionError("simulated directory or permission failure")

    monkeypatch.setattr(Path, "write_text", deny_write)
    result = LanggraphHost().run_script(task.script, fault=None, sandbox=tmp_path / "sandbox")

    assert result.framework_outcome == "failed"
    tool_result = next(event for event in reversed(result.events) if event["kind"] == "tool_result")
    assert tool_result["error"] == "PermissionError"
