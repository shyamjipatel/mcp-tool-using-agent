"""Provider configuration stays explicit and credential-free in tests."""

import pytest

from app.config import Settings, make_model


def test_hugging_face_is_default_and_requires_token() -> None:
    settings = Settings()
    assert settings.llm_provider == "huggingface"
    with pytest.raises(ValueError, match="HF_TOKEN"):
        make_model(settings)
    model = make_model(Settings(hf_token="test-token"))
    assert model.model_name == "openai/gpt-oss-120b:fastest"


def test_local_provider_requires_url_and_model() -> None:
    with pytest.raises(ValueError, match="LLM_BASE_URL"):
        make_model(Settings(llm_provider="local"))
    model = make_model(Settings(llm_provider="local", llm_model="test-model", llm_base_url="http://127.0.0.1:11434/v1"))
    assert model.model_name == "test-model"
