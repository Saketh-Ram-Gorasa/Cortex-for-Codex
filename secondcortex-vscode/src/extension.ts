import * as vscode from 'vscode';
import { createHash } from 'crypto';
import { EventCapture } from './capture/eventCapture';
import { Debouncer } from './capture/debouncer';
import { SnapshotCache } from './capture/snapshotCache';
import { SemanticFirewall } from './security/firewall';
import { WorkspaceResurrector } from './executor/workspace';
import { SidebarProvider } from './webview/sidebar';
import { ShadowGraphPanel } from './webview/shadowGraphPanel';
import { BackendClient } from './backendClient';
import { AuthService } from './auth/authService';
import { registerDecisionArchaeology } from './decision/decisionHover';

let eventCapture: EventCapture | undefined;
let snapshotCache: SnapshotCache | undefined;

const PROJECT_SELECTION_STATE_KEY = 'secondcortex.projects.byWorkspace';

function hashWorkspacePath(workspacePath: string): string {
    return createHash('sha256').update(workspacePath).digest('hex').slice(0, 32);
}

function getWorkspaceFolder(): vscode.WorkspaceFolder | undefined {
    return vscode.workspace.workspaceFolders?.[0];
}

function getWorkspaceFingerprint(workspaceFolder: vscode.WorkspaceFolder): string {
    return hashWorkspacePath(workspaceFolder.uri.fsPath);
}

async function getRepoRemote(): Promise<string> {
    try {
        const gitExt = vscode.extensions.getExtension('vscode.git')?.exports;
        const api = gitExt?.getAPI(1);
        const repo = api?.repositories?.[0];
        const remotes = repo?.state?.remotes || [];
        const origin = remotes.find((remote: any) => remote.name === 'origin') || remotes[0];
        return String(origin?.fetchUrl || origin?.pushUrl || '').trim();
    } catch {
        return '';
    }
}

function resolveConfiguredUrl(
    config: vscode.WorkspaceConfiguration,
    key: 'backendUrl' | 'frontendUrl',
    fallback: string,
    output: vscode.OutputChannel
): string {
    const rawValue = (config.get<string>(key, fallback) || '').trim();
    try {
        const parsed = new URL(rawValue);
        if (!/^https?:$/.test(parsed.protocol)) {
            throw new Error('Protocol must be http or https');
        }
        if (parsed.hostname.includes('_')) {
            throw new Error('Hostname cannot include underscore');
        }
        return parsed.toString().replace(/\/$/, '');
    } catch {
        output.appendLine(`[SecondCortex] Invalid secondcortex.${key} value: "${rawValue}". Falling back to default: ${fallback}`);
        return fallback;
    }
}

