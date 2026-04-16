import * as vscode from 'vscode';
import * as path from 'path';
import { Debouncer } from './debouncer';
import { SemanticFirewall } from '../security/firewall';
import { SnapshotCache } from './snapshotCache';
import { BackendClient } from '../backendClient';
import { DEMO_MODE } from '../demoMode';

export type CaptureLevel = 'base' | 'medium' | 'full' | 'ultra';

const ULTRA_MAX_EXTRA_FILES = 3;
const ULTRA_MAX_CHARS_PER_FILE = 2000;
const ULTRA_MAX_TOTAL_EXTRA_CHARS = 6000;

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
    projectId?: string;
    terminalCommands: string[];
    captureLevel: CaptureLevel;
    captureMeta: Record<string, unknown>;
    functionContext?: {
        activeSymbol: string | null;
        signatures?: string[];
        comments?: Array<{
            type: 'inline' | 'block' | 'todo' | 'fixme' | 'hack';
            content: string;
            line: number;
        }>;
        intentSummary?: string;
    };
}

interface CommentSignal {
    type: 'inline' | 'block' | 'todo' | 'fixme' | 'hack';
    content: string;
    line: number;
}

interface LevelBuildResult {
    shadowGraph: string;
    functionContext: CapturedSnapshot['functionContext'];
    captureMeta: Record<string, unknown>;
}

/**
 * EventCapture - listens to IDE events, feeds them through the Debouncer
 * and Semantic Firewall, then ships sanitized snapshots to the backend
 * (or caches them offline via SnapshotCache).
 */
export class EventCapture {
    private disposables: vscode.Disposable[] = [];
    private recentTerminalCommands: string[] = [];
    private deferredSnapshots: CapturedSnapshot[] = [];
    private lastProjectPromptAt = 0;

    constructor(
        private debouncer: Debouncer,
        private firewall: SemanticFirewall,
        private cache: SnapshotCache,
        private backend: BackendClient,
        private output: vscode.OutputChannel,
        private getSelectedProjectId?: () => string | undefined,
        private onProjectSelectionRequired?: () => void
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
                this.output.appendLine('[Capture Engine]');
                this.output.appendLine('Skipped (cortexignore)');
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
                this.output.appendLine('[Capture Engine]');
                this.output.appendLine('Skipped (cortexignore)');
                return;
            }

            if (DEMO_MODE) {
                this.output.appendLine('[Capture Engine]');
                this.output.appendLine('Event: File Edit');
                this.output.appendLine('[Debouncer] Passed (30s threshold)');
                this.captureDocumentAndShip(e.document).catch((err) => {
                    this.output.appendLine(`[EventCapture] Error capturing snapshot: ${err}`);
                });
                return;
            }

