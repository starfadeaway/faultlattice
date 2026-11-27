"""使用真实 LanceDB 临时目录验证向量写入、覆盖重建和相似查询。"""

import json
from pathlib import Path

import pytest

pytest.importorskip("lancedb")

from faultlattice.adapters.lance_similarity import LanceSimilarityStore  # noqa: E402
from faultlattice.errors import ConfigurationError, ModelProviderError  # noqa: E402
from faultlattice.indexing import EmbeddingSpec, load_run_index_record  # noqa: E402

SAMPLE = (
    Path(__file__).resolve().parent.parent.parent
    / "runs"
    / "_sample"
    / "20261124T124335-94ebab0a"
)


class FakeEmbedding:
    def __init__(self, spec: EmbeddingSpec) -> None:
        self.spec = spec

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] if "alpha" in text else [0.0, 2.0] for text in texts]


def _records():
    base = load_run_index_record(SAMPLE)
    return [
        base.model_copy(update={"run_id": "run-a", "search_text": "alpha tool error"}),
        base.model_copy(update={"run_id": "run-b", "search_text": "beta empty response"}),
    ]


def test_lancedb_rebuild_and_cosine_search(tmp_path: Path) -> None:
    spec = EmbeddingSpec(model_id="fake-embedding", model_version="v1", dimensions=2)
    provider = FakeEmbedding(spec)
    store = LanceSimilarityStore(tmp_path / "index", spec)
    assert store.rebuild(_records(), provider) == 2
    hits = store.search("alpha query", provider, limit=1)
    assert len(hits) == 1
    assert hits[0].run_id == "run-a"
    assert hits[0].score == pytest.approx(1.0)
    metadata = json.loads((tmp_path / "index" / "index-metadata.json").read_text(encoding="utf-8"))
    assert metadata["embedding"]["model_version"] == "v1"
    assert metadata["embedding"]["normalization"] == "l2"
    assert metadata["record_count"] == 2

    # 覆盖重建不会把同一批运行重复追加。
    assert store.rebuild(_records(), provider) == 2
    assert len(store.search("beta", provider)) == 2


def test_lancedb_rejects_model_mismatch_and_zero_vector(tmp_path: Path) -> None:
    spec = EmbeddingSpec(model_id="fake-embedding", model_version="v1", dimensions=2)
    store = LanceSimilarityStore(tmp_path / "index", spec)
    store.rebuild(_records(), FakeEmbedding(spec))
    other = EmbeddingSpec(model_id="fake-embedding", model_version="v2", dimensions=2)
    with pytest.raises(ConfigurationError, match="不一致"):
        store.search("alpha", FakeEmbedding(other))

    class ZeroEmbedding(FakeEmbedding):
        def embed(self, texts: list[str]) -> list[list[float]]:
            return [[0.0, 0.0] for _ in texts]

    with pytest.raises(ModelProviderError, match="零向量"):
        store.rebuild(_records(), ZeroEmbedding(spec))


def test_lancedb_empty_index_and_provider_count_mismatch(tmp_path: Path) -> None:
    spec = EmbeddingSpec(model_id="fake-embedding", model_version="v1", dimensions=2)
    provider = FakeEmbedding(spec)
    store = LanceSimilarityStore(tmp_path / "index", spec)
    assert store.rebuild([], provider) == 0
    assert store.search("alpha", provider) == []

    class EmptyEmbedding(FakeEmbedding):
        def embed(self, texts: list[str]) -> list[list[float]]:
            return []

    with pytest.raises(ModelProviderError, match="单次查询"):
        store.search("alpha", EmptyEmbedding(spec))
    with pytest.raises(ModelProviderError, match="数量与索引记录"):
        store.rebuild(_records(), EmptyEmbedding(spec))
