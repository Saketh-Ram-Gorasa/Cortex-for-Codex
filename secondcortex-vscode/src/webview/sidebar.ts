import * as vscode from 'vscode';
import { BackendClient } from '../backendClient';
import { AuthService } from '../auth/authService';

/**
 * SidebarProvider – renders a Webview-based sidebar inside VS Code.
 * Shows a login/signup form when unauthenticated, and the chat interface when authenticated.
 */
export class SidebarProvider implements vscode.WebviewViewProvider {
    private _view?: vscode.WebviewView;

    constructor(
        private readonly extensionUri: vscode.Uri,
        private readonly backend: BackendClient,
        private readonly auth: AuthService,
        private readonly output: vscode.OutputChannel
    ) { }

    resolveWebviewView(
        webviewView: vscode.WebviewView,
        _context: vscode.WebviewViewResolveContext,
        _token: vscode.CancellationToken
    ): void {
        this._view = webviewView;

        webviewView.webview.options = {
            enableScripts: true,
            localResourceRoots: [this.extensionUri],
        };

        // Enable context retention so chat doesn't vanish when switching tabs
        // Note: For WebviewView, we handle this by ensuring the view is resolved and messages are re-sent if needed
        // but 'retainContextWhenHidden' is specifically for WebviewPanels. 
        // For Sidebar, we will load history from the backend on every resolve.

        this.updateHtml();

        // Handle messages from the webview
        webviewView.webview.onDidReceiveMessage(async (message) => {
            switch (message.type) {
                case 'login': {
                    const result = await this.auth.login(message.email, message.password);
                    if (result.success) {
                        this.updateHtml();
                        this.postMessage({ type: 'authSuccess' });
                    } else {
                        this.postMessage({ type: 'authError', message: result.error });
                    }
                    break;
                }
                case 'signup': {
                    const result = await this.auth.signup(message.email, message.password, message.displayName || '');
                    if (result.success) {
                        this.updateHtml();
                        this.postMessage({ type: 'authSuccess' });
                    } else {
                        this.postMessage({ type: 'authError', message: result.error });
                    }
                    break;
                }
                case 'logout': {
                    await this.auth.logout();
                    this.updateHtml();
                    break;
                }
                case 'ask': {
                    const question = message.question as string;
                    let sessionId = message.sessionId as string | undefined;
                    this.output.appendLine(`[Sidebar] User asked: ${question} (session: ${sessionId})`);

                    // Ensure chats are always attached to a session so they appear in "Past Chats".
                    if (!sessionId) {
                        const autoTitle = (question || 'New Chat').trim().slice(0, 48) || 'New Chat';
                        const createdSessionId = await this.backend.createChatSession(autoTitle);
                        if (createdSessionId) {
                            sessionId = createdSessionId;
                            this.postMessage({ type: 'sessionBound', sessionId });
                        }
                    }

                    const normalized = (question || '').trim().toLowerCase();
                    const openShadowGraphIntent =
                        normalized.includes('open shadow graph') ||
                        normalized.includes('show shadow graph') ||
                        normalized.includes('launch shadow graph') ||
                        normalized === 'secondcortex: open shadow graph';

                    if (openShadowGraphIntent) {
                        await vscode.commands.executeCommand('secondcortex.openShadowGraph');
                        this.postMessage({
                            type: 'answer',
                            summary: 'Opened Shadow Graph in a side panel. Use the snapshot slider to time-travel and click Restore when ready.',
                            commands: [],
                            sessionId,
                        });
                        break;
                    }

                    this.postMessage({ type: 'loading' });

                    const response = await this.backend.askQuestion(question, sessionId);
                    if (response && !(response as any)._error) {
                        const styledSummary = this.formatAssistantResponse(response.summary, response.commands ?? []);
                        this.postMessage({
                            type: 'answer',
                            summary: styledSummary,
                            commands: response.commands ?? [],
                            sessionId: sessionId
                        });
                    } else if (response && (response as any)._error) {
                        this.postMessage({
                            type: 'error',
                            message: `Backend error: ${response.summary}`,
                        });
                    } else {
                        this.postMessage({
                            type: 'error',
                            message: 'Could not reach the SecondCortex backend. Is it running?',
                        });
                    }
                    break;
                }
                case 'checkAuth': {
                    const loggedIn = await this.auth.isLoggedIn();
                    const user = await this.auth.getUser();
                    this.postMessage({ type: 'authStatus', loggedIn, user });
                    break;
                }
                case 'getHistory': {
                    const history = await this.backend.getChatHistory(message.sessionId);
                    this.postMessage({ type: 'history', messages: history, sessionId: message.sessionId });
                    break;
                }
                case 'getSessions': {
                    const sessions = await this.backend.getChatSessions();
                    this.postMessage({ type: 'sessions', sessions });
                    break;
                }
                case 'newChat': {
                    const sessionTitle = message.title || "New Chat";
                    const newId = await this.backend.createChatSession(sessionTitle);
                    this.postMessage({ type: 'chatCleared', sessionId: newId });
                    const sessions = await this.backend.getChatSessions();
                    this.postMessage({ type: 'sessions', sessions });
                    break;
                }
                case 'switchSession': {
                    const history = await this.backend.getChatHistory(message.sessionId);
                    this.postMessage({ type: 'history', messages: history, sessionId: message.sessionId });
                    break;
                }
                case 'openShadowGraph': {
                    await vscode.commands.executeCommand('secondcortex.openShadowGraph');
                    this.postMessage({
                        type: 'answer',
                        summary: 'Opened Shadow Graph in a side panel.',
                        commands: [],
                        sessionId: message.sessionId,
                    });
                    break;
                }
            }
        });
    }

