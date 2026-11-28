"""CI 回归门禁使用真实公开四件套构造通过与回归案例，不调用外部服务。"""

import shutil
from pathlib import Path

import pytest

from faultlattice.canonical import canonical_bytes
from faultlattice.quality import evaluate_quality_gate
from faultlattice.report import generate_report
from faultlattice.runner import load_judgements, load_manifest
from faultlattice.schemas import FrameworkVerdict, InconclusiveReason

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SAMPLE = REPO_ROOT / "runs" / "_sample" / "20261124T124335-94ebab0a"


def _copy_sample(root: Path) -> Path:
    target = root / SAMPLE.name
    shutil.copytree(SAMPLE, target)
    return target


def _replace_oracle(run_dir: Path, verdict: FrameworkVerdict) -> None:
    judgement = load_judgements(run_dir)[0].model_copy(update={"verdict": verdict})
    (run_dir / "oracle.jsonl").write_bytes(
        canonical_bytes(judgement.model_dump(mode="json"))
    )
    generate_report(run_dir)


def test_identical_public_sample_passes(tmp_path: Path) -> None:
    current = _copy_sample(tmp_path / "current")
    result = evaluate_quality_gate("public", [SAMPLE], [current])
    assert result.passed, result.violations
    assert result.matched_coordinates == 1
    layer = result.comparisons[0].layers[0]
    assert layer.current_evaluable == 1
    assert layer.rate_stability == "below_min_evaluable"


@pytest.mark.parametrize(
    ("verdict", "code"),
    [
        (FrameworkVerdict.SILENT_FAILURE, "new_silent_failure"),
        (FrameworkVerdict.CONTRACT_VIOLATION, "new_contract_violation"),
    ],
)
def test_new_severe_verdict_is_rejected(
    tmp_path: Path, verdict: FrameworkVerdict, code: str
) -> None:
    current = _copy_sample(tmp_path / code)
    _replace_oracle(current, verdict)
    result = evaluate_quality_gate("public", [SAMPLE], [current])
    assert not result.passed
    assert code in {item.code for item in result.violations}


def test_new_injection_failure_and_evaluable_loss_are_rejected(tmp_path: Path) -> None:
    current = _copy_sample(tmp_path / "injection")
    manifest = load_manifest(current).model_copy(update={"injection_applied": False})
    (current / "run.json").write_bytes(canonical_bytes(manifest.model_dump(mode="json")))
    judgement = load_judgements(current)[0].model_copy(
        update={
            "verdict": FrameworkVerdict.INCONCLUSIVE,
            "inconclusive_reason": InconclusiveReason.INJECTION_FAILED,
        }
    )
    (current / "oracle.jsonl").write_bytes(
        canonical_bytes(judgement.model_dump(mode="json"))
    )
    generate_report(current)
    result = evaluate_quality_gate("public", [SAMPLE], [current])
    codes = {item.code for item in result.violations}
    assert "new_injection_failure" in codes
    assert "evaluable_run_lost" in codes


def test_missing_artifact_and_report_tampering_are_rejected(tmp_path: Path) -> None:
    missing = _copy_sample(tmp_path / "missing")
    (missing / "steps.jsonl").unlink()
    result = evaluate_quality_gate("public", [SAMPLE], [missing])
    assert "artifact_missing" in {item.code for item in result.violations}
    assert "evaluable_run_lost" in {item.code for item in result.violations}

    tampered = _copy_sample(tmp_path / "tampered")
    report = tampered / "report.md"
    report.write_text(report.read_text(encoding="utf-8") + "\n篡改说明\n", encoding="utf-8")
    # 正文也是交付产物；即使未改指标锚点，追加或删减同样必须拒绝。
    result = evaluate_quality_gate("public", [SAMPLE], [tampered])
    assert "report_verification_failed" in {item.code for item in result.violations}
    report.write_text(
        report.read_text(encoding="utf-8").replace('"run_id":"', '"run_id":"tampered-', 1),
        encoding="utf-8",
    )
    result = evaluate_quality_gate("public", [SAMPLE], [tampered])
    assert "report_verification_failed" in {item.code for item in result.violations}


