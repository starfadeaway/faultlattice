"""跨运行批次聚合、A/B 硬校验与批次报告复算（spec 第 6 节）。

批次报告只读取 run.json / oracle.jsonl；报告内嵌 canonical JSON 指标块，
batch-verify 从原始产物独立重算并逐字节比较。不同预注册声明、宿主版本或
故障条件不会被合并。沉默失败率受到 min_evaluable 与 inconclusive 阈值门禁，
不满足条件时保持为 None（报告中显示 N/A）。
"""

from __future__ import annotations

# 内嵌 Markdown 表格必须保持单行，避免把表格行拆成普通段落。
# ruff: noqa: E501
import re
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jinja2 import Template

from faultlattice.canonical import atomic_write, canonical_dumps, canonical_hash
from faultlattice.errors import ConfigurationError, TraceFormatError
from faultlattice.runner import load_judgements, load_manifest
from faultlattice.schemas import (
    ExecutionMode,
    FrameworkVerdict,
    InconclusiveReason,
    ModelVerdict,
    NotApplicableReason,
    ObservationStatus,
    OracleJudgement,
    RunManifest,
    SurfaceAs,
    TargetLayer,
    TaskDefinition,
)

BATCH_REPORT_MD = "batch-report.md"
_BATCH_METRICS_BLOCK_RE = re.compile(
    r"```json faultlattice-batch-metrics\n(?P<json>.*?)\n```", re.DOTALL
)


@dataclass(frozen=True)
class _RunRecord:
    manifest: RunManifest
    judgements: list[OracleJudgement]


def _tasks_by_pair(tasks: Sequence[TaskDefinition]) -> dict[str, list[TaskDefinition]]:
    pairs: dict[str, list[TaskDefinition]] = defaultdict(list)
    for task in tasks:
        if task.pair_id is not None:
            pairs[task.pair_id].append(task)
    return pairs


def _task_without_surface(task: TaskDefinition) -> dict[str, Any]:
    data = task.model_dump(mode="json")
    if data["fault"] is not None:
        data["fault"]["surface_as"] = None
    return data


def validate_ab_tasks(tasks: Sequence[TaskDefinition]) -> None:
    """在执行任何任务前校验 A/B 配对；差异按配置错误拒绝整个批次。"""
    for pair_id, pair_tasks in _tasks_by_pair(tasks).items():
        if any(task.fault is None for task in pair_tasks):
            raise ConfigurationError(f"A/B 配对 {pair_id}: 每个任务都必须声明故障")
        surfaces = {task.fault.surface_as for task in pair_tasks if task.fault is not None}
        if surfaces != {SurfaceAs.RETURN_VALUE, SurfaceAs.RAISE_EXCEPTION}:
            raise ConfigurationError(
                f"A/B 配对 {pair_id}: 必须同时包含 return_value（A）与 "
                "raise_exception（B），且不得使用其他 surface_as"
            )
        baselines = {canonical_dumps(_task_without_surface(task)) for task in pair_tasks}
        if len(baselines) != 1:
            raise ConfigurationError(
                f"A/B 配对 {pair_id}: 除 surface_as 外的预注册条件存在差异，拒绝执行"
            )


def _validate_ab_versions(records: Sequence[_RunRecord]) -> None:
    records_by_pair: dict[str, list[_RunRecord]] = defaultdict(list)
    for record in records:
        if record.manifest.task.pair_id is not None:
            records_by_pair[record.manifest.task.pair_id].append(record)
    for pair_id, pair_records in records_by_pair.items():
        pair_manifests = [record.manifest for record in pair_records]
        fields = (
            "host_package_version",
            "host_commit",
            "faultlattice_commit",
            "dependency_lock_hash",
        )
        for field in fields:
            values = {getattr(manifest.versions, field) for manifest in pair_manifests}
            if len(values) != 1:
                raise ConfigurationError(
                    f"A/B 配对 {pair_id}: 版本字段 {field} 不一致，拒绝聚合"
                )
        m3 = [manifest for manifest in pair_manifests if manifest.task.mode is ExecutionMode.M3]
        for field in ("model_id", "sampling_params"):
            values = {
                canonical_dumps(getattr(manifest.versions, field))
                for manifest in m3
            }
            if len(values) > 1:
                raise ConfigurationError(
                    f"A/B 配对 {pair_id}: M3 字段 {field} 不一致，拒绝聚合"
                )


def _load_records(run_dirs: Sequence[Path]) -> list[_RunRecord]:
    if not run_dirs:
        raise ConfigurationError("批次至少需要一个 run 目录")
    records = [
        _RunRecord(manifest=load_manifest(run_dir), judgements=load_judgements(run_dir))
        for run_dir in run_dirs
    ]
    run_ids = [record.manifest.run_id for record in records]
    if len(run_ids) != len(set(run_ids)):
        raise ConfigurationError("批次包含重复 run_id；同一运行不得重复计数")
    validate_ab_tasks([record.manifest.task for record in records])
    _validate_ab_versions(records)
    return records


