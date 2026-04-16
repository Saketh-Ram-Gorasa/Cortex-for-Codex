import * as vscode from 'vscode';
import { BackendClient } from '../backendClient';
import { DEMO_MODE, getMockDecisionForSymbol } from '../demoMode';
import { DecisionCache } from './decisionCache';
import { RequestDeduplicator } from './requestDeduplicator';
import { BlameResult, DecisionResult, ExtractedSymbol } from './types';

export async function fetchAndCacheDecision(
    cacheKey: string,
    document: vscode.TextDocument,
    symbol: ExtractedSymbol,
    blame: BlameResult,
    client: BackendClient,
    cache: DecisionCache,
    deduplicator: RequestDeduplicator<DecisionResult>,
    token?: vscode.CancellationToken
): Promise<DecisionResult | null> {
    if (token?.isCancellationRequested) {
        return null;
    }

    if (DEMO_MODE) {
        await sleep(2000);
        const mock = getMockDecisionForSymbol(symbol.name);
        if (!mock) {
            const fallback: DecisionResult = {
                found: false,
                summary: 'No decision history found for this symbol in current local context.',
                branchesTried: ['feat/payment-retry-v2'],
                terminalCommands: [],
                confidence: 0.75,
            };
            cache.set(cacheKey, fallback);
            return fallback;
        }

        const summaryParts: string[] = [];
        if (mock.why_retry_reduced) {
            summaryParts.push(`Why retry reduced: ${mock.why_retry_reduced}`);
        }
        if (mock.mutex_rejected) {
            summaryParts.push(`Mutex rejected: ${mock.mutex_rejected}`);
        }
        if (Array.isArray(mock.test_failures) && mock.test_failures.length > 0) {
            summaryParts.push(`Test failures: ${mock.test_failures.join('; ')}`);
        }

        const mapped: DecisionResult = {
            found: Boolean(mock.found),
            summary: summaryParts.join('\n\n') || mock.summary || 'Decision history loaded from local context.',
            branchesTried: mock.branchesTried || ['feat/payment-retry-v2'],
            terminalCommands: mock.commands_run || ['npm test -- payment.test.ts'],
            confidence: typeof mock.confidence === 'number' ? mock.confidence : 0.94,
        };

        cache.set(cacheKey, mapped);
        return mapped;
    }

    const result = await deduplicator.deduplicate(cacheKey, async () => {
        const relativeFilePath = vscode.workspace.asRelativePath(document.uri.fsPath).replace(/\\/g, '/');

        const response = await client.getDecisionArchaeology({
            filePath: relativeFilePath,
            symbolName: symbol.name,
            signature: symbol.signature,
            commitHash: blame.commitHash,
            commitMessage: blame.commitMessage,
            author: blame.author,
            timestamp: blame.timestamp.toISOString(),
        });

        if (!response) {
            return null;
        }

        const mapped: DecisionResult = {
            found: response.found,
            summary: response.summary ?? 'No workspace history found for this change.',
            branchesTried: response.branchesTried ?? [],
            terminalCommands: response.terminalCommands ?? [],
            confidence: response.confidence ?? 0,
        };

        cache.set(cacheKey, mapped);
        return mapped;
    });

    return result;
}

function sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
}
