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
from datetime import UTC
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
from faultlattice.trace import REPORT_MD, TraceWriter, read_jsonl

_METRICS_BLOCK_RE = re.compile(
    r"```json faultlattice-metrics\n(?P<json>.*?)\n```", re.DOTALL
)

_HOST_LABELS = {
    "local_controlled": "本地受控宿主",
    "smolagents": "smolagents",
    "langgraph": "LangGraph",
    "anchorline": "Anchorline",
    "lorekeeper": "LoreKeeper",
}
_MODE_LABELS = {
    "M0": "M0 · 预设脚本执行",
    "M1": "M1 · 纯轨迹重放",
    "M2": "M2 · 故障注入重放",
    "M3": "M3 · 真实模型反事实续跑",
}
_INJECTION_LABELS = {
    "tool_args": "工具参数（工具执行前）",
    "tool_result": "工具原始返回（工具执行后）",
    "observation": "模型观察（进入下一轮模型上下文前）",
    "none": "未注入",
}
_FAULT_LABELS = {
    "timeout": "超时",
    "empty_response": "空响应",
    "truncated": "内容截断",
    "malformed_content": "内容格式损坏",
    "error_response": "错误响应",
    "invalid_args": "非法参数",
    "none": "无故障",
}
_SURFACE_LABELS = {
    "return_value": "作为普通返回值呈现",
    "raise_exception": "作为显式异常呈现",
    "not_applicable": "不适用返回／异常语义",
    "none": "不适用",
}
_OBSERVATION_LABELS = {
    "reached": "故障内容已进入模型观察",
    "not_reached": "故障内容未进入模型观察",
    "not_applicable": "本次运行没有真实模型观察环节",
    "unknown": "无法确认故障内容是否进入模型观察",
}
_VERDICT_LABELS = {
    "completed": "正常完成",
    "explicit_failure": "显式失败（框架或模型暴露了失败信号）",
    "silent_failure": "沉默失败（未满足契约，却表现为正常完成）",
    "contract_violation": "违反预注册契约",
    "inconclusive": "证据不足，无法判定",
    "not_applicable": "本层不适用",
    "N/A": "不适用",
}