def _conditions(record: _RunRecord) -> dict[str, Any]:
    manifest = record.manifest
    task = manifest.task
    fault = task.fault
    return {
        "task_id": task.task_id,
        "task_fingerprint": canonical_hash(task.model_dump(mode="json")),
        "host": task.host,
        "host_package_version": manifest.versions.host_package_version,
        "host_commit": manifest.versions.host_commit,
        "faultlattice_commit": manifest.versions.faultlattice_commit,
        "dependency_lock_hash": manifest.versions.dependency_lock_hash,
        "mode": task.mode.value,
        "experiment_family": fault.experiment_family.value if fault else None,
        "injection_point": fault.injection_point.value if fault else None,
        "fault_type": fault.fault_type.value if fault else None,
        "surface_as": fault.surface_as.value if fault else None,
        "target_layers": [layer.value for layer in task.target_layers],
        "min_evaluable": task.min_evaluable,
        "inconclusive_threshold": task.inconclusive_threshold,
    }


def _layer_metrics(records: Sequence[_RunRecord], layer: TargetLayer) -> dict[str, Any]:
    task = records[0].manifest.task
    total_runs = len(records)
    injection_failed = sum(
        not record.manifest.injection_applied and record.manifest.task.fault is not None
        for record in records
    )
    targeted_records = [record for record in records if layer in record.manifest.task.target_layers]
    applicable = len(targeted_records)

    evaluable = 0
    silent = 0
    oracle_insufficient = 0
    not_applicable = {reason.value: 0 for reason in NotApplicableReason}

    for record in targeted_records:
        matches = [judgement for judgement in record.judgements if judgement.layer is layer]
        if len(matches) != 1:
            raise TraceFormatError(
                f"run {record.manifest.run_id}: {layer.value} 层应有且仅有一条 Oracle 判定，"
                f"实际为 {len(matches)} 条"
            )
        judgement = matches[0]
        manifest = record.manifest
        if judgement.inconclusive_reason is InconclusiveReason.ORACLE_EVIDENCE_INSUFFICIENT:
            oracle_insufficient += 1
        if judgement.not_applicable_reason is not None:
            not_applicable[judgement.not_applicable_reason.value] += 1

        if layer is TargetLayer.FRAMEWORK:
            is_evaluable = (
                manifest.injection_applied
                and judgement.verdict != FrameworkVerdict.INCONCLUSIVE
            )
            is_silent = judgement.verdict == FrameworkVerdict.SILENT_FAILURE
        else:
            is_evaluable = (
                manifest.injection_applied
                and manifest.observation_status is ObservationStatus.REACHED
                and judgement.verdict
                not in (ModelVerdict.INCONCLUSIVE, ModelVerdict.NOT_APPLICABLE)
            )
            is_silent = judgement.verdict == ModelVerdict.SILENT_FAILURE
        evaluable += int(is_evaluable)
        silent += int(is_evaluable and is_silent)

    suppressed_reason: str | None = None
    if evaluable == 0:
        suppressed_reason = "no_evaluable_runs"
    elif evaluable < max(3, task.min_evaluable):
        # 统一最低描述样本数与任务阈值同时生效，n=1/2 只列原始计数。
        suppressed_reason = "below_min_evaluable"
    elif applicable and oracle_insufficient / applicable > task.inconclusive_threshold:
        suppressed_reason = "inconclusive_threshold_exceeded"

    rate = None if suppressed_reason is not None else silent / evaluable
    coverage = evaluable / applicable if applicable else None
    return {
        "total_runs": total_runs,
        "injection_failed": injection_failed,
        "applicable": applicable,
        "applicable_ratio": applicable / total_runs,
        "evaluable": evaluable,
        "silent_failures": silent,
        "silent_failure_rate": rate,
        "rate_suppressed_reason": suppressed_reason,
        "oracle_coverage": coverage,
        "oracle_insufficient": oracle_insufficient,
        "oracle_insufficient_ratio": (
            oracle_insufficient / applicable if applicable else None
        ),
        "not_applicable": not_applicable,
    }


def _summarize_records(records: Sequence[_RunRecord]) -> dict[str, Any]:
    task = records[0].manifest.task
    return {
        "conditions": _conditions(records[0]),
        "run_ids": sorted(record.manifest.run_id for record in records),
        "framework": _layer_metrics(records, TargetLayer.FRAMEWORK),
        "model": (
            _layer_metrics(records, TargetLayer.MODEL)
            if TargetLayer.MODEL in task.target_layers
            else None
        ),
    }


