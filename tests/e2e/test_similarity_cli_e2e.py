"""相似索引 CLI 使用真实 LanceDB 文件，但模型端点替换为确定性伪向量。"""

import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

pytest.importorskip("lancedb")

from faultlattice.cli import app  # noqa: E402
from faultlattice.indexing import EmbeddingSpec  # noqa: E402

SAMPLE = (
    Path(__file__).resolve().parent.parent.parent
    / "runs"
    / "_sample"
    / "20261124T124335-94ebab0a"
)


def test_similarity_build_and_search_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runs = tmp_path / "runs"
    shutil.copytree(SAMPLE, runs / SAMPLE.name)
    spec = EmbeddingSpec(model_id="fake-embedding", model_version="v1", dimensions=2)

    class FakeProvider:
        def __init__(self) -> None:
            self.spec = spec

        def embed(self, texts: list[str]) -> list[list[float]]:
            return [[1.0, 0.0] for _ in texts]

    monkeypatch.setattr(
        "faultlattice.adapters.openai_embedding.OpenAIEmbeddingProvider.from_env",
        lambda: FakeProvider(),
    )
    runner = CliRunner()
    index = tmp_path / "index"
    built = runner.invoke(
        app,
        ["similarity-build", "--runs-root", str(runs), "--index-root", str(index)],
    )
    assert built.exit_code == 0, built.output
    assert "1 次运行" in built.output
    assert (index / "index-metadata.json").is_file()

    found = runner.invoke(
        app,
        ["similarity-search", "invalid args", "--index-root", str(index), "--limit", "1"],
    )
    assert found.exit_code == 0, found.output
    assert SAMPLE.name in found.output
    assert "1.000000" in found.output
