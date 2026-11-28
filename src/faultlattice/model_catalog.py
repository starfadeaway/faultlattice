"""OpenAI 兼容模型目录；核心 CLI 与控制台共用，密钥不进入公开响应。"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal, cast

from faultlattice.errors import ConfigurationError

ReasoningMode = Literal["default", "enabled", "disabled"]
_OPTION_ENV_RE = re.compile(
    r"^FAULTLATTICE_LLM_(?P<id>[A-Z0-9_]+?)_(?P<field>API_KEY|BASE_URL|MODEL_ID|LABEL|CAPABILITIES|REASONING_MODE|SAMPLING_PARAMS|ADVISOR_SAMPLING_PARAMS)$"
)
_REASONING_MODES = {"default", "enabled", "disabled"}


@dataclass(frozen=True)
class LLMOption:
    option_id: str
    label: str
    model_id: str
    base_url: str | None
    capabilities: tuple[str, ...]
    api_key: str
    reasoning_mode: ReasoningMode = "default"
    sampling_params: dict[str, object] = field(default_factory=dict)
    advisor_sampling_params: dict[str, object] = field(default_factory=dict)

    def public(self) -> dict[str, object]:
        return {
            "id": self.option_id,
            "label": self.label,
            "model_id": self.model_id,
            "base_url": self.base_url,
            "capabilities": list(self.capabilities),
            "reasoning_mode": self.reasoning_mode,
            "sampling_params": dict(self.sampling_params),
        }


def _sampling_params(
    option_id: str, config: Mapping[str, str], field_name: str
) -> dict[str, object]:
    raw = config.get(field_name, "").strip()
    try:
        value = json.loads(raw) if raw else {}
    except ValueError as exc:
        raise ConfigurationError(f"模型 {option_id} 的 {field_name} 必须是 JSON object") from exc
    if not isinstance(value, dict) or not all(isinstance(key, str) and key for key in value):
        raise ConfigurationError(f"模型 {option_id} 的 {field_name} 必须是 JSON object")
    return value


def _grouped(values: Mapping[str, str]) -> dict[str, dict[str, str]]:
    grouped: dict[str, dict[str, str]] = {}
    for name, raw_value in values.items():
        match = _OPTION_ENV_RE.fullmatch(name)
        if match is None:
            continue
        value = raw_value.strip()
        if value:
            grouped.setdefault(match.group("id"), {})[match.group("field")] = value
    return grouped


def _option(option_id: str, config: Mapping[str, str]) -> LLMOption | None:
    capabilities = tuple(
        item.strip().lower()
        for item in config.get("CAPABILITIES", "").split(",")
        if item.strip()
    )
    api_key = config.get("API_KEY", "")
    model_id = config.get("MODEL_ID", "")
    if "chat" not in capabilities or not api_key or not model_id:
        return None
    reasoning_mode = config.get("REASONING_MODE", "default").lower()
    if reasoning_mode not in _REASONING_MODES:
        raise ConfigurationError(
            f"模型 {option_id} 的 REASONING_MODE 只能是 default / enabled / disabled"
        )
    if not model_id.startswith("deepseek-") and reasoning_mode != "default":
        raise ConfigurationError(f"模型 {option_id} 尚未验证显式思考模式开关，请使用 default")
    normalized_id = option_id.lower()
    return LLMOption(
        option_id=normalized_id,
        label=config.get("LABEL", normalized_id),
        model_id=model_id,
        base_url=config.get("BASE_URL") or None,
        capabilities=capabilities,
        api_key=api_key,
        reasoning_mode=cast(ReasoningMode, reasoning_mode),
        sampling_params=_sampling_params(option_id, config, "SAMPLING_PARAMS"),
        advisor_sampling_params=_sampling_params(
            option_id, config, "ADVISOR_SAMPLING_PARAMS"
        ),
    )


def discover_model_options(env: Mapping[str, str] | None = None) -> list[LLMOption]:
    """校验完整聊天目录；供设置和模型选择界面使用。"""
    values = os.environ if env is None else env
    options = [
        option
        for option_id, config in sorted(_grouped(values).items())
        if (option := _option(option_id, config)) is not None
    ]
    legacy_key = values.get("FAULTLATTICE_MODEL_API_KEY", "").strip()
    legacy_advisor = values.get("FAULTLATTICE_ADVISOR_MODEL_ID", "").strip()
    if legacy_key and legacy_advisor:
        if any(option.option_id == "default" for option in options):
            raise ConfigurationError("模型选项 DEFAULT 与兼容默认配置重名，请改用其他 ID")
        options.insert(
            0,
            LLMOption(
                option_id="default",
                label="默认建议模型",
                model_id=legacy_advisor,
                base_url=values.get("FAULTLATTICE_MODEL_BASE_URL", "").strip() or None,
                capabilities=("chat",),
                api_key=legacy_key,
            ),
        )
    return options


def resolve_model_option(
    model_id: str, env: Mapping[str, str] | None = None
) -> LLMOption | None:
    """只解析并校验本次 model_id，避免无关目录项阻断 M3。"""
    values = os.environ if env is None else env
    matches = [
        option
        for option_id, config in sorted(_grouped(values).items())
        if config.get("MODEL_ID", "") == model_id
        if (option := _option(option_id, config)) is not None
    ]
    if len(matches) > 1:
        raise ConfigurationError(f"模型 {model_id} 在目录中有多个完整配置，请保证 model_id 唯一")
    if matches:
        return matches[0]
    api_key = values.get("FAULTLATTICE_MODEL_API_KEY", "").strip()
    if not api_key:
        return None
    return LLMOption(
        option_id="default",
        label="兼容默认模型",
        model_id=model_id,
        base_url=values.get("FAULTLATTICE_MODEL_BASE_URL", "").strip() or None,
        capabilities=("chat",),
        api_key=api_key,
    )


def resolve_advisor_option(option_id: str | None = None) -> LLMOption:
    options = discover_model_options()
    if not options:
        raise ConfigurationError(
            "尚未配置可用于对话的模型。请在本机 .env 配置带 chat 能力的 "
            "FAULTLATTICE_LLM_<ID>_* 项，或使用兼容默认配置"
        )
    if option_id is None:
        return options[0]
    selected = next((option for option in options if option.option_id == option_id), None)
    if selected is None:
        raise ConfigurationError(f"建议模型选项不存在或未完整配置: {option_id}")
    return selected