def _difference(b: dict[str, Any] | None, a: dict[str, Any] | None) -> float | None:
    if a is None or b is None:
        return None
    a_rate = a["silent_failure_rate"]
    b_rate = b["silent_failure_rate"]
    if a_rate is None or b_rate is None:
        return None
    return b_rate - a_rate


def compute_batch_metrics(run_dirs: Sequence[Path]) -> dict[str, Any]:
    """从原始产物独立计算完整批次指标。"""
    records = _load_records(run_dirs)

    grouped: dict[str, list[_RunRecord]] = defaultdict(list)
    for record in records:
        grouped[canonical_dumps(_conditions(record))].append(record)
    groups = [_summarize_records(group) for _, group in sorted(grouped.items())]

    records_by_pair: dict[str, list[_RunRecord]] = defaultdict(list)
    for record in records:
        if record.manifest.task.pair_id is not None:
            records_by_pair[record.manifest.task.pair_id].append(record)
    pairs = []
    for pair_id, pair_records in sorted(records_by_pair.items()):
        a_records = [
            record
            for record in pair_records
            if record.manifest.task.fault is not None
            and record.manifest.task.fault.surface_as is SurfaceAs.RETURN_VALUE
        ]
        b_records = [
            record
            for record in pair_records
            if record.manifest.task.fault is not None
            and record.manifest.task.fault.surface_as is SurfaceAs.RAISE_EXCEPTION
        ]
        a = _summarize_records(a_records)
        b = _summarize_records(b_records)
        pairs.append(
            {
                "pair_id": pair_id,
                "a": a,
                "b": b,
                "framework_rate_difference": _difference(b["framework"], a["framework"]),
                "model_rate_difference": _difference(b["model"], a["model"]),
            }
        )

    runs = [
        {
            **_conditions(record),
            "run_id": record.manifest.run_id,
            "run_dir": record.manifest.run_dir,
            "injection_applied": record.manifest.injection_applied,
            "observation_status": record.manifest.observation_status.value,
        }
        for record in records
    ]
    runs.sort(key=lambda run: run["run_id"])
    return {
        "schema_version": 1,
        "total_runs": len(records),
        "run_ids": sorted(record.manifest.run_id for record in records),
        "groups": groups,
        "pairs": pairs,
        "runs": runs,
    }


def _pct(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.2%}"


def _delta(value: float | None) -> str:
    return "N/A" if value is None else f"{value:+.2%}"


def _na_counts(counts: dict[str, int]) -> str:
    present = [f"{key}={value}" for key, value in counts.items() if value]
    return "；".join(present) if present else "—"


def _layer_label(name: str) -> str:
    return {"framework": "框架层", "model": "模型层"}.get(name, name)


def _gate_label(reason: str | None) -> str:
    return {
        None: "允许展示",
        "no_evaluable_runs": "没有可判定运行",
        "below_min_evaluable": "低于预注册最低样本数",
        "inconclusive_threshold_exceeded": "证据不足超过预注册阈值",
    }.get(reason, reason or "允许展示")


