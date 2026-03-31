import * as vscode from 'vscode';
import { createHash } from 'crypto';
import { execFile } from 'child_process';
import * as path from 'path';
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
import { DEMO_MODE, getMockMcpResponse } from './demoMode';

let eventCapture: EventCapture | undefined;
let snapshotCache: SnapshotCache | undefined;

const PROJECT_SELECTION_STATE_KEY = 'secondcortex.projects.byWorkspace';

interface GitIngestCommandRequest {
    repoPath: string;
    projectId?: string;
    projectName?: string;
    backendUrl?: string;
    maxCommits: number;
    maxPullRequests: number;
    includePullRequests: boolean;
}

function hashWorkspacePath(workspacePath: string): string {
    return createHash('sha256').update(workspacePath).digest('hex').slice(0, 32);
}

function getWorkspaceFolder(): vscode.WorkspaceFolder | undefined {
    return vscode.workspace.workspaceFolders?.[0];
}

function getWorkspaceFingerprint(workspaceFolder: vscode.WorkspaceFolder): string {
    return hashWorkspacePath(workspaceFolder.uri.fsPath);
}

function normalizeFsPath(fsPath: string): string {
    const normalized = path.normalize(path.resolve(fsPath));
    return process.platform === 'win32' ? normalized.toLowerCase() : normalized;
}

function pathsMatch(left: string | undefined, right: string | undefined): boolean {
    if (!left || !right) {
        return false;
    }
    return normalizeFsPath(left) === normalizeFsPath(right);
}

function parseIntegerFlag(value: string | undefined | null, fallback: number, minimum: number): number {
    const normalized = String(value || '').trim();
    if (!normalized) {
        return fallback;
    }
    const parsed = Number(normalized);
    if (Number.isFinite(parsed) && parsed >= minimum) {
        return Math.floor(parsed);
    }
    return fallback;
}

function parseBooleanFlag(value: string | undefined | null, fallback: boolean): boolean {
    const normalized = String(value || '').trim().toLowerCase();
    if (!normalized) {
        return fallback;
    }
    if (['1', 'true', 'yes', 'on'].includes(normalized)) {
        return true;
    }
    if (['0', 'false', 'no', 'off'].includes(normalized)) {
        return false;
    }
    return fallback;
}

function parseGitIngestUri(uri: vscode.Uri): GitIngestCommandRequest {
    const params = new URLSearchParams(uri.query);
    return {
        repoPath: String(params.get('repoPath') || '').trim(),
        projectId: String(params.get('projectId') || '').trim() || undefined,
        projectName: String(params.get('projectName') || '').trim() || undefined,
        backendUrl: String(params.get('backendUrl') || '').trim() || undefined,
        maxCommits: parseIntegerFlag(params.get('maxCommits'), 300, 1),
        maxPullRequests: parseIntegerFlag(params.get('maxPullRequests'), 30, 0),
        includePullRequests: parseBooleanFlag(params.get('includePullRequests'), true),
    };
}

function parseResurrectTarget(uri: vscode.Uri): string {
    const params = new URLSearchParams(uri.query);
    const target = String(params.get('target') || '').trim();
    if (target) {
        return target;
    }
    return decodeURIComponent(uri.query || '').trim() || 'latest';
}

