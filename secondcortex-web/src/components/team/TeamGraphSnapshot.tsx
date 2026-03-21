'use client';

import React from 'react';

interface TeamGraphSnapshotProps {
  teamId: string;
  token: string | null;
}

export default function TeamGraphSnapshot({ teamId, token }: TeamGraphSnapshotProps) {
  return (
    <div className="h-full flex flex-col">
      <h2 className="text-xl font-bold mb-4">Team Activity Graph</h2>
      <div className="flex-1 bg-slate-800 rounded p-4 flex items-center justify-center">
        <div className="text-center">
          <div className="text-lg font-semibold mb-2">Team Snapshot</div>
          <div className="text-sm text-slate-400">
            Real-time team activity graph will render here
          </div>
          {/* Placeholder for actual graph component */}
          <svg
            viewBox="0 0 400 200"
            className="mt-4 w-full h-64"
            style={{ maxWidth: '100%' }}
          >
            {/* Simple placeholder chart */}
            <polyline
              points="0,150 50,120 100,90 150,110 200,60 250,80 300,40 350,70 400,50"
              fill="none"
              stroke="#65a30d"
              strokeWidth="2"
            />
            <line x1="0" y1="160" x2="400" y2="160" stroke="#475569" strokeWidth="1" />
          </svg>
        </div>
      </div>
    </div>
  );
}
