"""草案静态检查：硬阻断与经人工确认的普通复核警告分离。"""

from pathlib import Path

import pytest

from console.server.authoring import (
    AIAuthoringService,
    SaveAdapterDraftRequest,
    TaskAuthoringService,
    inspect_adapter_source,
)
from faultlattice.errors import ConfigurationError
from faultlattice.external_registry import ExternalAgentService


def _service(root: Path) -> AIAuthoringService:
    agents = ExternalAgentService(root)
    return AIAuthoringService(root, TaskAuthoringService(root, agents))


def test_normal_agent_run_requires_confirmation_but_can_be_saved(tmp_path: Path) -> None:
    service = _service(tmp_path)
    content = (
        "class Adapter:\n"
        "    def run_script(self):\n"
        "        return self.agent.run('do the task')\n"
        "    def preflight(self, fault=None):\n"
        "        return None\n"
    )
    inspected = inspect_adapter_source(content, "Adapter")
    assert inspected["blockers"] == []
    request = SaveAdapterDraftRequest(
        agent_id="normal-run", class_name="Adapter", content=content
    )
    with pytest.raises(ConfigurationError, match="人工复核"):
        service.save_adapter(request)

    saved = service.save_adapter(request.model_copy(update={"allow_reviewed_risks": True}))
    assert Path(saved["entrypoint"]).name == "normal-run.py"


def test_hard_blocker_cannot_be_confirmed_through(tmp_path: Path) -> None:
    service = _service(tmp_path)
    content = (
        "import subprocess\n"
        "class Adapter:\n"
        "    def run_script(self):\n"
        "        return subprocess.run(['whoami'])\n"
        "    def preflight(self, fault=None):\n"
        "        return None\n"
    )
    with pytest.raises(ConfigurationError, match="硬阻断"):
        service.save_adapter(
            SaveAdapterDraftRequest(
                agent_id="hard-block",
                class_name="Adapter",
                content=content,
                allow_reviewed_risks=True,
            )
        )


def test_private_directory_name_above_workspace_does_not_block_source(tmp_path: Path) -> None:
    root = tmp_path / "runs" / "project"
    root.mkdir(parents=True)
    (root / "README.md").write_text("# Trusted project notes", encoding="utf-8")
    service = _service(root)

    documents, manifest, _ = service._sources(["README.md"])
    assert "Trusted project notes" in documents
    assert manifest[0]["path"] == "README.md"
