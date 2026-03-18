import * as vscode from 'vscode';

/**
 * AuthService – manages JWT-based authentication for SecondCortex.
 * 
 * Stores tokens securely using VS Code's SecretStorage API (encrypted,
 * per-user, never in plaintext settings).
 */
export class AuthService {
    private static readonly TOKEN_KEY = 'secondcortex.jwt';
    private static readonly USER_KEY = 'secondcortex.user';

    constructor(
        private readonly secrets: vscode.SecretStorage,
        private readonly output: vscode.OutputChannel,
        private readonly backendUrl: string
    ) { }

    // ── Token Storage ──────────────────────────────────────────────

    async getToken(): Promise<string | undefined> {
        return this.secrets.get(AuthService.TOKEN_KEY);
    }

    async setToken(token: string): Promise<void> {
        await this.secrets.store(AuthService.TOKEN_KEY, token);
    }

    async clearToken(): Promise<void> {
        await this.secrets.delete(AuthService.TOKEN_KEY);
        await this.secrets.delete(AuthService.USER_KEY);
    }

    async getUser(): Promise<{ userId: string; email: string; displayName: string; teamId?: string | null } | undefined> {
        const raw = await this.secrets.get(AuthService.USER_KEY);
        if (!raw) { return undefined; }
        try {
            return JSON.parse(raw);
        } catch {
            return undefined;
        }
    }

    async setUser(userId: string, email: string, displayName: string, teamId?: string | null): Promise<void> {
        await this.secrets.store(AuthService.USER_KEY, JSON.stringify({ userId, email, displayName, teamId: teamId ?? null }));
    }

    async isLoggedIn(): Promise<boolean> {
        const token = await this.getToken();
        return !!token;
    }

    // ── Auth API Calls ─────────────────────────────────────────────

    async signup(email: string, password: string, displayName: string): Promise<{ success: boolean; error?: string }> {
        try {
            const res = await fetch(`${this.backendUrl}/api/v1/auth/signup`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password, display_name: displayName }),
            });

            if (!res.ok) {
                const body = await res.json().catch(() => ({ detail: 'Signup failed' })) as { detail?: string };
                return { success: false, error: body.detail || `Signup failed (${res.status})` };
            }

            const data = await res.json() as { token: string; user_id: string; email: string; display_name: string; team_id?: string | null };
            await this.setToken(data.token);
            await this.setUser(data.user_id, data.email, data.display_name, data.team_id ?? null);
            this.output.appendLine(`[Auth] Signed up as ${data.email}`);
            return { success: true };
        } catch (err) {
            this.output.appendLine(`[Auth] Signup network error: ${err}`);
            return { success: false, error: 'Network error — is the backend reachable?' };
        }
    }

    async login(email: string, password: string): Promise<{ success: boolean; error?: string }> {
        try {
            const res = await fetch(`${this.backendUrl}/api/v1/auth/login`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password }),
            });

            if (!res.ok) {
                const body = await res.json().catch(() => ({ detail: 'Login failed' })) as { detail?: string };
                return { success: false, error: body.detail || `Login failed (${res.status})` };
            }

            const data = await res.json() as { token: string; user_id: string; email: string; display_name: string; team_id?: string | null };
            await this.setToken(data.token);
            await this.setUser(data.user_id, data.email, data.display_name, data.team_id ?? null);
            this.output.appendLine(`[Auth] Logged in as ${data.email}`);
            return { success: true };
        } catch (err) {
            this.output.appendLine(`[Auth] Login network error: ${err}`);
            return { success: false, error: 'Network error — is the backend reachable?' };
        }
    }

    async logout(): Promise<void> {
        await this.clearToken();
        this.output.appendLine('[Auth] Logged out.');
    }

    async getUserId(): Promise<string | undefined> {
        const user = await this.getUser();
        return user?.userId;
    }
}
