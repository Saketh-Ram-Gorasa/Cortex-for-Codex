import * as vscode from 'vscode';
import { Debouncer } from './debouncer';
import { SemanticFirewall } from '../security/firewall';
import { SnapshotCache } from './snapshotCache';
import { BackendClient } from '../backendClient';

/**
 * CapturedSnapshot – the sanitized data structure that leaves the laptop.
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
}

/**
 * EventCapture – listens to IDE events, feeds them through the Debouncer
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
        // ── Active editor changes ──────────────────────────────────
        const editorSub = vscode.window.onDidChangeActiveTextEditor((editor) => {
            const enabled = vscode.workspace.getConfiguration('secondcortex').get<boolean>('captureEnabled', true);
            if (!enabled || !editor || editor.document.uri.scheme !== 'file') { return; }

            const filePath = editor.document.uri.fsPath;

            // Check .cortexignore BEFORE debouncing
            if (this.firewall.isIgnored(filePath)) {
                this.output.appendLine(`[EventCapture] Ignored by .cortexignore: ${filePath}`);
                return;
            }

            this.debouncer.touch(filePath, () => {
                this.captureAndShip(editor).catch((err) => {
                    this.output.appendLine(`[EventCapture] Error capturing snapshot: ${err}`);
                });
            });
        });
        this.disposables.push(editorSub);

        // ── Text document close (noise detection) ──────────────────
        const closeSub = vscode.workspace.onDidCloseTextDocument((doc) => {
            const wasMeaningful = this.debouncer.cancel(doc.uri.fsPath);
            if (!wasMeaningful) {
                this.output.appendLine(`[EventCapture] Noise filtered: ${doc.uri.fsPath}`);
            }
        });
        this.disposables.push(closeSub);

        // ── Terminal open tracking ─────────────────────────────────
        const termSub = vscode.window.onDidOpenTerminal((terminal) => {
            this.recentTerminalCommands.push(`[terminal opened] ${terminal.name}`);
        });
        this.disposables.push(termSub);

        // ── Text edits (re-touch the debouncer on typing) ──────────
        const changeSub = vscode.workspace.onDidChangeTextDocument((e) => {
            const enabled = vscode.workspace.getConfiguration('secondcortex').get<boolean>('captureEnabled', true);
            if (!enabled || e.document.uri.scheme !== 'file') { return; }

            const filePath = e.document.uri.fsPath;
            if (this.firewall.isIgnored(filePath)) { return; }

            this.debouncer.touch(filePath, () => {
                const editor = vscode.window.activeTextEditor;
                if (editor && editor.document.uri.fsPath === filePath) {
                    this.captureAndShip(editor).catch((err) => {
                        this.output.appendLine(`[EventCapture] Error capturing snapshot: ${err}`);
                    });
                }
            });
        });
        this.disposables.push(changeSub);

        context.subscriptions.push(...this.disposables);
    }

    private async captureAndShip(editor: vscode.TextEditor): Promise<void> {
        const doc = editor.document;
        const rawContent = doc.getText();

        // ── Semantic Firewall: scrub secrets ──────────────────────
        const sanitized = this.firewall.scrub(rawContent);

        // ── Build the snapshot payload ────────────────────────────
        const snapshot: CapturedSnapshot = {
            timestamp: new Date().toISOString(),
            workspaceFolder: vscode.workspace.workspaceFolders?.[0]?.name ?? 'unknown',
            activeFile: doc.uri.fsPath,
            languageId: doc.languageId,
            shadowGraph: sanitized,
            gitBranch: await this.getCurrentGitBranch(),
            terminalCommands: [...this.recentTerminalCommands],
        };

        this.output.appendLine(`[EventCapture] Snapshot ready for: ${doc.uri.fsPath}`);

        // ── Ship or cache ─────────────────────────────────────────
        const success = await this.backend.sendSnapshot(snapshot as unknown as Record<string, unknown>);
        if (!success) {
            this.output.appendLine('[EventCapture] Backend unreachable — caching locally.');
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

    dispose(): void {
        this.debouncer.dispose();
        for (const d of this.disposables) {
            d.dispose();
        }
    }
}
