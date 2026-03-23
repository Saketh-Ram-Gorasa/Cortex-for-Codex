'use client';

import React, { useMemo, useState } from 'react';
import SummaryWidget from './SummaryWidget';

interface TeamChatPanelProps {
  teamId: string;
  token: string;
  backendUrl: string;
  selectedMemberId: string | null;
}

interface ChatMessage {
  role: 'assistant' | 'user';
  text: string;
}

interface MemberSnapshot {
  id: string;
  summary: string;
  active_file: string;
  git_branch: string | null;
  timestamp: number;
}

export default function TeamChatPanel({ teamId, token, backendUrl, selectedMemberId }: TeamChatPanelProps) {
  const [activeTab, setActiveTab] = useState<'daily' | 'weekly'>('daily');
  const [message, setMessage] = useState('');
  const [chatPending, setChatPending] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: 'assistant',
      text: 'Ask about team progress, blockers, or what a selected teammate worked on recently.',
    },
  ]);

  const canSend = useMemo(() => Boolean(message.trim()) && !chatPending, [message, chatPending]);

  const handleSendMessage = async () => {
    const trimmed = message.trim();
    if (!trimmed || chatPending) {
      return;
    }

    setMessages((prev) => [...prev, { role: 'user', text: trimmed }]);
    setMessage('');
    setChatPending(true);

    try {
      let selectedSnapshots: MemberSnapshot[] = [];
      if (selectedMemberId) {
        const snapRes = await fetch(
          `${backendUrl}/api/v1/teams/${teamId}/members/${selectedMemberId}/snapshots?limit=10`,
          {
            headers: { Authorization: `Bearer ${token}` },
          },
        );
        if (snapRes.ok) {
          selectedSnapshots = (await snapRes.json()) as MemberSnapshot[];
        }
      }

      const contextLines = selectedSnapshots.slice(0, 5).map((snapshot) => {
        const iso = snapshot.timestamp > 10_000_000_000
          ? new Date(snapshot.timestamp).toISOString()
          : new Date(snapshot.timestamp * 1000).toISOString();
        return `- ${iso} | ${snapshot.git_branch || 'no-branch'} | ${snapshot.active_file || 'unknown-file'} | ${snapshot.summary || 'No summary'}`;
      });

      const composedQuestion = [
        'You are assisting a software development team inside SecondCortex Team Space.',
        'Use only provided context and avoid inventing facts.',
        `Team ID: ${teamId}`,
        `Selected member: ${selectedMemberId || 'none'}`,
        contextLines.length ? `Selected member latest snapshots:\n${contextLines.join('\n')}` : 'No selected member snapshots were available.',
        `Question: ${trimmed}`,
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
        throw new Error(err.detail || 'Team chatbot request failed.');
      }

      const data = await res.json();
      const answer =
        typeof data.summary === 'string' && data.summary.trim()
          ? data.summary
          : 'No answer was returned. Please rephrase your question.';

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
    <div className="flex flex-col h-full">
      <div className="border-b border-slate-700 p-4">
        <h3 className="text-sm font-bold mb-3">Team Chat</h3>
        <div className="bg-slate-800 rounded p-3 h-40 mb-3 overflow-y-auto text-xs space-y-2">
          {messages.map((chat, index) => (
            <div
              key={`${chat.role}-${index}`}
              className={chat.role === 'user' ? 'text-blue-200' : 'text-slate-100'}
            >
              <span className="font-semibold mr-1">{chat.role === 'user' ? 'You:' : 'Assistant:'}</span>
              <span>{chat.text}</span>
            </div>
          ))}
          {chatPending && <div className="text-slate-400">Thinking...</div>}
        </div>
        <div className="flex gap-2">
          <input
            type="text"
            placeholder="Ask about team progress..."
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyPress={(e) => {
              if (e.key === 'Enter') handleSendMessage();
            }}
            className="flex-1 text-xs px-2 py-1 bg-slate-800 border border-slate-700 rounded"
          />
          <button
            onClick={handleSendMessage}
            disabled={!canSend}
            className="px-3 py-1 bg-green-700 text-xs rounded hover:bg-green-600"
          >
            {chatPending ? '...' : 'Send'}
          </button>
        </div>
      </div>

      <div className="flex-1 flex flex-col overflow-hidden">
        <div className="flex border-b border-slate-700 px-4 pt-4">
          <button
            onClick={() => setActiveTab('daily')}
            className={`px-3 py-2 text-xs font-semibold ${
              activeTab === 'daily'
                ? 'border-b-2 border-green-500 text-green-400'
                : 'text-slate-400'
            }`}
          >
            Daily
          </button>
          <button
            onClick={() => setActiveTab('weekly')}
            className={`px-3 py-2 text-xs font-semibold ${
              activeTab === 'weekly'
                ? 'border-b-2 border-green-500 text-green-400'
                : 'text-slate-400'
            }`}
          >
            Weekly
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4">
          <SummaryWidget
            teamId={teamId}
            period={activeTab}
            context="team"
            token={token}
            backendUrl={backendUrl}
          />
        </div>
      </div>
    </div>
  );
}
