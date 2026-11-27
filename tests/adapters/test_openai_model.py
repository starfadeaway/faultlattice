"""OpenAI 兼容模型适配器协议测试；不发起网络请求。"""

from types import SimpleNamespace
from typing import Any, cast

import pytest

openai = pytest.importorskip("openai")

from faultlattice.adapters.openai_model import (  # noqa: E402
    SUPPORTED_OPENAI_VERSION,
    OpenAICompatibleModel,
)
from faultlattice.errors import ModelProviderError  # noqa: E402
from faultlattice.schemas import ModelSpec  # noqa: E402


def _response(
    content: str = "完成",
    *,
    reasoning_content: str | None = None,
    arguments: str = '{"path":"a.txt","content":"x"}',
    finish_reason: str = "stop",
) -> SimpleNamespace:
    function = SimpleNamespace(name="write_file", arguments=arguments)
    call = SimpleNamespace(id="call-1", type="function", function=function)
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=content,
                    tool_calls=[call],
                    reasoning_content=reasoning_content,
                ),
                finish_reason=finish_reason,
            )
        ]
    )


def _capture(provider: OpenAICompatibleModel, response: SimpleNamespace) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    def create(**kwargs: Any) -> SimpleNamespace:
        captured.update(kwargs)
        return response

    provider._client = cast(
        Any, SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    )
    return captured


def test_openai_response_and_tool_call_mapping_preserves_reasoning() -> None:
    spec = ModelSpec(
        provider="openai_compatible",
        model_id="test-model",
        sampling_params={"temperature": 0.0},
    )
    provider = OpenAICompatibleModel(spec, api_key="test-only")
    captured = _capture(provider, _response("继续", reasoning_content="原始思考"))

    result = provider.generate(
        [{"role": "user", "content": "test"}],
        tools=[{"type": "function", "function": {"name": "write_file"}}],
    )
    assert captured["model"] == "test-model"
    assert captured["temperature"] == 0.0
    assert "extra_body" not in captured
    assert result.content == "继续"
    assert result.reasoning_content == "原始思考"
    assert result.finish_reason == "stop"
    assert result.tool_calls[0].args == {"path": "a.txt", "content": "x"}
    assert openai.__version__ == SUPPORTED_OPENAI_VERSION


def test_openai_rejects_non_object_tool_arguments() -> None:
    spec = ModelSpec(provider="openai_compatible", model_id="test-model")
    provider = OpenAICompatibleModel(spec, api_key="test-only")
    provider._client = cast(
        Any,
        SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=lambda **_kwargs: _response(arguments="[]"))
            )
        ),
    )
    with pytest.raises(ModelProviderError, match="JSON object"):
        provider.generate([], tools=[])


@pytest.mark.parametrize("mode", ["default", "enabled"])
def test_deepseek_thinking_requires_original_reasoning_before_tool_continuation(
    mode: str,
) -> None:
    spec = ModelSpec(
        provider="openai_compatible",
        model_id="deepseek-flash",
        sampling_params={"temperature": 0.0},
        reasoning_mode=mode,  # type: ignore[arg-type]
    )
    provider = OpenAICompatibleModel(spec, api_key="test-only")
    captured = _capture(provider, _response(reasoning_content="下一轮思考"))
    with pytest.raises(ModelProviderError, match="不得伪造字段或静默关闭思考"):
        provider.generate(
            [
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{"id": "old", "type": "function"}],
                },
                {"role": "tool", "tool_call_id": "old", "content": "error"},
            ],
            tools=[{"type": "function", "function": {"name": "write_file"}}],
        )
    assert captured == {}


def test_deepseek_thinking_is_explicit_and_reasoning_is_passed_back_unchanged() -> None:
    spec = ModelSpec(
        provider="openai_compatible",
        model_id="deepseek-flash",
        sampling_params={"temperature": 0.0},
        reasoning_mode="enabled",
    )
    provider = OpenAICompatibleModel(spec, api_key="test-only")
    captured = _capture(provider, _response(reasoning_content="第二轮原始思考"))
    assistant = {
        "role": "assistant",
        "content": "",
        "reasoning_content": "第一轮原始思考\n保持原样",
        "tool_calls": [{"id": "call-1", "type": "function"}],
    }
    result = provider.generate(
        [assistant, {"role": "tool", "tool_call_id": "call-1", "content": "error"}],
        tools=[{"type": "function", "function": {"name": "write_file"}}],
    )
    assert captured["messages"][0]["reasoning_content"] == "第一轮原始思考\n保持原样"
    assert captured["extra_body"] == {"thinking": {"type": "enabled"}}
    assert captured["temperature"] == 0.0
    assert result.reasoning_content == "第二轮原始思考"


def test_deepseek_non_thinking_is_only_an_explicit_condition() -> None:
    spec = ModelSpec(
        provider="openai_compatible",
        model_id="deepseek-flash",
        reasoning_mode="disabled",
    )
    provider = OpenAICompatibleModel(spec, api_key="test-only")
    captured = _capture(provider, _response())
    provider.generate([{"role": "user", "content": "test"}], tools=[])
    assert captured["extra_body"] == {"thinking": {"type": "disabled"}}
    assert provider.requires_reasoning_content is False
