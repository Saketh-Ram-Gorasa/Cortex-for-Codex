import * as vscode from 'vscode';
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

    /**
     * Query the backend for the resurrection plan and execute it.
     */
    async executeFromQuery(target: string, backend: BackendClient): Promise<void> {
        this.output.appendLine(`[Resurrector] Requesting resurrection plan for: ${target}`);

        const plan = await backend.getResurrectionPlan(target);
        if (!plan || !plan.commands || plan.commands.length === 0) {
            vscode.window.showWarningMessage('SecondCortex: No resurrection plan available for that target.');
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
        const uri = vscode.Uri.file(filePath);
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
    type: 'git_stash' | 'git_checkout' | 'open_file' | 'split_terminal' | 'run_command';
    branch?: string;
    filePath?: string;
    viewColumn?: number;
    command?: string;
}
