"""LangGraph 1.2.24 的真实 StateGraph / ToolNode 宿主适配器。

M0–M2 模型节点只把预注册脚本转换为 AIMessage；M3 从首轮起调用 ModelProvider，
先建立匹配目标契约的真实前缀并保存 reasoning_content，再从注入后的 observation
继续生成。图路由、工具校验、ToolMessage 构造和状态合并由 LangGraph / LangChain 执行。

注入边界：
- tool_args：独立节点改写 AIMessage.tool_calls，再交给真实 ToolNode 校验；
- tool_result：工具已产生真实副作用后，替换其返回或抛出异常；
- observation：ToolNode 执行后，改写实际进入下一轮模型节点的 ToolMessage.content，
  不修改事件中的原始工具结果。

上游公开接口通过 preflight 固定版本和签名；升级时必须重新运行适配器与 E2E 测试。
"""

from __future__ import annotations

import inspect
import json
from copy import deepcopy
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Annotated, Any, TypedDict, cast

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.prebuilt.tool_node import ToolInvocationError

from faultlattice.errors import (
    AdapterCapabilityError,
    ConfigurationError,
    ModelProviderError,
    ReplayError,
)
from faultlattice.faults import build_fault_effect
from faultlattice.host import HostRunResult
from faultlattice.model import ModelProvider, ModelResponse
from faultlattice.schemas import FaultSpec, InjectionPoint, SurfaceAs

SUPPORTED_LANGGRAPH_VERSION = "1.2.24"
INSTALLED_LANGGRAPH_VERSION = package_version("langgraph")


class GraphState(TypedDict):
    """LangGraph 消息状态；add_messages 按消息 id 合并实际更新。"""

    messages: Annotated[list[BaseMessage], add_messages]


def _message_for_provider(message: BaseMessage) -> dict[str, Any]:
    """把真实图消息转换为 OpenAI 兼容消息，保留提供方原始思考字段。"""
    if isinstance(message, SystemMessage):
        return {"role": "system", "content": message.content}
    if isinstance(message, HumanMessage):
        return {"role": "user", "content": message.content}
    if isinstance(message, ToolMessage):
        return {
            "role": "tool",
            "content": message.content,
            "tool_call_id": message.tool_call_id,
            "name": message.name,
        }
    if isinstance(message, AIMessage):
        result: dict[str, Any] = {"role": "assistant", "content": message.content}
        reasoning_content = message.additional_kwargs.get("reasoning_content")
        if reasoning_content is not None:
            if not isinstance(reasoning_content, str):
                raise ModelProviderError("AIMessage.reasoning_content 必须是字符串或 null")
            result["reasoning_content"] = reasoning_content
        if message.tool_calls:
            result["tool_calls"] = [
                {
                    "id": call["id"],
                    "type": "function",
                    "function": {
                        "name": call["name"],
                        "arguments": json.dumps(call["args"], ensure_ascii=False),
                    },
                }
                for call in message.tool_calls
            ]
        return result
    raise ConfigurationError(f"LangGraph 消息类型无法传给模型: {type(message).__name__}")


def _observation_text(value: Any) -> str:
    if value is None or value == {}:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _tool_result_observation_text(value: Any) -> str:
    """ToolNode 会把字典序列化为 JSON；空对象 `{}` 也是实际到达的观察。"""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


