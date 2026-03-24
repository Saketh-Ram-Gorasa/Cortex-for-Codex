'use client';

import React, { useEffect, useMemo, useState } from 'react';

interface TeamDashboardProps {
  teamId: string;
  token: string;
  backendUrl: string;
  teams?: TeamInfo[];
  onTeamChange?: (teamId: string) => void;
  onClose?: () => void;
}

interface TeamInfo {
  id: string;
  name: string;
  team_lead_id: string;
  member_count: number;
}

interface TeamMember {
  id: string;
  email: string;
  display_name: string;
  created_at: string;
}

interface MemberSnapshot {
  id: string;
  user_id: string;
  team_id: string | null;
  workspace: string;
  active_file: string;
  git_branch: string | null;
  terminal_commands: string[];
  summary: string;
  enriched_context: Record<string, unknown>;
  timestamp: number;
  synced: number;
}

interface MemberSummary {
  user_id: string;
  display_name: string;
  email: string;
  snapshots_count: number;
  commits_count: number;
  languages_used: string[];
  files_modified: number;
  status: string;
}

interface TeamSummaryResponse {
  team_id: string;
  period: 'daily' | 'weekly';
  members: MemberSummary[];
  total_snapshots: number;
  total_commits: number;
  active_members: number;
  daily_breakdown?: Record<string, number>;
  generated_at: string;
}

interface ChatMessage {
  role: 'assistant' | 'user';
  text: string;
}

type SummaryKind = 'daily' | 'weekly' | 'feature';

function toDisplayName(member: TeamMember): string {
  return (member.display_name || member.email.split('@')[0] || member.id).trim();
}

function toEpochMs(ts: number): number {
  if (ts > 10_000_000_000) {
    return ts;
  }
  return ts * 1000;
}

function fmtSnapshotLine(snapshot: MemberSnapshot): string {
  const when = new Date(toEpochMs(snapshot.timestamp)).toLocaleString();
  return `${when} | ${snapshot.git_branch || 'no-branch'} | ${snapshot.active_file || 'unknown-file'} | ${
    snapshot.summary || 'No summary'
  }`;
}

function topFiles(snapshots: MemberSnapshot[], limit: number): string[] {
  const counts: Record<string, number> = {};
  for (const snapshot of snapshots) {
    const key = snapshot.active_file || 'unknown-file';
    counts[key] = (counts[key] || 0) + 1;
  }
  return Object.entries(counts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit)
    .map(([file, count]) => `${file} (${count})`);
}

