"""研发控制台：清单推导、真实检查、局部错误与文件边界。"""

import json
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from console.server.app import app
from console.server.service import ManifestError, ProjectService


def _project(root: Path, *, second_check: str = "print('ok')") -> ProjectService:
    (root / "src").mkdir()
    (root / "tests").mkdir()
    (root / "src" / "main.py").write_text("print('source')\n", encoding="utf-8")
    (root / "tests" / "test_main.py").write_text("def test_ok(): pass\n", encoding="utf-8")
    manifest = {
        "name": "FaultLattice",
        "subtitle": "Agent Reliability Harness & Evaluation Platform",
        "checks": {
            "pass": {"name": "通过项", "command": ["python", "-c", "print('ok')"]},
            "other": {"name": "另一验收项", "command": ["python", "-c", second_check]},
        },
        "modules": [
            {
                "id": "core",
                "name": "核心",
                "source_paths": ["src"],
                "test_paths": ["tests"],
                "required_checks": ["pass"],
                "dependencies": [],
            }
        ],
    }
    (root / "project.manifest.yaml").write_text(
        yaml.safe_dump(manifest, allow_unicode=True), encoding="utf-8"
    )
    return ProjectService(root)


def test_verified_status_is_derived_from_real_passing_check(tmp_path: Path) -> None:
    snapshot = _project(tmp_path).project_snapshot()
    assert snapshot["summary"]["verified"] == 1
    assert snapshot["modules"][0]["status"] == "verified"
    assert snapshot["checks"][0]["status"] == "passed"
    assert "ok" in snapshot["checks"][0]["output"]


def test_failed_check_means_developing_without_losing_result(tmp_path: Path) -> None:
    service = _project(tmp_path)
    data = yaml.safe_load(service.manifest_path.read_text(encoding="utf-8"))
    data["modules"][0]["required_checks"] = ["pass", "other"]
    data["checks"]["other"]["command"] = ["python", "-c", "import sys; sys.exit(3)"]
    service.manifest_path.write_text(yaml.safe_dump(data), encoding="utf-8")
    snapshot = service.project_snapshot()
    module = snapshot["modules"][0]
    assert module["status"] == "developing"
    assert [check["status"] for check in module["checks"]] == ["passed", "failed"]
    assert module["checks"][1]["returncode"] == 3


def test_manual_status_is_rejected(tmp_path: Path) -> None:
    service = _project(tmp_path)
    data = yaml.safe_load(service.manifest_path.read_text(encoding="utf-8"))
    data["modules"][0]["status"] = "verified"
    service.manifest_path.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(ManifestError):
        service.load_manifest()


def test_source_is_limited_to_manifest_entries(tmp_path: Path) -> None:
    service = _project(tmp_path)
    assert "print('source')" in service.source("src/main.py")["content"]
    with pytest.raises(PermissionError):
        service.source("project.manifest.yaml")
    with pytest.raises(PermissionError):
        service.source("../outside.txt")


def test_artifacts_keep_good_entry_when_another_manifest_is_broken(tmp_path: Path) -> None:
    service = _project(tmp_path)
    good = tmp_path / "runs" / "good"
    bad = tmp_path / "runs" / "bad"
    good.mkdir(parents=True)
    bad.mkdir(parents=True)
    for name in ("run.json", "steps.jsonl", "oracle.jsonl", "report.md"):
        (good / name).write_text("", encoding="utf-8")
    (good / "run.json").write_text(
        json.dumps(
            {
                "run_id": "good",
                "created_at": "2026-01-01T00:00:00+00:00",
                "task": {
                    "task_id": "readable_task",
                    "description": "可读任务说明",
                    "expected_behavior": "可读任务目标",
                },
            }
        ),
        encoding="utf-8",
    )
    (bad / "run.json").write_text("not-json", encoding="utf-8")
    (bad / "report.md").write_text("broken run", encoding="utf-8")

    artifacts = service.artifacts()
    assert len(artifacts) == 2
    good_item = next(item for item in artifacts if item["run_id"] == "good")
    assert good_item["complete"] is True
    assert good_item["description"] == "可读任务说明"
    assert good_item["expected_behavior"] == "可读任务目标"
    bad_item = next(item for item in artifacts if item["path"] == "runs/bad")
    assert bad_item["error"]
    assert bad_item["description"] is None
    assert bad_item["expected_behavior"] is None
    assert service.artifact_report("good") == ("runs/good", "")


def test_public_reports_are_limited_to_indexed_external_markdown(tmp_path: Path) -> None:
    service = _project(tmp_path)
    external = tmp_path / "reports" / "external"
    external.mkdir(parents=True)
    (external / "accepted.md").write_text("# 公开验收\n", encoding="utf-8")
    (external / "unlisted.md").write_text("# 未登记\n", encoding="utf-8")
    (tmp_path / "reports" / "README.md").write_text(
        "\n".join(
            [
                "| 日期 | 报告 | 被测宿主及版本 | 一句话结论 | 链接 |",
                "|---|---|---|---|---|",
                "| 2026-11-26 | 外部依赖验收 | LanceDB 0.41.0 | 实机复核完成。 | "
                "[验收报告](external/accepted.md) |",
                "| 2026-11-26 | 越界条目 | 无 | 不应公开。 | [越界](external/../secret.md) |",
            ]
        ),
        encoding="utf-8",
    )

    assert service.public_reports() == [
        {
            "path": "external/accepted.md",
            "title": "外部依赖验收",
            "date": "2026-11-26",
            "host": "LanceDB 0.41.0",
            "summary": "实机复核完成。",
        }
    ]
    assert service.public_report("external/accepted.md") == (
        "reports/external/accepted.md",
        "# 公开验收\n",
    )
    for path in ("external/unlisted.md", "external/../secret.md", "../outside.md"):
        with pytest.raises(PermissionError):
            service.public_report(path)


def test_health_api() -> None:
    response = TestClient(app).get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "project": "FaultLattice"}


def test_public_report_api_uses_the_registered_index() -> None:
    client = TestClient(app)
    response = client.get("/api/public-reports")
    assert response.status_code == 200
    reports = response.json()
    assert any(
        item["path"] == "external/2026-11-26-external-dependency-acceptance.md"
        for item in reports
    )
    content = client.get(
        "/api/public-reports/content",
        params={"path": "external/2026-11-26-external-dependency-acceptance.md"},
    )
    assert content.status_code == 200
    assert "MySQL、真实 Embedding 与 LanceDB" in content.text
    assert client.get(
        "/api/public-reports/content", params={"path": "../README.md"}
    ).status_code == 403
