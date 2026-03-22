'use client';

import React, { useState, useEffect, useCallback } from 'react';
import SummaryWidget from '@/components/team/SummaryWidget';
import PMGuestDashboard from '@/components/PMGuestDashboard';

interface DashboardProps {
    token: string;
    backendUrl?: string;
    mode?: 'developer' | 'pm';
    isGuestPm?: boolean;
    isGuestDeveloper?: boolean;
}

interface Stats {
    totalSnapshots: number;
    lastSnapshotTime: string | null;
    activeProject: string;
}

function getUserIdFromToken(token: string): string | null {
    try {
        const payloadBase64 = token.split('.')[1];
        if (!payloadBase64) {
            return null;
        }

        const base64 = payloadBase64.replace(/-/g, '+').replace(/_/g, '/');
        const padded = base64 + '='.repeat((4 - (base64.length % 4)) % 4);
        const payload = JSON.parse(atob(padded));
        return typeof payload.sub === 'string' ? payload.sub : null;
    } catch {
        return null;
    }
}

export default function Dashboard({ 
    token, 
    backendUrl = 'https://sc-backend-suhaan.azurewebsites.net',
    mode = 'developer',
    isGuestPm = false,
    isGuestDeveloper = false,
}: DashboardProps) {
    if (mode === 'pm') {
        return <PMGuestDashboard token={token} isGuestPm={isGuestPm} backendUrl={backendUrl} />;
    }

    const userId = getUserIdFromToken(token);
    const [stats, setStats] = useState<Stats>({
        totalSnapshots: 0,
        lastSnapshotTime: null,
        activeProject: 'SecondCortex Labs'
    });

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

    useEffect(() => {
        fetchStats();
        const intervalId = window.setInterval(fetchStats, 5000);
        return () => window.clearInterval(intervalId);
    }, [fetchStats]);

    return (
        <div className="sc-dashboard-wrap">
            <div className="sc-dashboard-inner">
                <div className="sc-section-header">
                    <p className="section-label">Control Surface</p>
                    <h1 className="section-title">Developer Dashboard</h1>
                    <p className="section-desc">View your SecondCortex memory system stats and activity summaries.</p>
                    {isGuestDeveloper && <p className="pm-mode-chip">Guest Session: Suhaan</p>}
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
                </div>

                {userId && (
                    <div className="sc-dashboard-panel">
                        <div className="sc-dashboard-panel-inner" style={{ display: 'block' }}>
                            <div className="sc-dashboard-text" style={{ marginBottom: 16 }}>
                                <h2 className="sc-dashboard-h2">Your Activity</h2>
                                <p className="sc-dashboard-p">Daily and weekly summaries from the shared summary service.</p>
                            </div>

                            <div className="sc-guide-grid">
                                <div className="sc-guide-card">
                                    <SummaryWidget
                                        userId={userId}
                                        period="daily"
                                        context="individual"
                                        token={token}
                                    />
                                </div>
                                <div className="sc-guide-card">
                                    <SummaryWidget
                                        userId={userId}
                                        period="weekly"
                                        context="individual"
                                        token={token}
                                    />
                                </div>
                            </div>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}

function MonoIcon({ kind }: { kind: 'storage' | 'workspace' }) {
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
    return (
        <svg {...baseProps}><rect x="2.3" y="3" width="11.4" height="10" rx="1.4" /><path d="M2.3 6.2h11.4" /><path d="M5 9h2.5" /></svg>
    );
}

function StatCard({ title, value, subtitle, icon }: { title: string, value: string, subtitle: string, icon: 'storage' | 'workspace' }) {
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
