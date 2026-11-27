"""自定义任务、标准任务包与 AI 草案的契约和边界测试。"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from console.server.authoring import (
    AdapterDraftRequest,
    AIAuthoringService,
    SaveAdapterDraftRequest,
    TaskAuthoringService,
    TaskDraftRequest,
    TextFileUploadRequest,
    inspect_adapter_source,
)
from console.server.external_agents import ExternalAgentService
from console.server.models import LLMOption
from faultlattice.errors import ConfigurationError

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _workspace(root: Path) -> ExternalAgentService:
    (root / "tasks").mkdir()
    (root / "examples" / "external_agent").mkdir(parents=True)
    shutil.copyfile(
        REPO_ROOT / "examples" / "external_agent" / "reference_agent.py",
        root / "examples" / "external_agent" / "reference_agent.py",
    )
    (root / "README.md").write_text("# 示例 Agent\n使用真实工具并完成文件写入。", encoding="utf-8")
    agents = ExternalAgentService(root)
    agents.register(
        agent_id="external-demo",
        name="外部测试 Agent",
        entrypoint="examples/external_agent/reference_agent.py",
        class_name="ReferenceAgent",
    )
    return agents


def _draft(task_id: str = "custom-baseline") -> dict:
    return {
        "task_id": task_id,
        "description": "执行一次真实文件写入并核对结构化事件。",
        "tool_name": "write_file",
        "arguments": {"content": "custom task content\n"},
        "path_argument": "path",
        "file_path": "output/custom.txt",
        "content_contains": "custom task content",
        "final_answer": "已写入 output/custom.txt。",
        "expected_behavior": "文件存在且内容匹配时才允许报告完成。",
        "fault_kind": "none",
    }


def test_custom_task_create_list_match_and_delete(tmp_path: Path) -> None:
    agents = _workspace(tmp_path)
    service = TaskAuthoringService(tmp_path, agents)
    created = service.create("external-demo", _draft())

    assert created["path"] == "tasks/custom/custom-baseline.yaml"
    assert created["task"]["oracle"]["validation"] == "unvalidated"
    assert service.list_custom()[0]["task_id"] == "custom-baseline"
    public = agents.list()[0]
    custom = next(task for task in public["compatible_tasks"] if task["task_id"] == "custom-baseline")
    assert custom["origin"] == "custom"
    host, task, _ = agents.binding("external-demo", custom["path"])
    assert host.name == "reference_external_agent"
    assert task.fault is None

    with pytest.raises(ConfigurationError, match="已存在"):
        service.create("external-demo", _draft())
    service.delete("custom-baseline")
    assert service.list_custom() == []
    with pytest.raises(ConfigurationError, match="tasks/custom"):
        service.delete("custom-baseline")


def test_standard_pack_is_capability_aware_and_idempotent(tmp_path: Path) -> None:
    agents = _workspace(tmp_path)
    service = TaskAuthoringService(tmp_path, agents)
    first = service.standard_pack("external-demo")
    second = service.standard_pack("external-demo")

    assert len(first["created"]) == 5
    assert first["skipped"] == []
    assert second["created"] == []
    assert len(second["skipped"]) == 5
    assert len(service.list_custom()) == 5

    agents.register(
        agent_id="args-only",
        name="仅参数边界",
        entrypoint="examples/external_agent/reference_agent.py",
        class_name="ToolArgsReferenceAgent",
    )
    limited = service.standard_pack("args-only")
    assert len(limited["created"]) == 2
    assert all("result" not in path for path in limited["created"])


def test_task_validation_rejects_undeclared_tools_and_faults(tmp_path: Path) -> None:
    agents = _workspace(tmp_path)
    service = TaskAuthoringService(tmp_path, agents)
    with pytest.raises(ConfigurationError, match="不在"):
        service.create("external-demo", {**_draft(), "tool_name": "delete_everything"})
    with pytest.raises(ConfigurationError, match="相对路径"):
        service.create("external-demo", {**_draft(), "file_path": "../outside.txt"})


def test_adapter_static_check_and_budgets(tmp_path: Path) -> None:
    agents = _workspace(tmp_path)
    tasks = TaskAuthoringService(tmp_path, agents)
    service = AIAuthoringService(tmp_path, tasks)
    source = """from examples.external_agent.reference_agent import ReferenceAgent
