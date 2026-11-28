"""LangGraph M3 协议测试：伪模型只验证接线，不冒充真实模型实验。"""

from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("langgraph")

from faultlattice.adapters.langgraph import LanggraphHost  # noqa: E402
from faultlattice.errors import ModelProviderError, ReplayError  # noqa: E402
from faultlattice.model import ModelResponse, ModelToolCall  # noqa: E402
from faultlattice.schemas import FaultSpec  # noqa: E402

PREFIX = [
    {
        "tool_call": {
            "name": "write_file",
            "args": {"path": "output/hello.txt", "content": "hello m3\n"},
        }
    }
]


class FakeProvider:
    model_id = "fake-protocol-model"
    sampling_params = {"temperature": 0.0}

    def __init__(
        self,
        answer: str = "文件已写入，但工具返回错误。",
        *,
        reasoning_content: str | None = "第一轮真实思考",
        requires_reasoning_content: bool = False,
        matching_prefix: bool = True,
        state_claim_protocol: str = "directive_failure_v1",
    ) -> None:
        self.answer = answer
        self.state_claim_protocol = state_claim_protocol
        self.reasoning_content = reasoning_content
        self.requires_reasoning_content = requires_reasoning_content
        self.matching_prefix = matching_prefix
        self.calls: list[dict[str, Any]] = []

    def generate(
        self, messages: list[dict[str, Any]], *, tools: list[dict[str, Any]]
    ) -> ModelResponse:
        self.calls.append({"messages": messages, "tools": tools})
        if len(self.calls) == 1 and self.matching_prefix:
            target = PREFIX[0]["tool_call"]
            return ModelResponse(
                content="",
                tool_calls=[ModelToolCall(id="real-prefix-1", **target)],
                reasoning_content=self.reasoning_content,
            )
        return ModelResponse(content=self.answer, reasoning_content="续跑真实思考")


def _fault(point: str = "tool_result", surface: str = "return_value") -> FaultSpec:
    return FaultSpec.model_validate(
        {
            "injection_point": point,
            "fault_type": "error_response",
            "surface_as": surface,
            "params": {"message": "m3 actual replacement"},
        }
    )


def test_m3_real_prefix_and_reasoning_are_passed_to_injected_continuation(
    tmp_path: Path,
) -> None:
    provider = FakeProvider(requires_reasoning_content=True)
    result = LanggraphHost().run_counterfactual(
        PREFIX,
        fault=_fault(),
        sandbox=tmp_path,
        model_provider=provider,
    )
    assert result.model_invoked is True
    assert result.observation_status == "reached"
    assert result.model_id == "fake-protocol-model"
    assert result.sampling_params == {"temperature": 0.0}
    assert result.final_answer == "文件已写入，但工具返回错误。"
    assert len(provider.calls) == 2
    continuation = provider.calls[1]["messages"]
    prefix_message = next(message for message in continuation if message["role"] == "assistant")
    assert prefix_message["reasoning_content"] == "第一轮真实思考"
    assert prefix_message["tool_calls"][0]["id"] == "real-prefix-1"
    assert continuation[-1]["role"] == "tool"
    assert "m3 actual replacement" in continuation[-1]["content"]
    outputs = [event for event in result.events if event["kind"] == "model_output"]
    assert [event["m3_phase"] for event in outputs] == ["prefix", "continuation"]
    assert outputs[0]["reasoning_content"] == "第一轮真实思考"
    assert all(event["preset"] is False for event in outputs)


def test_m3_empty_tool_result_is_an_observation_that_reached_the_model(
    tmp_path: Path,
) -> None:
    """空对象是有效故障内容；空字符串不等于没有进入模型请求。"""
    provider = FakeProvider(answer="工具返回为空对象，无法据此确认成功。")
    fault = FaultSpec.model_validate(
        {
            "injection_point": "tool_result",
            "fault_type": "empty_response",
            "surface_as": "return_value",
            "params": {"empty": {}},
        }
    )
    result = LanggraphHost().run_counterfactual(
        PREFIX, fault=fault, sandbox=tmp_path, model_provider=provider
    )
    assert result.observation_status == "reached"
    assert provider.calls[1]["messages"][-1]["content"] == "{}"


def test_m3_observation_injection_reaches_provider_without_changing_tool_result(
    tmp_path: Path,
) -> None:
    provider = FakeProvider()
    result = LanggraphHost().run_counterfactual(
        PREFIX,
        fault=_fault("observation", "not_applicable"),
        sandbox=tmp_path,
        model_provider=provider,
    )
    tool_result = next(event for event in result.events if event["kind"] == "tool_result")
    assert tool_result["result"]["written"] == "output/hello.txt"
    assert tool_result["injected"] is False
    assert result.observation_status == "reached"
    assert "m3 actual replacement" in provider.calls[1]["messages"][-1]["content"]


