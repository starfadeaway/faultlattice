"""多模型目录只暴露元数据，embedding-only 不得用于对话。"""

import pytest
from fastapi.testclient import TestClient

from console.server import app as app_module
from console.server.models import discover_model_options, resolve_advisor_option
from faultlattice.errors import ConfigurationError


def test_chat_catalog_excludes_embedding_and_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FAULTLATTICE_MODEL_API_KEY", raising=False)
    monkeypatch.delenv("FAULTLATTICE_ADVISOR_MODEL_ID", raising=False)
    monkeypatch.setenv("FAULTLATTICE_LLM_KIMI_API_KEY", "never-return-this")
    monkeypatch.setenv("FAULTLATTICE_LLM_KIMI_BASE_URL", "https://kimi.example/v1")
    monkeypatch.setenv("FAULTLATTICE_LLM_KIMI_MODEL_ID", "kimi-k2.5")
    monkeypatch.setenv("FAULTLATTICE_LLM_KIMI_LABEL", "Kimi")
    monkeypatch.setenv("FAULTLATTICE_LLM_KIMI_CAPABILITIES", "chat")
    monkeypatch.setenv("FAULTLATTICE_LLM_KIMI_SAMPLING_PARAMS", '{"temperature":1}')
    monkeypatch.setenv("FAULTLATTICE_LLM_SILICONFLOW_API_KEY", "embedding-secret")
    monkeypatch.setenv("FAULTLATTICE_LLM_SILICONFLOW_MODEL_ID", "embedding-model")
    monkeypatch.setenv("FAULTLATTICE_LLM_SILICONFLOW_CAPABILITIES", "embedding")

    options = discover_model_options()
    assert [option.option_id for option in options] == ["kimi"]
    public = options[0].public()
    assert public["model_id"] == "kimi-k2.5"
    assert public["reasoning_mode"] == "default"
    assert public["sampling_params"] == {"temperature": 1}
    assert options[0].sampling_params == {"temperature": 1}
    assert "api_key" not in public
    assert "never-return-this" not in str(public)
    assert resolve_advisor_option("kimi").base_url == "https://kimi.example/v1"
    with pytest.raises(ConfigurationError, match="不存在"):
        resolve_advisor_option("siliconflow")

    client = TestClient(app_module.app)
    response = client.get("/api/experiments/models")
    assert response.status_code == 200
    assert response.json() == [public]
    assert "never-return-this" not in response.text
    assert "embedding-secret" not in response.text


def test_legacy_advisor_remains_available(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAULTLATTICE_MODEL_API_KEY", "legacy-secret")
    monkeypatch.setenv("FAULTLATTICE_ADVISOR_MODEL_ID", "legacy-model")
    monkeypatch.setenv("FAULTLATTICE_MODEL_BASE_URL", "https://legacy.example/v1")
    selected = resolve_advisor_option()
    assert selected.option_id == "default"
    assert selected.model_id == "legacy-model"
    assert selected.api_key == "legacy-secret"


def test_reasoning_mode_is_validated_and_never_implicitly_disabled() -> None:
    env = {
        "FAULTLATTICE_LLM_DEEPSEEK_API_KEY": "test-only",
        "FAULTLATTICE_LLM_DEEPSEEK_MODEL_ID": "deepseek-flash",
        "FAULTLATTICE_LLM_DEEPSEEK_CAPABILITIES": "chat",
        "FAULTLATTICE_LLM_DEEPSEEK_REASONING_MODE": "enabled",
    }
    selected = discover_model_options(env)[0]
    assert selected.reasoning_mode == "enabled"
    assert selected.public()["reasoning_mode"] == "enabled"

    invalid = {**env, "FAULTLATTICE_LLM_DEEPSEEK_REASONING_MODE": "auto-off"}
    with pytest.raises(ConfigurationError, match="REASONING_MODE"):
        discover_model_options(invalid)
    unsupported = {
        **env,
        "FAULTLATTICE_LLM_DEEPSEEK_MODEL_ID": "other-model",
        "FAULTLATTICE_LLM_DEEPSEEK_REASONING_MODE": "disabled",
    }
    with pytest.raises(ConfigurationError, match="尚未验证"):
        discover_model_options(unsupported)


@pytest.mark.parametrize("field_name", ["SAMPLING_PARAMS", "ADVISOR_SAMPLING_PARAMS"])
def test_sampling_params_must_be_an_explicit_json_object(field_name: str) -> None:
    env = {
        "FAULTLATTICE_LLM_KIMI_API_KEY": "test-only",
        "FAULTLATTICE_LLM_KIMI_MODEL_ID": "kimi-example",
        "FAULTLATTICE_LLM_KIMI_CAPABILITIES": "chat",
    }
    for invalid in ("not-json", "[]", '{"":1}'):
        with pytest.raises(ConfigurationError, match=field_name):
            discover_model_options({**env, f"FAULTLATTICE_LLM_KIMI_{field_name}": invalid})
