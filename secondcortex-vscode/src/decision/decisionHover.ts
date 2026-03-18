import * as vscode from 'vscode';
import { BackendClient } from '../backendClient';
import { BackgroundPrefetcher } from './backgroundPrefetcher';
import { DecisionCache } from './decisionCache';
import { runGitBlame } from './gitBlame';
import { formatHover, formatUnavailableHover } from './hoverFormatter';
import { RequestDeduplicator } from './requestDeduplicator';
import { fetchAndCacheDecision } from './service';
import { extractSymbol, SUPPORTED_LANGUAGES } from './symbolExtractor';
import { BlameResult, DecisionResult } from './types';

export function registerDecisionArchaeology(
    context: vscode.ExtensionContext,
    client: BackendClient
): vscode.Disposable[] {
    const cache = new DecisionCache();
    const deduplicator = new RequestDeduplicator<DecisionResult>();
    const prefetcher = new BackgroundPrefetcher(client, cache, deduplicator);

    const disposables: vscode.Disposable[] = [];

    for (const language of SUPPORTED_LANGUAGES) {
        const provider = vscode.languages.registerHoverProvider(language, {
            async provideHover(document, position, token) {
                return provideDecisionHover(
                    document,
                    position,
                    token,
                    client,
                    cache,
                    deduplicator
                );
            },
        });

        disposables.push(provider);
    }

    disposables.push(
        vscode.workspace.onDidOpenTextDocument((document) => {
            if (SUPPORTED_LANGUAGES.includes(document.languageId)) {
                prefetcher.scheduleFile(document);
            }
        })
    );

    for (const document of vscode.workspace.textDocuments) {
        if (SUPPORTED_LANGUAGES.includes(document.languageId)) {
            prefetcher.scheduleFile(document);
        }
    }

    context.subscriptions.push(...disposables);
    return disposables;
}

async function provideDecisionHover(
    document: vscode.TextDocument,
    position: vscode.Position,
    token: vscode.CancellationToken,
    client: BackendClient,
    cache: DecisionCache,
    deduplicator: RequestDeduplicator<DecisionResult>
): Promise<vscode.Hover | null> {
    const symbol = extractSymbol(document, position);
    if (!symbol) {
        return null;
    }

    const blame = await runGitBlame(document.uri.fsPath, symbol.range) ?? buildFallbackBlame();

    const cacheKey = cache.buildKey(document.uri.fsPath, symbol.name, blame.commitHash);
    const cached = cache.get(cacheKey);
    if (cached) {
        return formatHover(cached, symbol);
    }

    const fetched = await fetchAndCacheDecision(
        cacheKey,
        document,
        symbol,
        blame,
        client,
        cache,
        deduplicator,
        token
    );

    if (!fetched) {
        return formatUnavailableHover(
            symbol,
            '*Could not fetch decision context right now. Check backend connectivity and session auth.*'
        );
    }

    return formatHover(fetched, symbol);
}

function buildFallbackBlame(): BlameResult {
    return {
        commitHash: 'no-git',
        author: 'Unknown',
        timestamp: new Date(),
        commitMessage: '',
        linesChanged: 0,
    };
}
