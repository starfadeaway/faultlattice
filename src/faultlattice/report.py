"""报告生成与指标复算（spec 第 6、7 节）。

- report 只读取原始产物（run.json / oracle.jsonl）生成报告；
- verify 独立重算指标，与 report.md 内嵌的 metrics 块逐字节比较，
  不读取生成报告时的内存中间态；
- 报告正文用 Jinja2 渲染，数字全部来自 compute_metrics 的真实计算；
- 可判定运行数为 0 或低于 min_evaluable 时，沉默失败率为 None，
  渲染为 "N/A"，绝不写成 0%。

metrics 块格式：report.md 中一个 ```json faultlattice-metrics 围栏块，
内容是 canonical JSON。verify 提取该块并与独立重算结果比较。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from jinja2 import Template

from faultlattice.canonical import canonical_dumps
from faultlattice.runner import load_judgements, load_manifest
from faultlattice.schemas import (
    FrameworkVerdict,
    InconclusiveReason,
    ModelVerdict,
    ObservationStatus,
    OracleJudgement,
    RunManifest,
    TargetLayer,
)
from faultlattice.trace import REPORT_MD, TraceWriter

_METRICS_BLOCK_RE = re.compile(
    r"```json faultlattice-metrics\n(?P<json>.*?)\n```", re.DOTALL
)

REPORT_TEMPLATE = Template(
    """\
# FaultLattice 运行报告 {{ run_id }}

- 任务：{{ task_id }}（宿主 {{ host }}，模式 {{ mode }}）
- 故障：{{ injection_point }} / {{ fault_type }} / {{ surface_as }}（{{ experiment_family }}）
- injection_applied：{{ injection_applied }}；observation_status：{{ observation_status }}
- 预注册 target_layers：{{ target_layers }}

## 框架层指标

| 指标 | 值 |
|---|---|
| 总运行数 | {{ framework.total_runs }} |
| 注入失败数 | {{ framework.injection_failed }} |
| 适用集大小（/ 总运行数） | {{ framework.applicable }}（{{ framework.applicable_ratio }}） |
| 可判定运行数 | {{ framework.evaluable }} |
| 沉默失败次数 | {{ framework.silent_failures }} |
| 沉默失败率 | {{ framework.silent_failure_rate_display }} |
| Oracle 覆盖率 | {{ framework.oracle_coverage_display }} |
| oracle_evidence_insufficient | {{ framework.oi }}（占适用集 {{ framework.oi_ratio }}） |
| 框架层 verdict | {{ framework.verdict }} |

## 模型层指标

{% if model is none -%}
本次运行未评价模型层（{{ model_na_reason }}）。
{%- else %}
| 指标 | 值 |
|---|---|
| 总运行数 | {{ model.total_runs }} |
| 注入失败数 | {{ model.injection_failed }} |
| 适用集大小（/ 总运行数） | {{ model.applicable }}（{{ model.applicable_ratio }}） |
| 可判定运行数 | {{ model.evaluable }} |
| 沉默失败次数 | {{ model.silent_failures }} |
| 沉默失败率 | {{ model.silent_failure_rate_display }} |
| Oracle 覆盖率 | {{ model.oracle_coverage_display }} |
| oracle_evidence_insufficient | {{ model.oi }}（占适用集 {{ model.oi_ratio }}） |
| not_applicable 原因 | {{ model.not_applicable_reason }} |
{%- endif %}

## 分层明细

本切片每次报告对应单个运行；分层坐标（宿主 × 模式 × 族 × 注入点 × 故障类型 × surface_as）：
`{{ host }} × {{ mode }} × {{ experiment_family }}`
`{{ injection_point }} × {{ fault_type }} × {{ surface_as }}`。

