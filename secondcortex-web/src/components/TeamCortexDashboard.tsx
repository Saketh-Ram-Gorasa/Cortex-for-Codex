'use client';

import { useEffect, useMemo, useState } from 'react';

interface TeamCortexDashboardProps {
  token: string;
  isGuestPm: boolean;
  backendUrl?: string;
}

interface ProjectItem {
  id: string;
  name: string;
  visibility: 'private' | 'team';
  is_archived: boolean;
}

interface ProjectSnapshot {
  id: string;
  user_id: string;
  project_id: string | null;
  timestamp: number;
  active_file: string;
  git_branch: string | null;
  summary: string;
  terminal_commands: string[];
}

interface TeamInfo {
  id: string;
  name: string;
  team_lead_id: string;
  member_count: number;
}

interface EvolutionEntry {
  id: string;
  title: string;
  summary: string;
  timestamp: number;
  snapshot_count: number;
  member_names: string[];
  tag: 'daily' | 'feature';
}

interface EvolutionResponse {
  team_id: string;
  project_id: string | null;
  mode: 'daily' | 'feature';
  snapshot_count: number;
  member_count: number;
  used_project_filter?: boolean;
  entries: EvolutionEntry[];
}

interface ChatMessage {
  role: 'assistant' | 'user';
  text: string;
}

function toEpochMs(ts: number): number {
  if (ts > 10_000_000_000) {
    return ts;
  }
  return ts * 1000;
}

function fmtSnapshotLine(snapshot: ProjectSnapshot): string {
  const when = new Date(toEpochMs(snapshot.timestamp)).toLocaleString();
  return `${when} | ${snapshot.git_branch || 'no-branch'} | ${snapshot.active_file || 'unknown-file'} | ${
    snapshot.summary || 'No summary'
  }`;
}

function parseTokenPayload(token: string): Record<string, unknown> | null {
  try {
    const payloadBase64 = token.split('.')[1];
    if (!payloadBase64) {
      return null;
    }
    const base64 = payloadBase64.replace(/-/g, '+').replace(/_/g, '/');
    const padded = base64 + '='.repeat((4 - (base64.length % 4)) % 4);
    return JSON.parse(atob(padded)) as Record<string, unknown>;
  } catch {
    return null;
  }
}

