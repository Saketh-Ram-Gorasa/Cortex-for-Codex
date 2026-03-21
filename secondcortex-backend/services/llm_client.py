"""
Task-aware LLM routing and client factory utilities.

Supports:
  - Azure OpenAI v1 (managed identity / key / managed_identity_then_key)
  - GitHub Models
  - Groq

Also provides emergency per-task fallback routing for safe cutovers.
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

try:
    from azure.identity import DefaultAzureCredential, get_bearer_token_provider
except Exception:  # pragma: no cover - exercised in environments without azure-identity installed
    DefaultAzureCredential = None
    get_bearer_token_provider = None

logger = logging.getLogger("secondcortex.llm")

VALID_PROVIDERS = {"azure_openai", "github_models", "groq"}
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
    if normalized in {"azure", "azureopenai"}:
        return "azure_openai"
    if normalized in {"github", "githubmodel"}:
        return "github_models"
    return normalized


def _normalize_task(task: str) -> str:
    normalized = (task or "").strip().lower()
    if normalized not in ALL_TASKS:
        raise ValueError(f"Unsupported LLM task '{task}'. Expected one of: {', '.join(ALL_TASKS)}")
    return normalized


def _normalize_azure_base_url(raw: str) -> str:
    value = (raw or "").strip().rstrip("/")
    if not value:
        return ""

    # Legacy endpoint input: https://<resource>.openai.azure.com/
    if value.endswith(".openai.azure.com"):
        return f"{value}/openai/v1/"

    # Legacy style with /openai but missing /v1
    if value.endswith("/openai"):
        return f"{value}/v1/"

    # Already v1 style
    if value.endswith("/openai/v1"):
        return f"{value}/"

    if value.endswith("/openai/v1/"):
        return value

    # Last-resort compatibility for users passing raw host or partial path.
    if "openai.azure.com" in value and "/openai/v1" not in value:
        return f"{value}/openai/v1/"

    return value if value.endswith("/") else f"{value}/"


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


def _get_azure_task_deployment(task: str) -> str:
    task = _normalize_task(task)

    # Task-specific override takes precedence.
    task_value = (getattr(settings, f"azure_openai_deployment_{task}", "") or "").strip()
    if task_value:
        return task_value

    # Fallbacks by capability type.
    if task == EMBEDDING_TASK:
        return (settings.azure_openai_deployment_embeddings or settings.azure_openai_embedding_deployment or "").strip()

    return (settings.azure_openai_deployment or "").strip()


def _get_task_model(provider: str, task: str) -> str:
    task = _normalize_task(task)
    provider = _normalize_provider(provider)

    if provider == "azure_openai":
        return _get_azure_task_deployment(task)

    if provider == "groq":
        return (settings.groq_model or "").strip()

    # github_models
    if task == EMBEDDING_TASK:
        return (settings.github_models_embedding_model or "").strip()
    return (settings.github_models_chat_model or "").strip()


def _is_azure_auth_mode(value: str) -> bool:
    return value in {"managed_identity", "key", "managed_identity_then_key"}


def _get_azure_auth_mode() -> str:
    mode = (settings.azure_openai_auth_mode or "").strip().lower()
    if not _is_azure_auth_mode(mode):
        raise ValueError(
            f"Invalid AZURE_OPENAI_AUTH_MODE='{settings.azure_openai_auth_mode}'. "
            "Expected one of: managed_identity, key, managed_identity_then_key"
        )
    return mode


def _create_azure_token_provider():
    if DefaultAzureCredential is None or get_bearer_token_provider is None:
        raise RuntimeError("azure-identity is required for managed identity auth but is not installed.")

    kwargs = {}
    if settings.azure_openai_client_id:
        kwargs["managed_identity_client_id"] = settings.azure_openai_client_id
    credential = DefaultAzureCredential(**kwargs)
    return get_bearer_token_provider(credential, settings.azure_openai_token_scope)


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
        return client_cls(
            base_url=settings.github_models_endpoint,
            api_key=settings.github_token,
        )

    if provider == "groq":
        return client_cls(
            base_url=settings.groq_endpoint,
            api_key=settings.groq_api_key,
        )

    if provider != "azure_openai":
        raise ValueError(f"Unsupported provider '{provider}'")

    base_url = _normalize_azure_base_url(settings.azure_openai_base_url)
    mode = _get_azure_auth_mode()

    if auth_variant == "key":
        return client_cls(base_url=base_url, api_key=settings.azure_openai_api_key)

    if mode == "key":
        return client_cls(base_url=base_url, api_key=settings.azure_openai_api_key)

    # managed_identity OR managed_identity_then_key use token provider as primary.
    token_provider = _create_azure_token_provider()
    return client_cls(base_url=base_url, api_key=token_provider)


def resolve_route(task: str) -> RouteSelection:
    task = _normalize_task(task)
    provider = _get_task_provider(task)
    fallback_provider = _get_task_fallback_provider(task)
    model = _get_task_model(provider, task)
    fallback_model = _get_task_model(fallback_provider, task) if fallback_provider else None
    auth_mode = _get_azure_auth_mode() if provider == "azure_openai" else None
    return RouteSelection(
        task=task,
        provider=provider,
        fallback_provider=fallback_provider,
        model=model,
        fallback_model=fallback_model,
        auth_mode=auth_mode,
    )


def _looks_like_auth_error(exc: Exception) -> bool:
    text = str(exc).lower()
    auth_markers = (
        "401",
        "403",
        "unauthorized",
        "forbidden",
        "authentication",
        "token",
        "credential",
        "aadsts",
        "managed identity",
    )
    return any(marker in text for marker in auth_markers)


def _looks_like_rate_limit_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "429" in text or "rate limit" in text or "resource_exhausted" in text


def _looks_like_not_found_error(exc: Exception) -> bool:
    text = str(exc).lower()
    not_found_markers = (
        "404",
        "resource not found",
        "deploymentnotfound",
        "not_found",
    )
    return any(marker in text for marker in not_found_markers)


def _get_azure_alternate_models(task: str, primary_model: str) -> list[str]:
    task = _normalize_task(task)
    primary = (primary_model or "").strip()

    candidates: list[str] = []

    if task == EMBEDDING_TASK:
        candidates.extend(
            [
                (settings.azure_openai_deployment_embeddings or "").strip(),
                (settings.azure_openai_embedding_deployment or "").strip(),
            ]
        )
    else:
        candidates.extend(
            [
                (settings.azure_openai_deployment or "").strip(),
                "gpt-4o",
            ]
        )

    deduped: list[str] = []
    for model in candidates:
        if model and model != primary and model not in deduped:
            deduped.append(model)
    return deduped


async def _call_with_provider(
    *,
    provider: str,
    task: str,
    endpoint: str,
    model: str,
    payload: dict,
    auth_variant: str = "default",
):
    client = _cached_client(provider, async_mode=False, auth_variant=auth_variant)

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


def _has_azure_key() -> bool:
    return bool((settings.azure_openai_api_key or "").strip())


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

        # Azure model/deployment fallback: retry on 404 with alternate configured deployment names.
        if route.provider == "azure_openai" and _looks_like_not_found_error(primary_exc):
            alternate_models = _get_azure_alternate_models(route.task, route.model)
            for alternate_model in alternate_models:
                try:
                    fallback_used = True
                    _metric_inc("fallback_used", task=route.task, provider=route.provider)
                    response = await _call_with_provider(
                        provider=route.provider,
                        task=route.task,
                        endpoint=endpoint,
                        model=alternate_model,
                        payload=payload,
                    )
                    duration_ms = (time.perf_counter() - start) * 1000.0
                    logger.warning(
                        "LLM call recovered via Azure deployment fallback task=%s primary_model=%s fallback_model=%s latency_ms=%.1f",
                        route.task,
                        route.model,
                        alternate_model,
                        duration_ms,
                    )
                    return response
                except Exception as alt_exc:
                    logger.warning(
                        "LLM Azure deployment fallback failed task=%s fallback_model=%s error=%s",
                        route.task,
                        alternate_model,
                        alt_exc,
                    )

        # Azure auth fallback: managed identity -> key for auth failures.
        if (
            route.provider == "azure_openai"
            and route.auth_mode == "managed_identity_then_key"
            and _has_azure_key()
            and _looks_like_auth_error(primary_exc)
        ):
            try:
                fallback_used = True
                _metric_inc("fallback_used", task=route.task, provider=route.provider)
                response = await _call_with_provider(
                    provider=route.provider,
                    task=route.task,
                    endpoint=endpoint,
                    model=route.model,
                    payload=payload,
                    auth_variant="key",
                )
                duration_ms = (time.perf_counter() - start) * 1000.0
                logger.warning(
                    "LLM call recovered via Azure key fallback task=%s model=%s latency_ms=%.1f",
                    route.task,
                    route.model,
                    duration_ms,
                )
                return response
            except Exception as key_exc:
                logger.error(
                    "LLM Azure key fallback failed task=%s model=%s error=%s",
                    route.task,
                    route.model,
                    key_exc,
                )

        # Provider fallback (task-specific emergency rollback path).
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
        issues.append(f"{prefix} task={task}: no model/deployment configured for provider '{provider}'")

    if provider == "azure_openai":
        base_url = _normalize_azure_base_url(settings.azure_openai_base_url)
        if not base_url:
            issues.append(f"{prefix} task={task}: AZURE_OPENAI_BASE_URL or AZURE_OPENAI_ENDPOINT is required")

        mode = (settings.azure_openai_auth_mode or "").strip().lower()
        if not _is_azure_auth_mode(mode):
            issues.append(
                f"{prefix} task={task}: invalid AZURE_OPENAI_AUTH_MODE='{settings.azure_openai_auth_mode}'"
            )
        elif mode == "key":
            if not _has_azure_key():
                issues.append(f"{prefix} task={task}: AZURE_OPENAI_API_KEY is required for auth mode 'key'")
        elif mode == "managed_identity":
            if DefaultAzureCredential is None or get_bearer_token_provider is None:
                issues.append(f"{prefix} task={task}: azure-identity package is required for managed identity mode")
        elif mode == "managed_identity_then_key":
            if DefaultAzureCredential is None or get_bearer_token_provider is None:
                issues.append(
                    f"{prefix} task={task}: azure-identity package is required for managed_identity_then_key mode"
                )
            if not _has_azure_key():
                issues.append(
                    f"{prefix} task={task}: AZURE_OPENAI_API_KEY should be set for managed_identity_then_key fallback"
                )

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
