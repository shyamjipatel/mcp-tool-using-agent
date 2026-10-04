"""Environment-driven application configuration."""

import os
from dataclasses import dataclass
from typing import Literal

from langchain_openai import ChatOpenAI


ProviderName = Literal["huggingface", "openai", "local"]


@dataclass(frozen=True)
class Settings:
    llm_provider: ProviderName = "huggingface"
    llm_model: str = ""
    hf_token: str = ""
    openai_api_key: str = ""
    llm_base_url: str = ""
    mcp_server_url: str = ""
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Settings":
        provider = os.getenv("LLM_PROVIDER", "huggingface").lower()
        if provider not in ("huggingface", "openai", "local"):
            raise ValueError("LLM_PROVIDER must be huggingface, openai, or local.")
        return cls(
            llm_provider=provider,
            llm_model=os.getenv("LLM_MODEL", ""),
            hf_token=os.getenv("HF_TOKEN", ""),
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            llm_base_url=os.getenv("LLM_BASE_URL", ""),
            mcp_server_url=os.getenv("MCP_SERVER_URL", ""),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
        )


def make_model(settings: Settings) -> ChatOpenAI:
    if settings.llm_provider == "huggingface":
        if not settings.hf_token:
            raise ValueError("HF_TOKEN is required for the Hugging Face provider.")
        return ChatOpenAI(
            model=settings.llm_model or "openai/gpt-oss-120b:fastest",
            api_key=settings.hf_token,
            base_url="https://router.huggingface.co/v1",
            timeout=30,
            max_retries=1,
        )
    if settings.llm_provider == "openai":
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required for the OpenAI provider.")
        return ChatOpenAI(
            model=settings.llm_model or "gpt-4.1-mini",
            api_key=settings.openai_api_key,
            timeout=30,
            max_retries=1,
        )
    if not settings.llm_base_url or not settings.llm_model:
        raise ValueError("LLM_BASE_URL and LLM_MODEL are required for the local provider.")
    return ChatOpenAI(
        model=settings.llm_model,
        api_key="local",
        base_url=settings.llm_base_url,
        timeout=30,
        max_retries=1,
    )
