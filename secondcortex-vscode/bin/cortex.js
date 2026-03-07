#!/usr/bin/env node

/**
 * cortex CLI Wrapper
 * 
 * This CLI delegates commands to the SecondCortex VS Code extension
 * using URL handlers.
 */

const { exec } = require('child_process');

// Command line arguments (skip node and script path)
const args = process.argv.slice(2);

if (args.length === 0) {
    console.log(`
🧠 SecondCortex CLI

Commands:
  resurrect [target]   Resurrects a workspace state (latest by default).

Examples:
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
} else {
    console.error(`Unknown command: ${command}`);
    process.exit(1);
}
