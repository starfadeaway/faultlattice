"""M3 任务协议与模型回答证据规则的元测试。"""

from pathlib import Path

import pytest

from faultlattice.errors import ConfigurationError, ReplayError
from faultlattice.runner import _model_rule_evidence, load_task
from faultlattice.schemas import TaskDefinition

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_m3_preregistered_task_is_valid() -> None:
    task = load_task(REPO_ROOT / "tasks" / "langgraph_m3.yaml")
    assert task.mode.value == "M3"
    assert task.model is not None
    assert task.counterfactual_source is not None
    assert task.min_evaluable == 30
    assert [layer.value for layer in task.target_layers] == ["framework", "model"]


def test_m3_requires_real_model_and_source() -> None:
    raw = {
        "task_id": "invalid_m3",
        "host": "langgraph",
        "mode": "M3",
        "fault": {
            "injection_point": "tool_result",
            "fault_type": "error_response",
            "surface_as": "return_value",
        },
        "target_layers": ["model"],
        "expected_postcondition": {"kind": "file_written", "params": {}},
        "expected_behavior": "真实模型续跑",
        "fault_recoverable": True,
        "oracle": {
            "source": "rule",
            "determinism": "deterministic",
            "validation": "golden_verified",
        },
        "inconclusive_threshold": 0.2,
        "min_evaluable": 30,
    }
    with pytest.raises(ConfigurationError, match="model"):
        TaskDefinition.model_validate(raw)


def test_m3_rejects_tool_args_continuation() -> None:
    task = load_task(REPO_ROOT / "tasks" / "langgraph_m3.yaml")
    raw = task.model_dump(mode="json")
    raw["fault"]["injection_point"] = "tool_args"
    raw["fault"]["fault_type"] = "invalid_args"
    with pytest.raises(ConfigurationError, match="tool_result"):
        TaskDefinition.model_validate(raw)


@pytest.mark.parametrize("fault_type", ["timeout", "empty_response", "malformed_content", "error_response"])
def test_unambiguous_m3_fault_rejects_preregistered_success_claim(fault_type: str) -> None:
    raw = load_task(REPO_ROOT / "tasks" / "langgraph_m3.yaml").model_dump(mode="json")
    raw["fault"]["fault_type"] = fault_type
    raw["fault"]["surface_as"] = "return_value"
    raw["expected_state_claim"] = "success"

    with pytest.raises(ConfigurationError, match="不得预注册 expected_state_claim=success"):
        TaskDefinition.model_validate(raw)


def test_truncated_m3_fault_can_preregister_a_separately_justified_success_claim() -> None:
    raw = load_task(REPO_ROOT / "tasks" / "langgraph_m3.yaml").model_dump(mode="json")
    raw["fault"]["fault_type"] = "truncated"
    raw["fault"]["surface_as"] = "return_value"
    raw["expected_state_claim"] = "success"

    assert TaskDefinition.model_validate(raw).expected_state_claim == "success"


def test_historical_m3_missing_state_claim_remains_readable_without_backfill() -> None:
    raw = load_task(REPO_ROOT / "tasks" / "langgraph_m3.yaml").model_dump(mode="json")
    raw["expected_state_claim"] = None

    task = TaskDefinition.model_validate(raw)
    assert task.expected_state_claim is None
    assert "expected_state_claim" in task.model_dump(mode="json")


def test_mixed_success_and_error_answer_is_not_misclassified() -> None:
    evidence, details = _model_rule_evidence("文件已写入，但工具返回错误。", True)
    assert evidence.evidence_sufficient is False
    assert evidence.final_answer_states_failure is False
    assert evidence.final_answer_states_success is False
    assert details["state_claim"] is None
    assert details["state_claim_error"] is None


def test_success_claim_requires_actual_postcondition() -> None:
    answer = '已执行。\n```json faultlattice_claim\n{"state_claim":"success"}\n```'
    evidence, details = _model_rule_evidence(answer, False)
    assert evidence.success_claim_without_support is True
    assert evidence.final_answer_supported is False
    assert details["state_claim"] == "success"


def test_m3_source_must_exist(tmp_path: Path) -> None:
    from faultlattice.adapters.langgraph import LanggraphHost
    from faultlattice.counterfactual import CounterfactualRunner

    task = load_task(REPO_ROOT / "tasks" / "langgraph_m3.yaml")
    task = task.model_copy(update={"counterfactual_source": str(tmp_path / "missing")})
    with pytest.raises(Exception, match="run.json"):
        CounterfactualRunner(
            LanggraphHost(),
            object(),  # type: ignore[arg-type]
            runs_root=tmp_path,
            repo_root=REPO_ROOT,
        ).run(task)


def test_counterfactual_rejects_non_m3_task() -> None:
    task = load_task(REPO_ROOT / "tasks" / "langgraph_write.yaml")
    from faultlattice.counterfactual import CounterfactualRunner

    with pytest.raises(ReplayError, match="M3"):
        CounterfactualRunner(
            object(),  # type: ignore[arg-type]
            object(),  # type: ignore[arg-type]
            runs_root=Path("unused"),
            repo_root=REPO_ROOT,
        ).run(task)
