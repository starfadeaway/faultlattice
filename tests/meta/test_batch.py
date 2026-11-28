"""批次聚合、指标门禁与 A/B 硬校验的元测试。"""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from faultlattice.batch import (
    compute_batch_metrics,
    generate_batch_report,
    validate_ab_tasks,
    verify_batch_report,
)
from faultlattice.errors import ConfigurationError
from faultlattice.schemas import (
    ExecutionMode,
    ExpectedPostcondition,
    FaultSpec,
    FaultType,
    FrameworkVerdict,
    InconclusiveReason,
    InjectionPoint,
    ModelSpec,
    ModelVerdict,
    ObservationStatus,
    OracleDeterminism,
    OracleJudgement,
    OracleSource,
    OracleSpec,
    OracleValidation,
    RunManifest,
    SurfaceAs,
    TargetLayer,
    TaskDefinition,
    VersionInfo,
)
from faultlattice.trace import TraceWriter


def _task(
    *,
    surface: SurfaceAs = SurfaceAs.RAISE_EXCEPTION,
    mode: ExecutionMode = ExecutionMode.M0,
    layers: list[TargetLayer] | None = None,
    min_evaluable: int = 1,
    threshold: float = 1.0,
    pair_id: str | None = None,
) -> TaskDefinition:
    return TaskDefinition(
        task_id="batch_task",
        host="controlled",
        mode=mode,
        fault=FaultSpec(
            injection_point=InjectionPoint.TOOL_RESULT,
            fault_type=FaultType.ERROR_RESPONSE,
            surface_as=surface,
            params={"message": "injected"},
        ),
        target_layers=layers or [TargetLayer.FRAMEWORK],
        expected_postcondition=ExpectedPostcondition(kind="file_written", params={"path": "x"}),
        expected_behavior="controlled behavior",
        fault_recoverable=True,
        oracle=OracleSpec(
            source=OracleSource.STATE,
            determinism=OracleDeterminism.DETERMINISTIC,
            validation=OracleValidation.GOLDEN_VERIFIED,
        ),
        inconclusive_threshold=threshold,
        min_evaluable=min_evaluable,
        pair_id=pair_id,
        model=(
            ModelSpec(
                provider="openai_compatible",
                model_id="batch-fixture-model",
                sampling_params={"temperature": 0.0},
            )
            if mode is ExecutionMode.M3
            else None
        ),
        counterfactual_source="runs/source" if mode is ExecutionMode.M3 else None,
    )


def _write_run(
    root: Path,
    run_id: str,
    task: TaskDefinition,
    *,
    verdict: FrameworkVerdict | ModelVerdict,
    layer: TargetLayer = TargetLayer.FRAMEWORK,
    injection_applied: bool = True,
    inconclusive_reason: InconclusiveReason | None = None,
    observation_status: ObservationStatus = ObservationStatus.NOT_APPLICABLE,
    host_version: str = "1.0.0",
) -> Path:
    run_dir = root / run_id
    writer = TraceWriter(run_dir)
    now = datetime.now(UTC)
    writer.write_run_json(
        RunManifest(
            run_id=run_id,
            created_at=now,
            task=task,
            versions=VersionInfo(
                faultlattice_commit="abc123",
                host_package_version=host_version,
                host_commit="host123",
                python_version="3.13.5",
                dependency_lock_hash="lock123",
            ),
            injection_applied=injection_applied,
            observation_status=observation_status,
            model_invoked=layer is TargetLayer.MODEL,
            run_dir=str(run_dir),
        )
    )
    writer.append_oracle(
        OracleJudgement(
            run_id=run_id,
            layer=layer,
            verdict=verdict,
            inconclusive_reason=inconclusive_reason,
            oracle=task.oracle,
            timestamp=now,
        )
    )
    return run_dir