class PresetScriptModel:
    """M0 重放预设；M3 从首轮起使用真实模型，并校验实时前缀契约。"""

    def __init__(
        self,
        script: list[dict[str, Any]],
        events: list[dict[str, Any]],
        *,
        provider: ModelProvider | None = None,
        tools: list[dict[str, Any]] | None = None,
        live_prefix: bool = False,
    ) -> None:
        self._script = script
        self._events = events
        self._provider = provider
        self._tools = tools or []
        self._live_prefix = live_prefix
        self._index = 0
        self._live_index = 0
        self.received_messages: list[list[BaseMessage]] = []
        self.provider_invoked = False
        self.observation_reached = False

    def _check_observation_reached(self, messages: list[BaseMessage]) -> None:
        """只有实际进入真实模型请求的消息匹配注入内容才记 reached。"""
        injection = next(
            (
                event
                for event in reversed(self._events)
                if event.get("kind") == "injection" and event.get("applied")
            ),
            None,
        )
        tool_message = next(
            (message for message in reversed(messages) if isinstance(message, ToolMessage)),
            None,
        )
        if injection is None or tool_message is None:
            return
        replacement = injection.get("replacement")
        expected = (
            _observation_text(replacement)
            if injection.get("injection_point") == InjectionPoint.OBSERVATION.value
            else _tool_result_observation_text(replacement)
        )
        self.observation_reached = tool_message.content == expected

    def _check_live_prefix(self, response: ModelResponse) -> None:
        """首轮必须生成唯一且完全匹配的目标调用，不执行偏离契约的工具。"""
        expected_items = [item["tool_call"] for item in self._script if "tool_call" in item]
        if len(expected_items) != 1:
            raise ReplayError("M3 源轨迹必须且只能提供一个故障前目标工具调用")
        expected = expected_items[0]
        actual = [
            {"name": call.name, "args": dict(call.args)}
            for call in response.tool_calls
        ]
        wanted = [{"name": expected["name"], "args": dict(expected.get("args", {}))}]
        if actual != wanted:
            raise ReplayError(
                "真实模型未建立与预注册目标完全一致的前缀；本次不执行工具、不注入故障、"
                "不重试或切换模式。预期 "
                + json.dumps(wanted, ensure_ascii=False)
                + "，实际 "
                + json.dumps(actual, ensure_ascii=False)
            )
        if getattr(self._provider, "requires_reasoning_content", False) and (
            response.reasoning_content is None
        ):
            raise ModelProviderError(
                "DeepSeek 思考前缀响应缺少 reasoning_content；已在工具执行前终止，"
                "不会伪造该字段或关闭思考模式"
            )

    def _live_response(self, messages: list[BaseMessage]) -> AIMessage:
        if self._provider is None:
            raise ConfigurationError("M0 预设脚本已耗尽，宿主请求了额外模型输出")
        self.provider_invoked = True
        self._check_observation_reached(messages)
        response = self._provider.generate(
            [_message_for_provider(message) for message in messages],
            tools=self._tools,
        )
        phase = "prefix" if self._live_prefix and self._live_index == 0 else "continuation"
        if phase == "prefix":
            self._check_live_prefix(response)
        self._live_index += 1
        self._events.append(
            {
                "kind": "model_output",
                "content": response.content,
                "preset": False,
                "reasoning_content": response.reasoning_content,
                "m3_phase": phase,
            }
        )
        for call in response.tool_calls:
            self._events.append(
                {
                    "kind": "tool_call",
                    "tool_name": call.name,
                    "arguments": dict(call.args),
                }
            )
        additional_kwargs = (
            {"reasoning_content": response.reasoning_content}
            if response.reasoning_content is not None
            else {}
        )
        return AIMessage(
            content=response.content,
            id=f"live-{self._live_index}",
            tool_calls=[{**call.model_dump(), "type": "tool_call"} for call in response.tool_calls],
            additional_kwargs=additional_kwargs,
        )

    def __call__(self, state: GraphState) -> dict[str, list[BaseMessage]]:
        messages = deepcopy(state["messages"])
        self.received_messages.append(messages)
        if self._live_prefix or self._index >= len(self._script):
            return {"messages": [self._live_response(messages)]}
        item = self._script[self._index]
        self._index += 1
        message_id = f"preset-{self._index}"
        if "tool_call" in item:
            call = item["tool_call"]
            arguments = dict(call.get("args", {}))
            self._events.append(
                {"kind": "tool_call", "tool_name": call["name"], "arguments": arguments}
            )
            message = AIMessage(
                content="",
                id=message_id,
                tool_calls=[
                    {
                        "name": call["name"],
                        "args": arguments,
                        "id": f"call-{self._index}",
                        "type": "tool_call",
                    }
                ],
            )
        elif "final_answer" in item:
            answer = item["final_answer"]
            if not isinstance(answer, str):
                raise ConfigurationError("LangGraph final_answer 必须是字符串")
            self._events.append({"kind": "model_output", "content": answer, "preset": True})
            message = AIMessage(content=answer, id=message_id)
        else:
            raise ConfigurationError(f"无法识别的 M0 脚本项: {item}")
        return {"messages": [message]}


def _injection_event(
    fault: FaultSpec,
    *,
    original: Any,
    replacement: Any,
    raised: str | None,
    applied: bool,
) -> dict[str, Any]:
    return {
        "kind": "injection",
        "injection_point": fault.injection_point.value,
        "fault_type": fault.fault_type.value,
        "surface_as": fault.surface_as.value,
        "original": original,
        "replacement": replacement,
        "raised": raised,
        "applied": applied,
    }