    /** Refresh the webview content (e.g. after login/logout). */
    refreshView(): void {
        this.updateHtml();
    }

    private async updateHtml(): Promise<void> {
        if (!this._view) { return; }
        const loggedIn = await this.auth.isLoggedIn();
        const user = await this.auth.getUser();
        this._view.webview.html = this.getHtml(loggedIn, user);
    }

    private postMessage(message: Record<string, unknown>): void {
        this._view?.webview.postMessage(message);
    }

    private formatAssistantResponse(summary: string, commands: unknown[]): string {
        const cleanSummary = (summary || '').trim();
        const commandLines = this.buildCommandLines(commands);

        if (commandLines.length === 0) {
            return cleanSummary;
        }

        return `${cleanSummary}\n\nSuggested actions:\n${commandLines.map((line) => `- ${line}`).join('\n')}`;
    }

    private buildCommandLines(commands: unknown[]): string[] {
        const lines: string[] = [];

        for (const command of commands) {
            if (!command || typeof command !== 'object') {
                continue;
            }

            const cmd = command as {
                type?: string;
                branch?: string;
                filePath?: string;
                command?: string;
            };

            if (cmd.type === 'git_checkout' && cmd.branch) {
                lines.push(`Switch branch to \`${cmd.branch}\``);
            } else if (cmd.type === 'open_file' && cmd.filePath) {
                lines.push(`Open file \`${cmd.filePath}\``);
            } else if (cmd.type === 'run_command' && cmd.command) {
                lines.push(`Run \`${cmd.command}\``);
            } else if (cmd.type) {
                lines.push(`Run step: \`${cmd.type}\``);
            }
        }

        return lines;
    }

    private getHtml(loggedIn: boolean, user?: { userId: string; email: string; displayName: string }): string {
        if (!loggedIn) {
            return this.getAuthHtml();
        }
        return this.getChatHtml(user);
    }

    // ── Auth Page HTML ─────────────────────────────────────────────

