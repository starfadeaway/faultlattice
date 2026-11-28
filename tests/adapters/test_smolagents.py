"""真实 smolagents 适配器测试：必须证明目标内容改变，而非只检查包装器调用。"""

from pathlib import Path
from typing import Any

import pytest

smolagents = pytest.importorskip("smolagents")

from faultlattice.adapters.smolagents import (  # noqa: E402
    SUPPORTED_SMOLAGENTS_VERSION,
    FaultInjectedWriteFile,
    ObservationInjectingAgent,
    PresetScriptModel,
    SmolagentsHost,
)
from faultlattice.errors import (  # noqa: E402
    AdapterCapabilityError,
    ModelProviderError,
    ReplayError,
)
from faultlattice.model import ModelResponse  # noqa: E402
from faultlattice.schemas import FaultSpec  # noqa: E402

SCRIPT = [
    {
        "tool_call": {
            "name": "write_file",
            "args": {"path": "output/hello.txt", "content": "hello smolagents\n"},
        }
    },
    {"final_answer": "已写入 output/hello.txt。"},
]


class FakeProvider:
    """确定性协议替身只验证接线；不代表任何真实模型实验结果。"""

    model_id = "fake-smolagents-m3"
    sampling_params = {"temperature": 0.0}
    state_claim_protocol = "directive_failure_v1"
    requires_reasoning_content = True

    def __init__(
        self,
        target: dict[str, Any] | None = None,
        *,
        match_prefix: bool = True,
        prefix_reasoning: str | None = "真实前缀思考",
    ) -> None:
        self.target = target or SCRIPT[0]
        self.match_prefix = match_prefix
        self.prefix_reasoning = prefix_reasoning
        self.messages: list[list[dict[str, Any]]] = []
        self.tools: list[list[dict[str, Any]]] = []

    def generate(self, messages, *, tools) -> ModelResponse:
        self.messages.append(messages)
        self.tools.append(tools)
        if len(self.messages) == 1:
            arguments = dict(self.target["tool_call"]["args"])
            if not self.match_prefix:
                arguments["path"] = "output/not-registered.txt"
            return ModelResponse.model_validate({
                "content": "",
                "tool_calls": [{
                    "id": "real-prefix-smolagents",
                    "name": self.target["tool_call"]["name"],
                    "args": arguments,
                }],
                "reasoning_content": self.prefix_reasoning,
            })
        return ModelResponse.model_validate({
            "content": "",
            "tool_calls": [{
                "id": "real-final-smolagents",
                "name": "final_answer",
                "args": {"answer": "文件已写入，但工具返回错误。"},
            }],
            "reasoning_content": "续跑思考",
        })


def _events(result: Any, kind: str) -> list[dict[str, Any]]:
    return [event for event in result.events if event["kind"] == kind]


def test_real_host_baseline_writes_file(tmp_path: Path) -> None:
    host = SmolagentsHost()
    assert host.package_version == SUPPORTED_SMOLAGENTS_VERSION
    sandbox = tmp_path
    result = host.run_script(SCRIPT, sandbox=sandbox)
    assert result.framework_outcome == "completed"
    assert result.final_answer == "已写入 output/hello.txt。"
    assert (sandbox / "output" / "hello.txt").read_text(encoding="utf-8") == "hello smolagents\n"
    assert _events(result, "tool_result")[0]["result"]["written"] == "output/hello.txt"


def test_tool_result_return_value_is_actually_replaced(tmp_path: Path) -> None:
    fault = FaultSpec.model_validate({
        "injection_point": "tool_result",
        "fault_type": "error_response",
        "surface_as": "return_value",
        "params": {"message": "actual replacement"},
    })
    result = SmolagentsHost().run_script(SCRIPT, fault=fault, sandbox=tmp_path)
    injection = _events(result, "injection")[0]
    tool_result = _events(result, "tool_result")[0]
    assert injection["original"]["written"] == "output/hello.txt"
    assert injection["replacement"] == {
        "error": "error_response", "message": "actual replacement"
    }
    assert injection["applied"] is True
    assert tool_result["result"] == injection["replacement"]
    # tool_result 注入发生在工具执行之后，真实副作用不能被抹掉。
    assert (tmp_path / "output" / "hello.txt").is_file()


def test_tool_result_exception_reaches_real_host(tmp_path: Path) -> None:
    fault = FaultSpec.model_validate({
        "injection_point": "tool_result",
        "fault_type": "timeout",
        "surface_as": "raise_exception",
        "params": {"message": "actual timeout"},
    })
    result = SmolagentsHost().run_script(SCRIPT, fault=fault, sandbox=tmp_path)
    assert _events(result, "injection")[0]["raised"] == "TimeoutError"
    assert _events(result, "tool_result")[0]["error"] == "TimeoutError"