async function getRepoRemoteForPath(repoPath: string): Promise<string> {
    return new Promise((resolve) => {
        execFile(
            'git',
            ['-C', repoPath, 'remote', 'get-url', 'origin'],
            { windowsHide: true },
            (error, stdout) => {
                if (error) {
                    resolve('');
                    return;
                }
                resolve(String(stdout || '').trim());
            }
        );
    });
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
    if (DEMO_MODE) {
        outputChannel.appendLine('[SecondCortex] Local deterministic mode active - backend and network actions are bypassed.');
    }

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

    const selectProjectInteractive = async (options?: {
        baseUrl?: string;
        persistSelection?: boolean;
        placeHolder?: string;
    }): Promise<string | undefined> => {
        const baseUrl = options?.baseUrl;
        const persistSelection = options?.persistSelection ?? true;
        const placeHolder = options?.placeHolder || 'Select project for this workspace';
        const projects = await backendClient.listProjects(baseUrl);
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
                placeHolder,
            }
        );

        if (!pick) {
            return undefined;
        }

        const workspaceFolder = getWorkspaceFolder();
        if (persistSelection && workspaceFolder) {
            await setProjectForWorkspace(getWorkspaceFingerprint(workspaceFolder), pick.projectId);
            await eventCapture?.flushDeferredSnapshots(pick.projectId);
            if (sidebarProviderRef) {
                sidebarProviderRef.notifyProjectSelected(pick.label, pick.projectId);
            }
        }
        return pick.projectId;
    };

    const resolveProjectIdByName = async (projectName: string, baseUrl?: string): Promise<string> => {
        const normalizedTarget = String(projectName || '').trim().toLowerCase();
        if (!normalizedTarget) {
            throw new Error('Project name cannot be empty.');
        }

        const projects = await backendClient.listProjects(baseUrl);
        const exactMatches = projects.filter(
            (project) => String(project.name || '').trim().toLowerCase() === normalizedTarget
        );

        if (exactMatches.length === 1) {
            return String(exactMatches[0].id || '').trim();
        }

        if (exactMatches.length > 1) {
            const ids = exactMatches
                .map((project) => String(project.id || '').trim())
                .filter(Boolean);
            throw new Error(`Project name "${projectName}" is ambiguous. Use --project-id explicitly. Matches: ${ids.join(', ')}`);
        }

        throw new Error(`Project name "${projectName}" not found. Create it first or use --project-id.`);
    };

    const promptForLogin = async (): Promise<void> => {
        const choice = await vscode.window.showWarningMessage(
            'Log in to SecondCortex in VS Code to run git ingest.',
            'Open Login'
        );
        if (choice === 'Open Login') {
            await vscode.commands.executeCommand('secondcortex.chatView.focus');
        }
    };

    const resolveProjectIdForGitIngest = async (request: GitIngestCommandRequest): Promise<string | undefined> => {
        const explicitProjectId = String(request.projectId || '').trim();
        if (explicitProjectId) {
            return explicitProjectId;
        }

        const explicitProjectName = String(request.projectName || '').trim();
        if (explicitProjectName) {
            return resolveProjectIdByName(explicitProjectName, request.backendUrl);
        }

        const repoPath = path.resolve(request.repoPath);
        const workspaceFolder = getWorkspaceFolder();
        const persistSelection = Boolean(workspaceFolder && pathsMatch(workspaceFolder.uri.fsPath, repoPath));

        if (persistSelection && selectedProjectId) {
            return selectedProjectId;
        }

        const resolved = await backendClient.resolveProject(
            {
                workspaceName: path.basename(repoPath),
                workspacePathHash: hashWorkspacePath(repoPath),
                repoRemote: await getRepoRemoteForPath(repoPath),
            },
            request.backendUrl
        );

        if (resolved?.status === 'resolved' && resolved.projectId) {
            if (persistSelection && workspaceFolder) {
                await setProjectForWorkspace(getWorkspaceFingerprint(workspaceFolder), resolved.projectId);
                await eventCapture?.flushDeferredSnapshots(resolved.projectId);
            }
            return resolved.projectId;
        }

        return selectProjectInteractive({
            baseUrl: request.backendUrl,
            persistSelection,
            placeHolder: persistSelection
                ? 'Select project for this workspace'
                : `Select project for git ingest (${path.basename(repoPath)})`,
        });
    };

    const runGitIngest = async (incomingRequest?: Partial<GitIngestCommandRequest>): Promise<void> => {
        if (DEMO_MODE) {
            vscode.window.showInformationMessage('SecondCortex: Git ingest completed using local workspace history.');
            outputChannel.appendLine('[SecondCortex] Git ingest completed locally.');
            return;
        }

        const fallbackRepoPath = getWorkspaceFolder()?.uri.fsPath || '';
        const requestedRepoPath = String(incomingRequest?.repoPath || fallbackRepoPath || '').trim();
        if (!requestedRepoPath) {
            vscode.window.showWarningMessage('Open the repository in VS Code or pass --repo-path to cortex ingest.');
            return;
        }

        const request: GitIngestCommandRequest = {
            repoPath: path.resolve(requestedRepoPath),
            projectId: String(incomingRequest?.projectId || '').trim() || undefined,
            projectName: String(incomingRequest?.projectName || '').trim() || undefined,
            backendUrl: String(incomingRequest?.backendUrl || '').trim() || undefined,
            maxCommits: parseIntegerFlag(String(incomingRequest?.maxCommits ?? ''), 300, 1),
            maxPullRequests: parseIntegerFlag(String(incomingRequest?.maxPullRequests ?? ''), 30, 0),
            includePullRequests: incomingRequest?.includePullRequests !== false,
        };

        if (!(await authService.isLoggedIn())) {
            await promptForLogin();
            return;
        }

        try {
            await vscode.window.withProgress(
                {
                    location: vscode.ProgressLocation.Notification,
                    title: `SecondCortex: Ingesting git history from ${path.basename(request.repoPath)}`,
                    cancellable: false,
                },
                async () => {
                    const projectId = await resolveProjectIdForGitIngest(request);
                    if (!projectId) {
                        outputChannel.appendLine(`[SecondCortex] Git ingest cancelled: no project selected for ${request.repoPath}`);
                        return;
                    }

                    outputChannel.appendLine(
                        `[SecondCortex] Starting git ingest for repo=${request.repoPath} project=${projectId} commits=${request.maxCommits} prs=${request.maxPullRequests}`
                    );

                    const result = await backendClient.ingestGitHistory(
                        {
                            repoPath: request.repoPath,
                            projectId,
                            maxCommits: request.maxCommits,
                            maxPullRequests: request.maxPullRequests,
                            includePullRequests: request.includePullRequests,
                        },
                        request.backendUrl
                    );

                    outputChannel.appendLine(
                        `[SecondCortex] Git ingest complete: ingested=${result.ingestedCount} commits=${result.commitCount} prs=${result.prCount} skipped=${result.skippedCount}`
                    );
                    if (result.warnings.length > 0) {
                        outputChannel.appendLine(`[SecondCortex] Git ingest warnings:\n- ${result.warnings.join('\n- ')}`);
                    }

                    const action = result.warnings.length > 0 ? 'View Output' : undefined;
                    const message = `SecondCortex ingested ${result.ingestedCount} record(s) from ${path.basename(request.repoPath)}.`;
                    if (action) {
                        const choice = await vscode.window.showInformationMessage(message, action);
                        if (choice === action) {
                            outputChannel.show(true);
                        }
                        return;
                    }

                    vscode.window.showInformationMessage(message);
                }
            );
        } catch (err) {
            const message = err instanceof Error ? err.message : String(err);
            outputChannel.appendLine(`[SecondCortex] Git ingest failed: ${message}`);
            const choice = await vscode.window.showErrorMessage(`SecondCortex ingest failed: ${message}`, 'View Output');
            if (choice === 'View Output') {
                outputChannel.show(true);
            }
        }
    };

    const resolveProjectForWorkspace = async (promptOnUnresolved: boolean): Promise<void> => {
        if (DEMO_MODE) {
            selectedProjectId = 'workspace-project';
            return;
        }

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
        vscode.commands.registerCommand('secondcortex.ingestGitHistory', async (request?: Partial<GitIngestCommandRequest>) => {
            await runGitIngest(request);
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
                if (DEMO_MODE) {
                    const mcpEnabled = vscode.workspace
                        .getConfiguration('secondcortex')
                        .get<boolean>('enableSecondCortexMcp', false);
                    const response = mcpEnabled
                        ? getMockMcpResponse(question)
                        : 'Payment retry was reduced from 5 to 3 after two deterministic test failures.';
                    outputChannel.appendLine(`[SecondCortex] Answer: ${response}`);
                    vscode.window.showInformationMessage(`SecondCortex: ${response}`);
                    return;
                }

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
            if (DEMO_MODE) {
                selectedProjectId = 'workspace-project';
                vscode.window.showInformationMessage('SecondCortex: workspace-project selected.');
                return;
            }
            await selectProjectInteractive();
        })
    );

    context.subscriptions.push(
        vscode.window.registerUriHandler({
            handleUri: async (uri: vscode.Uri) => {
                const action = String(uri.path || '').replace(/^\/+/, '').trim().toLowerCase();
                outputChannel.appendLine(`[SecondCortex] Received URI action: ${action || '<empty>'}`);

                if (action === 'ingest') {
                    await runGitIngest(parseGitIngestUri(uri));
                    return;
                }

                if (action === 'resurrect') {
                    const target = parseResurrectTarget(uri);
                    const currentWorkspace = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
                    await resurrector.executeFromQuery(target, backendClient, currentWorkspace);
                    return;
                }

                vscode.window.showWarningMessage(`SecondCortex: Unsupported CLI command "${action || 'unknown'}".`);
            },
        })
    );

    context.subscriptions.push(
        vscode.workspace.onDidChangeWorkspaceFolders(async () => {
            await resolveProjectForWorkspace(true);
        })
    );

    // Offline sync
    if (!DEMO_MODE) {
        snapshotCache.flushToBackend(backendClient).catch((err) => {
            outputChannel.appendLine(`[SecondCortex] Offline sync error: ${err}`);
        });
    }

    resolveProjectForWorkspace(true).catch((err) => {
        outputChannel.appendLine(`[SecondCortex] Project resolver startup error: ${err}`);
    });

    outputChannel.appendLine('[SecondCortex] Extension activated successfully.');
}

export function deactivate() {
    eventCapture?.dispose();
    snapshotCache?.close();
}
