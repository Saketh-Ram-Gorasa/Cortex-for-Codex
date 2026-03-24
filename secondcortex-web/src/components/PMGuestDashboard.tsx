'use client';

import { useEffect, useMemo, useState } from 'react';

interface PMGuestDashboardProps {
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

export default function PMGuestDashboard({ token, isGuestPm, backendUrl }: PMGuestDashboardProps) {
  const apiBase = backendUrl || process.env.NEXT_PUBLIC_BACKEND_URL || 'https://sc-backend-suhaan.azurewebsites.net';

  const [projects, setProjects] = useState<ProjectItem[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [projectSnapshots, setProjectSnapshots] = useState<ProjectSnapshot[]>([]);
  const [projectSnapshotError, setProjectSnapshotError] = useState<string>('');

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [chatPending, setChatPending] = useState(false);

  const [question, setQuestion] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: 'assistant',
      text: 'Welcome PM. Chat is connected to the integrated backend LLM. Ask about project progress, status, or any development questions.',
    },
  ]);

  useEffect(() => {
    let cancelled = false;
    let polling = false;

    const loadData = async (background: boolean) => {
      if (!background) {
        setLoading(true);
        setError(null);
      }
      try {
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

        // Fetch snapshots for selected project
        if (selectedProjectId && projectList.some(p => p.id === selectedProjectId)) {
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
              setProjectSnapshots([]);
            } else {
              const timelineData = (await snapshotsRes.json()) as { timeline: ProjectSnapshot[] };
              setProjectSnapshots(timelineData.timeline || []);
              setProjectSnapshotError('');
            }
          } catch (err) {
            const msg = err instanceof Error ? err.message : 'Snapshot fetch failed';
            setProjectSnapshotError(msg);
            setProjectSnapshots([]);
          }
        }

        if (!cancelled) {
          setLoading(false);
        }
      } catch (err) {
        if (!cancelled && !background) {
          setError(err instanceof Error ? err.message : 'Failed to load PM dashboard data.');
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
  }, [apiBase, token, selectedProjectId]);

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
      const projectContext = selectedProject
        ? [
            `Selected project: ${selectedProject.name}`,
            `Project visibility: ${selectedProject.visibility || 'private'}`,
            `Project status: ${selectedProject.is_archived ? 'archived' : 'active'}`,
            `Total snapshots tracked: ${projectSnapshots.length}`,
            `Recent Project Activity (last 20 snapshots):`,
            ...(projectSnapshots.slice(0, 20).map((snapshot) => `- ${fmtSnapshotLine(snapshot)}`) || []),
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
          <p className="section-label">PM Control Surface</p>
          <h1 className="section-title pm-title">Project Manager Dashboard</h1>
          <p className="section-desc">
            Manage projects and track their evolution. View project snapshots, analyze progress, and chat with AI for project insights.
          </p>
          <p className="pm-mode-chip">{isGuestPm ? 'Guest PM Session' : 'Authenticated PM Session'}</p>
        </div>

        <div className="sc-stats-grid">
          <StatCard title="Active Projects" value={String(projects.length)} subtitle="In your portfolio" />
          <StatCard title="Project Snapshots" value={String(projectSnapshots.length)} subtitle="Evolution history available" />
          <StatCard
            title="Evolution Status"
            value={projectSnapshots.length > 0 ? 'Tracking' : 'Pending'}
            subtitle={selectedProjectId ? `Selected: ${projects.find(p => p.id === selectedProjectId)?.name || 'Unknown'}` : 'Select a project'}
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

        {!loading && !error && (
          <div className="pm-grid" style={{ display: 'grid', gridTemplateColumns: '25% 1fr', gap: '16px', marginTop: '20px' }}>
            {/* LEFT PANEL: Project List */}
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

            {/* RIGHT SIDE: 2-row layout (evolution + chat) */}
            <div style={{ display: 'grid', gridTemplateRows: '1fr 1fr', gap: '16px' }}>
              {/* RIGHT-TOP: Project Evolution */}
              <section className="pm-panel">
                <p className="pm-panel-kicker">Evolution</p>
                <h2 className="pm-panel-title">Project Progress</h2>
                <div className="pm-history">
                  {projectSnapshotError && <p className="sc-auth-error">Snapshot sync error: {projectSnapshotError}</p>}
                  {projectSnapshots.length === 0 && !projectSnapshotError && (
                    <p className="pm-history-summary">No snapshots for this project yet.</p>
                  )}
                  {projectSnapshots.length > 0 && (
                    <div style={{ whiteSpace: 'pre-wrap', fontSize: '12px', color: '#666', padding: '8px', backgroundColor: '#f5f5f5', borderRadius: '4px' }}>
                      {getProjectEvolutionSummary()}
                    </div>
                  )}
                  <div style={{ marginTop: '12px', maxHeight: '200px', overflowY: 'auto' }}>
                    {projectSnapshots.slice(0, 5).map((snapshot) => (
                      <article key={snapshot.id} className="pm-history-item">
                        <div className="pm-history-head">
                          <span>{new Date(toEpochMs(snapshot.timestamp)).toLocaleString()}</span>
                          <span>{snapshot.git_branch || 'no-branch'}</span>
                        </div>
                        <div className="pm-history-file">{snapshot.active_file || 'Unknown file'}</div>
                        <p className="pm-history-summary">{snapshot.summary || 'No summary for this snapshot.'}</p>
                      </article>
                    ))}
                  </div>
                </div>
              </section>

              {/* RIGHT-BOTTOM: Chatbot */}
              <section className="pm-panel">
                <p className="pm-panel-kicker">Assistant</p>
                <h2 className="pm-panel-title">Project Insights</h2>
                <p className="pm-chat-sub">Ask about project progress and evolution.</p>

                <div className="pm-chat-quick">
                  <button type="button" onClick={() => sendQuestion('What is the current project status based on recent activity?')}>
                    Project status
                  </button>
                  <button type="button" onClick={() => sendQuestion('What are the key files and technologies in use?')}>
                    Tech stack
                  </button>
                  <button type="button" onClick={() => sendQuestion('Summarize the project progress.')}>
                    Progress
                  </button>
                </div>

                <div className="pm-chat-log" style={{ maxHeight: '150px', overflowY: 'auto', marginBottom: '12px' }}>
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
                    placeholder="Ask about project"
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
