"""CLI 端到端测试：run → verify → replay(M1/M2) → report → verify。

验证的是命令、退出码、产物和复算结果，而不只是内部函数。
"""

import json
from pathlib import Path

from typer.testing import CliRunner

from faultlattice.cli import app

runner = CliRunner()
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TASK_FILE = REPO_ROOT / "tasks" / "local_write.yaml"
FOUR_ARTIFACTS = ["run.json", "steps.jsonl", "oracle.jsonl", "report.md"]


def _do_run(runs_root: Path) -> Path:
    result = runner.invoke(app, ["run", str(TASK_FILE), "--runs-root", str(runs_root)])
    assert result.exit_code == 0, result.output
    dirs = [d for d in runs_root.iterdir() if d.is_dir()]
    assert len(dirs) == 1
    return dirs[0]


def test_run_produces_four_artifacts(tmp_path: Path) -> None:
    run_dir = _do_run(tmp_path / "runs")
    for name in FOUR_ARTIFACTS:
        assert (run_dir / name).is_file(), f"缺少产物 {name}"


def test_run_manifest_and_oracle(tmp_path: Path) -> None:
    run_dir = _do_run(tmp_path / "runs")
    manifest = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    # invalid_args 注入应真实生效；版本字段必须存在（不适用时为 null + 原因）
    assert manifest["injection_applied"] is True
    versions = manifest["versions"]
    assert versions["python_version"]
    assert versions["dependency_lock_hash"]
    assert versions["model_id"] is None
    assert "model_id" in versions["null_reasons"]
    # 预注册声明原样复制进 run.json
    assert manifest["task"]["target_layers"] == ["framework"]

    judgements = [
        json.loads(line)
        for line in (run_dir / "oracle.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(judgements) == 1
    # 参数校验抛错 → 文件未写入 + 框架返回失败信号 → explicit_failure
    assert judgements[0]["layer"] == "framework"
    assert judgements[0]["verdict"] == "explicit_failure"
    # 文件确实没有被写入（副作用证据）
    assert not (run_dir / "sandbox" / "output" / "hello.txt").exists()


def test_verify_passes_on_fresh_run(tmp_path: Path) -> None:
    run_dir = _do_run(tmp_path / "runs")
    result = runner.invoke(app, ["verify", str(run_dir)])
    assert result.exit_code == 0, result.output


def test_verify_fails_on_tampered_report(tmp_path: Path) -> None:
    run_dir = _do_run(tmp_path / "runs")
    report_path = run_dir / "report.md"
    text = report_path.read_text(encoding="utf-8")
    # 篡改报告数字：把总运行数 1 改成 99
    assert '"total_runs":1' in text
    report_path.write_text(text.replace('"total_runs":1', '"total_runs":99'), encoding="utf-8")
    result = runner.invoke(app, ["verify", str(run_dir)])
    assert result.exit_code == 1
    assert "复算失败" in result.output


def test_report_regeneration_keeps_verify_green(tmp_path: Path) -> None:
    run_dir = _do_run(tmp_path / "runs")
    result = runner.invoke(app, ["report", str(run_dir)])
    assert result.exit_code == 0, result.output
    assert runner.invoke(app, ["verify", str(run_dir)]).exit_code == 0


def test_replay_m1_and_m2(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    source = _do_run(runs_root)

    r1 = runner.invoke(app, ["replay", str(source), "--mode", "M1", "--runs-root", str(runs_root)])
    assert r1.exit_code == 0, r1.output
    r2 = runner.invoke(app, ["replay", str(source), "--mode", "M2", "--runs-root", str(runs_root)])
    assert r2.exit_code == 0, r2.output

    dirs = sorted(d for d in runs_root.iterdir() if d.is_dir())
    assert len(dirs) == 3
    for d in dirs:
        assert runner.invoke(app, ["verify", str(d)]).exit_code == 0

    # 按 run.json 中的 mode 区分重放产物（同秒创建时目录名顺序不可靠）
    by_mode = {}
    for d in dirs:
        m = json.loads((d / "run.json").read_text(encoding="utf-8"))
        by_mode[m["task"]["mode"]] = m

    # M1 重放不带故障：文件应真实写入、injection_applied 为 False
    assert by_mode["M1"]["injection_applied"] is False
    # M2 重放重新注入同一故障：injection_applied 为 True
    assert by_mode["M2"]["injection_applied"] is True


def test_run_with_bad_task_file_fails_nonzero(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("task_id: x\n", encoding="utf-8")  # 缺大量必填字段
    result = runner.invoke(app, ["run", str(bad), "--runs-root", str(tmp_path / "runs")])
    assert result.exit_code == 2
    assert "ConfigurationError" in result.output
