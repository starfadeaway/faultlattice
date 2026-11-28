"""OpenAI 兼容 Chat Completions 的真实模型提供方（SDK 固定为 3.59.0）。

只负责 SDK 与 FaultLattice 的 ModelProvider 协议互转，不包含 Agent loop。
API 密钥只从环境变量传入，不写入任务、轨迹、报告或异常消息。
"""

from __future__ import annotations

import json
import re
from importlib.metadata import version as package_version
from typing import Any, cast

from openai import APIStatusError, OpenAI, OpenAIError

from faultlattice.errors import AdapterCapabilityError, ModelProviderError
from faultlattice.model import ModelResponse, ModelToolCall
from faultlattice.schemas import ModelSpec

SUPPORTED_OPENAI_VERSION = "3.59.0"
INSTALLED_OPENAI_VERSION = package_version("openai")


class OpenAICompatibleModel:
    """调用用户配置的 OpenAI 兼容端点；禁用 SDK 隐式重试和模式降级。"""

    def __init__(
        self,
        spec: ModelSpec,
        *,
        api_key: str,
        base_url: str | None = None,
        timeout_seconds: float = 60.0,
    ) -> None:
        if INSTALLED_OPENAI_VERSION != SUPPORTED_OPENAI_VERSION:
            raise AdapterCapabilityError(
                f"OpenAI SDK 必须为 {SUPPORTED_OPENAI_VERSION}，"
                f"实际为 {INSTALLED_OPENAI_VERSION}。"
            )
        if spec.provider != "openai_compatible":
            raise AdapterCapabilityError(f"不支持的模型提供方: {spec.provider}")
        self.model_id = spec.model_id
        self.sampling_params = dict(spec.sampling_params)
        self.reasoning_mode = spec.reasoning_mode
        self.state_claim_protocol = spec.state_claim_protocol
        self.is_deepseek = self.model_id.startswith("deepseek-")
        if not self.is_deepseek and self.reasoning_mode != "default":
            raise AdapterCapabilityError("当前仅验证 DeepSeek 的显式思考模式开关")
        # DeepSeek default 当前也是思考模式；工具续跑必须回传上一轮原始字段。
        self.requires_reasoning_content = self.is_deepseek and self.reasoning_mode in (
            "default",
            "enabled",
        )
        self._client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout_seconds,
            max_retries=0,
        )

    def generate(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]],
    ) -> ModelResponse:
        """执行一次真实请求；网络与 SDK 错误不得伪装成实验故障。"""
        if self.requires_reasoning_content and tools:
            missing = any(
                message.get("role") == "assistant" and "reasoning_content" not in message
                for message in messages
            )
            if missing:
                raise ModelProviderError(
                    "DeepSeek 思考模式要求回传此前每轮 assistant 的 reasoning_content；"
                    "当前上下文缺少该原始字段。不得伪造字段或静默关闭思考，请从真实模型前缀重新运行。"
                )
        request: dict[str, Any] = {
            "model": self.model_id,
            "messages": cast(Any, messages),
            "tools": cast(Any, tools),
            **self.sampling_params,
        }
        if self.is_deepseek and self.reasoning_mode != "default":
            request["extra_body"] = {
                "thinking": {"type": "enabled" if self.reasoning_mode == "enabled" else "disabled"}
            }
        try:
            response = self._client.chat.completions.create(**request)
        except OpenAIError as exc:
            # 只保留状态码与提供方错误消息，不拼接请求、响应头或 Authorization。
            detail = ""
            if isinstance(exc, APIStatusError):
                detail = f"（HTTP {exc.status_code}）"
                body = exc.body if isinstance(exc.body, dict) else {}
                error = body.get("error") if isinstance(body.get("error"), dict) else body
                message = error.get("message") if isinstance(error, dict) else None
                if isinstance(message, str):
                    safe_message = re.sub(r"sk-[A-Za-z0-9_-]+", "sk-***", message)
                    safe_message = " ".join(safe_message.splitlines())[:500]
                    detail = f"（HTTP {exc.status_code}：{safe_message}）"
            raise ModelProviderError(
                f"真实模型请求失败: {type(exc).__name__}{detail}"
            ) from exc
        if not response.choices:
            raise ModelProviderError("真实模型响应缺少 choices")
        choice = response.choices[0]
        message = choice.message
        reasoning_content = getattr(message, "reasoning_content", None)
        if reasoning_content is not None and not isinstance(reasoning_content, str):
            raise ModelProviderError("真实模型 reasoning_content 必须是字符串或 null")
        calls: list[ModelToolCall] = []
        for call in message.tool_calls or []:
            if call.type != "function":
                raise ModelProviderError(f"不支持的工具调用类型: {call.type}")
            try:
                args = json.loads(call.function.arguments)
            except json.JSONDecodeError as exc:
                raise ModelProviderError("真实模型工具参数不是合法 JSON") from exc
            if not isinstance(args, dict):
                raise ModelProviderError("真实模型工具参数必须是 JSON object")
            calls.append(ModelToolCall(id=call.id, name=call.function.name, args=args))
        return ModelResponse(
            content=message.content or "",
            tool_calls=calls,
            reasoning_content=reasoning_content,
            finish_reason=choice.finish_reason,
        )
