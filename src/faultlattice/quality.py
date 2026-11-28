# 内嵌 Markdown 表格必须保持单行，避免破坏人读报告。
# ruff: noqa: E501
"""基于原始四件套的 CI 回归质量门禁。

门禁只比较相同预注册坐标下的 baseline / current，不执行新实验，也不调用
模型、数据库或向量服务。样本不足只抑制稳定比例结论；新增严重判定、注入
失败、可判定样本丢失、产物损坏和报告复算失败会明确拒绝 current。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml
from jinja2 import Template
from pydantic import BaseModel, ConfigDict, Field

from faultlattice.canonical import atomic_write, canonical_dumps, canonical_hash
from faultlattice.errors import ConfigurationError, FaultLatticeError
from faultlattice.indexing import load_run_index_record
from faultlattice.report import verify_report
from faultlattice.runner import load_judgements, load_manifest
from faultlattice.schemas import (
    ObservationStatus,
    RunManifest,
    TargetLayer,
)

_REQUIRED_ARTIFACTS = ("run.json", "steps.jsonl", "oracle.jsonl", "report.md")
_SEVERE_VERDICTS = ("silent_failure", "contract_violation")


class QualityBaseline(BaseModel):
    """版本化 baseline 配置；运行路径相对仓库根目录解析。"""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal[1]
    name: str = Field(min_length=1)
    runs: list[str] = Field(min_length=1)


class QualityViolation(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    message: str
    run_id: str | None = None
    coordinate: dict[str, str | None] | None = None


class LayerComparison(BaseModel):
    model_config = ConfigDict(frozen=True)

    layer: str
    baseline_evaluable: int
    current_evaluable: int
    baseline_silent_failures: int
    current_silent_failures: int
    baseline_contract_violations: int
    current_contract_violations: int
    min_evaluable: int
    rate_stability: str


class CoordinateComparison(BaseModel):
    model_config = ConfigDict(frozen=True)

    coordinate: dict[str, str | None]
    baseline_runs: int
    current_runs: int
    baseline_injection_failures: int
    current_injection_failures: int
    layers: list[LayerComparison]
    # 无故障运行不进入故障实验的 evaluable 分母，但判定变化仍是回归信号。
    baseline_no_fault_verdicts: list[str] = Field(default_factory=list)
    current_no_fault_verdicts: list[str] = Field(default_factory=list)


class QualityGateResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: Literal[1] = 1
    baseline_name: str
    passed: bool
    baseline_runs: int
    current_runs: int
    matched_coordinates: int
    comparisons: list[CoordinateComparison]
    violations: list[QualityViolation]


@dataclass(frozen=True)
class _RunSnapshot:
    run_dir: Path
    manifest: RunManifest | None
    verdicts: dict[str, str]
    problems: tuple[tuple[str, str], ...]

    @property
    def run_id(self) -> str:
        return self.manifest.run_id if self.manifest is not None else self.run_dir.name


def load_quality_baseline(path: Path, repo_root: Path) -> tuple[str, list[Path]]:
    """读取真实运行目录清单；拒绝空配置、重复路径和绝对路径。"""
    path = Path(path)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        config = QualityBaseline.model_validate(raw)
    except Exception as exc:
        raise ConfigurationError(f"质量门禁 baseline 配置无效: {path}: {exc}") from exc
    run_dirs: list[Path] = []
    for value in config.runs:
        candidate = Path(value)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ConfigurationError(f"baseline 运行路径必须是仓库内的相对路径: {value}")
        run_dirs.append(Path(repo_root) / candidate)
    if len(set(run_dirs)) != len(run_dirs):
        raise ConfigurationError("baseline 配置包含重复运行目录")
    return config.name, run_dirs


def _coordinate(manifest: RunManifest) -> dict[str, str | None]:
    task = manifest.task
    fault = task.fault
    return {
        "task_id": task.task_id,
        "host": task.host,
        "mode": task.mode.value,
        "experiment_family": fault.experiment_family.value if fault else None,
        "injection_point": fault.injection_point.value if fault else None,
        "fault_type": fault.fault_type.value if fault else None,
        "surface_as": fault.surface_as.value if fault else None,
        "model_id": task.model.model_id if task.model else None,
        "reasoning_mode": task.model.reasoning_mode if task.model else None,
    }


def _load_snapshot(run_dir: Path) -> _RunSnapshot:
    problems: list[tuple[str, str]] = []
    manifest: RunManifest | None = None
    verdicts: dict[str, str] = {}
    missing = [name for name in _REQUIRED_ARTIFACTS if not (run_dir / name).is_file()]
    if missing:
        problems.append(("artifact_missing", "缺少四件套文件：" + "、".join(missing)))
    try:
        manifest = load_manifest(run_dir)
    except FaultLatticeError as exc:
        problems.append(("artifact_invalid", str(exc)))
    if manifest is not None:
        try:
            load_run_index_record(run_dir)
            judgements = load_judgements(run_dir)
            for layer in TargetLayer:
                matches = [item for item in judgements if item.layer is layer]
                if layer in manifest.task.target_layers and len(matches) != 1:
                    problems.append(
                        (
                            "artifact_invalid",
                            f"{layer.value} 层应有且仅有一条 Oracle 判定，实际 {len(matches)} 条",
                        )
                    )
                if len(matches) > 1:
                    problems.append(("artifact_invalid", f"{layer.value} 层存在重复判定"))
                if len(matches) == 1:
                    verdicts[layer.value] = matches[0].verdict.value
        except FaultLatticeError as exc:
            problems.append(("artifact_invalid", str(exc)))
        for problem in verify_report(run_dir):
            problems.append(("report_verification_failed", problem))
    return _RunSnapshot(run_dir, manifest, verdicts, tuple(problems))


def _is_evaluable(snapshot: _RunSnapshot, layer: TargetLayer) -> bool:
    manifest = snapshot.manifest
    if manifest is None or layer not in manifest.task.target_layers:
        return False
    verdict = snapshot.verdicts.get(layer.value)
    if verdict is None or not manifest.injection_applied:
        return False
    if layer is TargetLayer.MODEL:
        return (
            manifest.observation_status is ObservationStatus.REACHED
            and verdict not in {"inconclusive", "not_applicable"}
        )
    return verdict != "inconclusive"


def _layer_comparison(
    baseline: list[_RunSnapshot], current: list[_RunSnapshot], layer: TargetLayer
) -> LayerComparison:
    baseline_targeted = [
        item for item in baseline if item.manifest and layer in item.manifest.task.target_layers
    ]
    current_targeted = [
        item for item in current if item.manifest and layer in item.manifest.task.target_layers
    ]
    baseline_evaluable = sum(_is_evaluable(item, layer) for item in baseline_targeted)
    current_evaluable = sum(_is_evaluable(item, layer) for item in current_targeted)
    manifests = [
        item.manifest
        for item in [*baseline_targeted, *current_targeted]
        if item.manifest is not None
    ]
    min_evaluable = max(3, *(item.task.min_evaluable for item in manifests))
    applicable = len(current_targeted)
    oracle_insufficient = sum(
        snapshot.verdicts.get(layer.value) == "inconclusive"
        and snapshot.manifest is not None
        and snapshot.manifest.injection_applied
        for snapshot in current_targeted
    )
    threshold = min(item.task.inconclusive_threshold for item in manifests)
    if current_evaluable == 0:
        stability = "no_evaluable_runs"
    elif current_evaluable < min_evaluable:
        stability = "below_min_evaluable"
    elif applicable and oracle_insufficient / applicable > threshold:
        stability = "inconclusive_threshold_exceeded"
    else:
        stability = "eligible_descriptive_rate"
    return LayerComparison(
        layer=layer.value,
        baseline_evaluable=baseline_evaluable,
        current_evaluable=current_evaluable,
        baseline_silent_failures=sum(
            _is_evaluable(item, layer) and item.verdicts.get(layer.value) == "silent_failure"
            for item in baseline_targeted
        ),
        current_silent_failures=sum(
            _is_evaluable(item, layer) and item.verdicts.get(layer.value) == "silent_failure"
            for item in current_targeted
        ),
        baseline_contract_violations=sum(
            _is_evaluable(item, layer) and item.verdicts.get(layer.value) == "contract_violation"
            for item in baseline_targeted
        ),
        current_contract_violations=sum(
            _is_evaluable(item, layer) and item.verdicts.get(layer.value) == "contract_violation"
            for item in current_targeted
        ),
        min_evaluable=min_evaluable,
        rate_stability=stability,
    )


def _injection_failures(snapshots: list[_RunSnapshot]) -> int:
    return sum(
        item.manifest is not None
        and item.manifest.task.fault is not None
        and not item.manifest.injection_applied
        for item in snapshots
    )


def _no_fault_verdicts(snapshots: list[_RunSnapshot]) -> list[str]:
    """保留无故障运行的逐层判定；它们不进入故障实验的可判定分母。"""
    return sorted(
        f"{layer}={verdict}"
        for snapshot in snapshots
        if snapshot.manifest is not None and snapshot.manifest.task.fault is None
        for layer, verdict in snapshot.verdicts.items()
    )


def evaluate_quality_gate(
    baseline_name: str, baseline_dirs: list[Path], current_dirs: list[Path]
) -> QualityGateResult:
    """比较完整坐标分组；current 为空或 baseline 为空均不得假绿。"""
    if not baseline_dirs or not current_dirs:
        raise ConfigurationError("质量门禁要求 baseline 与 current 都至少包含一个运行目录")
    baseline = [_load_snapshot(Path(path)) for path in baseline_dirs]
    current = [_load_snapshot(Path(path)) for path in current_dirs]
    violations = [
        QualityViolation(code=code, message=message, run_id=snapshot.run_id)
        for snapshot in [*baseline, *current]
        for code, message in snapshot.problems
    ]
    violations.extend(
        QualityViolation(
            code="unexpected_injection_for_no_fault",
            message="无故障任务不得把 injection_applied 记为 true",
            run_id=snapshot.run_id,
            coordinate=_coordinate(snapshot.manifest),
        )
        for snapshot in [*baseline, *current]
        if snapshot.manifest is not None
        and snapshot.manifest.task.fault is None
        and snapshot.manifest.injection_applied
    )
    grouped: dict[str, dict[str, Any]] = {}
    for side, snapshots in (("baseline", baseline), ("current", current)):
        for snapshot in snapshots:
            if snapshot.manifest is None:
                continue
            coordinate = _coordinate(snapshot.manifest)
            key = canonical_dumps(coordinate)
            group = grouped.setdefault(
                key, {"coordinate": coordinate, "baseline": [], "current": []}
            )
            group[side].append(snapshot)

    comparisons: list[CoordinateComparison] = []
    matched_coordinates = 0
    for key in sorted(grouped):
        group = grouped[key]
        baseline_group: list[_RunSnapshot] = group["baseline"]
        current_group: list[_RunSnapshot] = group["current"]
        coordinate: dict[str, str | None] = group["coordinate"]
        if baseline_group and current_group:
            matched_coordinates += 1
        if baseline_group and not current_group:
            violations.append(
                QualityViolation(
                    code="missing_current_coordinate",
                    message="current 缺少 baseline 中已有的完整实验坐标",
                    coordinate=coordinate,
                )
            )
        manifests = [
            item.manifest
            for item in [*baseline_group, *current_group]
            if item.manifest is not None
        ]
        fingerprints = {
            canonical_hash(item.task.model_dump(mode="json")) for item in manifests
        }
        if len(fingerprints) != 1:
            violations.append(
                QualityViolation(
                    code="preregistration_changed",
                    message="同一坐标的任务预注册声明发生变化，不能用新口径掩盖回归",
                    coordinate=coordinate,
                )
            )
        baseline_failures = _injection_failures(baseline_group)
        current_failures = _injection_failures(current_group)
        if current_failures > baseline_failures:
            violations.append(
                QualityViolation(
                    code="new_injection_failure",
                    message=(
                        f"新增注入失败：baseline={baseline_failures}，current={current_failures}"
                    ),
                    coordinate=coordinate,
                )
            )
        baseline_no_fault = _no_fault_verdicts(baseline_group)
        current_no_fault = _no_fault_verdicts(current_group)
        if baseline_no_fault != current_no_fault:
            violations.append(
                QualityViolation(
                    code="no_fault_verdict_changed",
                    message=(
                        "无故障运行的逐层判定发生变化："
                        f"baseline={baseline_no_fault}，current={current_no_fault}"
                    ),
                    coordinate=coordinate,
                )
            )
        layers = [
            layer
            for layer in TargetLayer
            if any(
                item.manifest is not None and layer in item.manifest.task.target_layers
                for item in [*baseline_group, *current_group]
            )
        ]
        layer_comparisons = [
            _layer_comparison(baseline_group, current_group, layer) for layer in layers
        ]
        for layer in layer_comparisons:
            for verdict in _SEVERE_VERDICTS:
                before = getattr(layer, f"baseline_{verdict}s")
                after = getattr(layer, f"current_{verdict}s")
                if after > before:
                    violations.append(
                        QualityViolation(
                            code=f"new_{verdict}",
                            message=(
                                f"{layer.layer} 层新增 {verdict}：baseline={before}，current={after}"
                            ),
                            coordinate=coordinate,
                        )
                    )
            if layer.current_evaluable < layer.baseline_evaluable:
                violations.append(
                    QualityViolation(
                        code="evaluable_run_lost",
                        message=(
                            f"{layer.layer} 层可判定运行减少："
                            f"baseline={layer.baseline_evaluable}，current={layer.current_evaluable}"
                        ),
                        coordinate=coordinate,
                    )
                )
        comparisons.append(
            CoordinateComparison(
                coordinate=coordinate,
                baseline_runs=len(baseline_group),
                current_runs=len(current_group),
                baseline_injection_failures=baseline_failures,
                current_injection_failures=current_failures,
                layers=layer_comparisons,
                baseline_no_fault_verdicts=baseline_no_fault,
                current_no_fault_verdicts=current_no_fault,
            )
        )
    return QualityGateResult(
        baseline_name=baseline_name,
        passed=not violations,
        baseline_runs=len(baseline),
        current_runs=len(current),
        matched_coordinates=matched_coordinates,
        comparisons=comparisons,
        violations=violations,
    )


_QUALITY_REPORT = Template(
    """\