export default function TeamCortexDashboard({ token, isGuestPm, backendUrl }: TeamCortexDashboardProps) {
  const apiBase = backendUrl || process.env.NEXT_PUBLIC_BACKEND_URL || 'https://sc-backend-suhaan.azurewebsites.net';

  const [projects, setProjects] = useState<ProjectItem[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [projectSnapshots, setProjectSnapshots] = useState<ProjectSnapshot[]>([]);
  const [evolutionEntries, setEvolutionEntries] = useState<EvolutionEntry[]>([]);
  const [teamId, setTeamId] = useState<string | null>(null);
  const [timelineMode, setTimelineMode] = useState<'daily' | 'feature'>('daily');
  const [projectSnapshotError, setProjectSnapshotError] = useState<string>('');

  const [loading, setLoading] = useState(true);
  const [hasLoadedDashboard, setHasLoadedDashboard] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [chatPending, setChatPending] = useState(false);

  const [question, setQuestion] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: 'assistant',
      text: 'Welcome to Team Cortex. Ask about project evolution, delivery risk, or latest team outcomes.',
    },
  ]);

  useEffect(() => {
    let cancelled = false;
    let polling = false;

    const resolveTeamId = async (): Promise<string | null> => {
      const payload = parseTokenPayload(token);
      const role = String(payload?.role || 'user');
      const tokenTeamId = String(payload?.team_id || '').trim();

      if (role === 'pm_guest' && tokenTeamId) {
        return tokenTeamId;
      }

      const teamsRes = await fetch(`${apiBase}/api/v1/teams/mine`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (!teamsRes.ok) {
        return tokenTeamId || null;
      }

      const teams = (await teamsRes.json()) as TeamInfo[];
      if (!Array.isArray(teams) || teams.length === 0) {
        return tokenTeamId || null;
      }

      return teams[0].id;
    };

    const loadData = async (background: boolean) => {
      if (!background && !hasLoadedDashboard) {
        setLoading(true);
        setError(null);
      }
      try {
        const resolvedTeamId = await resolveTeamId();
        if (!cancelled) {
          setTeamId(resolvedTeamId);
        }

        // Fetch projects list
        const projectsRes = await fetch(`${apiBase}/api/v1/projects`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!projectsRes.ok) {
          throw new Error('Unable to fetch projects list.');
        }
        const projectsData = (await projectsRes.json()) as { projects: ProjectItem[] };
        const projectList = projectsData.projects || [];
        
        if (cancelled) {
          return;
        }
        
        setProjects(projectList);
        
        // Auto-select first project if none selected
        if (!selectedProjectId && projectList.length > 0) {
          setSelectedProjectId(projectList[0].id);
        }

        // Fetch snapshots + compressed evolution for selected project
        if (selectedProjectId && projectList.some((p) => p.id === selectedProjectId)) {
          try {
            const snapshotsRes = await fetch(
              `${apiBase}/api/v1/snapshots/timeline?projectId=${encodeURIComponent(selectedProjectId)}&limit=1000`,
              {
                headers: { Authorization: `Bearer ${token}` },
              },
            );
            if (!snapshotsRes.ok) {
              const errBody = await snapshotsRes.json().catch(() => ({}));
              const errDetail =
                typeof errBody?.detail === 'string'
                  ? errBody.detail
                  : `HTTP ${snapshotsRes.status} while fetching project timeline`;
              setProjectSnapshotError(errDetail);
              if (!background) {
                setProjectSnapshots([]);
              }
            } else {
              const timelineData = (await snapshotsRes.json()) as { timeline: ProjectSnapshot[] };
              setProjectSnapshots(timelineData.timeline || []);
              setProjectSnapshotError('');
            }
          } catch (err) {
            const msg = err instanceof Error ? err.message : 'Snapshot fetch failed';
            setProjectSnapshotError(msg);
            if (!background) {
              setProjectSnapshots([]);
            }
          }

          try {
            if (resolvedTeamId) {
              const evolutionRes = await fetch(
                `${apiBase}/api/v1/summaries/team/${encodeURIComponent(resolvedTeamId)}/evolution?mode=${timelineMode}&projectId=${encodeURIComponent(selectedProjectId)}&limit=120`,
                {
                  headers: { Authorization: `Bearer ${token}` },
                },
              );

              if (evolutionRes.ok) {
                const evolutionData = (await evolutionRes.json()) as EvolutionResponse;
                setEvolutionEntries(Array.isArray(evolutionData.entries) ? evolutionData.entries : []);
              } else if (!background) {
                setEvolutionEntries([]);
              }
            } else if (!background) {
              setEvolutionEntries([]);
            }
          } catch {
            if (!background) {
              setEvolutionEntries([]);
            }
          }
        } else {
          setProjectSnapshots([]);
          setEvolutionEntries([]);
        }

        if (!cancelled) {
          if (!hasLoadedDashboard) {
            setHasLoadedDashboard(true);
          }
          setLoading(false);
        }
      } catch (err) {
        if (!cancelled && !background) {
          setError(err instanceof Error ? err.message : 'Failed to load Team Cortex dashboard data.');
          setLoading(false);
        }
      }
    };

    void loadData(false);

    const intervalId = window.setInterval(async () => {
      if (cancelled || polling) {
        return;
      }

      polling = true;
      try {
        await loadData(true);
      } finally {
        polling = false;
      }
    }, 5000);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [apiBase, token, selectedProjectId, timelineMode, hasLoadedDashboard]);

  const sendQuestion = async (input: string) => {
    const trimmed = input.trim();
    if (!trimmed || chatPending) {
      return;
    }

    setMessages((prev) => [...prev, { role: 'user', text: trimmed }]);
    setQuestion('');
    setChatPending(true);

    try {
      const selectedProject = projects.find((p) => p.id === selectedProjectId);
      const topTimeline = evolutionEntries.slice(0, 12);
      const projectContext = selectedProject
        ? [
            `Selected project: ${selectedProject.name}`,
            `Project visibility: ${selectedProject.visibility || 'private'}`,
            `Project status: ${selectedProject.is_archived ? 'archived' : 'active'}`,
            `Total snapshots tracked: ${projectSnapshots.length}`,
        `Timeline mode: ${timelineMode}`,
            `Recent Project Activity (last 20 snapshots):`,
            ...(projectSnapshots.slice(0, 20).map((snapshot) => `- ${fmtSnapshotLine(snapshot)}`) || []),
        `Compressed Team Evolution (latest first):`,
        ...(topTimeline.map((entry) => `- [${new Date(toEpochMs(entry.timestamp)).toLocaleString()}] ${entry.title} | ${entry.summary}`) || []),
            `Project Evolution Summary:`,
            getProjectEvolutionSummary(),
          ].join('\n')
        : 'No project selected.';

      const composedQuestion = [
        'You are assisting a Project Manager on SecondCortex.',
        'Provide practical insights about project progress and evolution.',
        'Do not attribute work to individuals; focus on project status.',
        'Avoid hallucinations and stick to the provided context.',
        projectContext,
        `PM question: ${trimmed}`,
      ].join('\n\n');

      const res = await fetch(`${apiBase}/api/v1/pm/query`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ question: composedQuestion }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'LLM query failed.');
      }

      const data = await res.json();
      const answer =
        typeof data.summary === 'string' && data.summary.trim()
          ? data.summary
          : 'LLM returned an empty answer. Please try rephrasing.';

      setMessages((prev) => [...prev, { role: 'assistant', text: answer }]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          text: `Chatbot error: ${err instanceof Error ? err.message : 'Unknown error'}`,
        },
      ]);
    } finally {
      setChatPending(false);
    }
  };

  // Compute project evolution summary (feature compression)
  const getProjectEvolutionSummary = (): string => {
    if (!selectedProjectId) {
      return 'Select a project to view evolution timeline.';
    }
    
    const snapshots = projectSnapshots;
    if (snapshots.length === 0) {
      return 'No snapshots available for this project yet.';
    }

    // Extract top files, branches, and recent activity
    const fileMap = new Map<string, number>();
    const branchSet = new Set<string>();
    const commandSamples: string[] = [];

    snapshots.forEach((snapshot) => {
      if (snapshot.active_file) {
        const ext = snapshot.active_file.split('.').pop() || 'file';
        const key = `[${ext}] ${snapshot.active_file.split('/').pop()}`;
        fileMap.set(key, (fileMap.get(key) || 0) + 1);
      }
      if (snapshot.git_branch) {
        branchSet.add(snapshot.git_branch);
      }
      if (snapshot.terminal_commands && snapshot.terminal_commands.length > 0) {
        commandSamples.push(...snapshot.terminal_commands.slice(0, 1));
      }
    });

    const topFiles = Array.from(fileMap.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 3)
      .map(([file]) => file);

    const branches = Array.from(branchSet).slice(0, 3);
    const recentActivity = snapshots
      .slice(0, 2)
      .map((s) => `[${new Date(toEpochMs(s.timestamp)).toLocaleTimeString()}] ${fmtSnapshotLine(s)}`)
      .join('\n');

    return [
      `Project Evolution Summary:`,
      `Total snapshots tracked: ${snapshots.length}`,
      `Most active files: ${topFiles.join(', ') || 'none'}`,
      `Active branches: ${branches.join(', ') || 'main'}`,
      `\nRecent Activity:\n${recentActivity}`,
    ].join('\n');
  };

  return (
    <div className="sc-dashboard-wrap">
      <div className="sc-dashboard-inner">
        <div className="sc-section-header pm-header">
          <p className="section-label">Team Cortex Control Surface</p>
          <h1 className="section-title pm-title">Team Cortex</h1>
          <p className="section-desc">
            Track project evolution using compressed timeline summaries, then query the assistant for deeper analysis.
          </p>
          <p className="pm-mode-chip">{isGuestPm ? 'Team Cortex Guest Session' : 'Team Cortex Authenticated Session'}</p>
        </div>

        <div className="sc-stats-grid">
          <StatCard title="Active Projects" value={String(projects.length)} subtitle="In your portfolio" />
          <StatCard title="Project Snapshots" value={String(projectSnapshots.length)} subtitle="Evolution history available" />
          <StatCard
            title="Evolution Status"
            value={evolutionEntries.length > 0 ? 'Tracking' : 'Pending'}
            subtitle={selectedProjectId ? `Selected: ${projects.find((p) => p.id === selectedProjectId)?.name || 'Unknown'}` : 'Select a project'}
          />
        </div>

        {loading && (
          <div className="sc-dashboard-panel">
            <div className="sc-dashboard-panel-inner" style={{ display: 'block' }}>
              <p className="sc-dashboard-p">Loading projects and evolution data...</p>
            </div>
          </div>
        )}

        {error && (
          <div className="sc-dashboard-panel">
            <div className="sc-dashboard-panel-inner" style={{ display: 'block' }}>
              <p className="sc-auth-error">{error}</p>
            </div>
          </div>
        )}

        {!loading && (
          <div style={{ marginTop: '20px' }}>
            {/* TOP: Project List - Full Width */}
            <section className="pm-panel">
              <p className="pm-panel-kicker">Portfolio</p>
              <h2 className="pm-panel-title">Projects</h2>
              <div className="pm-member-list">
                {projects.length === 0 ? (
                  <p style={{ padding: '12px', color: '#999' }}>No projects available.</p>
                ) : (
                  projects.map((project) => (
                    <div key={project.id} className={`pm-member-btn ${project.id === selectedProjectId ? 'active' : ''}`}>
                      <button
                        className="pm-member-main"
                        type="button"
                        onClick={() => setSelectedProjectId(project.id)}
                      >
                        <span className="pm-member-name">{project.name}</span>
                        <span className="pm-member-role">{project.visibility || 'private'}</span>
                      </button>
                    </div>
                  ))
                )}
              </div>
            </section>

            {/* BELOW: 2/3 Evolution + Snapshots (Left) | 1/3 Chatbot (Right) */}
            <div className="pm-grid" style={{ marginTop: '20px', display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '20px' }}>
              {/* LEFT: Timeline Evolution + Project Snapshots */}
              <section className="pm-panel">
                <p className="pm-panel-kicker">Timeline Evolution</p>
                <h2 className="pm-panel-title">Compressed Project Evolution</h2>

                <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
                  <button
                    type="button"
                    className="btn-secondary"
                    style={{ opacity: timelineMode === 'daily' ? 1 : 0.75 }}
                    onClick={() => setTimelineMode('daily')}
                  >
                    Daily
                  </button>
                  <button
                    type="button"
                    className="btn-secondary"
                    style={{ opacity: timelineMode === 'feature' ? 1 : 0.75 }}
                    onClick={() => setTimelineMode('feature')}
                  >
                    Feature
                  </button>
                </div>

                <div className="pm-history" style={{ maxHeight: 600, overflowY: 'auto' }}>
                  {projectSnapshotError && <p className="sc-auth-error">Snapshot sync error: {projectSnapshotError}</p>}
                  {teamId === null && <p className="pm-history-summary">Join or create a team to view team evolution.</p>}
                  
                  {/* Compressed Evolution Entries */}
                  {teamId !== null && evolutionEntries.length === 0 && !projectSnapshotError && projectSnapshots.length === 0 && (
                    <p className="pm-history-summary">No compressed timeline entries are available for this project yet.</p>
                  )}

                  {evolutionEntries.map((entry) => (
                    <article key={entry.id} className="pm-history-item">
                      <div className="pm-history-head">
                        <span>{new Date(toEpochMs(entry.timestamp)).toLocaleString()}</span>
                        <span>{entry.tag.toUpperCase()}</span>
                      </div>
                      <div className="pm-history-file">{entry.title}</div>
                      <p className="pm-history-summary" style={{ whiteSpace: 'pre-line' }}>
                        {entry.summary || 'No summary available for this timeline bucket.'}
                      </p>
                      <p className="pm-history-summary" style={{ marginTop: 8 }}>
                        Contributors: {entry.member_names.join(', ') || 'Unknown'} | Snapshots: {entry.snapshot_count}
                      </p>
                    </article>
                  ))}

                  {/* Project Snapshots */}
                  {projectSnapshots.length > 0 && (
                    <>
                      <div style={{ marginTop: 16, paddingTop: 16, borderTop: '1px solid #333' }}>
                        <h3 style={{ fontSize: '0.9rem', fontWeight: 600, marginBottom: 8, color: '#ccc' }}>Project Snapshots</h3>
                      </div>
                      {projectSnapshots.map((snapshot, idx) => (
                        <article key={snapshot.id || idx} className="pm-history-item" style={{ marginTop: 8 }}>
                          <div className="pm-history-head">
                            <span>{new Date(toEpochMs(snapshot.timestamp)).toLocaleString()}</span>
                            <span style={{ color: '#888' }}>{snapshot.git_branch || 'no-branch'}</span>
                          </div>
                          <div className="pm-history-file">{snapshot.active_file || 'unknown-file'}</div>
                          <p className="pm-history-summary" style={{ marginTop: 4 }}>
                            {snapshot.summary || 'No summary available'}
                          </p>
                        </article>
                      ))}
                    </>
                  )}
                </div>
              </section>

              {/* RIGHT: Chatbot */}
              <section className="pm-panel">
                <p className="pm-panel-kicker">Assistant</p>
                <h2 className="pm-panel-title">Team Cortex Chat</h2>
                <p className="pm-chat-sub">Query any project detail, timeline shift, risk signal, or delivery status.</p>

                <div className="pm-chat-quick">
                  <button type="button" onClick={() => sendQuestion('Where are the current delivery risks based on the latest Team Cortex timeline?')}>
                    Risk windows
                  </button>
                  <button type="button" onClick={() => sendQuestion('What trend do you see in recent timeline outcomes?')}>
                    Outcome trend
                  </button>
                  <button type="button" onClick={() => sendQuestion('What should be the next actions for this project?')}>
                    Next actions
                  </button>
                </div>

                <div className="pm-chat-log" style={{ marginBottom: '12px', maxHeight: 450, overflowY: 'auto' }}>
                  {messages.map((message, index) => (
                    <div key={`${message.role}-${index}`} className={`pm-chat-msg ${message.role}`}>
                      {message.text}
                    </div>
                  ))}
                </div>

                <div className="pm-chat-input-wrap">
                  <input
                    className="query-input"
                    type="text"
                    value={question}
                    onChange={(event) => setQuestion(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter') {
                        void sendQuestion(question);
                      }
                    }}
                    placeholder="Ask Team Cortex"
                  />
                  <button className="query-btn" type="button" disabled={chatPending} onClick={() => void sendQuestion(question)}>
                    {chatPending ? 'Asking...' : 'Ask'}
                  </button>
                </div>
              </section>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function StatCard({ title, value, subtitle }: { title: string; value: string; subtitle: string }) {
  return (
    <div className="sc-stat-card">
      <div className="sc-stat-head">
        <span className="sc-stat-title">{title}</span>
      </div>
      <div>
        <div className="sc-stat-value">{value}</div>
        <div className="sc-stat-sub">{subtitle}</div>
      </div>
    </div>
  );
}
