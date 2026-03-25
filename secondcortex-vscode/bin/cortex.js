#!/usr/bin/env node

/**
 * cortex CLI Wrapper
 * 
 * This CLI delegates commands to the SecondCortex VS Code extension
 * using URL handlers.
 */

const { exec } = require('child_process');
const path = require('path');

// Command line arguments (skip node and script path)
const args = process.argv.slice(2);

if (args.length === 0) {
    console.log(`
🧠 SecondCortex CLI

Commands:
    ingest               Cold-start ingest current codebase (git history) into snapshots.
  resurrect [target]   Resurrects a workspace state (latest by default).

Examples:
    cortex ingest --project-id proj_123
        cortex ingest --project-name "SusyDB Test"
    cortex ingest --repo-path . --project-id proj_123 --max-commits 250
  cortex resurrect
  cortex resurrect feature/auth-fix
`);
    process.exit(0);
}

const command = args[0];

if (command === 'resurrect') {
    const target = args[1] || 'latest';
    console.log(`[SecondCortex] Requesting workspace resurrection for: ${target}`);

    // Construct the vscode:// URI to trigger the handler in the extension
    // URI Format: vscode://<publisher>.<extension-name>/<path>?<query>
    const uri = `vscode://secondcortex-labs.secondcortex/resurrect?${encodeURIComponent(target)}`;

    let openCmd;
    if (process.platform === 'win32') {
        openCmd = `start "" "${uri}"`;
    } else if (process.platform === 'darwin') {
        openCmd = `open "${uri}"`;
    } else {
        openCmd = `xdg-open "${uri}"`;
    }

    exec(openCmd, (error) => {
        if (error) {
            console.error('\n❌ Failed to send command to VS Code.');
            console.error('Ensure VS Code is installed and the SecondCortex extension is active.');
            console.error(error.message);
            process.exit(1);
        }
        console.log('✅ Command sent to VS Code successfully.');
    });
} else if (command === 'ingest') {
    const parsed = parseIngestArgs(args.slice(1));

    const backendUrl = (parsed.backendUrl || process.env.SECONDCORTEX_BACKEND_URL || 'http://localhost:8000').replace(/\/$/, '');
    const token = parsed.token || process.env.SECONDCORTEX_TOKEN || process.env.SECONDCORTEX_AUTH_TOKEN;

    if (!token) {
        console.error('❌ Missing auth token. Provide --token or set SECONDCORTEX_TOKEN.');
        process.exit(1);
    }

    runIngest(parsed, backendUrl, token).catch((err) => {
        console.error('❌ Failed to run cortex ingest.');
        console.error(err && err.message ? err.message : String(err));
        process.exit(1);
    });
} else {
    console.error(`Unknown command: ${command}`);
    process.exit(1);
}

function parseIngestArgs(ingestArgs) {
    const parsed = {
        repoPath: process.cwd(),
        projectId: '',
        projectName: '',
        backendUrl: process.env.SECONDCORTEX_BACKEND_URL || '',
        token: process.env.SECONDCORTEX_TOKEN || process.env.SECONDCORTEX_AUTH_TOKEN || '',
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
            parsed.token = next;
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

async function runIngest(parsed, backendUrl, token) {
    let resolvedProjectId = (parsed.projectId || '').trim();
    if (!resolvedProjectId && parsed.projectName) {
        resolvedProjectId = await resolveProjectIdByName({
            backendUrl,
            token,
            projectName: parsed.projectName,
        });
    }

    if (!resolvedProjectId) {
        throw new Error('Missing required target project. Use --project-id <id> or --project-name "<name>".');
    }

    const payload = {
        repoPath: path.resolve(parsed.repoPath || process.cwd()),
        maxCommits: parsed.maxCommits,
        maxPullRequests: parsed.maxPullRequests,
        includePullRequests: parsed.includePullRequests,
        projectId: resolvedProjectId,
    };

    console.log(`[SecondCortex] Starting cold-start ingest for ${payload.repoPath}`);
    console.log(`[SecondCortex] Target project: ${payload.projectId}`);

    const response = await fetch(`${backendUrl}/api/v1/ingest/git`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify(payload),
    });

    const text = await response.text();
    if (!response.ok) {
        throw new Error(`Ingest failed (${response.status} ${response.statusText}): ${text || 'No response body'}`);
    }

    let data = {};
    try {
        data = text ? JSON.parse(text) : {};
    } catch {
        data = { raw: text };
    }

    const ingested = Number(data.ingestedCount || 0);
    const commits = Number(data.commitCount || 0);
    const prs = Number(data.prCount || 0);
    const skipped = Number(data.skippedCount || 0);

    console.log('✅ Cold-start ingest completed.');
    console.log(`   ingestedCount=${ingested} commitCount=${commits} prCount=${prs} skippedCount=${skipped}`);

    const warnings = Array.isArray(data.warnings) ? data.warnings : [];
    if (warnings.length > 0) {
        console.log('⚠️ Warnings:');
        for (const warning of warnings) {
            console.log(`   - ${warning}`);
        }
    }
}

async function resolveProjectIdByName({ backendUrl, token, projectName }) {
    const normalizedTarget = String(projectName || '').trim().toLowerCase();
    if (!normalizedTarget) {
        return '';
    }

    const response = await fetch(`${backendUrl}/api/v1/projects`, {
        method: 'GET',
        headers: {
            'Authorization': `Bearer ${token}`,
        },
    });

    const text = await response.text();
    if (!response.ok) {
        throw new Error(`Unable to list projects (${response.status} ${response.statusText}): ${text || 'No response body'}`);
    }

    let data = {};
    try {
        data = text ? JSON.parse(text) : {};
    } catch {
        throw new Error('Project lookup returned non-JSON response.');
    }

    const projects = Array.isArray(data.projects) ? data.projects : [];
    const exactMatches = projects.filter((project) => String(project.name || '').trim().toLowerCase() === normalizedTarget);

    if (exactMatches.length === 1) {
        return String(exactMatches[0].id || '').trim();
    }

    if (exactMatches.length > 1) {
        const ids = exactMatches.map((project) => String(project.id || '').trim()).filter(Boolean);
        throw new Error(`Project name "${projectName}" is ambiguous. Use --project-id explicitly. Matches: ${ids.join(', ')}`);
    }

    throw new Error(`Project name "${projectName}" not found. Create it first or use --project-id.`);
}