class MyAdapter(ReferenceAgent):
    capabilities = {'modes': ['M0'], 'injection_points': [], 'tools': ['write_file']}
"""
    inspected = inspect_adapter_source(source)
    assert inspected["class_name"] == "MyAdapter"
    assert len(inspected["warnings"]) == 2
    with pytest.raises(ConfigurationError, match="语法错误"):
        inspect_adapter_source("class Broken(:\n")

    request = AdapterDraftRequest(source_paths=["README.md"], agent_goal="接入一个真实文件写入 Agent")
    documents, manifest, total = service._sources(request.source_paths)
    assert "untrusted_agent_document" in documents
    assert manifest == [{"path": "README.md", "characters": total, "truncated": False}]
    with pytest.raises(ConfigurationError, match="允许扩展名"):
        service._sources([".env"])
    with pytest.raises(ConfigurationError, match="越出项目"):
        service._sources(["../README.md"])


def test_ai_adapter_is_only_an_editable_draft_until_explicit_save(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agents = _workspace(tmp_path)
    tasks = TaskAuthoringService(tmp_path, agents)
    service = AIAuthoringService(tmp_path, tasks)
    code = """from examples.external_agent.reference_agent import ReferenceAgent
class GeneratedAdapter(ReferenceAgent):
    # TODO: 用真实 Agent 循环替换继承的参考循环。
    capabilities = {'modes': ['M0'], 'injection_points': ['tool_result'], 'tools': ['write_file']}
"""
    option = LLMOption("test", "测试模型", "test-model", None, ("chat",), "secret")

    class FakeModel:
        def generate(self, messages: list[dict], *, tools: list[dict]) -> SimpleNamespace:
            assert tools == []
            assert "不可信资料" in messages[0]["content"]
            assert "untrusted_agent_document" in messages[1]["content"]
            return SimpleNamespace(content=f"```python\n{code}```")

    monkeypatch.setattr(service, "_model", lambda option_id, *, max_tokens: (FakeModel(), option))
    result = service.adapter_draft(
        AdapterDraftRequest(source_paths=["README.md"], agent_goal="根据说明生成文件写入 Agent 适配器")
    )
    assert result["class_name"] == "GeneratedAdapter"
    assert result["model_option_id"] == "test"
    assert not (tmp_path / "external_agents" / "drafts").exists()

    saved = service.save_adapter(
        SaveAdapterDraftRequest(
            agent_id="generated-agent", class_name="GeneratedAdapter", content=result["content"]
        )
    )
    assert saved["entrypoint"] == "external_agents/drafts/generated-agent.py"
    assert "尚未登记" in saved["message"]
    assert [item["id"] for item in agents.list()] == ["external-demo"]


def test_ai_task_draft_is_validated_but_not_saved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    agents = _workspace(tmp_path)
    tasks = TaskAuthoringService(tmp_path, agents)
    service = AIAuthoringService(tmp_path, tasks)
    option = LLMOption("test", "测试模型", "test-model", None, ("chat",), "secret")

    class FakeModel:
        def generate(self, messages: list[dict], *, tools: list[dict]) -> SimpleNamespace:
            assert tools == []
            assert "untrusted_goal" in messages[1]["content"]
            return SimpleNamespace(content=json.dumps(_draft("ai-task"), ensure_ascii=False))

    monkeypatch.setattr(service, "_model", lambda option_id, *, max_tokens: (FakeModel(), option))
    result = service.task_draft(
        TaskDraftRequest(agent_id="external-demo", goal="生成一个可复核的文件写入基线任务")
    )
    assert result["draft"]["task_id"] == "ai-task"
    assert tasks.list_custom() == []


def test_authoring_model_uses_bounded_non_m3_sampling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agents = _workspace(tmp_path)
    service = AIAuthoringService(tmp_path, TaskAuthoringService(tmp_path, agents))
    option = LLMOption(
        "deepseek",
        "测试思考模型",
        "deepseek-flash",
        None,
        ("chat",),
        "secret",
        reasoning_mode="enabled",
        sampling_params={"temperature": 0.4, "max_tokens": 999},
        advisor_sampling_params={"reasoning_effort": "low"},
    )
    monkeypatch.setattr("console.server.authoring.resolve_advisor_option", lambda _: option)

    model, resolved = service._model("deepseek", max_tokens=16_000)

    assert resolved is option
    assert model.reasoning_mode == "enabled"
    assert model.sampling_params == {
        "temperature": 0.4,
        "reasoning_effort": "low",
        "max_tokens": 16_000,
    }


def test_ai_adapter_reports_reasoning_only_response_without_saving(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from faultlattice.errors import ModelProviderError

    agents = _workspace(tmp_path)
    service = AIAuthoringService(tmp_path, TaskAuthoringService(tmp_path, agents))
    option = LLMOption("test", "测试模型", "test-model", None, ("chat",), "secret")

    class ReasoningOnlyModel:
        def generate(self, messages: list[dict], *, tools: list[dict]) -> SimpleNamespace:
            return SimpleNamespace(content="", reasoning_content="仅用于测试的思考内容")

    monkeypatch.setattr(
        service, "_model", lambda option_id, *, max_tokens: (ReasoningOnlyModel(), option)
    )
    with pytest.raises(ModelProviderError, match="仅收到思考内容"):
        service.adapter_draft(
            AdapterDraftRequest(source_paths=["README.md"], agent_goal="生成一个文件写入适配器草案")
        )
    assert not (tmp_path / "external_agents" / "drafts").exists()


def test_adapter_static_check_skips_auxiliary_classes() -> None:
    source = """from dataclasses import dataclass
