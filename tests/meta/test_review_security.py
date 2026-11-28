"""互评提出的本地适配器与 AI 资料边界回归。"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from console.server.authoring import (
    AIAuthoringService,
    SaveAdapterDraftRequest,
    TaskAuthoringService,
)
from console.server.external_agents import ExternalAgentService
from faultlattice.errors import ConfigurationError


def _registry(root: Path, entrypoint: str) -> None:
    path = root / "external_agents" / "registry.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(
        yaml.safe_dump(
            {
                "agents": [
                    {
                        "id": "review-agent",
                        "name": "互评安全夹具",
                        "entrypoint": entrypoint,
                        "class_name": "ReviewAgent",
                        "created_at": "2026-11-28T00:00:00Z",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def test_listing_agents_never_executes_adapter_module(tmp_path: Path) -> None:
    marker = tmp_path / "module-executed.txt"
    source = tmp_path / "agent.py"
    source.write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n"
        "class ReviewAgent:\n    pass\n",
        encoding="utf-8",
    )
    _registry(tmp_path, "agent.py")

    listed = ExternalAgentService(tmp_path).list()

    assert listed[0]["status"] == "registered"
    assert listed[0]["compatible_tasks"] == []
    assert not marker.exists()


def test_uploaded_python_file_cannot_be_registered_as_entrypoint(tmp_path: Path) -> None:
    uploaded = tmp_path / "external_agents" / "uploads" / "review" / "agent.py"
    uploaded.parent.mkdir(parents=True)
    uploaded.write_text("class ReviewAgent:\n    pass\n", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="上传资料区"):
        ExternalAgentService(tmp_path).register(
            agent_id="review-agent",
            name="不可执行的上传资料",
            entrypoint="external_agents/uploads/review/agent.py",
            class_name="ReviewAgent",
        )


@pytest.mark.parametrize("filename", ["secrets.json", "config.toml"])
def test_sensitive_or_general_config_is_not_sent_to_ai(
    tmp_path: Path, filename: str
) -> None:
    (tmp_path / filename).write_text("private = true\n", encoding="utf-8")
    agents = ExternalAgentService(tmp_path)
    tasks = TaskAuthoringService(tmp_path, agents)
    service = AIAuthoringService(tmp_path, tasks)

    with pytest.raises(ConfigurationError, match="不得发送给模型|默认只接受"):
        service._sources([filename])


def test_high_risk_ai_adapter_draft_is_not_saved(tmp_path: Path) -> None:
    agents = ExternalAgentService(tmp_path)
    tasks = TaskAuthoringService(tmp_path, agents)
    service = AIAuthoringService(tmp_path, tasks)
    content = (
        "import subprocess\n"
        "class ReviewAgent:\n"
        "    def run_script(self):\n"
        "        return subprocess.run(['whoami'])\n"
        "    def preflight(self, fault=None):\n"
        "        return None\n"
    )

    with pytest.raises(ConfigurationError, match="高风险"):
        service.save_adapter(
            SaveAdapterDraftRequest(
                agent_id="review-agent", class_name="ReviewAgent", content=content
            )
        )
    assert not (tmp_path / "external_agents" / "drafts" / "review-agent.py").exists()
