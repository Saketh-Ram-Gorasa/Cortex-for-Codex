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
  token: string | null;
}

export default function TeamMembersPanel({ teamId, teamInfo, token }: TeamMembersPanelProps) {
  const [members, setMembers] = useState<TeamMember[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!token) return;

    const fetchMembers = async () => {
      try {
        const response = await fetch(`/api/v1/teams/${teamId}/members`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        const data = await response.json();
        setMembers(data);
      } catch (error) {
        console.error('Failed to fetch team members:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchMembers();
  }, [teamId, token]);

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
            className="text-sm p-2 bg-slate-800 rounded hover:bg-slate-700 cursor-pointer truncate"
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