def test_batch_metrics_aggregate_without_hiding_evidence_gaps(tmp_path: Path) -> None:
    task = _task(min_evaluable=2, threshold=0.5)
    runs = [
        _write_run(tmp_path, "run-a", task, verdict=FrameworkVerdict.SILENT_FAILURE),
        _write_run(tmp_path, "run-b", task, verdict=FrameworkVerdict.COMPLETED),
        _write_run(tmp_path, "run-c", task, verdict=FrameworkVerdict.COMPLETED),
        _write_run(
            tmp_path,
            "run-d",
            task,
            verdict=FrameworkVerdict.INCONCLUSIVE,
            inconclusive_reason=InconclusiveReason.ORACLE_EVIDENCE_INSUFFICIENT,
        ),
    ]

    metrics = compute_batch_metrics(runs)
    assert metrics["total_runs"] == 4
    assert len(metrics["groups"]) == 1
    framework = metrics["groups"][0]["framework"]
    assert framework["applicable"] == 4
    assert framework["evaluable"] == 3
    assert framework["silent_failures"] == 1
    assert framework["silent_failure_rate"] == pytest.approx(1 / 3)
    assert framework["oracle_coverage"] == pytest.approx(3 / 4)
    assert framework["oracle_insufficient"] == 1
    assert framework["rate_suppressed_reason"] is None


def test_min_evaluable_gate_suppresses_rate(tmp_path: Path) -> None:
    task = _task(min_evaluable=2)
    run = _write_run(tmp_path, "run-a", task, verdict=FrameworkVerdict.SILENT_FAILURE)
    framework = compute_batch_metrics([run])["groups"][0]["framework"]
    assert framework["silent_failure_rate"] is None
    assert framework["rate_suppressed_reason"] == "below_min_evaluable"
    assert framework["silent_failures"] == 1


def test_inconclusive_threshold_gate_suppresses_rate(tmp_path: Path) -> None:
    task = _task(min_evaluable=2, threshold=0.25)
    runs = [
        _write_run(tmp_path, "run-a", task, verdict=FrameworkVerdict.SILENT_FAILURE),
        _write_run(tmp_path, "run-b", task, verdict=FrameworkVerdict.COMPLETED),
        _write_run(tmp_path, "run-c", task, verdict=FrameworkVerdict.COMPLETED),
        _write_run(
            tmp_path,
            "run-d",
            task,
            verdict=FrameworkVerdict.INCONCLUSIVE,
            inconclusive_reason=InconclusiveReason.ORACLE_EVIDENCE_INSUFFICIENT,
        ),
        _write_run(
            tmp_path,
            "run-e",
            task,
            verdict=FrameworkVerdict.INCONCLUSIVE,
            inconclusive_reason=InconclusiveReason.ORACLE_EVIDENCE_INSUFFICIENT,
        ),
    ]
    framework = compute_batch_metrics(runs)["groups"][0]["framework"]
    assert framework["evaluable"] == 3
    assert framework["oracle_insufficient_ratio"] == 0.4
    assert framework["silent_failure_rate"] is None
    assert framework["rate_suppressed_reason"] == "inconclusive_threshold_exceeded"


def test_injection_failure_is_not_oracle_evidence_insufficiency(tmp_path: Path) -> None:
    task = _task()
    runs = [
        _write_run(
            tmp_path,
            "run-a",
            task,
            verdict=FrameworkVerdict.INCONCLUSIVE,
            injection_applied=False,
            inconclusive_reason=InconclusiveReason.INJECTION_FAILED,
        ),
        *[
            _write_run(tmp_path, f"run-{suffix}", task, verdict=FrameworkVerdict.COMPLETED)
            for suffix in ("b", "c", "d")
        ],
    ]
    framework = compute_batch_metrics(runs)["groups"][0]["framework"]
    assert framework["injection_failed"] == 1
    assert framework["oracle_insufficient"] == 0
    assert framework["evaluable"] == 3
    assert framework["silent_failure_rate"] == 0.0