def test_m3_tool_exception_after_real_prefix_does_not_continue(tmp_path: Path) -> None:
    provider = FakeProvider()
    result = LanggraphHost().run_counterfactual(
        PREFIX,
        fault=_fault(surface="raise_exception"),
        sandbox=tmp_path,
        model_provider=provider,
    )
    assert result.framework_outcome == "failed"
    assert result.model_invoked is True
    assert result.observation_status == "not_reached"
    assert len(provider.calls) == 1


def test_m3_rejects_mismatched_real_prefix_before_tool_execution(tmp_path: Path) -> None:
    provider = FakeProvider(matching_prefix=False)
    with pytest.raises(ReplayError, match="本次不执行工具"):
        LanggraphHost().run_counterfactual(
            PREFIX,
            fault=_fault(),
            sandbox=tmp_path,
            model_provider=provider,
        )
    assert not (tmp_path / "output" / "hello.txt").exists()
    assert len(provider.calls) == 1


def test_m3_rejects_missing_thinking_field_before_tool_execution(tmp_path: Path) -> None:
    provider = FakeProvider(reasoning_content=None, requires_reasoning_content=True)
    with pytest.raises(ModelProviderError, match="不会伪造该字段或关闭思考模式"):
        LanggraphHost().run_counterfactual(
            PREFIX,
            fault=_fault(),
            sandbox=tmp_path,
            model_provider=provider,
        )
    assert not (tmp_path / "output" / "hello.txt").exists()


def test_m3_unchanged_observation_is_not_reached(tmp_path: Path) -> None:
    provider = FakeProvider()
    fault = FaultSpec.model_validate(
        {
            "injection_point": "observation",
            "fault_type": "truncated",
            "surface_as": "not_applicable",
            "params": {"keep": 10000},
        }
    )
    result = LanggraphHost().run_counterfactual(
        PREFIX, fault=fault, sandbox=tmp_path, model_provider=provider
    )
    assert result.model_invoked is True
    assert result.observation_status == "not_reached"
    injection = next(event for event in result.events if event["kind"] == "injection")
    assert injection["applied"] is False


def test_m3_precall_contract_removes_tools_and_blocks_extra_write(tmp_path: Path) -> None:
    class ExtraToolProvider(FakeProvider):
        def generate(self, messages, *, tools) -> ModelResponse:
            super().generate(messages, tools=tools)
            if len(self.calls) == 1:
                target = PREFIX[0]["tool_call"]
                return ModelResponse(
                    content="",
                    tool_calls=[ModelToolCall(id="real-prefix-1", **target)],
                    reasoning_content="真实前缀思考",
                )
            return ModelResponse(
                content="尝试诊断写入",
                tool_calls=[
                    ModelToolCall(
                        id="blocked-probe",
                        name="write_file",
                        args={"path": "output/probe.txt", "content": "must not exist"},
                    )
                ],
                reasoning_content="续跑思考",
            )

    provider = ExtraToolProvider()
    with pytest.raises(ReplayError, match="已在执行前阻断"):
        LanggraphHost().run_counterfactual(
            PREFIX, fault=_fault(), sandbox=tmp_path, model_provider=provider
        )

    assert provider.calls[1]["tools"] == []
    system = provider.calls[0]["messages"][0]["content"]
    # 所有易错点必须在第一次真实请求前出现，而不是续跑出错后才补充。
    assert "【M3 调用前契约｜必须逐条遵守，不得跳步】" in system
    assert "【第一轮｜只建立精确目标前缀】" in system
    assert "【第二轮禁止事项｜收到首轮工具结果后立即生效】" in system
    assert "【状态声明格式｜以下易错点从第一轮起生效】" in system
    assert "不得调用 final_answer" in system
    assert "字符串末尾换行 \\n" in system
    assert '"content": "hello m3\\n"' in system
    assert "不得重试相同参数或不同参数" in system
    assert "不得创建探针文件" in system
    assert "正确示例" in system and "错误示例（均禁止）" in system
    assert '```json\n{"state_claim":"failure","reason":"工具返回错误"}\n```' in system
    assert "【LangGraph 第二轮终答协议】" in system
    assert (tmp_path / "output" / "hello.txt").is_file()
    assert not (tmp_path / "output" / "probe.txt").exists()


def test_custom_provider_uses_independent_prompt_without_silent_fallback(tmp_path: Path) -> None:
    provider = FakeProvider(state_claim_protocol="independent_judgment_v1")
    LanggraphHost().run_counterfactual(
        PREFIX, fault=_fault(), sandbox=tmp_path, model_provider=provider
    )

    system = provider.calls[0]["messages"][0]["content"]
    assert "【状态判断与声明格式｜根据实际观察独立判断】" in system
    assert "收到错误、空或损坏的工具观察时必须声明 failure" not in system
    assert system.count('{"state_claim":"unknown"') == 1
