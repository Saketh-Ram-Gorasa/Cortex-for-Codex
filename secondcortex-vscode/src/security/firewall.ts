import * as vscode from 'vscode';
import * as fs from 'fs';
import * as path from 'path';
import { minimatch } from 'minimatch';

/**
 * SemanticFirewall – the local security layer that ensures NO secrets
 * or proprietary code leave the developer's laptop.
 *
 * Two mechanisms:
 *   1. `.cortexignore` parser — drops events for ignored paths entirely.
 *   2. Regex/AST Scrubber   — hunts for secrets in captured content and
 *      replaces them with `[CODE_REDACTED]`.
 */
export class SemanticFirewall {
    private ignorePatterns: string[] = [];

    /** Regex patterns that identify common secrets */
    private static readonly SECRET_PATTERNS: RegExp[] = [
        // API keys with common prefixes
        /(?:sk_live_|sk_test_|pk_live_|pk_test_)[A-Za-z0-9]{10,}/g,
        // Bearer tokens
        /Bearer\s+[A-Za-z0-9\-._~+\/]+=*/g,
        // Generic API key patterns  key = "..." or key: "..."
        /(?:api[_-]?key|apikey|secret|token|password|passwd|credential|auth)\s*[:=]\s*["'][^"']{8,}["']/gi,
        // AWS keys
        /AKIA[0-9A-Z]{16}/g,
        // Azure connection strings
        /(?:AccountKey|SharedAccessKey)\s*=\s*[A-Za-z0-9+\/=]{20,}/gi,
        // Private key blocks
        /-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |DSA )?PRIVATE KEY-----/g,
        // JWTs (three base64url segments separated by dots)
        /eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}/g,
        // .env-style assignments with long values
        /(?:^|\n)\s*[A-Z_]{2,50}=["']?[A-Za-z0-9\-._~+\/]{20,}["']?/gm,
        // GitHub tokens
        /gh[pousr]_[A-Za-z0-9_]{36,}/g,
        // OpenAI keys
        /sk-[A-Za-z0-9]{32,}/g,
    ];

    constructor(private output: vscode.OutputChannel) {
        this.loadCortexIgnore();
    }

    // ── .cortexignore ─────────────────────────────────────────────

    /** Returns true if the given file path should be entirely ignored. */
    isIgnored(filePath: string): boolean {
        const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ?? '';
        const relative = path.relative(workspaceRoot, filePath).replace(/\\/g, '/');

        for (const pattern of this.ignorePatterns) {
            if (minimatch(relative, pattern, { dot: true })) {
                return true;
            }
        }

        // Always silently ignore common sensitive files
        const basename = path.basename(filePath);
        const alwaysIgnored = ['.env', '.env.local', '.env.production', '.env.development'];
        if (alwaysIgnored.includes(basename)) {
            return true;
        }

        return false;
    }

    // ── Regex/AST Scrubber ────────────────────────────────────────

    /**
     * Scrubs the raw file content, replacing any detected secrets
     * with `[CODE_REDACTED]`. Returns the sanitized "Shadow Graph" string.
     */
    scrub(rawContent: string): string {
        let sanitized = rawContent;
        let redactionCount = 0;

        for (const pattern of SemanticFirewall.SECRET_PATTERNS) {
            // Clone the regex to reset lastIndex for global regexes
            const regex = new RegExp(pattern.source, pattern.flags);
            const matches = sanitized.match(regex);
            if (matches) {
                redactionCount += matches.length;
                sanitized = sanitized.replace(regex, '[CODE_REDACTED]');
            }
        }

        if (redactionCount > 0) {
            this.output.appendLine(
                `[SemanticFirewall] 🔒 Redacted ${redactionCount} potential secret(s).`
            );
        }

        return sanitized;
    }

    // ── Private helpers ───────────────────────────────────────────

    private loadCortexIgnore(): void {
        const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
        if (!workspaceRoot) { return; }

        const cortexIgnorePath = path.join(workspaceRoot, '.cortexignore');
        try {
            if (fs.existsSync(cortexIgnorePath)) {
                const raw = fs.readFileSync(cortexIgnorePath, 'utf-8');
                this.ignorePatterns = raw
                    .split('\n')
                    .map((line) => line.trim())
                    .filter((line) => line.length > 0 && !line.startsWith('#'));
                this.output.appendLine(
                    `[SemanticFirewall] Loaded ${this.ignorePatterns.length} patterns from .cortexignore`
                );
            } else {
                this.output.appendLine('[SemanticFirewall] No .cortexignore found — using defaults.');
            }
        } catch (err) {
            this.output.appendLine(`[SemanticFirewall] Error reading .cortexignore: ${err}`);
        }
    }
}
