import * as fs from 'fs';
import * as path from 'path';
import * as vscode from 'vscode';

export const DEMO_MODE = true;

export interface MockSnapshotData {
    last_active_file: string;
    branch: string;
    open_files: string[];
    terminal: string;
    failing_tests: number;
    last_action: string;
    workspace?: string;
    summary?: string;
}

interface MockDecisionEntry {
    found: boolean;
    why_retry_reduced?: string;
    mutex_rejected?: string;
    test_failures?: string[];
    commands_run?: string[];
    summary?: string;
    branchesTried?: string[];
    confidence?: number;
}

interface MockMcpResponses {
    default: string;
    responses?: Record<string, string>;
}

function getWorkspaceRoot(): string {
    return vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || process.cwd();
}

function getCandidateRoots(): string[] {
    const roots = new Set<string>();
    roots.add(getWorkspaceRoot());
    roots.add(process.cwd());

    const extensionRoot = path.resolve(__dirname, '..', '..');
    const repoRoot = path.resolve(extensionRoot, '..');
    roots.add(extensionRoot);
    roots.add(repoRoot);

    return [...roots];
}

function readMockFile<T>(fileName: string, fallback: T): T {
    try {
        const candidates: string[] = [];
        for (const root of getCandidateRoots()) {
            candidates.push(path.join(root, 'context', fileName));
            candidates.push(path.join(root, 'mock', fileName));
        }

        for (const fullPath of candidates) {
            if (!fs.existsSync(fullPath)) {
                continue;
            }
            const raw = fs.readFileSync(fullPath, 'utf8');
            return JSON.parse(raw) as T;
        }

        return fallback;
    } catch {
        return fallback;
    }
}

export function getMockSnapshot(): MockSnapshotData {
    return readMockFile<MockSnapshotData>('workspaceSnapshots.json', {
        last_active_file: 'secondcortex-backend/services/payment_pipeline.py',
        branch: 'feat/payment-retry-v2',
        open_files: ['payment_pipeline.py', 'token_refresh_service.py'],
        terminal: 'pytest tests/payment_pipeline_test.py',
        failing_tests: 2,
        last_action: 'reduced retry from 5 to 3',
        workspace: 'SecondCortex',
        summary: 'You were updating the payment retry policy and token refresh race handling.',
    });
}

function getLocalDecisionHistory(): Record<string, MockDecisionEntry> {
    return readMockFile<Record<string, MockDecisionEntry>>('decisionHistory.json', {
        handleRetryPolicy: {
            found: true,
            why_retry_reduced: 'Reduced retries to lower duplicated side effects.',
            mutex_rejected: 'Mutex rejected due to queue contention and latency.',
            test_failures: ['payment.test.ts failed twice'],
            commands_run: ['npm test -- payment.test.ts'],
            summary: 'Retry policy tightened to 3 after failing tests.',
            branchesTried: ['feat/payment-retry-v2'],
            confidence: 0.9,
        },
        resolveTokenRefreshRace: {
            found: true,
            why_retry_reduced: 'Refresh attempts were constrained to prevent duplicate token writes under burst load.',
            mutex_rejected: 'Global lock caused queue buildup; switched to key-scoped in-flight refresh tracking.',
            test_failures: ['tokenRefresh.test.ts failed under concurrent refresh simulation'],
            commands_run: ['npm test -- tokenRefresh.test.ts'],
            summary: 'Token refresh now deduplicates in-flight requests and applies bounded retries.',
            branchesTried: ['feat/payment-refresh-dedupe'],
            confidence: 0.9,
        },
    });
}

export function getMockDecisionForSymbol(symbolName: string): MockDecisionEntry | null {
    const normalized = String(symbolName || '').trim();
    if (!normalized) {
        return null;
    }

    const data = getLocalDecisionHistory();
    if (data[normalized]) {
        return data[normalized];
    }

    const snakeCase = normalized
        .replace(/([a-z0-9])([A-Z])/g, '$1_$2')
        .replace(/-/g, '_')
        .toLowerCase();
    if (data[snakeCase]) {
        return data[snakeCase];
    }

    const camelCase = normalized.replace(/_([a-z])/g, (_, ch: string) => ch.toUpperCase());
    if (data[camelCase]) {
        return data[camelCase];
    }

    return null;
}

export function getMockMcpResponse(question: string): string {
    const data = readMockFile<MockMcpResponses>('mcpResponses.json', {
        default: 'Context response loaded from local workspace memory.',
        responses: {},
    });

    const normalized = (question || '').toLowerCase();
    const responseMap = data.responses || {};

    if (normalized.includes('status') && responseMap.status) {
        return responseMap.status;
    }
    if (normalized.includes('retry') && responseMap.retry) {
        return responseMap.retry;
    }
    if (normalized.includes('workspace') && responseMap.workspace) {
        return responseMap.workspace;
    }

    return data.default;
}

export function getDemoSummaryFromSnapshot(): string {
    const snapshot = getMockSnapshot();
    return [
        `Last active file: ${snapshot.last_active_file}`,
        `Branch: ${snapshot.branch}`,
        `Open files: ${snapshot.open_files.join(', ')}`,
        `Terminal: ${snapshot.terminal}`,
        `Failing tests: ${snapshot.failing_tests}`,
        `Last action: ${snapshot.last_action}`,
    ].join('\n');
}
