"""控制台兼容入口；模型目录实现位于可安装核心包。"""

from faultlattice.model_catalog import (
    LLMOption,
    ReasoningMode,
    discover_model_options,
    resolve_advisor_option,
    resolve_model_option,
)

__all__ = [
    "LLMOption",
    "ReasoningMode",
    "discover_model_options",
    "resolve_advisor_option",
    "resolve_model_option",
]
