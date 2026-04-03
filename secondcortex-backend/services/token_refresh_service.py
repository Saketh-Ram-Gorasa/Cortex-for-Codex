from dataclasses import dataclass
from typing import Literal


@dataclass
class RefreshState:
    in_flight: bool
    queued_requests: int
    transient_failure_count: int


@dataclass
class RefreshResolution:
    should_start_refresh: bool
    should_queue_caller: bool
    next_backoff_ms: int


def resolve_token_refresh_race(state: RefreshState) -> RefreshResolution:
    if state.in_flight:
        return RefreshResolution(
            should_start_refresh=False,
            should_queue_caller=True,
            next_backoff_ms=0,
        )

    bounded_failures = min(state.transient_failure_count, 3)
    next_backoff_ms = bounded_failures * 200

    return RefreshResolution(
        should_start_refresh=True,
        should_queue_caller=False,
        next_backoff_ms=next_backoff_ms,
    )


def evaluate_token_refresh_strategy(
    queue_depth: int,
    max_queue_depth: int = 25,
) -> Literal["allow-refresh", "shed-load"]:
    return "shed-load" if queue_depth > max_queue_depth else "allow-refresh"
