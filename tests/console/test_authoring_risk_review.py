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


@pytest.mark.parametrize(
    ("statement", "expected"),
    [
        ("subprocess.run(['whoami'])", "subprocess.run"),
        ("subprocess.call(['whoami'])", "subprocess.call"),
        ("subprocess.check_call(['whoami'])", "subprocess.check_call"),
        ("subprocess.check_output(['whoami'])", "subprocess.check_output"),
        ("subprocess.Popen(['whoami'])", "subprocess.Popen"),
        ("os.system('whoami')", "os.system"),
        ("os.popen('whoami')", "os.popen"),
        ("os.spawnl(0, 'whoami')", "os.spawnl"),
        ("os.spawnlp(0, 'whoami')", "os.spawnlp"),
        ("os.spawnv(0, 'whoami', [])", "os.spawnv"),
        ("os.spawnvp(0, 'whoami', [])", "os.spawnvp"),
        ("os.posix_spawn('whoami', [], {})", "os.posix_spawn"),
        ("os.posix_spawnp('whoami', [], {})", "os.posix_spawnp"),
        ("shutil.rmtree('output')", "shutil.rmtree"),
    ],
)
def test_direct_process_and_recursive_delete_calls_are_blocked(
    statement: str, expected: str
) -> None:
    content = (
        "import os, shutil, subprocess\n"
        "class Adapter:\n"
        "    def run_script(self):\n"
        f"        return {statement}\n"
        "    def preflight(self):\n"
        "        return None\n"
    )
    assert inspect_adapter_source(content)["blockers"] == [expected]


@pytest.mark.parametrize(
    ("imports", "statement", "expected"),
    [
        ("import subprocess as sp", "sp.run(['whoami'])", "subprocess.run"),
        ("import os as operating_system", "operating_system.system('x')", "os.system"),
        ("import shutil as sh", "sh.rmtree('output')", "shutil.rmtree"),
        ("from subprocess import run as launch", "launch(['whoami'])", "subprocess.run"),
        ("from subprocess import check_output", "check_output(['whoami'])", "subprocess.check_output"),
        ("from os import posix_spawn as spawn", "spawn('whoami', [], {})", "os.posix_spawn"),
        ("from shutil import rmtree as remove_tree", "remove_tree('output')", "shutil.rmtree"),
    ],
)
def test_import_aliases_resolve_to_their_dangerous_qualified_call(
    imports: str, statement: str, expected: str
) -> None:
    content = (
        f"{imports}\n"
        "class Adapter:\n"
        "    def run_script(self):\n"
        f"        return {statement}\n"
        "    def preflight(self):\n"
        "        return None\n"
    )
    assert inspect_adapter_source(content)["blockers"] == [expected]


def test_dynamic_process_lookup_remains_a_review_warning_not_a_sandbox_claim() -> None:
    content = (
        "import subprocess\n"
        "class Adapter:\n"
        "    def run_script(self):\n"
        "        return getattr(subprocess, 'run')(['whoami'])\n"
        "    def preflight(self):\n"
        "        return None\n"
    )
    inspected = inspect_adapter_source(content)
    assert inspected["blockers"] == []
    assert any("getattr" in warning for warning in inspected["warnings"])


def test_private_directory_name_above_workspace_does_not_block_source(tmp_path: Path) -> None:
    root = tmp_path / "runs" / "project"
    root.mkdir(parents=True)
    (root / "README.md").write_text("# Trusted project notes", encoding="utf-8")
    service = _service(root)

    documents, manifest, _ = service._sources(["README.md"])
    assert "Trusted project notes" in documents
    assert manifest[0]["path"] == "README.md"
