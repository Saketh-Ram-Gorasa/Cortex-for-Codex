/**
 * Debouncer – Prevents context noise by only emitting events after sustained activity.
 *
 * Rules (from System Design):
 *   - A file is only logged after 30s of active typing/scrolling.
 *   - If the file is closed within 10s, it is ignored as noise.
 */
export class Debouncer {
    /** Maps filePath → setTimeout handle for the sustained-activity timer */
    private activeTimers = new Map<string, ReturnType<typeof setTimeout>>();
    /** Maps filePath → timestamp when the file was first opened/touched */
    private openTimestamps = new Map<string, number>();

    constructor(
        /** Duration of sustained activity before a snapshot fires (default 30 000 ms) */
        private readonly sustainedDelayMs: number = 30_000,
        /** Minimum time a file must stay open to not be treated as noise (default 10 000 ms) */
        private readonly noiseThresholdMs: number = 10_000
    ) { }

    /**
     * Called every time the user interacts with a file (opens it, types in it, scrolls).
     * When the sustained delay elapses without `cancel`, the `onReady` callback fires.
     */
    touch(filePath: string, onReady: () => void): void {
        // Record the first-open timestamp only once
        if (!this.openTimestamps.has(filePath)) {
            this.openTimestamps.set(filePath, Date.now());
        }

        // Reset the debounce timer on each interaction
        const existing = this.activeTimers.get(filePath);
        if (existing) {
            clearTimeout(existing);
        }

        const timer = setTimeout(() => {
            this.activeTimers.delete(filePath);
            this.openTimestamps.delete(filePath);
            onReady();
        }, this.sustainedDelayMs);

        this.activeTimers.set(filePath, timer);
    }

    /**
     * Cancel tracking for a file (e.g., the file was closed).
     * If the file was open for less than the noise threshold, it is silently dropped.
     * Returns `true` if the file was still interesting (above noise threshold).
     */
    cancel(filePath: string): boolean {
        const timer = this.activeTimers.get(filePath);
        if (timer) {
            clearTimeout(timer);
            this.activeTimers.delete(filePath);
        }

        const openedAt = this.openTimestamps.get(filePath);
        this.openTimestamps.delete(filePath);

        if (openedAt && Date.now() - openedAt < this.noiseThresholdMs) {
            // File was closed too quickly — noise.
            return false;
        }
        return true;
    }

    /** Clean up all timers (extension deactivation). */
    dispose(): void {
        for (const timer of this.activeTimers.values()) {
            clearTimeout(timer);
        }
        this.activeTimers.clear();
        this.openTimestamps.clear();
    }
}