export function activate(context: vscode.ExtensionContext) {
    const outputChannel = vscode.window.createOutputChannel('SecondCortex');
    outputChannel.appendLine('[SecondCortex] Extension activating...');

    // **AZURE OPENAI MIGRATION FIX**: Clear old cached state to force fresh backend fetch
    // This ensures users see current data instead of snapshots from before migration
    try {
        const storageFile = context.globalStorageUri.fsPath;
        const fs = require('fs');
        const path = require('path');
        const cacheFile = path.join(storageFile, 'offline-snapshots.json');
        if (fs.existsSync(cacheFile)) {
            fs.unlinkSync(cacheFile);
            outputChannel.appendLine('[SecondCortex] Cleared old offline snapshot cache on activation.');
        }
    } catch (err) {
        outputChannel.appendLine(`[SecondCortex] Warning: Could not clear snapshot cache: ${err}`);
    }

    // Configuration
    const config = vscode.workspace.getConfiguration('secondcortex');
    const backendUrl = resolveConfiguredUrl(
        config,
        'backendUrl',
        'https://sc-backend-suhaan.azurewebsites.net',
        outputChannel
    );
    const frontendUrl = resolveConfiguredUrl(
        config,
        'frontendUrl',
        'https://sc-frontend-suhaan.azurewebsites.net',
        outputChannel
    );
    const debouncerDelayMs = config.get<number>('debouncerDelayMs', 30000);
    const noiseThresholdMs = config.get<number>('noiseThresholdMs', 10000);
    outputChannel.appendLine(`[SecondCortex] Using backend URL: ${backendUrl}`);
    outputChannel.appendLine(`[SecondCortex] Using frontend URL: ${frontendUrl}`);

    // Auth
    const authService = new AuthService(context.secrets, outputChannel, backendUrl);

    // Services
    const backendClient = new BackendClient(backendUrl, outputChannel);
    backendClient.setAuthService(authService);

    let selectedProjectId: string | undefined;
    let sidebarProviderRef: SidebarProvider | undefined;

    const getProjectMap = (): Record<string, string> => {
        return context.workspaceState.get<Record<string, string>>(PROJECT_SELECTION_STATE_KEY, {});
    };

    const setProjectForWorkspace = async (workspaceFingerprint: string, projectId: string): Promise<void> => {
        const map = getProjectMap();
        map[workspaceFingerprint] = projectId;
        await context.workspaceState.update(PROJECT_SELECTION_STATE_KEY, map);
        selectedProjectId = projectId;
        outputChannel.appendLine(`[SecondCortex] Active project selected: ${projectId}`);
    };

    const selectProjectInteractive = async (): Promise<string | undefined> => {
        const projects = await backendClient.listProjects();
        if (projects.length === 0) {
            vscode.window.showWarningMessage('No projects found. Create one in dashboard before selecting.');
            return undefined;
        }

        const pick = await vscode.window.showQuickPick(
            projects.map((project) => ({
                label: project.name,
                description: `${project.visibility}${project.workspace_name ? ` • ${project.workspace_name}` : ''}`,
                projectId: project.id,
            })),
            {
                placeHolder: 'Select project for this workspace',
            }
        );

        if (!pick) {
            return undefined;
        }

        const workspaceFolder = getWorkspaceFolder();
        if (workspaceFolder) {
            await setProjectForWorkspace(getWorkspaceFingerprint(workspaceFolder), pick.projectId);
            await eventCapture?.flushDeferredSnapshots(pick.projectId);
            if (sidebarProviderRef) {
                sidebarProviderRef.notifyProjectSelected(pick.label, pick.projectId);
            }
        }
        return pick.projectId;
    };

    const resolveProjectForWorkspace = async (promptOnUnresolved: boolean): Promise<void> => {
        const workspaceFolder = getWorkspaceFolder();
        if (!workspaceFolder) {
            selectedProjectId = undefined;
            return;
        }

        const workspaceName = workspaceFolder.name;
        const workspacePathHash = hashWorkspacePath(workspaceFolder.uri.fsPath);
        const workspaceFingerprint = getWorkspaceFingerprint(workspaceFolder);
        const repoRemote = await getRepoRemote();
        const map = getProjectMap();
        const persistedProjectId = map[workspaceFingerprint];

        const resolved = await backendClient.resolveProject({
            workspaceName,
            workspacePathHash,
            repoRemote,
        });

        if (resolved?.status === 'resolved' && resolved.projectId) {
            await setProjectForWorkspace(workspaceFingerprint, resolved.projectId);
            await eventCapture?.flushDeferredSnapshots(resolved.projectId);
            return;
        }

        if (persistedProjectId) {
            selectedProjectId = persistedProjectId;
            outputChannel.appendLine(`[SecondCortex] Using persisted project selection: ${persistedProjectId}`);
            await eventCapture?.flushDeferredSnapshots(persistedProjectId);
            return;
        }

        selectedProjectId = undefined;
        outputChannel.appendLine('[SecondCortex] Project unresolved for workspace; waiting for explicit selection.');
        if (promptOnUnresolved) {
            vscode.window
                .showInformationMessage(
                    'SecondCortex needs a project selection for this workspace before sending snapshots.',
                    'Select Project'
                )
                .then((choice) => {
                    if (choice === 'Select Project') {
                        vscode.commands.executeCommand('secondcortex.selectProject');
                    }
                });
        }
    };

    const firewall = new SemanticFirewall(outputChannel);
    const debouncer = new Debouncer(debouncerDelayMs, noiseThresholdMs);
    snapshotCache = new SnapshotCache(context.globalStorageUri.fsPath, outputChannel);

    const resurrector = new WorkspaceResurrector(outputChannel);
    const shadowGraphPanel = new ShadowGraphPanel(backendClient, resurrector, outputChannel, frontendUrl);

    // Data Capture
    eventCapture = new EventCapture(
        debouncer,
        firewall,
        snapshotCache,
        backendClient,
        outputChannel,
        () => selectedProjectId,
        () => {
            vscode.window
                .showWarningMessage(
                    'Project is not selected. Choose a project to continue snapshot ingestion.',
                    'Select Project'
                )
                .then((choice) => {
                    if (choice === 'Select Project') {
                        vscode.commands.executeCommand('secondcortex.selectProject');
                    }
                });
        }
    );
    eventCapture.register(context);

    // Webview Sidebar
    const sidebarProvider = new SidebarProvider(
        context.extensionUri,
        backendClient,
        authService,
        outputChannel,
        () => vscode.commands.executeCommand('secondcortex.selectProject'),
        () => selectedProjectId
    );
    sidebarProviderRef = sidebarProvider;
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

    context.subscriptions.push(
        vscode.commands.registerCommand('secondcortex.selectProject', async () => {
            await selectProjectInteractive();
        })
    );

    context.subscriptions.push(
        vscode.workspace.onDidChangeWorkspaceFolders(async () => {
            await resolveProjectForWorkspace(true);
        })
    );

    // Offline sync
    snapshotCache.flushToBackend(backendClient).catch((err) => {
        outputChannel.appendLine(`[SecondCortex] Offline sync error: ${err}`);
    });

    resolveProjectForWorkspace(true).catch((err) => {
        outputChannel.appendLine(`[SecondCortex] Project resolver startup error: ${err}`);
    });

    outputChannel.appendLine('[SecondCortex] Extension activated successfully.');
}

export function deactivate() {
    eventCapture?.dispose();
    snapshotCache?.close();
}
