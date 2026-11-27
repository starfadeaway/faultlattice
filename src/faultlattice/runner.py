"""运行编排器：执行宿主 → 注入故障 → 记录轨迹 → 调用 Oracle → 写产物。

确定性实验流程（spec 第 1 节），不含任何 Agent loop。runner 只面向
faultlattice.host.HostAdapter 协议编程，具体宿主由 CLI 装配传入
（core 不依赖 adapters，由 AST 检查强制）。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import yaml

from faultlattice.errors import ConfigurationError, TraceFormatError
from faultlattice.host import (
    CounterfactualHost,
    HostAdapter,
    PostconditionObservation,
    StatefulHost,
)
from faultlattice.model import ModelProvider
from faultlattice.oracle.judge import (
    FrameworkEvidence,
    ModelEvidence,
    judge_framework,
    judge_model,
    resolve_not_applicable_reason,
)
from faultlattice.schemas import (
    FrameworkVerdict,
    InconclusiveReason,
    ModelVerdict,
    ObservationStatus,
    OracleJudgement,
    RunManifest,
    TargetLayer,
    TaskDefinition,
)
from faultlattice.trace import TraceWriter, read_jsonl
from faultlattice.versions import collect_versions


def load_task(path: Path) -> TaskDefinition:
    """加载并校验预注册任务文件。缺字段 / 非法组合在此显式报错。"""
    path = Path(path)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigurationError(f"任务文件不是合法 YAML: {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigurationError(f"任务文件必须是 YAML mapping: {path}")
    try:
        return TaskDefinition.model_validate(raw)
    except Exception as exc:
        raise ConfigurationError(f"任务预注册校验失败: {path}: {exc}") from exc


def _new_run_id(task_id: str) -> str:
    from faultlattice.canonical import sha256_hex

    now = datetime.now(UTC)
    seed = f"{task_id}|{now.isoformat()}".encode()
    return f"{now.strftime('%Y%m%dT%H%M%S')}-{sha256_hex(seed)[:8]}"


def _evaluate_postcondition(
    task: TaskDefinition, sandbox: Path, host: HostAdapter
) -> tuple[bool, bool, dict]:
    """分别返回任务完成、副作用符合预期和原始证据，三者不能混为一谈。"""
    pc = task.expected_postcondition
    if pc.kind == "file_written":
        rel = pc.params.get("path", "")
        target = sandbox / rel
        exists = target.is_file()
        contains_ok = True
        if exists and "content_contains" in pc.params:
            contains_ok = pc.params["content_contains"] in target.read_text(encoding="utf-8")
        ok = exists and contains_ok
        return ok, ok, {
            "kind": pc.kind,
            "path": rel,
            "exists": exists,
            "content_contains_ok": contains_ok,
        }
    if pc.kind == "file_absent":
        rel = pc.params.get("path", "")
        exists = (sandbox / rel).exists()
        side_effect_ok = not exists
        # 当前用于 write_file 硬超时：文件按预期未写入，但写入任务并未完成。
        return False, side_effect_ok, {"kind": pc.kind, "path": rel, "exists": exists}
    if pc.kind == "host_state":
        if not isinstance(host, StatefulHost):
            return False, False, {
                "kind": pc.kind,
                "evidence_sufficient": False,
                "observation_summary": "宿主未实现 StatefulHost，无法核验业务状态",
            }
        try:
            observed = host.observe_postcondition(pc, sandbox=sandbox)
        except Exception as exc:
            return False, False, {
                "kind": pc.kind,
                "evidence_sufficient": False,
                "observation_summary": f"业务状态观察失败（{type(exc).__name__}），未形成判定证据",
            }
        if not isinstance(observed, PostconditionObservation):
            return False, False, {
                "kind": pc.kind,
                "evidence_sufficient": False,
                "observation_summary": "宿主返回了非法的业务状态观察类型",
            }
        evidence = {
            "kind": pc.kind,
            "evidence_sufficient": observed.evidence_sufficient,
            **observed.evidence,
        }
        return observed.task_succeeded, observed.side_effects_as_expected, evidence
    # 未知的 postcondition 类型：证据不足，由 Oracle 判 inconclusive
    return False, False, {"kind": pc.kind, "unknown_postcondition_kind": True}


def _model_rule_evidence(
    final_answer: str | None, task_succeeded: bool
) -> tuple[ModelEvidence, dict]:
    """用公开、确定性的文本规则提取模型回答证据。

    该规则只识别明确的成功 / 失败声明，不声称理解任意自然语言。混合回答
    （例如“文件已写入，但工具返回错误”）不会被简单归类为任务失败。
    """
    answer = final_answer or ""
    lowered = answer.lower()
    failure_markers = ["失败", "无法", "未能", "错误", "failed", "failure", "error"]
    success_markers = ["已写入", "已完成", "成功", "written", "completed", "success"]
    matched_failure = [marker for marker in failure_markers if marker in lowered]
    matched_success = [marker for marker in success_markers if marker in lowered]
    states_failure = bool(matched_failure) and not matched_success
    success_without_support = bool(matched_success) and not task_succeeded
    evidence = ModelEvidence(
        evidence_sufficient=True,
        task_succeeded=task_succeeded,
        final_answer_states_failure=states_failure,
        final_answer_empty_or_irrelevant=not answer.strip(),
        success_claim_without_support=success_without_support,
        behavior_matches_contract=True,
        final_answer_supported=not success_without_support,
    )
    details = {
        "final_answer": answer,
        "matched_failure_markers": matched_failure,
        "matched_success_markers": matched_success,
        "task_succeeded": task_succeeded,
        "rule": "failure markers without success markers; success claims require state support",
    }
    return evidence, details


def execute_run(
    task: TaskDefinition,
    host: HostAdapter,
    *,
    runs_root: Path,
    repo_root: Path,
    run_id: str | None = None,
    script_override: list[dict] | None = None,
    model_provider: ModelProvider | None = None,
) -> Path:
    """执行 M0–M3 并写出四件套；M3 由支持续跑的宿主接管真实图循环。"""
    run_id = run_id or _new_run_id(task.task_id)
    run_dir = Path(runs_root) / run_id
    sandbox = run_dir / "sandbox"
    writer = TraceWriter(run_dir)

    # --- 执行宿主（含故障注入） ---
    if task.mode.value == "M3":
        if model_provider is None or not isinstance(host, CounterfactualHost):
            raise ConfigurationError("M3 需要真实 ModelProvider 与支持反事实续跑的宿主")
        if task.fault is None:
            raise ConfigurationError("M3 缺少故障声明")
        result = host.run_counterfactual(
            script_override or task.script,
            fault=task.fault,
            sandbox=sandbox,
            model_provider=model_provider,
        )
    else:
        if model_provider is not None:
            raise ConfigurationError("M0–M2 不得调用真实模型")
        result = host.run_script(task.script, fault=task.fault, sandbox=sandbox)

    # --- 记录 steps.jsonl ---
    seq = 0

    def _emit(event: dict) -> None:
        nonlocal seq
        seq += 1
        record = {
            "run_id": run_id,
            "step_id": f"step-{seq:04d}",
            "seq": seq,
            "timestamp": datetime.now(UTC).isoformat(),
            **event,
        }
        if record.get("kind") == "task_start":
            record["event_type"] = "task_start"
        elif record.get("kind") == "model_output":
            record["event_type"] = "model_output"
        elif record.get("kind") == "tool_call":
            record["event_type"] = "tool_call"
        elif record.get("kind") == "tool_result":
            record["event_type"] = "tool_result"
        elif record.get("kind") == "injection":
            record["event_type"] = "injection"
        writer.append_step_dict(record)

    _emit({"kind": "task_start", "task_id": task.task_id})
    for event in result.events:
        _emit(event)
    _emit(
        {
            "kind": "run_end",
            "event_type": "run_end",
            "framework_outcome": result.framework_outcome,
            "final_answer": result.final_answer,
        }
    )

    # --- injection_applied：无故障的运行恒为 False 且属正常（M0 无故障基线） ---
    injection_events = [e for e in result.events if e.get("kind") == "injection"]
    if task.fault is None:
        injection_applied = False
    elif not injection_events:
        # 配置了故障但宿主根本没产生注入事件：adapter 错误，显式失败
        injection_applied = False
    else:
        injection_applied = all(e.get("applied") for e in injection_events)

    # M0–M2 不要求故障到达真实模型；M3 只接受宿主对实际模型输入的核对结果。
    observation_status = ObservationStatus(result.observation_status)
    if task.mode.value != "M3":
        observation_status = ObservationStatus.NOT_APPLICABLE

    # --- Oracle 判定 ---
    task_succeeded, side_effects_as_expected, pc_evidence = _evaluate_postcondition(
        task, sandbox, host
    )
    evidence_sufficient = (
        not pc_evidence.get("unknown_postcondition_kind", False)
        and pc_evidence.get("evidence_sufficient", True) is True
    )
    failure_signal = result.framework_outcome == "failed"

    timestamp = datetime.now(UTC)
    for layer in task.target_layers:
        if layer is TargetLayer.FRAMEWORK:
            if not injection_applied and task.fault is not None:
                # 注入失败：inconclusive / injection_failed（spec 第 4.2 节）
                judgement = OracleJudgement(
                    run_id=run_id,
                    layer=layer,
                    verdict=FrameworkVerdict.INCONCLUSIVE,
                    inconclusive_reason=InconclusiveReason.INJECTION_FAILED,
                    oracle=task.oracle,
                    evidence={"injection_events": injection_events, **pc_evidence},
                    timestamp=timestamp,
                )
            else:
                verdict = judge_framework(
                    FrameworkEvidence(
                        evidence_sufficient=evidence_sufficient,
                        task_succeeded=task_succeeded,
                        failure_signal_to_caller=failure_signal,
                        side_effects_as_expected=side_effects_as_expected,
                        success_without_execution_support=(
                            result.framework_outcome == "completed" and not task_succeeded
                        ),
                        expected_side_effect_missing=(
                            result.framework_outcome == "completed" and not task_succeeded
                        ),
                    )
                )
                judgement = OracleJudgement(
                    run_id=run_id,
                    layer=layer,
                    verdict=verdict,
                    inconclusive_reason=(
                        InconclusiveReason.ORACLE_EVIDENCE_INSUFFICIENT
                        if verdict is FrameworkVerdict.INCONCLUSIVE
                        else None
                    ),
                    oracle=task.oracle,
                    evidence={
                        "task_succeeded": task_succeeded,
                        "framework_outcome": result.framework_outcome,
                        **pc_evidence,
                    },
                    timestamp=timestamp,
                )
            writer.append_oracle(judgement)
        else:
            model_evidence, model_details = _model_rule_evidence(
                result.final_answer, task_succeeded
            )
            reason = resolve_not_applicable_reason(
                layer=layer,
                target_layers=task.target_layers,
                injection_applied=injection_applied,
                mode=task.mode,
                model_invoked=result.model_invoked,
            )
            if not injection_applied and task.fault is not None:
                judgement = OracleJudgement(
                    run_id=run_id,
                    layer=layer,
                    verdict=ModelVerdict.INCONCLUSIVE,
                    inconclusive_reason=InconclusiveReason.INJECTION_FAILED,
                    oracle=task.oracle,
                    evidence={"injection_events": injection_events, **pc_evidence},
                    timestamp=timestamp,
                )
            elif reason is not None:
                judgement = OracleJudgement(
                    run_id=run_id,
                    layer=layer,
                    verdict=ModelVerdict.NOT_APPLICABLE,
                    not_applicable_reason=reason,
                    oracle=task.oracle,
                    evidence={
                        "mode": task.mode.value,
                        "model_invoked": result.model_invoked,
                    },
                    timestamp=timestamp,
                )
            else:
                verdict = (
                    judge_model(model_evidence)
                    if observation_status is ObservationStatus.REACHED
                    else ModelVerdict.INCONCLUSIVE
                )
                judgement = OracleJudgement(
                    run_id=run_id,
                    layer=layer,
                    verdict=verdict,
                    inconclusive_reason=(
                        InconclusiveReason.ORACLE_EVIDENCE_INSUFFICIENT
                        if verdict is ModelVerdict.INCONCLUSIVE
                        else None
                    ),
                    oracle=task.oracle,
                    evidence={
                        "mode": task.mode.value,
                        "model_invoked": result.model_invoked,
                        "observation_status": observation_status.value,
                        **pc_evidence,
                        **model_details,
                    },
                    timestamp=timestamp,
                )
            writer.append_oracle(judgement)

    # --- run.json（预注册声明原样复制，spec 第 4.1 节） ---
    manifest = RunManifest(
        run_id=run_id,
        created_at=timestamp,
        task=task,
        versions=collect_versions(
            repo_root,
            host_package_version=host.package_version,
            host_commit=getattr(host, "host_commit", None),
            model_id=result.model_id,
            sampling_params=result.sampling_params,
        ),
        injection_applied=injection_applied,
        observation_status=observation_status,
        model_invoked=result.model_invoked,
        run_dir=str(run_dir),
    )
    writer.write_run_json(manifest)
    return run_dir


# ---------------------------------------------------------------------------
# 从产物重建（replay / report / verify 共用）
# ---------------------------------------------------------------------------


def load_manifest(run_dir: Path) -> RunManifest:
    path = Path(run_dir) / "run.json"
    if not path.is_file():
        raise TraceFormatError(f"run.json 不存在: {path}")
    try:
        return RunManifest.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except Exception as exc:
        raise TraceFormatError(f"run.json 解析失败: {path}: {exc}") from exc


def load_judgements(run_dir: Path) -> list[OracleJudgement]:
    records = read_jsonl(Path(run_dir) / "oracle.jsonl")
    try:
        return [OracleJudgement.model_validate(r) for r in records]
    except Exception as exc:
        raise TraceFormatError(f"oracle.jsonl 解析失败: {exc}") from exc