```json faultlattice-metrics
{{ metrics_json }}
```
"""
)


def _layer_metrics(
    manifest: RunManifest,
    judgements: list[OracleJudgement],
    layer: TargetLayer,
) -> dict[str, Any]:
    """按 spec 第 6 节口径计算单层指标（单运行实验：总运行数 = 1）。"""
    task = manifest.task
    total_runs = 1
    injection_failed = 0 if manifest.injection_applied else (1 if task.fault is not None else 0)

    targeted = layer in task.target_layers
    applicable = 1 if targeted else 0

    judgement = next((j for j in judgements if j.layer is layer), None)

    oracle_insufficient = 0
    evaluable = 0
    silent = 0
    verdict_display = "N/A"
    na_reason: str | None = None

    if judgement is not None:
        verdict_display = str(judgement.verdict.value)
        na_reason = (
            judgement.not_applicable_reason.value if judgement.not_applicable_reason else None
        )
        if judgement.inconclusive_reason is InconclusiveReason.ORACLE_EVIDENCE_INSUFFICIENT:
            oracle_insufficient = 1
        if layer is TargetLayer.FRAMEWORK:
            evaluable = int(
                targeted
                and manifest.injection_applied
                and judgement.verdict != FrameworkVerdict.INCONCLUSIVE
            )
        else:
            evaluable = int(
                targeted
                and manifest.injection_applied
                and manifest.observation_status is ObservationStatus.REACHED
                and judgement.verdict
                not in (ModelVerdict.INCONCLUSIVE, ModelVerdict.NOT_APPLICABLE)
            )
        silent = int(judgement.verdict in (FrameworkVerdict.SILENT_FAILURE, ModelVerdict.SILENT_FAILURE))

    # 可判定数为 0 或低于预注册 min_evaluable：沉默失败率为 None → "N/A"
    if evaluable == 0 or evaluable < task.min_evaluable:
        rate: float | None = None
    else:
        rate = silent / evaluable

    coverage: float | None = (evaluable / applicable) if applicable else None

    return {
        "total_runs": total_runs,
        "injection_failed": injection_failed,
        "applicable": applicable,
        "applicable_ratio": f"{applicable}/{total_runs}",
        "evaluable": evaluable,
        "silent_failures": silent,
        # None 表示 N/A；渲染层与 verify 都以这个 None 为准，不落地成 0
        "silent_failure_rate": rate,
        "silent_failure_rate_display": ("N/A" if rate is None else f"{rate:.2%}"),
        "oracle_coverage": coverage,
        "oracle_coverage_display": ("N/A" if coverage is None else f"{coverage:.2%}"),
        "oracle_insufficient": oracle_insufficient,
        "oracle_insufficient_ratio": (
            f"{oracle_insufficient}/{applicable}" if applicable else "N/A"
        ),
        "verdict": verdict_display,
        "not_applicable_reason": na_reason,
    }


def compute_metrics(run_dir: Path) -> dict[str, Any]:
    """从原始产物独立计算指标。report 与 verify 共用此函数。"""
    run_dir = Path(run_dir)
    manifest = load_manifest(run_dir)
    judgements = load_judgements(run_dir)
    return {
        "run_id": manifest.run_id,
        "task_id": manifest.task.task_id,
        "framework": _layer_metrics(manifest, judgements, TargetLayer.FRAMEWORK),
        "model": (
            _layer_metrics(manifest, judgements, TargetLayer.MODEL)
            if TargetLayer.MODEL in manifest.task.target_layers
            else None
        ),
    }


def render_report(run_dir: Path) -> str:
    """读取原始产物，渲染 report.md 文本（不写盘）。"""
    run_dir = Path(run_dir)
    manifest = load_manifest(run_dir)
    metrics = compute_metrics(run_dir)
    task = manifest.task
    fault = task.fault

    model_metrics = metrics["model"]
    model_na_reason = "target_layers 未包含 model"

    def _view(layer_metrics: dict[str, Any]) -> dict[str, Any]:
        # 模板用短别名避免超长行；canonical metrics 块仍使用完整键名
        return {
            **layer_metrics,
            "oi": layer_metrics["oracle_insufficient"],
            "oi_ratio": layer_metrics["oracle_insufficient_ratio"],
        }

    return REPORT_TEMPLATE.render(
        run_id=manifest.run_id,
        task_id=task.task_id,
        host=task.host,
        mode=task.mode.value,
        injection_point=fault.injection_point.value if fault else "none",
        fault_type=fault.fault_type.value if fault else "none",
        surface_as=fault.surface_as.value if fault else "none",
        experiment_family=fault.experiment_family.value if fault else "none",
        injection_applied=manifest.injection_applied,
        observation_status=manifest.observation_status.value,
        target_layers=[layer.value for layer in task.target_layers],
        framework=_view(metrics["framework"]),
        model=_view(model_metrics) if model_metrics else None,
        model_na_reason=model_na_reason,
        metrics_json=canonical_dumps(metrics),
    )


def generate_report(run_dir: Path) -> Path:
    """生成 report.md 并写盘（只读原始产物）。"""
    writer = TraceWriter(Path(run_dir))
    writer.write_report(render_report(run_dir))
    return Path(run_dir) / REPORT_MD


def verify_report(run_dir: Path) -> list[str]:
    """独立重算指标并与 report.md 内嵌 metrics 块比较。

    返回问题列表；空列表表示复算一致。调用方（CLI）据此决定退出码。
    """
    run_dir = Path(run_dir)
    problems: list[str] = []

    report_path = run_dir / REPORT_MD
    if not report_path.is_file():
        return [f"report.md 不存在: {report_path}"]

    text = report_path.read_text(encoding="utf-8")
    match = _METRICS_BLOCK_RE.search(text)
    if match is None:
        return ["report.md 中找不到 ```json faultlattice-metrics 指标块"]

    expected = canonical_dumps(compute_metrics(run_dir))
    actual = match.group("json")
    if actual != expected:
        problems.append(
            "report.md 指标与独立重算结果不一致：\n"
            f"  报告内嵌: {actual}\n  独立重算: {expected}"
        )
    return problems
