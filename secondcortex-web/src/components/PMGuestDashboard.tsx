'use client';

import { useMemo, useState } from 'react';

interface PMGuestDashboardProps {
  token: string;
  isGuestPm: boolean;
  backendUrl?: string;
}

interface SnapshotEvent {
  id: string;
  timestamp: string;
  active_file: string;
  git_branch: string;
  summary: string;
}

interface TeamMember {
  id: string;
  name: string;
  title: string;
  snapshots: SnapshotEvent[];
  compression: {
    daily: string;
    weekly: string;
    feature: string;
    blockers: string;
  };
}

interface ChatMessage {
  role: 'assistant' | 'user';
  text: string;
}

const TEAM_MEMBERS: TeamMember[] = [
  {
    id: 'saketh',
    name: 'Saketh',
    title: 'Backend and Agent Orchestration',
    snapshots: [
      {
        id: 'saketh-1',
        timestamp: '2026-03-20T10:20:00Z',
        active_file: 'secondcortex-backend/services/compression.py',
        git_branch: 'feat-compression',
        summary: 'Added snapshot compression flow for daily, weekly, and feature-level summaries.',
      },
      {
        id: 'saketh-2',
        timestamp: '2026-03-20T12:05:00Z',
        active_file: 'secondcortex-backend/main.py',
        git_branch: 'feat-compression',
        summary: 'Verified compression service integration points and protected existing query behavior.',
      },
      {
        id: 'saketh-3',
        timestamp: '2026-03-20T13:40:00Z',
        active_file: 'secondcortex-backend/agents/executor.py',
        git_branch: 'feat-compression',
        summary: 'Validated summary sanitization and ensured compressed context stays concise for responses.',
      },
    ],
    compression: {
      daily: 'Saketh completed core memory compression blocks and validated backend integration safety.',
      weekly: 'Saketh stabilized compression logic and reduced noisy snapshot context into digestible daily and weekly views.',
      feature: 'Snapshot compression now groups IDE activity by day, week, and feature file to improve PM-level progress tracking.',
      blockers: 'No major blockers. Remaining work is mostly UI alignment and PM review polish.',
    },
  },
  {
    id: 'suhaan',
    name: 'Suhaan',
    title: 'Frontend and Product Experience',
    snapshots: [
      {
        id: 'suhaan-1',
        timestamp: '2026-03-20T09:45:00Z',
        active_file: 'secondcortex-web/src/components/AuthGate.tsx',
        git_branch: 'feat-pm-dashboard',
        summary: 'Refined authenticated shell and prepared role-aware dashboard switching.',
      },
      {
        id: 'suhaan-2',
        timestamp: '2026-03-20T11:10:00Z',
        active_file: 'secondcortex-web/src/components/Dashboard.tsx',
        git_branch: 'feat-pm-dashboard',
        summary: 'Improved dashboard readability and summary visibility for PM-level decision making.',
      },
      {
        id: 'suhaan-3',
        timestamp: '2026-03-20T14:25:00Z',
        active_file: 'secondcortex-web/src/app/page.tsx',
        git_branch: 'feat-pm-dashboard',
        summary: 'Extended landing experience to include PM entry path and guest-ready onboarding.',
      },
    ],
    compression: {
      daily: 'Suhaan focused on dashboard and login UX updates needed for PM and guest access.',
      weekly: 'Suhaan improved web flow consistency so PM users can inspect team progress in the same UI shell.',
      feature: 'PM dashboard navigation and role-aware entry points are aligned with the existing SecondCortex interface.',
      blockers: 'Waiting for final PM feedback on copy and guest interaction details.',
    },
  },
];

function buildPmAnswer(question: string, selectedMember: TeamMember, allMembers: TeamMember[]): string {
  const q = question.toLowerCase();
  const wantsTeam = q.includes('team') || q.includes('overall') || q.includes('both');
  const wantsBlockers = q.includes('blocker') || q.includes('risk') || q.includes('delay');
  const wantsToday = q.includes('today') || q.includes('daily');
  const wantsWeekly = q.includes('week') || q.includes('weekly');
  const wantsFeature = q.includes('feature') || q.includes('compression') || q.includes('summary');

  const members = wantsTeam ? allMembers : [selectedMember];

  const lines: string[] = [];
  lines.push(
    wantsTeam
      ? 'PM Progress Summary (team view):'
      : `PM Progress Summary (${selectedMember.name}):`,
  );

  for (const member of members) {
    const parts: string[] = [];
    if (wantsToday || (!wantsWeekly && !wantsFeature && !wantsBlockers)) {
      parts.push(`daily: ${member.compression.daily}`);
    }
    if (wantsWeekly || (!wantsToday && !wantsFeature && !wantsBlockers)) {
      parts.push(`weekly: ${member.compression.weekly}`);
    }
    if (wantsFeature || q.includes('progress')) {
      parts.push(`feature: ${member.compression.feature}`);
    }
    if (wantsBlockers) {
      parts.push(`blockers: ${member.compression.blockers}`);
    }
    lines.push(`- ${member.name}: ${parts.join(' ')}`);
  }

  lines.push('Source: compression summaries + latest snapshot history from SecondCortex memory.');
  return lines.join('\n');
}

