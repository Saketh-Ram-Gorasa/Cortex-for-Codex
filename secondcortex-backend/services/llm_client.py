"""
LLM Client Factory — creates the correct OpenAI-compatible client
based on the configured provider (GitHub Models vs Azure OpenAI).
"""

from __future__ import annotations

import logging
from openai import OpenAI, AzureOpenAI
from config import settings

logger = logging.getLogger("secondcortex.llm")


def create_llm_client() -> OpenAI:
    """Return an OpenAI-compatible client based on the configured provider."""
    if settings.llm_provider == "github_models":
        logger.info("Using GitHub Models (endpoint: %s, model: %s)",
                     settings.github_models_endpoint, settings.github_models_chat_model)
        return OpenAI(
            base_url=settings.github_models_endpoint,
            api_key=settings.github_token,
        )
    else:
        logger.info("Using Azure OpenAI (endpoint: %s)", settings.azure_openai_endpoint)
        return AzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
        )


def get_chat_model() -> str:
    """Return the chat model name for the configured provider."""
    if settings.llm_provider == "github_models":
        return settings.github_models_chat_model
    return settings.azure_openai_deployment


def get_embedding_model() -> str:
    """Return the embedding model name for the configured provider."""
    if settings.llm_provider == "github_models":
        return settings.github_models_embedding_model
    return settings.azure_openai_embedding_deployment
