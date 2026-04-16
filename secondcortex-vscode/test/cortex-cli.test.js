const assert = require('node:assert/strict');
const path = require('path');

const cortexCli = require('../bin/cortex.js');

function run() {
    const parsedArgs = cortexCli.parseIngestArgs([
        '--repo-path',
        '.',
        '--project-id',
        'proj_123',
        '--max-commits',
        '25',
        '--max-pull-requests',
        '5',
        '--no-prs',
    ]);

    assert.equal(parsedArgs.projectId, 'proj_123');
    assert.equal(parsedArgs.maxCommits, 25);
    assert.equal(parsedArgs.maxPullRequests, 5);
    assert.equal(parsedArgs.includePullRequests, false);

    const ingestUri = cortexCli.buildCommandUri('ingest', {
        repoPath: path.join('C:', 'Users', 'SUHAAN', 'repo with spaces'),
        projectName: 'SusyDB Test',
        backendUrl: 'http://localhost:8000/',
        maxCommits: 50,
        maxPullRequests: 0,
        includePullRequests: false,
    });

    const parsedUri = new URL(ingestUri);
    assert.equal(parsedUri.pathname, '/ingest');
    assert.equal(parsedUri.searchParams.get('projectName'), 'SusyDB Test');
    assert.equal(parsedUri.searchParams.get('backendUrl'), 'http://localhost:8000');
    assert.equal(parsedUri.searchParams.get('maxCommits'), '50');
    assert.equal(parsedUri.searchParams.get('maxPullRequests'), '0');
    assert.equal(parsedUri.searchParams.get('includePullRequests'), 'false');

    let openCommand = '';
    return cortexCli.main(
        ['ingest', '--project-id', 'proj_123'],
        {
            io: {
                log() { },
                error() { },
            },
            execFn: (command, callback) => {
                openCommand = command;
                callback(null);
            },
            platform: 'win32',
        }
    ).then(() => {
        assert.match(openCommand, /vscode:\/\/secondcortex-labs\.secondcortex\/ingest\?/);
        assert.doesNotMatch(openCommand, /SECONDCORTEX_TOKEN/);
        console.log('cortex CLI regression checks passed');
    });
}

run().catch((error) => {
    console.error(error && error.stack ? error.stack : String(error));
    process.exit(1);
});
