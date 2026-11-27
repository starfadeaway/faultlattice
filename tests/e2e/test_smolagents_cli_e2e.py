"""smolagents 宿主的 CLI 纵向切片：真实运行、四件套、报告复算与重放。"""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

pytest.importorskip("smolagents")

from faultlattice.cli import app  # noqa: E402

runner = CliRunner()
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TASK_FILE = REPO_ROOT / "tasks" / "smolagents_write.yaml"


def test_smolagents_run_verify_and_replay(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    result = runner.invoke(app, ["run", str(TASK_FILE), "--runs-root", str(runs_root)])
    assert result.exit_code == 0, result.output
    source = next(path for path in runs_root.iterdir() if path.is_dir())
    for name in ("run.json", "steps.jsonl", "oracle.jsonl", "report.md"):
        assert (source / name).is_file()

    manifest = json.loads((source / "run.json").read_text(encoding="utf-8"))
    assert manifest["task"]["host"] == "smolagents"
    assert manifest["versions"]["host_package_version"] == "1.26.0"
    assert manifest["versions"]["host_commit"] is None
    assert "host_commit" in manifest["versions"]["null_reasons"]
    assert manifest["injection_applied"] is True
    assert (source / "sandbox" / "output" / "hello.txt").is_file()
    assert runner.invoke(app, ["verify", str(source)]).exit_code == 0

    replayed = runner.invoke(
        app, ["replay", str(source), "--mode", "M2", "--runs-root", str(runs_root)]
    )
    assert replayed.exit_code == 0, replayed.output
    replay_dir = next(path for path in runs_root.iterdir() if path.is_dir() and path != source)
    replay_manifest = json.loads((replay_dir / "run.json").read_text(encoding="utf-8"))
    assert replay_manifest["task"]["mode"] == "M2"
    assert replay_manifest["task"]["host"] == "smolagents"
    assert replay_manifest["injection_applied"] is True
    assert runner.invoke(app, ["verify", str(replay_dir)]).exit_code == 0
