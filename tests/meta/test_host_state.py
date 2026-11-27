"""外部业务状态后置条件：独立观察、失败关闭与人读证据。"""

from pathlib import Path

from faultlattice.host import HostRunResult, PostconditionObservation
from faultlattice.report import generate_report
from faultlattice.runner import execute_run, load_judgements
from faultlattice.schemas import (
    ExecutionMode,
    ExpectedPostcondition,
    FrameworkVerdict,
    InconclusiveReason,
    OracleDeterminism,
    OracleSource,
    OracleSpec,
    OracleValidation,
    TargetLayer,
    TaskDefinition,
)


def _task() -> TaskDefinition:
    return TaskDefinition(
        task_id="host-state-check",
        description="核验外部业务状态而不是文件或最终回答",
        host="stateful-test-double",
        mode=ExecutionMode.M0,
        target_layers=[TargetLayer.FRAMEWORK],
        script=[{"final_answer": "预设完成"}],
        expected_postcondition=ExpectedPostcondition(
            kind="host_state",
            params={"summary": "测试记录应与预注册值一致"},
        ),
        expected_behavior="真实记录存在且值一致时才允许完成",
        fault_recoverable=True,
        oracle=OracleSpec(
            source=OracleSource.STATE,
            determinism=OracleDeterminism.DETERMINISTIC,
            validation=OracleValidation.UNVALIDATED,
        ),
        inconclusive_threshold=0.5,
        min_evaluable=1,
    )


class _StatefulHost:
    name = "stateful-test-double"
    package_version = "1.0.0"
    host_commit = None

    def __init__(self, *, matches: bool = True, fail_observation: bool = False) -> None:
        self.matches = matches
        self.fail_observation = fail_observation

    def run_script(self, script, *, fault=None, sandbox: Path) -> HostRunResult:
        return HostRunResult(
            framework_outcome="completed",
            final_answer="预设完成",
            events=[{"kind": "model_output", "content": "预设完成", "preset": True}],
        )

    def observe_postcondition(self, expected, *, sandbox: Path) -> PostconditionObservation:
        if self.fail_observation:
            raise RuntimeError("database password must not leak into evidence")
        return PostconditionObservation(
            task_succeeded=self.matches,
            side_effects_as_expected=self.matches,
            evidence={"observation_summary": "测试记录已独立查询", "record_matches": self.matches},
        )


class _FileOnlyHost:
    name = "file-only-test-double"
    package_version = "1.0.0"
    host_commit = None

    def run_script(self, script, *, fault=None, sandbox: Path) -> HostRunResult:
        return HostRunResult(framework_outcome="completed", final_answer="done", events=[])


def _run(tmp_path: Path, host) -> Path:
    run_dir = execute_run(_task(), host, runs_root=tmp_path / "runs", repo_root=tmp_path)
    generate_report(run_dir)
    return run_dir


def test_host_state_uses_independent_observation(tmp_path: Path) -> None:
    run_dir = _run(tmp_path, _StatefulHost())
    judgement = load_judgements(run_dir)[0]
    assert judgement.verdict is FrameworkVerdict.COMPLETED
    assert judgement.evidence["record_matches"] is True
    report = (run_dir / "report.md").read_text(encoding="utf-8")
    assert "独立只读状态观察" in report
    assert "测试记录已独立查询" in report


def test_host_state_false_is_not_success(tmp_path: Path) -> None:
    judgement = load_judgements(_run(tmp_path, _StatefulHost(matches=False)))[0]
    assert judgement.verdict is FrameworkVerdict.SILENT_FAILURE


def test_host_state_missing_or_failed_observation_is_inconclusive(tmp_path: Path) -> None:
    for index, host in enumerate((_FileOnlyHost(), _StatefulHost(fail_observation=True))):
        run_dir = _run(tmp_path / str(index), host)
        judgement = load_judgements(run_dir)[0]
        assert judgement.verdict is FrameworkVerdict.INCONCLUSIVE
        assert judgement.inconclusive_reason is InconclusiveReason.ORACLE_EVIDENCE_INSUFFICIENT
        assert "password" not in (run_dir / "report.md").read_text(encoding="utf-8")
