'use client';

import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import ContextGraph from '@/components/ContextGraph';
import Dashboard from '@/components/Dashboard';
import ProjectSelector from '@/components/ProjectSelector';
import ProjectManager from '@/components/ProjectManager';
import TeamDashboard from '@/components/team/TeamDashboard';

type SessionMode = 'developer' | 'pm';

interface TeamInfo {
  id: string;
  name: string;
  team_lead_id: string;
  member_count: number;
}

/**
 * AuthGate: protection wrapper for dashboard and live graph.
 * Supports:
 * - Standard developer login
 * - PM login (?pm=true)
 * - PM guest mode (?pm=true&guest=true)
 */
export default function AuthGate() {
  const router = useRouter();

  const [token, setToken] = useState<string | null>(null);
  const [isChecking, setIsChecking] = useState(true);
  const [activeTab, setActiveTab] = useState<'dashboard' | 'live' | 'team'>('dashboard');
  const [sessionMode, setSessionMode] = useState<SessionMode>('developer');
  const [isPmGuest, setIsPmGuest] = useState(false);
  const [isDevGuest, setIsDevGuest] = useState(false);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [selectedProjectName, setSelectedProjectName] = useState<string | null>(null);
  const [projectRefreshKey, setProjectRefreshKey] = useState(0);

  const [mcpKey, setMcpKey] = useState<string | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [showMcpModal, setShowMcpModal] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // Project Manager modal
  const [showProjectManager, setShowProjectManager] = useState(false);

  // Teams state
  const [showTeamModal, setShowTeamModal] = useState(false);
  const [teams, setTeams] = useState<TeamInfo[]>([]);
  const [selectedTeamId, setSelectedTeamId] = useState<string | null>(null);
  const [teamAction, setTeamAction] = useState<'create' | 'join'>('create');
  const [teamNameInput, setTeamNameInput] = useState('');
  const [joinCodeInput, setJoinCodeInput] = useState('');
  const [generatedInviteCode, setGeneratedInviteCode] = useState('');
  const [teamActionError, setTeamActionError] = useState<string | null>(null);
  const [teamActionNotice, setTeamActionNotice] = useState<string | null>(null);
  const [teamLoading, setTeamLoading] = useState(false);

  const backendUrl =
    process.env.NEXT_PUBLIC_BACKEND_URL ||
    (typeof window !== 'undefined' && ['localhost', '127.0.0.1'].includes(window.location.hostname)
      ? 'http://127.0.0.1:8000'
      : 'https://sc-backend-suhaan.azurewebsites.net');

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const pmQuery = params.get('pm') === 'true';
    const guestQuery = params.get('guest') === 'true';
    const storedPmGuest = localStorage.getItem('sc_pm_guest_mode') === 'true';
    const storedPmAuth = localStorage.getItem('sc_pm_mode') === 'auth' || storedPmGuest;
    const storedDevGuest = localStorage.getItem('sc_dev_guest_mode') === 'true';

    const storedToken = localStorage.getItem('sc_jwt_token');
    if (!storedToken) {
      if (pmQuery) {
        const redirect = guestQuery ? '/?pm=true&guest=true' : '/?pm=true';
        router.push(redirect);
      } else {
        router.push('/');
      }
      setIsChecking(false);
      return;
    }

    const nextMode: SessionMode = pmQuery || storedPmAuth ? 'pm' : 'developer';
    const nextGuest = nextMode === 'pm' && (guestQuery || storedPmGuest);
    setSessionMode(nextMode);
    setIsPmGuest(nextGuest);
    setIsDevGuest(nextMode === 'developer' && storedDevGuest);
    setToken(storedToken);
    if (nextGuest) {
      setActiveTab('dashboard');
    }

    if (nextMode === 'developer') {
      fetchMcpKey(storedToken);
    }

    setIsChecking(false);
  }, [router]);

  const fetchMcpKey = async (authToken: string) => {
    try {
      const res = await fetch(`${backendUrl}/api/v1/auth/mcp-key`, {
        headers: { Authorization: `Bearer ${authToken}` },
      });
      if (res.ok) {
        const data = await res.json();
        if (data.api_key) {
          setMcpKey(data.api_key);
        }
      }
    } catch (err) {
      console.error('Failed to fetch MCP key', err);
    }
  };

  const handleGenerateKey = async () => {
    if (!token) {
      return;
    }

    setIsGenerating(true);
    setError(null);
    try {
      const res = await fetch(`${backendUrl}/api/v1/auth/mcp-key`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setMcpKey(data.api_key);
        setShowMcpModal(true);
      } else {
        setError('Failed to generate key. Please try again.');
      }
    } catch {
      setError('Connection error. Check your internet.');
    } finally {
      setIsGenerating(false);
    }
  };

  const copyToClipboard = () => {
    if (mcpKey) {
      navigator.clipboard.writeText(mcpKey);
      setNotice('API key copied to clipboard.');
    }
  };

  // --- Team-related handlers ---
  const fetchMyTeams = useCallback(async () => {
    if (!token) return;
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

  const handleLogout = () => {
    localStorage.removeItem('sc_jwt_token');
    localStorage.removeItem('sc_pm_mode');
    localStorage.removeItem('sc_pm_guest_mode');
    localStorage.removeItem('sc_dev_guest_mode');

    setToken(null);
    setSessionMode('developer');
    setIsPmGuest(false);
    setIsDevGuest(false);
    setActiveTab('dashboard');

    router.push('/');
  };

  if (isChecking) {
    return (
      <div className="sc-shell sc-dashboard-wrap">
        <div className="sc-dashboard-inner">
          <div className="sc-shimmer-card" aria-live="polite">
            <div className="sc-shimmer-stack">
              <div className="sc-shimmer-line xl w-40" />
              <div className="sc-shimmer-line lg w-60" />
              <div className="sc-shimmer-line w-80" />
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (!token) {
    return null;
  }

  // Team Dashboard full-screen view
  if (activeTab === 'team' && selectedTeam) {
    return (
      <div className="sc-shell sc-app-shell">
        <div className="sc-app-topbar">
          <div className="nav-logo">
            Second<span>Cortex</span>
          </div>

          <div className="sc-app-tabs">
            <button
              onClick={() => setActiveTab('dashboard')}
              className="sc-app-tab"
            >
              Dashboard
            </button>
            <button
              onClick={() => setActiveTab('live')}
              className="sc-app-tab"
            >
              Live Context Graph
            </button>
            <button
              className="sc-app-tab active"
            >
              Team Space
            </button>
          </div>

          <button onClick={handleLogout} className="btn-secondary sc-logout" type="button">
            Logout
          </button>
        </div>

        <div className="sc-app-content custom-scrollbar">
          <TeamDashboard
            teamId={selectedTeam.id}
            token={token}
            backendUrl={backendUrl}
            teams={teams}
            onTeamChange={setSelectedTeamId}
            onClose={() => setActiveTab('dashboard')}
          />
        </div>

        <style jsx global>{`
          .sc-role-badge {
            display: inline-block;
            margin-left: 8px;
            padding: 2px 6px;
            border: 1px solid rgba(255, 255, 255, 0.4);
            font-family: var(--font-mono);
            font-size: 9px;
            letter-spacing: 0.08em;
            vertical-align: middle;
          }
          .custom-scrollbar::-webkit-scrollbar {
            width: 6px;
          }
          .custom-scrollbar::-webkit-scrollbar-track {
            background: transparent;
          }
          .custom-scrollbar::-webkit-scrollbar-thumb {
            background: rgba(255, 255, 255, 0.1);
            border-radius: 10px;
          }
          .custom-scrollbar::-webkit-scrollbar-thumb:hover {
            background: rgba(255, 255, 255, 0.2);
          }
        `}</style>
      </div>
    );
  }

  return (
    <div className="sc-shell sc-app-shell">
      <div className="sc-app-topbar">
        <div className="nav-logo">
          Second<span>Cortex</span>
          {sessionMode === 'pm' && <span className="sc-role-badge">PM</span>}
          {sessionMode === 'developer' && isDevGuest && <span className="sc-role-badge">Guest</span>}
        </div>

        <div className="sc-app-tabs">
          <button
            onClick={() => setActiveTab('dashboard')}
            className={`sc-app-tab ${activeTab === 'dashboard' ? 'active' : ''}`}
          >
            {sessionMode === 'pm' ? 'Team Cortex' : 'Dashboard'}
          </button>
          {!isPmGuest && (
            <button
              onClick={() => setActiveTab('live')}
              className={`sc-app-tab ${activeTab === 'live' ? 'active' : ''}`}
            >
              Live Context Graph
            </button>
          )}
        </div>

        {/* Project selector in navbar */}
        {sessionMode === 'developer' && (
          <div className="sc-navbar-project-group">
            <ProjectSelector
              token={token}
              backendUrl={backendUrl}
              selectedProjectId={selectedProjectId}
              onChange={setSelectedProjectId}
              refreshKey={projectRefreshKey}
              onSelectedNameChange={setSelectedProjectName}
            />
          </div>
        )}

        {/* Navbar action buttons */}
        {sessionMode === 'developer' && (
          <div className="sc-navbar-actions">
            <button
              type="button"
              className="sc-nav-action-btn"
              onClick={() => setShowProjectManager(true)}
              title="Manage Projects"
            >
              <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"><rect x="2.3" y="3" width="11.4" height="10" rx="1.4" /><path d="M2.3 6.2h11.4" /><path d="M5 9h2.5" /></svg>
              <span>Projects</span>
            </button>
            <button
              type="button"
              className="sc-nav-action-btn"
              onClick={openTeamsModal}
              title="Create or Join Teams"
            >
              <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"><circle cx="6" cy="5" r="2.5" /><path d="M1.5 13.5c0-2.5 2-4.5 4.5-4.5s4.5 2 4.5 4.5" /><circle cx="11.5" cy="5.5" r="1.8" /><path d="M14.5 13.5c0-2 -1.3-3.5-3-3.5" /></svg>
              <span>Teams</span>
            </button>
            <button
              type="button"
              className="sc-nav-action-btn"
              onClick={async () => {
                await fetchMyTeams();
                if (teams.length > 0 || selectedTeamId) {
                  setActiveTab('team');
                } else {
                  openTeamsModal();
                }
              }}
              title="View Team Dashboard"
            >
              <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"><rect x="1.5" y="2" width="13" height="12" rx="1.5" /><path d="M1.5 6h13" /><path d="M5.5 6v8" /></svg>
              <span>My Teams</span>
            </button>
            <button
              onClick={mcpKey ? () => setShowMcpModal(true) : handleGenerateKey}
              disabled={isGenerating}
              className="sc-nav-action-btn sc-mcp-action"
              title={mcpKey ? 'View MCP Integration' : 'Generate MCP API Key'}
            >
              <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"><circle cx="6" cy="6" r="4" /><path d="M9 9l5 5" /><path d="M12 11l2 0" /><path d="M11 12l0 2" /></svg>
              <span>{isGenerating ? '...' : mcpKey ? 'MCP Key' : 'MCP'}</span>
            </button>
          </div>
        )}

        <button onClick={handleLogout} className="btn-secondary sc-logout" type="button">
          {isPmGuest ? 'Exit PM Guest' : 'Logout'}
        </button>
      </div>

      <div className="sc-app-content custom-scrollbar">
        {activeTab === 'dashboard' ? (
          <Dashboard
            token={token}
            mode={sessionMode}
            isGuestPm={isPmGuest}
            isGuestDeveloper={isDevGuest}
            selectedProjectId={selectedProjectId}
            selectedProjectName={selectedProjectName}
          />
        ) : sessionMode === 'pm' && isPmGuest ? (
          <div className="sc-dashboard-wrap">
            <div className="sc-dashboard-inner">
              <div className="sc-dashboard-panel">
                <div className="sc-dashboard-panel-inner" style={{ display: 'block' }}>
                  <h2 className="sc-dashboard-h2">Live Context Graph Disabled in PM Guest Mode</h2>
                  <p className="sc-dashboard-p">
                    Use Team Cortex to inspect teammate snapshots and compression summaries. Authenticated Team Cortex login
                    enables live graph access.
                  </p>
                </div>
              </div>
            </div>
          </div>
        ) : (
          <ContextGraph
            token={token}
            onUnauthorized={handleLogout}
            selectedProjectId={selectedProjectId}
          />
        )}
      </div>

      <style jsx global>{`
        .sc-role-badge {
          display: inline-block;
          margin-left: 8px;
          padding: 2px 6px;
          border: 1px solid rgba(255, 255, 255, 0.4);
          font-family: var(--font-mono);
          font-size: 9px;
          letter-spacing: 0.08em;
          vertical-align: middle;
        }
        .custom-scrollbar::-webkit-scrollbar {
          width: 6px;
        }
        .custom-scrollbar::-webkit-scrollbar-track {
          background: transparent;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb {
          background: rgba(255, 255, 255, 0.1);
          border-radius: 10px;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover {
          background: rgba(255, 255, 255, 0.2);
        }
      `}</style>

      {/* Project Manager Modal */}
      {showProjectManager && (
        <ProjectManager
          token={token}
          backendUrl={backendUrl}
          onClose={() => setShowProjectManager(false)}
          onProjectsChanged={() => {
            setProjectRefreshKey((value) => value + 1);
          }}
        />
      )}

      {/* Teams Modal */}
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
                    {teamLoading ? (
                      <>
                        <span className="loading-ring" aria-hidden="true" />
                        Creating…
                      </>
                    ) : (
                      'Create Team'
                    )}
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
                    {teamLoading ? (
                      <>
                        <span className="loading-ring" aria-hidden="true" />
                        Joining…
                      </>
                    ) : (
                      'Join Team'
                    )}
                  </button>
                </>
              )}

              {teamActionError && <p className="sc-auth-error">{teamActionError}</p>}
              {teamActionNotice && <p className="sc-auth-sub">{teamActionNotice}</p>}

              <div className="sc-modal-warn">
                <span>My Teams</span>
                {teams.length > 0 ? (
                  <div style={{ display: 'grid', gap: '6px', marginTop: '6px' }}>
                    {teams.map((team) => (
                      <div
                        key={team.id}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '8px',
                          padding: '6px 8px',
                          border: '1px solid var(--border)',
                          borderRadius: '6px',
                          fontSize: '12px',
                          fontFamily: 'var(--font-mono)',
                        }}
                      >
                        <span style={{ flex: 1 }}>{team.name} ({team.member_count})</span>
                        <button
                          type="button"
                          className="btn-secondary"
                          style={{ fontSize: '10px', padding: '4px 8px' }}
                          onClick={async () => {
                            if (!window.confirm(`Leave team "${team.name}"?`)) return;
                            setTeamLoading(true);
                            try {
                              const res = await fetch(`${backendUrl}/api/v1/teams/${team.id}/leave`, {
                                method: 'POST',
                                headers: { Authorization: `Bearer ${token}` },
                              });
                              const payload = await res.json().catch(() => ({}));
                              if (!res.ok) {
                                setTeamActionError(payload.detail || 'Failed to leave team');
                              } else {
                                setTeamActionNotice(`Left team "${team.name}"`);
                                await fetchMyTeams();
                              }
                            } catch {
                              setTeamActionError('Failed to leave team');
                            } finally {
                              setTeamLoading(false);
                            }
                          }}
                        >
                          Leave
                        </button>
                        <button
                          type="button"
                          className="btn-secondary"
                          style={{ fontSize: '10px', padding: '4px 8px', color: '#ff6b6b' }}
                          onClick={async () => {
                            if (!window.confirm(`Delete team "${team.name}"? This cannot be undone.`)) return;
                            setTeamLoading(true);
                            try {
                              const res = await fetch(`${backendUrl}/api/v1/teams/${team.id}`, {
                                method: 'DELETE',
                                headers: { Authorization: `Bearer ${token}` },
                              });
                              const payload = await res.json().catch(() => ({}));
                              if (!res.ok) {
                                setTeamActionError(payload.detail || 'Failed to delete team');
                              } else {
                                setTeamActionNotice(`Deleted team "${team.name}"`);
                                await fetchMyTeams();
                              }
                            } catch {
                              setTeamActionError('Failed to delete team');
                            } finally {
                              setTeamLoading(false);
                            }
                          }}
                        >
                          Delete
                        </button>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p>No teams yet.</p>
                )}
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

      {/* MCP Key Modal */}
      {sessionMode === 'developer' && showMcpModal && (
        <div className="sc-modal-wrap">
          <div className="sc-modal-backdrop" onClick={() => setShowMcpModal(false)} />
          <div className="sc-modal-card">
            <div className="sc-modal-stack">
              <div className="sc-modal-head">
                <div className="sc-modal-emoji">Key</div>
                <h3 className="sc-modal-title">Your MCP API Key</h3>
                <p className="sc-modal-sub">Use this key to authorize external MCP clients.</p>
              </div>

              <div className="sc-modal-key">
                <span className="sc-modal-key-text">{mcpKey}</span>
                <button onClick={copyToClipboard} className="btn-secondary" title="Copy to clipboard">
                  Copy
                </button>
              </div>

              <div className="sc-modal-warn">
                <span>Warning</span>
                <p>Do not share this key publicly. It grants access to your snapshot history.</p>
              </div>

              {error && <p className="sc-auth-error">{error}</p>}
              {notice && <p className="sc-auth-sub">{notice}</p>}

              <button onClick={() => setShowMcpModal(false)} className="btn-primary sc-modal-close">
                Got it
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
