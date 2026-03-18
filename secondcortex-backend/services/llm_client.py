"""
LLM Client Factory — creates the correct OpenAI-compatible client
based on the configured provider (GitHub Models vs Azure OpenAI).
"""

from __future__ import annotations

import logging
from openai import OpenAI, AzureOpenAI, AsyncOpenAI, AsyncAzureOpenAI
from config import settings

logger = logging.getLogger("secondcortex.llm")


def create_llm_client() -> OpenAI:
    """Return an OpenAI-compatible client based on the configured provider."""
    if settings.llm_provider == "github_models":
        key_status = "present" if settings.github_token else "MISSING"
        logger.info("Using GitHub Models (endpoint: %s, model: %s). API Key: %s",
                     settings.github_models_endpoint, settings.github_models_chat_model, key_status)
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


def create_async_llm_client() -> AsyncOpenAI | AsyncAzureOpenAI:
    """Return an async OpenAI-compatible client based on the configured provider."""
    if settings.llm_provider == "github_models":
        logger.debug("Creating async GitHub Models client")
        return AsyncOpenAI(
            base_url=settings.github_models_endpoint,
            api_key=settings.github_token,
        )
    else:
        logger.debug("Creating async Azure OpenAI client")
        return AsyncAzureOpenAI(
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


# ── Groq (used by fast LLM agents) ──────────────────────────────────

def create_groq_client() -> OpenAI:
    """Return an OpenAI-compatible client pointed at the Groq API."""
    key_status = "present" if settings.groq_api_key else "MISSING"
    logger.info("Creating Groq client (model: %s). API Key: %s",
                settings.groq_model, key_status)
    return OpenAI(
        base_url=settings.groq_endpoint,
        api_key=settings.groq_api_key,
    )


def get_groq_model() -> str:
    """Return the Groq chat model name."""
    return settings.groq_model
