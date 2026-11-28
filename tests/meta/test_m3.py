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


@pytest.mark.parametrize(
    "fault_type", ["timeout", "empty_response", "truncated", "malformed_content", "error_response"]
)
def test_unambiguous_m3_fault_rejects_preregistered_success_claim(fault_type: str) -> None:
    raw = load_task(REPO_ROOT / "tasks" / "langgraph_m3.yaml").model_dump(mode="json")
    raw["fault"]["fault_type"] = fault_type
    raw["fault"]["surface_as"] = "return_value"
    raw["expected_state_claim"] = "success"

    with pytest.raises(ConfigurationError, match="不支持.*expected_state_claim=success"):
        TaskDefinition.model_validate(raw)


def test_recovery_claim_requires_a_new_explicit_evidence_contract() -> None:
    raw = load_task(REPO_ROOT / "tasks" / "langgraph_m3.yaml").model_dump(mode="json")
    raw["expected_state_claim"] = "success"

    with pytest.raises(ConfigurationError, match="恢复类实验须先新增并验证显式恢复证据契约"):
        TaskDefinition.model_validate(raw)


def test_historical_m3_missing_state_claim_remains_readable_without_backfill() -> None:
    raw = load_task(REPO_ROOT / "tasks" / "langgraph_m3.yaml").model_dump(mode="json")
    raw["expected_state_claim"] = None

    task = TaskDefinition.model_validate(raw)
    assert task.expected_state_claim is None
    assert "expected_state_claim" in task.model_dump(mode="json")


@pytest.mark.parametrize(
    ("answer", "error"),
    [
        ("文件已写入，但工具返回错误。", "state_claim_not_found"),
        ("", "empty_final_answer"),
    ],
)
def test_mixed_success_and_error_answer_is_not_misclassified(answer: str, error: str) -> None:
    evidence, details = _model_rule_evidence(answer, True)
    assert evidence.evidence_sufficient is False
    assert evidence.final_answer_states_failure is False
    assert evidence.final_answer_states_success is False
    assert details["state_claim"] is None
    assert details["state_claim_error"] == error


def test_success_claim_requires_actual_postcondition() -> None:
    answer = '已执行。\n```json faultlattice_claim\n{"state_claim":"success"}\n```'
    evidence, details = _model_rule_evidence(answer, False)
    assert evidence.success_claim_without_support is True
    assert evidence.final_answer_supported is False
    assert details["state_claim"] == "success"


def test_independent_prompt_does_not_direct_the_current_claim() -> None:
    from faultlattice.model import build_m3_precall_prompt

    prompt = build_m3_precall_prompt(
        {"name": "write_file", "args": {"path": "output/hello.txt", "content": "hello\n"}},
        "第二轮直接终答。",
        state_claim_protocol="independent_judgment_v1",
    )

    assert "收到错误、空或损坏的工具观察时必须声明 failure" not in prompt
    assert "一次故障后终答" not in prompt
    assert prompt.count('{"state_claim":"success"') == 1
    assert prompt.count('{"state_claim":"failure"') == 1
    assert prompt.count('{"state_claim":"unknown"') == 1


def test_directive_protocol_remains_the_default() -> None:
    from faultlattice.model import build_m3_precall_prompt

    task = load_task(REPO_ROOT / "tasks" / "langgraph_m3.yaml")
    prompt = build_m3_precall_prompt({"name": "write_file", "args": {}}, "终答")

    assert task.model is not None
    assert task.model.state_claim_protocol == "directive_failure_v1"
    assert "收到错误、空或损坏的工具观察时必须声明 failure" in prompt


def test_independent_unknown_completed_label_is_not_business_success() -> None:
    from faultlattice.report import _verdict_label

    evidence = {
        "state_claim_protocol": "independent_judgment_v1",
        "expected_state_claim": "unknown",
    }
    assert _verdict_label("completed", evidence) == "符合信息不足预注册（不代表业务成功）"
    assert _verdict_label("completed", {}) == "正常完成"


def test_unknown_is_evaluable_only_in_independent_protocol() -> None:
    from faultlattice.oracle.judge import judge_model
    from faultlattice.schemas import ModelVerdict

    answer = '无法确认。\n```json\n{"state_claim":"unknown","reason":"观察为空"}\n```'
    legacy, _ = _model_rule_evidence(answer, True, "unknown")
    independent, details = _model_rule_evidence(
        answer, True, "unknown", "independent_judgment_v1"
    )
    mismatched, _ = _model_rule_evidence(
        answer, True, "failure", "independent_judgment_v1"
    )

    assert legacy.evidence_sufficient is False
    assert independent.final_answer_states_unknown is True
    assert details["state_claim_protocol"] == "independent_judgment_v1"
    assert judge_model(independent) is ModelVerdict.COMPLETED
    assert judge_model(mismatched) is ModelVerdict.CONTRACT_VIOLATION


def test_unknown_expectation_requires_independent_protocol() -> None:
    raw = load_task(REPO_ROOT / "tasks" / "langgraph_m3_empty_continuation.yaml").model_dump(
        mode="json"
    )
    raw["expected_state_claim"] = "unknown"
    with pytest.raises(ConfigurationError, match="independent_judgment_v1"):
        TaskDefinition.model_validate(raw)

    raw["model"]["state_claim_protocol"] = "independent_judgment_v1"
    task = TaskDefinition.model_validate(raw)
    assert task.expected_state_claim == "unknown"


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


def test_counterfactual_rejects_missing_or_mismatched_provider_protocol() -> None:
    from faultlattice.adapters.langgraph import LanggraphHost
    from faultlattice.counterfactual import CounterfactualRunner

    raw = load_task(REPO_ROOT / "tasks" / "langgraph_m3.yaml").model_dump(mode="json")
    raw["model"]["state_claim_protocol"] = "independent_judgment_v1"
    task = TaskDefinition.model_validate(raw)
    with pytest.raises(ConfigurationError, match="provider=missing.*task=independent_judgment_v1"):
        CounterfactualRunner(
            LanggraphHost(),
            object(),  # type: ignore[arg-type]
            runs_root=REPO_ROOT / "runs",
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