@dataclass
class InjectionEvent:
    original: object
    replacement: object

class HostAdapter(ReferenceAgent):
    def preflight(self, fault):
        return None

    def run_script(self, script, *, fault=None, sandbox):
        return []
"""
    inspected = inspect_adapter_source(source)
    assert inspected["class_name"] == "HostAdapter"
    assert inspected["warnings"] == []


def test_task_file_upload_is_editable_and_not_saved(tmp_path: Path) -> None:
    agents = _workspace(tmp_path)
    service = TaskAuthoringService(tmp_path, agents)
    result = service.import_draft(
        TextFileUploadRequest(filename="task.yaml", content=yaml.safe_dump(_draft("uploaded-task")))
    )

    assert result["draft"]["task_id"] == "uploaded-task"
    assert "尚未保存" in result["notice"]
    assert service.list_custom() == []

    created = service.create("external-demo", result["draft"])
    full = service.import_draft(
        TextFileUploadRequest(
            filename="task.json",
            content=json.dumps(created["task"], ensure_ascii=False),
        )
    )
    assert full["draft"]["task_id"] == "uploaded-task"
    assert full["draft"]["file_path"] == "output/custom.txt"
    with pytest.raises(ConfigurationError, match="仅支持"):
        service.import_draft(TextFileUploadRequest(filename="task.txt", content="task_id: nope"))


def test_adapter_reference_upload_uses_private_project_upload_area(tmp_path: Path) -> None:
    agents = _workspace(tmp_path)
    service = AIAuthoringService(tmp_path, TaskAuthoringService(tmp_path, agents))
    uploaded = service.upload_source(
        TextFileUploadRequest(filename="AGENT.md", content="# Agent\n真实写文件。")
    )

    path = tmp_path / uploaded["path"]
    assert uploaded["filename"] == "AGENT.md"
    assert uploaded["path"].startswith("external_agents/uploads/")
    assert path.read_text(encoding="utf-8") == "# Agent\n真实写文件。"
    assert len(agents.list()) == 1
    with pytest.raises(ConfigurationError, match="文件名"):
        service.upload_source(TextFileUploadRequest(filename="../secret.md", content="不得写入"))
    with pytest.raises(ConfigurationError, match="扩展名"):
        service.upload_source(TextFileUploadRequest(filename="credentials.env", content="SECRET=x"))
