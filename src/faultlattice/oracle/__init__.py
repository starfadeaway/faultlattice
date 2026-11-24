"""Oracle 包：判定器与 golden case 支持。

判定规则见 docs/spec-v0.1.md 第 5 节。
"""

from faultlattice.oracle.judge import (
    FrameworkEvidence,
    ModelEvidence,
    judge_framework,
    judge_model,
    resolve_not_applicable_reason,
)

__all__ = [
    "FrameworkEvidence",
    "ModelEvidence",
    "judge_framework",
    "judge_model",
    "resolve_not_applicable_reason",
]
