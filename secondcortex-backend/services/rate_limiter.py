"""
Provider-aware rate limiting and retry wrapper for LLM API calls.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import time
from dataclasses import dataclass

from config import settings

logger = logging.getLogger("secondcortex.rate_limiter")


@dataclass
class RateLimitPolicy:
    calls_per_minute: int
    max_retries: int


class RateLimiter:
    """Async-safe token bucket limiter with retry metadata."""

    def __init__(self, policy: RateLimitPolicy, key: str) -> None:
        self.policy = policy
        self.key = key
        self._call_timestamps: list[float] = []
        self._lock = asyncio.Lock()

    def _cleanup_old_timestamps(self) -> None:
        cutoff = time.time() - 60.0
        self._call_timestamps = [t for t in self._call_timestamps if t > cutoff]

    async def wait_if_needed(self) -> None:
        wait_time = 0.0
        async with self._lock:
            self._cleanup_old_timestamps()
            if len(self._call_timestamps) >= self.policy.calls_per_minute:
                oldest = self._call_timestamps[0]
                wait_time = max(0.0, 60.0 - (time.time() - oldest) + 0.5)
                if wait_time > 0:
                    logger.warning(
                        "Rate limit reached key=%s calls=%d/%d wait_s=%.1f",
                        self.key,
                        len(self._call_timestamps),
                        self.policy.calls_per_minute,
                        wait_time,
                    )

        if wait_time > 0:
            await asyncio.sleep(wait_time)

        async with self._lock:
            self._cleanup_old_timestamps()
            self._call_timestamps.append(time.time())

    async def record_429(self) -> None:
        async with self._lock:
            logger.warning("429 received key=%s. Entering cooldown window.", self.key)
            self._call_timestamps = [time.time()] * self.policy.calls_per_minute


_limiters: dict[str, RateLimiter] = {}
_registry_lock = asyncio.Lock()


def _get_calls_per_minute_for_provider(provider: str) -> int:
    normalized = (provider or "").strip().lower()
    if normalized == "groq":
        return max(1, settings.llm_rate_limit_groq_per_minute)
    if normalized == "openai":
        return max(1, settings.llm_rate_limit_openai_per_minute)
    if normalized == "github_models":
        return max(1, settings.llm_rate_limit_github_models_per_minute)
    return max(1, settings.llm_rate_limit_default_per_minute)


def _build_policy(provider: str, max_retries: int | None) -> RateLimitPolicy:
    return RateLimitPolicy(
        calls_per_minute=_get_calls_per_minute_for_provider(provider),
        max_retries=settings.llm_rate_limit_max_retries if max_retries is None else max_retries,
    )


def _get_limiter_key(provider: str, task: str) -> str:
    p = (provider or "default").strip().lower() or "default"
    t = (task or "general").strip().lower() or "general"
    return f"{p}:{t}"


async def get_rate_limiter(
    provider: str = "default",
    task: str = "general",
    *,
    max_retries: int | None = None,
) -> RateLimiter:
    key = _get_limiter_key(provider, task)
    existing = _limiters.get(key)
    if existing is not None:
        return existing

    async with _registry_lock:
        existing = _limiters.get(key)
        if existing is not None:
            return existing
        limiter = RateLimiter(policy=_build_policy(provider, max_retries), key=key)
        _limiters[key] = limiter
        return limiter


def _looks_like_rate_limit_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "429" in text or "resource_exhausted" in text or "rate limit" in text


def _looks_like_hard_quota_error(exc: Exception) -> bool:
    text = str(exc).lower()
    hard_limit_markers = (
        "limit: 0",
        "insufficient_quota",
        "quota exceeded",
        "quota has been exhausted",
    )
    return any(marker in text for marker in hard_limit_markers)


async def rate_limited_call(
    func,
    *args,
    provider: str = "default",
    task: str = "general",
    max_retries: int | None = None,
    **kwargs,
):
    """
    Execute sync API function in a worker thread with provider/task rate limiting.
    Retries are only applied for 429/rate-limit style failures.
    """
    limiter = await get_rate_limiter(provider, task, max_retries=max_retries)

    for attempt in range(limiter.policy.max_retries + 1):
        await limiter.wait_if_needed()
        try:
            if inspect.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            result = await asyncio.to_thread(func, *args, **kwargs)
            if inspect.isawaitable(result):
                return await result
            return result
        except Exception as exc:
            if not _looks_like_rate_limit_error(exc):
                raise

            await limiter.record_429()

            if _looks_like_hard_quota_error(exc):
                logger.error(
                    "Hard quota exhaustion provider=%s task=%s. Failing fast. error=%s",
                    provider,
                    task,
                    exc,
                )
                raise

            if attempt >= limiter.policy.max_retries:
                logger.error(
                    "Rate-limit retries exhausted provider=%s task=%s attempts=%d error=%s",
                    provider,
                    task,
                    limiter.policy.max_retries + 1,
                    exc,
                )
                raise

            backoff_seconds = (attempt + 1) * 5
            logger.warning(
                "Rate-limited provider=%s task=%s attempt=%d/%d retry_in=%ds",
                provider,
                task,
                attempt + 1,
                limiter.policy.max_retries + 1,
                backoff_seconds,
            )
            await asyncio.sleep(backoff_seconds)

    # Defensive fallback; loop always returns or raises.
    raise RuntimeError("rate_limited_call reached unreachable state")
