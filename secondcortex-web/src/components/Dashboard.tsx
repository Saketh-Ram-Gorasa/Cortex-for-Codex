'use client';

import React, { useState, useEffect, useCallback } from 'react';

interface DashboardProps {
    token: string;
    backendUrl?: string;
}

interface Stats {
    totalSnapshots: number;
    lastSnapshotTime: string | null;
    activeProject: string;
}

export default function Dashboard({ 
    token, 
    backendUrl = 'https://sc-backend-suhaan.azurewebsites.net' 
}: DashboardProps) {
    const [stats, setStats] = useState<Stats>({
        totalSnapshots: 0,
        lastSnapshotTime: null,
        activeProject: 'SecondCortex Labs'
    });
    const [mcpKey, setMcpKey] = useState<string | null>(null);
    const [isGenerating, setIsGenerating] = useState(false);
    const [showModal, setShowModal] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [notice, setNotice] = useState<string | null>(null);

    const fetchStats = useCallback(async () => {
        try {
            const res = await fetch(`${backendUrl}/api/v1/snapshots/timeline?limit=1000`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            if (res.ok) {
                const data = await res.json();
                if (data.timeline && data.timeline.length > 0) {
                    const latest = data.timeline[data.timeline.length - 1];
                    setStats(prev => ({
                        ...prev,
                        totalSnapshots: data.timeline.length,
                        lastSnapshotTime: latest?.timestamp ?? null,
                    }));
                } else {
                    setStats(prev => ({
                        ...prev,
                        totalSnapshots: 0,
                        lastSnapshotTime: null,
                    }));
                }
            }
        } catch (err) {
            console.error("Failed to fetch stats", err);
        }
    }, [backendUrl, token]);

    const fetchMcpKey = useCallback(async () => {
        try {
            const res = await fetch(`${backendUrl}/api/v1/auth/mcp-key`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            if (res.ok) {
                const data = await res.json();
                if (data.api_key) {
                    setMcpKey(data.api_key);
                }
            }
        } catch (err) {
            console.error("Failed to fetch MCP key", err);
        }
    }, [backendUrl, token]);

    useEffect(() => {
        fetchStats();
        fetchMcpKey();
        const intervalId = window.setInterval(fetchStats, 5000);
        return () => window.clearInterval(intervalId);
    }, [fetchStats, fetchMcpKey]);

    const handleGenerateKey = async () => {
        setIsGenerating(true);
        setError(null);
        try {
            const res = await fetch(`${backendUrl}/api/v1/auth/mcp-key`, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}` }
            });
            if (res.ok) {
                const data = await res.json();
                setMcpKey(data.api_key);
                setShowModal(true);
            } else {
                setError("Failed to generate key. Please try again.");
            }
        } catch {
            setError("Connection error. Check your internet.");
        } finally {
            setIsGenerating(false);
        }
    };

    const copyToClipboard = () => {
        if (mcpKey) {
            navigator.clipboard.writeText(mcpKey);
            setNotice("API key copied to clipboard.");
        }
    };

    return (
        <div className="sc-dashboard-wrap">
            <div className="sc-dashboard-inner">
                <div className="sc-section-header">
                    <p className="section-label">Control Surface</p>
                    <h1 className="section-title">Developer Dashboard</h1>
                    <p className="section-desc">Manage your SecondCortex memory system and external MCP integrations.</p>
                </div>

                <div className="sc-stats-grid">
                    <StatCard 
                        title="Memory Snapshots" 
                        value={stats.totalSnapshots.toString()} 
                        subtitle={stats.lastSnapshotTime ? `Last update: ${new Date(stats.lastSnapshotTime).toLocaleTimeString()}` : "No snapshots yet"} 
                        icon="storage"
                    />
                    <StatCard 
                        title="Active Project" 
                        value={stats.activeProject} 
                        subtitle="Current workspace scope" 
                        icon="workspace"
                    />
                    <StatCard 
                        title="MCP Status" 
                        value={mcpKey ? "Connected" : "Not Linked"} 
                        subtitle={mcpKey ? "Authentication active" : "Requires API Key"} 
                        icon="connection"
                    />
                </div>

                <div className="sc-dashboard-panel">
                    <div className="sc-dashboard-panel-inner">
                        <div className="sc-dashboard-text">
                            <h2 className="sc-dashboard-h2">
                                <span className="sc-icon-cell"><MonoIcon kind="connection" /></span>
                                MCP Integration (Model Context Protocol)
                            </h2>
                            <p className="sc-dashboard-p">
                                Connect external AI assistants like Claude Desktop or Cursor to your local context memory. 
                                Secure your connection by generating a unique API key.
                            </p>
                        </div>
                        <div className="sc-dashboard-actions">
                            <button
                                onClick={mcpKey ? () => setShowModal(true) : handleGenerateKey}
                                disabled={isGenerating}
                                className="btn-primary sc-dashboard-btn"
                            >
                                {isGenerating ? "Processing..." : mcpKey ? "View Existing Key" : "Generate MCP Key"}
                            </button>
                            {error && <p className="sc-auth-error">{error}</p>}
                            {notice && <p className="sc-auth-sub">{notice}</p>}
                        </div>
                    </div>
                </div>

                <div className="sc-guide-grid">
                    <div className="sc-guide-card">
                        <h3 className="sc-guide-title">Quick Start: Claude Desktop</h3>
                        <pre className="sc-guide-code">
{`"mcpServers": {
  "secondcortex": {
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-sse", "https://sc-backend-suhaan.azurewebsites.net/mcp/sse"],
    "env": {
      "SECOND_CORTEX_API_KEY": "YOUR_KEY_HERE"
    }
  }
}`}
                        </pre>
                    </div>
                                        <div className="sc-guide-card">
                                                <h3 className="sc-guide-title">Integration Tips</h3>
                                                <ul className="sc-guide-list">
                            <li>Keep your API key private — it grants access to your memory.</li>
                            <li>You can regenerate your key at any time to revoke old ones.</li>
                            <li>Ensure your backend is awake by visiting the dashboard occasionally.</li>
                        </ul>
                    </div>
                </div>
            </div>

            {/* Modal */}
            {showModal && (
                <div className="sc-modal-wrap">
                    <div className="sc-modal-backdrop" onClick={() => setShowModal(false)} />
                    <div className="sc-modal-card">
                        <div className="sc-modal-stack">
                            <div className="sc-modal-head">
                                <div className="sc-modal-emoji"><MonoIcon kind="key" /></div>
                                <h3 className="sc-modal-title">Your MCP API Key</h3>
                                <p className="sc-modal-sub">Use this key to authorize external MCP clients.</p>
                            </div>

                            <div className="sc-modal-key">
                                <span className="sc-modal-key-text">{mcpKey}</span>
                                <button 
                                    onClick={copyToClipboard}
                                    className="btn-secondary"
                                    title="Copy to clipboard"
                                >
                                    <MonoIcon kind="copy" />
                                </button>
                            </div>

                            <div className="sc-modal-warn">
                                <span><MonoIcon kind="warning" /></span>
                                <p>
                                    Warning: This key grants full access to your snapshot history. 
                                    Do not share it on public forums or commit it to GitHub.
                                </p>
                            </div>

                            <button 
                                onClick={() => setShowModal(false)}
                                className="btn-primary sc-modal-close"
                            >
                                Got it
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

function MonoIcon({ kind }: { kind: 'storage' | 'workspace' | 'connection' | 'key' | 'copy' | 'warning' }) {
    const baseProps = {
        width: 16,
        height: 16,
        viewBox: '0 0 16 16',
        fill: 'none',
        stroke: 'currentColor',
        strokeWidth: 1.3,
        strokeLinecap: 'round' as const,
        strokeLinejoin: 'round' as const,
        'aria-hidden': true,
    };

    if (kind === 'storage') {
        return (
            <svg {...baseProps}><ellipse cx="8" cy="3.5" rx="5.5" ry="2.2" /><path d="M2.5 3.5v6.2c0 1.2 2.5 2.2 5.5 2.2s5.5-1 5.5-2.2V3.5" /><path d="M2.5 6.6c0 1.2 2.5 2.2 5.5 2.2s5.5-1 5.5-2.2" /></svg>
        );
    }
    if (kind === 'workspace') {
        return (
            <svg {...baseProps}><rect x="2.3" y="3" width="11.4" height="10" rx="1.4" /><path d="M2.3 6.2h11.4" /><path d="M5 9h2.5" /></svg>
        );
    }
    if (kind === 'connection') {
        return (
            <svg {...baseProps}><path d="M5.1 4.4h2.2a2 2 0 0 1 0 4H5.1" /><path d="M10.9 11.6H8.7a2 2 0 1 1 0-4h2.2" /><path d="M6.3 8h3.4" /></svg>
        );
    }
    if (kind === 'key') {
        return (
            <svg {...baseProps}><circle cx="5.4" cy="8" r="2.3" /><path d="M7.7 8h5.8" /><path d="M11.2 8v2" /><path d="M13 8v1.2" /></svg>
        );
    }
    if (kind === 'copy') {
        return (
            <svg {...baseProps}><rect x="5" y="4" width="8" height="9" rx="1" /><path d="M3 10V3.8A.8.8 0 0 1 3.8 3H10" /></svg>
        );
    }
    return (
        <svg {...baseProps}><path d="M8 2.2 13.3 12H2.7L8 2.2Z" /><path d="M8 6v2.8" /><circle cx="8" cy="10.7" r=".7" fill="currentColor" stroke="none" /></svg>
    );
}

function StatCard({ title, value, subtitle, icon }: { title: string, value: string, subtitle: string, icon: 'storage' | 'workspace' | 'connection' }) {
    return (
        <div className="sc-stat-card">
            <div className="sc-stat-head">
                <span className="sc-stat-title">{title}</span>
                <span className="sc-icon-cell"><MonoIcon kind={icon} /></span>
            </div>
            <div>
                <div className="sc-stat-value">{value}</div>
                <div className="sc-stat-sub">{subtitle}</div>
            </div>
        </div>
    );
}
