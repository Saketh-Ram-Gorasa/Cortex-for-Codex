import * as vscode from 'vscode';
import * as fs from 'fs';
import * as path from 'path';
import { minimatch } from 'minimatch';
import * as ts from 'typescript'; // The AST Engine

/**
 * SemanticFirewall – the local security layer that ensures NO secrets
 * or proprietary code leave the developer's laptop.
 *
 * Three-layered defense:
 *   1. `.cortexignore` parser — drops events for ignored paths entirely.
 *   2. AST Scrubber           — uses the TypeScript Compiler API to
 *      structurally identify secrets by variable/property names and
 *      surgically redact their values.
 *   3. Regex Fallback         — catches hardcoded patterns (API keys,
 *      JWTs, etc.) that the AST layer might miss.
 */
export class SemanticFirewall {
    private ignorePatterns: string[] = [];

    /** Fallback Regex for hardcoded secrets not caught by variable names */
    private static readonly SECRET_PATTERNS: RegExp[] = [
        // API keys with common prefixes (Stripe, etc.)
        /(?:sk_live_|sk_test_|pk_live_|pk_test_)[A-Za-z0-9]{10,}/g,
        // Bearer tokens
        /Bearer\s+[A-Za-z0-9\-._~+\/]+=*/g,
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

    // ── AST Scrubber (The "Smart" Firewall) ──────────────────────────

    /**
     * Parses raw content into a TypeScript AST and walks the tree looking
     * for string literals assigned to variables or properties whose names
     * semantically imply a secret (key, token, password, etc.).
     *
     * This is smarter than regex because it understands code *structure*:
     *   const myCustomToken = "xyz123";   // ← regex misses, AST catches
     *   { authToken: "s3cr3t" }           // ← regex misses, AST catches
     */
    private astScrub(rawContent: string): { sanitized: string; count: number } {
        // 1. Parse the raw text into an Abstract Syntax Tree
        const sourceFile = ts.createSourceFile(
            'snapshot.ts',
            rawContent,
            ts.ScriptTarget.Latest,
            true
        );

        const replacements: { start: number; end: number; text: string }[] = [];

        // Semantic keywords that imply a secret is being stored
        const sensitiveNames = /key|token|secret|password|passwd|credential|auth/i;

        // 2. Traverse the AST nodes recursively
        const visit = (node: ts.Node) => {
            // We only care about String Literals (the actual secret values)
            if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) {
                let isSensitive = false;

                // Scenario A: Variable Declaration (e.g., const stripeKey = "...")
                if (node.parent && ts.isVariableDeclaration(node.parent)) {
                    const varName = node.parent.name.getText();
                    if (sensitiveNames.test(varName)) {
                        isSensitive = true;
                    }
                }
                // Scenario B: Object Property Assignment (e.g., { authToken: "..." })
                else if (node.parent && ts.isPropertyAssignment(node.parent)) {
                    const propName = node.parent.name.getText();
                    if (sensitiveNames.test(propName)) {
                        isSensitive = true;
                    }
                }

                // If structurally identified as a secret, mark the node for redaction
                if (isSensitive) {
                    replacements.push({
                        start: node.getStart(),
                        end: node.getEnd(),
                        text: '"[CODE_REDACTED]"'
                    });
                }
            }
            ts.forEachChild(node, visit);
        };

        visit(sourceFile);

        // 3. Apply replacements back-to-front to avoid index shifting
        replacements.sort((a, b) => b.start - a.start);
        let result = rawContent;
        for (const rep of replacements) {
            result = result.slice(0, rep.start) + rep.text + result.slice(rep.end);
        }

        return { sanitized: result, count: replacements.length };
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

    // ── The Main Scrub Pipeline ──────────────────────────────────────

    /**
     * Runs the AST Parser first (smart, structural), then falls back
     * to Regex (pattern-based safety net).
     *
     * Returns the sanitized "Shadow Graph" string.
     */
    scrub(rawContent: string): string {
        let redactionCount = 0;

        // Phase 1: AST Structural Scrubbing
        try {
            const astResult = this.astScrub(rawContent);
            rawContent = astResult.sanitized;
            redactionCount += astResult.count;
        } catch (err) {
            // If AST parsing fails (e.g., non-TS/JS content), silently skip
            this.output.appendLine(
                `[SemanticFirewall] AST parse skipped (non-parseable content): ${err}`
            );
        }

        // Phase 2: Fallback Regex Scrubbing
        let sanitized = rawContent;
        for (const pattern of SemanticFirewall.SECRET_PATTERNS) {
            const regex = new RegExp(pattern.source, pattern.flags);
            const matches = sanitized.match(regex);
            if (matches) {
                redactionCount += matches.length;
                sanitized = sanitized.replace(regex, '[CODE_REDACTED]');
            }
        }

        if (redactionCount > 0) {
            this.output.appendLine(
                `[Agent:Retrieving][SemanticFirewall] Redacted ${redactionCount} potential secret(s) using AST and regex.`
            );
        } else {
            this.output.appendLine(
                '[Agent:Retrieving][SemanticFirewall] Scan complete. No secrets redacted.'
            );
        }

        return sanitized;
    }

    // ── Private helpers ───────────────────────────────────────────

    private loadCortexIgnore(): void {
        const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
        if (!workspaceRoot) { return; }

        const defaultPatterns = ['.env', '**/.env', 'secrets/**', '**/secrets/**'];

        const cortexIgnorePath = path.join(workspaceRoot, '.cortexignore');
        try {
            if (fs.existsSync(cortexIgnorePath)) {
                const raw = fs.readFileSync(cortexIgnorePath, 'utf-8');
                this.ignorePatterns = raw
                    .split('\n')
                    .map((line) => line.trim())
                    .filter((line) => line.length > 0 && !line.startsWith('#'));
                for (const pattern of defaultPatterns) {
                    if (!this.ignorePatterns.includes(pattern)) {
                        this.ignorePatterns.push(pattern);
                    }
                }
                this.output.appendLine(
                    `[SemanticFirewall] Loaded ${this.ignorePatterns.length} patterns from .cortexignore`
                );
            } else {
                this.ignorePatterns = [...defaultPatterns];
                this.output.appendLine('[SemanticFirewall] No .cortexignore found — using defaults.');
            }
        } catch (err) {
            this.output.appendLine(`[SemanticFirewall] Error reading .cortexignore: ${err}`);
        }
    }
}