BATCH_REPORT_TEMPLATE = Template(
    """\
# FaultLattice 批次报告

## 阅读摘要

- 本批次包含 **{{ total_runs }} 次真实运行**、**{{ groups|length }} 个分层实验条件**、**{{ pairs|length }} 个 A/B 配对**。
- “总运行数”是 Harness 执行并落盘的数量，不是 Agent 通过数；“可判定”是 Oracle 证据足够的数量，也不等于行为正确。
- 每个坐标的沉默失败率只有在可判定数达到预注册 `min_evaluable`，且证据不足未超过阈值时才展示；否则为 **N/A**。A/B 不合并平均。
- 具体行为结论应回到对应 run 的人读报告；本页负责同坐标聚合和复算，不用一个百分比替代原始轨迹。

## 分层指标主表

`framework` 为框架层，`model` 为模型层；故障条件依次是“注入点 / 故障类型 / 呈现方式”。“门禁”说明比例被隐藏的原因，不是 Harness 错误。

| 实验单元 | 宿主 × 模式 | 故障条件 | 评价层 | 总运行数 | 注入失败 | 适用集 | 可判定 | 沉默失败次数 | 沉默失败率 | Oracle 覆盖率 | 证据不足 | 不适用原因计数 | 比例门禁 |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
{% for group in groups -%}
{% for layer_name in ["framework", "model"] -%}
{% set layer = group[layer_name] -%}
{% if layer is not none -%}
| {{ group.conditions.task_id }} | {{ group.conditions.host }} × {{ group.conditions.mode }} | {{ group.conditions.injection_point }} / {{ group.conditions.fault_type }} / {{ group.conditions.surface_as }} | {{ layer_label(layer_name) }} | {{ layer.total_runs }} | {{ layer.injection_failed }} | {{ layer.applicable }}/{{ layer.total_runs }}（{{ pct(layer.applicable_ratio) }}） | {{ layer.evaluable }} | {{ layer.silent_failures }} | {{ pct(layer.silent_failure_rate) }} | {{ pct(layer.oracle_coverage) }} | {{ layer.oracle_insufficient }}（{{ pct(layer.oracle_insufficient_ratio) }}） | {{ na_counts(layer.not_applicable) }} | {{ gate_label(layer.rate_suppressed_reason) }} |
{% endif -%}
{% endfor -%}
{% endfor %}

## A/B 对照

{% if not pairs -%}
本批次没有预注册 A/B 配对，因此不计算组间差值，也不把不同模型或任务拼成 A/B。
{% endif -%}
{% for pair in pairs %}
### {{ pair.pair_id }}

| 层 | 组别 | surface_as | 样本数 | 可判定数 | 沉默失败次数 | 沉默失败率 |
|---|---|---|---:|---:|---:|---:|
{% for layer_name in ["framework", "model"] -%}
{% if pair.a[layer_name] is not none -%}
{% for arm_name, arm_label in [["a", "A"], ["b", "B"]] -%}
{% set arm = pair[arm_name] -%}
| {{ layer_name }} | {{ arm_label }} | {{ arm.conditions.surface_as }} | {{ arm[layer_name].total_runs }} | {{ arm[layer_name].evaluable }} | {{ arm[layer_name].silent_failures }} | {{ pct(arm[layer_name].silent_failure_rate) }} |
{% endfor -%}
{% endif -%}
{% endfor %}

- 框架层沉默失败率差值（B − A）：{{ delta(pair.framework_rate_difference) }}。
- 模型层沉默失败率差值（B − A）：{{ delta(pair.model_rate_difference) }}。
{% endfor %}

## 完整分层明细

下表用于定位原始四件套。`injection_applied=True` 只表示故障确实生效；`observation_status` 只表示故障是否进入模型观察，两者都不是“测试通过”。

| run_id | 任务 | 宿主 × 模式 | 族 | 注入点 | 故障类型 | surface_as | 注入生效 | observation_status |
|---|---|---|---|---|---|---|---|---|
{% for run in runs -%}
| {{ run.run_id }} | {{ run.task_id }} | {{ run.host }} × {{ run.mode }} | {{ run.experiment_family }} | {{ run.injection_point }} | {{ run.fault_type }} | {{ run.surface_as }} | {{ run.injection_applied }} | {{ run.observation_status }} |
{% endfor %}

<details>
<summary>查看机器复算锚点（供 batch-verify 逐字核对）</summary>

以下 JSON 是完整机器指标，不是另一套实验结论。`faultlattice batch-verify` 会从上述原始运行独立重算并逐字比较。

```json faultlattice-batch-metrics
{{ metrics_json }}
```

</details>
"""
)


def render_batch_report(run_dirs: Sequence[Path]) -> str:
    """只读原始 run 产物，渲染批次报告文本（不写盘）。"""
    metrics = compute_batch_metrics(run_dirs)
    return BATCH_REPORT_TEMPLATE.render(
        **metrics,
        metrics_json=canonical_dumps(metrics),
        pct=_pct,
        delta=_delta,
        na_counts=_na_counts,
        layer_label=_layer_label,
        gate_label=_gate_label,
    )


def generate_batch_report(run_dirs: Sequence[Path], output_path: Path) -> Path:
    """生成 batch-report.md；输出路径可以是任意批次报告文件。"""
    output_path = Path(output_path)
    markdown = render_batch_report(run_dirs)
    if not markdown.endswith("\n"):
        markdown += "\n"
    atomic_write(output_path, markdown.encode("utf-8"))
    return output_path


def verify_batch_report(report_path: Path, run_dirs: Sequence[Path]) -> list[str]:
    """独立重算批次指标并与报告内嵌 metrics 块比较。"""
    report_path = Path(report_path)
    if not report_path.is_file():
        return [f"批次报告不存在: {report_path}"]
    match = _BATCH_METRICS_BLOCK_RE.search(report_path.read_text(encoding="utf-8"))
    if match is None:
        return ["批次报告中找不到 ```json faultlattice-batch-metrics 指标块"]
    expected = canonical_dumps(compute_batch_metrics(run_dirs))
    actual = match.group("json")
    problems = []
    if actual != expected:
        problems.append("批次报告指标与原始产物独立重算结果不一致")
    expected_text = render_batch_report(run_dirs)
    if not expected_text.endswith("\n"):
        expected_text += "\n"
    if report_path.read_text(encoding="utf-8") != expected_text:
        problems.append("批次报告正文与原始产物重渲染结果不一致")
    return problems