    private getAuthHtml(): string {
        return /*html*/ `
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>SecondCortex — Sign In</title>
    <style>
        :root {
            --bg: #080808;
            --surface: #111111;
            --border: rgba(255,255,255,0.08);
            --text: #f0f0f0;
            --muted: rgba(255,255,255,0.55);
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: var(--vscode-font-family);
            color: var(--text);
            background: var(--bg);
            padding: 16px;
            display: flex;
            flex-direction: column;
            height: 100vh;
        }
        .brand {
            margin-bottom: 22px;
            padding-top: 14px;
        }
        .brand::before {
            content: 'SecondCortex Access';
            display: block;
            font-size: 10px;
            letter-spacing: 0.14em;
            text-transform: uppercase;
            color: var(--muted);
            margin-bottom: 8px;
        }
        .brand h1 {
            font-size: 20px;
            font-weight: 700;
            margin-bottom: 6px;
            letter-spacing: 0.06em;
            text-transform: uppercase;
        }
        .brand p {
            font-size: 12px;
            color: var(--muted);
        }
        .tabs {
            display: flex;
            gap: 0;
            margin-bottom: 18px;
            border: 1px solid var(--border);
            background: var(--surface);
            border-radius: 8px;
            padding: 4px;
        }
        .tab {
            flex: 1;
            padding: 8px 0;
            text-align: center;
            font-size: 11px;
            font-weight: 600;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            cursor: pointer;
            border: none;
            background: transparent;
            color: var(--muted);
            border-radius: 6px;
            transition: all 0.2s;
        }
        .tab.active {
            color: var(--text);
            background: rgba(255,255,255,0.08);
        }
        .tab:hover { color: var(--text); }
        .form-group {
            margin-bottom: 10px;
        }
        .form-group label {
            display: block;
            font-size: 10px;
            font-weight: 600;
            letter-spacing: 0.1em;
            text-transform: uppercase;
            margin-bottom: 6px;
            color: var(--muted);
        }
        .form-group input {
            width: 100%;
            padding: 9px 11px;
            font-size: 13px;
            border: 1px solid var(--border);
            background: var(--surface);
            color: var(--text);
            border-radius: 6px;
            outline: none;
        }
        .form-group input:focus {
            border-color: rgba(255,255,255,0.28);
        }
        .submit-btn {
            width: 100%;
            padding: 11px;
            margin-top: 10px;
            font-size: 11px;
            font-weight: 600;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            background: rgba(255,255,255,0.9);
            color: #0b0b0b;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            transition: opacity 0.2s;
        }
        .submit-btn:hover {
            opacity: 0.86;
        }
        .submit-btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }
        .error-msg {
            color: var(--vscode-inputValidation-errorForeground, #f48771);
            background: var(--vscode-inputValidation-errorBackground, rgba(244,135,113,0.1));
            border: 1px solid var(--vscode-inputValidation-errorBorder, #f48771);
            padding: 6px 10px;
            border-radius: 4px;
            font-size: 12px;
            margin-top: 8px;
            display: none;
        }
        #signup-fields { display: none; }
    </style>
</head>
<body>
    <div class="brand">
        <h1>SecondCortex</h1>
        <p>Persistent context for your code</p>
    </div>

    <div class="tabs">
        <button class="tab active" id="tab-login" onclick="switchTab('login')">Log In</button>
        <button class="tab" id="tab-signup" onclick="switchTab('signup')">Sign Up</button>
    </div>

    <form id="auth-form" onsubmit="handleSubmit(event)">
        <div class="form-group">
            <label for="email">Email</label>
            <input id="email" type="email" placeholder="you@example.com" required />
        </div>
        <div class="form-group">
            <label for="password">Password</label>
            <input id="password" type="password" placeholder="••••••••" required minlength="6" />
        </div>
        <div id="signup-fields">
            <div class="form-group">
                <label for="display-name">Display Name</label>
                <input id="display-name" type="text" placeholder="Your Name" />
            </div>
        </div>
        <button type="submit" class="submit-btn" id="submit-btn">Log In</button>
        <div class="error-msg" id="error-msg"></div>
    </form>

    <script>
        const vscode = acquireVsCodeApi();
        let mode = 'login';

        function switchTab(tab) {
            mode = tab;
            document.getElementById('tab-login').classList.toggle('active', tab === 'login');
            document.getElementById('tab-signup').classList.toggle('active', tab === 'signup');
            document.getElementById('signup-fields').style.display = tab === 'signup' ? 'block' : 'none';
            document.getElementById('submit-btn').textContent = tab === 'login' ? 'Log In' : 'Create Account';
            document.getElementById('error-msg').style.display = 'none';
        }

        function handleSubmit(e) {
            e.preventDefault();
            const email = document.getElementById('email').value.trim();
            const password = document.getElementById('password').value;
            const btn = document.getElementById('submit-btn');
            btn.disabled = true;
            btn.textContent = 'Please wait...';
            document.getElementById('error-msg').style.display = 'none';

            if (mode === 'login') {
                vscode.postMessage({ type: 'login', email, password });
            } else {
                const displayName = document.getElementById('display-name').value.trim();
                vscode.postMessage({ type: 'signup', email, password, displayName });
            }
        }

        window.addEventListener('message', (event) => {
            const msg = event.data;
            const btn = document.getElementById('submit-btn');
            if (msg.type === 'authError') {
                btn.disabled = false;
                btn.textContent = mode === 'login' ? 'Log In' : 'Create Account';
                const errEl = document.getElementById('error-msg');
                errEl.textContent = msg.message;
                errEl.style.display = 'block';
            }
            // authSuccess is handled by the extension re-rendering the webview
        });
    </script>
</body>
</html>`;
    }

