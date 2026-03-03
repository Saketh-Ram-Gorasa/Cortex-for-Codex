import * as vscode from 'vscode';

/**
 * BackendClient – HTTP client for communicating with the SecondCortex Azure FastAPI backend.
 */
export class BackendClient {
    constructor(
        private baseUrl: string,
        private output: vscode.OutputChannel
    ) { }

    /**
     * Send a sanitized snapshot to the backend.
     * Returns true on success, false on failure (so caller can cache it locally).
     */
    async sendSnapshot(payload: Record<string, unknown>): Promise<boolean> {
        try {
            const res = await fetch(`${this.baseUrl}/api/v1/snapshot`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            if (!res.ok) {
                this.output.appendLine(`[BackendClient] Snapshot upload failed: ${res.status} ${res.statusText}`);
                return false;
            }
            this.output.appendLine('[BackendClient] Snapshot uploaded successfully.');
            return true;
        } catch (err) {
            this.output.appendLine(`[BackendClient] Network error sending snapshot: ${err}`);
            return false;
        }
    }

    /**
     * Ask a natural-language question to the Planner agent.
     */
    async askQuestion(question: string): Promise<{ summary: string; commands?: unknown[] } | null> {
        try {
            const res = await fetch(`${this.baseUrl}/api/v1/query`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ question }),
            });
            if (!res.ok) {
                this.output.appendLine(`[BackendClient] Query failed: ${res.status}`);
                return null;
            }
            return (await res.json()) as { summary: string; commands?: unknown[] };
        } catch (err) {
            this.output.appendLine(`[BackendClient] Network error querying backend: ${err}`);
            return null;
        }
    }

    /**
     * Request a workspace resurrection plan from the backend.
     */
    async getResurrectionPlan(target: string): Promise<{ commands: unknown[] } | null> {
        try {
            const res = await fetch(`${this.baseUrl}/api/v1/resurrect`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ target }),
            });
            if (!res.ok) {
                this.output.appendLine(`[BackendClient] Resurrection request failed: ${res.status}`);
                return null;
            }
            return (await res.json()) as { commands: unknown[] };
        } catch (err) {
            this.output.appendLine(`[BackendClient] Network error requesting resurrection: ${err}`);
            return null;
        }
    }
}
