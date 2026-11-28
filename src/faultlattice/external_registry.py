"""外部 Agent 适配器登记、真实加载、能力预检与兼容任务筛选。

这里接入的是实现 HostAdapter 的本地 Python 宿主，不是普通聊天模型端点。
适配器文件必须位于项目内；登记和预检会执行其模块顶层代码与构造函数，
因此只能接入用户明确信任的代码。运行证据仍由 runner 和 Oracle 独立核验。
"""

from __future__ import annotations

import importlib.util
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from faultlattice.canonical import atomic_write, sha256_hex
from faultlattice.errors import AdapterCapabilityError, ConfigurationError, FaultLatticeError
from faultlattice.host import CounterfactualHost, HostAdapter
from faultlattice.runner import load_task
from faultlattice.schemas import ExecutionMode, InjectionPoint, TaskDefinition


class ExternalCapabilities(BaseModel):
    """外部宿主必须显式声明的能力；未声明的能力一律视为不支持。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    modes: list[ExecutionMode] = Field(min_length=1)
    injection_points: list[InjectionPoint] = Field(default_factory=list)
    tools: list[str] = Field(min_length=1)


class ExternalRegistration(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(pattern=r"^[a-z][a-z0-9-]{1,49}$")
    name: str = Field(min_length=1, max_length=80)
    entrypoint: str = Field(min_length=1, max_length=240)
    class_name: str = Field(min_length=1, max_length=120)
    created_at: datetime


_EXTERNAL_ID = re.compile(r"^[a-z][a-z0-9-]{1,49}$")


class ExternalRegistry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    agents: list[ExternalRegistration] = Field(default_factory=list)


class ExternalAgentService:
    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.registry_path = self.root / "external_agents" / "registry.yaml"
        # 只有显式登记、预检或运行才执行适配器；列表只读缓存和登记元数据。
        self._inspections: dict[str, dict[str, Any]] = {}

    def _safe_error(self, exc: BaseException) -> str:
        return str(exc).replace(str(self.root), "<workspace>")

    def _resolve_entrypoint(self, relative: str) -> Path:
        candidate = Path(relative)
        if candidate.is_absolute() or candidate.suffix != ".py":
            raise ConfigurationError("适配器入口必须是项目内的相对 .py 文件路径")
        if candidate.parts[:2] == ("external_agents", "uploads"):
            raise ConfigurationError("上传资料区不可作为可执行适配器入口；请人工审查并保存为草案")
        path = (self.root / candidate).resolve()
        if self.root not in path.parents:
            raise ConfigurationError("适配器入口不得越出项目根目录")
        if not path.is_file():
            raise ConfigurationError(f"适配器入口不存在: {candidate.as_posix()}")
        return path

    def _registry(self) -> ExternalRegistry:
        if not self.registry_path.is_file():
            return ExternalRegistry()
        try:
            raw = yaml.safe_load(self.registry_path.read_text(encoding="utf-8"))
            return ExternalRegistry.model_validate(raw)
        except (OSError, yaml.YAMLError, ValidationError) as exc:
            raise ConfigurationError(f"外部 Agent 登记无法加载: {self._safe_error(exc)}") from exc

    def _save_registry(self, registry: ExternalRegistry) -> None:
        payload = yaml.safe_dump(registry.model_dump(mode="json"), allow_unicode=True, sort_keys=False)
        try:
            atomic_write(self.registry_path, payload.encode("utf-8"))
        except OSError as exc:
            raise ConfigurationError(f"外部 Agent 登记保存失败: {self._safe_error(exc)}") from exc

    def _registration(self, agent_id: str) -> ExternalRegistration:
        registration = next((item for item in self._registry().agents if item.id == agent_id), None)
        if registration is None:
            raise ConfigurationError(f"未知外部 Agent: {agent_id}")
        return registration

    def _load_host(self, registration: ExternalRegistration) -> tuple[HostAdapter, ExternalCapabilities, str]:
        path = self._resolve_entrypoint(registration.entrypoint)
        try:
            source = path.read_bytes()
        except OSError as exc:
            raise AdapterCapabilityError(f"适配器源码读取失败: {self._safe_error(exc)}") from exc
        source_hash = sha256_hex(source)
        module_name = f"faultlattice_external_{registration.id.replace('-', '_')}_{source_hash[:12]}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, path)
            if spec is None or spec.loader is None:
                raise AdapterCapabilityError("无法为适配器创建 Python 加载器")
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            factory = getattr(module, registration.class_name)
            host = factory()
        except Exception as exc:
            sys.modules.pop(module_name, None)
            raise AdapterCapabilityError(
                f"外部适配器加载失败: {type(exc).__name__}: {self._safe_error(exc)}"
            ) from exc

        if not isinstance(host, HostAdapter):
            raise AdapterCapabilityError(
                f"{registration.class_name} 未实现 HostAdapter 的 name、版本字段与 run_script"
            )
        preflight = getattr(host, "preflight", None)
        if not callable(preflight):
            raise AdapterCapabilityError("外部适配器必须实现 preflight(fault)，不支持时必须显式报错")
        raw_capabilities = getattr(host, "capabilities", None)
        if callable(raw_capabilities):
            raw_capabilities = raw_capabilities()
        try:
            capabilities = ExternalCapabilities.model_validate(raw_capabilities)
            preflight(None)
        except Exception as exc:
            # 第三方构造后的基础预检异常也必须成为当前适配器的局部错误。
            raise AdapterCapabilityError(f"外部适配器基础预检失败: {self._safe_error(exc)}") from exc
        return host, capabilities, source_hash

    @staticmethod
    def _script_tools(task: TaskDefinition) -> set[str]:
        return {
            str(item["tool_call"]["name"])
            for item in task.script
            if isinstance(item, dict) and isinstance(item.get("tool_call"), dict)
        }

    def _compatible_tasks(
        self, host: HostAdapter, capabilities: ExternalCapabilities
    ) -> list[dict[str, Any]]:
        tasks_root = self.root / "tasks"
        compatible: list[dict[str, Any]] = []
        # 内置任务与 tasks/custom 中经契约校验的用户任务共用同一筛选和绑定链。
        for path in sorted(tasks_root.rglob("*.yaml")):
            try:
                original = load_task(path)
                if original.mode not in capabilities.modes:
                    continue
                if original.mode is ExecutionMode.M3 and not isinstance(host, CounterfactualHost):
                    continue
                if not self._script_tools(original) <= set(capabilities.tools):
                    continue
                if (
                    original.fault is not None
                    and original.fault.injection_point not in capabilities.injection_points
                ):
                    continue
                preflight = getattr(host, "preflight", None)
                if not callable(preflight):
                    continue
                preflight(original.fault)
            except Exception:
                # 第三方 preflight 的任意普通异常只排除当前任务，不应变成接口 500。
                # KeyboardInterrupt / SystemExit 等 BaseException 不在此吞掉。
                continue
            compatible.append(
                {
                    "path": path.relative_to(self.root).as_posix(),
                    "task_id": original.task_id,
                    "origin": "custom" if path.parent.name == "custom" else "builtin",
                    "description": original.description,
                    "expected_behavior": original.expected_behavior,
                    "mode": original.mode.value,
                    "target_layers": [layer.value for layer in original.target_layers],
                    "fault": (original.fault.model_dump(mode="json") if original.fault else None),
                }
            )
        return compatible

    def _inspect_loaded(
        self,
        registration: ExternalRegistration,
        host: HostAdapter,
        capabilities: ExternalCapabilities,
        source_hash: str,
    ) -> dict[str, Any]:
        inspected = {
            **registration.model_dump(mode="json"),
            "status": "ready",
            "error": None,
            "host_name": host.name,
            "host_package_version": host.package_version,
            "host_commit": host.host_commit,
            "source_sha256": source_hash,
            "capabilities": capabilities.model_dump(mode="json"),
            "compatible_tasks": self._compatible_tasks(host, capabilities),
        }
        self._inspections[registration.id] = inspected
        return inspected

    def _inspect(self, registration: ExternalRegistration) -> dict[str, Any]:
        host, capabilities, source_hash = self._load_host(registration)
        return self._inspect_loaded(registration, host, capabilities, source_hash)

    def preflight(self, agent_id: str) -> dict[str, Any]:
        """显式加载一个已登记宿主；其他适配器不会被执行。"""
        return self._inspect(self._registration(agent_id))

    def invalidate_inspections(self) -> None:
        """任务集合变化后丢弃能力缓存；不加载或执行任何适配器。"""
        self._inspections.clear()

    def list(self) -> list[dict[str, Any]]:
        """只读登记、源码哈希与已有预检缓存，不执行任何适配器代码。"""
        result = []
        for registration in self._registry().agents:
            base = {
                **registration.model_dump(mode="json"),
                "status": "registered",
                "error": None,
                "host_name": None,
                "host_package_version": None,
                "host_commit": None,
                "source_sha256": None,
                "capabilities": None,
                "compatible_tasks": [],
            }
            try:
                source_hash = sha256_hex(self._resolve_entrypoint(registration.entrypoint).read_bytes())
                base["source_sha256"] = source_hash
                cached = self._inspections.get(registration.id)
                if cached is not None and cached["source_sha256"] == source_hash:
                    result.append(cached)
                    continue
                if cached is not None:
                    base["error"] = "适配器源码已变化，请显式重新预检"
            except (OSError, FaultLatticeError) as exc:
                base["status"] = "error"
                base["error"] = self._safe_error(exc)
            result.append(base)
        return result

    def register(self, *, agent_id: str, name: str, entrypoint: str, class_name: str) -> dict[str, Any]:
        if not _EXTERNAL_ID.fullmatch(agent_id):
            raise ConfigurationError("接入标识需为 2–50 位小写字母、数字或连字符，并以字母开头")
        try:
            registration = ExternalRegistration(
                id=agent_id,
                name=name.strip(),
                entrypoint=entrypoint.strip().replace("\\", "/"),
                class_name=class_name.strip(),
                created_at=datetime.now(UTC),
            )
        except ValidationError as exc:
            raise ConfigurationError(f"外部 Agent 登记字段不合法: {self._safe_error(exc)}") from exc
        registry = self._registry()
        if any(item.id == agent_id for item in registry.agents):
            raise ConfigurationError(f"接入标识已存在: {agent_id}")
        inspected = self._inspect(registration)
        self._save_registry(ExternalRegistry(agents=[*registry.agents, registration]))
        return inspected

    def binding(self, agent_id: str, task_path: str) -> tuple[HostAdapter, TaskDefinition, dict[str, Any]]:
        """返回已预检宿主及启动前冻结的任务副本，不改写原任务文件。"""
        registration = self._registration(agent_id)
        # 同一次绑定只加载一次，避免适配器顶层代码和构造函数执行两遍。
        host, capabilities, source_hash = self._load_host(registration)
        public = self._inspect_loaded(registration, host, capabilities, source_hash)
        selected = next((item for item in public["compatible_tasks"] if item["path"] == task_path), None)
        if selected is None:
            raise AdapterCapabilityError("该任务与外部宿主能力不兼容，或源码预检已失效")
        task = load_task(self.root / task_path).model_copy(update={"host": host.name})
        return host, task, public
