from __future__ import annotations

import asyncio

from services.rate_limiter import rate_limited_call


def test_rate_limited_call_supports_async_callable():
    calls: list[str] = []

    async def async_func(value: str) -> str:
        calls.append(value)
        return f"ok:{value}"

    result = asyncio.run(
        rate_limited_call(
            async_func,
            "x",
            provider="azure_openai",
            task="planner",
            max_retries=0,
        )
    )

    assert result == "ok:x"
    assert calls == ["x"]


def test_rate_limited_call_still_supports_sync_callable():
    def sync_func(value: int) -> int:
        return value + 1

    result = asyncio.run(
        rate_limited_call(
            sync_func,
            2,
            provider="azure_openai",
            task="planner",
            max_retries=0,
        )
    )

    assert result == 3


def test_rate_limited_call_awaits_sync_callable_returning_coroutine():
    async def async_inner(value: str) -> str:
        return f"ok:{value}"

    def wrapper(value: str):
        return async_inner(value)

    result = asyncio.run(
        rate_limited_call(
            wrapper,
            "wrapped",
            provider="azure_openai",
            task="retriever",
            max_retries=0,
        )
    )

    assert result == "ok:wrapped"
