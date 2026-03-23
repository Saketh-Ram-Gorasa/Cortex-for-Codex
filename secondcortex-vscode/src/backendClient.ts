import * as vscode from 'vscode';
import { AuthService } from './auth/authService';

export interface ProjectSummary {
    id: string;
    owner_user_id: string;
    name: string;
    slug: string | null;
    visibility: 'private' | 'team';
    team_id: string | null;
    workspace_name: string | null;
    workspace_path_hash: string | null;
    repo_remote: string | null;
    is_archived: boolean;
    created_at: number;
    updated_at: number;
}

export interface ProjectResolveRequest {
    workspaceName: string;
    workspacePathHash: string;
    repoRemote?: string;
    teamId?: string;
}

export interface ProjectResolveCandidate {
    projectId: string;
    name: string;
    confidence: number;
}

export interface ProjectResolveResponse {
    status: 'resolved' | 'ambiguous' | 'unresolved';
    projectId: string | null;
    confidence: number;
    candidates: ProjectResolveCandidate[];
    needsSelection: boolean;
}

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

    async listProjects(): Promise<ProjectSummary[]> {
        try {
            const res = await fetch(`${this.baseUrl}/api/v1/projects`, {
                method: 'GET',
                headers: await this.getHeaders(),
            });
            if (res.status === 401) {
                await this.handle401();
                return [];
            }
            if (!res.ok) {
                this.output.appendLine(`[BackendClient] List projects failed: ${res.status} ${res.statusText}`);
                return [];
            }
            const data = await res.json() as { projects?: ProjectSummary[] };
            return data.projects || [];
        } catch (err) {
            this.output.appendLine(`[BackendClient] Network error listing projects: ${err}`);
            return [];
        }
    }

    async resolveProject(request: ProjectResolveRequest): Promise<ProjectResolveResponse | null> {
        try {
            const res = await fetch(`${this.baseUrl}/api/v1/projects/resolve`, {
                method: 'POST',
                headers: await this.getHeaders(),
                body: JSON.stringify(request),
            });
            if (res.status === 401) {
                await this.handle401();
                return null;
            }
            if (!res.ok) {
                this.output.appendLine(`[BackendClient] Resolve project failed: ${res.status} ${res.statusText}`);
                return null;
            }
            return (await res.json()) as ProjectResolveResponse;
        } catch (err) {
            this.output.appendLine(`[BackendClient] Network error resolving project: ${err}`);
            return null;
        }
    }

    /**
     * Ask a natural-language question to the Planner agent.
     */
    async askQuestion(question: string, sessionId?: string): Promise<{ summary: string; commands?: unknown[] } | null> {
        try {
            let url = `${this.baseUrl}/api/v1/query`;
            if (sessionId) {
                url += `?session_id=${encodeURIComponent(sessionId)}`;
            }
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
    async getResurrectionPlan(target: string, currentWorkspace?: string): Promise<{ commands: unknown[], planSummary?: string } | null> {
        try {
            const body: any = { target };
            if (currentWorkspace) {
                body.current_workspace = currentWorkspace;
            }

            const res = await fetch(`${this.baseUrl}/api/v1/resurrect`, {
                method: 'POST',
                headers: await this.getHeaders(),
                body: JSON.stringify(body),
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
    async getChatHistory(sessionId?: string): Promise<{ role: string; content: string; timestamp: string }[]> {
        try {
            let url = `${this.baseUrl}/api/v1/chat/history`;
            if (sessionId) {
                url += `?session_id=${encodeURIComponent(sessionId)}`;
            }
            const res = await fetch(url, {
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
     * Fetch list of chat sessions for the current user.
     */
    async getChatSessions(): Promise<{ id: string; title: string; created_at: string }[]> {
        try {
            const res = await fetch(`${this.baseUrl}/api/v1/chat/sessions`, {
                headers: await this.getHeaders(),
            });
            if (res.status === 401) {
                await this.handle401();
                return [];
            }
            if (!res.ok) return [];
            const data = await res.json() as { sessions: any[] };
            return data.sessions || [];
        } catch (err) {
            this.output.appendLine(`[BackendClient] Network error fetching chat sessions: ${err}`);
            return [];
        }
    }

    /**
     * Clear chat history (single session or all).
     */
    async clearChatHistory(sessionId?: string): Promise<boolean> {
        try {
            let url = `${this.baseUrl}/api/v1/chat/history`;
            if (sessionId) {
                url += `?session_id=${encodeURIComponent(sessionId)}`;
            }
            const res = await fetch(url, {
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

    /**
     * Create a new chat session.
     */
    async createChatSession(title: string): Promise<string | null> {
        try {
            const res = await fetch(`${this.baseUrl}/api/v1/chat/sessions`, {
                method: 'POST',
                headers: await this.getHeaders(),
                body: JSON.stringify({ title }),
            });
            if (res.status === 401) {
                await this.handle401();
                return null;
            }
            if (!res.ok) return null;
            const data = await res.json() as { session_id: string };
            return data.session_id;
        } catch (err) {
            this.output.appendLine(`[BackendClient] Network error creating chat session: ${err}`);
            return null;
        }
    }

    /** Fetch linear snapshot timeline for Shadow Graph time-travel UI. */
    async getSnapshotTimeline(limit: number = 200, projectId?: string): Promise<Array<{
        id: string;
        timestamp: string;
        active_file: string;
        git_branch: string | null;
        project_id?: string | null;
        summary: string;
        entities: string[];
    }>> {
        try {
            const projectQuery = projectId ? `&projectId=${encodeURIComponent(projectId)}` : '';
            const res = await fetch(`${this.baseUrl}/api/v1/snapshots/timeline?limit=${encodeURIComponent(limit)}${projectQuery}`, {
                headers: await this.getHeaders(),
            });
            if (res.status === 401) {
                await this.handle401();
                return [];
            }
            if (!res.ok) {
                this.output.appendLine(`[BackendClient] Timeline request failed: ${res.status} ${res.statusText}`);
                return [];
            }

            const data = await res.json() as { timeline?: Array<any> };
            return (data.timeline || []) as Array<{
                id: string;
                timestamp: string;
                active_file: string;
                git_branch: string | null;
                project_id?: string | null;
                summary: string;
                entities: string[];
            }>;
        } catch (err) {
            this.output.appendLine(`[BackendClient] Network error fetching timeline: ${err}`);
            return [];
        }
    }

    /** Fetch one snapshot record by ID. */
    async getSnapshotById(snapshotId: string): Promise<{
        id: string;
        timestamp: string;
        workspace_folder?: string;
        active_file: string;
        git_branch: string | null;
        summary: string;
        entities: string[];
        shadow_graph: string;
        active_symbol?: string;
        function_signatures?: string[];
    } | null> {
        try {
            const res = await fetch(`${this.baseUrl}/api/v1/snapshots/${encodeURIComponent(snapshotId)}`, {
                headers: await this.getHeaders(),
            });
            if (res.status === 401) {
                await this.handle401();
                return null;
            }
            if (res.status === 404) {
                return null;
            }
            if (!res.ok) {
                this.output.appendLine(`[BackendClient] Snapshot lookup failed: ${res.status} ${res.statusText}`);
                return null;
            }
            const data = await res.json() as { snapshot?: any };
            return (data.snapshot || null) as {
                id: string;
                timestamp: string;
                workspace_folder?: string;
                active_file: string;
                git_branch: string | null;
                summary: string;
                entities: string[];
                shadow_graph: string;
            } | null;
        } catch (err) {
            this.output.appendLine(`[BackendClient] Network error fetching snapshot by ID: ${err}`);
            return null;
        }
    }

    /** Request decision archaeology synthesis for a symbol+commit context. */
    async getDecisionArchaeology(payload: {
        filePath: string;
        symbolName: string;
        signature: string;
        commitHash: string;
        commitMessage: string;
        author: string;
        timestamp: string;
        projectId?: string;
    }): Promise<{
        found: boolean;
        summary: string | null;
        branchesTried: string[];
        terminalCommands: string[];
        confidence: number;
    } | null> {
        try {
            const res = await fetch(`${this.baseUrl}/api/v1/decision-archaeology`, {
                method: 'POST',
                headers: await this.getHeaders(),
                body: JSON.stringify(payload),
            });
            if (res.status === 401) {
                await this.handle401();
                return null;
            }
            if (!res.ok) {
                this.output.appendLine(`[BackendClient] Decision archaeology failed: ${res.status} ${res.statusText}`);
                return null;
            }
            return (await res.json()) as {
                found: boolean;
                summary: string | null;
                branchesTried: string[];
                terminalCommands: string[];
                confidence: number;
            };
        } catch (err) {
            this.output.appendLine(`[BackendClient] Network error fetching decision archaeology: ${err}`);
            return null;
        }
    }
}
