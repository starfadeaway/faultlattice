"""外部 Agent：真实文件加载、能力预检、复用实验闭环与注入防假绿。"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from console.server import app as app_module
from console.server.experiments import ExperimentService
from console.server.external_agents import ExternalAgentService
from faultlattice.errors import AdapterCapabilityError, ConfigurationError

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _workspace(root: Path) -> None:
    (root / "tasks").mkdir()
    shutil.copyfile(REPO_ROOT / "tasks" / "local_write.yaml", root / "tasks" / "local_write.yaml")
    (root / "examples" / "external_agent").mkdir(parents=True)
    shutil.copyfile(
        REPO_ROOT / "examples" / "external_agent" / "reference_agent.py",
        root / "examples" / "external_agent" / "reference_agent.py",
    )


def _register(service: ExternalAgentService) -> dict:
    return service.register(
        agent_id="external-demo",
        name="外部测试 Agent",
        entrypoint="examples/external_agent/reference_agent.py",
        class_name="ReferenceAgent",
    )


def _wait(service: ExperimentService, batch_id: str) -> dict:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        state = service.get(batch_id)
        if state["status"] != "running":
            return state
        time.sleep(0.02)
    pytest.fail("外部 Agent 测试未在限时内结束")


def test_external_adapter_registration_preflight_and_real_e2e(tmp_path: Path) -> None:
    _workspace(tmp_path)
    agents = ExternalAgentService(tmp_path)
    public = _register(agents)

    assert public["status"] == "ready"
    assert public["host_name"] == "reference_external_agent"
    assert public["host_package_version"] == "1.0.0"
    assert len(public["source_sha256"]) == 64
    assert public["capabilities"]["modes"] == ["M0"]
    assert [task["task_id"] for task in public["compatible_tasks"]] == ["local_write"]
    assert ExternalAgentService(tmp_path).list()[0]["id"] == "external-demo"

    host, task, public = agents.binding("external-demo", "tasks/local_write.yaml")
    assert task.host == "reference_external_agent"
    experiments = ExperimentService(tmp_path)
    started = experiments.start_external_task(
        host=host,
        task=task,
        task_path="tasks/local_write.yaml",
        public=public,
    )
    state = _wait(experiments, started["batch_id"])

    assert state["status"] == "completed", state["error"]
    assert state["source_kind"] == "external_agent"
    assert state["external_agent"]["source_sha256"] == public["source_sha256"]
    result = state["tasks"][0]
    assert result["status"] == "completed", result["error"]
    assert result["judgements"][0]["verdict"] == "explicit_failure"
    manifest = json.loads(
        (tmp_path / "runs" / result["run_id"] / "run.json").read_text(encoding="utf-8")
    )
    assert manifest["task"]["host"] == "reference_external_agent"
    assert manifest["injection_applied"] is True
    assert manifest["versions"]["host_package_version"] == "1.0.0"
    assert "外部 Agent 适配器" in experiments.report(state["batch_id"])


def test_external_adapter_rejects_unsafe_paths_and_incompatible_tasks(tmp_path: Path) -> None:
    _workspace(tmp_path)
    agents = ExternalAgentService(tmp_path)
    with pytest.raises(ConfigurationError, match="登记字段不合法"):
        agents.register(
            agent_id="blank-name",
            name="   ",
            entrypoint="examples/external_agent/reference_agent.py",
            class_name="ReferenceAgent",
        )
    with pytest.raises(ConfigurationError, match="越出项目"):
        agents.register(
            agent_id="outside-agent",
            name="越界适配器",
            entrypoint="../outside.py",
            class_name="ReferenceAgent",
        )
    with pytest.raises(ConfigurationError, match="相对 .py"):
        agents.register(
            agent_id="absolute-agent",
            name="绝对路径适配器",
            entrypoint=str(REPO_ROOT / "examples" / "external_agent" / "reference_agent.py"),
            class_name="ReferenceAgent",
        )
    _register(agents)
    with pytest.raises(AdapterCapabilityError, match="不兼容"):
        agents.binding("external-demo", "tasks/missing.yaml")


def test_external_adapter_templates_enforce_distinct_capabilities(tmp_path: Path) -> None:
    _workspace(tmp_path)
    shutil.copyfile(
        REPO_ROOT / "tasks" / "langgraph_write.yaml",
        tmp_path / "tasks" / "langgraph_write.yaml",
    )
    agents = ExternalAgentService(tmp_path)
    args_agent = agents.register(
        agent_id="args-agent",
        name="参数边界模板",
        entrypoint="examples/external_agent/reference_agent.py",
        class_name="ToolArgsReferenceAgent",
    )
    result_agent = agents.register(
        agent_id="result-agent",
        name="工具结果模板",
        entrypoint="examples/external_agent/reference_agent.py",
        class_name="ToolResultReferenceAgent",
    )

    assert [task["task_id"] for task in args_agent["compatible_tasks"]] == ["local_write"]
    assert [task["task_id"] for task in result_agent["compatible_tasks"]] == ["langgraph_write_error"]
    with pytest.raises(AdapterCapabilityError, match="不兼容"):
        agents.binding("result-agent", "tasks/local_write.yaml")

    host, task, public = agents.binding("result-agent", "tasks/langgraph_write.yaml")
    experiments = ExperimentService(tmp_path)
    state = _wait(
        experiments,
        experiments.start_external_task(
            host=host,
            task=task,
            task_path="tasks/langgraph_write.yaml",
            public=public,
        )["batch_id"],
    )
    assert state["status"] == "completed", state["error"]
    assert state["tasks"][0]["run_id"] is not None
    manifest = json.loads(
        (tmp_path / "runs" / state["tasks"][0]["run_id"] / "run.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["injection_applied"] is True


def test_external_adapter_without_injection_evidence_fails_closed(tmp_path: Path) -> None:
    _workspace(tmp_path)
    bad_source = '''from faultlattice.host import HostRunResult
class BadAgent:
    name = "bad_external_agent"
    package_version = "1"
    host_commit = None
    capabilities = {"modes": ["M0"], "injection_points": ["tool_args"], "tools": ["write_file"]}
    def preflight(self, fault):
        return None
    def run_script(self, script, *, fault=None, sandbox):
        return HostRunResult(framework_outcome="completed", final_answer="done", events=[])
'''
    (tmp_path / "examples" / "external_agent" / "bad_agent.py").write_text(bad_source)
    agents = ExternalAgentService(tmp_path)
    public = agents.register(
        agent_id="bad-agent",
        name="缺少注入证据的 Agent",
        entrypoint="examples/external_agent/bad_agent.py",
        class_name="BadAgent",
    )
    host, task, public = agents.binding("bad-agent", "tasks/local_write.yaml")
    experiments = ExperimentService(tmp_path)
    state = _wait(
        experiments,
        experiments.start_external_task(
            host=host,
            task=task,
            task_path="tasks/local_write.yaml",
            public=public,
        )["batch_id"],
    )
    assert state["status"] == "failed"
    assert "未提供有效注入证据" in state["tasks"][0]["error"]
    assert state["tasks"][0]["run_id"] is not None
    assert state["tasks"][0]["events"]
    assert state["tasks"][0]["judgements"]


def test_external_agent_api_registers_preflights_and_starts_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _workspace(tmp_path)
    agents = ExternalAgentService(tmp_path)
    experiments = ExperimentService(tmp_path)
    monkeypatch.setattr(app_module, "external_agent_service", agents)
    monkeypatch.setattr(app_module, "experiment_service", experiments)
    client = TestClient(app_module.app)

    assert client.get("/api/external-agents").json() == []
    registered = client.post(
        "/api/external-agents/register",
        json={
            "agent_id": "external-demo",
            "name": "外部测试 Agent",
            "entrypoint": "examples/external_agent/reference_agent.py",
            "class_name": "ReferenceAgent",
        },
    )
    assert registered.status_code == 200, registered.text
    preflight = client.post("/api/external-agents/external-demo/preflight")
    assert preflight.status_code == 200
    assert preflight.json()["compatible_tasks"][0]["path"] == "tasks/local_write.yaml"
    started = client.post(
        "/api/external-agents/external-demo/run",
        json={"task_path": "tasks/local_write.yaml"},
    )
    assert started.status_code == 200, started.text
    assert _wait(experiments, started.json()["batch_id"])["status"] == "completed"
    assert client.post("/api/external-agents/missing/preflight").status_code == 404