export default function TeamDashboard({
  teamId,
  token,
  backendUrl,
  teams = [],
  onTeamChange,
  onClose,
}: TeamDashboardProps) {
  const [teamInfo, setTeamInfo] = useState<TeamInfo | null>(null);
  const [members, setMembers] = useState<TeamMember[]>([]);
  const [selectedMemberId, setSelectedMemberId] = useState<string>('');
  const [summarySelection, setSummarySelection] = useState<{ memberId: string; kind: SummaryKind } | null>(null);
  const [snapshotsByMember, setSnapshotsByMember] = useState<Record<string, MemberSnapshot[]>>({});
  const [dailySummary, setDailySummary] = useState<TeamSummaryResponse | null>(null);
  const [weeklySummary, setWeeklySummary] = useState<TeamSummaryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [chatPending, setChatPending] = useState(false);
  const [question, setQuestion] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: 'assistant',
      text: 'Welcome Team Space. Chat is connected to the integrated backend LLM. Use member summary buttons for daily, weekly, or feature compression views.',
    },
  ]);

  useEffect(() => {
    let cancelled = false;

    const loadData = async () => {
      setLoading(true);
      setError(null);
      try {
        const infoRes = await fetch(`${backendUrl}/api/v1/teams/${teamId}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!infoRes.ok) {
          throw new Error(`Failed to fetch team info (${infoRes.status})`);
        }
        const infoData = (await infoRes.json()) as TeamInfo;
        if (!cancelled) {
          setTeamInfo(infoData);
        }

        const membersRes = await fetch(`${backendUrl}/api/v1/teams/${teamId}/members`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!membersRes.ok) {
          throw new Error('Unable to fetch team members.');
        }
        const memberList = (await membersRes.json()) as TeamMember[];
        const orderedMembers = [...memberList].sort((a, b) => toDisplayName(a).localeCompare(toDisplayName(b)));

        if (!cancelled) {
          setMembers(orderedMembers);
          if (orderedMembers.length > 0) {
            const initial = orderedMembers[0].id;
            setSelectedMemberId((prev) => prev || initial);
            setSummarySelection((prev) => prev || { memberId: initial, kind: 'daily' });
          }
        }

        const snapshotEntries = await Promise.all(
          orderedMembers.map(async (member) => {
            const res = await fetch(
              `${backendUrl}/api/v1/teams/${teamId}/members/${member.id}/snapshots?limit=1000`,
              {
                headers: { Authorization: `Bearer ${token}` },
              },
            );
            if (!res.ok) {
              return [member.id, []] as const;
            }
            const snapshots = (await res.json()) as MemberSnapshot[];
            return [member.id, snapshots] as const;
          }),
        );
        if (!cancelled) {
          setSnapshotsByMember(Object.fromEntries(snapshotEntries));
        }

        const [dailyRes, weeklyRes] = await Promise.all([
          fetch(`${backendUrl}/api/v1/summaries/team/${teamId}/daily`, {
            headers: { Authorization: `Bearer ${token}` },
          }),
          fetch(`${backendUrl}/api/v1/summaries/team/${teamId}/weekly`, {
            headers: { Authorization: `Bearer ${token}` },
          }),
        ]);

        if (!cancelled) {
          if (dailyRes.ok) {
            setDailySummary((await dailyRes.json()) as TeamSummaryResponse);
          }
          if (weeklyRes.ok) {
            setWeeklySummary((await weeklyRes.json()) as TeamSummaryResponse);
          }
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load team dashboard data.');
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    if (token && teamId) {
      void loadData();
    }

    return () => {
      cancelled = true;
    };
  }, [teamId, token, backendUrl]);

  const selectedMember = useMemo(
    () => members.find((member) => member.id === selectedMemberId),
    [members, selectedMemberId],
  );

  const selectedSnapshots = selectedMemberId ? snapshotsByMember[selectedMemberId] || [] : [];
  const totalSnapshots = Object.values(snapshotsByMember).reduce((sum, snapshots) => sum + snapshots.length, 0);

  const getCompressedSummaryText = (memberId: string, kind: SummaryKind): string => {
    const member = members.find((m) => m.id === memberId);
    if (!member) {
      return 'Member not found.';
    }

    const snapshots = snapshotsByMember[memberId] || [];
    const name = toDisplayName(member);

    if (kind === 'daily') {
      const now = Date.now();
      const dayCutoff = now - 24 * 60 * 60 * 1000;
      const lastDay = snapshots.filter((snapshot) => toEpochMs(snapshot.timestamp) >= dayCutoff);
      const dailyRow = dailySummary?.members?.find((m) => m.user_id === memberId);
      const recentLines = lastDay.slice(0, 2).map((snapshot) => fmtSnapshotLine(snapshot));
      return [
        `${name} daily summary:`,
        dailyRow
          ? `Snapshots: ${dailyRow.snapshots_count}, Files modified: ${dailyRow.files_modified}, Status: ${dailyRow.status}`
          : `Snapshots (last 24h): ${lastDay.length}`,
        recentLines.length > 0 ? `Recent: ${recentLines.join(' | ')}` : 'No recent IDE entries in last 24h.',
      ].join('\n');
    }

    if (kind === 'weekly') {
      const now = Date.now();
      const weekCutoff = now - 7 * 24 * 60 * 60 * 1000;
      const lastWeek = snapshots.filter((snapshot) => toEpochMs(snapshot.timestamp) >= weekCutoff);
      const weeklyRow = weeklySummary?.members?.find((m) => m.user_id === memberId);
      return [
        `${name} weekly summary:`,
        weeklyRow
          ? `Snapshots: ${weeklyRow.snapshots_count}, Files modified: ${weeklyRow.files_modified}, Status: ${weeklyRow.status}`
          : `Snapshots (last 7d): ${lastWeek.length}`,
        `Top files: ${topFiles(lastWeek, 3).join(', ') || 'none'}`,
      ].join('\n');
    }

    const featureFiles = topFiles(snapshots, 4);
    const latest = snapshots.slice(0, 3).map((snapshot) => fmtSnapshotLine(snapshot));
    return [
      `${name} feature summary:`,
      `Most active feature files: ${featureFiles.join(', ') || 'none'}`,
      latest.length > 0 ? `Latest feature work: ${latest.join(' | ')}` : 'No feature snapshots available.',
    ].join('\n');
  };

  const selectedSummaryText = useMemo(() => {
    if (!summarySelection) {
      return 'Select a summary button beside a team member to view compressed output.';
    }
    return getCompressedSummaryText(summarySelection.memberId, summarySelection.kind);
  }, [summarySelection, members, snapshotsByMember, dailySummary, weeklySummary]);

  const sendQuestion = async (input: string) => {
    const trimmed = input.trim();
    if (!trimmed || chatPending) {
      return;
    }

    setMessages((prev) => [...prev, { role: 'user', text: trimmed }]);
    setQuestion('');
    setChatPending(true);

    try {
      const memberContext = selectedMember
        ? [
            `Selected member: ${toDisplayName(selectedMember)} (${selectedMember.email})`,
            `Latest IDE history lines:`,
            ...(selectedSnapshots.slice(0, 20).map((snapshot) => `- ${fmtSnapshotLine(snapshot)}`) || []),
            `Compressed daily: ${getCompressedSummaryText(selectedMember.id, 'daily')}`,
            `Compressed weekly: ${getCompressedSummaryText(selectedMember.id, 'weekly')}`,
            `Compressed feature: ${getCompressedSummaryText(selectedMember.id, 'feature')}`,
          ].join('\n')
        : 'No member selected.';

      const composedQuestion = [
        'You are assisting a Project Manager on SecondCortex.',
        'Answer with practical project-status details and avoid hallucinations.',
        memberContext,
        `PM question: ${trimmed}`,
      ].join('\n\n');

      const res = await fetch(`${backendUrl}/api/v1/pm/query`, {
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

  if (loading) {
    return (
      <div className="sc-dashboard-wrap">
        <div className="sc-dashboard-inner">
          <div className="sc-dashboard-panel">
            <div className="sc-dashboard-panel-inner" style={{ display: 'block' }}>
              <div className="sc-shimmer-stack" aria-live="polite">
                <div className="sc-shimmer-line xl w-40" />
                <div className="sc-shimmer-line lg w-60" />
                <div className="sc-shimmer-grid">
                  <div className="sc-shimmer-card"><div className="sc-shimmer-line w-80" /></div>
                  <div className="sc-shimmer-card"><div className="sc-shimmer-line w-80" /></div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="sc-dashboard-wrap">
        <div className="sc-dashboard-inner">
          <div className="sc-dashboard-panel">
            <div className="sc-dashboard-panel-inner" style={{ display: 'block' }}>
              <p className="sc-auth-error">{error}</p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="sc-dashboard-wrap">
      <div className="sc-dashboard-inner">
        <div className="sc-section-header pm-header">
          <p className="section-label">Team Control Surface</p>
          <h1 className="section-title pm-title">Team Dashboard</h1>
          <p className="section-desc">
            Chat uses the integrated backend LLM. Compressed summaries are shown in member mini-boxes: Daily, Weekly,
            Feature.
          </p>
          <p className="pm-mode-chip">Team Space Session</p>

          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
            {onClose && (
              <button type="button" className="btn-secondary" onClick={onClose}>
                Back to Developer Dashboard
              </button>
            )}
            {teams.map((team) => (
              <button
                key={team.id}
                type="button"
                className="btn-secondary"
                onClick={() => onTeamChange?.(team.id)}
                style={{
                  borderColor: team.id === teamId ? 'var(--text)' : undefined,
                  color: team.id === teamId ? 'var(--text)' : undefined,
                }}
              >
                {team.name}
              </button>
            ))}
          </div>
        </div>

        <div className="sc-stats-grid">
          <StatCard title="Team Members" value={String(members.length)} subtitle="Visible in team scope" />
          <StatCard title="Snapshots Indexed" value={String(totalSnapshots)} subtitle="Full IDE history available" />
          <StatCard
            title="Compression Feed"
            value={dailySummary || weeklySummary ? 'Connected' : 'Pending'}
            subtitle={teamInfo ? `Team: ${teamInfo.name}` : 'No team'}
          />
        </div>

        <div className="pm-grid">
          <section className="pm-panel">
            <p className="pm-panel-kicker">Team Directory</p>
            <h2 className="pm-panel-title">Team Members</h2>
            <div className="pm-member-list">
              {members.map((member) => (
                <div key={member.id} className={`pm-member-btn ${member.id === selectedMemberId ? 'active' : ''}`}>
                  <button className="pm-member-main" type="button" onClick={() => setSelectedMemberId(member.id)}>
                    <span className="pm-member-name">{toDisplayName(member)}</span>
                    <span className="pm-member-role">{member.email}</span>
                  </button>

                  <div className="pm-member-actions">
                    <button
                      type="button"
                      className="pm-mini-btn"
                      onClick={() => {
                        setSelectedMemberId(member.id);
                        setSummarySelection({ memberId: member.id, kind: 'daily' });
                      }}
                    >
                      <span className="pm-mini-btn-key">D</span>
                      <span className="pm-mini-btn-label">Daily</span>
                    </button>
                    <button
                      type="button"
                      className="pm-mini-btn"
                      onClick={() => {
                        setSelectedMemberId(member.id);
                        setSummarySelection({ memberId: member.id, kind: 'weekly' });
                      }}
                    >
                      <span className="pm-mini-btn-key">W</span>
                      <span className="pm-mini-btn-label">Weekly</span>
                    </button>
                    <button
                      type="button"
                      className="pm-mini-btn"
                      onClick={() => {
                        setSelectedMemberId(member.id);
                        setSummarySelection({ memberId: member.id, kind: 'feature' });
                      }}
                    >
                      <span className="pm-mini-btn-key">F</span>
                      <span className="pm-mini-btn-label">Feature</span>
                    </button>
                  </div>
                </div>
              ))}
            </div>

            <div className="pm-summary-card">
              <div className="pm-summary-head">
                <span>Compressed Summary</span>
                <span className="pm-summary-tag">{summarySelection ? summarySelection.kind.toUpperCase() : 'NONE'}</span>
              </div>
              <p>{selectedSummaryText}</p>
            </div>
          </section>

          <section className="pm-panel">
            <p className="pm-panel-kicker">Timeline</p>
            <h2 className="pm-panel-title">
              {selectedMember ? `${toDisplayName(selectedMember)} Snapshot History` : 'Snapshot History'}
            </h2>
            <div className="pm-history">
              {selectedSnapshots.length === 0 && <p className="pm-history-summary">No synced snapshots found.</p>}
              {selectedSnapshots.map((snapshot) => (
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
          </section>

          <section className="pm-panel">
            <p className="pm-panel-kicker">Assistant</p>
            <h2 className="pm-panel-title">Team Chatbot</h2>
            <p className="pm-chat-sub">Powered by the integrated LLM endpoint (`/api/v1/pm/query`).</p>

            <div className="pm-chat-quick">
              <button type="button" onClick={() => void sendQuestion('What is this member currently progressing on?')}>
                Current progress
              </button>
              <button type="button" onClick={() => void sendQuestion('Any blockers or execution risks from current history?')}>
                Risks
              </button>
              <button type="button" onClick={() => void sendQuestion('Summarize the last sprint progress for team review')}>
                Sprint summary
              </button>
            </div>

            <div className="pm-chat-log">
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
                placeholder="Ask team progress question"
              />
              <button className="query-btn" type="button" disabled={chatPending} onClick={() => void sendQuestion(question)}>
                  {chatPending ? (
                    <>
                      <span className="loading-ring" aria-hidden="true" />
                      Asking…
                    </>
                  ) : (
                    'Ask'
                  )}
              </button>
            </div>
          </section>
        </div>
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
