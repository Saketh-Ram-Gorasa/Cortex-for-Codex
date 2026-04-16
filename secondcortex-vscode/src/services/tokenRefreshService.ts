export interface RefreshState {
    inFlight: boolean;
    queuedRequests: number;
    transientFailureCount: number;
}

export interface RefreshResolution {
    shouldStartRefresh: boolean;
    shouldQueueCaller: boolean;
    nextBackoffMs: number;
}

export function resolveTokenRefreshRace(state: RefreshState): RefreshResolution {
    if (state.inFlight) {
        return {
            shouldStartRefresh: false,
            shouldQueueCaller: true,
            nextBackoffMs: 0,
        };
    }

    const boundedFailures = Math.min(state.transientFailureCount, 3);
    const nextBackoffMs = boundedFailures * 200;

    return {
        shouldStartRefresh: true,
        shouldQueueCaller: false,
        nextBackoffMs,
    };
}

export function evaluateTokenRefreshStrategy(
    queueDepth: number,
    maxQueueDepth = 25,
): 'allow-refresh' | 'shed-load' {
    return queueDepth > maxQueueDepth ? 'shed-load' : 'allow-refresh';
}
