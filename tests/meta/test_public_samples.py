"""公开报告必须附带完整、脱敏且可独立复算的原始四件套。"""

from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest
import yaml

from faultlattice.batch import validate_ab_tasks, verify_batch_report
from faultlattice.report import verify_report
from faultlattice.runner import load_judgements, load_manifest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SAMPLE_ROOT = REPO_ROOT / "runs" / "_sample"
PUBLIC_SAMPLES = sorted(path for path in SAMPLE_ROOT.iterdir() if path.is_dir())
PUBLIC_BATCHES = [
    (
        "2026-11-25-deepseek-m3-batch.md",
        [
            "20261125T140942-3b2af870",
            "20261125T140947-7422b201",
            "20261125T140951-30ee91b7",
            "20261125T140957-e4cf19bd",
        ],
    ),
    (
        "2026-11-25-kimi-m3-batch.md",
        [
            "20261125T143002-c4adae6c",
            "20261125T143029-fa4d6cf0",
            "20261125T143050-afe298f3",
            "20261125T143110-9effe896",
        ],
    ),
    (
        "2026-11-25-minimax-m3-batch.md",
        [
            "20261125T143232-9ac09615",
            "20261125T143244-3f7b04d1",
            "20261125T143250-978d183b",
            "20261125T143300-e3c70adc",
        ],
    ),
    (
        "2026-11-27-anchorline-memory-result-surface-ab.md",
        [
            "20261127T145247-77cdae58",
            "20261127T145248-20a065b6",
        ],
    ),
]


def test_public_sample_collection_is_not_empty() -> None:
    assert PUBLIC_SAMPLES


@pytest.mark.parametrize("run_dir", PUBLIC_SAMPLES, ids=lambda path: path.name)
def test_public_sample_is_complete_relative_and_reproducible(run_dir: Path) -> None:
    for name in ("run.json", "steps.jsonl", "oracle.jsonl", "report.md"):
        assert (run_dir / name).is_file(), f"公开样例缺少 {name}: {run_dir.name}"

    manifest = load_manifest(run_dir)
    normalized = manifest.run_dir.replace("\\", "/")
    assert not PurePosixPath(manifest.run_dir).is_absolute()
    assert not PureWindowsPath(manifest.run_dir).is_absolute()
    assert normalized == f"runs/_sample/{run_dir.name}"
    assert verify_report(run_dir) == []


@pytest.mark.parametrize(
    ("report_name", "run_ids"), PUBLIC_BATCHES, ids=lambda value: str(value)
)
def test_public_batch_report_is_reproducible(report_name: str, run_ids: list[str]) -> None:
    report_path = REPO_ROOT / "reports" / "external" / report_name
    run_dirs = [SAMPLE_ROOT / run_id for run_id in run_ids]
    assert verify_batch_report(report_path, run_dirs) == []


def test_anchorline_surface_pair_is_frozen_and_not_deduplicated() -> None:
    run_dirs = [
        SAMPLE_ROOT / "20261127T145247-77cdae58",
        SAMPLE_ROOT / "20261127T145248-20a065b6",
    ]
    manifests = [load_manifest(run_dir) for run_dir in run_dirs]
    validate_ab_tasks([manifest.task for manifest in manifests])
    assert {manifest.task.pair_id for manifest in manifests} == {
        "anchorline-memory-result-surface-v1"
    }
    assert {manifest.task.min_evaluable for manifest in manifests} == {2}

    judgements = [load_judgements(run_dir)[0] for run_dir in run_dirs]
    assert {item.verdict.value for item in judgements} == {"contract_violation"}
    fact_ids = {item.evidence["fact_id"] for item in judgements}
    assert len(fact_ids) == 2
    assert all(item.evidence["task_succeeded"] for item in judgements)


def test_console_external_check_is_integrity_verification_not_self_comparison() -> None:
    manifest = yaml.safe_load((REPO_ROOT / "project.manifest.yaml").read_text(encoding="utf-8"))
    command = manifest["checks"]["external-quality-gate"]["command"]

    assert command == ["python", "-m", "pytest", "tests/meta/test_public_samples.py", "-q"]
    assert "完整性" in manifest["checks"]["external-quality-gate"]["name"]
    assert "quality-gate" not in command


def test_console_public_gate_generates_independent_current() -> None:
    manifest = yaml.safe_load((REPO_ROOT / "project.manifest.yaml").read_text(encoding="utf-8"))
    command = manifest["checks"]["quality-gate"]["command"]

    assert command[:2] == ["python", "scripts/check_public_regression.py"]
    assert "runs/_sample/" not in " ".join(command[:2])
    assert (REPO_ROOT / command[1]).is_file()


def test_public_report_index_has_no_dead_links() -> None:
    index = (REPO_ROOT / "reports" / "README.md").read_text(encoding="utf-8")
    rows = [line for line in index.splitlines() if line.startswith("| 2026-")]
    assert rows
    for row in rows:
        target = row.rsplit("](", 1)[1].split(")", 1)[0]
        assert target.startswith("external/")
        assert (REPO_ROOT / "reports" / target).is_file(), f"报告索引死链: {target}"
