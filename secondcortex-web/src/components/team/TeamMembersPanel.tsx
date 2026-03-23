'use client';

import React, { useEffect, useState } from 'react';

interface TeamMember {
  id: string;
  email: string;
  display_name: string;
  created_at: string;
}

interface TeamMembersPanelProps {
  teamId: string;
  teamInfo: any;
  token: string;
  backendUrl: string;
  selectedMemberId: string | null;
  onSelectMember: (memberId: string) => void;
}

export default function TeamMembersPanel({
  teamId,
  teamInfo,
  token,
  backendUrl,
  selectedMemberId,
  onSelectMember,
}: TeamMembersPanelProps) {
  const [members, setMembers] = useState<TeamMember[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchMembers = async () => {
      try {
        const response = await fetch(`${backendUrl}/api/v1/teams/${teamId}/members`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!response.ok) {
          throw new Error(`Failed to fetch members (${response.status})`);
        }
        const data = await response.json();
        setMembers(data);
      } catch (error) {
        console.error('Failed to fetch team members:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchMembers();
  }, [teamId, token, backendUrl]);

  useEffect(() => {
    if (members.length === 0) {
      return;
    }

    if (!selectedMemberId || !members.some((member) => member.id === selectedMemberId)) {
      onSelectMember(members[0].id);
    }
  }, [members, selectedMemberId, onSelectMember]);

  if (loading) {
    return <div className="p-4 text-sm">Loading members...</div>;
  }

  return (
    <div className="p-4">
      <h2 className="text-lg font-bold mb-4">Team Members</h2>
      <div className="space-y-2">
        {members.map((member) => (
          <div
            key={member.id}
            onClick={() => onSelectMember(member.id)}
            className={`text-sm p-2 rounded cursor-pointer truncate border ${
              selectedMemberId === member.id
                ? 'bg-emerald-700/30 border-emerald-500'
                : 'bg-slate-800 border-slate-700 hover:bg-slate-700'
            }`}
            title={member.display_name}
          >
            {member.display_name}
          </div>
        ))}
      </div>
      <div className="mt-4 text-xs text-slate-400">
        {members.length} members
      </div>
    </div>
  );
}
