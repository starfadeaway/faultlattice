"""真实模型提供方协议与框架无关的数据结构（spec 第 2 节 M3）。

核心只定义消息、工具 schema 和返回值协议，不导入 OpenAI SDK，也不实现
Agent loop。具体 SDK 在 adapters 中；真实图循环仍由被测宿主执行。
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field


class ModelToolCall(BaseModel):
    """一次真实模型工具调用；参数必须是已解析的 JSON object。"""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    args: dict[str, Any]


class ModelResponse(BaseModel):
    """真实模型单轮输出；文本与工具调用可以同时存在。"""

    model_config = ConfigDict(frozen=True)

    content: str = ""
    tool_calls: list[ModelToolCall] = Field(default_factory=list)
    # 提供方原始思考字段；工具续跑时必须随对应 assistant 消息完整回传。
    reasoning_content: str | None = None
    # 保留提供方结束原因，调用方必须能识别 length 造成的截断输出。
    finish_reason: str | None = None


@runtime_checkable
class ModelProvider(Protocol):
    """M3 模型提供方协议；实现方必须执行真实模型请求。"""

    model_id: str
    sampling_params: dict[str, Any]

    def generate(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]],
    ) -> ModelResponse:
        """根据实际消息上下文和工具 schema 生成下一轮输出。"""
        ...
