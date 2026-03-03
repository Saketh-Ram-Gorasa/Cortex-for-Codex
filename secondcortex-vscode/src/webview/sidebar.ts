import * as vscode from 'vscode';
import { BackendClient } from '../backendClient';

/**
 * SidebarProvider – renders a Webview-based chat sidebar inside VS Code
 * where the user can ask questions like "Why did we roll back?"
 * and see agent reasoning logs.
 */
export class SidebarProvider implements vscode.WebviewViewProvider {
    private _view?: vscode.WebviewView;

    constructor(
        private readonly extensionUri: vscode.Uri,
        private readonly backend: BackendClient,
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

        webviewView.webview.html = this.getHtml();

        // Handle messages from the webview
        webviewView.webview.onDidReceiveMessage(async (message) => {
            switch (message.type) {
                case 'ask': {
                    const question = message.question as string;
                    this.output.appendLine(`[Sidebar] User asked: ${question}`);

                    // Show a loading state
                    this.postMessage({ type: 'loading' });

                    const response = await this.backend.askQuestion(question);
                    if (response) {
                        this.postMessage({
                            type: 'answer',
                            summary: response.summary,
                            commands: response.commands ?? [],
                        });
                    } else {
                        this.postMessage({
                            type: 'error',
                            message: 'Could not reach the SecondCortex backend. Is it running?',
                        });
                    }
                    break;
                }
            }
        });
    }

    private postMessage(message: Record<string, unknown>): void {
        this._view?.webview.postMessage(message);
    }

    private getHtml(): string {
        return /*html*/ `
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>SecondCortex</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: var(--vscode-font-family);
            color: var(--vscode-foreground);
            background: var(--vscode-sideBar-background);
            padding: 12px;
            display: flex;
            flex-direction: column;
            height: 100vh;
        }
        h2 {
            font-size: 14px;
            font-weight: 600;
            margin-bottom: 12px;
            color: var(--vscode-foreground);
        }
        #chat-log {
            flex: 1;
            overflow-y: auto;
            margin-bottom: 12px;
            display: flex;
            flex-direction: column;
            gap: 8px;
        }
        .msg {
            padding: 8px 10px;
            border-radius: 6px;
            font-size: 13px;
            line-height: 1.4;
            word-wrap: break-word;
        }
        .msg.user {
            background: var(--vscode-button-background);
            color: var(--vscode-button-foreground);
            align-self: flex-end;
            max-width: 85%;
        }
        .msg.assistant {
            background: var(--vscode-editor-background);
            border: 1px solid var(--vscode-panel-border);
            align-self: flex-start;
            max-width: 85%;
        }
        .msg.error {
            background: var(--vscode-inputValidation-errorBackground);
            border: 1px solid var(--vscode-inputValidation-errorBorder);
            color: var(--vscode-inputValidation-errorForeground);
        }
        .msg.loading {
            opacity: 0.6;
            font-style: italic;
        }
        #input-area {
            display: flex;
            gap: 6px;
        }
        #question-input {
            flex: 1;
            padding: 8px;
            font-size: 13px;
            border: 1px solid var(--vscode-input-border);
            background: var(--vscode-input-background);
            color: var(--vscode-input-foreground);
            border-radius: 4px;
            outline: none;
        }
        #question-input:focus {
            border-color: var(--vscode-focusBorder);
        }
        #send-btn {
            padding: 8px 14px;
            font-size: 13px;
            background: var(--vscode-button-background);
            color: var(--vscode-button-foreground);
            border: none;
            border-radius: 4px;
            cursor: pointer;
        }
        #send-btn:hover {
            background: var(--vscode-button-hoverBackground);
        }
    </style>
</head>
<body>
    <h2>🧠 SecondCortex</h2>
    <div id="chat-log"></div>
    <div id="input-area">
        <input id="question-input" type="text" placeholder="Ask about your project history..." />
        <button id="send-btn">Ask</button>
    </div>

    <script>
        const vscode = acquireVsCodeApi();
        const chatLog = document.getElementById('chat-log');
        const input = document.getElementById('question-input');
        const sendBtn = document.getElementById('send-btn');

        function addMessage(className, text) {
            const div = document.createElement('div');
            div.className = 'msg ' + className;
            div.textContent = text;
            chatLog.appendChild(div);
            chatLog.scrollTop = chatLog.scrollHeight;
        }

        function send() {
            const q = input.value.trim();
            if (!q) return;
            addMessage('user', q);
            input.value = '';
            vscode.postMessage({ type: 'ask', question: q });
        }

        sendBtn.addEventListener('click', send);
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') send();
        });

        window.addEventListener('message', (event) => {
            const msg = event.data;
            // Remove any loading indicators
            const loadingMsgs = chatLog.querySelectorAll('.loading');
            loadingMsgs.forEach(el => el.remove());

            switch (msg.type) {
                case 'loading':
                    addMessage('loading', 'Thinking...');
                    break;
                case 'answer':
                    addMessage('assistant', msg.summary);
                    break;
                case 'error':
                    addMessage('error', msg.message);
                    break;
            }
        });
    </script>
</body>
</html>`;
    }
}
