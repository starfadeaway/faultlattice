"""Anchorline 0.1.0 的真实 memory_write 工具边界适配器（人工复核稿）。

仅接入 M0 预设脚本，不调用模型，不冒充 LangGraph 真实模型循环。
生产工具来自 anchorline.tools.build_tools；Oracle 在提交后另开只读会话核验。
"""

from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any

from faultlattice.errors import AdapterCapabilityError, ConfigurationError
from faultlattice.faults import build_fault_effect
from faultlattice.host import HostRunResult, PostconditionObservation
from faultlattice.schemas import ExpectedPostcondition, FaultSpec, InjectionPoint


class AnchorlineHostAdapter:
    name = "anchorline"
    package_version = "0.1.0"
    host_commit = None
    capabilities = {
        "modes": ["M0"],
        "injection_points": ["tool_result"],
        "tools": ["memory_write"],
    }

    @staticmethod
    def _root() -> Path:
        return Path(__file__).resolve().parents[2]

    @staticmethod
    def _configure_embedding() -> None:
        """显式桥接向量配置；不得回退读取 Anchorline 原项目的 .env。"""
        prefix = "FAULTLATTICE_LLM_SILICONFLOW_"
        target_names = (
            "SILICONFLOW_API_KEY",
            "SILICONFLOW_BASE_URL",
            "SILICONFLOW_EMBEDDING_MODEL",
        )
        for name in target_names:
            os.environ[name] = ""
        api_key = os.environ.get(prefix + "API_KEY", "").strip()
        base_url = os.environ.get(prefix + "BASE_URL", "").strip()
        model_id = os.environ.get(prefix + "MODEL_ID", "").strip()
        capabilities = {
            item.strip().lower()
            for item in os.environ.get(prefix + "CAPABILITIES", "").split(",")
            if item.strip()
        }
        if not any((api_key, base_url, model_id, *capabilities)):
            return
        if "embedding" not in capabilities or not all((api_key, base_url, model_id)):
            raise ConfigurationError("Anchorline 向量索引需要完整的硅基流动 embedding 配置")
        if model_id != "BAAI/bge-m3":
            raise ConfigurationError("Anchorline 验收向量模型冻结为 BAAI/bge-m3，不能静默替换")
        os.environ.update(
            {
                "SILICONFLOW_API_KEY": api_key,
                "SILICONFLOW_BASE_URL": base_url,
                "SILICONFLOW_EMBEDDING_MODEL": model_id,
            }
        )

    @classmethod
    def _prepare_imports(cls) -> None:
        source = cls._root() / "external_projects" / "anchorline" / "src"
        if not source.is_dir():
            raise ConfigurationError("Anchorline 工作区源码副本不存在")
        sys.path.insert(0, str(source)) if str(source) not in sys.path else None
        # 索引副作用限制在工作区；store.py 读取 ANCHORLINE_LANCEDB 而非设置项。
        index_root = str(cls._root() / ".verify" / "anchorline-lancedb")
        os.environ["ANCHORLINE_LANCEDB"] = index_root
        os.environ["LANCEDB_URI"] = index_root
        os.environ["LOREKEEPER_LANCE_DIR"] = ""
        cls._configure_embedding()

    @staticmethod
    def _mysql_settings() -> dict[str, Any]:
        user = os.environ.get("FAULTLATTICE_MYSQL_USER", "").strip()
        if not user:
            raise ConfigurationError("Anchorline 需要本机 FAULTLATTICE_MYSQL_USER 配置")
        try:
            port = int(os.environ.get("FAULTLATTICE_MYSQL_PORT", "3306"))
        except ValueError as exc:
            raise ConfigurationError("FAULTLATTICE_MYSQL_PORT 必须是整数") from exc
        return {
            "mysql_host": os.environ.get("FAULTLATTICE_MYSQL_HOST", "127.0.0.1").strip(),
            "mysql_port": port,
            "mysql_database": os.environ.get(
                "FAULTLATTICE_ANCHORLINE_DATABASE", "anchorline_faultlattice"
            ).strip(),
            "mysql_user": user,
            "mysql_password": os.environ.get("FAULTLATTICE_MYSQL_PASSWORD", ""),
        }

    @classmethod
    def _session_factory(cls):
        cls._prepare_imports()
        try:
            config = importlib.import_module("anchorline.config")
            db = importlib.import_module("sqlalchemy")
            orm = importlib.import_module("sqlalchemy.orm")
            settings = config.Settings(**cls._mysql_settings())
            engine = db.create_engine(settings.mysql_dsn, pool_pre_ping=True)
            return orm.sessionmaker(bind=engine, expire_on_commit=False), engine
        except ConfigurationError:
            raise
        except Exception as exc:
            raise ConfigurationError(
                f"Anchorline 数据库初始化失败（{type(exc).__name__}）"
            ) from exc

    def preflight(self, fault: FaultSpec | None) -> None:
        if fault is not None and fault.injection_point is not InjectionPoint.TOOL_RESULT:
            raise AdapterCapabilityError("Anchorline 当前只支持 tool_result 注入")
        engine = None
        try:
            factory, engine = self._session_factory()
            del factory
            sqlalchemy = importlib.import_module("sqlalchemy")
            with engine.connect() as connection:
                connection.execute(sqlalchemy.text("SELECT 1"))
            if not sqlalchemy.inspect(engine).has_table("facts"):
                raise ConfigurationError("Anchorline 独立测试数据库缺少 facts 表")
            importlib.import_module("anchorline.memory.store")
            importlib.import_module("anchorline.tools")
        except (ConfigurationError, AdapterCapabilityError):
            raise
        except Exception as exc:
            raise ConfigurationError(
                f"Anchorline 预检失败（{type(exc).__name__}）；请检查依赖与独立测试数据库"
            ) from exc
        finally:
            if engine is not None:
                engine.dispose()

    @staticmethod
    def _result_record(result: Any) -> dict[str, Any]:
        return {
            "ok": bool(result.ok),
            "content": str(result.content),
            "meta": json.loads(json.dumps(result.meta, ensure_ascii=False, default=str)),
        }

    @staticmethod
    def _arguments(call: dict[str, Any]) -> dict[str, Any]:
        if call.get("name") != "memory_write":
            raise AdapterCapabilityError("Anchorline 适配器只登记了 memory_write")
        arguments = call.get("args", {})
        if not isinstance(arguments, dict):
            raise ConfigurationError("memory_write 参数必须是 object")
        allowed = {
            "entity_id", "attribute", "value", "valid_from", "confidence",
            "source_session_id", "supersedes_id", "conflict_type",
        }
        if set(arguments) - allowed:
            raise ConfigurationError("memory_write 包含未登记参数")
        if not all(isinstance(arguments.get(key), str) and arguments[key].strip()
                   for key in ("entity_id", "attribute", "value")):
            raise ConfigurationError("memory_write 的 entity_id、attribute、value 必须是非空字符串")
        return dict(arguments)

    def run_script(
        self,
        script: list[dict[str, Any]],
        *,
        fault: FaultSpec | None = None,
        sandbox: Path,
    ) -> HostRunResult:
        self.preflight(fault)
        sandbox = Path(sandbox).resolve()
        sandbox.mkdir(parents=True, exist_ok=True)
        factory, engine = self._session_factory()
        session = factory()
        events: list[dict[str, Any]] = []
        final_answer: str | None = None
        outcome = "completed"
        try:
            store_module = importlib.import_module("anchorline.memory.store")
            tools_module = importlib.import_module("anchorline.tools")
            store = store_module.FactStore(session)
            tool = tools_module.build_tools(store, session_id=f"faultlattice-{sandbox.parent.name}")[
                "memory_write"
            ]
            for item in script:
                if "tool_call" not in item:
                    if "final_answer" not in item or not isinstance(item["final_answer"], str):
                        raise ConfigurationError("Anchorline 无法识别该脚本项")
                    final_answer = item["final_answer"]
                    events.append({"kind": "model_output", "content": final_answer, "preset": True})
                    continue
                arguments = self._arguments(item["tool_call"])
                events.append({
                    "kind": "tool_call", "tool_name": "memory_write", "arguments": dict(arguments)
                })
                injected = False
                try:
                    produced = self._result_record(tool(**arguments))
                    session.commit()
                except Exception as exc:
                    session.rollback()
                    events.append({
                        "kind": "tool_result", "tool_name": "memory_write", "result": None,
                        "error": type(exc).__name__, "injected": False,
                    })
                    outcome = "failed"
                    break
                observed = produced
                if fault is not None:
                    effect = build_fault_effect(
                        fault.fault_type, fault.surface_as, fault.params, original=produced
                    )
                    if effect.raises:
                        events.append({
                            "kind": "injection",
                            "injection_point": fault.injection_point.value,
                            "fault_type": fault.fault_type.value,
                            "surface_as": fault.surface_as.value,
                            "original": produced, "replacement": None,
                            "raised": type(effect.exception).__name__, "applied": True,
                        })
                        events.append({
                            "kind": "tool_result", "tool_name": "memory_write", "result": None,
                            "error": type(effect.exception).__name__, "injected": True,
                        })
                        outcome = "failed"
                        break
                    injected = effect.replacement != produced
                    events.append({
                        "kind": "injection",
                        "injection_point": fault.injection_point.value,
                        "fault_type": fault.fault_type.value,
                        "surface_as": fault.surface_as.value,
                        "original": produced, "replacement": effect.replacement,
                        "raised": None, "applied": injected,
                    })
                    observed = effect.replacement
                events.append({
                    "kind": "tool_result", "tool_name": "memory_write", "result": observed,
                    "error": None, "injected": injected,
                })
                if isinstance(observed, dict) and (
                    observed.get("error") is not None or observed.get("ok") is False
                ):
                    outcome = "failed"
                    break
        finally:
            session.close()
            engine.dispose()
        return HostRunResult(
            framework_outcome=outcome,
            final_answer=final_answer if outcome == "completed" else None,
            events=events,
            model_invoked=False,
        )

    def observe_postcondition(
        self, expected: ExpectedPostcondition, *, sandbox: Path
    ) -> PostconditionObservation:
        if expected.kind != "host_state":
            raise ConfigurationError("Anchorline 只观察 host_state")
        params = expected.params
        required = ("entity_id", "attribute", "value")
        if not all(isinstance(params.get(key), str) for key in required):
            return PostconditionObservation(
                task_succeeded=False,
                side_effects_as_expected=False,
                evidence_sufficient=False,
                evidence={"observation_summary": "后置条件缺少 entity_id、attribute 或 value"},
            )
        factory, engine = self._session_factory()
        session = factory()
        try:
            store_module = importlib.import_module("anchorline.memory.store")
            current = store_module.FactStore(session).current(params["entity_id"], params["attribute"])
            matches = current is not None and current.value == params["value"]
            summary = (
                f"独立会话已查询事实 {params['entity_id']}.{params['attribute']}；"
                + ("当前值与预注册值完全一致" if matches else "当前事实不存在或值与预注册不一致")
            )
            return PostconditionObservation(
                task_succeeded=matches,
                side_effects_as_expected=matches,
                evidence={
                    "observation_summary": summary,
                    "fact_found": current is not None,
                    "value_matches": matches,
                    "fact_id": current.id if current is not None else None,
                },
            )
        finally:
            session.close()
            engine.dispose()
