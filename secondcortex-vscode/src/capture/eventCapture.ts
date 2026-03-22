import * as vscode from 'vscode';
import * as path from 'path';
import { Debouncer } from './debouncer';
import { SemanticFirewall } from '../security/firewall';
import { SnapshotCache } from './snapshotCache';
import { BackendClient } from '../backendClient';

/**
 * CapturedSnapshot - the sanitized data structure that leaves the laptop.
 */
export interface CapturedSnapshot {
    timestamp: string;
    workspaceFolder: string;
    activeFile: string;
    languageId: string;
    /** Sanitized code context (secrets replaced with [CODE_REDACTED]) */
    shadowGraph: string;
    gitBranch: string | null;
    terminalCommands: string[];
    functionContext?: {
        activeSymbol: string | null;
        signatures: string[];
    };
}

/**
 * EventCapture - listens to IDE events, feeds them through the Debouncer
 * and Semantic Firewall, then ships sanitized snapshots to the backend
 * (or caches them offline via SnapshotCache).
 */
export class EventCapture {
    private disposables: vscode.Disposable[] = [];
    private recentTerminalCommands: string[] = [];

    constructor(
        private debouncer: Debouncer,
        private firewall: SemanticFirewall,
        private cache: SnapshotCache,
        private backend: BackendClient,
        private output: vscode.OutputChannel
    ) { }

    register(context: vscode.ExtensionContext): void {
        // Active editor changes
        const editorSub = vscode.window.onDidChangeActiveTextEditor((editor) => {
            const enabled = vscode.workspace.getConfiguration('secondcortex').get<boolean>('captureEnabled', true);
            if (!enabled || !editor || editor.document.uri.scheme !== 'file') {
                return;
            }

            const filePath = editor.document.uri.fsPath;

            // Check .cortexignore BEFORE debouncing
            if (this.firewall.isIgnored(filePath)) {
                this.output.appendLine(`[EventCapture] Ignored by .cortexignore: ${filePath}`);
                return;
            }

            this.debouncer.touch(filePath, () => {
                this.captureDocumentAndShip(editor.document).catch((err) => {
                    this.output.appendLine(`[EventCapture] Error capturing snapshot: ${err}`);
                });
            });
        });
        this.disposables.push(editorSub);

        // Text document close (noise detection)
        const closeSub = vscode.workspace.onDidCloseTextDocument((doc) => {
            const wasMeaningful = this.debouncer.cancel(doc.uri.fsPath);
            if (!wasMeaningful) {
                this.output.appendLine(`[EventCapture] Noise filtered: ${doc.uri.fsPath}`);
            }
        });
        this.disposables.push(closeSub);

        // Terminal open tracking
        const termSub = vscode.window.onDidOpenTerminal((terminal) => {
            this.recentTerminalCommands.push(`[terminal opened] ${terminal.name}`);
        });
        this.disposables.push(termSub);

        // Text edits (re-touch the debouncer on typing)
        const changeSub = vscode.workspace.onDidChangeTextDocument((e) => {
            const enabled = vscode.workspace.getConfiguration('secondcortex').get<boolean>('captureEnabled', true);
            if (!enabled || e.document.uri.scheme !== 'file') {
                return;
            }

            const filePath = e.document.uri.fsPath;
            const docUri = e.document.uri.toString();
            if (this.firewall.isIgnored(filePath)) {
                return;
            }

            this.debouncer.touch(filePath, () => {
                const doc = vscode.workspace.textDocuments.find((d) => d.uri.toString() === docUri);
                if (doc && !doc.isClosed) {
                    this.captureDocumentAndShip(doc).catch((err) => {
                        this.output.appendLine(`[EventCapture] Error capturing snapshot: ${err}`);
                    });
                }
            });
        });
        this.disposables.push(changeSub);

        // Save events (immediate capture)
        const saveSub = vscode.workspace.onDidSaveTextDocument((doc) => {
            const enabled = vscode.workspace.getConfiguration('secondcortex').get<boolean>('captureEnabled', true);
            if (!enabled || doc.uri.scheme !== 'file') {
                return;
            }

            const filePath = doc.uri.fsPath;
            if (this.firewall.isIgnored(filePath)) {
                return;
            }

            this.captureDocumentAndShip(doc).catch((err) => {
                this.output.appendLine(`[EventCapture] Error capturing saved snapshot: ${err}`);
            });
        });
        this.disposables.push(saveSub);

        // Background flush (works even when sidebar is closed)
        const flushInterval = setInterval(() => {
            this.cache.flushToBackend(this.backend).catch((err) => {
                this.output.appendLine(`[EventCapture] Background cache flush error: ${err}`);
            });
        }, 15000);
        this.disposables.push(new vscode.Disposable(() => clearInterval(flushInterval)));

        // Also flush whenever VS Code regains focus.
        const focusSub = vscode.window.onDidChangeWindowState((state) => {
            if (!state.focused) {
                return;
            }
            this.cache.flushToBackend(this.backend).catch((err) => {
                this.output.appendLine(`[EventCapture] Focus-triggered cache flush error: ${err}`);
            });
        });
        this.disposables.push(focusSub);

        // Seed context immediately so first chat query has at least one snapshot.
        const bootstrapEditor = vscode.window.activeTextEditor;
        const captureEnabled = vscode.workspace.getConfiguration('secondcortex').get<boolean>('captureEnabled', true);
        if (captureEnabled && bootstrapEditor && bootstrapEditor.document.uri.scheme === 'file') {
            const bootstrapPath = bootstrapEditor.document.uri.fsPath;
            if (!this.firewall.isIgnored(bootstrapPath)) {
                this.captureDocumentAndShip(bootstrapEditor.document).catch((err) => {
                    this.output.appendLine(`[EventCapture] Error capturing startup snapshot: ${err}`);
                });
            }
        }

        context.subscriptions.push(...this.disposables);
    }