def test_model_evaluable_requires_observation_reached(tmp_path: Path) -> None:
    task = _task(mode=ExecutionMode.M3, layers=[TargetLayer.MODEL])
    runs = [
        *[
            _write_run(
                tmp_path,
                f"run-{suffix}",
                task,
                layer=TargetLayer.MODEL,
                verdict=ModelVerdict.COMPLETED,
                observation_status=ObservationStatus.REACHED,
            )
            for suffix in ("a", "c", "d")
        ],
        _write_run(
            tmp_path,
            "run-b",
            task,
            layer=TargetLayer.MODEL,
            verdict=ModelVerdict.SILENT_FAILURE,
            observation_status=ObservationStatus.NOT_REACHED,
        ),
    ]
    model = compute_batch_metrics(runs)["groups"][0]["model"]
    assert model["applicable"] == 4
    assert model["evaluable"] == 3
    assert model["silent_failures"] == 0
    assert model["silent_failure_rate"] == 0.0


def test_ab_preflight_rejects_non_surface_difference() -> None:
    a = _task(surface=SurfaceAs.RETURN_VALUE, pair_id="pair-1")
    b = _task(surface=SurfaceAs.RAISE_EXCEPTION, pair_id="pair-1")
    validate_ab_tasks([a, b])

    changed = b.model_copy(update={"expected_behavior": "changed after seeing A"})
    with pytest.raises(ConfigurationError, match="预注册条件存在差异"):
        validate_ab_tasks([a, changed])


def test_ab_preflight_requires_both_arms() -> None:
    a = _task(surface=SurfaceAs.RETURN_VALUE, pair_id="pair-1")
    with pytest.raises(ConfigurationError, match="必须同时包含"):
        validate_ab_tasks([a, a])


def test_ab_metrics_report_each_arm_and_b_minus_a(tmp_path: Path) -> None:
    a = _task(surface=SurfaceAs.RETURN_VALUE, pair_id="pair-1")
    b = _task(surface=SurfaceAs.RAISE_EXCEPTION, pair_id="pair-1")
    runs = [
        *[
            _write_run(tmp_path, f"run-a-{index}", a, verdict=FrameworkVerdict.SILENT_FAILURE)
            for index in range(3)
        ],
        *[
            _write_run(tmp_path, f"run-b-{index}", b, verdict=FrameworkVerdict.EXPLICIT_FAILURE)
            for index in range(3)
        ],
    ]
    metrics = compute_batch_metrics(runs)
    pair = metrics["pairs"][0]
    assert pair["a"]["framework"]["silent_failure_rate"] == 1.0
    assert pair["b"]["framework"]["silent_failure_rate"] == 0.0
    assert pair["framework_rate_difference"] == -1.0


def test_ab_version_mismatch_is_hard_error(tmp_path: Path) -> None:
    a = _task(surface=SurfaceAs.RETURN_VALUE, pair_id="pair-1")
    b = _task(surface=SurfaceAs.RAISE_EXCEPTION, pair_id="pair-1")
    runs = [
        _write_run(tmp_path, "run-a", a, verdict=FrameworkVerdict.SILENT_FAILURE),
        _write_run(
            tmp_path,
            "run-b",
            b,
            verdict=FrameworkVerdict.EXPLICIT_FAILURE,
            host_version="2.0.0",
        ),
    ]
    with pytest.raises(ConfigurationError, match="host_package_version"):
        compute_batch_metrics(runs)


def test_batch_report_round_trip_and_tamper_detection(tmp_path: Path) -> None:
    task = _task()
    run = _write_run(tmp_path, "run-a", task, verdict=FrameworkVerdict.COMPLETED)
    report = generate_batch_report([run], tmp_path / "batch-report.md")
    assert verify_batch_report(report, [run]) == []
    assert "faultlattice-batch-metrics" in report.read_text(encoding="utf-8")

    report.write_text(
        report.read_text(encoding="utf-8").replace('"total_runs":1', '"total_runs":99'),
        encoding="utf-8",
    )
    assert verify_batch_report(report, [run])