            this.debouncer.touch(filePath, () => {
                this.output.appendLine('[Capture Engine]');
                this.output.appendLine('Event: File Edit');
                this.output.appendLine('[Debouncer] Passed (30s threshold)');
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
                this.output.appendLine('[Capture Engine]');
                this.output.appendLine('Skipped (cortexignore)');
                return;
            }

            const text = doc.getText();
            if (text.includes('sk_live_') || text.includes('API_KEY')) {
                this.output.appendLine('[Semantic Firewall]');
                this.output.appendLine('Detected sensitive token');
                this.output.appendLine('Redacted → [CODE_REDACTED]');
            }

            this.captureDocumentAndShip(doc).catch((err) => {
                this.output.appendLine(`[EventCapture] Error capturing saved snapshot: ${err}`);
            });
        });
        this.disposables.push(saveSub);

        // Background flush (works even when sidebar is closed)
        if (!DEMO_MODE) {
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
        }

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
        const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ?? '';
        const relativePath = workspaceRoot
            ? path.relative(workspaceRoot, doc.uri.fsPath).replace(/\\/g, '/')
            : path.basename(doc.uri.fsPath);

        const captureLevel = this.getCaptureLevel();
        const rawContent = doc.getText();
        this.output.appendLine(`[Agent:Planning] Preparing snapshot for ${doc.uri.fsPath}`);
        const sanitized = this.firewall.scrub(rawContent);
        this.output.appendLine(`[Agent:Retrieving] Semantic firewall scan complete for ${doc.uri.fsPath}`);

        const levelBuild = await this.buildSnapshotForLevel({
            doc,
            relativePath,
            captureLevel,
            sanitizedContent: sanitized,
        });

        const snapshot: CapturedSnapshot = {
            timestamp: new Date().toISOString(),
            workspaceFolder: vscode.workspace.workspaceFolders?.[0]?.name ?? 'unknown',
            activeFile: relativePath,
            languageId: doc.languageId,
            shadowGraph: levelBuild.shadowGraph,
            gitBranch: await this.getCurrentGitBranch(),
            terminalCommands: [...this.recentTerminalCommands],
            captureLevel,
            captureMeta: levelBuild.captureMeta,
            functionContext: levelBuild.functionContext,
        };

        const selectedProjectId = this.getSelectedProjectId?.();
        if (!selectedProjectId) {
            this.deferredSnapshots.push(snapshot);
            this.output.appendLine('[EventCapture] Snapshot deferred: no active project selection.');
            const now = Date.now();
            if (now - this.lastProjectPromptAt > 20000) {
                this.lastProjectPromptAt = now;
                this.onProjectSelectionRequired?.();
            }
            this.recentTerminalCommands = [];
            return;
        }

        snapshot.projectId = selectedProjectId;

        this.output.appendLine(`[EventCapture] Snapshot ready for: ${doc.uri.fsPath} (${captureLevel})`);

        await this.flushDeferredSnapshots(selectedProjectId);
        await this.sendOrCache(snapshot);

        // Clear terminal buffer after shipping
        this.recentTerminalCommands = [];
    }

    private getCaptureLevel(): CaptureLevel {
        const configured = String(vscode.workspace.getConfiguration('secondcortex').get<string>('captureLevel', 'medium') || '').trim().toLowerCase();
        if (configured === 'base' || configured === 'medium' || configured === 'full' || configured === 'ultra') {
            return configured;
        }
        return 'medium';
    }

    private async buildSnapshotForLevel(args: {
        doc: vscode.TextDocument;
        relativePath: string;
        captureLevel: CaptureLevel;
        sanitizedContent: string;
    }): Promise<LevelBuildResult> {
        const { doc, relativePath, captureLevel, sanitizedContent } = args;
        const fullFunctionContext = this.extractFunctionContext(doc);
        const commentSignals = this.extractCommentSignals(sanitizedContent);
        const intentSummary = this.buildIntentSummary(relativePath, fullFunctionContext, commentSignals);

        if (captureLevel === 'base') {
            const functionContext: CapturedSnapshot['functionContext'] = {
                activeSymbol: fullFunctionContext.activeSymbol,
            };

            return {
                shadowGraph: [
                    'Capture level: base',
                    `File: ${relativePath}`,
                    `Language: ${doc.languageId}`,
                    `Active symbol: ${fullFunctionContext.activeSymbol || 'none'}`,
                    'Code body omitted by policy.',
                ].join('\n'),
                functionContext,
                captureMeta: {
                    includedArtifacts: {
                        metadata: true,
                        comments: false,
                        functionSignatures: false,
                        activeFileContent: false,
                        openFileContext: false,
                    },
                    signatureCount: 0,
                    commentCount: 0,
                    todoCount: 0,
                    truncated: false,
                },
            };
        }

        if (captureLevel === 'medium') {
            const functionContext: CapturedSnapshot['functionContext'] = {
                activeSymbol: fullFunctionContext.activeSymbol,
                signatures: fullFunctionContext.signatures,
                comments: commentSignals.slice(0, 20),
                intentSummary,
            };

            const shadowGraph = this.buildMediumShadowGraph(relativePath, fullFunctionContext, commentSignals, intentSummary, sanitizedContent);
            return {
                shadowGraph,
                functionContext,
                captureMeta: {
                    includedArtifacts: {
                        metadata: true,
                        comments: true,
                        functionSignatures: true,
                        activeFileContent: false,
                        openFileContext: false,
                    },
                    signatureCount: fullFunctionContext.signatures.length,
                    commentCount: commentSignals.length,
                    todoCount: commentSignals.filter((signal) => signal.type === 'todo' || signal.type === 'fixme' || signal.type === 'hack').length,
                    truncated: false,
                },
            };
        }

        if (captureLevel === 'full') {
            const functionContext: CapturedSnapshot['functionContext'] = {
                activeSymbol: fullFunctionContext.activeSymbol,
                signatures: fullFunctionContext.signatures,
                comments: commentSignals.slice(0, 30),
                intentSummary,
            };

            return {
                shadowGraph: sanitizedContent,
                functionContext,
                captureMeta: {
                    includedArtifacts: {
                        metadata: true,
                        comments: true,
                        functionSignatures: true,
                        activeFileContent: true,
                        openFileContext: false,
                    },
                    signatureCount: fullFunctionContext.signatures.length,
                    commentCount: commentSignals.length,
                    todoCount: commentSignals.filter((signal) => signal.type === 'todo' || signal.type === 'fixme' || signal.type === 'hack').length,
                    truncated: false,
                },
            };
        }

        const ultraContext = this.collectUltraOpenFileContext(doc);
        const shadowGraph = ultraContext.text
            ? `${sanitizedContent}\n\n[ULTRA_EXTRA_OPEN_FILE_CONTEXT]\n${ultraContext.text}`
            : sanitizedContent;

        const functionContext: CapturedSnapshot['functionContext'] = {
            activeSymbol: fullFunctionContext.activeSymbol,
            signatures: fullFunctionContext.signatures,
            comments: commentSignals.slice(0, 30),
            intentSummary,
        };

        return {
            shadowGraph,
            functionContext,
            captureMeta: {
                includedArtifacts: {
                    metadata: true,
                    comments: true,
                    functionSignatures: true,
                    activeFileContent: true,
                    openFileContext: true,
                },
                signatureCount: fullFunctionContext.signatures.length,
                commentCount: commentSignals.length,
                todoCount: commentSignals.filter((signal) => signal.type === 'todo' || signal.type === 'fixme' || signal.type === 'hack').length,
                openFileContext: {
                    filesConsidered: ultraContext.filesConsidered,
                    filesIncluded: ultraContext.filesIncluded,
                    charsIncluded: ultraContext.charsIncluded,
                },
                limits: {
                    maxExtraFiles: ULTRA_MAX_EXTRA_FILES,
                    maxCharsPerFile: ULTRA_MAX_CHARS_PER_FILE,
                    maxTotalExtraChars: ULTRA_MAX_TOTAL_EXTRA_CHARS,
                },
                truncated: ultraContext.truncated,
                truncationReasons: ultraContext.truncationReasons,
            },
        };
    }

    private buildMediumShadowGraph(
        relativePath: string,
        functionContext: { activeSymbol: string | null; signatures: string[] },
        commentSignals: CommentSignal[],
        intentSummary: string,
        sanitizedContent: string,
    ): string {
        const commentLines = commentSignals
            .slice(0, 10)
            .map((signal) => `[${signal.type}] L${signal.line + 1}: ${signal.content}`)
            .join('\n');

        const signatures = functionContext.signatures.slice(0, 12).join('\n') || 'none';

        const fragmentLines = sanitizedContent
            .split(/\r?\n/)
            .map((line) => line.trim())
            .filter((line) => line.length > 0)
            .slice(0, 20)
            .join('\n')
            .slice(0, 800);

        return [
            'Capture level: medium',
            `File: ${relativePath}`,
            `Intent summary: ${intentSummary}`,
            `Active symbol: ${functionContext.activeSymbol || 'none'}`,
            'Function signatures:',
            signatures,
            'Comment signals:',
            commentLines || 'none',
            'Code intent fragment:',
            fragmentLines || 'none',
        ].join('\n');
    }

    private buildIntentSummary(
        relativePath: string,
        functionContext: { activeSymbol: string | null; signatures: string[] },
        commentSignals: CommentSignal[],
    ): string {
        const todoCount = commentSignals.filter((signal) => signal.type === 'todo' || signal.type === 'fixme' || signal.type === 'hack').length;
        const commentCount = commentSignals.length;
        return [
            `Editing ${relativePath}`,
            functionContext.activeSymbol ? `around symbol ${functionContext.activeSymbol}` : 'without an active symbol',
            `with ${functionContext.signatures.length} discovered function signatures`,
            `and ${commentCount} comment signals (${todoCount} todo-like markers).`,
        ].join(' ');
    }

    private extractCommentSignals(sanitizedContent: string): CommentSignal[] {
        const lines = sanitizedContent.split(/\r?\n/);
        const results: CommentSignal[] = [];
        let inBlock = false;

        for (let index = 0; index < lines.length; index += 1) {
            const rawLine = lines[index] || '';
            const trimmed = rawLine.trim();
            if (!trimmed) {
                continue;
            }

            const startsBlock = trimmed.includes('/*');
            const endsBlock = trimmed.includes('*/');
            if (startsBlock) {
                inBlock = true;
            }

            const inlineMatch = trimmed.match(/(^|\s)\/\/(.*)$/);
            if (inlineMatch) {
                const content = (inlineMatch[2] || '').trim();
                if (content) {
                    results.push({
                        type: this.detectCommentType(content),
                        content: content.slice(0, 240),
                        line: index,
                    });
                }
            } else if (trimmed.startsWith('#')) {
                const content = trimmed.replace(/^#+/, '').trim();
                if (content) {
                    results.push({
                        type: this.detectCommentType(content),
                        content: content.slice(0, 240),
                        line: index,
                    });
                }
            } else if (inBlock || trimmed.startsWith('*')) {
                const content = trimmed
                    .replace(/^\/+\*?/, '')
                    .replace(/\*+\/$/, '')
                    .replace(/^\*+/, '')
                    .trim();
                if (content) {
                    results.push({
                        type: this.detectCommentType(content, true),
                        content: content.slice(0, 240),
                        line: index,
                    });
                }
            }

            if (endsBlock) {
                inBlock = false;
            }

            if (results.length >= 80) {
                break;
            }
        }

        return results;
    }

    private detectCommentType(content: string, isBlock: boolean = false): CommentSignal['type'] {
        const lowered = content.toLowerCase();
        if (lowered.includes('todo')) {
            return 'todo';
        }
        if (lowered.includes('fixme')) {
            return 'fixme';
        }
        if (lowered.includes('hack')) {
            return 'hack';
        }
        return isBlock ? 'block' : 'inline';
    }

    private collectUltraOpenFileContext(activeDoc: vscode.TextDocument): {
        text: string;
        filesConsidered: number;
        filesIncluded: number;
        charsIncluded: number;
        truncated: boolean;
        truncationReasons: string[];
    } {
        const uniqueDocs = new Map<string, vscode.TextDocument>();
        for (const editor of vscode.window.visibleTextEditors) {
            const doc = editor.document;
            if (doc.uri.scheme !== 'file') {
                continue;
            }
            if (doc.uri.toString() === activeDoc.uri.toString()) {
                continue;
            }
            if (this.firewall.isIgnored(doc.uri.fsPath)) {
                continue;
            }
            if (!uniqueDocs.has(doc.uri.toString())) {
                uniqueDocs.set(doc.uri.toString(), doc);
            }
        }

        const docs = Array.from(uniqueDocs.values());
        const truncationReasons: string[] = [];

        let remainingChars = ULTRA_MAX_TOTAL_EXTRA_CHARS;
        let filesIncluded = 0;
        let charsIncluded = 0;
        const chunks: string[] = [];

        const selectedDocs = docs.slice(0, ULTRA_MAX_EXTRA_FILES);
        if (docs.length > ULTRA_MAX_EXTRA_FILES) {
            truncationReasons.push('extra_file_limit_reached');
        }

        for (const doc of selectedDocs) {
            if (remainingChars <= 0) {
                truncationReasons.push('total_char_limit_reached');
                break;
            }

            const sanitized = this.firewall.scrub(doc.getText());
            const perFileSlice = sanitized.slice(0, ULTRA_MAX_CHARS_PER_FILE);
            if (sanitized.length > ULTRA_MAX_CHARS_PER_FILE) {
                truncationReasons.push(`per_file_char_limit:${path.basename(doc.uri.fsPath)}`);
            }

            const finalSlice = perFileSlice.slice(0, remainingChars);
            if (!finalSlice.trim()) {
                continue;
            }

            const displayPath = this.toRelativePath(doc.uri.fsPath);
            chunks.push([
                `--- file: ${displayPath} ---`,
                finalSlice,
            ].join('\n'));

            filesIncluded += 1;
            charsIncluded += finalSlice.length;
            remainingChars -= finalSlice.length;

            if (finalSlice.length < perFileSlice.length || remainingChars <= 0) {
                truncationReasons.push('total_char_limit_reached');
                break;
            }
        }

        return {
            text: chunks.join('\n\n'),
            filesConsidered: docs.length,
            filesIncluded,
            charsIncluded,
            truncated: truncationReasons.length > 0,
            truncationReasons,
        };
    }

    private toRelativePath(fsPath: string): string {
        const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ?? '';
        if (!workspaceRoot) {
            return path.basename(fsPath);
        }
        return path.relative(workspaceRoot, fsPath).replace(/\\/g, '/');
    }

    async flushDeferredSnapshots(projectId?: string): Promise<void> {
        const activeProjectId = projectId || this.getSelectedProjectId?.();
        if (!activeProjectId || this.deferredSnapshots.length === 0) {
            return;
        }

        const pending = [...this.deferredSnapshots];
        this.deferredSnapshots = [];

        for (const snapshot of pending) {
            snapshot.projectId = activeProjectId;
            await this.sendOrCache(snapshot);
        }
    }

    private async sendOrCache(snapshot: CapturedSnapshot): Promise<void> {
        if (DEMO_MODE) {
            this.cache.store(snapshot);
            this.output.appendLine('Snapshot stored locally');
            this.output.appendLine('[Sync] Local mode active; remote sync skipped');
            return;
        }

        this.output.appendLine(`[Agent:Executing] Uploading snapshot for ${snapshot.activeFile}`);
        const uploadOk = await this.backend.sendSnapshot(snapshot as unknown as Record<string, unknown>);
        if (!uploadOk) {
            this.output.appendLine('[Agent:Executing] Upload failed - caching snapshot locally.');
            this.output.appendLine('[EventCapture] Backend unreachable - caching snapshot locally.');
            this.cache.store(snapshot);
        }
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
