"""
Task-aware LLM routing and client factory utilities.

Current behavior:
  - Primary provider: OpenAI API
  - Optional fallbacks: GitHub Models, Groq

The provider is configurable per task via env vars.
"""

from __future__ import annotations

import logging
import time
from collections import Counter
from dataclasses import dataclass
from threading import Lock

from openai import AsyncOpenAI, OpenAI

from config import settings
from services.rate_limiter import rate_limited_call


logger = logging.getLogger("secondcortex.llm")

VALID_PROVIDERS = {"openai", "github_models", "groq"}
CHAT_TASKS = {"retriever", "planner", "executor", "simulator", "archaeology"}
EMBEDDING_TASK = "embeddings"
ALL_TASKS = tuple(sorted(CHAT_TASKS | {EMBEDDING_TASK}))

_client_cache: dict[tuple[str, str], OpenAI | AsyncOpenAI] = {}
_client_lock = Lock()

_metrics = Counter()
_metrics_lock = Lock()


@dataclass(frozen=True)
class RouteSelection:
    task: str
    provider: str
    fallback_provider: str | None
    model: str
    fallback_model: str | None
    auth_mode: str | None


def _metric_inc(name: str, *, task: str, provider: str) -> None:
    key = (name, task, provider)
    with _metrics_lock:
        _metrics[key] += 1


def get_llm_metrics_snapshot() -> dict[str, int]:
    with _metrics_lock:
        return {f"{name}|task={task}|provider={provider}": count for (name, task, provider), count in _metrics.items()}