# 模板保留适合 Markdown 阅读的完整中文句子，不按 Python 代码行宽拆分。
# ruff: noqa: E501
REPORT_TEMPLATE = Template(
    """\
# FaultLattice 运行报告：{{ host_label }} · {{ task_id }}

> 本报告先解释实际业务状态与框架信号，再列出过程、Oracle 和复算锚点。原始标识仅供定位，不代替中文结论。

## 结论速览

{{ headline }}

| 阅读项 | 本次实际结果 |
|---|---|
| 业务任务是否完成 | {{ outcome_summary.task_succeeded }} |
| 框架向调用方报告 | {{ outcome_summary.framework_signal }} |
| 故障是否实际注入 | {{ injection_applied_label }} |
| 框架层 Oracle | {{ framework.verdict_label }}（`{{ framework.verdict }}`） |
{% if model is not none -%}
| 模型层 Oracle | {{ model.verdict_label }}（`{{ model.verdict }}`） |
{%- endif %}

**不要把这些概念混为一谈：** 业务任务完成与否、框架返回成功还是失败、Harness 是否完成执行，是三件不同的事。本报告的 Oracle 判定不是“整个 Agent 测试通过”的徽章。

## 一、这次测试做了什么

| 项目 | 内容 |
|---|---|
| 任务名称 | `{{ task_id }}` |
| 任务说明 | {{ task_description }} |
| 执行宿主 | {{ host_label }}（`{{ host }}`） |
| 执行模式 | {{ mode_label }} |
| 运行时间 | {{ created_at_display }} |
| 运行标识 | `{{ run_id }}` |

### 任务目标与验收契约

{{ expected_behavior }}

**预期后置条件：** {{ postcondition_display }}

**允许的安全降级：** {{ allowed_degradation }}

任务说明描述测试场景，预期行为描述被测 Agent 应如何处理，后置条件则给出可检查的实际结果。三者均在运行前冻结；运行完成后不会因为结果而临时改口径。

## 二、注入了什么故障

| 项目 | 含义 |
|---|---|
| 注入位置 | {{ injection_label }}（`{{ injection_point }}`） |
| 故障类型 | {{ fault_label }}（`{{ fault_type }}`） |
| 呈现方式 | {{ surface_label }}（`{{ surface_as }}`） |
| 实验族 | `{{ experiment_family }}` |
| 具体故障参数 | `{{ fault_params_display }}` |
| 是否实际生效 | {{ injection_applied_label }} |
| 模型观察状态 | {{ observation_label }}（`{{ observation_status }}`） |

{{ fault_explanation }}

“呈现方式”说明宿主看到的是普通返回值还是显式异常；它与“故障类型”不是同一维度。例如，同一种错误响应可以分别包装为返回值或异常，用来比较宿主对两种信号的处理差异。

## 三、模型是否参与

- 模型标识：`{{ model_id }}`
- 是否真实调用模型：{{ model_invoked_label }}
- 思考模式：{{ reasoning_mode_label }}
- 本次预注册评价层：{{ target_layers_label }}
- 采样参数：`{{ sampling_params_display }}`
{% if mode == "M3" -%}
- 故障前前缀：由本次所选真实模型现场生成，并在工具执行前校验其名称和参数与预注册契约完全一致；M0 源轨迹只提供契约，不提供伪造的思考字段。
- 原始思考字段记录：{{ execution.reasoning_output_count }} 条；原文保存在 `steps.jsonl`，用于同一提供方的后续工具请求，不作为 Oracle 的行为判定依据。
{%- endif %}

{% if not model_invoked -%}
本次结果只用于评价宿主框架对故障的处理，不代表任何真实模型的行为表现。轨迹中的 `model_output` 若标记为 `preset=true`，表示它是预注册脚本内容，不是模型现场生成。
{%- else -%}
本次确实调用了预注册模型。模型层只依据真实续跑轨迹、观察状态及公开 Oracle 规则判定；模型被调用并不等于模型行为正确，单次结果也不推广为稳定比例。
{%- endif %}

## 四、实际执行过程

| 过程指标 | 本次记录 |
|---|---:|
| 轨迹事件总数 | {{ execution.event_count }} |
| 工具调用次数 | {{ execution.tool_call_count }} |
| 工具返回次数 | {{ execution.tool_result_count }} |
| 故障注入事件数 | {{ execution.injection_count }} |
| 模型输出事件数（含预设） | {{ execution.model_output_count }} |
| 最终框架信号 | `{{ execution.framework_outcome }}` |
| 是否产生非空最终回答 | {{ execution.has_final_answer_label }} |

**涉及工具：** {{ execution.tool_names_display }}

### Harness 独立后置核验

{{ postcondition_result_display }}

### {{ final_answer_heading }}

{{ execution.final_answer_display }}

{{ final_answer_explanation }}

### 逐步事件摘要

下表来自 `steps.jsonl` 的实际顺序，不是事后推测。参数和返回内容以 JSON 表示；`preset` 只用于区分预设输出与真实模型输出。工具返回中的“错误信息”是工具或宿主记录的错误文本，不自动等于未捕获异常。

| 顺序 | 事件 | 实际内容 |
|---:|---|---|
{% for row in trace_rows -%}
| {{ row.seq }} | {{ row.event_label }}（`{{ row.event_type }}`） | {{ row.detail }} |
{% endfor %}

## 五、Oracle 如何判定

| 评价层 | 中文判定 | 原始标识 |
|---|---|---|
| 框架层 | {{ framework.verdict_label }} | `{{ framework.verdict }}` |
{% if model is not none -%}
| 模型层 | {{ model.verdict_label }} | `{{ model.verdict }}` |
{%- endif %}

框架层依据实际副作用、最终信号和后置条件；模型层依据真实调用、观察状态及公开规则。下面先列出人读证据，再保留可折叠的机器原文，便于复核而不是只给一个结论标签。

{% for judgement in judgement_views -%}
### {{ judgement.layer_label }}

- **判定：** {{ judgement.verdict_label }}（`{{ judgement.verdict }}`）
- **Oracle 说明：** {{ judgement.description }}
- **证据来源：** {{ judgement.source_label }}（`{{ judgement.source }}`）
- **确定性：** {{ judgement.determinism_label }}（`{{ judgement.determinism }}`）
- **验证状态：** {{ judgement.validation_label }}（`{{ judgement.validation }}`）
- **不适用原因：** {{ judgement.not_applicable_display }}
- **证据不足原因：** {{ judgement.inconclusive_display }}

关键证据：

| 证据项 | 实际值 |
|---|---|
{% for row in judgement.evidence_rows -%}
| {{ row.label }} | {{ row.value }} |
{% endfor %}

<details>
<summary>查看机器可读原始证据（审计用，不是另一项判定）</summary>

```json
{{ judgement.evidence_json }}
```

</details>
{% endfor %}

## 六、指标怎么读

### 框架层

| 指标 | 值 |
|---|---:|
| 总运行数 | {{ framework.total_runs }} |
| 注入失败数 | {{ framework.injection_failed }} |
| 适用运行数 | {{ framework.applicable }} / {{ framework.total_runs }} |
| 可判定运行数 | {{ framework.evaluable }} |
| 沉默失败次数 | {{ framework.silent_failures }} |
| 沉默失败率 | {{ framework.silent_failure_rate_display }} |
| Oracle 覆盖率 | {{ framework.oracle_coverage_display }} |
| 证据不足次数 | {{ framework.oi }} |

{% if model is not none -%}
### 模型层

| 指标 | 值 |
|---|---:|
| 总运行数 | {{ model.total_runs }} |
| 注入失败数 | {{ model.injection_failed }} |
| 适用运行数 | {{ model.applicable }} / {{ model.total_runs }} |
| 可判定运行数 | {{ model.evaluable }} |
| 沉默失败次数 | {{ model.silent_failures }} |
| 沉默失败率 | {{ model.silent_failure_rate_display }} |
| Oracle 覆盖率 | {{ model.oracle_coverage_display }} |
| 证据不足次数 | {{ model.oi }} |
{%- endif %}

- 总运行数：本报告只汇总当前一次运行，因此固定为 1；批次统计应查看套件报告。
- 注入失败数：任务声明了故障但注入未实际生效时记 1；这类运行不能冒充有效故障样本。
- 适用运行数：该层在本次预注册评价范围内的运行数；未列入 `target_layers` 的层不适用。
- 可判定运行数：注入、观察和证据满足该层判定条件的运行数；不适用和证据不足不会混入正常样本。
- 沉默失败次数：未满足契约却被表现为正常完成的次数，必须同时有实际证据支持。
- 沉默失败率：沉默失败数 ÷ 可判定运行数；分母为 0、低于最低样本数或只有单次运行时，人读报告显示 N/A，而不是 0% 或 100%。
- Oracle 覆盖率：可判定运行数 ÷ 适用运行数；单次报告只显示原始数量，不把 1/1 渲染成稳定覆盖率。
- 证据不足次数：Oracle 无法获得足够证据的次数，与“测试通过”或“发现缺陷”都不同。

**预注册最低可判定样本数：{{ min_evaluable }}。** 单运行报告始终只作定性案例；即使该阈值为 1，也不把一次结果换算成稳定比例。下方机器锚点仍保留原始数值，供同坐标批次聚合和独立复算。

## 七、结果边界与常见误读

- **注入边界：** {{ injection_boundary }}
- **观察边界：** {{ observation_boundary }}
- **模型边界：** {{ model_boundary }}
- **执行完成不等于没有缺陷：** Harness 执行完成只说明运行、落盘和复算流程结束；被测 Agent 仍可能得到显式失败、沉默失败或违反契约的判定。
- **四件套齐全不等于测试通过：** 它只说明 `run.json`、`steps.jsonl`、`oracle.jsonl`、`report.md` 都存在，不能替代对判定和证据的阅读。
- **N/A 不等于 0：** N/A 可能表示不适用、没有可判定样本或低于最低样本数；它不提供“没有发生失败”的证据。
- **单次样本不可外推：** 本报告不估计真实世界故障率，也不证明其他任务、宿主版本或模型具有相同表现。

## 八、分层坐标与复算

分层坐标为“宿主 × 执行模式 × 故障族 × 注入位置 × 故障类型 × 呈现方式”。
本次前段坐标：`{{ host }} × {{ mode }} × {{ experiment_family }}`；
故障坐标：`{{ injection_point }} × {{ fault_type }} × {{ surface_as }}`。
只有坐标与预注册声明一致的结果才可聚合，避免把不同实验混为一谈。

### 复算环境

| 字段 | 本次值 |
|---|---|
| FaultLattice commit | `{{ versions.faultlattice_commit_display }}` |
| 宿主包版本 | `{{ versions.host_package_version_display }}` |
| 宿主源码 commit | `{{ versions.host_commit_display }}` |
| Python 版本 | `{{ versions.python_version }}` |
| 依赖锁哈希 | `{{ versions.dependency_lock_hash_display }}` |

{% if versions.null_reasons -%}
字段为 `null` 的原因：

| 字段 | 原因 |
|---|---|
{% for item in versions.null_reasons -%}
| `{{ item.name }}` | {{ item.reason }} |
{% endfor %}
{%- endif %}

<details>
<summary>查看机器复算锚点（供 faultlattice verify 逐字核对）</summary>

下方 JSON 不是实验结论正文，而是机器复算锚点；`faultlattice verify` 会从原始产物独立重算并逐字比较，不受上方说明文字影响。

```json faultlattice-metrics
{{ metrics_json }}
```

</details>
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


def _postcondition_display(manifest: RunManifest) -> str:
    condition = manifest.task.expected_postcondition
    if condition.kind == "file_written":
        path = condition.params.get("path", "未登记路径")
        content = condition.params.get("content_contains")
        suffix = f"，且内容包含“{content}”" if content is not None else ""
        return f"沙箱文件 `{path}` 应已写入{suffix}。"
    if condition.kind == "file_absent":
        path = condition.params.get("path", "未登记路径")
        return f"沙箱文件 `{path}` 不应存在；用于证明超时后工具没有继续产生副作用。"
    if condition.kind == "host_state":
        summary = condition.params.get("summary", "满足预注册的宿主业务状态")
        return f"运行结束后由宿主适配器只读查询实际业务状态：{summary}"
    return f"应满足 `{condition.kind}`：{canonical_dumps(condition.params)}"


def _postcondition_result_display(judgements: list[OracleJudgement]) -> str:
    """报告业务目标与后置条件，不把故障场景中的预期失败写成 Harness 失败。"""
    framework = next((item for item in judgements if item.layer is TargetLayer.FRAMEWORK), None)
    if framework is None:
        return "本次未登记框架层后置核验，无法从该层给出业务状态结论。"
    evidence = framework.evidence
    kind = evidence.get("kind")
    if kind == "host_state":
        summary = str(evidence.get("observation_summary") or "宿主未提供人读观察摘要")
        if evidence.get("evidence_sufficient") is False:
            return f"**业务状态证据不足：** {summary}。本次不能据最终回答推定任务成功或失败。"
        if evidence.get("task_succeeded") is True:
            return f"**业务目标已完成：** {summary}。该结论来自运行结束后的独立只读状态观察。"
        expected_failure = framework.verdict is FrameworkVerdict.EXPLICIT_FAILURE
        label = "业务目标未完成，宿主已明确报告失败" if expected_failure else "业务目标未完成"
        return f"**{label}：** {summary}。这是故障场景下的实际业务结果，不是 Harness 执行错误。"
    if kind not in ("file_written", "file_absent") or not isinstance(evidence.get("exists"), bool):
        return "本次没有完整的文件后置证据，请查看下方 Oracle 的不适用或证据不足原因。"
    path = evidence.get("path", "未登记路径")
    exists = evidence["exists"]
    if kind == "file_absent":
        result = (
            f"**后置条件已满足：** Harness 确认 `{path}` 不存在，超时进程没有继续产生该文件"
            if not exists
            else f"**后置条件未满足：** Harness 确认 `{path}` 仍存在，不能证明副作用已被阻止"
        )
        return result + "。该结论来自实际状态，不依赖进程是否已经返回结果。"
    content_ok = evidence.get("content_contains_ok", True) is True
    if exists and content_ok:
        result = f"**后置条件已满足：** Harness 在运行结束后直接检查沙箱，确认 `{path}` 存在且内容符合预注册条件"
    elif exists:
        result = f"**后置条件未满足：** Harness 确认 `{path}` 存在，但内容不符合预注册条件"
    else:
        result = f"**后置条件未满足：** Harness 未在沙箱中找到 `{path}`"
    return result + "。该结论来自实际状态，不依赖被测模型是否拥有读取工具。"


def _outcome_summary(
    manifest: RunManifest, judgements: list[OracleJudgement]
) -> tuple[str, dict[str, str]]:
    """用业务状态和调用方信号生成一句话结论，不把 Oracle 标签当作通过率。"""
    framework = next((item for item in judgements if item.layer is TargetLayer.FRAMEWORK), None)
    evidence = framework.evidence if framework is not None else {}
    succeeded = evidence.get("task_succeeded")
    outcome = str(evidence.get("framework_outcome") or "not_recorded")
    verdict = framework.verdict if framework is not None else None
    if succeeded is True:
        task_display = "是（独立状态证据）"
    elif succeeded is False:
        task_display = "否（独立状态证据）"
    else:
        task_display = "证据不足"
    signal_display = {
        "completed": "正常完成（`completed`）",
        "failed": "明确失败（`failed`）",
    }.get(outcome, "未记录")
    if succeeded is True and outcome == "failed":
        headline = (
            "**业务任务实际完成，但框架向调用方报告失败。** 实际状态与调用方信号不一致，"
            "因此本次判为违反预注册契约；不能笼统写成“写入未验证”。"
        )
    elif succeeded is False and outcome == "failed":
        headline = (
            "**业务任务未完成，框架返回了明确失败信号。** 这符合本次故障任务的显式失败处理预期，"
            "但不证明其他任务、模型或真实模型反应也已通过。"
        )
    elif succeeded is False and outcome == "completed":
        headline = (
            "**业务任务未完成，框架却报告正常完成。** 本次存在沉默失败或契约风险，"
            "应结合下方 Oracle 判定与状态证据处理。"
        )
    elif succeeded is True and outcome == "completed":
        headline = "**业务任务完成，框架报告正常完成。** 该结论仅适用于当前一次预注册坐标。"
    else:
        headline = "**业务状态证据不足，无法给出可靠的成功或失败结论。** 请先看观察失败原因。"
    if verdict is FrameworkVerdict.INCONCLUSIVE:
        headline = "**本次为证据不足（inconclusive），不是测试通过或 Agent 缺陷结论。** " + headline
    model = next((item for item in judgements if item.layer is TargetLayer.MODEL), None)
    if model is not None and model.verdict not in (
        ModelVerdict.COMPLETED,
        ModelVerdict.NOT_APPLICABLE,
    ):
        headline += f" 模型层另判为 `{model.verdict.value}`，不能用框架层结果覆盖。"
    return headline, {"task_succeeded": task_display, "framework_signal": signal_display}


def _fault_explanation(manifest: RunManifest) -> str:
    fault = manifest.task.fault
    if fault is None:
        return "这是无故障基线运行，用于确认宿主在正常条件下满足预注册契约。"
    if fault.injection_point.value == "tool_args":
        return "故障发生在工具真正执行之前，用来检查参数校验与异常是否被宿主正确传播。"
    if fault.injection_point.value == "tool_result":
        if fault.params.get("timeout_mode") == "process":
            return (
                "工具在独立子进程中执行；达到真实时钟期限后，Harness 终止并回收该进程，"
                "再向宿主报告 TimeoutError。该模式不同于工具完成后的模拟超时替换。"
            )
        return "故障发生在工具执行之后：真实副作用可能已经发生，但宿主看到的是被替换的返回或异常。"
    return "故障只改变进入模型下一轮上下文的内容，不改写工具已经产生的真实副作用。"


_EVENT_LABELS = {
    "task_start": "任务开始",
    "tool_call": "工具调用",
    "injection": "故障注入",
    "tool_result": "工具返回",
    "model_output": "模型输出",
    "run_end": "运行结束",
}
_ORACLE_SOURCE_LABELS = {
    "state": "实际状态",
    "rule": "确定性规则",
    "human": "人工复核",
    "judge": "评审器",
}
_ORACLE_DETERMINISM_LABELS = {
    "deterministic": "确定性（相同证据得到相同结果）",
    "stochastic": "随机性（结果可能受采样影响）",
}
_ORACLE_VALIDATION_LABELS = {
    "unvalidated": "尚未做黄金样例或人工对齐验证",
    "golden_verified": "已通过黄金样例验证",
    "human_aligned": "已与人工判定对齐",
}
_NOT_APPLICABLE_LABELS = {
    "layer_not_targeted": "该层不在预注册评价范围内",
    "injection_failed": "故障未实际注入，无法形成对应样本",
    "mode_not_applicable": "当前执行模式不适用该层",
    "model_not_invoked": "没有真实调用模型",
}
_INCONCLUSIVE_LABELS = {
    "injection_failed": "注入失败，不能据此判断被测对象",
    "oracle_evidence_insufficient": "Oracle 证据不足，不能强行归类",
}


def _markdown_cell(value: Any) -> str:
    """避免实际参数里的竖线或换行破坏人读表格。"""
    return str(value).replace("|", "\\|").replace("\r\n", "\n").replace("\n", "<br>")


def _event_detail(step: dict[str, Any]) -> str:
    event_type = step.get("event_type")
    if event_type == "task_start":
        return f"开始执行预注册任务 `{step.get('task_id', '未登记')}`。"
    if event_type == "tool_call":
        return _markdown_cell(
            f"调用 `{step.get('tool_name', '未知工具')}`；参数：{canonical_dumps(step.get('arguments', {}))}"
        )
    if event_type == "injection":
        parts = [
            f"实际生效：{'是' if step.get('applied') else '否'}",
            f"原始内容：{canonical_dumps(step.get('original'))}",
            f"替换内容：{canonical_dumps(step.get('replacement'))}",
        ]
        if step.get("raised") is not None:
            parts.append(f"抛出异常：{step['raised']}")
        return _markdown_cell("；".join(parts) + "。")
    if event_type == "tool_result":
        result = step.get("result")
        error = step.get("error")
        if error is not None:
            content = f"工具返回错误：{error}"
            if result is not None and result != error:
                content += f"；同时记录的返回值：{canonical_dumps(result)}"
        else:
            content = f"返回：{canonical_dumps(result)}"
        injected = "；该结果被故障注入改写" if step.get("injected") else ""
        return _markdown_cell(f"工具 `{step.get('tool_name', '未知工具')}`；{content}{injected}。")
    if event_type == "model_output":
        source = "预设脚本输出" if step.get("preset") else "真实模型输出"
        phase = {"prefix": "真实前缀", "continuation": "故障后续跑"}.get(
            str(step.get("m3_phase") or ""), ""
        )
        reasoning = "；原始思考字段已记录" if step.get("reasoning_content") is not None else ""
        prefix = f"（{phase}）" if phase else ""
        return _markdown_cell(
            f"{source}{prefix}：{step.get('content') or '（空内容）'}{reasoning}"
        )
    if event_type == "run_end":
        return _markdown_cell(
            f"框架信号：`{step.get('framework_outcome', '未记录')}`；"
            f"最终回答：{step.get('final_answer') or '（无非空最终回答）'}"
        )
    return "已记录该事件；完整字段见 `steps.jsonl`。"


def _execution_summary(run_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    steps = read_jsonl(run_dir / "steps.jsonl")
    run_end = next((step for step in steps if step.get("event_type") == "run_end"), None)
    final_answer = run_end.get("final_answer") if run_end is not None else None
    has_final_answer = isinstance(final_answer, str) and bool(final_answer.strip())
    tool_names = sorted(
        {
            str(step.get("tool_name"))
            for step in steps
            if step.get("event_type") == "tool_call" and step.get("tool_name") is not None
        }
    )
    summary = {
        "event_count": len(steps),
        "tool_call_count": sum(step.get("event_type") == "tool_call" for step in steps),
        "tool_result_count": sum(step.get("event_type") == "tool_result" for step in steps),
        "injection_count": sum(step.get("event_type") == "injection" for step in steps),
        "model_output_count": sum(step.get("event_type") == "model_output" for step in steps),
        "reasoning_output_count": sum(
            step.get("event_type") == "model_output" and step.get("reasoning_content") is not None
            for step in steps
        ),
        "framework_outcome": (
            run_end.get("framework_outcome", "not_recorded") if run_end is not None else "not_recorded"
        ),
        "has_final_answer_label": "是" if has_final_answer else "否",
        "tool_names_display": "、".join(f"`{name}`" for name in tool_names) or "本次没有工具调用",
        "final_answer_display": _markdown_cell(final_answer or "本次未产生非空最终回答。"),
    }
    rows = [
        {
            "seq": step.get("seq", index),
            "event_type": step.get("event_type", "unknown"),
            "event_label": _EVENT_LABELS.get(str(step.get("event_type") or ""), "其他事件"),
            "detail": _event_detail(step),
        }
        for index, step in enumerate(steps, start=1)
    ]
    return summary, rows


def _evidence_rows(evidence: dict[str, Any]) -> list[dict[str, str]]:
    """把常用证据翻译成人读字段；未识别的数据仍完整保留在折叠原文中。"""
    labels = {
        "evidence_sufficient": "证据是否充分",
        "task_succeeded": "业务任务是否完成",
        "framework_outcome": "框架向调用方报告",
        "observation_summary": "独立状态观察",
        "fact_found": "独立查询是否找到事实",
        "value_matches": "事实当前值是否符合预注册",
        "fact_id": "实际事实 ID",
        "original_expression_succeeded": "原算式是否成功计算",
        "injected_failure_observed": "注入后的错误是否留痕",
        "tool_failures": "生产状态中的工具失败数",
        "stop_reason": "生产循环停止原因",
        "answer": "宿主最终回答",
        "exists": "目标文件是否存在",
        "content_contains_ok": "文件内容是否符合预期",
        "path": "核验路径",
        "model_invoked": "是否真实调用模型",
        "observation_status": "模型观察状态",
        "final_answer": "最终回答",
    }
    rows: list[dict[str, str]] = []
    for key, label in labels.items():
        if key not in evidence:
            continue
        value = evidence[key]
        if isinstance(value, bool):
            display = "是" if value else "否"
        elif value is None:
            display = "无"
        else:
            display = _markdown_cell(value)
        rows.append({"label": label, "value": display})
    steps = evidence.get("steps")
    if isinstance(steps, list):
        rows.append({"label": "生产工具步骤数", "value": str(len(steps))})
    if not rows:
        rows.append({"label": "证据字段", "value": "无常用字段；请展开下方原始证据复核"})
    return rows


def _judgement_views(judgements: list[OracleJudgement]) -> list[dict[str, Any]]:
    views = []
    for judgement in judgements:
        verdict = judgement.verdict.value
        na_reason = judgement.not_applicable_reason.value if judgement.not_applicable_reason else None
        inconclusive = judgement.inconclusive_reason.value if judgement.inconclusive_reason else None
        views.append(
            {
                "layer_label": "框架层" if judgement.layer is TargetLayer.FRAMEWORK else "模型层",
                "verdict": verdict,
                "verdict_label": _VERDICT_LABELS.get(verdict, verdict),
                "description": judgement.oracle.description,
                "source": judgement.oracle.source.value,
                "source_label": _ORACLE_SOURCE_LABELS[judgement.oracle.source.value],
                "determinism": judgement.oracle.determinism.value,
                "determinism_label": _ORACLE_DETERMINISM_LABELS[judgement.oracle.determinism.value],
                "validation": judgement.oracle.validation.value,
                "validation_label": _ORACLE_VALIDATION_LABELS[judgement.oracle.validation.value],
                "not_applicable_display": (
                    f"{_NOT_APPLICABLE_LABELS[na_reason]}（`{na_reason}`）" if na_reason else "无"
                ),
                "inconclusive_display": (
                    f"{_INCONCLUSIVE_LABELS[inconclusive]}（`{inconclusive}`）"
                    if inconclusive
                    else "无"
                ),
                "evidence_rows": _evidence_rows(judgement.evidence),
                "evidence_json": canonical_dumps(judgement.evidence),
            }
        )
    return views


def _boundary_text(manifest: RunManifest) -> tuple[str, str, str]:
    if manifest.task.fault is None:
        injection = "这是无故障基线，不把 `injection_applied` 解释为故障测试已经成功。"
    elif manifest.injection_applied:
        injection = "`true` 只证明指定内容确实按预注册规则发生变化，不证明被测 Agent 处理正确。"
    else:
        injection = "`false` 表示故障未实际生效；该次运行不能作为有效故障样本，应先看配置或适配器错误。"
    observation_status = manifest.observation_status.value
    observation = {
        "reached": "`reached` 只证明故障内容进入模型观察，不证明模型理解或正确处理了它。",
        "not_reached": "`not_reached` 表示故障没有进入模型观察，不能据此评价模型会如何处理该故障。",
        "not_applicable": "`not_applicable` 表示本次没有真实模型观察环节，常见于 M0–M2；它不是观察失败。",
        "unknown": "`unknown` 表示现有证据无法确认观察是否到达，相关模型层结论应保持证据不足。",
    }[observation_status]
    model = (
        "真实模型已参与本次续跑，但调用成功只说明获得响应，不自动意味着行为满足契约。"
        if manifest.model_invoked
        else "本次没有真实模型参与，因此不能形成真实模型行为结论，也不能把预设输出当作模型能力证据。"
    )
    return injection, observation, model


def _version_view(manifest: RunManifest) -> dict[str, Any]:
    versions = manifest.versions
    reasons = dict(versions.null_reasons)
    # 早期通用采集器把所有无版本宿主都写成“本地受控宿主／PyPI 包”。
    # 人读报告按实际外部快照纠正说明，但不回改冻结的 run.json。
    if manifest.task.host not in {"local_controlled", "smolagents", "langgraph"}:
        if versions.host_package_version is None:
            reasons["host_package_version"] = "外部项目以工作区源码快照接入，未登记独立包版本"
        if versions.host_commit is None:
            reasons["host_commit"] = (
                "外部源码副本未登记 commit；适配器源码 SHA-256 已保存在接入登记与批次记录中"
            )
    return {
        "faultlattice_commit_display": versions.faultlattice_commit or "null",
        "host_package_version_display": versions.host_package_version or "null",
        "host_commit_display": versions.host_commit or "null",
        "python_version": versions.python_version,
        "dependency_lock_hash_display": versions.dependency_lock_hash or "null",
        "null_reasons": [
            {"name": name, "reason": reason} for name, reason in sorted(reasons.items())
        ],
    }


def render_report(run_dir: Path) -> str:
    """读取原始产物，渲染 report.md 文本（不写盘）。"""
    run_dir = Path(run_dir)
    manifest = load_manifest(run_dir)
    metrics = compute_metrics(run_dir)
    task = manifest.task
    fault = task.fault
    injection_point = fault.injection_point.value if fault else "none"
    fault_type = fault.fault_type.value if fault else "none"
    surface_as = fault.surface_as.value if fault else "none"
    observation_status = manifest.observation_status.value
    execution, trace_rows = _execution_summary(run_dir)
    judgements = load_judgements(run_dir)
    injection_boundary, observation_boundary, model_boundary = _boundary_text(manifest)
    headline, outcome_summary = _outcome_summary(manifest, judgements)

    def _view(layer_metrics: dict[str, Any]) -> dict[str, Any]:
        # 单次运行只展示原始计数；机器指标不改动，verify 仍按原始锚点复算。
        single_run = layer_metrics["total_runs"] == 1
        applicable = layer_metrics["applicable"]
        return {
            **layer_metrics,
            "oi": layer_metrics["oracle_insufficient"],
            "oi_ratio": layer_metrics["oracle_insufficient_ratio"],
            "silent_failure_rate_display": (
                "N/A（单次样本）" if single_run else layer_metrics["silent_failure_rate_display"]
            ),
            "oracle_coverage_display": (
                f"{layer_metrics['evaluable']}/{applicable}（仅本次）"
                if single_run and applicable
                else layer_metrics["oracle_coverage_display"]
            ),
            "verdict_label": _VERDICT_LABELS.get(layer_metrics["verdict"], layer_metrics["verdict"]),
        }

    model_metrics = metrics["model"]
    return REPORT_TEMPLATE.render(
        run_id=manifest.run_id,
        task_id=task.task_id,
        task_description=task.description,
        host=task.host,
        host_label=_HOST_LABELS.get(task.host, task.host),
        mode=task.mode.value,
        mode_label=_MODE_LABELS[task.mode.value],
        created_at_display=manifest.created_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
        expected_behavior=task.expected_behavior,
        postcondition_display=_postcondition_display(manifest),
        postcondition_result_display=_postcondition_result_display(judgements),
        allowed_degradation="；".join(task.allowed_degradation) or "未声明",
        injection_point=injection_point,
        injection_label=_INJECTION_LABELS[injection_point],
        fault_type=fault_type,
        fault_label=_FAULT_LABELS[fault_type],
        surface_as=surface_as,
        surface_label=_SURFACE_LABELS[surface_as],
        fault_explanation=_fault_explanation(manifest),
        fault_params_display=canonical_dumps(fault.params) if fault else "{}",
        experiment_family=fault.experiment_family.value if fault else "none",
        injection_applied_label="是" if manifest.injection_applied else "否",
        headline=headline,
        outcome_summary=outcome_summary,
        final_answer_heading=(
            "真实模型最终回答（自述）" if manifest.model_invoked else "预设最终回答（非真实模型输出）"
        ),
        final_answer_explanation=(
            "模型自述只用于模型层规则，不替代 Harness 对真实状态的独立核验；模型未读取业务状态时，"
            "其“未验证”不等于 Harness 也未验证。"
            if manifest.model_invoked
            else "这段文字来自运行前冻结的脚本，只用于驱动生产循环，不能用于评价模型能力。"
            "业务结论来自真实工具、生产状态和独立后置观察。"
        ),
        model_id=manifest.versions.model_id or "未使用模型",
        model_invoked=manifest.model_invoked,
        model_invoked_label="是" if manifest.model_invoked else "否（预设脚本不调用真实模型）",
        reasoning_mode_label=(
            {
                "enabled": "思考模式（显式启用，原始字段逐轮回传）",
                "disabled": "非思考模式（显式实验条件，不得外推为思考表现）",
            }.get(
                task.model.reasoning_mode,
                "思考模式（提供方默认开启）"
                if task.model.model_id.startswith("deepseek-")
                else "提供方默认",
            )
            if task.model
            else "不适用（本次未预注册真实模型）"
        ),
        sampling_params_display=(
            canonical_dumps(manifest.versions.sampling_params)
            if manifest.versions.sampling_params is not None
            else "null（本次未使用真实模型采样参数）"
        ),
        observation_status=observation_status,
        observation_label=_OBSERVATION_LABELS[observation_status],
        target_layers_label="、".join(
            "框架层" if layer is TargetLayer.FRAMEWORK else "模型层"
            for layer in task.target_layers
        ),
        execution=execution,
        trace_rows=trace_rows,
        judgement_views=_judgement_views(judgements),
        injection_boundary=injection_boundary,
        observation_boundary=observation_boundary,
        model_boundary=model_boundary,
        versions=_version_view(manifest),
        min_evaluable=task.min_evaluable,
        framework=_view(metrics["framework"]),
        model=_view(model_metrics) if model_metrics else None,
        metrics_json=canonical_dumps(metrics),
    )


def generate_report(run_dir: Path) -> Path:
    """生成 report.md 并写盘（只读原始产物）。"""
    writer = TraceWriter(Path(run_dir))
    writer.write_report(render_report(run_dir))
    return Path(run_dir) / REPORT_MD


def verify_report(run_dir: Path) -> list[str]:
    """独立重算指标并与 report.md 内嵌 metrics 块比较。"""
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
