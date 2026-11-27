"""公开报告必须附带完整、脱敏且可独立复算的原始四件套。"""

from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest

from faultlattice.batch import verify_batch_report
from faultlattice.report import verify_report
from faultlattice.runner import load_manifest

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
def test_public_m3_batch_report_is_reproducible(
    report_name: str, run_ids: list[str]
) -> None:
    report_path = REPO_ROOT / "reports" / "external" / report_name
    run_dirs = [SAMPLE_ROOT / run_id for run_id in run_ids]
    assert verify_batch_report(report_path, run_dirs) == []
