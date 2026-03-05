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
                    this.output.appendLine(`[Sidebar] User asked: ${question}`);
                    this.postMessage({ type: 'loading' });

                    const response = await this.backend.askQuestion(question);
                    if (response && !(response as any)._error) {
                        this.postMessage({
                            type: 'answer',
                            summary: response.summary,
                            commands: response.commands ?? [],
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
                    const history = await this.backend.getChatHistory();
                    this.postMessage({ type: 'history', messages: history });
                    break;
                }
                case 'newChat': {
                    await this.backend.clearChatHistory();
                    this.postMessage({ type: 'chatCleared' });
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
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: var(--vscode-font-family);
            color: var(--vscode-foreground);
            background: var(--vscode-sideBar-background);
            padding: 16px;
            display: flex;
            flex-direction: column;
            height: 100vh;
        }
        .brand {
            text-align: center;
            margin-bottom: 24px;
            padding-top: 20px;
        }
        .brand h1 {
            font-size: 18px;
            font-weight: 700;
            margin-bottom: 4px;
        }
        .brand p {
            font-size: 11px;
            opacity: 0.6;
        }
        .tabs {
            display: flex;
            gap: 0;
            margin-bottom: 16px;
            border-bottom: 1px solid var(--vscode-panel-border);
        }
        .tab {
            flex: 1;
            padding: 8px 0;
            text-align: center;
            font-size: 13px;
            font-weight: 500;
            cursor: pointer;
            border: none;
            background: transparent;
            color: var(--vscode-foreground);
            opacity: 0.5;
            border-bottom: 2px solid transparent;
            transition: all 0.2s;
        }
        .tab.active {
            opacity: 1;
            border-bottom-color: var(--vscode-button-background);
        }
        .tab:hover { opacity: 0.8; }
        .form-group {
            margin-bottom: 12px;
        }
        .form-group label {
            display: block;
            font-size: 12px;
            font-weight: 500;
            margin-bottom: 4px;
            opacity: 0.8;
        }
        .form-group input {
            width: 100%;
            padding: 8px 10px;
            font-size: 13px;
            border: 1px solid var(--vscode-input-border);
            background: var(--vscode-input-background);
            color: var(--vscode-input-foreground);
            border-radius: 4px;
            outline: none;
        }
        .form-group input:focus {
            border-color: var(--vscode-focusBorder);
        }
        .submit-btn {
            width: 100%;
            padding: 10px;
            margin-top: 8px;
            font-size: 13px;
            font-weight: 600;
            background: var(--vscode-button-background);
            color: var(--vscode-button-foreground);
            border: none;
            border-radius: 4px;
            cursor: pointer;
            transition: background 0.2s;
        }
        .submit-btn:hover {
            background: var(--vscode-button-hoverBackground);
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
        <h1>🧠 SecondCortex</h1>
        <p>Your AI-Powered Second Brain</p>
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
            --accent: #6366f1;
            --accent-glow: rgba(99, 102, 241, 0.4);
            --bg: #020617;
            --surface: #0f172a;
            --border: rgba(255, 255, 255, 0.08);
            --text-main: #f8fafc;
            --text-dim: #94a3b8;
        }

        * { box-sizing: border-box; margin: 0; padding: 0; }
        
        body {
            font-family: 'Inter', var(--vscode-font-family), system-ui;
            color: var(--text-main);
            background: var(--bg);
            padding: 0;
            display: flex;
            flex-direction: column;
            height: 100vh;
            overflow: hidden;
            background-image: 
                radial-gradient(circle at top right, rgba(99, 102, 241, 0.05), transparent 400px),
                radial-gradient(circle at bottom left, rgba(244, 114, 182, 0.03), transparent 300px);
        }

        /* ── Header ────────────────────────────────────────── */
        .header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 16px;
            background: rgba(15, 23, 42, 0.7);
            backdrop-filter: blur(12px);
            border-bottom: 1px solid var(--border);
            z-index: 10;
        }
        .header h2 {
            font-size: 15px;
            font-weight: 700;
            background: linear-gradient(135deg, #fff 0%, #94a3b8 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            letter-spacing: -0.01em;
        }
        .header-actions {
            display: flex;
            gap: 8px;
            align-items: center;
        }
        .user-info {
            font-size: 11px;
            color: var(--text-dim);
            font-weight: 500;
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
            background: rgba(99, 102, 241, 0.1);
            border-color: rgba(99, 102, 241, 0.2);
            color: #818cf8;
        }
        .icon-btn.primary:hover {
            background: var(--accent);
            color: #fff;
            box-shadow: 0 0 16px var(--accent-glow);
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
        .user .msg {
            background: var(--accent);
            color: #fff;
            border-bottom-right-radius: 2px;
            box-shadow: 0 4px 12px rgba(99, 102, 241, 0.2);
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
            background: rgba(15, 23, 42, 0.8);
            backdrop-filter: blur(12px);
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
            box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
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
            color: #fff;
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

        /* ── Typography Highlighting ───────────────────────── */
        code {
            background: rgba(255, 255, 255, 0.05);
            padding: 2px 4px;
            border-radius: 3px;
            font-family: 'Fira Code', monospace;
            font-size: 0.9em;
        }
    </style>
</head>
<body>
    <div class="header">
        <h2>🧠 SecondCortex</h2>
        <div class="header-actions">
            <button class="icon-btn primary" onclick="startNewChat()">+ New Chat</button>
            <button class="icon-btn" onclick="doLogout()">Logout</button>
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
    </div>

    <script>
        const vscode = acquireVsCodeApi();
        const chatLog = document.getElementById('chat-log');
        const input = document.getElementById('question-input');
        const sendBtn = document.getElementById('send-btn');

        // Initializing history
        vscode.postMessage({ type: 'getHistory' });

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

        function formatText(t) {
            // Simple backtick formatting for code
            return t.replace(/\`([^\`]+)\`/g, '<code>$1</code>');
        }

        function startNewChat() {
            if (confirm('Reset conversation? All current messages will be archived.')) {
                vscode.postMessage({ type: 'newChat' });
            }
        }

        function send() {
            const q = input.value.trim();
            if (!q) return;
            addMessage('user', q);
            input.value = '';
            vscode.postMessage({ type: 'ask', question: q });
        }

        function doLogout() {
            vscode.postMessage({ type: 'logout' });
        }

        sendBtn.addEventListener('click', send);
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') send();
        });

        window.addEventListener('message', (event) => {
            const msg = event.data;
            const loadingWrappers = chatLog.querySelectorAll('.loading-wrapper');
            loadingWrappers.forEach(el => el.remove());

            switch (msg.type) {
                case 'history':
                    chatLog.innerHTML = '';
                    if (msg.messages.length === 0) {
                        addMessage('assistant', 'Welcome! How can I help you today?');
                    } else {
                        msg.messages.forEach(m => {
                            addMessage(m.role, m.content, true);
                        });
                    }
                    chatLog.scrollTop = chatLog.scrollHeight;
                    break;
                case 'chatCleared':
                    chatLog.innerHTML = '';
                    addMessage('assistant', 'Context reset. I am ready for a new task.');
                    break;
                case 'loading':
                    const loader = document.createElement('div');
                    loader.className = 'msg-wrapper assistant loading-wrapper';
                    loader.innerHTML = '<div class="msg loading">Thinking...</div>';
                    chatLog.appendChild(loader);
                    chatLog.scrollTop = chatLog.scrollHeight;
                    break;
                case 'answer':
                    addMessage('assistant', msg.summary);
                    break;
                case 'error':
                    const errWrapper = document.createElement('div');
                    errWrapper.className = 'msg-wrapper assistant';
                    errWrapper.innerHTML = '<div class="msg error">Error: ' + msg.message + '</div>';
                    chatLog.appendChild(errWrapper);
                    break;
            }
        });
    </script>
</body>
</html>`;
    }

}
