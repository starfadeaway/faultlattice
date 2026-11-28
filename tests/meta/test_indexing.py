"""运行索引提取只读四件套，并排除套件状态与公开样例目录。"""

import json
import shutil
from pathlib import Path

import pytest

from faultlattice.errors import ArtifactError
from faultlattice.indexing import collect_run_records, load_run_index_record

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SAMPLE = REPO_ROOT / "runs" / "_sample" / "20261124T124335-94ebab0a"


def test_public_sample_becomes_structured_record_without_changing_source() -> None:
    before = {path.name: path.read_bytes() for path in SAMPLE.iterdir() if path.is_file()}
    record = load_run_index_record(SAMPLE)
    assert record.run_id == SAMPLE.name
    assert record.task_id == "local_write"
    assert record.host == "local_controlled"
    assert record.mode.value == "M0"
    assert record.injection_point == "tool_args"
    assert record.fault_type == "invalid_args"
    assert record.surface_as == "raise_exception"
    assert record.framework_verdict == "explicit_failure"
    assert record.model_verdict is None
    assert len(record.manifest_sha256) == 64
    assert "预注册预期" in record.search_text
    assert before == {path.name: path.read_bytes() for path in SAMPLE.iterdir() if path.is_file()}


def test_collect_skips_auxiliary_and_failed_runs_but_rejects_damaged_complete_run(
    tmp_path: Path,
) -> None:
    runs = tmp_path / "runs"
    shutil.copytree(SAMPLE, runs / SAMPLE.name)
    shutil.copytree(SAMPLE, runs / "_sample" / SAMPLE.name)
    (runs / "suites").mkdir()
    (runs / "_index").mkdir()
    (runs / "_quality").mkdir()
    (runs / "empty-output").mkdir()
    failed = runs / "20261129T000000-failed"
    shutil.copytree(SAMPLE, failed)
    (failed / "oracle.jsonl").unlink()
    (failed / "report.md").unlink()
    manifest_path = failed / "run.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["run_id"] = failed.name
    manifest["execution_status"] = "harness_failed"
    manifest["oracle_sha256"] = None
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    records = collect_run_records(runs)
    assert [record.run_id for record in records] == [SAMPLE.name]

    (runs / SAMPLE.name / "report.md").unlink()
    with pytest.raises(ArtifactError, match="report.md"):
        collect_run_records(runs)


def test_cli_env_loader_uses_installed_package_not_repository_launcher(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import faultlattice.cli as cli

    calls: list[Path] = []
    monkeypatch.setattr("faultlattice.env.load_env", lambda path: calls.append(path))
    cli._load_local_env()
    assert calls == [cli._repo_root() / ".env"]
