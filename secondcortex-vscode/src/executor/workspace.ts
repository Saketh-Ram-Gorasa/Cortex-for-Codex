import * as vscode from 'vscode';
import * as path from 'path';
import { BackendClient } from '../backendClient';

/**
 * WorkspaceResurrector – "The Hands"
 *
 * Receives a JSON command array from the Azure backend and physically
 * restores the developer's IDE environment using the VS Code API:
 *   1. git stash
 *   2. git checkout <target_branch>
 *   3. Open the exact working files
 *   4. Split the terminal and start the dev server
 */
export class WorkspaceResurrector {
    constructor(private output: vscode.OutputChannel) { }

    async executeFromQuery(target: string, backend: BackendClient, currentWorkspace?: string): Promise<void> {
        this.output.appendLine(`[Resurrector] Requesting resurrection plan for: ${target}`);

        const plan = await backend.getResurrectionPlan(target, currentWorkspace);
        if (!plan || !plan.commands || plan.commands.length === 0) {
            vscode.window.showWarningMessage('SecondCortex: No resurrection plan available for that target.');
            return;
        }

        // Show proposed action plan to the user for Human-in-the-Loop confirmation
        const planSummary = plan.planSummary || 'I will restore your workspace state based on the retrieved context.';
        const userChoice = await vscode.window.showInformationMessage(
            `SecondCortex: Proposed Action Plan\n\n${planSummary}\n\nDo you want to proceed?`,
            { modal: true },
            'Proceed',
            'Cancel'
        );

        if (userChoice !== 'Proceed') {
            this.output.appendLine('[Resurrector] Resurrection canceled by user.');
            return;
        }

        await this.execute(plan.commands as ResurrectionCommand[]);
    }

    /**
     * Execute a pre-defined command array directly.
     */
    async execute(commands: ResurrectionCommand[]): Promise<void> {
        this.output.appendLine(`[Resurrector] Executing ${commands.length} resurrection commands...`);

        for (const cmd of commands) {
            try {
                switch (cmd.type) {
                    case 'open_workspace': {
                        if (cmd.filePath) {
                            const userChoice = await vscode.window.showInformationMessage(
                                `Session target belongs to a different workspace: ${cmd.filePath}. Open it?`,
                                'Reuse Current Window',
                                'Open in New Window',
                                'Cancel'
                            );
                            if (userChoice === 'Reuse Current Window') {
                                const uri = vscode.Uri.file(cmd.filePath);
                                await vscode.commands.executeCommand('vscode.openFolder', uri, false);
                            } else if (userChoice === 'Open in New Window') {
                                const uri = vscode.Uri.file(cmd.filePath);
                                await vscode.commands.executeCommand('vscode.openFolder', uri, true);
                            }
                        }
                        return; // Abort remaining commands in this window once workspace switch is handled.
                    }

                    case 'git_stash':
                        await this.runTerminalCommand('git stash');
                        break;

                    case 'git_checkout':
                        await this.runTerminalCommand(`git checkout ${cmd.branch ?? 'main'}`);
                        break;

                    case 'open_file':
                        if (cmd.filePath) {
                            await this.openFile(cmd.filePath, cmd.viewColumn);
                        }
                        break;

                    case 'split_terminal':
                        await this.splitTerminal(cmd.command);
                        break;

                    case 'run_command':
                        await this.runTerminalCommand(cmd.command ?? '');
                        break;

                    default:
                        this.output.appendLine(`[Resurrector] Unknown command type: ${(cmd as ResurrectionCommand).type}`);
                }
            } catch (err) {
                this.output.appendLine(`[Resurrector] Error executing command ${cmd.type}: ${err}`);
            }
        }

        vscode.window.showInformationMessage('SecondCortex: Workspace resurrection complete! ✅');
        this.output.appendLine('[Resurrector] Resurrection complete.');
    }

    // ── Private helpers ───────────────────────────────────────────

    private async runTerminalCommand(command: string): Promise<void> {
        this.output.appendLine(`[Resurrector] Running: ${command}`);
        const terminal = vscode.window.activeTerminal ?? vscode.window.createTerminal('SecondCortex');
        terminal.show();
        terminal.sendText(command);
        // Give the command a moment to execute
        await this.sleep(1500);
    }

    private async openFile(filePath: string, viewColumn?: number): Promise<void> {
        this.output.appendLine(`[Resurrector] Opening file: ${filePath}`);

        // Resolve relative paths to workspace root
        let absolutePath = filePath;
        if (!path.isAbsolute(filePath)) {
            const root = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
            if (root) {
                absolutePath = path.join(root, filePath);
            }
        }

        const uri = vscode.Uri.file(absolutePath);
        const doc = await vscode.workspace.openTextDocument(uri);
        await vscode.window.showTextDocument(doc, {
            viewColumn: viewColumn
                ? (viewColumn as vscode.ViewColumn)
                : vscode.ViewColumn.One,
            preserveFocus: false,
        });
    }

    private async splitTerminal(command?: string): Promise<void> {
        this.output.appendLine('[Resurrector] Splitting terminal...');
        // VS Code command to create a split terminal
        await vscode.commands.executeCommand('workbench.action.terminal.split');
        await this.sleep(500);
        if (command) {
            const terminal = vscode.window.activeTerminal;
            if (terminal) {
                terminal.sendText(command);
            }
        }
    }

    private sleep(ms: number): Promise<void> {
        return new Promise((resolve) => setTimeout(resolve, ms));
    }
}

// ── Types ─────────────────────────────────────────────────────────

export interface ResurrectionCommand {
    type: 'git_stash' | 'git_checkout' | 'open_file' | 'split_terminal' | 'run_command' | 'open_workspace';
    branch?: string;
    filePath?: string;
    viewColumn?: number;
    command?: string;
}
