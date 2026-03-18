import * as vscode from 'vscode';
import { EventCapture, SnapshotSyncClient } from './capture/eventCapture';
import { Debouncer } from './capture/debouncer';
import { SnapshotCache } from './capture/snapshotCache';
import { SemanticFirewall } from './security/firewall';
import { WorkspaceResurrector } from './executor/workspace';
import { SidebarProvider } from './webview/sidebar';
import { ShadowGraphPanel } from './webview/shadowGraphPanel';
import { BackendClient } from './backendClient';
import { AuthService } from './auth/authService';
import { registerDecisionArchaeology } from './decision/decisionHover';
import type { SyncStatus } from './sync/powerSyncClient';

interface PowerSyncLifecycle extends SnapshotSyncClient {
    close(): void;
}

let eventCapture: EventCapture | undefined;
let snapshotCache: SnapshotCache | undefined;
let powerSyncClient: PowerSyncLifecycle | undefined;
let syncStatusBar: vscode.StatusBarItem | undefined;

function renderSyncStatus(status: SyncStatus): void {
    if (!syncStatusBar) {
        return;
    }

    if (status.state === 'synced') {
        syncStatusBar.text = '$(check) SecondCortex: Synced';
        syncStatusBar.color = new vscode.ThemeColor('charts.green');
        syncStatusBar.tooltip = 'SecondCortex sync is up to date';
        return;
    }

    if (status.state === 'syncing') {
        syncStatusBar.text = `$(sync~spin) SecondCortex: Syncing... (${status.pending} pending)`;
        syncStatusBar.color = new vscode.ThemeColor('charts.yellow');
        syncStatusBar.tooltip = 'SecondCortex is syncing pending snapshots';
        return;
    }

    syncStatusBar.text = `$(cloud-offline) SecondCortex: Offline - ${status.pending} queued`;
    syncStatusBar.color = new vscode.ThemeColor('disabledForeground');
    syncStatusBar.tooltip = 'SecondCortex is offline. Local queue will sync when connectivity resumes';
}

function setSyncFallbackStatus(): void {
    if (!syncStatusBar) {
        return;
    }

    syncStatusBar.text = '$(warning) SecondCortex: HTTP fallback';
    syncStatusBar.color = new vscode.ThemeColor('charts.yellow');
    syncStatusBar.tooltip = 'PowerSync is unavailable. Using direct snapshot upload and offline cache fallback.';
}

function setHttpModeStatus(): void {
    if (!syncStatusBar) {
        return;
    }

    syncStatusBar.text = '$(cloud) SecondCortex: HTTP mode';
    syncStatusBar.color = new vscode.ThemeColor('disabledForeground');
    syncStatusBar.tooltip = 'PowerSync is disabled. Using direct snapshot upload and offline cache fallback.';
}

function tryCreatePowerSyncClient(
    storagePath: string,
    backendClient: BackendClient,
    outputChannel: vscode.OutputChannel
): PowerSyncLifecycle | undefined {
    try {
        const syncModule = require('./sync/powerSyncClient') as typeof import('./sync/powerSyncClient');
        return new syncModule.PowerSyncClient(storagePath, backendClient, outputChannel, renderSyncStatus) as PowerSyncLifecycle;
    } catch (err) {
        outputChannel.appendLine(`[SecondCortex] PowerSync unavailable; continuing in HTTP fallback mode: ${err}`);
        setSyncFallbackStatus();
        return undefined;
    }
}

