#!/usr/bin/env node

/**
 * cortex CLI Wrapper
 *
 * This CLI delegates commands to the SecondCortex VS Code extension
 * using URL handlers so the extension can use its existing secure session.
 */

const { exec } = require('child_process');
const path = require('path');

const EXTENSION_URI_PREFIX = 'vscode://secondcortex-labs.secondcortex';

function printHelp(io = console) {
    io.log(`
🧠 SecondCortex CLI

Commands:
    ingest               Cold-start ingest current codebase (git history) into snapshots.
  resurrect [target]   Resurrects a workspace state (latest by default).

Examples:
    cortex ingest
    cortex ingest --project-id proj_123
    cortex ingest --project-name "SusyDB Test"
    cortex ingest --repo-path . --max-commits 250
  cortex resurrect
  cortex resurrect feature/auth-fix
`);
}

function buildCommandUri(command, payload) {
    if (command === 'resurrect') {
        const target = String(payload && payload.target ? payload.target : 'latest').trim() || 'latest';
        return `${EXTENSION_URI_PREFIX}/resurrect?${encodeURIComponent(target)}`;
    }

    if (command === 'ingest') {
        const params = new URLSearchParams();
        params.set('repoPath', path.resolve(payload && payload.repoPath ? payload.repoPath : process.cwd()));
        params.set('maxCommits', String(payload && payload.maxCommits ? payload.maxCommits : 300));
        params.set('maxPullRequests', String(payload && payload.maxPullRequests !== undefined ? payload.maxPullRequests : 30));
        params.set('includePullRequests', payload && payload.includePullRequests === false ? 'false' : 'true');

        const projectId = String(payload && payload.projectId ? payload.projectId : '').trim();
        const projectName = String(payload && payload.projectName ? payload.projectName : '').trim();
        const backendUrl = String(payload && payload.backendUrl ? payload.backendUrl : '').trim();

        if (projectId) {
            params.set('projectId', projectId);
        }
        if (projectName) {
            params.set('projectName', projectName);
        }
        if (backendUrl) {
            params.set('backendUrl', backendUrl.replace(/\/$/, ''));
        }

        return `${EXTENSION_URI_PREFIX}/ingest?${params.toString()}`;
    }

    throw new Error(`Unknown command: ${command}`);
}

function getOpenCommand(uri, platform = process.platform) {
    if (platform === 'win32') {
        return `start "" "${uri}"`;
    }
    if (platform === 'darwin') {
        return `open "${uri}"`;
    }
    return `xdg-open "${uri}"`;
}

function dispatchUri(uri, { execFn = exec, platform = process.platform } = {}) {
    const openCmd = getOpenCommand(uri, platform);

    return new Promise((resolve, reject) => {
        execFn(openCmd, (error) => {
            if (error) {
                reject(new Error(`Ensure VS Code is installed and the SecondCortex extension is active.\n${error.message}`));
                return;
            }
            resolve();
        });
    });
}

async function main(cliArgs = process.argv.slice(2), { io = console, execFn = exec, platform = process.platform } = {}) {
    if (cliArgs.length === 0) {
        printHelp(io);
        return 0;
    }

    const command = cliArgs[0];

    if (command === 'resurrect') {
        const target = cliArgs[1] || 'latest';
        io.log(`[SecondCortex] Requesting workspace resurrection for: ${target}`);
        await dispatchUri(buildCommandUri('resurrect', { target }), { execFn, platform });
        io.log('✅ Command sent to VS Code successfully.');
        return 0;
    }

    if (command === 'ingest') {
        const parsed = parseIngestArgs(cliArgs.slice(1));
        const repoPath = path.resolve(parsed.repoPath || process.cwd());
        io.log(`[SecondCortex] Requesting git history ingest for: ${repoPath}`);
        await dispatchUri(buildCommandUri('ingest', parsed), { execFn, platform });
        io.log('✅ Ingest request sent to VS Code.');
        io.log('   The SecondCortex extension will use your existing login and project context there.');
        return 0;
    }

    throw new Error(`Unknown command: ${command}`);
}

function parseIngestArgs(ingestArgs) {
    const parsed = {
        repoPath: process.cwd(),
        projectId: '',
        projectName: '',
        backendUrl: process.env.SECONDCORTEX_BACKEND_URL || '',
        maxCommits: 300,
        maxPullRequests: 30,
        includePullRequests: true,
    };

    for (let index = 0; index < ingestArgs.length; index += 1) {
        const arg = ingestArgs[index];
        const next = ingestArgs[index + 1];

        if ((arg === '--repo-path' || arg === '--repo') && next) {
            parsed.repoPath = next;
            index += 1;
            continue;
        }
        if (arg === '--project-id' && next) {
            parsed.projectId = next;
            index += 1;
            continue;
        }
        if ((arg === '--project-name' || arg === '--project') && next) {
            parsed.projectName = next;
            index += 1;
            continue;
        }
        if (arg === '--backend-url' && next) {
            parsed.backendUrl = next;
            index += 1;
            continue;
        }
        if (arg === '--token' && next) {
            index += 1;
            continue;
        }
        if (arg === '--max-commits' && next) {
            const value = Number(next);
            if (Number.isFinite(value) && value > 0) {
                parsed.maxCommits = Math.floor(value);
            }
            index += 1;
            continue;
        }
        if (arg === '--max-pull-requests' && next) {
            const value = Number(next);
            if (Number.isFinite(value) && value >= 0) {
                parsed.maxPullRequests = Math.floor(value);
            }
            index += 1;
            continue;
        }
        if (arg === '--no-prs') {
            parsed.includePullRequests = false;
            continue;
        }
    }

    return parsed;
}

if (require.main === module) {
    main().catch((error) => {
        console.error('\n❌ Failed to send command to VS Code.');
        console.error(error && error.message ? error.message : String(error));
        process.exit(1);
    });
}

module.exports = {
    buildCommandUri,
    dispatchUri,
    getOpenCommand,
    main,
    parseIngestArgs,
    printHelp,
};