# FaultLattice CI 回归质量门禁

- Baseline：{{ result.baseline_name }}
- 结论：{{ "通过" if result.passed else "拒绝" }}
- 运行数：baseline {{ result.baseline_runs }}，current {{ result.current_runs }}
- 成功配对坐标：{{ result.matched_coordinates }}
- 违规项：{{ result.violations|length }}

本门禁只检查相对回归，不替代 pytest、Ruff、Pyright，也不证明被测 Agent 没有缺陷。
沉默失败率是描述性指标；可判定数低于任务预注册 min_evaluable、没有可判定样本或证据不足
超过阈值时，仅显示对应抑制原因，不形成稳定比例结论。
无故障运行的可判定数保持为 0，另比较逐层判定是否变化；该检查不评价 Oracle 本身是否正确。

## 完整坐标比较

| 任务 | 宿主 | 模式 | 故障族 | 注入点 | 故障类型 | 呈现方式 | 运行数 B/C | 注入失败 B/C | 层 | 可判定 B/C | 无故障判定 B/C | 最低样本 | 比例结论状态 |
|---|---|---|---|---|---|---|---:|---:|---|---:|---|---:|---|
{% for item in result.comparisons -%}
{% for layer in item.layers -%}
| {{ item.coordinate.task_id }} | {{ item.coordinate.host }} | {{ item.coordinate.mode }} | {{ item.coordinate.experiment_family or "N/A" }} | {{ item.coordinate.injection_point or "N/A" }} | {{ item.coordinate.fault_type or "N/A" }} | {{ item.coordinate.surface_as or "N/A" }} | {{ item.baseline_runs }}/{{ item.current_runs }} | {{ item.baseline_injection_failures }}/{{ item.current_injection_failures }} | {{ layer.layer }} | {{ layer.baseline_evaluable }}/{{ layer.current_evaluable }} | {{ item.baseline_no_fault_verdicts|join(", ") or "N/A" }} / {{ item.current_no_fault_verdicts|join(", ") or "N/A" }} | {{ layer.min_evaluable }} | {{ layer.rate_stability }} |
{% endfor -%}
{% endfor %}

## 违规项

{% if not result.violations -%}
未发现登记的回归条件。该结论只覆盖当前 baseline 与 current 的配对范围。
{% endif -%}
{% for item in result.violations -%}
- `{{ item.code }}`：{{ item.message }}{% if item.run_id %}（run_id=`{{ item.run_id }}`）{% endif %}
{% endfor %}

```json faultlattice-quality-gate
{{ metrics_json }}
```
"""
)


def generate_quality_gate_report(result: QualityGateResult, output_path: Path) -> Path:
    markdown = _QUALITY_REPORT.render(
        result=result, metrics_json=canonical_dumps(result.model_dump(mode="json"))
    )
    atomic_write(Path(output_path), (markdown.rstrip() + "\n").encode("utf-8"))
    return Path(output_path)
