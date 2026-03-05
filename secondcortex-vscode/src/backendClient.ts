import * as vscode from 'vscode';
import { AuthService } from './auth/authService';

/**
 * BackendClient – HTTP client for communicating with the SecondCortex FastAPI backend.
 * Sends an Authorization: Bearer <JWT> header for per-user authentication.
 */
export class BackendClient {
    private auth?: AuthService;

    constructor(
        private baseUrl: string,
        private output: vscode.OutputChannel
    ) { }

    /** Attach the AuthService instance (set after construction). */
    setAuthService(auth: AuthService): void {
        this.auth = auth;
    }

    /** Build common headers including the JWT Bearer token. */
    private async getHeaders(): Promise<Record<string, string>> {
        const headers: Record<string, string> = {
            'Content-Type': 'application/json',
        };
        if (this.auth) {
            const token = await this.auth.getToken();
            if (token) {
                headers['Authorization'] = `Bearer ${token}`;
            }
        }
        return headers;
    }

    /** Handle 401 responses by prompting re-login. */
    private async handle401(): Promise<void> {
        this.output.appendLine('[BackendClient] 401 Unauthorized — token expired or invalid.');
        if (this.auth) {
            await this.auth.clearToken();
        }
        vscode.window.showWarningMessage(
            'SecondCortex session expired. Please log in again.',
            'Log In'
        ).then((choice) => {
            if (choice === 'Log In') {
                vscode.commands.executeCommand('secondcortex.login');
            }
        });
    }

    /**
     * Send a sanitized snapshot to the backend.
     * Returns true on success, false on failure (so caller can cache it locally).
     */
    async sendSnapshot(payload: Record<string, unknown>): Promise<boolean> {
        try {
            const res = await fetch(`${this.baseUrl}/api/v1/snapshot`, {
                method: 'POST',
                headers: await this.getHeaders(),
                body: JSON.stringify(payload),
            });
            if (res.status === 401) {
                await this.handle401();
                return false;
            }
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
            const url = `${this.baseUrl}/api/v1/query`;
            this.output.appendLine(`[BackendClient] POST ${url}`);

            const res = await fetch(url, {
                method: 'POST',
                headers: await this.getHeaders(),
                body: JSON.stringify({ question }),
            });

            if (res.status === 401) {
                await this.handle401();
                return null;
            }
            if (!res.ok) {
                const text = await res.text().catch(() => 'No response body');
                this.output.appendLine(`[BackendClient] Query failed: ${res.status} ${res.statusText}`);
                this.output.appendLine(`[BackendClient] Error details: ${text}`);
                // Parse the error detail if possible
                let errorMsg = `Backend error (${res.status})`;
                try {
                    const errJson = JSON.parse(text);
                    if (errJson.detail) { errorMsg = errJson.detail; }
                } catch { /* not JSON */ }
                return { summary: errorMsg, commands: [], _error: true } as any;
            }
            return (await res.json()) as { summary: string; commands?: unknown[] };
        } catch (err: any) {
            this.output.appendLine(`[BackendClient] Network error querying backend: ${err.message || err}`);
            if (err.stack) {
                this.output.appendLine(`[BackendClient] Stack: ${err.stack}`);
            }
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
                headers: await this.getHeaders(),
                body: JSON.stringify({ target }),
            });
            if (res.status === 401) {
                await this.handle401();
                return null;
            }
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

    /**
     * Fetch persistent chat history for the current user.
     */
    async getChatHistory(): Promise<{ role: string; content: string; timestamp: string }[]> {
        try {
            const res = await fetch(`${this.baseUrl}/api/v1/chat/history`, {
                headers: await this.getHeaders(),
            });
            if (res.status === 401) {
                await this.handle401();
                return [];
            }
            if (!res.ok) return [];
            const data = await res.json() as { messages: any[] };
            return data.messages || [];
        } catch (err) {
            this.output.appendLine(`[BackendClient] Network error fetching chat history: ${err}`);
            return [];
        }
    }

    /**
     * Clear all chat history for the current user.
     */
    async clearChatHistory(): Promise<boolean> {
        try {
            const res = await fetch(`${this.baseUrl}/api/v1/chat/history`, {
                method: 'DELETE',
                headers: await this.getHeaders(),
            });
            if (res.status === 401) {
                await this.handle401();
                return false;
            }
            return res.ok;
        } catch (err) {
            this.output.appendLine(`[BackendClient] Network error clearing chat history: ${err}`);
            return false;
        }
    }
}

