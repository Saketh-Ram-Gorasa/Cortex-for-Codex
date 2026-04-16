export interface PaymentAttempt {
    attempt: number;
    statusCode: number;
    isTerminal: boolean;
}

export interface RetryPolicyDecision {
    maxRetries: number;
    shouldRetry: boolean;
    reason: string;
}

export function handleRetryPolicy(attempt: PaymentAttempt): RetryPolicyDecision {
    const maxRetries = attempt.statusCode >= 500 ? 3 : 1;
    const shouldRetry = !attempt.isTerminal && attempt.attempt < maxRetries;

    if (!shouldRetry) {
        return {
            maxRetries,
            shouldRetry: false,
            reason: 'Retry budget exhausted or terminal failure reached.',
        };
    }

    return {
        maxRetries,
        shouldRetry: true,
        reason: 'Transient failure detected; retry remains within capped budget.',
    };
}

export function processPaymentPipeline(attempts: PaymentAttempt[]): RetryPolicyDecision[] {
    return attempts.map((attempt) => handleRetryPolicy(attempt));
}
