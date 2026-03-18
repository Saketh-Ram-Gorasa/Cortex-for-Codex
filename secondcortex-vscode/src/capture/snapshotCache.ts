import * as vscode from 'vscode';
import * as fs from 'fs';
import * as path from 'path';
import { BackendClient } from '../backendClient';
import { CapturedSnapshot } from './eventCapture';

/**
 * SnapshotCache – local SQLite-like JSON file cache for offline resilience.
 *
 * When the backend is unreachable, snapshots are written to a local store.
 * On reconnection (or next activation), `flushToBackend()` replays them chronologically.
 *
 * Uses a simple JSON file store to avoid native module/runtime complexity.
 */
export class SnapshotCache {
    private readonly cacheFilePath: string;
    private queue: CapturedSnapshot[] = [];

    constructor(
        storagePath: string,
        private output: vscode.OutputChannel
    ) {
        // Ensure the storage directory exists
        if (!fs.existsSync(storagePath)) {
            fs.mkdirSync(storagePath, { recursive: true });
        }
        this.cacheFilePath = path.join(storagePath, 'offline-snapshots.json');

        // Load any existing cached snapshots from disk
        this.loadFromDisk();
    }

    /** Persist a snapshot locally when the backend is unreachable. */
    store(snapshot: CapturedSnapshot): void {
        this.queue.push(snapshot);
        this.saveToDisk();
        this.output.appendLine(`[SnapshotCache] Cached snapshot (${this.queue.length} total pending).`);
    }

    /**
     * Attempt to flush all cached snapshots to the backend in chronological order.
     * Successfully sent snapshots are removed from the cache.
     */
    async flushToBackend(backend: BackendClient): Promise<void> {
        if (this.queue.length === 0) {
            return;
        }

        this.output.appendLine(`[SnapshotCache] Flushing ${this.queue.length} cached snapshots...`);

        const remaining: CapturedSnapshot[] = [];

        for (const snapshot of this.queue) {
            const success = await backend.sendSnapshot(snapshot as unknown as Record<string, unknown>);
            if (!success) {
                // Stop flushing on first failure — the backend may still be down
                remaining.push(snapshot);
                // Push the rest without trying
                const idx = this.queue.indexOf(snapshot);
                remaining.push(...this.queue.slice(idx + 1));
                break;
            }
        }

        this.queue = remaining;
        this.saveToDisk();

        this.output.appendLine(
            remaining.length === 0
                ? '[SnapshotCache] All offline snapshots flushed successfully.'
                : `[SnapshotCache] ${remaining.length} snapshots still pending.`
        );
    }

    /** Close the cache (write any unsaved data). */
    close(): void {
        this.saveToDisk();
    }

    // ── Private helpers ───────────────────────────────────────────

    private loadFromDisk(): void {
        try {
            if (fs.existsSync(this.cacheFilePath)) {
                const raw = fs.readFileSync(this.cacheFilePath, 'utf-8');
                this.queue = JSON.parse(raw) as CapturedSnapshot[];
                this.output.appendLine(`[SnapshotCache] Loaded ${this.queue.length} cached snapshots from disk.`);
            }
        } catch (err) {
            this.output.appendLine(`[SnapshotCache] Failed to load cache: ${err}`);
            this.queue = [];
        }
    }

    private saveToDisk(): void {
        try {
            fs.writeFileSync(this.cacheFilePath, JSON.stringify(this.queue, null, 2), 'utf-8');
        } catch (err) {
            this.output.appendLine(`[SnapshotCache] Failed to persist cache: ${err}`);
        }
    }
}