def _normalize_provider(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    if normalized in {"github", "githubmodel"}:
        return "github_models"
    if normalized in {"azure_openai", "azure-openai", "azureopenai"}:
        return "openai"
    return normalized


def _normalize_task(task: str) -> str:
    normalized = (task or "").strip().lower()
    if normalized not in ALL_TASKS:
        raise ValueError(f"Unsupported LLM task '{task}'. Expected one of: {', '.join(ALL_TASKS)}")
    return normalized


def _get_task_provider(task: str) -> str:
    task = _normalize_task(task)
    override = getattr(settings, f"llm_provider_{task}", "")
    provider = _normalize_provider(override) or _normalize_provider(settings.llm_provider_default)
    if provider not in VALID_PROVIDERS:
        raise ValueError(
            f"Invalid provider '{provider}' for task '{task}'. "
            f"Valid providers: {', '.join(sorted(VALID_PROVIDERS))}"
        )
    return provider


def _get_task_fallback_provider(task: str) -> str | None:
    task = _normalize_task(task)
    fallback = _normalize_provider(getattr(settings, f"llm_fallback_provider_{task}", ""))
    if not fallback:
        return None
    if fallback not in VALID_PROVIDERS:
        raise ValueError(
            f"Invalid fallback provider '{fallback}' for task '{task}'. "
            f"Valid providers: {', '.join(sorted(VALID_PROVIDERS))}"
        )
    return fallback


def _normalize_openai_base_url(raw: str) -> str:
    value = (raw or "").strip()
    return value[:-1] if value.endswith("/") else value


def _get_task_model(provider: str, task: str) -> str:
    task = _normalize_task(task)
    provider = _normalize_provider(provider)

    if provider == "openai":
        if task == EMBEDDING_TASK:
            return (settings.openai_embedding_model or "").strip()
        return (settings.openai_chat_model or "").strip()

    if provider == "groq":
        return (settings.groq_model or "").strip()

    if task == EMBEDDING_TASK:
        return (settings.github_models_embedding_model or "").strip()
    return (settings.github_models_chat_model or "").strip()


def _get_cache_key(provider: str, async_mode: bool, auth_variant: str = "default") -> tuple[str, str]:
    prefix = "async" if async_mode else "sync"
    return (f"{prefix}:{provider}", auth_variant)


def _cached_client(
    provider: str,
    *,
    async_mode: bool = False,
    auth_variant: str = "default",
) -> OpenAI | AsyncOpenAI:
    key = _get_cache_key(provider, async_mode, auth_variant)
    with _client_lock:
        client = _client_cache.get(key)
        if client is not None:
            return client

        client = _build_client(provider, async_mode=async_mode, auth_variant=auth_variant)
        _client_cache[key] = client
        return client


def _build_client(
    provider: str,
    *,
    async_mode: bool = False,
    auth_variant: str = "default",
) -> OpenAI | AsyncOpenAI:
    provider = _normalize_provider(provider)
    client_cls = AsyncOpenAI if async_mode else OpenAI

    if provider == "github_models":
        kwargs = {"base_url": settings.github_models_endpoint, "api_key": settings.github_token}
        return client_cls(**kwargs)

    if provider == "groq":
        kwargs = {"base_url": settings.groq_endpoint, "api_key": settings.groq_api_key}
        return client_cls(**kwargs)

    if provider != "openai":
        raise ValueError(f"Unsupported provider '{provider}'")

    base_url = _normalize_openai_base_url(settings.openai_api_base_url)
    api_key = settings.openai_api_key
    if not api_key:
        raise ValueError("OPENAI_API_KEY is required for provider 'openai'")

    kwargs = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url

    return client_cls(**kwargs)


def resolve_route(task: str) -> RouteSelection:
    task = _normalize_task(task)
    provider = _get_task_provider(task)
    fallback_provider = _get_task_fallback_provider(task)
    model = _get_task_model(provider, task)
    fallback_model = _get_task_model(fallback_provider, task) if fallback_provider else None
    return RouteSelection(
        task=task,
        provider=provider,
        fallback_provider=fallback_provider,
        model=model,
        fallback_model=fallback_model,
        auth_mode=None,
    )


def _looks_like_rate_limit_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "429" in text or "rate limit" in text or "resource_exhausted" in text


async def _call_with_provider(
    *,
    provider: str,
    task: str,
    endpoint: str,
    model: str,
    payload: dict,
    auth_variant: str = "default",
):
    client = _cached_client(provider, async_mode=True, auth_variant=auth_variant)

    if endpoint == "chat.completions":
        return await rate_limited_call(
            client.chat.completions.create,
            model=model,
            provider=provider,
            task=task,
            **payload,
        )

    if endpoint == "embeddings":
        return await rate_limited_call(
            client.embeddings.create,
            model=model,
            provider=provider,
            task=task,
            **payload,
        )

    raise ValueError(f"Unsupported endpoint '{endpoint}'")


def _has_openai_key() -> bool:
    return bool((settings.openai_api_key or "").strip())


async def _call_with_fallbacks(
    *,
    route: RouteSelection,
    endpoint: str,
    payload: dict,
):
    start = time.perf_counter()
    _metric_inc("calls_total", task=route.task, provider=route.provider)
    fallback_used = False

    try:
        response = await _call_with_provider(
            provider=route.provider,
            task=route.task,
            endpoint=endpoint,
            model=route.model,
            payload=payload,
        )
        duration_ms = (time.perf_counter() - start) * 1000.0
        logger.info(
            "LLM call success task=%s provider=%s model=%s latency_ms=%.1f fallback_used=%s",
            route.task,
            route.provider,
            route.model,
            duration_ms,
            fallback_used,
        )
        return response
    except Exception as primary_exc:
        _metric_inc("calls_failed", task=route.task, provider=route.provider)
        if _looks_like_rate_limit_error(primary_exc):
            _metric_inc("rate_limit_errors", task=route.task, provider=route.provider)
        logger.warning(
            "LLM primary call failed task=%s provider=%s model=%s error=%s",
            route.task,
            route.provider,
            route.model,
            primary_exc,
        )

        # OpenAI key safety net: if openai key is missing for primary openai route,
        # still allow task-specific fallback provider to run.
        if route.provider == "openai" and not _has_openai_key():
            logger.warning(
                "LLM provider 'openai' was configured but no OPENAI_API_KEY is present. "
                "Attempting fallback provider."
            )

        # Optional provider fallback (task-specific emergency path)
        if route.fallback_provider:
            try:
                fallback_used = True
                _metric_inc("fallback_used", task=route.task, provider=route.fallback_provider)
                response = await _call_with_provider(
                    provider=route.fallback_provider,
                    task=route.task,
                    endpoint=endpoint,
                    model=route.fallback_model or _get_task_model(route.fallback_provider, route.task),
                    payload=payload,
                )
                duration_ms = (time.perf_counter() - start) * 1000.0
                logger.warning(
                    "LLM call recovered via provider fallback task=%s provider=%s latency_ms=%.1f",
                    route.task,
                    route.fallback_provider,
                    duration_ms,
                )
                return response
            except Exception as fallback_exc:
                _metric_inc("calls_failed", task=route.task, provider=route.fallback_provider)
                logger.error(
                    "LLM provider fallback failed task=%s provider=%s error=%s",
                    route.task,
                    route.fallback_provider,
                    fallback_exc,
                )
                raise fallback_exc from primary_exc

        raise primary_exc


async def task_chat_completion(
    *,
    task: str,
    messages: list[dict[str, str]],
    temperature: float = 0.2,
    max_tokens: int = 400,
    **kwargs,
):
    route = resolve_route(task)
    payload = {
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        **kwargs,
    }
    return await _call_with_fallbacks(route=route, endpoint="chat.completions", payload=payload)


async def task_embedding_create(
    *,
    task: str = EMBEDDING_TASK,
    input: str | list[str] = "",
    **kwargs,
):
    route = resolve_route(task)
    payload = {"input": input, **kwargs}
    return await _call_with_fallbacks(route=route, endpoint="embeddings", payload=payload)


def validate_llm_configuration() -> list[str]:
    """
    Validate task routing and provider configuration at startup.
    Returns list of human-readable errors.
    """
    errors: list[str] = []

    for task in ALL_TASKS:
        try:
            route = resolve_route(task)
        except Exception as exc:
            errors.append(f"task={task}: {exc}")
            continue

        # Primary provider checks
        errors.extend(_validate_provider_config(route.provider, task, route.model))

        # Optional fallback checks
        if route.fallback_provider:
            fallback_model = route.fallback_model or _get_task_model(route.fallback_provider, task)
            errors.extend(_validate_provider_config(route.fallback_provider, task, fallback_model, prefix="fallback"))

    return errors


def _validate_provider_config(provider: str, task: str, model: str, prefix: str = "primary") -> list[str]:
    issues: list[str] = []
    provider = _normalize_provider(provider)

    if not model:
        issues.append(f"{prefix} task={task}: no model configured for provider '{provider}'")

    if provider == "openai":
        if not (settings.openai_api_key or "").strip():
            issues.append(f"{prefix} task={task}: OPENAI_API_KEY is required for provider 'openai'")

    elif provider == "groq":
        if not (settings.groq_api_key or "").strip():
            issues.append(f"{prefix} task={task}: GROQ_API_KEY is required for provider 'groq'")

    elif provider == "github_models":
        if not (settings.github_token or "").strip():
            issues.append(f"{prefix} task={task}: GITHUB_TOKEN is required for provider 'github_models'")
        if not (settings.github_models_endpoint or "").strip():
            issues.append(f"{prefix} task={task}: GITHUB_MODELS_ENDPOINT is required for provider 'github_models'")

    else:
        issues.append(f"{prefix} task={task}: unsupported provider '{provider}'")

    return issues


# Backward-compatible API helpers retained for existing imports.
def create_llm_client() -> OpenAI:
    provider = _get_task_provider("archaeology")
    return _cached_client(provider, async_mode=False)  # type: ignore[return-value]


def create_async_llm_client() -> AsyncOpenAI:
    provider = _get_task_provider("archaeology")
    return _cached_client(provider, async_mode=True)  # type: ignore[return-value]


def get_chat_model() -> str:
    return _get_task_model(_get_task_provider("archaeology"), "archaeology")


def get_embedding_model() -> str:
    return _get_task_model(_get_task_provider("embeddings"), "embeddings")


def create_groq_client() -> OpenAI:
    return _cached_client("groq", async_mode=False)  # type: ignore[return-value]


def get_groq_model() -> str:
    return settings.groq_model