    // ── Chat Page HTML ─────────────────────────────────────────────

    private getChatHtml(user?: { userId: string; email: string; displayName: string }): string {
        const displayName = user?.displayName || user?.email || 'User';
        return /*html*/ `
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>SecondCortex</title>
    <style>
        :root {
            --accent: #e5e7eb;
            --accent-soft: rgba(229, 231, 235, 0.12);
            --bg: #080808;
            --surface: #111111;
            --border: rgba(255, 255, 255, 0.08);
            --text-main: #f0f0f0;
            --text-dim: rgba(255,255,255,0.55);
        }

        * { box-sizing: border-box; margin: 0; padding: 0; }
        
        body {
            font-family: var(--vscode-font-family), system-ui;
            color: var(--text-main);
            background: var(--bg);
            padding: 0;
            display: flex;
            flex-direction: column;
            height: 100vh;
            overflow: hidden;
            background-image: radial-gradient(circle at 20% 0%, rgba(255, 255, 255, 0.04), transparent 50%);
        }

        /* ── Header ────────────────────────────────────────── */
        .header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 16px;
            background: rgba(17, 17, 17, 0.95);
            border-bottom: 1px solid var(--border);
            z-index: 20;
        }
        .header h2 {
            font-size: 15px;
            font-weight: 700;
            color: var(--text-main);
            letter-spacing: -0.01em;
            text-transform: uppercase;
        }
        .header-actions {
            display: flex;
            gap: 8px;
            align-items: center;
        }

        /* ── Action Buttons ────────────────────────────────── */
        .icon-btn {
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid var(--border);
            color: var(--text-dim);
            padding: 6px 10px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 11px;
            font-weight: 600;
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
            display: flex;
            align-items: center;
            gap: 4px;
        }
        .icon-btn:hover {
            color: #fff;
            background: rgba(255, 255, 255, 0.08);
            border-color: rgba(255, 255, 255, 0.2);
            transform: translateY(-1px);
        }
        .icon-btn.primary {
            background: var(--accent-soft);
            border-color: rgba(255, 255, 255, 0.22);
            color: var(--text-main);
        }
        .icon-btn.primary:hover {
            background: var(--accent);
            color: #0b0b0b;
        }

        /* ── History Panel ─────────────────────────────────── */
        #history-panel {
            position: absolute;
            top: 60px;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(8, 8, 8, 0.96);
            z-index: 30;
            transform: translateX(-100%);
            transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            padding: 20px;
            border-right: 1px solid var(--border);
        }
        #history-panel.open {
            transform: translateX(0);
        }
        .history-list {
            margin-top: 20px;
            display: flex;
            flex-direction: column;
            gap: 8px;
            overflow-y: auto;
            max-height: calc(100vh - 150px);
        }
        .history-item {
            padding: 12px;
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid var(--border);
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.2s;
        }
        .history-item:hover {
            background: rgba(255, 255, 255, 0.08);
            border-color: var(--accent);
        }
        .history-item.active {
            border-color: var(--accent);
            background: var(--accent-soft);
        }
        .history-item-title {
            font-size: 13px;
            font-weight: 600;
            color: var(--text-main);
            margin-bottom: 4px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .history-item-date {
            font-size: 10px;
            color: var(--text-dim);
        }

        /* ── Chat Log ──────────────────────────────────────── */
        #chat-log {
            flex: 1;
            overflow-y: auto;
            padding: 20px 16px;
            display: flex;
            flex-direction: column;
            gap: 16px;
            scroll-behavior: smooth;
        }
        #chat-log::-webkit-scrollbar { width: 4px; }
        #chat-log::-webkit-scrollbar-track { background: transparent; }
        #chat-log::-webkit-scrollbar-thumb { background: rgba(255, 255, 255, 0.1); border-radius: 10px; }

        .msg-wrapper {
            display: flex;
            flex-direction: column;
            max-width: 90%;
            animation: slideUp 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        @keyframes slideUp {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .msg-wrapper.user { align-self: flex-end; }
        .msg-wrapper.assistant { align-self: flex-start; }

        .msg {
            padding: 12px 14px;
            border-radius: 12px;
            font-size: 13px;
            line-height: 1.5;
            word-wrap: break-word;
            position: relative;
        }
        .msg p { margin: 0 0 8px 0; }
        .msg p:last-child { margin-bottom: 0; }
        .msg h3 {
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            color: var(--text-dim);
            margin: 0 0 8px 0;
        }
        .msg ul {
            margin: 0 0 8px 0;
            padding-left: 16px;
        }
        .msg li { margin: 3px 0; }
        .msg code {
            font-family: var(--vscode-editor-font-family), monospace;
            font-size: 12px;
            background: rgba(255,255,255,0.08);
            border: 1px solid rgba(255,255,255,0.12);
            border-radius: 5px;
            padding: 1px 6px;
        }
        .msg pre {
            margin: 8px 0;
            padding: 10px;
            border-radius: 8px;
            background: rgba(0,0,0,0.3);
            border: 1px solid rgba(255,255,255,0.08);
            overflow-x: auto;
        }
        .msg pre code {
            padding: 0;
            border: none;
            background: transparent;
            font-size: 12px;
            white-space: pre;
        }
        .user .msg {
            background: #e5e7eb;
            color: #0b0b0b;
            border-bottom-right-radius: 2px;
            box-shadow: none;
        }
        .assistant .msg {
            background: var(--surface);
            border: 1px solid var(--border);
            color: var(--text-main);
            border-bottom-left-radius: 2px;
        }
        .msg.loading {
            opacity: 0.6;
            font-style: italic;
            background: transparent;
            border: none;
            padding-left: 0;
        }
        .msg.error {
            background: rgba(239, 68, 68, 0.1);
            border: 1px solid rgba(239, 68, 68, 0.2);
            color: #f87171;
        }

        .meta {
            font-size: 9px;
            color: var(--text-dim);
            margin-top: 4px;
            font-weight: 500;
        }
        .user .meta { text-align: right; }

        /* ── Input Area ────────────────────────────────────── */
        .footer {
            padding: 16px;
            background: rgba(17, 17, 17, 0.95);
            border-top: 1px solid var(--border);
        }
        .input-container {
            position: relative;
            display: flex;
            background: rgba(0, 0, 0, 0.2);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 4px;
            transition: all 0.2s;
        }
        .input-container:focus-within {
            border-color: var(--accent);
            box-shadow: 0 0 0 3px rgba(255, 255, 255, 0.08);
        }
        #question-input {
            flex: 1;
            background: transparent;
            border: none;
            color: var(--text-main);
            padding: 8px 12px;
            font-size: 13px;
            outline: none;
            font-family: inherit;
        }
        #send-btn {
            background: var(--accent);
            color: #0b0b0b;
            border: none;
            border-radius: 7px;
            padding: 0 14px;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
        }
        #send-btn:hover {
            transform: scale(1.02);
            filter: brightness(1.1);
        }
        #send-btn:active { transform: scale(0.98); }
        #send-btn:disabled {
            opacity: 0.6;
            cursor: not-allowed;
            transform: none;
            filter: none;
        }

        .shield-badge {
            display: flex;
            align-items: center;
            gap: 6px;
            margin-top: 6px;
            flex-wrap: wrap;
        }

        .shield-pill {
            display: inline-flex;
            align-items: center;
            font-size: 10px;
            font-weight: 700;
            color: var(--text-main);
            background: rgba(255, 255, 255, 0.1);
            border: 1px solid rgba(255, 255, 255, 0.22);
            padding: 3px 9px;
            border-radius: 999px;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            line-height: 1;
            white-space: nowrap;
        }

        .shield-pill.secure {
            background: rgba(62, 202, 137, 0.18);
            border-color: rgba(62, 202, 137, 0.55);
            color: #ccffe7;
        }

        .user-info {
            font-size: 11px;
            color: var(--text-dim);
            font-weight: 500;
        }

        .bottom-actions {
            margin-top: 10px;
            display: flex;
            justify-content: center;
        }

        .bottom-actions .icon-btn {
            width: 100%;
            justify-content: center;
            padding: 8px 10px;
            font-size: 11px;
        }
    </style>
</head>
<body>
    <div class="header">
        <div>
            <h2 id="current-title">SecondCortex</h2>
            <div class="shield-badge">
                <span class="shield-pill secure">Secure</span>
                <span class="shield-pill">Privacy Protected</span>
            </div>
        </div>
        <div class="header-actions">
            <button class="icon-btn" onclick="toggleHistory()">History</button>
            <button class="icon-btn primary" onclick="startNewChat()">New Chat</button>
            <button class="icon-btn" onclick="doLogout()">Logout</button>
        </div>
    </div>

    <!-- History View -->
    <div id="history-panel">
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <h3 style="font-size: 14px;">Past Chats</h3>
            <button class="icon-btn" onclick="toggleHistory()">Close</button>
        </div>
        <div id="history-list" class="history-list">
            <!-- Items injected by JS -->
        </div>
    </div>
    
    <div id="chat-log"></div>
    
    <div class="footer">
        <div class="input-container">
            <input id="question-input" type="text" placeholder="Explain your code architecture..." autocomplete="off" />
            <button id="send-btn">Ask</button>
        </div>
        <div style="text-align: center; margin-top: 8px;">
            <span class="user-info">Logged in as ${displayName}</span>
        </div>
        <div class="bottom-actions">
            <button class="icon-btn" onclick="openShadowGraph()">Open Shadow Graph</button>
        </div>
    </div>

    <script>
        const vscode = acquireVsCodeApi();
        const chatLog = document.getElementById('chat-log');
        const input = document.getElementById('question-input');
        const sendBtn = document.getElementById('send-btn');
        const historyPanel = document.getElementById('history-panel');
        const historyList = document.getElementById('history-list');

        // State persistence
        let state = vscode.getState() || { messages: [], sessionId: null, sessions: [] };
        let isAwaitingResponse = false;
        
        // Initial render from state (instant recovery)
        if (state.messages && state.messages.length > 0) {
            renderAllMessages(state.messages);
        } else {
            addMessage('assistant', 'Welcome! How can I help you today?', true);
        }

        // Fetch latest from backend to sync
        vscode.postMessage({ type: 'getHistory', sessionId: state.sessionId });
        vscode.postMessage({ type: 'getSessions' });

        function saveState() {
            vscode.setState(state);
        }

        function setPendingRequest(pending) {
            isAwaitingResponse = pending;
            sendBtn.disabled = pending;
            input.disabled = pending;
        }

        function renderAllMessages(messages) {
            chatLog.innerHTML = '';
            if (messages.length === 0) {
                addMessage('assistant', 'Welcome! How can I help you today?', true);
            } else {
                messages.forEach(m => {
                    addMessage(m.role, m.content, true);
                });
            }
            chatLog.scrollTop = chatLog.scrollHeight;
        }

        function addMessage(role, text, skipScroll = false) {
            const wrapper = document.createElement('div');
            wrapper.className = 'msg-wrapper ' + (role === 'user' ? 'user' : 'assistant');
            
            const msgDiv = document.createElement('div');
            msgDiv.className = 'msg';
            msgDiv.innerHTML = formatText(text);
            
            const metaDiv = document.createElement('div');
            metaDiv.className = 'meta';
            metaDiv.textContent = role === 'user' ? 'You' : 'Cortex';
            
            wrapper.appendChild(msgDiv);
            wrapper.appendChild(metaDiv);
            chatLog.appendChild(wrapper);
            
            if (!skipScroll) {
                chatLog.scrollTop = chatLog.scrollHeight;
            }
        }

        function escapeHtml(text) {
            return text
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;');
        }

        function formatInline(text) {
            return escapeHtml(text).replace(/\`([^\`]+)\`/g, '<code>$1</code>');
        }

        function formatText(t) {
            if (!t) return '';

            const parts = String(t).split(/\`\`\`/);
            let html = '';

            for (let i = 0; i < parts.length; i++) {
                if (i % 2 === 1) {
                    html += '<pre><code>' + escapeHtml(parts[i].replace(/^\\n/, '').replace(/\\n$/, '')) + '</code></pre>';
                    continue;
                }

                const blocks = parts[i].split(/\\n\\n+/);
                for (const block of blocks) {
                    const trimmed = block.trim();
                    if (!trimmed) continue;

                    const lines = trimmed.split('\\n');
                    const isList = lines.every(line => /^[-*]\\s+/.test(line.trim()));

                    if (isList) {
                        const items = lines
                            .map(line => line.trim().replace(/^[-*]\\s+/, ''))
                            .map(item => '<li>' + formatInline(item) + '</li>')
                            .join('');
                        html += '<ul>' + items + '</ul>';
                        continue;
                    }

                    if (/^#{1,3}\\s+/.test(trimmed)) {
                        const heading = trimmed.replace(/^#{1,3}\\s+/, '');
                        html += '<h3>' + formatInline(heading) + '</h3>';
                        continue;
                    }

                    html += '<p>' + formatInline(lines.join(' ')) + '</p>';
                }
            }

            return html;
        }

        function toggleHistory() {
            historyPanel.classList.toggle('open');
            if (historyPanel.classList.contains('open')) {
                vscode.postMessage({ type: 'getSessions' });
            }
        }

        function startNewChat() {
            vscode.postMessage({ type: 'newChat', title: 'New Chat' });
        }

        function loadSession(id) {
            state.sessionId = id;
            vscode.postMessage({ type: 'switchSession', sessionId: id });
            toggleHistory();
        }

        function renderSessions(sessions) {
            state.sessions = sessions;
            saveState();
            historyList.innerHTML = '';
            sessions.forEach(s => {
                const item = document.createElement('div');
                item.className = 'history-item' + (s.id === state.sessionId ? ' active' : '');
                item.onclick = () => loadSession(s.id);
                
                const date = new Date(s.created_at).toLocaleDateString();
                item.innerHTML = \`
                    <div class="history-item-title">\${s.title}</div>
                    <div class="history-item-date">\${date}</div>
                \`;
                historyList.appendChild(item);
            });
        }

        function send() {
            if (isAwaitingResponse) return;
            const q = input.value.trim();
            if (!q) return;

            addMessage('user', q);
            state.messages.push({ role: 'user', content: q, timestamp: new Date().toISOString() });
            saveState();
            input.value = '';
            setPendingRequest(true);
            vscode.postMessage({ type: 'ask', question: q, sessionId: state.sessionId });
        }

        function doLogout() {
            vscode.postMessage({ type: 'logout' });
        }

        function openShadowGraph() {
            vscode.postMessage({ type: 'openShadowGraph', sessionId: state.sessionId });
        }

        sendBtn.addEventListener('click', send);
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') send();
        });

        window.addEventListener('message', (event) => {
            const msg = event.data;
            
            // Clean up any persistence-specific loading UI
            const loadingWrappers = chatLog.querySelectorAll('.loading-wrapper');
            loadingWrappers.forEach(el => el.remove());

            switch (msg.type) {
                case 'history':
                    state.messages = msg.messages;
                    state.sessionId = msg.sessionId;
                    renderAllMessages(msg.messages);
                    saveState();
                    break;
                case 'sessions':
                    renderSessions(msg.sessions);
                    if (!state.sessionId && Array.isArray(msg.sessions) && msg.sessions.length > 0) {
                        state.sessionId = msg.sessions[0].id;
                        vscode.postMessage({ type: 'switchSession', sessionId: state.sessionId });
                    }
                    break;
                case 'chatCleared':
                    state.sessionId = msg.sessionId;
                    state.messages = [];
                    renderAllMessages([]);
                    saveState();
                    vscode.postMessage({ type: 'getSessions' });
                    break;
                case 'sessionBound':
                    state.sessionId = msg.sessionId;
                    saveState();
                    vscode.postMessage({ type: 'getSessions' });
                    break;
                case 'loading':
                    if (chatLog.querySelector('.loading-wrapper')) {
                        break;
                    }
                    const loader = document.createElement('div');
                    loader.className = 'msg-wrapper assistant loading-wrapper';
                    loader.innerHTML = '<div class="msg loading">Thinking...</div>';
                    chatLog.appendChild(loader);
                    chatLog.scrollTop = chatLog.scrollHeight;
                    break;
                case 'answer':
                    addMessage('assistant', msg.summary);
                    state.messages.push({ role: 'assistant', content: msg.summary, timestamp: new Date().toISOString() });
                    saveState();
                    setPendingRequest(false);
                    break;
                case 'error':
                    const errWrapper = document.createElement('div');
                    errWrapper.className = 'msg-wrapper assistant';
                    errWrapper.innerHTML = '<div class="msg error">Error: ' + msg.message + '</div>';
                    chatLog.appendChild(errWrapper);
                    chatLog.scrollTop = chatLog.scrollHeight;
                    setPendingRequest(false);
                    break;
            }
        });
    </script>
</body>
</html>`;
    }

}
