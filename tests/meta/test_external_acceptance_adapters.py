"""外部接入验收适配器的无故障与故障观察分支回归测试。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from external_agents.drafts.lorekeeper import LoreKeeperHostAdapter
from faultlattice.errors import ConfigurationError
from faultlattice.schemas import ExpectedPostcondition

ORIGINAL = "(0.8 + 0.2) * 1000"


def _state(*, expression: str, ok: bool, error: str | None, failures: int) -> Any:
    return SimpleNamespace(
        steps=[
            SimpleNamespace(
                step=1,
                tool_name="calculator",
                args={"expression": expression},
                ok=ok,
                error=error,
                latency_ms=1,
                result_chars=4,
            )
        ],
        tool_failures=failures,
        stop_reason="final_answer",
        answer="[计算完成] 完成。" if ok else "[计算失败] 失败。",
    )


def _expected(corrupted: str | None = None) -> ExpectedPostcondition:
    params: dict[str, Any] = {"summary": "测试", "original_expression": ORIGINAL}
    if corrupted is not None:
        params["corrupted_expression"] = corrupted
    return ExpectedPostcondition(kind="host_state", params=params)


def test_lorekeeper_no_fault_observation_requires_original_success(tmp_path: Path) -> None:
    adapter = LoreKeeperHostAdapter()
    adapter._last_state = _state(expression=ORIGINAL, ok=True, error=None, failures=0)

    observed = adapter.observe_postcondition(_expected(), sandbox=tmp_path)

    assert observed.task_succeeded is True
    assert observed.side_effects_as_expected is True
    assert observed.evidence_sufficient is True
    assert observed.evidence["injected_failure_observed"] is False
    assert observed.evidence["steps"][0]["args"]["expression"] == ORIGINAL


def test_lorekeeper_fault_observation_contract_is_unchanged(tmp_path: Path) -> None:
    adapter = LoreKeeperHostAdapter()
    adapter._last_state = _state(
        expression="1 / 0", ok=False, error="[错误] 1 / 0 出现除零。", failures=1
    )

    observed = adapter.observe_postcondition(_expected("1 / 0"), sandbox=tmp_path)

    assert observed.task_succeeded is False
    assert observed.side_effects_as_expected is True
    assert observed.evidence["injected_failure_observed"] is True
    assert observed.evidence["tool_failures"] == 1


@pytest.mark.parametrize("answer", ["[计算失败] 失败。", "[计算完成] 完成。"])
def test_lorekeeper_script_accepts_explicit_result_prefixes(answer: str) -> None:
    script = [
        {"tool_call": {"name": "calculator", "args": {"expression": ORIGINAL}}},
        {"final_answer": answer},
    ]

    assert LoreKeeperHostAdapter._parse_script(script)[:2] == (ORIGINAL, answer)


def test_lorekeeper_script_rejects_unregistered_result_prefix() -> None:
    script = [
        {"tool_call": {"name": "calculator", "args": {"expression": ORIGINAL}}},
        {"final_answer": "已经完成。"},
    ]

    with pytest.raises(ConfigurationError, match="计算失败.*计算完成"):
        LoreKeeperHostAdapter._parse_script(script)
