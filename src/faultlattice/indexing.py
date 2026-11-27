"""可重建运行索引与相似检索的框架无关契约。

原始四件套永远是事实来源。本模块只提取公开元数据和检索文本，不连接
MySQL、LanceDB 或模型 SDK；具体外部服务由 adapters 与 CLI 装配。
"""

from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from faultlattice.canonical import canonical_dumps, canonical_hash
from faultlattice.errors import ArtifactError, ConfigurationError, ModelProviderError
from faultlattice.runner import load_manifest
from faultlattice.schemas import ExecutionMode, OracleJudgement
from faultlattice.trace import read_jsonl


class RunIndexRecord(BaseModel):
    """一次运行的可重建结构索引；字段不包含任何环境凭据。"""

    model_config = ConfigDict(frozen=True)

    run_id: str
    created_at: datetime
    task_id: str
    description: str
    expected_behavior: str
    host: str
    host_package_version: str | None
    mode: ExecutionMode
    experiment_family: str | None
    injection_point: str | None
    fault_type: str | None
    surface_as: str | None
    target_layers: list[str]
    injection_applied: bool
    observation_status: str
    framework_verdict: str | None
    model_verdict: str | None
    run_dir: str
    manifest_sha256: str
    search_text: str


class EmbeddingSpec(BaseModel):
    """向量索引的冻结契约；任何字段变化都不得与旧索引混用。"""

    model_config = ConfigDict(frozen=True)

    model_id: str = "BAAI/bge-m3"
    # 服务方未提供可核验的远程权重 commit，因此这里冻结的是模型配置版本，
    # 不虚构上游 SHA；更换模型或提供方版本时必须使用新的索引目录。
    model_version: str = "bge-m3"
    dimensions: int = Field(default=1024, ge=1)
    normalization: str = "l2"
    distance_metric: str = "cosine"


class EmbeddingProvider(Protocol):
    """文本向量提供方；真实 HTTP 实现位于可选 adapter。"""

    spec: EmbeddingSpec

    def embed(self, texts: list[str]) -> list[list[float]]:
        """按输入顺序返回向量，不隐式改变模型或维度。"""
        ...


class SimilarityHit(BaseModel):
    """单个相似运行结果；score 是 cosine similarity，不是百分比或成功率。"""

    model_config = ConfigDict(frozen=True)

    run_id: str
    task_id: str
    host: str
    mode: str
    fault_type: str | None
    surface_as: str | None
    score: float


def normalize_embedding(vector: list[float], dimensions: int) -> list[float]:
    """校验有限数值和维度，并显式执行 L2 归一化。"""
    if len(vector) != dimensions:
        raise ModelProviderError(f"向量维度为 {len(vector)}，索引要求 {dimensions}")
    if not vector or not all(math.isfinite(value) for value in vector):
        raise ModelProviderError("向量包含 NaN / Infinity 或为空")
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        raise ModelProviderError("零向量无法执行 L2 归一化")
    return [value / norm for value in vector]


def load_run_index_record(run_dir: Path) -> RunIndexRecord:
    """读取并校验完整四件套，生成一条派生索引记录。"""
    run_dir = Path(run_dir)
    missing = [
        name
        for name in ("run.json", "steps.jsonl", "oracle.jsonl", "report.md")
        if not (run_dir / name).is_file()
    ]
    if missing:
        raise ArtifactError(f"运行 {run_dir.name} 缺少索引所需产物: {', '.join(missing)}")
    manifest = load_manifest(run_dir)
    if manifest.run_id != run_dir.name:
        raise ArtifactError(f"run_id 与目录名不一致: {run_dir}")
    events = read_jsonl(run_dir / "steps.jsonl")
    judgements = [
        OracleJudgement.model_validate(item) for item in read_jsonl(run_dir / "oracle.jsonl")
    ]
    verdicts = {item.layer.value: item.verdict.value for item in judgements}
    task = manifest.task
    fault = task.fault
    final_answers = [
        str(event.get("final_answer", ""))
        for event in events
        if event.get("event_type") == "run_end" and event.get("final_answer")
    ]
    search_parts = [
        f"任务：{task.task_id}\n{task.description}",
        f"宿主与模式：{task.host} / {task.mode.value}",
        "故障：" + (canonical_dumps(fault.model_dump(mode="json")) if fault else "无故障"),
        f"预注册预期：{task.expected_behavior}",
        *[
            canonical_dumps(
                {
                    "layer": item.layer.value,
                    "verdict": item.verdict.value,
                    "evidence": item.evidence,
                }
            )
            for item in judgements
        ],
        *(f"最终回答：{answer}" for answer in final_answers),
    ]
    return RunIndexRecord(
        run_id=manifest.run_id,
        created_at=manifest.created_at,
        task_id=task.task_id,
        description=task.description,
        expected_behavior=task.expected_behavior,
        host=task.host,
        host_package_version=manifest.versions.host_package_version,
        mode=task.mode,
        experiment_family=fault.experiment_family.value if fault else None,
        injection_point=fault.injection_point.value if fault else None,
        fault_type=fault.fault_type.value if fault else None,
        surface_as=fault.surface_as.value if fault else None,
        target_layers=[layer.value for layer in task.target_layers],
        injection_applied=manifest.injection_applied,
        observation_status=manifest.observation_status.value,
        framework_verdict=verdicts.get("framework"),
        model_verdict=verdicts.get("model"),
        run_dir=manifest.run_dir,
        manifest_sha256=canonical_hash(manifest.model_dump(mode="json")),
        search_text="\n\n".join(search_parts),
    )


def collect_run_records(runs_root: Path) -> list[RunIndexRecord]:
    """收集普通运行目录；套件状态和公开样例不混入默认索引。"""
    runs_root = Path(runs_root)
    if not runs_root.exists():
        return []
    if not runs_root.is_dir():
        raise ConfigurationError(f"runs_root 不是目录: {runs_root}")
    records = []
    for path in sorted(runs_root.iterdir(), key=lambda item: item.name):
        if not path.is_dir() or path.name in {"_sample", "suites", "_index"}:
            continue
        records.append(load_run_index_record(path))
    return records
