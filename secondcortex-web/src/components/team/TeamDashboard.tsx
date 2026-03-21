'use client';

import React, { useEffect, useState } from 'react';
import TeamMembersPanel from './TeamMembersPanel';
import TeamGraphSnapshot from './TeamGraphSnapshot';
import TeamChatPanel from './TeamChatPanel';

interface TeamDashboardProps {
  teamId: string;
}

export default function TeamDashboard({ teamId }: TeamDashboardProps) {
  const [teamInfo, setTeamInfo] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [token, setToken] = useState<string | null>(null);

  useEffect(() => {
    // Get token from localStorage
    const storedToken = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
    setToken(storedToken);
  }, []);

  useEffect(() => {
    if (!token) return;

    const fetchTeamInfo = async () => {
      try {
        const response = await fetch(`/api/v1/teams/${teamId}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        const data = await response.json();
        setTeamInfo(data);
      } catch (error) {
        console.error('Failed to fetch team info:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchTeamInfo();
  }, [teamId, token]);

  if (loading) {
    return <div className="p-4">Loading team dashboard...</div>;
  }

  return (
    <div className="flex h-screen bg-slate-900 text-white">
      {/* Left Panel: Team Members */}
      <aside
        data-section="members"
        className="w-40 border-r border-slate-700 overflow-y-auto"
      >
        <TeamMembersPanel teamId={teamId} teamInfo={teamInfo} token={token} />
      </aside>

      {/* Center: Team Graph Snapshot */}
      <main
        data-section="graph"
        className="flex-1 border-r border-slate-700 p-4 overflow-y-auto"
      >
        <TeamGraphSnapshot teamId={teamId} token={token} />
      </main>

      {/* Right Panel: Chat + Summaries */}
      <aside
        data-section="chat"
        className="w-80 border-l border-slate-700 flex flex-col overflow-hidden"
      >
        <TeamChatPanel teamId={teamId} token={token} />
      </aside>
    </div>
  );
}
