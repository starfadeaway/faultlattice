"""LoreKeeper 真实 ReAct 循环与 calculator 的 M0 适配器（人工复核稿）。

运行 external_projects/lorekeeper 工作区副本的生产 ReActAgent.run。
chat_fn 只按任务脚本返回预设输出，不调用真实模型；工具参数在 _exec_call
边界真实改写。Oracle 通过运行后的 AgentState 独立观察工具记录与业务状态。
"""

from __future__ import annotations

import asyncio
import copy
import importlib
import re
import sys
from pathlib import Path
from types import MethodType
from typing import Any, cast

from faultlattice.errors import AdapterCapabilityError, ConfigurationError
from faultlattice.host import HostRunResult, PostconditionObservation
from faultlattice.schemas import ExpectedPostcondition, FaultSpec, InjectionPoint


class LoreKeeperHostAdapter:
    name = "lorekeeper"
    package_version = None
    host_commit = None
    capabilities = {
        "modes": ["M0"],
        "injection_points": ["tool_args"],
        "tools": ["calculator"],
    }

    def __init__(self) -> None:
        self._last_state: Any = None

    @staticmethod
    def _root() -> Path:
        return Path(__file__).resolve().parents[2]

    @classmethod
    def _prepare_imports(cls) -> None:
        backend = cls._root() / "external_projects" / "lorekeeper" / "backend"
        if not backend.is_dir():
            raise ConfigurationError("LoreKeeper 工作区源码副本不存在")
        if str(backend) not in sys.path:
            sys.path.insert(0, str(backend))

    @classmethod
    def _modules(cls) -> tuple[Any, Any, Any, Any]:
        cls._prepare_imports()
        try:
            react = importlib.import_module("app.agent.react")
            tools = importlib.import_module("app.agent.tools")
            config = importlib.import_module("app.core.config")
            llm = importlib.import_module("app.llm.client")
        except Exception as exc:
            raise ConfigurationError(
                f"LoreKeeper 依赖或源码导入失败（{type(exc).__name__}）"
            ) from exc
        return react, tools, config, llm

    def preflight(self, fault: FaultSpec | None) -> None:
        if fault is not None and fault.injection_point is not InjectionPoint.TOOL_ARGS:
            raise AdapterCapabilityError("LoreKeeper 当前只支持 tool_args 注入")
        if fault is not None:
            corrupt = fault.params.get("corrupt_args")
            if not isinstance(corrupt, dict) or set(corrupt) != {"expression"}:
                raise ConfigurationError("LoreKeeper 注入必须且只能改写 expression")
            if not isinstance(corrupt.get("expression"), str):
                raise ConfigurationError("注入后的 expression 必须是字符串")
        _, tools, _, _ = self._modules()
        if "calculator" not in tools.REGISTRY:
            raise ConfigurationError("LoreKeeper 生产工具表中没有 calculator")

    @staticmethod
    def _parse_script(script: list[dict[str, Any]]) -> tuple[str, str, str]:
        if len(script) != 2:
            raise ConfigurationError("LoreKeeper M0 脚本必须包含一次工具调用和一个最终回答")
        call = script[0].get("tool_call")
        answer = script[1].get("final_answer")
        if not isinstance(call, dict) or call.get("name") != "calculator":
            raise ConfigurationError("LoreKeeper M0 只支持 calculator")
        arguments = call.get("args")
        if not isinstance(arguments, dict) or set(arguments) != {"expression"}:
            raise ConfigurationError("calculator 脚本必须且只能提供 expression")
        expression = arguments.get("expression")
        if not isinstance(expression, str) or not re.fullmatch(
            r"[0-9+\-*/().%^ ]+", expression.strip()
        ):
            raise ConfigurationError("原始 expression 必须是非空合法算式字符序列")
        if not isinstance(answer, str) or not answer.startswith(("[计算失败]", "[计算完成]")):
            raise ConfigurationError(
                "预设最终回答必须以 [计算失败] 或 [计算完成] 开头，形成明确的适配器结果信号"
            )
        return expression.strip(), answer, str(call.get("id") or "faultlattice-calculator-0")

    async def _run(
        self,
        *,
        expression: str,
        answer: str,
        call_id: str,
        fault: FaultSpec | None,
    ) -> tuple[Any, list[dict[str, Any]]]:
        react, tools, config, llm_module = self._modules()
        settings = config.Settings(
            agent_tools="calculator",
            deepseek_api_key="",
            siliconflow_api_key="",
            minimax_api_key="",
            mysql_password="",
            data_root=str(self._root() / ".verify" / "lorekeeper-data"),
            vector_backend="numpy",
            chat_fallbacks="",
        )
        # calculator 不读取 retriever / store；显式空依赖避免初始化网络、数据库和索引。
        context = tools.ToolContext(settings=settings, retriever=None, store=None)
        llm = llm_module.LLMClient(settings)
        events: list[dict[str, Any]] = []
        outputs = [
            {
                "content": "我将调用计算器。",
                "tool_calls": [
                    {"id": call_id, "name": "calculator", "args": {"expression": expression}}
                ],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0},
            },
            {
                "content": answer,
                "tool_calls": [],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0},
            },
        ]
        cursor = 0

        async def chat_fn(messages: list[dict], **kwargs: Any) -> dict:
            nonlocal cursor
            del messages, kwargs
            if cursor >= len(outputs):
                raise RuntimeError("生产循环请求了未预注册的额外模型输出")
            output = copy.deepcopy(outputs[cursor])
            cursor += 1
            events.append(
                {"kind": "model_output", "content": str(output["content"]), "preset": True}
            )
            return output

        agent = react.ReActAgent(
            settings=settings,
            llm=llm,
            tools=tools.get_schemas(["calculator"]),
            chat_fn=chat_fn,
        )
        original_exec = agent._exec_call

        async def injected_exec(agent_self: Any, call: dict, *args: Any) -> Any:
            del agent_self
            original_args = copy.deepcopy(call.get("args"))
            events.append(
                {
                    "kind": "tool_call",
                    "tool_name": "calculator",
                    "arguments": copy.deepcopy(original_args),
                }
            )
            injected = False
            if fault is not None:
                replacement = cast(dict[str, Any], copy.deepcopy(original_args))
                replacement.update(copy.deepcopy(fault.params["corrupt_args"]))
                injected = replacement != original_args
                events.append(
                    {
                        "kind": "injection",
                        "injection_point": fault.injection_point.value,
                        "fault_type": fault.fault_type.value,
                        "surface_as": fault.surface_as.value,
                        "original": original_args,
                        "replacement": copy.deepcopy(replacement),
                        "raised": None,
                        "applied": injected,
                    }
                )
                call["args"] = replacement
            text, record = await original_exec(call, *args)
            events.append(
                {
                    "kind": "tool_result",
                    "tool_name": "calculator",
                    "result": text,
                    "error": record.error,
                    "injected": injected,
                }
            )
            return text, record

        agent._exec_call = MethodType(injected_exec, agent)
        try:
            state = await agent.run(
                f"请使用计算器计算：{expression}",
                session_key="faultlattice-lorekeeper-m0",
                ctx=context,
                stream=False,
            )
        finally:
            # LLMClient 只提供生产消息格式函数；显式关闭其未使用的 HTTP 客户端。
            await llm._rerank_http.aclose()
        return state, events

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
        expression, answer, call_id = self._parse_script(script)
        self._last_state = None
        state, events = asyncio.run(
            self._run(expression=expression, answer=answer, call_id=call_id, fault=fault)
        )
        self._last_state = state
        # 适配器公开契约：[计算失败] 前缀映射为显式失败信号；它不作为任务成功证据。
        outcome = (
            "failed"
            if state.stop_reason == "error" or str(state.answer).startswith("[计算失败]")
            else "completed"
        )
        return HostRunResult(
            framework_outcome=outcome,
            final_answer=str(state.answer) if state.answer else None,
            events=events,
            model_invoked=False,
        )

    def observe_postcondition(
        self, expected: ExpectedPostcondition, *, sandbox: Path
    ) -> PostconditionObservation:
        del sandbox
        if expected.kind != "host_state":
            raise ConfigurationError("LoreKeeper 只观察 host_state")
        original = expected.params.get("original_expression")
        corrupted = expected.params.get("corrupted_expression")
        state = self._last_state
        if (
            state is None
            or not isinstance(original, str)
            or (corrupted is not None and not isinstance(corrupted, str))
        ):
            return PostconditionObservation(
                task_succeeded=False,
                side_effects_as_expected=False,
                evidence_sufficient=False,
                evidence={"observation_summary": "缺少运行后的 AgentState 或预期算式"},
            )
        steps = [
            {
                "step": int(step.step),
                "tool_name": str(step.tool_name),
                "args": copy.deepcopy(step.args),
                "ok": bool(step.ok),
                "error": step.error,
                "latency_ms": int(step.latency_ms),
                "result_chars": int(step.result_chars),
            }
            for step in state.steps
        ]
        calculator_steps = [step for step in steps if step["tool_name"] == "calculator"]
        original_succeeded = any(
            step["ok"] and step["args"].get("expression") == original
            for step in calculator_steps
        )
        if corrupted is None:
            side_effects_ok = (
                len(calculator_steps) == 1
                and original_succeeded
                and int(state.tool_failures) == 0
            )
            injected_failure_observed = False
            summary = (
                f"生产 AgentState 记录了 {len(calculator_steps)} 次 calculator 调用、"
                f"{int(state.tool_failures)} 次工具失败；未注入故障，原算式"
                + ("已使用原始参数成功执行" if original_succeeded else "没有成功结果")
                + "；"
                + ("正常调用及零失败计数均符合预期" if side_effects_ok else "调用次数或失败计数不符合预期")
            )
        else:
            injected_failure_observed = any(
                not step["ok"]
                and step["args"].get("expression") == corrupted
                and isinstance(step["error"], str)
                and step["error"].startswith("[错误]")
                for step in calculator_steps
            )
            side_effects_ok = (
                len(calculator_steps) == 1
                and injected_failure_observed
                and int(state.tool_failures) == 1
            )
            summary = (
                f"生产 AgentState 记录了 {len(calculator_steps)} 次 calculator 调用、"
                f"{int(state.tool_failures)} 次工具失败；原算式"
                + ("已有成功结果" if original_succeeded else "没有成功结果")
                + "，注入后的失败参数"
                + ("已留下明确错误记录" if injected_failure_observed else "未形成预期错误记录")
            )
        return PostconditionObservation(
            task_succeeded=original_succeeded,
            side_effects_as_expected=side_effects_ok,
            evidence={
                "observation_summary": summary,
                "original_expression_succeeded": original_succeeded,
                "injected_failure_observed": injected_failure_observed,
                "tool_failures": int(state.tool_failures),
                "stop_reason": str(state.stop_reason),
                "answer": str(state.answer),
                "steps": steps,
            },
        )