def test_below_min_evaluable_does_not_claim_stable_rate(tmp_path: Path) -> None:
    baseline = _copy_sample(tmp_path / "baseline")
    current = _copy_sample(tmp_path / "current")
    for run_dir in (baseline, current):
        manifest = load_manifest(run_dir)
        task = manifest.task.model_copy(update={"min_evaluable": 2})
        changed = manifest.model_copy(update={"task": task})
        (run_dir / "run.json").write_bytes(canonical_bytes(changed.model_dump(mode="json")))
        generate_report(run_dir)
    result = evaluate_quality_gate("small-sample", [baseline], [current])
    assert result.passed, result.violations
    layer = result.comparisons[0].layers[0]
    assert layer.min_evaluable == 3
    assert layer.current_evaluable == 1
    assert layer.rate_stability == "below_min_evaluable"


def test_missing_current_coordinate_is_rejected(tmp_path: Path) -> None:
    current = _copy_sample(tmp_path / "current")
    manifest = load_manifest(current)
    task = manifest.task.model_copy(update={"task_id": "different_task"})
    changed = manifest.model_copy(update={"task": task})
    (current / "run.json").write_bytes(canonical_bytes(changed.model_dump(mode="json")))
    generate_report(current)
    result = evaluate_quality_gate("public", [SAMPLE], [current])
    assert not result.passed
    assert "missing_current_coordinate" in {item.code for item in result.violations}


EXTERNAL_SAMPLES = [
    REPO_ROOT / "runs" / "_sample" / run_id
    for run_id in (
        "20261127T131928-4a109d3f",
        "20261126T175052-1730a492",
        "20261127T131958-b5e13aff",
        "20261126T180523-058c206a",
        "20261127T145247-77cdae58",
        "20261127T145248-20a065b6",
    )
]
NO_FAULT_SAMPLE = EXTERNAL_SAMPLES[0]


def test_external_agent_public_samples_pass_quality_gate() -> None:
    result = evaluate_quality_gate("external", EXTERNAL_SAMPLES, EXTERNAL_SAMPLES)

    assert result.passed, result.violations
    assert result.matched_coordinates == 6
    no_fault = [item for item in result.comparisons if item.coordinate["fault_type"] is None]
    assert len(no_fault) == 2
    for item in no_fault:
        assert item.baseline_no_fault_verdicts == ["framework=completed"]
        assert item.current_no_fault_verdicts == ["framework=completed"]
        assert item.layers[0].baseline_evaluable == 0
        assert item.layers[0].current_evaluable == 0


def test_no_fault_verdict_change_is_rejected_without_changing_denominator(
    tmp_path: Path,
) -> None:
    current = tmp_path / "current"
    shutil.copytree(NO_FAULT_SAMPLE, current)
    _replace_oracle(current, FrameworkVerdict.EXPLICIT_FAILURE)

    result = evaluate_quality_gate("external", [NO_FAULT_SAMPLE], [current])

    assert not result.passed
    assert "no_fault_verdict_changed" in {item.code for item in result.violations}
    layer = result.comparisons[0].layers[0]
    assert layer.baseline_evaluable == 0
    assert layer.current_evaluable == 0
    assert "evaluable_run_lost" not in {item.code for item in result.violations}


def test_no_fault_unexpected_injection_is_rejected(tmp_path: Path) -> None:
    current = tmp_path / "current"
    shutil.copytree(NO_FAULT_SAMPLE, current)
    changed = load_manifest(current).model_copy(update={"injection_applied": True})
    (current / "run.json").write_bytes(canonical_bytes(changed.model_dump(mode="json")))
    generate_report(current)

    result = evaluate_quality_gate("external", [NO_FAULT_SAMPLE], [current])

    assert not result.passed
    assert "unexpected_injection_for_no_fault" in {
        item.code for item in result.violations
    }
