import * as vscode from 'vscode';
import { BackendClient } from '../backendClient';
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
