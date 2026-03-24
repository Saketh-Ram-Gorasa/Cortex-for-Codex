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

interface SummaryResponse {
  total_snapshots: number;
  active_members?: number;
  members?: MemberSummary[];
  daily_breakdown?: Record<string, number>;
  generated_at: string;
}

interface SummaryWidgetProps {
  teamId?: string;
  userId?: string;
  period: 'daily' | 'weekly';
  context: 'team' | 'pm' | 'individual'; // Determines styling and data shown
  token: string;
  backendUrl?: string;
  selectedProjectId?: string | null;
}

const SUMMARY_CACHE_TTL_MS = 2 * 60 * 1000;

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
  token,
  backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || 'https://sc-backend-suhaan.azurewebsites.net',
  selectedProjectId,
}: SummaryWidgetProps) {
  const [summary, setSummary] = useState<SummaryResponse | null>(null);
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

        const projectKey = selectedProjectId || 'all-projects';
        const cacheKey = `sc:summary:${teamId ? `team:${teamId}` : `user:${userId}`}:${period}:project:${projectKey}`;
        const cached = typeof window !== 'undefined' ? sessionStorage.getItem(cacheKey) : null;

        if (cached) {
          try {
            const parsed = JSON.parse(cached) as { savedAt?: number; data?: SummaryResponse };
            if (parsed.savedAt && parsed.data && Date.now() - parsed.savedAt < SUMMARY_CACHE_TTL_MS) {
              setSummary(parsed.data);
              setLoading(false);
              return;
            }
          } catch {}
        }

        const response = await fetch(`${backendUrl}${endpoint}`, {
          headers: { Authorization: `Bearer ${token}` },
        });

        if (!response.ok) {
          throw new Error('Failed to fetch summary');
        }

        const data = await response.json();
        setSummary(data);

        if (typeof window !== 'undefined') {
          sessionStorage.setItem(cacheKey, JSON.stringify({ savedAt: Date.now(), data }));
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error');
      } finally {
        setLoading(false);
      }
    };

    if (token) {
      fetchSummary();
    }
  }, [teamId, userId, period, token, backendUrl, selectedProjectId]);

  if (loading) {
    return (
      <div className="sc-shimmer-stack" aria-live="polite">
        <div className="sc-shimmer-line lg w-40" />
        <div className="sc-shimmer-line w-80" />
        <div className="sc-shimmer-line w-60" />
        <div className="sc-shimmer-line w-80" />
      </div>
    );
  }

  if (error) {
    return <div className="text-xs text-red-400">Error: {error}</div>;
  }

  if (!summary) {
    return <div className="text-xs text-slate-400">No data available</div>;
  }

  const members = summary.members ?? [];
  const activeMembers = summary.active_members ?? 0;
  const topMember = members.reduce<MemberSummary | null>((best, member) => {
    if (!best || member.snapshots_count > best.snapshots_count) {
      return member;
    }
    return best;
  }, null);

  const weeklyPeakDay = summary.daily_breakdown
    ? Object.entries(summary.daily_breakdown).reduce<[string, number]>((best, entry) => {
        return entry[1] > best[1] ? entry : best;
      }, ['none', 0])
    : null;

  const title = period === 'daily' ? 'Today' : 'This Week';
  const mainExplanation =
    period === 'daily'
      ? summary.total_snapshots > 0
        ? `You captured ${summary.total_snapshots} snapshot${summary.total_snapshots === 1 ? '' : 's'} today.`
        : 'No snapshots have been captured today yet.'
      : `You captured ${summary.total_snapshots} snapshot${summary.total_snapshots === 1 ? '' : 's'} this week.`;

  const memberExplanation =
    members.length > 0
      ? topMember && topMember.snapshots_count > 0
        ? `${topMember.display_name} contributed the most with ${topMember.snapshots_count} snapshot${topMember.snapshots_count === 1 ? '' : 's'}.`
        : 'No member activity was detected in this period.'
      : 'No member-level activity is available for this period.';

  const periodExplanation =
    period === 'daily'
      ? 'This card summarizes your most recent 24 hours of captured work.'
      : 'This card summarizes your last 7 days of captured work.';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
      <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text)' }}>{title}</div>

      <p style={{ fontSize: '13px', color: 'var(--text)', margin: 0 }}>{mainExplanation}</p>
      <p style={{ fontSize: '13px', color: 'var(--muted)', margin: 0 }}>{periodExplanation}</p>

      <p style={{ fontSize: '13px', color: 'var(--text)', margin: 0 }}>
        {activeMembers} active member{activeMembers === 1 ? '' : 's'} in this period.
      </p>

      <p style={{ fontSize: '13px', color: 'var(--text)', margin: 0 }}>{memberExplanation}</p>

      {period === 'weekly' && weeklyPeakDay && (
        <p style={{ fontSize: '13px', color: 'var(--text)', margin: 0 }}>
          Peak day this week: {weeklyPeakDay[0]} with {weeklyPeakDay[1]} snapshot{weeklyPeakDay[1] === 1 ? '' : 's'}.
        </p>
      )}

      <div style={{ fontSize: '11px', color: 'var(--muted)', borderTop: '1px solid var(--border)', paddingTop: '10px', marginTop: '4px' }}>
        Last updated at {new Date(summary.generated_at).toLocaleTimeString()}.
      </div>
    </div>
  );
}
