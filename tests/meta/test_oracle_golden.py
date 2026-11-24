"""Oracle 元测试：golden cases 驱动判定器回归（spec 第 5.3 节）。

- 每个 golden case 是一个"证据 → 预期 verdict"的固定样例；
- 元测试断言：判定器输出与 golden case 一致、输出确定（跑两次相同）、
  框架层五类 verdict 全覆盖——这是 Oracle 标记为 golden_verified 的依据；
- golden case 变更 = 判据变更，必须同步修订 spec 第 5 节。
"""

from pathlib import Path

import pytest
import yaml

from faultlattice.oracle.judge import (
    FrameworkEvidence,
    ModelEvidence,
    judge_framework,
    judge_model,
)
from faultlattice.schemas import FrameworkVerdict, ModelVerdict

GOLDEN_DIR = Path(__file__).parent.parent / "golden"


def _load_cases() -> list[dict]:
    cases = []
    for path in sorted(GOLDEN_DIR.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        data["_file"] = path.name
        cases.append(data)
    return cases


CASES = _load_cases()


def _judge(case: dict) -> str:
    evidence = case["evidence"]
    if case["layer"] == "framework":
        return judge_framework(FrameworkEvidence(**evidence)).value
    return judge_model(ModelEvidence(**evidence)).value


@pytest.mark.parametrize("case", CASES, ids=[c["case_id"] for c in CASES])
def test_golden_case(case: dict) -> None:
    assert _judge(case) == case["expected_verdict"], (
        f"golden case {case['_file']} 判定不一致："
        f"期望 {case['expected_verdict']}，实际 {_judge(case)}"
    )


@pytest.mark.parametrize("case", CASES, ids=[c["case_id"] for c in CASES])
def test_judge_is_deterministic(case: dict) -> None:
    # 同一证据两次判定必须完全一致（deterministic Oracle 的基本要求）
    assert _judge(case) == _judge(case)


def test_framework_golden_cases_cover_all_five_verdicts() -> None:
    covered = {c["expected_verdict"] for c in CASES if c["layer"] == "framework"}
    expected = {v.value for v in FrameworkVerdict}
    assert covered == expected, f"框架层 golden cases 未覆盖全部 verdict，缺: {expected - covered}"


def test_model_golden_cases_cover_all_judgeable_verdicts() -> None:
    # not_applicable 不由 judge_model 产生（由 resolve_not_applicable_reason 决定），
    # 因此模型层 golden cases 覆盖其余五类即可
    covered = {c["expected_verdict"] for c in CASES if c["layer"] == "model"}
    expected = {v.value for v in ModelVerdict} - {ModelVerdict.NOT_APPLICABLE.value}
    assert covered == expected, f"模型层 golden cases 未覆盖全部 verdict，缺: {expected - covered}"