def test_process_timeout_is_rejected_instead_of_simulated() -> None:
    fault = FaultSpec.model_validate({
        "injection_point": "tool_result",
        "fault_type": "timeout",
        "surface_as": "raise_exception",
        "params": {"timeout_mode": "process"},
    })
    with pytest.raises(AdapterCapabilityError, match="不能退回模拟超时"):
        SmolagentsHost().preflight(fault)


def test_tool_args_are_changed_before_smolagents_validation(tmp_path: Path) -> None:
    fault = FaultSpec.model_validate({
        "injection_point": "tool_args",
        "fault_type": "invalid_args",
        "surface_as": "raise_exception",
        "params": {"corrupt_args": {"path": 123}},
    })
    result = SmolagentsHost().run_script(SCRIPT, fault=fault, sandbox=tmp_path)
    injection = _events(result, "injection")[0]
    assert injection["original"]["path"] == "output/hello.txt"
    assert injection["replacement"]["path"] == 123
    assert injection["applied"] is True
    assert injection["raised"] == "AgentToolCallError"
    assert not (tmp_path / "output" / "hello.txt").exists()


def test_observation_changes_next_real_model_input_but_not_tool_result(tmp_path: Path) -> None:
    fault = FaultSpec.model_validate({
        "injection_point": "observation",
        "fault_type": "truncated",
        "surface_as": "not_applicable",
        "params": {"keep": 4},
    })
    events: list[dict[str, Any]] = []
    model = PresetScriptModel(SCRIPT, events)
    tool = FaultInjectedWriteFile(tmp_path, fault, events)
    agent = ObservationInjectingAgent(tools=[tool], model=model, fault=fault, events=events)
    agent.run("执行预注册写文件任务。")

    injection = next(event for event in events if event["kind"] == "injection")
    assert "output/hello.txt" in injection["original"]
    assert injection["replacement"] == injection["original"][:4]
    assert injection["applied"] is True
    tool_result = next(event for event in events if event["kind"] == "tool_result")
    assert tool_result["result"]["written"] == "output/hello.txt"
    assert tool_result["injected"] is False
    # 第二次 generate 收到的是 smolagents 写回的上下文，而非 adapter 自造日志。
    second_input = str(model.received_messages[1])
    assert injection["replacement"] in second_input
    assert injection["original"] not in second_input


