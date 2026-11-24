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
from faultlattice.host import HostAdapter
from faultlattice.oracle.judge import (
    FrameworkEvidence,
    judge_framework,
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


def _evaluate_postcondition(task: TaskDefinition, sandbox: Path) -> tuple[bool, dict]:
    """检查预期后置条件是否成立（state 类 Oracle 的事实来源）。"""
    pc = task.expected_postcondition
    if pc.kind == "file_written":
        rel = pc.params.get("path", "")
        target = sandbox / rel
        exists = target.is_file()
        contains_ok = True
        if exists and "content_contains" in pc.params:
            contains_ok = pc.params["content_contains"] in target.read_text(encoding="utf-8")
        ok = exists and contains_ok
        return ok, {
            "kind": pc.kind,
            "path": rel,
            "exists": exists,
            "content_contains_ok": contains_ok,
        }
    # 未知的 postcondition 类型：证据不足，由 Oracle 判 inconclusive
    return False, {"kind": pc.kind, "unknown_postcondition_kind": True}


def execute_run(
    task: TaskDefinition,
    host: HostAdapter,
    *,
    runs_root: Path,
    repo_root: Path,
    run_id: str | None = None,
) -> Path:
    """执行一次 M0 运行并写出四件套，返回 run 目录。

    预期注入故障是实验数据：宿主因注入故障而失败时本函数正常返回，
    只有 Harness 自身错误才抛异常（对应 CLI 非零退出码）。
    """
    run_id = run_id or _new_run_id(task.task_id)
    run_dir = Path(runs_root) / run_id
    sandbox = run_dir / "sandbox"
    writer = TraceWriter(run_dir)

    # --- 执行宿主（含故障注入） ---
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

    # M0–M2 不要求故障到达真实模型（spec 第 4.3 节）
    observation_status = ObservationStatus.NOT_APPLICABLE

    # --- Oracle 判定 ---
    task_succeeded, pc_evidence = _evaluate_postcondition(task, sandbox)
    evidence_sufficient = not pc_evidence.get("unknown_postcondition_kind", False)
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
                        side_effects_as_expected=task_succeeded,
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
            # 模型层：M0–M2 恒为 not_applicable，原因按固定顺序取第一个匹配
            reason = resolve_not_applicable_reason(
                layer=layer,
                target_layers=task.target_layers,
                injection_applied=injection_applied,
                mode=task.mode,
                model_invoked=False,
            )
            judgement = OracleJudgement(
                run_id=run_id,
                layer=layer,
                verdict=ModelVerdict.NOT_APPLICABLE,
                not_applicable_reason=reason,
                oracle=task.oracle,
                evidence={"mode": task.mode.value},
                timestamp=timestamp,
            )
            writer.append_oracle(judgement)

    # --- run.json（预注册声明原样复制，spec 第 4.1 节） ---
    manifest = RunManifest(
        run_id=run_id,
        created_at=timestamp,
        task=task,
        versions=collect_versions(repo_root, host_package_version=host.package_version),
        injection_applied=injection_applied,
        observation_status=observation_status,
        model_invoked=False,
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