export function activate(context: vscode.ExtensionContext) {
    const outputChannel = vscode.window.createOutputChannel('SecondCortex');
    outputChannel.appendLine('[SecondCortex] Extension activating...');

    // Configuration
    const config = vscode.workspace.getConfiguration('secondcortex');
    const backendUrl = config.get<string>('backendUrl', 'https://sc-backend-suhaan.azurewebsites.net');
    const frontendUrl = config.get<string>('frontendUrl', 'https://sc-frontend-suhaan.azurewebsites.net');
    const debouncerDelayMs = config.get<number>('debouncerDelayMs', 30000);
    const noiseThresholdMs = config.get<number>('noiseThresholdMs', 10000);
    const enablePowerSync = config.get<boolean>('enablePowerSync', false);

    // Auth
    const authService = new AuthService(context.secrets, outputChannel, backendUrl);

    // Services
    const backendClient = new BackendClient(backendUrl, outputChannel);
    backendClient.setAuthService(authService);

    syncStatusBar = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
    syncStatusBar.name = 'SecondCortex Sync';
    syncStatusBar.show();
    context.subscriptions.push(syncStatusBar);

    const firewall = new SemanticFirewall(outputChannel);
    const debouncer = new Debouncer(debouncerDelayMs, noiseThresholdMs);
    snapshotCache = new SnapshotCache(context.globalStorageUri.fsPath, outputChannel);
    let syncClient: SnapshotSyncClient | undefined;
    if (enablePowerSync) {
        powerSyncClient = tryCreatePowerSyncClient(context.globalStorageUri.fsPath, backendClient, outputChannel);
        syncClient = powerSyncClient;
        if (!powerSyncClient) {
            setSyncFallbackStatus();
        }
    } else {
        powerSyncClient = undefined;
        setHttpModeStatus();
        outputChannel.appendLine('[SecondCortex] PowerSync is disabled by configuration. Running in HTTP mode.');
    }

    const resurrector = new WorkspaceResurrector(outputChannel);
    const shadowGraphPanel = new ShadowGraphPanel(backendClient, resurrector, outputChannel, frontendUrl);

    // Data Capture
    eventCapture = new EventCapture(debouncer, firewall, snapshotCache, syncClient, backendClient, authService, outputChannel);
    eventCapture.register(context);

    // Webview Sidebar
    const sidebarProvider = new SidebarProvider(context.extensionUri, backendClient, authService, outputChannel);
    context.subscriptions.push(
        vscode.window.registerWebviewViewProvider('secondcortex.chatView', sidebarProvider)
    );

    // Decision Archaeology Hover
    registerDecisionArchaeology(context, backendClient);
    outputChannel.appendLine('[SecondCortex] Decision Archaeology hover provider registered.');

    // Commands
    context.subscriptions.push(
        vscode.commands.registerCommand('secondcortex.login', async () => {
            // The sidebar will handle the actual login UI
            vscode.commands.executeCommand('secondcortex.chatView.focus');
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('secondcortex.logout', async () => {
            await authService.logout();
            sidebarProvider.refreshView();
            vscode.window.showInformationMessage('SecondCortex: Logged out successfully.');
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('secondcortex.resurrectWorkspace', async () => {
            const answer = await vscode.window.showInputBox({
                prompt: 'Enter the branch or snapshot ID to resurrect',
                placeHolder: 'e.g., feature/auth-fix or snapshot-abc123',
            });
            if (answer) {
                const currentWorkspace = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
                await resurrector.executeFromQuery(answer, backendClient, currentWorkspace);
            }
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('secondcortex.askQuestion', async () => {
            const question = await vscode.window.showInputBox({
                prompt: 'Ask SecondCortex a question about your project history',
                placeHolder: 'e.g., Why did we roll back the payment module?',
            });
            if (question) {
                const response = await backendClient.askQuestion(question);
                outputChannel.appendLine(`[SecondCortex] Answer: ${JSON.stringify(response)}`);
                vscode.window.showInformationMessage(`SecondCortex: ${response?.summary || 'No answer available.'}`);
            }
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('secondcortex.openShadowGraph', async () => {
            shadowGraphPanel.show();
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('secondcortex.toggleCapture', () => {
            const current = vscode.workspace.getConfiguration('secondcortex').get<boolean>('captureEnabled', true);
            vscode.workspace.getConfiguration('secondcortex').update('captureEnabled', !current, vscode.ConfigurationTarget.Global);
            vscode.window.showInformationMessage(`SecondCortex capture ${!current ? 'enabled' : 'disabled'}.`);
        })
    );

    // Offline sync
    snapshotCache.flushToBackend(backendClient).catch((err) => {
        outputChannel.appendLine(`[SecondCortex] Offline sync error: ${err}`);
    });

    if (powerSyncClient) {
        powerSyncClient.syncPending().catch((err) => {
            outputChannel.appendLine(`[SecondCortex] PowerSync bootstrap error: ${err}`);
        });
    } else {
        outputChannel.appendLine('[SecondCortex] PowerSync inactive. Running with HTTP snapshot fallback only.');
    }

    outputChannel.appendLine('[SecondCortex] Extension activated successfully.');
}

export function deactivate() {
    eventCapture?.dispose();
    snapshotCache?.close();
    powerSyncClient?.close();
}