    private async captureDocumentAndShip(doc: vscode.TextDocument): Promise<void> {
        const rawContent = doc.getText();

        // Semantic Firewall: scrub secrets
        const sanitized = this.firewall.scrub(rawContent);

        // Build snapshot payload
        const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ?? '';
        const relativePath = workspaceRoot
            ? path.relative(workspaceRoot, doc.uri.fsPath).replace(/\\/g, '/')
            : path.basename(doc.uri.fsPath);

        const functionContext = this.extractFunctionContext(doc);

        const snapshot: CapturedSnapshot = {
            timestamp: new Date().toISOString(),
            workspaceFolder: vscode.workspace.workspaceFolders?.[0]?.name ?? 'unknown',
            activeFile: relativePath,
            languageId: doc.languageId,
            shadowGraph: sanitized,
            gitBranch: await this.getCurrentGitBranch(),
            terminalCommands: [...this.recentTerminalCommands],
            functionContext,
        };

        this.output.appendLine(`[EventCapture] Snapshot ready for: ${doc.uri.fsPath}`);

        const uploadOk = await this.backend.sendSnapshot(snapshot as unknown as Record<string, unknown>);
        if (!uploadOk) {
            this.output.appendLine('[EventCapture] Backend unreachable - caching snapshot locally.');
            this.cache.store(snapshot);
        }

        // Clear terminal buffer after shipping
        this.recentTerminalCommands = [];
    }

    private async getCurrentGitBranch(): Promise<string | null> {
        try {
            const gitExt = vscode.extensions.getExtension('vscode.git')?.exports;
            const api = gitExt?.getAPI(1);
            const repo = api?.repositories[0];
            return repo?.state?.HEAD?.name ?? null;
        } catch {
            return null;
        }
    }

    private extractFunctionContext(doc: vscode.TextDocument): { activeSymbol: string | null; signatures: string[] } {
        const text = doc.getText();
        const lines = text.split(/\r?\n/);
        const signatures: string[] = [];
        const signaturesWithLine: Array<{ symbol: string; signature: string; line: number }> = [];

        const patterns = this.getFunctionPatterns(doc.languageId);
        for (let index = 0; index < lines.length; index += 1) {
            const line = lines[index];
            for (const pattern of patterns) {
                const match = line.match(pattern);
                if (!match) {
                    continue;
                }

                const symbol = String(match[1] || '').trim();
                const signature = line.trim();
                if (!symbol || !signature) {
                    continue;
                }

                if (!signatures.includes(signature)) {
                    signatures.push(signature);
                    signaturesWithLine.push({ symbol, signature, line: index });
                }
                break;
            }
        }

        const cappedSignatures = signatures.slice(0, 30);
        const activeLine = this.getActiveLineForDocument(doc);
        let activeSymbol: string | null = null;

        for (let index = signaturesWithLine.length - 1; index >= 0; index -= 1) {
            const candidate = signaturesWithLine[index];
            if (candidate.line <= activeLine) {
                activeSymbol = candidate.symbol;
                break;
            }
        }

        if (!activeSymbol && signaturesWithLine.length > 0) {
            activeSymbol = signaturesWithLine[0].symbol;
        }

        return {
            activeSymbol,
            signatures: cappedSignatures,
        };
    }

    private getActiveLineForDocument(doc: vscode.TextDocument): number {
        const activeEditor = vscode.window.activeTextEditor;
        if (activeEditor && activeEditor.document.uri.toString() === doc.uri.toString()) {
            return activeEditor.selection.active.line;
        }
        return 0;
    }

    private getFunctionPatterns(languageId: string): RegExp[] {
        switch (languageId) {
            case 'python':
                return [
                    /^\s*def\s+([A-Za-z_][\w]*)\s*\([^)]*\)\s*:/,
                    /^\s*async\s+def\s+([A-Za-z_][\w]*)\s*\([^)]*\)\s*:/,
                ];
            case 'typescript':
            case 'javascript':
            case 'typescriptreact':
            case 'javascriptreact':
                return [
                    /^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\([^)]*\)/,
                    /^\s*(?:export\s+)?const\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>/,
                ];
            case 'go':
                return [
                    /^\s*func\s+(?:\([^)]+\)\s*)?([A-Za-z_][\w]*)\s*\([^)]*\)/,
                ];
            default:
                return [
                    /^\s*(?:public|private|protected|static|async|final|virtual|override|\s)*\s*([A-Za-z_][\w]*)\s*\([^)]*\)\s*\{/,
                ];
        }
    }

    dispose(): void {
        this.debouncer.dispose();
        for (const d of this.disposables) {
            d.dispose();
        }
    }
}
