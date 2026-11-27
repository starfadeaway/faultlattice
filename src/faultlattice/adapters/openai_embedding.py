"""OpenAI 兼容 embeddings 端点；当前索引冻结为 BAAI/bge-m3 稠密向量。"""

from __future__ import annotations

import os
from collections.abc import Mapping

from openai import OpenAI, OpenAIError

from faultlattice.adapters.openai_model import (
    INSTALLED_OPENAI_VERSION,
    SUPPORTED_OPENAI_VERSION,
)
from faultlattice.errors import AdapterCapabilityError, ConfigurationError, ModelProviderError
from faultlattice.indexing import EmbeddingSpec


class OpenAIEmbeddingProvider:
    """仅做文本到向量的协议转换，不参与实验编排或对话。"""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str | None,
        spec: EmbeddingSpec | None = None,
    ) -> None:
        if INSTALLED_OPENAI_VERSION != SUPPORTED_OPENAI_VERSION:
            raise AdapterCapabilityError(
                f"OpenAI SDK 必须为 {SUPPORTED_OPENAI_VERSION}，实际为 {INSTALLED_OPENAI_VERSION}"
            )
        self.spec = spec or EmbeddingSpec()
        self._client = OpenAI(
            api_key=api_key, base_url=base_url, timeout=60.0, max_retries=0
        )

    @classmethod
    def from_env(
        cls, env: Mapping[str, str] | None = None
    ) -> OpenAIEmbeddingProvider:
        values = os.environ if env is None else env
        prefix = "FAULTLATTICE_LLM_SILICONFLOW_"
        capabilities = values.get(prefix + "CAPABILITIES", "").lower().split(",")
        api_key = values.get(prefix + "API_KEY", "").strip()
        model_id = values.get(prefix + "MODEL_ID", "").strip()
        if "embedding" not in capabilities or not api_key or not model_id:
            raise ConfigurationError("相似检索需要完整配置硅基流动 embedding 模型")
        if model_id != "BAAI/bge-m3":
            raise ConfigurationError("当前相似索引冻结为 BAAI/bge-m3，不能静默替换模型")
        spec = EmbeddingSpec(
            model_version=values.get("FAULTLATTICE_EMBEDDING_MODEL_VERSION", "bge-m3").strip()
        )
        return cls(
            api_key=api_key,
            base_url=values.get(prefix + "BASE_URL", "").strip() or None,
            spec=spec,
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            response = self._client.embeddings.create(model=self.spec.model_id, input=texts)
        except OpenAIError as exc:
            raise ModelProviderError(f"向量模型请求失败: {type(exc).__name__}") from exc
        ordered = sorted(response.data, key=lambda item: item.index)
        vectors = [list(item.embedding) for item in ordered]
        if len(vectors) != len(texts):
            raise ModelProviderError("向量模型返回数量与输入数量不一致")
        return vectors
