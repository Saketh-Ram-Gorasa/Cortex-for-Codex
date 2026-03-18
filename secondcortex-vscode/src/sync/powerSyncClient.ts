import * as fs from 'fs';
import * as path from 'path';
import Database from 'better-sqlite3';
import * as vscode from 'vscode';
import { BackendClient } from '../backendClient';

export interface PowerSyncSnapshotRow {
    id: string;
    user_id: string;
    team_id: string | null;
    workspace: string;
    active_file: string;
    git_branch: string | null;
    terminal_commands: string;
    summary: string;
    enriched_context: string;
    timestamp: number;
    synced: number;
}

export interface SyncStatus {
    state: 'synced' | 'syncing' | 'offline';
    pending: number;
}

export class PowerSyncClient {
    private readonly dbPath: string;
    private readonly db: any;

    constructor(
        storagePath: string,
        private readonly backend: BackendClient,
        private readonly output: vscode.OutputChannel,
        private readonly onStatus?: (status: SyncStatus) => void,
    ) {
        if (!fs.existsSync(storagePath)) {
            fs.mkdirSync(storagePath, { recursive: true });
        }

        this.dbPath = path.join(storagePath, 'powersync-local.db');
        this.db = new Database(this.dbPath);
        this.initSchema();
        this.emitStatus(this.getPendingCount() > 0 ? 'offline' : 'synced');
    }

    buildRow(params: {
        id: string;
        userId: string;
        teamId: string | null;
        workspace: string;
        activeFile: string;
        gitBranch: string | null;
        terminalCommands: string[];
        summary: string;
        enrichedContext: string;
        timestampMs: number;
    }): PowerSyncSnapshotRow {
        return {
            id: params.id,
            user_id: params.userId,
            team_id: params.teamId,
            workspace: params.workspace,
            active_file: params.activeFile,
            git_branch: params.gitBranch,
            terminal_commands: JSON.stringify(params.terminalCommands || []),
            summary: params.summary,
            enriched_context: params.enrichedContext || '{}',
            timestamp: params.timestampMs,
            synced: 0,
        };
    }

    storeSnapshot(row: PowerSyncSnapshotRow): void {
        const stmt = this.db.prepare(`
            INSERT OR REPLACE INTO snapshots (
                id, user_id, team_id, workspace, active_file, git_branch,
                terminal_commands, summary, enriched_context, timestamp, synced
            ) VALUES (
                @id, @user_id, @team_id, @workspace, @active_file, @git_branch,
                @terminal_commands, @summary, @enriched_context, @timestamp, @synced
            )
        `);
        stmt.run(row);
        this.output.appendLine(`[PowerSync] Snapshot ${row.id} stored locally.`);
        this.emitStatus('offline');
    }

    async syncPending(limit: number = 200): Promise<boolean> {
        const pending = this.getPendingRows(limit);
        if (pending.length === 0) {
            this.emitStatus('synced');
            return true;
        }

        this.emitStatus('syncing');

        try {
            const auth = await this.backend.getSyncAuth();
            if (!auth?.token) {
                this.output.appendLine('[PowerSync] Missing sync token.');
                this.emitStatus('offline');
                return false;
            }

            const result = await this.backend.putSyncRows(pending, auth.token);
            if (!result.success) {
                this.output.appendLine(`[PowerSync] Sync upload failed (${result.status}).`);
                this.emitStatus('offline');
                return false;
            }

            const accepted = new Set(result.syncedIds || []);
            if (accepted.size > 0) {
                this.markSynced(Array.from(accepted));
            }

            const remaining = this.getPendingCount();
            if (remaining === 0) {
                this.emitStatus('synced');
                this.output.appendLine('[PowerSync] Local queue fully synced.');
                return true;
            }

            this.output.appendLine(`[PowerSync] Partial sync. ${remaining} pending.`);
            this.emitStatus('offline');
            return false;
        } catch (err) {
            this.output.appendLine(`[PowerSync] Sync exception: ${err}`);
            this.emitStatus('offline');
            return false;
        }
    }

    markSynced(ids: string[]): void {
        if (ids.length === 0) {
            return;
        }
        const stmt = this.db.prepare('UPDATE snapshots SET synced = 1 WHERE id = ?');
        const tx = this.db.transaction((input: string[]) => {
            for (const id of input) {
                stmt.run(id);
            }
        });
        tx(ids);
        this.emitStatus(this.getPendingCount() === 0 ? 'synced' : 'offline');
    }

    getPendingCount(): number {
        const row = this.db.prepare('SELECT COUNT(1) as c FROM snapshots WHERE synced = 0').get() as { c: number };
        return row.c || 0;
    }

    close(): void {
        this.db.close();
    }

    private initSchema(): void {
        this.db.exec(`
            CREATE TABLE IF NOT EXISTS snapshots (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                team_id TEXT,
                workspace TEXT NOT NULL,
                active_file TEXT NOT NULL,
                git_branch TEXT,
                terminal_commands TEXT NOT NULL,
                summary TEXT NOT NULL,
                enriched_context TEXT NOT NULL DEFAULT '{}',
                timestamp INTEGER NOT NULL,
                synced INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_snapshots_synced_timestamp
            ON snapshots (synced, timestamp DESC);
        `);

        const existingColumns = this.db
            .prepare('PRAGMA table_info(snapshots)')
            .all()
            .map((c: { name: string }) => c.name);

        if (!existingColumns.includes('enriched_context')) {
            this.db.exec("ALTER TABLE snapshots ADD COLUMN enriched_context TEXT NOT NULL DEFAULT '{}';");
        }
    }

    private getPendingRows(limit: number): PowerSyncSnapshotRow[] {
        const stmt = this.db.prepare(`
            SELECT id, user_id, team_id, workspace, active_file, git_branch,
                   terminal_commands, summary, enriched_context, timestamp, synced
            FROM snapshots
            WHERE synced = 0
            ORDER BY timestamp ASC
            LIMIT ?
        `);
        return stmt.all(limit) as PowerSyncSnapshotRow[];
    }

    private emitStatus(state: SyncStatus['state']): void {
        const status: SyncStatus = {
            state,
            pending: this.getPendingCount(),
        };
        this.onStatus?.(status);
    }
}
