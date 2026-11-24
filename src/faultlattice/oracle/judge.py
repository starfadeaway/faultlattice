"""Oracle 判定器：框架层与模型层判据的确定性实现。

判据全文见 docs/spec-v0.1.md 第 5 节。本模块是判定树的直接翻译，
不引入任何 LLM；判据改动必须先改 spec 再改这里。

重要边界：
- 证据不足返回 inconclusive，是正常判定结果，不是程序异常；
- inconclusive / not_applicable 的原因判定顺序固定（spec 5.2）：
  layer_not_targeted → injection_failed → mode_not_applicable
  → model_not_invoked → oracle_evidence_insufficient；
- 框架层判据不读取或虚构"最终回答"；模型层判据不覆盖框架层结论。
"""

from __future__ import annotations

from faultlattice.schemas import (
    ExecutionMode,
    FrameworkVerdict,
    ModelVerdict,
    NotApplicableReason,
    TargetLayer,
)


class FrameworkEvidence:
    """框架层判定所需的事实证据（全部来自轨迹与实际副作用，非推断）。

    evidence_sufficient=False 时其余字段可以不可信，判定器直接返回
    inconclusive，不强行判沉默失败（spec 第 4.4 节）。
    """

    def __init__(
        self,
        *,
        evidence_sufficient: bool,
        task_succeeded: bool,
        failure_signal_to_caller: bool,
        side_effects_as_expected: bool,
        extra_side_effects: bool = False,
        silent_empty_result: bool = False,
        success_without_execution_support: bool = False,
        expected_side_effect_missing: bool = False,
    ) -> None:
        self.evidence_sufficient = evidence_sufficient
        self.task_succeeded = task_succeeded
        self.failure_signal_to_caller = failure_signal_to_caller
        self.side_effects_as_expected = side_effects_as_expected
        self.extra_side_effects = extra_side_effects
        self.silent_empty_result = silent_empty_result
        self.success_without_execution_support = success_without_execution_support
        self.expected_side_effect_missing = expected_side_effect_missing


class ModelEvidence:
    """模型层判定所需的事实证据。"""

    def __init__(
        self,
        *,
        evidence_sufficient: bool,
        task_succeeded: bool,
        final_answer_states_failure: bool,
        final_answer_empty_or_irrelevant: bool = False,
        success_claim_without_support: bool = False,
        behavior_matches_contract: bool = True,
        final_answer_supported: bool = True,
    ) -> None:
        self.evidence_sufficient = evidence_sufficient
        self.task_succeeded = task_succeeded
        self.final_answer_states_failure = final_answer_states_failure
        self.final_answer_empty_or_irrelevant = final_answer_empty_or_irrelevant
        self.success_claim_without_support = success_claim_without_support
        self.behavior_matches_contract = behavior_matches_contract
        self.final_answer_supported = final_answer_supported


def judge_framework(ev: FrameworkEvidence) -> FrameworkVerdict:
    """框架层判定树（spec 第 5.1 节的逐条翻译）。"""
    if not ev.evidence_sufficient:
        return FrameworkVerdict.INCONCLUSIVE

    if ev.task_succeeded and ev.failure_signal_to_caller:
        # 任务实际成功，框架却向调用方返回失败信号
        return FrameworkVerdict.CONTRACT_VIOLATION

    if (
        not ev.task_succeeded
        and ev.failure_signal_to_caller
        and not ev.extra_side_effects
    ):
        return FrameworkVerdict.EXPLICIT_FAILURE

    if not ev.failure_signal_to_caller and (
        ev.silent_empty_result
        or ev.success_without_execution_support
        or ev.expected_side_effect_missing
    ):
        return FrameworkVerdict.SILENT_FAILURE

    if (
        ev.side_effects_as_expected
        and not ev.success_without_execution_support
        and ev.task_succeeded
    ):
        return FrameworkVerdict.COMPLETED

    return FrameworkVerdict.CONTRACT_VIOLATION


def judge_model(ev: ModelEvidence) -> ModelVerdict:
    """模型层判定树（spec 第 5.2 节的逐条翻译）。

    调用前必须先确认模型层适用（not_applicable 的判定见
    resolve_not_applicable_reason），本函数不处理不适用情形。
    """
    if not ev.evidence_sufficient:
        return ModelVerdict.INCONCLUSIVE

    if ev.task_succeeded and ev.final_answer_states_failure:
        return ModelVerdict.CONTRACT_VIOLATION

    if not ev.task_succeeded and ev.final_answer_states_failure:
        return ModelVerdict.EXPLICIT_FAILURE

    if not ev.final_answer_states_failure and (
        ev.final_answer_empty_or_irrelevant or ev.success_claim_without_support
    ):
        return ModelVerdict.SILENT_FAILURE

    if ev.task_succeeded and ev.behavior_matches_contract and ev.final_answer_supported:
        return ModelVerdict.COMPLETED

    return ModelVerdict.CONTRACT_VIOLATION


def resolve_not_applicable_reason(
    *,
    layer: TargetLayer,
    target_layers: list[TargetLayer],
    injection_applied: bool,
    mode: ExecutionMode,
    model_invoked: bool,
) -> NotApplicableReason | None:
    """按固定顺序判定模型层 not_applicable 的主原因（spec 第 5.2 节）。

    返回 None 表示该层适用、需要正常判定。框架层不会被判 not_applicable
    （框架在 M0–M2 中必然参与），这里只对模型层返回非 None。
    """
    if layer not in target_layers:
        return NotApplicableReason.LAYER_NOT_TARGETED
    if not injection_applied:
        # 注入失败的运行不进入"模型是否被调用"等后续判断
        return NotApplicableReason.INJECTION_FAILED
    if mode in (ExecutionMode.M0, ExecutionMode.M1, ExecutionMode.M2):
        return NotApplicableReason.MODE_NOT_APPLICABLE
    if layer is TargetLayer.MODEL and not model_invoked:
        return NotApplicableReason.MODEL_NOT_INVOKED
    return None