def test_preflight_rejects_unverified_host_version(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(smolagents, "__version__", "0.0.0")
    with pytest.raises(AdapterCapabilityError, match="1.26.0"):
        SmolagentsHost().preflight(None)


def test_m3_tool_result_reaches_real_model_and_preserves_reasoning(tmp_path: Path) -> None:
    fault = FaultSpec.model_validate({
        "injection_point": "tool_result",
        "fault_type": "error_response",
        "surface_as": "return_value",
        "params": {"message": "actual M3 replacement"},
    })
    provider = FakeProvider()
    host = SmolagentsHost()
    result = host.run_counterfactual(
        SCRIPT, fault=fault, sandbox=tmp_path, model_provider=provider
    )

    assert result.framework_outcome == "completed"
    assert result.final_answer == "文件已写入，但工具返回错误。"
    assert result.model_invoked is True
    assert result.observation_status == "reached"
    assert result.model_id == "fake-smolagents-m3"
    assert result.sampling_params == {"temperature": 0.0}
    assert (tmp_path / "output" / "hello.txt").is_file()
    assert len(provider.messages) == 2
    injection = _events(result, "injection")[0]
    tool_message = next(
        message for message in reversed(provider.messages[1]) if message["role"] == "tool"
    )
    assert tool_message["content"] == str(injection["replacement"]).strip()
    assert tool_message["tool_call_id"] == "real-prefix-smolagents"
    assistant = next(
        message for message in provider.messages[1] if message["role"] == "assistant"
    )
    assert assistant["reasoning_content"] == "真实前缀思考"
    assert assistant["tool_calls"][0]["id"] == "real-prefix-smolagents"
    assert {
        tool["function"]["name"] for tool in provider.tools[0]
    } == {"write_file", "final_answer"}
    outputs = _events(result, "model_output")
    assert [event["m3_phase"] for event in outputs] == ["prefix", "continuation"]
    assert all(event["preset"] is False for event in outputs)
    assert _events(result, "tool_call")[-1]["tool_name"] == "final_answer"


def test_m3_observation_replacement_reaches_structured_tool_message(tmp_path: Path) -> None:
    target = {
        "tool_call": {
            "name": "write_file",
            "args": {"path": "output/hello.txt", "content": "hello smolagents observation\n"},
        }
    }
    fault = FaultSpec.model_validate({
        "injection_point": "observation",
        "fault_type": "error_response",
        "surface_as": "not_applicable",
        "params": {"message": "actual corrupted observation"},
    })
    provider = FakeProvider(target)
    result = SmolagentsHost().run_counterfactual(
        [target], fault=fault, sandbox=tmp_path, model_provider=provider
    )

    injection = _events(result, "injection")[0]
    assert result.observation_status == "reached"
    assert provider.messages[1][-1]["role"] == "tool"
    assert provider.messages[1][-1]["content"] == injection["replacement"]
    tool_result = _events(result, "tool_result")[0]
    assert tool_result["result"]["written"] == "output/hello.txt"
    assert tool_result["injected"] is False


def test_m3_prefix_mismatch_stops_before_tool_and_injection(tmp_path: Path) -> None:
    fault = FaultSpec.model_validate({
        "injection_point": "tool_result",
        "fault_type": "error_response",
        "surface_as": "return_value",
    })
    provider = FakeProvider(match_prefix=False)
    with pytest.raises(ReplayError, match="完全一致"):
        SmolagentsHost().run_counterfactual(
            SCRIPT, fault=fault, sandbox=tmp_path, model_provider=provider
        )
    assert len(provider.messages) == 1
    assert not (tmp_path / "output" / "hello.txt").exists()
    assert not (tmp_path / "output" / "not-registered.txt").exists()


def test_m3_missing_reasoning_stops_before_tool_execution(tmp_path: Path) -> None:
    fault = FaultSpec.model_validate({
        "injection_point": "tool_result",
        "fault_type": "error_response",
        "surface_as": "return_value",
    })
    provider = FakeProvider(prefix_reasoning=None)
    with pytest.raises(ModelProviderError, match="reasoning_content"):
        SmolagentsHost().run_counterfactual(
            SCRIPT, fault=fault, sandbox=tmp_path, model_provider=provider
        )
    assert len(provider.messages) == 1
    assert not (tmp_path / "output" / "hello.txt").exists()


def test_m3_provider_error_is_not_converted_to_injected_failure(tmp_path: Path) -> None:
    class FailingProvider:
        model_id = "failing-provider"
        sampling_params: dict[str, Any] = {}
        state_claim_protocol = "directive_failure_v1"

        def generate(self, messages, *, tools) -> ModelResponse:
            del messages, tools
            raise ModelProviderError("真实模型请求失败: test")

    fault = FaultSpec.model_validate({
        "injection_point": "tool_result",
        "fault_type": "error_response",
        "surface_as": "return_value",
    })
    with pytest.raises(ModelProviderError, match="真实模型请求失败"):
        SmolagentsHost().run_counterfactual(
            SCRIPT, fault=fault, sandbox=tmp_path, model_provider=FailingProvider()
        )
    assert not (tmp_path / "output" / "hello.txt").exists()


def test_m3_precall_contract_only_exposes_final_answer_and_blocks_probe(
    tmp_path: Path,
) -> None:
    class ExtraToolProvider(FakeProvider):
        def generate(self, messages, *, tools) -> ModelResponse:
            response = super().generate(messages, tools=tools)
            if len(self.messages) == 1:
                return response
            return ModelResponse.model_validate({
                "content": "尝试诊断写入",
                "tool_calls": [{
                    "id": "blocked-probe",
                    "name": "write_file",
                    "args": {"path": "output/probe.txt", "content": "must not exist"},
                }],
                "reasoning_content": "续跑思考",
            })

    fault = FaultSpec.model_validate({
        "injection_point": "tool_result",
        "fault_type": "error_response",
        "surface_as": "return_value",
        "params": {"message": "actual M3 replacement"},
    })
    provider = ExtraToolProvider()
    with pytest.raises(ReplayError, match="已在执行前阻断"):
        SmolagentsHost().run_counterfactual(
            SCRIPT, fault=fault, sandbox=tmp_path, model_provider=provider
        )

    assert {tool["function"]["name"] for tool in provider.tools[0]} == {
        "write_file",
        "final_answer",
    }
    assert {tool["function"]["name"] for tool in provider.tools[1]} == {"final_answer"}
    prompt = "\n".join(str(message.get("content", "")) for message in provider.messages[0])
    # 直接检查首次请求的完整提示，而非只检查续跑工具列表或异常信息。
    assert "【M3 调用前契约｜必须逐条遵守，不得跳步】" in prompt
    assert "【第一轮｜只建立精确目标前缀】" in prompt
    assert "【第二轮禁止事项｜收到首轮工具结果后立即生效】" in prompt
    assert "【状态声明格式｜以下易错点从第一轮起生效】" in prompt
    assert "不得调用 final_answer" in prompt
    assert "字符串末尾换行 \\n" in prompt
    assert '"content": "hello smolagents\\n"' in prompt
    assert "不得重试相同参数或不同参数" in prompt
    assert "不得创建探针文件" in prompt
    assert "正确示例" in prompt and "错误示例（均禁止）" in prompt
    assert '```json\n{"state_claim":"failure","reason":"工具返回错误"}\n```' in prompt
    assert "【smolagents 第二轮终答协议】" in prompt
    assert "不得以普通文本结束" in prompt
    assert (tmp_path / "output" / "hello.txt").is_file()
    assert not (tmp_path / "output" / "probe.txt").exists()
