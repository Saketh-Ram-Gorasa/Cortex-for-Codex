'use client';

import React, { useState, useEffect, useCallback } from 'react';
import SummaryWidget from '@/components/team/SummaryWidget';
import TeamDashboard from '@/components/team/TeamDashboard';
import PMGuestDashboard from '@/components/PMGuestDashboard';
import ProjectManager from '@/components/ProjectManager';
import ProjectSelector from '@/components/ProjectSelector';

interface DashboardProps {
    token: string;
    backendUrl?: string;
    mode?: 'developer' | 'pm';
    isGuestPm?: boolean;
    isGuestDeveloper?: boolean;
    selectedProjectId: string | null;
    onSelectedProjectChange: (projectId: string | null) => void;
}

interface Stats {
    totalSnapshots: number;
    lastSnapshotTime: string | null;
    activeProject: string;
}

interface TeamInfo {
    id: string;
    name: string;
    team_lead_id: string;
    member_count: number;
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
    backendUrl =
        process.env.NEXT_PUBLIC_BACKEND_URL ||
        (typeof window !== 'undefined' && ['localhost', '127.0.0.1'].includes(window.location.hostname)
            ? 'http://127.0.0.1:8000'
            : 'https://sc-backend-suhaan.azurewebsites.net'),
    mode = 'developer',
    isGuestPm = false,
    isGuestDeveloper = false,
    selectedProjectId,
    onSelectedProjectChange,
}: DashboardProps) {
    if (mode === 'pm') {
        return <PMGuestDashboard token={token} isGuestPm={isGuestPm} backendUrl={backendUrl} />;
    }

    const userId = getUserIdFromToken(token);
    const [showProjectManager, setShowProjectManager] = useState(false);
    const [showTeamModal, setShowTeamModal] = useState(false);
    const [showTeamDashboard, setShowTeamDashboard] = useState(false);
    const [teams, setTeams] = useState<TeamInfo[]>([]);
    const [selectedTeamId, setSelectedTeamId] = useState<string | null>(null);
    const [teamAction, setTeamAction] = useState<'create' | 'join'>('create');
    const [teamNameInput, setTeamNameInput] = useState('');
    const [joinCodeInput, setJoinCodeInput] = useState('');
    const [generatedInviteCode, setGeneratedInviteCode] = useState('');
    const [teamActionError, setTeamActionError] = useState<string | null>(null);
    const [teamActionNotice, setTeamActionNotice] = useState<string | null>(null);
    const [teamLoading, setTeamLoading] = useState(false);
    const [projectRefreshKey, setProjectRefreshKey] = useState(0);
    const [selectedProjectName, setSelectedProjectName] = useState<string | null>(null);
    const [stats, setStats] = useState<Stats>({
        totalSnapshots: 0,
        lastSnapshotTime: null,
        activeProject: 'No Project Selected'
    });

    const fetchStats = useCallback(async () => {
        try {
            const projectQuery = selectedProjectId ? `&projectId=${encodeURIComponent(selectedProjectId)}` : '';
            const res = await fetch(`${backendUrl}/api/v1/snapshots/timeline?limit=1000${projectQuery}`, {
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
                        activeProject: selectedProjectId ? 'Selected Project' : 'All Projects',
                    }));
                } else {
                    setStats(prev => ({
                        ...prev,
                        totalSnapshots: 0,
                        lastSnapshotTime: null,
                        activeProject: selectedProjectId ? 'Selected Project' : 'All Projects',
                    }));
                }
            }
        } catch (err) {
            console.error("Failed to fetch stats", err);
        }
    }, [backendUrl, token, selectedProjectId]);

    useEffect(() => {
        fetchStats();
        const intervalId = window.setInterval(fetchStats, 5000);
        return () => window.clearInterval(intervalId);
    }, [fetchStats]);

    const fetchMyTeams = useCallback(async () => {
        setTeamLoading(true);
        setTeamActionError(null);
        try {
            const res = await fetch(`${backendUrl}/api/v1/teams/mine`, {
                headers: { Authorization: `Bearer ${token}` },
            });
            if (!res.ok) {
                throw new Error(`Failed to load teams (${res.status})`);
            }

            const data = (await res.json()) as TeamInfo[];
            setTeams(Array.isArray(data) ? data : []);
            setSelectedTeamId((prev) => {
                if (prev && data.some((team) => team.id === prev)) {
                    return prev;
                }
                return data.length > 0 ? data[0].id : null;
            });
        } catch (err) {
            setTeamActionError(err instanceof Error ? err.message : 'Failed to fetch teams');
        } finally {
            setTeamLoading(false);
        }
    }, [backendUrl, token]);

    const openTeamsModal = useCallback(async () => {
        setShowTeamModal(true);
        setTeamAction('create');
        setTeamActionError(null);
        setTeamActionNotice(null);
        setGeneratedInviteCode('');
        await fetchMyTeams();
    }, [fetchMyTeams]);

    const handleCreateTeam = useCallback(async () => {
        const trimmedName = teamNameInput.trim();
        if (!trimmedName) {
            setTeamActionError('Enter a team name first.');
            return;
        }

        setTeamLoading(true);
        setTeamActionError(null);
        setTeamActionNotice(null);
        try {
            const res = await fetch(`${backendUrl}/api/v1/teams`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    Authorization: `Bearer ${token}`,
                },
                body: JSON.stringify({ name: trimmedName }),
            });

            const payload = await res.json().catch(() => ({}));
            if (!res.ok) {
                throw new Error(payload.detail || 'Failed to create team');
            }

            setGeneratedInviteCode(String(payload.invite_code || ''));
            setTeamActionNotice('Team created successfully. Share the invite code with teammates.');
            setTeamNameInput('');
            await fetchMyTeams();
            if (payload.team_id) {
                setSelectedTeamId(String(payload.team_id));
            }
        } catch (err) {
            setTeamActionError(err instanceof Error ? err.message : 'Failed to create team');
        } finally {
            setTeamLoading(false);
        }
    }, [backendUrl, token, teamNameInput, fetchMyTeams]);

    const handleJoinTeam = useCallback(async () => {
        const trimmedCode = joinCodeInput.trim();
        if (!trimmedCode) {
            setTeamActionError('Enter an invite code first.');
            return;
        }

        setTeamLoading(true);
        setTeamActionError(null);
        setTeamActionNotice(null);
        try {
            const res = await fetch(`${backendUrl}/api/v1/teams/join`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    Authorization: `Bearer ${token}`,
                },
                body: JSON.stringify({ invite_code: trimmedCode }),
            });
            const payload = await res.json().catch(() => ({}));
            if (!res.ok) {
                throw new Error(payload.detail || 'Failed to join team');
            }

            setJoinCodeInput('');
            setTeamActionNotice(`Joined team ${payload.name || ''}`.trim());
            await fetchMyTeams();
            if (payload.team_id) {
                setSelectedTeamId(String(payload.team_id));
            }
        } catch (err) {
            setTeamActionError(err instanceof Error ? err.message : 'Failed to join team');
        } finally {
            setTeamLoading(false);
        }
    }, [backendUrl, token, joinCodeInput, fetchMyTeams]);

    const selectedTeam = teams.find((team) => team.id === selectedTeamId) || null;

    return (
        <div className="sc-dashboard-wrap">
            <div className="sc-dashboard-inner">
                <div className="sc-section-header">
                    <p className="section-label">Control Surface</p>
                    <h1 className="section-title">Developer Dashboard</h1>
                    <p className="section-desc">View your SecondCortex memory system stats and activity summaries.</p>
                    {isGuestDeveloper && <p className="pm-mode-chip">Guest Session: Suhaan</p>}
                    <div style={{ display: 'flex', gap: '8px', alignItems: 'center', marginTop: '8px' }}>
                        <ProjectSelector
                            token={token}
                            backendUrl={backendUrl}
                            selectedProjectId={selectedProjectId}
                            onChange={onSelectedProjectChange}
                            refreshKey={projectRefreshKey}
                            onSelectedNameChange={setSelectedProjectName}
                        />
                        <button
                            type="button"
                            className="btn-secondary"
                            onClick={() => setShowProjectManager(true)}
                        >
                            My Projects
                        </button>
                        <button
                            type="button"
                            className="btn-secondary"
                            onClick={openTeamsModal}
                        >
                            Teams
                        </button>
                        <button
                            type="button"
                            className="btn-secondary"
                            onClick={async () => {
                                await fetchMyTeams();
                                setShowTeamDashboard(true);
                            }}
                        >
                            My Teams
                        </button>
                    </div>
                </div>

                {showProjectManager && (
                    <ProjectManager
                        token={token}
                        backendUrl={backendUrl}
                        onClose={() => setShowProjectManager(false)}
                        onProjectsChanged={() => {
                            fetchStats();
                            setProjectRefreshKey((value) => value + 1);
                        }}
                    />
                )}

                {showTeamDashboard && (
                    <div className="sc-modal-wrap">
                        <div className="sc-modal-backdrop" onClick={() => setShowTeamDashboard(false)} />
                        <div className="sc-modal-card" style={{ maxWidth: '1200px', width: '95vw' }}>
                            <div className="sc-modal-stack" style={{ gap: 12 }}>
                                <div className="sc-modal-head">
                                    <div className="sc-modal-emoji">Team</div>
                                    <h3 className="sc-modal-title">My Teams</h3>
                                    <p className="sc-modal-sub">Choose a team to open team snapshots, summaries, and chatbot.</p>
                                </div>

                                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                                    {teams.map((team) => (
                                        <button
                                            key={team.id}
                                            type="button"
                                            className="btn-secondary"
                                            onClick={() => setSelectedTeamId(team.id)}
                                            style={{
                                                borderColor: selectedTeamId === team.id ? 'var(--accent)' : undefined,
                                                color: selectedTeamId === team.id ? 'var(--text)' : undefined,
                                            }}
                                        >
                                            {team.name}
                                        </button>
                                    ))}
                                </div>

                                {teamLoading && <p className="sc-auth-sub">Loading team data...</p>}
                                {!teamLoading && teams.length === 0 && (
                                    <p className="sc-auth-sub">You are not in any team yet. Use the Teams button to create or join one.</p>
                                )}

                                {selectedTeam && (
                                    <TeamDashboard
                                        teamId={selectedTeam.id}
                                        token={token}
                                        backendUrl={backendUrl}
                                    />
                                )}

                                <button onClick={() => setShowTeamDashboard(false)} className="btn-primary sc-modal-close">
                                    Close
                                </button>
                            </div>
                        </div>
                    </div>
                )}

                {showTeamModal && (
                    <div className="sc-modal-wrap">
                        <div className="sc-modal-backdrop" onClick={() => setShowTeamModal(false)} />
                        <div className="sc-modal-card">
                            <div className="sc-modal-stack">
                                <div className="sc-modal-head">
                                    <div className="sc-modal-emoji">Team</div>
                                    <h3 className="sc-modal-title">Team Space</h3>
                                    <p className="sc-modal-sub">Create a team or join with an invite code.</p>
                                </div>

                                <div style={{ display: 'flex', gap: 8 }}>
                                    <button
                                        type="button"
                                        className="btn-secondary"
                                        onClick={() => {
                                            setTeamAction('create');
                                            setTeamActionError(null);
                                            setTeamActionNotice(null);
                                        }}
                                    >
                                        Create Team
                                    </button>
                                    <button
                                        type="button"
                                        className="btn-secondary"
                                        onClick={() => {
                                            setTeamAction('join');
                                            setTeamActionError(null);
                                            setTeamActionNotice(null);
                                        }}
                                    >
                                        Join Team
                                    </button>
                                </div>

                                {teamAction === 'create' ? (
                                    <>
                                        <input
                                            type="text"
                                            value={teamNameInput}
                                            onChange={(e) => setTeamNameInput(e.target.value)}
                                            placeholder="Team name"
                                            className="sc-auth-input"
                                        />
                                        <button
                                            type="button"
                                            className="btn-primary"
                                            onClick={handleCreateTeam}
                                            disabled={teamLoading}
                                        >
                                            {teamLoading ? 'Creating...' : 'Create Team'}
                                        </button>
                                        {generatedInviteCode && (
                                            <div className="sc-modal-key">
                                                <span className="sc-modal-key-text">{generatedInviteCode}</span>
                                                <button
                                                    type="button"
                                                    className="btn-secondary"
                                                    onClick={() => navigator.clipboard.writeText(generatedInviteCode)}
                                                >
                                                    Copy Code
                                                </button>
                                            </div>
                                        )}
                                    </>
                                ) : (
                                    <>
                                        <input
                                            type="text"
                                            value={joinCodeInput}
                                            onChange={(e) => setJoinCodeInput(e.target.value.toUpperCase())}
                                            placeholder="Invite code"
                                            className="sc-auth-input"
                                        />
                                        <button
                                            type="button"
                                            className="btn-primary"
                                            onClick={handleJoinTeam}
                                            disabled={teamLoading}
                                        >
                                            {teamLoading ? 'Joining...' : 'Join Team'}
                                        </button>
                                    </>
                                )}

                                {teamActionError && <p className="sc-auth-error">{teamActionError}</p>}
                                {teamActionNotice && <p className="sc-auth-sub">{teamActionNotice}</p>}

                                <div className="sc-modal-warn">
                                    <span>My Teams</span>
                                    <p>
                                        {teams.length > 0
                                            ? teams.map((team) => `${team.name} (${team.member_count})`).join(', ')
                                            : 'No teams yet.'}
                                    </p>
                                </div>

                                <button
                                    onClick={() => {
                                        setShowTeamModal(false);
                                        setGeneratedInviteCode('');
                                    }}
                                    className="btn-primary sc-modal-close"
                                >
                                    Done
                                </button>
                            </div>
                        </div>
                    </div>
                )}

                <div className="sc-stats-grid">
                    <StatCard 
                        title="Memory Snapshots" 
                        value={stats.totalSnapshots.toString()} 
                        subtitle={stats.lastSnapshotTime ? `Last update: ${new Date(stats.lastSnapshotTime).toLocaleTimeString()}` : "No snapshots yet"} 
                        icon="storage"
                    />
                    <StatCard 
                        title="Active Project" 
                        value={selectedProjectName || 'No Project Selected'} 
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
                                        selectedProjectId={selectedProjectId}
                                    />
                                </div>
                                <div className="sc-guide-card">
                                    <SummaryWidget
                                        userId={userId}
                                        period="weekly"
                                        context="individual"
                                        token={token}
                                        selectedProjectId={selectedProjectId}
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
