"""测试默认隔离本机模型凭据，防止真实配置影响测试前提或触发计费调用。"""

import os

import pytest


@pytest.fixture(autouse=True)
def _isolate_model_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(os.environ):
        if name.startswith("FAULTLATTICE_LLM_") or name in {
            "FAULTLATTICE_MODEL_API_KEY",
            "FAULTLATTICE_MODEL_BASE_URL",
            "FAULTLATTICE_ADVISOR_MODEL_ID",
        }:
            monkeypatch.delenv(name, raising=False)
