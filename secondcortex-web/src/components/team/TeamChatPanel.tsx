'use client';

import React, { useState } from 'react';
import SummaryWidget from './SummaryWidget';

interface TeamChatPanelProps {
  teamId: string;
  token: string | null;
}

export default function TeamChatPanel({ teamId, token }: TeamChatPanelProps) {
  const [activeTab, setActiveTab] = useState<'daily' | 'weekly'>('daily');
  const [message, setMessage] = useState('');

  const handleSendMessage = () => {
    // TODO: Implement chat functionality
    setMessage('');
  };

  return (
    <div className="flex flex-col h-full">
      {/* Chat Section */}
      <div className="border-b border-slate-700 p-4">
        <h3 className="text-sm font-bold mb-3">Team Chat</h3>
        <div className="bg-slate-800 rounded p-3 h-32 mb-3 overflow-y-auto text-xs">
          <div className="text-slate-400">Chat messages appear here</div>
        </div>
        <div className="flex gap-2">
          <input
            type="text"
            placeholder="Type message..."
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyPress={(e) => {
              if (e.key === 'Enter') handleSendMessage();
            }}
            className="flex-1 text-xs px-2 py-1 bg-slate-800 border border-slate-700 rounded"
          />
          <button
            onClick={handleSendMessage}
            className="px-3 py-1 bg-green-700 text-xs rounded hover:bg-green-600"
          >
            Send
          </button>
        </div>
      </div>

      {/* Summary Tabs */}
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

        {/* Summary Content */}
        <div className="flex-1 overflow-y-auto p-4">
          {token && (
            <SummaryWidget
              teamId={teamId}
              period={activeTab}
              context="team"
              token={token}
            />
          )}
        </div>
      </div>
    </div>
  );
}
