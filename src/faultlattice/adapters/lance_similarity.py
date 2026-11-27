"""LanceDB 本地相似故障索引；向量与文本查询共用同一冻结模型契约。"""

from __future__ import annotations

from pathlib import Path

import lancedb
import pyarrow as pa

from faultlattice.canonical import atomic_write, canonical_bytes, canonical_dumps
from faultlattice.errors import ConfigurationError, ModelProviderError
from faultlattice.indexing import (
    EmbeddingProvider,
    EmbeddingSpec,
    RunIndexRecord,
    SimilarityHit,
    normalize_embedding,
)


class LanceSimilarityStore:
    """小规模精确向量检索；不为了展示技术栈提前制造 IVF 参数。"""

    TABLE_NAME = "fault_runs"
    METADATA_NAME = "index-metadata.json"

    def __init__(self, root: Path, spec: EmbeddingSpec) -> None:
        self.root = Path(root)
        self.spec = spec

    def _schema(self) -> pa.Schema:
        fields = [
            pa.field("run_id", pa.string(), nullable=False),
            pa.field("task_id", pa.string(), nullable=False),
            pa.field("host", pa.string(), nullable=False),
            pa.field("mode", pa.string(), nullable=False),
            pa.field("fault_type", pa.string()),
            pa.field("surface_as", pa.string()),
            pa.field("search_text", pa.string(), nullable=False),
            pa.field("vector", pa.list_(pa.float32(), self.spec.dimensions), nullable=False),
        ]
        metadata = {
            "faultlattice.embedding": canonical_dumps(
                self.spec.model_dump(mode="json")
            ).encode("utf-8")
        }
        return pa.schema(fields, metadata=metadata)

    def _metadata(self, record_ids: list[str]) -> dict[str, object]:
        return {
            "schema_version": 1,
            "embedding": self.spec.model_dump(mode="json"),
            "record_count": len(record_ids),
            "run_ids": record_ids,
        }

    def rebuild(
        self, records: list[RunIndexRecord], provider: EmbeddingProvider
    ) -> int:
        """一次覆盖重建，避免同一 run 重复追加或混用不同向量模型。"""
        if provider.spec != self.spec:
            raise ConfigurationError("向量提供方与索引的模型、版本、维度或归一化契约不一致")
        vectors = provider.embed([item.search_text for item in records])
        if len(vectors) != len(records):
            raise ModelProviderError("向量模型返回数量与索引记录数量不一致")
        normalized = normalize_many(vectors, self.spec)
        rows = [
            {
                "run_id": record.run_id,
                "task_id": record.task_id,
                "host": record.host,
                "mode": record.mode.value,
                "fault_type": record.fault_type,
                "surface_as": record.surface_as,
                "search_text": record.search_text,
                "vector": vector,
            }
            for record, vector in zip(records, normalized, strict=True)
        ]
        self.root.mkdir(parents=True, exist_ok=True)
        database = lancedb.connect(str(self.root))
        if rows:
            database.create_table(
                self.TABLE_NAME, data=rows, schema=self._schema(), mode="overwrite"
            )
        else:
            database.create_table(self.TABLE_NAME, schema=self._schema(), mode="overwrite")
        record_ids = [record.run_id for record in records]
        atomic_write(self.root / self.METADATA_NAME, canonical_bytes(self._metadata(record_ids)))
        return len(records)

    def _validate(self) -> None:
        import json

        try:
            metadata = json.loads((self.root / self.METADATA_NAME).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ConfigurationError("相似索引缺少有效元数据，请先执行 similarity-build") from exc
        if metadata.get("embedding") != self.spec.model_dump(mode="json"):
            raise ConfigurationError("当前向量模型契约与已有索引不一致，请使用新目录重建")

    def search(
        self, query: str, provider: EmbeddingProvider, *, limit: int = 5
    ) -> list[SimilarityHit]:
        """执行真实 LanceDB cosine 查询；score 不解释为实验成功率。"""
        if not query.strip():
            raise ConfigurationError("相似检索查询不能为空")
        if not 1 <= limit <= 100:
            raise ConfigurationError("limit 必须在 1–100 之间")
        self._validate()
        if provider.spec != self.spec:
            raise ConfigurationError("查询向量提供方与索引契约不一致")
        vectors = provider.embed([query])
        if len(vectors) != 1:
            raise ModelProviderError("向量模型必须为单次查询返回一个向量")
        vector = normalize_embedding(vectors[0], self.spec.dimensions)
        database = lancedb.connect(str(self.root))
        try:
            table = database.open_table(self.TABLE_NAME)
        except (OSError, ValueError) as exc:
            raise ConfigurationError("相似索引表不存在或不可读，请重新构建索引") from exc
        # lancedb 0.41.0 运行时支持 distance_type，但其 LanceQueryBuilder 类型声明漏掉了该方法。
        rows = (
            table.search(vector)
            .distance_type(self.spec.distance_metric)  # pyright: ignore[reportAttributeAccessIssue]
            .select(["run_id", "task_id", "host", "mode", "fault_type", "surface_as"])
            .limit(limit)
            .to_arrow()
            .to_pylist()
        )
        return [
            SimilarityHit(
                run_id=row["run_id"],
                task_id=row["task_id"],
                host=row["host"],
                mode=row["mode"],
                fault_type=row["fault_type"],
                surface_as=row["surface_as"],
                score=1.0 - float(row["_distance"]),
            )
            for row in rows
        ]


def normalize_many(vectors: list[list[float]], spec: EmbeddingSpec) -> list[list[float]]:
    return [normalize_embedding(vector, spec.dimensions) for vector in vectors]
