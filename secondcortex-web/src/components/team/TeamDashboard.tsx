'use client';

import React, { useEffect, useState } from 'react';
import TeamMembersPanel from './TeamMembersPanel';
import TeamGraphSnapshot from './TeamGraphSnapshot';
import TeamChatPanel from './TeamChatPanel';

interface TeamDashboardProps {
  teamId: string;
  token: string;
  backendUrl: string;
}

interface TeamInfo {
  id: string;
  name: string;
  team_lead_id: string;
  member_count: number;
}

export default function TeamDashboard({ teamId, token, backendUrl }: TeamDashboardProps) {
  const [teamInfo, setTeamInfo] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedMemberId, setSelectedMemberId] = useState<string | null>(null);

  useEffect(() => {
    if (!token || !teamId) {
      return;
    }

    const fetchTeamInfo = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch(`${backendUrl}/api/v1/teams/${teamId}`, {
          headers: { Authorization: `Bearer ${token}` },
        });

        if (!response.ok) {
          throw new Error(`Failed to fetch team info (${response.status})`);
        }

        const data = (await response.json()) as TeamInfo;
        setTeamInfo(data);
      } catch (error) {
        setError(error instanceof Error ? error.message : 'Failed to fetch team info');
      } finally {
        setLoading(false);
      }
    };

    fetchTeamInfo();
  }, [teamId, token, backendUrl]);

  if (loading) {
    return <div className="p-4 text-sm text-slate-300">Loading team dashboard...</div>;
  }

  if (error) {
    return <div className="p-4 text-sm text-red-300">{error}</div>;
  }

  return (
    <div className="flex h-full min-h-[520px] bg-slate-900 text-white rounded border border-slate-700 overflow-hidden">
      <aside
        data-section="members"
        className="w-56 border-r border-slate-700 overflow-y-auto"
      >
        <TeamMembersPanel
          teamId={teamId}
          teamInfo={teamInfo}
          token={token}
          backendUrl={backendUrl}
          selectedMemberId={selectedMemberId}
          onSelectMember={setSelectedMemberId}
        />
      </aside>

      <main
        data-section="graph"
        className="flex-1 border-r border-slate-700 p-4 overflow-y-auto"
      >
        <div className="mb-4">
          <h2 className="text-lg font-semibold">{teamInfo?.name || 'Team Space'}</h2>
          <p className="text-xs text-slate-300">
            Team snapshots, contexts, summaries, and chat collaboration.
          </p>
        </div>
        <TeamGraphSnapshot
          teamId={teamId}
          token={token}
          backendUrl={backendUrl}
          selectedMemberId={selectedMemberId}
        />
      </main>

      <aside
        data-section="chat"
        className="w-96 border-l border-slate-700 flex flex-col overflow-hidden"
      >
        <TeamChatPanel
          teamId={teamId}
          token={token}
          backendUrl={backendUrl}
          selectedMemberId={selectedMemberId}
        />
      </aside>
    </div>
  );
}
