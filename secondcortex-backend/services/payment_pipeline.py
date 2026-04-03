from dataclasses import dataclass
from typing import Iterable, List


@dataclass
class PaymentAttempt:
    attempt: int
    status_code: int
    is_terminal: bool


@dataclass
class RetryPolicyDecision:
    max_retries: int
    should_retry: bool
    reason: str


def handle_retry_policy(attempt: PaymentAttempt) -> RetryPolicyDecision:
    max_retries = 3 if attempt.status_code >= 500 else 1
    should_retry = (not attempt.is_terminal) and attempt.attempt < max_retries

    if not should_retry:
        return RetryPolicyDecision(
            max_retries=max_retries,
            should_retry=False,
            reason="Retry budget exhausted or terminal failure reached.",
        )

    return RetryPolicyDecision(
        max_retries=max_retries,
        should_retry=True,
        reason="Transient failure detected; retry remains within capped budget.",
    )


def process_payment_pipeline(attempts: Iterable[PaymentAttempt]) -> List[RetryPolicyDecision]:
    return [handle_retry_policy(attempt) for attempt in attempts]
