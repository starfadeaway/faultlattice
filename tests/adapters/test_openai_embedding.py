"""OpenAI 兼容向量适配器测试；不发起真实 HTTP 请求。"""

from types import SimpleNamespace
from typing import Any, cast

import pytest

pytest.importorskip("openai")

from faultlattice.adapters.openai_embedding import OpenAIEmbeddingProvider  # noqa: E402
from faultlattice.errors import ConfigurationError  # noqa: E402
from faultlattice.indexing import EmbeddingSpec  # noqa: E402


def test_embedding_response_is_restored_to_input_order() -> None:
    provider = OpenAIEmbeddingProvider(
        api_key="test-only", base_url="https://embedding.example/v1"
    )
    captured = {}

    def create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            data=[
                SimpleNamespace(index=1, embedding=[0.0, 2.0]),
                SimpleNamespace(index=0, embedding=[1.0, 0.0]),
            ]
        )

    provider._client = cast(
        Any, SimpleNamespace(embeddings=SimpleNamespace(create=create))
    )
    assert provider.embed(["first", "second"]) == [[1.0, 0.0], [0.0, 2.0]]
    assert captured["model"] == "BAAI/bge-m3"
    assert captured["input"] == ["first", "second"]


def test_embedding_environment_excludes_chat_only_and_preserves_frozen_model() -> None:
    with pytest.raises(ConfigurationError, match="embedding"):
        OpenAIEmbeddingProvider.from_env({})
    with pytest.raises(ConfigurationError, match="冻结"):
        OpenAIEmbeddingProvider.from_env(
            {
                "FAULTLATTICE_LLM_SILICONFLOW_API_KEY": "test-only",
                "FAULTLATTICE_LLM_SILICONFLOW_MODEL_ID": "other-model",
                "FAULTLATTICE_LLM_SILICONFLOW_CAPABILITIES": "embedding",
            }
        )
    provider = OpenAIEmbeddingProvider.from_env(
        {
            "FAULTLATTICE_LLM_SILICONFLOW_API_KEY": "test-only",
            "FAULTLATTICE_LLM_SILICONFLOW_BASE_URL": "https://embedding.example/v1",
            "FAULTLATTICE_LLM_SILICONFLOW_MODEL_ID": "BAAI/bge-m3",
            "FAULTLATTICE_LLM_SILICONFLOW_CAPABILITIES": "chat,embedding",
            "FAULTLATTICE_EMBEDDING_MODEL_VERSION": "bge-m3",
        }
    )
    assert provider.spec == EmbeddingSpec()
