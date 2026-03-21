'use client';

import React, { useEffect, useState } from 'react';

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

interface SummaryWidgetProps {
  teamId?: string;
  userId?: string;
  period: 'daily' | 'weekly';
  context: 'team' | 'pm' | 'individual'; // Determines styling and data shown
  token: string;
}

/**
 * Reusable summary widget that can be embedded in:
 * - Team Dashboard
 * - PM Dashboard (read-only access to teams)
 * - Individual Developer Dashboard (new summary section)
 */
export default function SummaryWidget({
  teamId,
  userId,
  period,
  context,
  token,
}: SummaryWidgetProps) {
  const [summary, setSummary] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchSummary = async () => {
      try {
        let endpoint = '';

        if (teamId) {
          endpoint = `/api/v1/summaries/team/${teamId}/${period}`;
        } else if (userId) {
          endpoint = `/api/v1/summaries/user/${userId}/${period}`;
        } else {
          setError('No team or user ID provided');
          setLoading(false);
          return;
        }

        const response = await fetch(endpoint, {
          headers: { Authorization: `Bearer ${token}` },
        });

        if (!response.ok) {
          throw new Error('Failed to fetch summary');
        }

        const data = await response.json();
        setSummary(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error');
      } finally {
        setLoading(false);
      }
    };

    if (token) {
      fetchSummary();
    }
  }, [teamId, userId, period, token]);

  if (loading) {
    return <div className="text-xs text-slate-400">Loading summary...</div>;
  }

  if (error) {
    return <div className="text-xs text-red-400">Error: {error}</div>;
  }

  if (!summary) {
    return <div className="text-xs text-slate-400">No data available</div>;
  }

  const contextStyles = {
    team: 'bg-slate-900 text-white',
    pm: 'bg-blue-900 text-blue-50',
    individual: 'bg-slate-800 text-slate-100',
  };

  return (
    <div className={`space-y-3 text-xs ${contextStyles[context]}`}>
      <div className="space-y-1">
        <div className="font-semibold text-slate-300">
          {period === 'daily' ? 'Today' : 'This Week'}
        </div>
        <div className="text-2xl font-bold">
          {summary.total_snapshots}
        </div>
        <div className="text-slate-400">snapshots</div>
      </div>

      {summary.active_members !== undefined && (
        <div className="space-y-1 border-t border-slate-700 pt-3">
          <div className="text-slate-300">Active Members</div>
          <div className="text-xl font-bold">
            {summary.active_members}
          </div>
        </div>
      )}

      {summary.members && summary.members.length > 0 && (
        <div className="border-t border-slate-700 pt-3">
          <div className="text-slate-300 mb-2">Members</div>
          <div className="space-y-1 max-h-48 overflow-y-auto">
            {summary.members.map((member: MemberSummary) => (
              <div
                key={member.user_id}
                className={`p-2 rounded ${
                  member.status === 'active'
                    ? 'bg-green-900 bg-opacity-20'
                    : 'bg-slate-700 bg-opacity-30'
                }`}
              >
                <div className="font-semibold truncate">
                  {member.display_name}
                </div>
                <div className="text-slate-400">
                  {member.snapshots_count} snapshots
                  {member.commits_count > 0 && `, ${member.commits_count} commits`}
                </div>
                {member.languages_used.length > 0 && (
                  <div className="text-slate-500 mt-1">
                    {member.languages_used.join(', ')}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {summary.daily_breakdown && period === 'weekly' && (
        <div className="border-t border-slate-700 pt-3">
          <div className="text-slate-300 mb-2">Daily Breakdown</div>
          <div className="space-y-1 text-slate-400">
            {Object.entries(summary.daily_breakdown).map(([day, count]: [string, any]) => (
              <div key={day} className="flex justify-between">
                <span>{day}</span>
                <span className="text-green-400 font-semibold">{count}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="text-slate-500 text-xs border-t border-slate-700 pt-2">
        Updated {new Date(summary.generated_at).toLocaleTimeString()}
      </div>
    </div>
  );
}
