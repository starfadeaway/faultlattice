"""实验视图：预注册套件、一键执行、过程事件、历史恢复与 API。"""

import json
import shutil
import time
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from console.server import app as app_module
from console.server.experiments import ExperimentService
from faultlattice.errors import ConfigurationError
from faultlattice.model import ModelResponse

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class FakeAdvisor:
    model_id = "fake-advisor"
    sampling_params = {"temperature": 0.2}

    def __init__(self) -> None:
        self.messages: list[dict] = []

    def generate(self, messages, *, tools) -> ModelResponse:
        self.messages = messages
        assert tools == []
        return ModelResponse(
            content=(
                "### 优先修复\n"
                "保留参数错误传播，并为 `write_file` 增加异常边界回归测试。\n\n"
                "该建议不会修改 Oracle。"
            )
        )


class TruncatedAdvisor(FakeAdvisor):
    def generate(self, messages, *, tools) -> ModelResponse:
        super().generate(messages, tools=tools)
        return ModelResponse(content="### 未完成的", finish_reason="length")


def _service(root: Path) -> ExperimentService:
    tasks = root / "tasks"
    tasks.mkdir(parents=True)
    shutil.copyfile(REPO_ROOT / "tasks" / "local_write.yaml", tasks / "local_write.yaml")
    experiments = root / "experiments"
    experiments.mkdir()
    registry = {
        "suites": [
            {
                "id": "local-suite",
                "name": "本地自动测试",
                "version": 1,
                "description": "在隔离工作区运行一个真实本地任务。",
                "tasks": ["tasks/local_write.yaml"],
            }
        ]
    }
    (experiments / "suites.yaml").write_text(
        yaml.safe_dump(registry, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    return ExperimentService(root)


def _wait_for_completion(service: ExperimentService, batch_id: str) -> dict:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        state = service.get(batch_id)
        if state["status"] != "running":
            return state
        time.sleep(0.02)
    pytest.fail(f"套件未在限时内完成: {batch_id}")


def test_suite_executes_and_restores_complete_history(tmp_path: Path) -> None:
    service = _service(tmp_path)

    suites = service.suites()
    assert len(suites) == 1
    assert suites[0]["task_details"][0]["task_id"] == "local_write"
    assert suites[0]["task_details"][0]["expected_behavior"]
    assert suites[0]["requires_model"] is False

    started = service.start_suite("local-suite")
    assert started["status"] == "running"
    assert started["total_tasks"] == 1
    state = _wait_for_completion(service, started["batch_id"])

    assert state["status"] == "completed", state["error"]
    assert state["completed_tasks"] == 1
    assert state["current_task_id"] is None
    task = state["tasks"][0]
    assert task["status"] == "completed", task["error"]
    assert task["run_id"]
    event_types = {event["event_type"] for event in task["events"]}
    assert {"tool_call", "injection", "tool_result", "run_end"} <= event_types
    assert task["judgements"][0]["layer"] == "framework"
    assert task["judgements"][0]["verdict"] == "explicit_failure"

    run_dir = tmp_path / "runs" / task["run_id"]
    for name in ("run.json", "steps.jsonl", "oracle.jsonl", "report.md"):
        assert (run_dir / name).is_file()
    suite_dir = tmp_path / "runs" / "suites" / state["batch_id"]
    assert json.loads((suite_dir / "suite.json").read_text(encoding="utf-8"))["status"] == "completed"
    report = service.report(state["batch_id"])
    assert state["batch_id"] in report
    assert task["run_id"] in report
    assert "completed 表示实验和复算完成，不等于被测 Agent 没有缺陷" in report

    restored = ExperimentService(tmp_path)
    assert restored.history()[0]["batch_id"] == state["batch_id"]
    assert restored.get(state["batch_id"]) == state
    assert restored.report(state["batch_id"]) == report


def test_llm_advice_uses_trace_evidence_and_persists_without_changing_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = _service(tmp_path)
    monkeypatch.setattr(app_module, "experiment_service", service)
    monkeypatch.delenv("FAULTLATTICE_MODEL_API_KEY", raising=False)
    monkeypatch.delenv("FAULTLATTICE_ADVISOR_MODEL_ID", raising=False)
    state = _wait_for_completion(service, service.start_suite("local-suite")["batch_id"])
    original_judgements = state["tasks"][0]["judgements"]
    client = TestClient(app_module.app)
    path = f"/api/experiments/history/{state['batch_id']}/tasks/local_write/advice"

    assert service.suites()[0]["advisor_configured"] is False
    assert client.post(path).status_code == 409

    advisor = FakeAdvisor()
    monkeypatch.setattr(service, "_advisor_model", lambda option_id=None: advisor)
    response = client.post(path, json={"advisor_option_id": "kimi"})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["advice_model"] == "fake-advisor"
    assert result["advice_option_id"] == "kimi"
    assert "保留参数错误传播" in result["content"]
    assert "未自动修改代码" in result["content"]
    assert "explicit_failure" in advisor.messages[1]["content"]
    assert "faultlattice-evidence" in advisor.messages[1]["content"]
    assert client.post(
        f"/api/experiments/history/{state['batch_id']}/tasks/not-found/advice"
    ).status_code == 404

    restored = ExperimentService(tmp_path).get(state["batch_id"])["tasks"][0]
    assert restored["advice"] == result["content"]
    assert restored["advice_generated_at"] == result["advice_generated_at"]
    assert restored["judgements"] == original_judgements

    truncated = TruncatedAdvisor()
    monkeypatch.setattr(service, "_advisor_model", lambda option_id=None: truncated)
    rejected = client.post(path, json={"advisor_option_id": "kimi"})
    assert rejected.status_code == 409
    assert "正文已截断" in rejected.json()["detail"]
    unchanged = ExperimentService(tmp_path).get(state["batch_id"])["tasks"][0]
    assert unchanged["advice"] == result["content"]


def test_unknown_suite_and_concurrent_run_are_rejected(tmp_path: Path) -> None:
    service = _service(tmp_path)
    with pytest.raises(ConfigurationError, match="未知实验套件"):
        service.start_suite("missing")

    service._history["occupied"] = {"batch_id": "occupied", "status": "running"}
    with pytest.raises(ConfigurationError, match="已有实验套件正在运行"):
        service.start_suite("local-suite")


def test_experiment_api_supports_one_click_progress_and_markdown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = _service(tmp_path)
    monkeypatch.setattr(app_module, "experiment_service", service)
    client = TestClient(app_module.app)

    suite_response = client.get("/api/experiments/suites")
    assert suite_response.status_code == 200
    assert suite_response.json()[0]["id"] == "local-suite"
    assert client.post("/api/experiments/run", json={"suite_id": "missing"}).status_code == 409

    response = client.post("/api/experiments/run", json={"suite_id": "local-suite"})
    assert response.status_code == 200, response.text
    batch_id = response.json()["batch_id"]
    state = _wait_for_completion(service, batch_id)
    assert state["status"] == "completed"

    detail = client.get(f"/api/experiments/history/{batch_id}")
    assert detail.status_code == 200
    assert detail.json()["tasks"][0]["events"]
    history = client.get("/api/experiments/history")
    assert history.status_code == 200
    assert history.json()[0]["batch_id"] == batch_id
    report = client.get(f"/api/experiments/history/{batch_id}/report")
    assert report.status_code == 200
    assert report.headers["content-type"].startswith("text/plain")
    assert f"# FaultLattice 套件报告 {batch_id}" in report.text
    assert client.get("/api/experiments/history/not-found").status_code == 404


def test_m3_model_choice_is_frozen_before_background_start_without_leaking_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tasks = tmp_path / "tasks"
    tasks.mkdir()
    shutil.copyfile(REPO_ROOT / "tasks" / "langgraph_m3.yaml", tasks / "langgraph_m3.yaml")
    experiments = tmp_path / "experiments"
    experiments.mkdir()
    (experiments / "suites.yaml").write_text(
        yaml.safe_dump(
            {
                "suites": [
                    {
                        "id": "m3-suite",
                        "name": "真实模型续跑",
                        "version": 1,
                        "description": "验证启动前模型冻结。",
                        "tasks": ["tasks/langgraph_m3.yaml"],
                    }
                ]
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    for provider, model in (("KIMI", "kimi-example"), ("DEEPSEEK", "deepseek-example")):
        monkeypatch.setenv(f"FAULTLATTICE_LLM_{provider}_API_KEY", f"{provider.lower()}-secret")
        monkeypatch.setenv(f"FAULTLATTICE_LLM_{provider}_BASE_URL", f"https://{provider.lower()}.example/v1")
        monkeypatch.setenv(f"FAULTLATTICE_LLM_{provider}_MODEL_ID", model)
        monkeypatch.setenv(f"FAULTLATTICE_LLM_{provider}_LABEL", provider.title())
        monkeypatch.setenv(f"FAULTLATTICE_LLM_{provider}_CAPABILITIES", "chat")
    monkeypatch.setenv("FAULTLATTICE_LLM_DEEPSEEK_REASONING_MODE", "enabled")
    monkeypatch.setenv("FAULTLATTICE_LLM_KIMI_SAMPLING_PARAMS", '{"temperature":1}')
    monkeypatch.setenv(
        "FAULTLATTICE_LLM_KIMI_ADVISOR_SAMPLING_PARAMS",
        '{"temperature":0.2,"reasoning_effort":"low"}',
    )

    service = ExperimentService(tmp_path)
    assert service.suites()[0]["model_configured"] is True

    threads = []

    class FrozenThread:
        def __init__(self, *, target, args, name, daemon) -> None:
            self.args = args
            threads.append(self)

        def start(self) -> None:
            # 只验证启动边界，不发送真实模型请求。
            return None

    monkeypatch.setattr("console.server.experiments.threading.Thread", FrozenThread)
    monkeypatch.setattr(app_module, "experiment_service", service)
    client = TestClient(app_module.app)
    invalid = client.post(
        "/api/experiments/run", json={"suite_id": "m3-suite", "model_option_id": "missing"}
    )
    assert invalid.status_code == 409

    response = client.post(
        "/api/experiments/run", json={"suite_id": "m3-suite", "model_option_id": "deepseek"}
    )
    assert response.status_code == 200, response.text
    state = response.json()
    assert state["model_option_id"] == "deepseek"
    assert state["model_id"] == "deepseek-example"
    assert state["model_reasoning_mode"] == "enabled"
    assert state["model_sampling_params"] == {"temperature": 0.0}
    frozen_task = threads[0].args[2][0]
    assert frozen_task.model.model_id == "deepseek-example"
    assert frozen_task.model.reasoning_mode == "enabled"
    assert frozen_task.model.sampling_params == {"temperature": 0.0}
    assert threads[0].args[3].option_id == "deepseek"
    assert "deepseek-secret" not in json.dumps(state)
    persisted = (tmp_path / "runs" / "suites" / state["batch_id"] / "suite.json").read_text(
        encoding="utf-8"
    )
    assert "deepseek-secret" not in persisted

    kimi_tasks, kimi_option = ExperimentService._freeze_model_choice([frozen_task], "kimi")
    assert kimi_option is not None
    assert kimi_tasks[0].model is not None
    assert kimi_tasks[0].model.sampling_params == {"temperature": 1}
    advisor = service._advisor_model("kimi")
    assert advisor.sampling_params == {
        "temperature": 0.2,
        "max_tokens": 16_384,
        "reasoning_effort": "low",
    }
    assert advisor._client.timeout == 180.0
    assert "kimi-secret" not in json.dumps(kimi_option.public())


def test_llm_cross_batch_analysis_uses_aggregate_evidence_without_persistence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = _service(tmp_path)
    monkeypatch.setattr(app_module, "experiment_service", service)
    monkeypatch.delenv("FAULTLATTICE_MODEL_API_KEY", raising=False)
    monkeypatch.delenv("FAULTLATTICE_ADVISOR_MODEL_ID", raising=False)
    state = _wait_for_completion(service, service.start_suite("local-suite")["batch_id"])
    original = service.get(state["batch_id"])
    advisor = FakeAdvisor()
    monkeypatch.setattr(service, "_advisor_model", lambda option_id=None: advisor)
    client = TestClient(app_module.app)
    selection = {"batch_id": state["batch_id"], "task_id": "local_write"}

    response = client.post(
        "/api/experiments/analysis",
        json={"selections": [selection], "layer": "framework", "model_option_id": "kimi"},
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["model_id"] == "fake-advisor"
    assert result["model_option_id"] == "kimi"
    assert result["generated_at"]
    assert "保留参数错误传播" in result["content"]
    prompt = advisor.messages[1]["content"]
    assert "faultlattice-analysis" in prompt
    assert '"task_groups"' in prompt
    assert '"explicit_failure":1' in prompt
    assert '"events"' not in prompt
    assert str(tmp_path) not in prompt
    assert service.get(state["batch_id"]) == original

    model_only = service._analysis_evidence([(state, state["tasks"][0])], "model")
    assert model_only["totals"]["oracle_judgements"] == 0
    assert client.post(
        "/api/experiments/analysis",
        json={"selections": [selection, selection], "layer": "all"},
    ).status_code == 409
    assert client.post(
        "/api/experiments/analysis",
        json={
            "selections": [{"batch_id": state["batch_id"], "task_id": "missing"}],
            "layer": "all",
        },
    ).status_code == 404
