"""批次 CLI：A/B 运行前硬校验、聚合报告与独立复算。"""

import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from faultlattice.cli import app

runner = CliRunner()
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TASK_FILE = REPO_ROOT / "tasks" / "local_write.yaml"


def _write_pair(tmp_path: Path, *, mutate_b: bool = False) -> tuple[Path, Path]:
    original = yaml.safe_load(TASK_FILE.read_text(encoding="utf-8"))
    a = dict(original)
    a["pair_id"] = "local-write-ab"
    a["fault"] = {**original["fault"], "surface_as": "return_value"}
    b = dict(original)
    b["pair_id"] = "local-write-ab"
    b["fault"] = {**original["fault"], "surface_as": "raise_exception"}
    if mutate_b:
        b["expected_behavior"] = "与 A 不同的预注册契约"
    a_path = tmp_path / "a.yaml"
    b_path = tmp_path / "b.yaml"
    a_path.write_text(yaml.safe_dump(a, allow_unicode=True), encoding="utf-8")
    b_path.write_text(yaml.safe_dump(b, allow_unicode=True), encoding="utf-8")
    return a_path, b_path


def test_run_batch_generates_and_verifies_ab_report(tmp_path: Path) -> None:
    a, b = _write_pair(tmp_path)
    runs_root = tmp_path / "runs"
    result = runner.invoke(app, ["run-batch", str(a), str(b), "--runs-root", str(runs_root)])
    assert result.exit_code == 0, result.output

    run_dirs = sorted(path for path in runs_root.iterdir() if path.is_dir())
    assert len(run_dirs) == 2
    report = runs_root / "batch-report.md"
    assert report.is_file()
    verify = runner.invoke(
        app,
        [
            "batch-verify",
            *(str(path) for path in run_dirs),
            "--report",
            str(report),
        ],
    )
    assert verify.exit_code == 0, verify.output

    text = report.read_text(encoding="utf-8")
    metrics_json = text.split("```json faultlattice-batch-metrics\n", 1)[1].split("\n```", 1)[0]
    metrics = json.loads(metrics_json)
    assert metrics["total_runs"] == 2
    assert len(metrics["groups"]) == 2
    assert len(metrics["pairs"]) == 1
    assert metrics["pairs"][0]["a"]["conditions"]["surface_as"] == "return_value"
    assert metrics["pairs"][0]["b"]["conditions"]["surface_as"] == "raise_exception"


def test_invalid_ab_batch_executes_nothing(tmp_path: Path) -> None:
    a, b = _write_pair(tmp_path, mutate_b=True)
    runs_root = tmp_path / "runs"
    result = runner.invoke(app, ["run-batch", str(a), str(b), "--runs-root", str(runs_root)])
    assert result.exit_code == 2
    assert "预注册条件存在差异" in result.output
    assert not runs_root.exists() or not list(runs_root.iterdir())


def test_batch_report_command_rebuilds_from_existing_runs(tmp_path: Path) -> None:
    a, b = _write_pair(tmp_path)
    runs_root = tmp_path / "runs"
    result = runner.invoke(app, ["run-batch", str(a), str(b), "--runs-root", str(runs_root)])
    assert result.exit_code == 0, result.output
    run_dirs = sorted(path for path in runs_root.iterdir() if path.is_dir())
    output = tmp_path / "rebuilt.md"
    rebuilt = runner.invoke(
        app,
        ["batch-report", *(str(path) for path in run_dirs), "--output", str(output)],
    )
    assert rebuilt.exit_code == 0, rebuilt.output
    assert output.read_bytes() == (runs_root / "batch-report.md").read_bytes()