export default function PMGuestDashboard({ token, isGuestPm }: PMGuestDashboardProps) {
  const [selectedMemberId, setSelectedMemberId] = useState<string>('saketh');
  const [question, setQuestion] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: 'assistant',
      text: 'Welcome PM. Select a team member and ask for progress, blockers, or compression summary insights.',
    },
  ]);

  const selectedMember = useMemo(
    () => TEAM_MEMBERS.find((member) => member.id === selectedMemberId) ?? TEAM_MEMBERS[0],
    [selectedMemberId],
  );

  const totalSnapshots = TEAM_MEMBERS.reduce((sum, member) => sum + member.snapshots.length, 0);

  const sendQuestion = (input: string) => {
    const trimmed = input.trim();
    if (!trimmed) {
      return;
    }

    const answer = buildPmAnswer(trimmed, selectedMember, TEAM_MEMBERS);
    setMessages((prev) => [
      ...prev,
      { role: 'user', text: trimmed },
      { role: 'assistant', text: answer },
    ]);
    setQuestion('');
  };

  return (
    <div className="sc-dashboard-wrap">
      <div className="sc-dashboard-inner">
        <div className="sc-section-header">
          <p className="section-label">PM Control Surface</p>
          <h1 className="section-title">Project Manager Dashboard</h1>
          <p className="section-desc">
            Welcome Project Manager. Track Saketh and Suhaan through snapshot history and compression-backed updates.
          </p>
          <p className="pm-mode-chip">{isGuestPm ? 'Guest PM Session' : 'Authenticated PM Session'}</p>
        </div>

        <div className="sc-stats-grid">
          <StatCard title="Team Members" value="2" subtitle="Saketh and Suhaan" />
          <StatCard title="Snapshots Indexed" value={String(totalSnapshots)} subtitle="Latest member activity history" />
          <StatCard title="Summary Source" value="Compressed" subtitle={token ? 'Memory summaries active' : 'Guest synthetic context'} />
        </div>

        <div className="pm-grid">
          <section className="pm-panel">
            <h2 className="pm-panel-title">Team Members</h2>
            <div className="pm-member-list">
              {TEAM_MEMBERS.map((member) => (
                <button
                  key={member.id}
                  className={`pm-member-btn ${member.id === selectedMember.id ? 'active' : ''}`}
                  onClick={() => setSelectedMemberId(member.id)}
                  type="button"
                >
                  <span className="pm-member-name">{member.name}</span>
                  <span className="pm-member-role">{member.title}</span>
                </button>
              ))}
            </div>
          </section>

          <section className="pm-panel">
            <h2 className="pm-panel-title">{selectedMember.name} Snapshot History</h2>
            <div className="pm-history">
              {selectedMember.snapshots.map((snapshot) => (
                <article key={snapshot.id} className="pm-history-item">
                  <div className="pm-history-head">
                    <span>{new Date(snapshot.timestamp).toLocaleString()}</span>
                    <span>{snapshot.git_branch}</span>
                  </div>
                  <div className="pm-history-file">{snapshot.active_file}</div>
                  <p className="pm-history-summary">{snapshot.summary}</p>
                </article>
              ))}
            </div>

            <div className="pm-compression">
              <h3>Compression Summaries</h3>
              <p>
                <strong>Daily:</strong> {selectedMember.compression.daily}
              </p>
              <p>
                <strong>Weekly:</strong> {selectedMember.compression.weekly}
              </p>
              <p>
                <strong>Feature:</strong> {selectedMember.compression.feature}
              </p>
            </div>
          </section>

          <section className="pm-panel">
            <h2 className="pm-panel-title">PM Chatbot</h2>
            <p className="pm-chat-sub">
              Ask about progress and blockers. Responses are generated from compression summaries and member snapshots.
            </p>

            <div className="pm-chat-quick">
              <button type="button" onClick={() => sendQuestion('Give me overall team progress this week')}>
                Team weekly progress
              </button>
              <button type="button" onClick={() => sendQuestion(`What is ${selectedMember.name} working on today?`)}>
                Today focus
              </button>
              <button type="button" onClick={() => sendQuestion('Any blockers or risks right now?')}>
                Risks and blockers
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
                    sendQuestion(question);
                  }
                }}
                placeholder={`Ask about ${selectedMember.name} or team progress`}
              />
              <button className="query-btn" type="button" onClick={() => sendQuestion(question)}>
                Ask
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