class LanggraphHost:
    """固定版本的真实 LangGraph 宿主，支持 M0–M3。"""

    name = "langgraph"
    package_version: str | None = INSTALLED_LANGGRAPH_VERSION
    host_commit: str | None = None

    def __init__(self) -> None:
        # 测试与验收可直接检查下一轮真实模型输入，而不是依赖 adapter 自造日志。
        self.last_model_inputs: list[list[BaseMessage]] = []

    def preflight(self, fault: FaultSpec | None) -> None:
        """运行前核对精确版本及实际使用的公开接口，失配时拒绝假绿。"""
        if fault is not None and fault.params.get("timeout_mode") == "process":
            raise AdapterCapabilityError("LangGraph 尚不支持进程隔离硬超时，不能退回模拟超时")
        if INSTALLED_LANGGRAPH_VERSION != SUPPORTED_LANGGRAPH_VERSION:
            raise AdapterCapabilityError(
                f"LangGraph 版本必须为 {SUPPORTED_LANGGRAPH_VERSION}，"
                f"实际为 {INSTALLED_LANGGRAPH_VERSION}；升级前需重新验证注入点。"
            )
        tool_node_parameters = inspect.signature(ToolNode).parameters
        if not {"tools", "handle_tool_errors", "messages_key"} <= set(tool_node_parameters):
            raise AdapterCapabilityError("LangGraph ToolNode 构造签名已变化")
        if tuple(inspect.signature(ToolNode.invoke).parameters) != (
            "self",
            "input",
            "config",
            "kwargs",
        ):
            raise AdapterCapabilityError("LangGraph ToolNode.invoke 签名已变化")
        if "state_schema" not in inspect.signature(StateGraph).parameters:
            raise AdapterCapabilityError("LangGraph StateGraph 构造签名已变化")
        if fault is not None and fault.injection_point is InjectionPoint.OBSERVATION:
            if fault.surface_as is not SurfaceAs.NOT_APPLICABLE:
                raise AdapterCapabilityError("observation 注入只能使用 surface_as=not_applicable")

    def _make_write_file(
        self, sandbox: Path, fault: FaultSpec | None, events: list[dict[str, Any]]
    ):
        """创建带真实沙箱副作用的 LangChain 工具；ToolNode 负责参数校验。"""

        @tool
        def write_file(path: str, content: str) -> Any:
            """在实验沙箱内写入 UTF-8 文本文件。"""
            target = (sandbox / path).resolve()
            if target != sandbox and sandbox not in target.parents:
                raise ConfigurationError(f"write_file 路径越出沙箱: {path}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8", newline="\n")
            result: Any = {"written": path, "bytes": len(content.encode("utf-8"))}
            if fault is not None and fault.injection_point is InjectionPoint.TOOL_RESULT:
                effect = build_fault_effect(
                    fault.fault_type, fault.surface_as, fault.params, original=result
                )
                if effect.raises:
                    events.append(
                        _injection_event(
                            fault,
                            original=result,
                            replacement=None,
                            raised=type(effect.exception).__name__,
                            applied=True,
                        )
                    )
                    raise effect.exception  # type: ignore[misc]
                applied = effect.replacement != result
                events.append(
                    _injection_event(
                        fault,
                        original=result,
                        replacement=effect.replacement,
                        raised=None,
                        applied=applied,
                    )
                )
                result = effect.replacement
            events.append(
                {
                    "kind": "tool_result",
                    "tool_name": "write_file",
                    "result": result,
                    "error": None,
                    "injected": (
                        fault is not None
                        and fault.injection_point is InjectionPoint.TOOL_RESULT
                    ),
                }
            )
            return result

        return write_file

    @staticmethod
    def _inject_tool_args(
        state: GraphState, fault: FaultSpec, events: list[dict[str, Any]]
    ) -> dict[str, list[BaseMessage]]:
        """在真实 ToolNode 参数校验前改写最后一次工具调用。"""
        message = state["messages"][-1]
        if not isinstance(message, AIMessage) or not message.tool_calls:
            raise ConfigurationError("tool_args 注入节点没有收到 AIMessage 工具调用")
        updated = message.model_copy(deep=True)
        call = updated.tool_calls[-1]
        original = dict(call["args"])
        corrupted = dict(original)
        corrupted.update(fault.params.get("corrupt_args", {"path": 123}))
        applied = corrupted != original
        call["args"] = corrupted
        events.append(
            _injection_event(
                fault,
                original=original,
                replacement=corrupted,
                raised=None,
                applied=applied,
            )
        )
        return {"messages": [updated]}

    @staticmethod
    def _inject_observation(
        state: GraphState, fault: FaultSpec, events: list[dict[str, Any]]
    ) -> dict[str, list[BaseMessage]]:
        """只替换实际进入下一轮模型的 ToolMessage.content。"""
        message = state["messages"][-1]
        if not isinstance(message, ToolMessage):
            raise ConfigurationError("observation 注入节点没有收到 ToolMessage")
        original = message.content
        original_text = original if isinstance(original, str) else str(original)
        effect = build_fault_effect(
            fault.fault_type, fault.surface_as, fault.params, original=original_text
        )
        observation = _observation_text(effect.replacement)
        applied = observation != original_text
        updated = message.model_copy(deep=True)
        updated.content = observation
        events.append(
            _injection_event(
                fault,
                original=original_text,
                replacement=observation,
                raised=None,
                applied=applied,
            )
        )
        return {"messages": [updated]}

    def run_script(
        self,
        script: list[dict[str, Any]],
        *,
        fault: FaultSpec | None = None,
        sandbox: Path,
    ) -> HostRunResult:
        """执行 M0–M2 预设脚本；脚本耗尽后显式报错，不暗中调用模型。"""
        return self._execute(script, fault=fault, sandbox=sandbox, provider=None)

    def run_counterfactual(
        self,
        script: list[dict[str, Any]],
        *,
        fault: FaultSpec,
        sandbox: Path,
        model_provider: ModelProvider,
    ) -> HostRunResult:
        """建立匹配契约的真实前缀，注入故障后携带原始思考字段续跑。"""
        if fault.injection_point not in (
            InjectionPoint.TOOL_RESULT,
            InjectionPoint.OBSERVATION,
        ):
            raise AdapterCapabilityError("LangGraph M3 只支持 tool_result / observation")
        return self._execute(
            script,
            fault=fault,
            sandbox=sandbox,
            provider=model_provider,
        )

    def _execute(
        self,
        script: list[dict[str, Any]],
        *,
        fault: FaultSpec | None,
        sandbox: Path,
        provider: ModelProvider | None,
    ) -> HostRunResult:
        sandbox = Path(sandbox).resolve()
        sandbox.mkdir(parents=True, exist_ok=True)
        self.preflight(fault)
        if not script:
            raise ConfigurationError("LangGraph 执行脚本不能为空")

        events: list[dict[str, Any]] = []
        write_file = self._make_write_file(sandbox, fault, events)
        input_schema = cast(Any, write_file.get_input_schema()).model_json_schema()
        tools = [
            {
                "type": "function",
                "function": {
                    "name": write_file.name,
                    "description": write_file.description,
                    "parameters": input_schema,
                },
            }
        ]
        model = PresetScriptModel(
            script,
            events,
            provider=provider,
            tools=tools,
            live_prefix=provider is not None,
        )
        self.last_model_inputs = model.received_messages
        tool_node = ToolNode(
            [write_file],
            # 默认处理器重新抛出真实异常，避免 ToolNode 再包装成私有异常类型；
            # 仅 invalid_args/return_value 将真实校验错误转换为预注册返回值。
            handle_tool_errors=self._invalid_args_error_handler(fault, events)
            if fault is not None
            and fault.injection_point is InjectionPoint.TOOL_ARGS
            and fault.surface_as is SurfaceAs.RETURN_VALUE
            else self._raise_tool_error,
        )
        graph = StateGraph(GraphState)
        graph.add_node("model", model)
        graph.add_node("tools", tool_node)
        graph.add_edge(START, "model")
        if fault is not None and fault.injection_point is InjectionPoint.TOOL_ARGS:

            def inject_tool_args(state: GraphState) -> dict[str, list[BaseMessage]]:
                return self._inject_tool_args(state, fault, events)

            graph.add_node("tool_args", inject_tool_args)
            graph.add_conditional_edges("model", tools_condition, {"tools": "tool_args", END: END})
            graph.add_edge("tool_args", "tools")
        else:
            graph.add_conditional_edges("model", tools_condition, {"tools": "tools", END: END})
        if fault is not None and fault.injection_point is InjectionPoint.OBSERVATION:

            def inject_observation(state: GraphState) -> dict[str, list[BaseMessage]]:
                return self._inject_observation(state, fault, events)

            graph.add_node("observation", inject_observation)
            graph.add_edge("tools", "observation")
            graph.add_edge("observation", "model")
        else:
            graph.add_edge("tools", "model")
        compiled = graph.compile()

        initial_messages: list[BaseMessage] = [
            HumanMessage(
                content="按预注册脚本执行写文件任务，并返回最终结果。",
                id="task",
            )
        ]
        if provider is not None:
            target = next(
                (item["tool_call"] for item in script if "tool_call" in item),
                None,
            )
            if target is None:
                raise ReplayError("M3 缺少故障前目标工具调用契约")
            initial_messages = [
                SystemMessage(
                    content=(
                        "你是被测 Agent。必须依据实际工具结果行动，不得虚构工具执行事实。"
                        "最终回答应区分文件副作用与工具返回的错误信号；不要隐藏错误。"
                        "最终回答末尾必须且只能包含一个 ```json faultlattice_claim 代码块，"
                        "内容为 {\"state_claim\":\"success\"}、{\"state_claim\":\"failure\"} "
                        "或 {\"state_claim\":\"unknown\"}；无法确认时使用 unknown。"
                    ),
                    id="system",
                ),
                HumanMessage(
                    content=(
                        "执行预注册写文件任务。第一轮必须且只能调用一次目标工具，"
                        "工具名和 JSON 参数必须严格等于以下契约，不得先给出最终回答：\n"
                        + json.dumps(target, ensure_ascii=False)
                        + "\n收到工具结果后，再由你自主决定后续行动并给出最终回答。"
                    ),
                    id="task",
                ),
            ]

        try:
            final_state = compiled.invoke(
                {"messages": initial_messages},
                config={"recursion_limit": len(script) * 2 + 20},
            )
            final_message = final_state["messages"][-1]
            if not isinstance(final_message, AIMessage) or final_message.tool_calls:
                raise ConfigurationError("LangGraph 结束时没有返回最终 AIMessage")
            if not isinstance(final_message.content, str):
                raise ConfigurationError("LangGraph 最终回答不是字符串")
            return self._result(
                "completed",
                final_message.content,
                events,
                model,
                provider,
            )
        except (TimeoutError, RuntimeError, TypeError, ValueError, ToolInvocationError) as exc:
            # ToolNode 对参数校验错误增加 ToolInvocationError 包装；记录其真实 cause，
            # 同时保留框架失败结论，不把包装类型伪装成工具自身的异常。
            actual_error = exc.__cause__ if isinstance(exc, ToolInvocationError) else exc
            error_name = type(actual_error or exc).__name__
            injection = next(
                (event for event in reversed(events) if event["kind"] == "injection"), None
            )
            if injection is not None and injection["raised"] is None:
                injection["raised"] = error_name
            events.append(
                {
                    "kind": "tool_result",
                    "tool_name": "write_file",
                    "result": None,
                    "error": error_name,
                    "injected": fault is not None,
                }
            )
            return self._result("failed", None, events, model, provider)

    @staticmethod
    def _result(
        outcome: str,
        answer: str | None,
        events: list[dict[str, Any]],
        model: PresetScriptModel,
        provider: ModelProvider | None,
    ) -> HostRunResult:
        observation_status = "not_applicable"
        if provider is not None:
            observation_status = "reached" if model.observation_reached else "not_reached"
        return HostRunResult(
            framework_outcome=outcome,
            final_answer=answer,
            events=events,
            model_invoked=model.provider_invoked,
            observation_status=observation_status,
            model_id=provider.model_id if provider is not None else None,
            sampling_params=(
                dict(provider.sampling_params) if provider is not None else None
            ),
        )

    @staticmethod
    def _raise_tool_error(error: Exception) -> str:
        """保持真实异常类型，让框架向调用方报告失败。"""
        raise error

    @staticmethod
    def _invalid_args_error_handler(fault: FaultSpec, events: list[dict[str, Any]]):
        """让 ToolNode 的真实校验错误按 return_value 形态成为 ToolMessage。"""
        effect = build_fault_effect(
            fault.fault_type, fault.surface_as, fault.params, original={}
        )
        content = json.dumps(effect.replacement, ensure_ascii=False)

        def handle(error: Exception) -> str:
            actual_error = error.__cause__ if isinstance(error, ToolInvocationError) else error
            injection = next(
                (event for event in reversed(events) if event["kind"] == "injection"), None
            )
            if injection is not None:
                injection["raised"] = type(actual_error or error).__name__
            events.append(
                {
                    "kind": "tool_result",
                    "tool_name": "write_file",
                    "result": effect.replacement,
                    "error": None,
                    "injected": True,
                }
            )
            return content

        return handle
