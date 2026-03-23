'use client';

import React, { useEffect, useMemo, useState } from 'react';

interface TeamGraphSnapshotProps {
  teamId: string;
  token: string;
  backendUrl: string;
  selectedMemberId: string | null;
}

interface MemberSnapshot {
  id: string;
  workspace: string;
  active_file: string;
  git_branch: string | null;
  terminal_commands: string[];
  summary: string;
  enriched_context: Record<string, unknown>;
  timestamp: number;
}

function toIsoFromAnyTimestamp(ts: number): string {
  if (ts > 1_000_000_000_000) {
    return new Date(ts).toISOString();
  }
  if (ts > 1_000_000_000) {
    return new Date(ts * 1000).toISOString();
  }
  return new Date().toISOString();
}

export default function TeamGraphSnapshot({
  teamId,
  token,
  backendUrl,
  selectedMemberId,
}: TeamGraphSnapshotProps) {
  const [snapshots, setSnapshots] = useState<MemberSnapshot[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!selectedMemberId) {
      setSnapshots([]);
      setError(null);
      setLoading(false);
      return;
    }

    const fetchSnapshots = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch(
          `${backendUrl}/api/v1/teams/${teamId}/members/${selectedMemberId}/snapshots?limit=25`,
          {
            headers: { Authorization: `Bearer ${token}` },
          }
        );

        if (!response.ok) {
          throw new Error(`Failed to fetch snapshots (${response.status})`);
        }

        const data = (await response.json()) as MemberSnapshot[];
        setSnapshots(Array.isArray(data) ? data : []);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load snapshots');
      } finally {
        setLoading(false);
      }
    };

    fetchSnapshots();
  }, [selectedMemberId, backendUrl, teamId, token]);

  const latestSnapshot = useMemo(() => {
    if (snapshots.length === 0) {
      return null;
    }
    return snapshots[0];
  }, [snapshots]);

  return (
    <div className="h-full flex flex-col">
      <h2 className="text-xl font-bold mb-4">Team Snapshots & Context</h2>
      <div className="flex-1 bg-slate-800 rounded p-4 overflow-y-auto">
        {!selectedMemberId && <div className="text-sm text-slate-300">Select a teammate to view snapshots.</div>}
        {loading && <div className="text-sm text-slate-300">Loading snapshots...</div>}
        {error && <div className="text-sm text-red-300">{error}</div>}

        {!loading && !error && selectedMemberId && snapshots.length === 0 && (
          <div className="text-sm text-slate-300">No snapshots found for this teammate yet.</div>
        )}

        {!loading && !error && latestSnapshot && (
          <div className="mb-4 rounded border border-slate-600 p-3 bg-slate-900/50">
            <div className="text-xs uppercase tracking-wide text-emerald-300 mb-2">Latest Context</div>
            <div className="text-sm text-white mb-1">{latestSnapshot.summary || 'No summary captured.'}</div>
            <div className="text-xs text-slate-300">File: {latestSnapshot.active_file || 'n/a'}</div>
            <div className="text-xs text-slate-300">Workspace: {latestSnapshot.workspace || 'n/a'}</div>
            <div className="text-xs text-slate-300">Branch: {latestSnapshot.git_branch || 'n/a'}</div>
          </div>
        )}

        {!loading && !error && snapshots.length > 0 && (
          <div className="space-y-2">
            {snapshots.map((snapshot) => (
              <div key={snapshot.id} className="rounded border border-slate-700 p-3 bg-slate-900/40">
                <div className="text-xs text-slate-300 mb-1">
                  {new Date(toIsoFromAnyTimestamp(snapshot.timestamp)).toLocaleString()}
                </div>
                <div className="text-sm text-white mb-2">{snapshot.summary || 'No summary captured.'}</div>
                {snapshot.terminal_commands?.length > 0 && (
                  <div className="text-xs text-slate-300 mb-1">Commands: {snapshot.terminal_commands.slice(0, 3).join(' | ')}</div>
                )}
                <div className="text-xs text-slate-400">
                  Context keys: {Object.keys(snapshot.enriched_context || {}).slice(0, 4).join(', ') || 'none'}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
