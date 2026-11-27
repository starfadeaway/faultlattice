"""真实进程硬超时的 CLI、四件套与复算端到端验收。"""

import json
from pathlib import Path

from typer.testing import CliRunner

from faultlattice.cli import app

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TASK_FILE = REPO_ROOT / "tasks" / "local_hard_timeout.yaml"


def test_process_timeout_cli_run_and_verify(tmp_path: Path) -> None:
    runner = CliRunner()
    runs_root = tmp_path / "runs"
    result = runner.invoke(
        app, ["run", str(TASK_FILE), "--runs-root", str(runs_root)]
    )
    assert result.exit_code == 0, result.output

    run_dir = next(runs_root.iterdir())
    assert {path.name for path in run_dir.iterdir() if path.is_file()} == {
        "run.json", "steps.jsonl", "oracle.jsonl", "report.md"
    }
    manifest = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert manifest["injection_applied"] is True
    assert manifest["task"]["fault"]["params"]["timeout_mode"] == "process"

    events = [json.loads(line) for line in (run_dir / "steps.jsonl").read_text().splitlines()]
    injection = next(event for event in events if event["event_type"] == "injection")
    assert injection["process_terminated"] is True
    assert injection["worker_pid"] > 0
    assert injection["elapsed_seconds"] >= 0.1
    assert not (run_dir / "sandbox" / "output" / "hard-timeout.txt").exists()

    oracle = json.loads((run_dir / "oracle.jsonl").read_text(encoding="utf-8").strip())
    assert oracle["verdict"] == "explicit_failure"
    assert oracle["evidence"]["kind"] == "file_absent"
    assert oracle["evidence"]["exists"] is False
    assert "真实时钟期限" in (run_dir / "report.md").read_text(encoding="utf-8")

    verified = runner.invoke(app, ["verify", str(run_dir)])
    assert verified.exit_code == 0, verified.output
