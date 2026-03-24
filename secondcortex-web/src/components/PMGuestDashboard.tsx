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

interface TeamMember {
  id: string;
  email: string;
  display_name: string;
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

interface TimelineEvolutionEntry {
  id: string;
  dayLabel: string;
  snapshotCount: number;
  topFeatures: string[];
  topBranches: string[];
  combinedSummary: string;
  outcome: 'successful' | 'needs_rework' | 'mixed' | 'in_progress';
}

type TimelineGrouping = 'daily' | 'feature';

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

function summarizeFeatureName(activeFile: string): string {
  const clean = activeFile.replace(/\\/g, '/');
  const base = clean.split('/').pop() || clean;
  return base.replace(/\.[^.]+$/, '') || base;
}

function parseTeamIdFromToken(token: string): string | null {
  try {
    const payloadBase64 = token.split('.')[1];
    if (!payloadBase64) {
      return null;
    }
    const base64 = payloadBase64.replace(/-/g, '+').replace(/_/g, '/');
    const padded = base64 + '='.repeat((4 - (base64.length % 4)) % 4);
    const payload = JSON.parse(atob(padded));
    const teamId = String(payload.team_id || '').trim();
    return teamId || null;
  } catch {
    return null;
  }
}

function classifyOutcome(text: string): TimelineEvolutionEntry['outcome'] {
  const hasFailureSignal = /\b(fail|failed|failure|error|bug|bugs|rollback|revert|blocked|issue|broken|regression|timeout|crash|hotfix|retry|flaky|unstable|degraded|incident)\b/i.test(
    text,
  );
  const hasSuccessSignal = /\b(success|successful|fixed|resolved|merged|completed|shipped|stable|pass|passed|improved|optimized|released|delivery complete|validated|green)\b/i.test(
    text,
  );

  if (hasFailureSignal && hasSuccessSignal) {
    return 'mixed';
  }
  if (hasFailureSignal) {
    return 'needs_rework';
  }
  if (hasSuccessSignal) {
    return 'successful';
  }
  return 'in_progress';
}

function outcomeLabel(outcome: TimelineEvolutionEntry['outcome']): string {
  if (outcome === 'successful') {
    return 'Successful';
  }
  if (outcome === 'needs_rework') {
    return 'Needs Rework';
  }
  if (outcome === 'mixed') {
    return 'Mixed';
  }
  return 'In Progress';
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
  const [timelineGrouping, setTimelineGrouping] = useState<TimelineGrouping>('daily');

  const [question, setQuestion] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: 'assistant',
      text: 'Welcome to Team Cortex. Ask about project progress, timeline evolution, delivery risk, or feature outcomes.',
    },
  ]);

  const selectedProject = useMemo(
    () => projects.find((project) => project.id === selectedProjectId) || null,
    [projects, selectedProjectId],
  );

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

        const effectiveProjectId = selectedProjectId || (projectList.length > 0 ? projectList[0].id : null);
        const authHeaders = { Authorization: `Bearer ${token}` };

        let mergedTeamSnapshots: ProjectSnapshot[] = [];

        // Team Cortex should reflect both Saketh + Suhaan streams when available.
        const teamIdFromToken = parseTeamIdFromToken(token);
        if (teamIdFromToken) {
          const membersRes = await fetch(`${apiBase}/api/v1/teams/${teamIdFromToken}/members`, {
            headers: authHeaders,
          });

          if (membersRes.ok) {
            const members = ((await membersRes.json()) as TeamMember[]) || [];
            const preferredMembers = members.filter((member) => {
              const email = String(member.email || '');
              const displayName = String(member.display_name || '');
              return /sak|suh/i.test(email) || /sak|suh/i.test(displayName);
            });

            const targetMembers = preferredMembers.length >= 2 ? preferredMembers : members;

            const projectQuery = effectiveProjectId ? `&projectId=${encodeURIComponent(effectiveProjectId)}` : '';
            const memberSnapshotEntries = await Promise.all(
              targetMembers.map(async (member) => {
                const res = await fetch(
                  `${apiBase}/api/v1/teams/${teamIdFromToken}/members/${member.id}/snapshots?limit=1000${projectQuery}`,
                  { headers: authHeaders },
                );
                if (!res.ok) {
                  return [] as ProjectSnapshot[];
                }
                const rows = (await res.json()) as ProjectSnapshot[];
                return Array.isArray(rows) ? rows : [];
              }),
            );

            mergedTeamSnapshots = memberSnapshotEntries.flat();

            // If project-scoped rows are empty, fallback to latest member snapshots without project filter.
            if (mergedTeamSnapshots.length === 0 && effectiveProjectId) {
              const fallbackEntries = await Promise.all(
                targetMembers.map(async (member) => {
                  const res = await fetch(
                    `${apiBase}/api/v1/teams/${teamIdFromToken}/members/${member.id}/snapshots?limit=1000`,
                    { headers: authHeaders },
                  );
                  if (!res.ok) {
                    return [] as ProjectSnapshot[];
                  }
                  const rows = (await res.json()) as ProjectSnapshot[];
                  return Array.isArray(rows) ? rows : [];
                }),
              );
              mergedTeamSnapshots = fallbackEntries.flat();
            }

            const dedupedById = new Map<string, ProjectSnapshot>();
            for (const row of mergedTeamSnapshots) {
              const key = String(row.id || `${row.user_id}:${row.timestamp}:${row.active_file}`);
              dedupedById.set(key, row);
            }
            mergedTeamSnapshots = Array.from(dedupedById.values()).sort((a, b) => toEpochMs(b.timestamp) - toEpochMs(a.timestamp));
          }
        }

        // Fetch snapshots for selected project
        if (effectiveProjectId && projectList.some((project) => project.id === effectiveProjectId)) {
          try {
            const snapshotsRes = await fetch(
              `${apiBase}/api/v1/snapshots/timeline?projectId=${encodeURIComponent(effectiveProjectId)}&limit=1000`,
              {
                headers: authHeaders,
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
              const timelineRows = timelineData.timeline || [];
              const snapshotsToRender = mergedTeamSnapshots.length > 0 ? mergedTeamSnapshots : timelineRows;
              setProjectSnapshots(snapshotsToRender);
              setProjectSnapshotError('');
            }
          } catch (err) {
            const msg = err instanceof Error ? err.message : 'Snapshot fetch failed';
            setProjectSnapshotError(msg);
            setProjectSnapshots([]);
          }
        } else {
          setProjectSnapshots([]);
          setProjectSnapshotError('');
        }

        if (!cancelled) {
          setLoading(false);
        }
      } catch (err) {
        if (!cancelled && !background) {
          setError(err instanceof Error ? err.message : 'Failed to load Team Cortex data.');
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

  const evolutionTimeline = useMemo<TimelineEvolutionEntry[]>(() => {
    if (!selectedProjectId || projectSnapshots.length === 0) {
      return [];
    }

    const snapshotsDesc = [...projectSnapshots].sort((a, b) => toEpochMs(b.timestamp) - toEpochMs(a.timestamp));
    const grouped = new Map<string, ProjectSnapshot[]>();

    snapshotsDesc.forEach((snapshot) => {
      const groupKey =
        timelineGrouping === 'feature'
          ? `feature:${summarizeFeatureName(snapshot.active_file || 'unknown')}`
          : `day:${new Date(toEpochMs(snapshot.timestamp)).toISOString().slice(0, 10)}`;
      const current = grouped.get(groupKey) || [];
      current.push(snapshot);
      grouped.set(groupKey, current);
    });

    return Array.from(grouped.entries())
      .sort((a, b) => {
        if (timelineGrouping === 'feature') {
          return b[1].length - a[1].length;
        }
        return a[0] < b[0] ? 1 : -1;
      })
      .map(([groupKey, daySnapshots]) => {
        const summarySet = new Set<string>();
        const branchSet = new Set<string>();
        const featureCounts = new Map<string, number>();

        daySnapshots.forEach((snapshot) => {
          const trimmedSummary = (snapshot.summary || '').trim();
          if (trimmedSummary) {
            summarySet.add(trimmedSummary);
          }

          const branch = (snapshot.git_branch || '').trim();
          if (branch) {
            branchSet.add(branch);
          }

          const feature = summarizeFeatureName(snapshot.active_file || 'unknown');
          featureCounts.set(feature, (featureCounts.get(feature) || 0) + 1);
        });

        const topFeatures = Array.from(featureCounts.entries())
          .sort((a, b) => b[1] - a[1])
          .slice(0, 3)
          .map(([feature]) => feature);

        const topBranches = Array.from(branchSet).slice(0, 3);
        const summarySnippets = Array.from(summarySet).slice(0, 3);

        const combinedSummary =
          summarySnippets.length > 0
            ? summarySnippets.join(' | ')
            : 'No compressed summary was captured for this timeline window.';

        const outcome = classifyOutcome(combinedSummary);
        const dayLabel =
          timelineGrouping === 'feature'
            ? `Feature: ${groupKey.replace(/^feature:/, '')}`
            : new Date(`${groupKey.replace(/^day:/, '')}T00:00:00`).toLocaleDateString(undefined, {
                month: 'short',
                day: 'numeric',
                year: 'numeric',
              });

        return {
          id: groupKey,
          dayLabel,
          snapshotCount: daySnapshots.length,
          topFeatures,
          topBranches,
          combinedSummary,
          outcome,
        };
      });
  }, [projectSnapshots, selectedProjectId, timelineGrouping]);

  const combinedEvolutionSummary = useMemo(() => {
    if (!selectedProjectId) {
      return 'Select a project to see timeline-based evolution.';
    }
    if (evolutionTimeline.length === 0) {
      return 'No timeline entries are available for this project yet.';
    }

    const successfulDays = evolutionTimeline.filter((entry) => entry.outcome === 'successful').length;
    const reworkDays = evolutionTimeline.filter((entry) => entry.outcome === 'needs_rework').length;
    const mixedDays = evolutionTimeline.filter((entry) => entry.outcome === 'mixed').length;

    return [
      `Grouping: ${timelineGrouping === 'daily' ? 'Daily windows' : 'Feature windows'}`,
      `Timeline windows: ${evolutionTimeline.length}`,
      `Successful windows: ${successfulDays}`,
      `Needs rework windows: ${reworkDays}`,
      `Mixed windows: ${mixedDays}`,
      `Total project snapshots: ${projectSnapshots.length}`,
    ].join(' | ');
  }, [evolutionTimeline, projectSnapshots.length, selectedProjectId, timelineGrouping]);

  const sendQuestion = async (input: string) => {
    const trimmed = input.trim();
    if (!trimmed || chatPending) {
      return;
    }

    setMessages((prev) => [...prev, { role: 'user', text: trimmed }]);
    setQuestion('');
    setChatPending(true);

    try {
      const projectContext = selectedProject
        ? [
            `Selected project: ${selectedProject.name}`,
            `Project visibility: ${selectedProject.visibility || 'private'}`,
            `Project status: ${selectedProject.is_archived ? 'archived' : 'active'}`,
            `Total snapshots tracked: ${projectSnapshots.length}`,
            `Evolution timeline (most recent first):`,
            ...evolutionTimeline.slice(0, 8).map(
              (entry) =>
                `- ${entry.dayLabel} | ${outcomeLabel(entry.outcome)} | features: ${entry.topFeatures.join(', ') || 'none'} | summary: ${entry.combinedSummary}`,
            ),
            `Latest snapshot lines (last 20):`,
            ...projectSnapshots.slice(0, 20).map((snapshot) => `- ${fmtSnapshotLine(snapshot)}`),
          ].join('\n')
        : 'No project selected.';

      const composedQuestion = [
        'You are assisting Team Cortex on SecondCortex.',
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

  return (
    <div className="sc-dashboard-wrap">
      <div className="sc-dashboard-inner">
        <div className="sc-section-header pm-header">
          <p className="section-label">Team Cortex Control Surface</p>
          <h1 className="section-title pm-title">Team Cortex</h1>
          <p className="section-desc">
            Track project evolution using compressed timeline summaries, then query the assistant for deeper analysis.
          </p>
          <p className="pm-mode-chip">{isGuestPm ? 'Team Cortex Guest Session' : 'Team Cortex Session'}</p>
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
          <div className="pm-grid pm-grid-layout">
            <div className="pm-left-layout">
              <section className="pm-panel">
                <p className="pm-panel-kicker">Portfolio</p>
                <h2 className="pm-panel-title">Projects</h2>
                <div className="pm-member-list">
                  {projects.length === 0 ? (
                    <p style={{ padding: '12px', color: '#999' }}>No projects available.</p>
                  ) : (
                    projects.map((project) => (
                      <div key={project.id} className={`pm-member-btn ${project.id === selectedProjectId ? 'active' : ''}`}>
                        <button className="pm-member-main" type="button" onClick={() => setSelectedProjectId(project.id)}>
                          <span className="pm-member-name">{project.name}</span>
                          <span className="pm-member-role">{project.visibility || 'private'}</span>
                        </button>
                      </div>
                    ))
                  )}
                </div>
              </section>

              <section className="pm-panel">
                <p className="pm-panel-kicker">Timeline Evolution</p>
                <h2 className="pm-panel-title">Compressed Project Evolution</h2>
                <div className="pm-timeline-controls">
                  <button
                    type="button"
                    className={`pm-timeline-toggle ${timelineGrouping === 'daily' ? 'active' : ''}`}
                    onClick={() => setTimelineGrouping('daily')}
                  >
                    Daily
                  </button>
                  <button
                    type="button"
                    className={`pm-timeline-toggle ${timelineGrouping === 'feature' ? 'active' : ''}`}
                    onClick={() => setTimelineGrouping('feature')}
                  >
                    Feature
                  </button>
                </div>
                <div className="pm-summary-card">
                  <div className="pm-summary-head">
                    <span>{selectedProject ? selectedProject.name : 'No project selected'}</span>
                    <span className="pm-summary-tag">SUMMARY</span>
                  </div>
                  <p>{combinedEvolutionSummary}</p>
                </div>

                <div className="pm-history" style={{ marginTop: '12px', maxHeight: '540px' }}>
                  {projectSnapshotError && <p className="sc-auth-error">Snapshot sync error: {projectSnapshotError}</p>}
                  {evolutionTimeline.length === 0 && !projectSnapshotError && (
                    <p className="pm-history-summary">No compressed timeline entries are available for this project yet.</p>
                  )}
                  {evolutionTimeline.map((entry) => (
                    <article key={entry.id} className="pm-history-item">
                      <div className="pm-history-head">
                        <span>{entry.dayLabel}</span>
                        <span>{entry.snapshotCount} snapshots</span>
                      </div>
                      <div className="pm-history-file">Features: {entry.topFeatures.join(', ') || 'Not identified'}</div>
                      <p className="pm-history-summary">{entry.combinedSummary}</p>
                      <div className="pm-compression">
                        <p>Branches: {entry.topBranches.join(', ') || 'main'}</p>
                        <p>
                          Outcome:{' '}
                          <span className={`pm-outcome-chip ${entry.outcome}`}>{outcomeLabel(entry.outcome)}</span>
                        </p>
                      </div>
                    </article>
                  ))}
                </div>
              </section>
            </div>

            <section className="pm-panel" style={{ display: 'flex', flexDirection: 'column' }}>
              <p className="pm-panel-kicker">Assistant</p>
              <h2 className="pm-panel-title">Team Cortex Chat</h2>
              <p className="pm-chat-sub">Query any project detail, timeline shift, risk signal, or delivery status.</p>

              <div className="pm-chat-quick">
                <button type="button" onClick={() => sendQuestion('Which recent timeline windows indicate risk and why?')}>
                  Risk windows
                </button>
                <button type="button" onClick={() => sendQuestion('Summarize whether the latest feature work was successful or not.')}>
                  Outcome trend
                </button>
                <button type="button" onClick={() => sendQuestion('What should the team do next based on timeline evolution?')}>
                  Next actions
                </button>
              </div>

              <div className="pm-chat-log" style={{ flex: 1, minHeight: '340px' }}>
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
