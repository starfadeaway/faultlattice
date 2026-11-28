"""研发视图的数据服务：项目清单、真实验收、源码与实验产物。

模块状态不读取人工填写的 status：只有源码和测试路径存在、至少声明一项
验收且全部 required_checks 实际通过时才为 verified，否则为 developing。
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

import faultlattice

ARTIFACT_FILES = ("run.json", "steps.jsonl", "oracle.jsonl", "report.md")


class ManifestError(RuntimeError):
    """项目清单或其路径配置无效。"""


class CheckDefinition(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    command: list[str] = Field(min_length=1)
    cwd: str = "."


class ModuleDefinition(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    name: str
    source_paths: list[str] = Field(min_length=1)
    test_paths: list[str] = Field(min_length=1)
    required_checks: list[str] = Field(min_length=1)
    dependencies: list[str] = Field(default_factory=list)


class ProjectManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    subtitle: str
    checks: dict[str, CheckDefinition]
    modules: list[ModuleDefinition] = Field(min_length=1)


class ProjectService:
    """从项目文件和实际子进程结果生成研发视图数据。"""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.manifest_path = self.root / "project.manifest.yaml"

    def _resolve_relative(self, relative: str) -> Path:
        candidate = (self.root / relative).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise ManifestError(f"路径越出项目根目录: {relative}")
        return candidate

    def load_manifest(self) -> ProjectManifest:
        try:
            raw = yaml.safe_load(self.manifest_path.read_text(encoding="utf-8"))
            manifest = ProjectManifest.model_validate(raw)
        except (OSError, yaml.YAMLError, ValidationError) as exc:
            raise ManifestError(f"project.manifest.yaml 无法加载: {exc}") from exc
        module_ids = [module.id for module in manifest.modules]
        if len(module_ids) != len(set(module_ids)):
            raise ManifestError("模块 id 不得重复")
        for module in manifest.modules:
            unknown = set(module.required_checks) - set(manifest.checks)
            unknown.update(set(module.dependencies) - set(module_ids))
            if unknown:
                raise ManifestError(f"模块 {module.id} 引用了未知检查或依赖: {sorted(unknown)}")
            for path in [*module.source_paths, *module.test_paths]:
                self._resolve_relative(path)
        return manifest

    def _command(self, command: Sequence[str]) -> list[str]:
        resolved = list(command)
        if resolved[0] == "python":
            resolved[0] = sys.executable
        elif resolved[0] == "npm":
            executable = shutil.which("npm.cmd" if os.name == "nt" else "npm")
            if executable is None:
                raise OSError("找不到 npm；请先安装 Node.js")
            resolved[0] = executable
        return resolved

    def _run_check(self, check_id: str, definition: CheckDefinition) -> dict[str, Any]:
        command_display = shlex.join(definition.command)
        started = time.monotonic()
        try:
            command = self._command(definition.command)
            cwd = self._resolve_relative(definition.cwd)
            completed = subprocess.run(
                command,
                cwd=cwd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=180,
                check=False,
            )
            output = (completed.stdout + completed.stderr).strip()
            returncode = completed.returncode
        except (OSError, subprocess.SubprocessError) as exc:
            output = str(exc)
            returncode = -1
        return {
            "id": check_id,
            "name": definition.name,
            "command": command_display,
            "status": "passed" if returncode == 0 else "failed",
            "returncode": returncode,
            "duration_ms": round((time.monotonic() - started) * 1000),
            "output": output[-8000:],
        }

    def _source_files(self, source_paths: Sequence[str]) -> list[str]:
        files: set[str] = set()
        for relative in source_paths:
            path = self._resolve_relative(relative)
            if path.is_file():
                files.add(path.relative_to(self.root).as_posix())
            elif path.is_dir():
                files.update(
                    item.relative_to(self.root).as_posix()
                    for item in path.rglob("*")
                    if item.is_file() and "__pycache__" not in item.parts
                )
        return sorted(files)

    def project_snapshot(self) -> dict[str, Any]:
        """执行全部指定验收并生成快照；单个检查失败会作为数据返回。"""
        manifest = self.load_manifest()
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {
                check_id: pool.submit(self._run_check, check_id, definition)
                for check_id, definition in manifest.checks.items()
            }
            check_results = {check_id: future.result() for check_id, future in futures.items()}

        modules = []
        for module in manifest.modules:
            paths_exist = all(
                self._resolve_relative(path).exists()
                for path in [*module.source_paths, *module.test_paths]
            )
            checks = [check_results[check_id] for check_id in module.required_checks]
            verified = paths_exist and all(check["status"] == "passed" for check in checks)
            modules.append(
                {
                    "id": module.id,
                    "name": module.name,
                    "source_paths": module.source_paths,
                    "test_paths": module.test_paths,
                    "source_files": self._source_files(module.source_paths),
                    "dependencies": module.dependencies,
                    "required_checks": module.required_checks,
                    "checks": checks,
                    "paths_exist": paths_exist,
                    "status": "verified" if verified else "developing",
                }
            )
        return {
            "project": {
                "name": manifest.name,
                "subtitle": manifest.subtitle,
                "version": faultlattice.__version__,
                "manifest": "project.manifest.yaml",
            },
            "summary": {
                "modules": len(modules),
                "verified": sum(module["status"] == "verified" for module in modules),
                "checks": len(check_results),
                "passed_checks": sum(
                    result["status"] == "passed" for result in check_results.values()
                ),
            },
            "checks": list(check_results.values()),
            "modules": modules,
        }

    def naming(self) -> dict[str, str]:
        path = self.root / "docs" / "NAMING.md"
        return {"path": "docs/NAMING.md", "content": path.read_text(encoding="utf-8")}

    def source(self, relative: str) -> dict[str, str]:
        """只开放清单登记的源码文件，防止任意文件读取。"""
        manifest = self.load_manifest()
        allowed = {
            file
            for module in manifest.modules
            for file in self._source_files(module.source_paths)
        }
        normalized = Path(relative).as_posix().removeprefix("./")
        if normalized not in allowed:
            raise PermissionError(f"文件不在项目清单的源码入口中: {relative}")
        path = self._resolve_relative(normalized)
        return {"path": normalized, "content": path.read_text(encoding="utf-8")}

    def artifacts(self) -> list[dict[str, Any]]:
        runs_root = self.root / "runs"
        if not runs_root.exists():
            return []
        artifacts = []
        for manifest_path in sorted(runs_root.rglob("run.json")):
            run_dir = manifest_path.parent
            item: dict[str, Any] = {
                "run_id": run_dir.name,
                "path": run_dir.relative_to(self.root).as_posix(),
                "files": [name for name in ARTIFACT_FILES if (run_dir / name).is_file()],
                "complete": all((run_dir / name).is_file() for name in ARTIFACT_FILES),
                "task_id": None,
                "description": None,
                "expected_behavior": None,
                "host": None,
                "mode": None,
                "created_at": None,
                "execution_status": "completed",
                "error": None,
            }
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
                harness_error = data.get("harness_error") or {}
                item.update(
                    run_id=data.get("run_id", run_dir.name),
                    task_id=data.get("task", {}).get("task_id"),
                    description=data.get("task", {}).get("description"),
                    expected_behavior=data.get("task", {}).get("expected_behavior"),
                    host=data.get("task", {}).get("host"),
                    mode=data.get("task", {}).get("mode"),
                    created_at=data.get("created_at"),
                    execution_status=data.get("execution_status", "completed"),
                    error=(
                        f"{harness_error.get('type', 'HarnessError')}: "
                        f"{harness_error.get('message', '未记录错误详情')}"
                        if data.get("execution_status") == "harness_failed"
                        else None
                    ),
                )
            except (OSError, json.JSONDecodeError) as exc:
                # 单个损坏产物只在自己的行内显示错误，不影响其他实验入口。
                item["error"] = str(exc)
            artifacts.append(item)
        return sorted(artifacts, key=lambda item: item["created_at"] or "", reverse=True)

    def artifact_report(self, run_id: str) -> tuple[str, str]:
        matches = [item for item in self.artifacts() if item["run_id"] == run_id]
        if not matches:
            raise FileNotFoundError(f"找不到实验运行: {run_id}")
        if len(matches) > 1:
            raise ManifestError(f"存在重复 run_id: {run_id}")
        item = matches[0]
        path = self._resolve_relative(item["path"]) / "report.md"
        return item["path"], path.read_text(encoding="utf-8")

    def public_reports(self) -> list[dict[str, str]]:
        """只列出报告索引中登记且实际存在的 external Markdown。"""
        index_path = self.root / "reports" / "README.md"
        if not index_path.is_file():
            return []
        external_root = (self.root / "reports" / "external").resolve()
        reports: list[dict[str, str]] = []
        seen: set[str] = set()
        for line in index_path.read_text(encoding="utf-8").splitlines():
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if len(cells) != 5:
                continue
            match = re.fullmatch(r"\[[^\]]+\]\(([^)]+\.md)\)", cells[4])
            if match is None:
                continue
            try:
                path = self._resolve_relative(f"reports/{match.group(1)}")
            except ManifestError:
                continue
            if external_root not in path.parents or not path.is_file():
                continue
            relative = path.relative_to(self.root / "reports").as_posix()
            if relative in seen:
                continue
            seen.add(relative)
            reports.append(
                {
                    "path": relative,
                    "title": cells[1],
                    "date": cells[0],
                    "host": cells[2],
                    "summary": cells[3],
                }
            )
        return reports

    def public_report(self, relative: str) -> tuple[str, str]:
        matches = [item for item in self.public_reports() if item["path"] == relative]
        if not matches:
            raise PermissionError(f"报告未在公开索引中登记: {relative}")
        path = self._resolve_relative(f"reports/{relative}")
        return f"reports/{relative}", path.read_text(encoding="utf-8")
