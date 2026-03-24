'use client';

import React, { useEffect, useState } from 'react';

interface ProjectItem {
  id: string;
  name: string;
  visibility: 'private' | 'team';
  is_archived: boolean;
}

interface ProjectManagerProps {
  token: string;
  backendUrl: string;
  onClose: () => void;
  onProjectsChanged: () => void;
}

export default function ProjectManager({
  token,
  backendUrl,
  onClose,
  onProjectsChanged,
}: ProjectManagerProps) {
  const [projects, setProjects] = useState<ProjectItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionPending, setActionPending] = useState(false);
  const [newProjectName, setNewProjectName] = useState('');
  const [renameValueById, setRenameValueById] = useState<Record<string, string>>({});

  const loadProjects = async () => {
    setLoading(true);
    const response = await fetch(`${backendUrl}/api/v1/projects`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok) {
      setLoading(false);
      return;
    }
    const data = await response.json() as { projects?: ProjectItem[] };
    const list = data.projects || [];
    setProjects(list);
    setRenameValueById(Object.fromEntries(list.map((project) => [project.id, project.name])));
    setLoading(false);
  };

  useEffect(() => {
    loadProjects().catch(() => undefined);
  }, []);

  const createProject = async () => {
    if (!newProjectName.trim()) {
      return;
    }
    setActionPending(true);
    const response = await fetch(`${backendUrl}/api/v1/projects`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ name: newProjectName.trim() }),
    });
    if (!response.ok) {
      setActionPending(false);
      return;
    }
    setNewProjectName('');
    await loadProjects();
    onProjectsChanged();
    setActionPending(false);
  };

  const renameProject = async (projectId: string) => {
    const nextName = (renameValueById[projectId] || '').trim();
    if (!nextName) {
      return;
    }
    setActionPending(true);
    const response = await fetch(`${backendUrl}/api/v1/projects/${projectId}`, {
      method: 'PATCH',
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ name: nextName }),
    });
    if (!response.ok) {
      setActionPending(false);
      return;
    }
    await loadProjects();
    onProjectsChanged();
    setActionPending(false);
  };

  const toggleArchive = async (project: ProjectItem) => {
    setActionPending(true);
    const endpoint = project.is_archived ? 'unarchive' : 'archive';
    const response = await fetch(`${backendUrl}/api/v1/projects/${project.id}/${endpoint}`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok) {
      setActionPending(false);
      return;
    }
    await loadProjects();
    onProjectsChanged();
    setActionPending(false);
  };

  const deleteProject = async (project: ProjectItem) => {
    if (!window.confirm(`Delete project "${project.name}"? This cannot be undone.`)) {
      return;
    }
    setActionPending(true);
    const response = await fetch(`${backendUrl}/api/v1/projects/${project.id}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok) {
      setActionPending(false);
      return;
    }
    await loadProjects();
    onProjectsChanged();
    setActionPending(false);
  };

  return (
    <div className="sc-modal-wrap">
      <div className="sc-modal-backdrop" onClick={onClose} />
      <div className="sc-modal-card" style={{ maxWidth: 560 }}>
        <div className="sc-modal-stack">
          <div className="sc-modal-head">
            <div className="sc-modal-emoji">
              <svg width="20" height="20" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"><rect x="2.3" y="3" width="11.4" height="10" rx="1.4" /><path d="M2.3 6.2h11.4" /><path d="M5 9h2.5" /></svg>
            </div>
            <h3 className="sc-modal-title">My Projects</h3>
            <p className="sc-modal-sub">Create, rename, or archive your projects.</p>
          </div>

          <div style={{ display: 'flex', gap: '8px' }}>
            <input
              value={newProjectName}
              onChange={(event) => setNewProjectName(event.target.value)}
              placeholder="New project name"
              className="sc-auth-input"
              style={{ flex: 1, marginBottom: 0 }}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  createProject();
                }
              }}
            />
            <button className="btn-primary" onClick={createProject} type="button">Create</button>
          </div>

          <div style={{ display: 'grid', gap: '8px', maxHeight: '320px', overflowY: 'auto' }}>
            {loading && (
              <div className="sc-shimmer-stack" aria-live="polite">
                <div className="sc-shimmer-card"><div className="sc-shimmer-line xl w-60" /></div>
                <div className="sc-shimmer-card"><div className="sc-shimmer-line xl w-60" /></div>
                <div className="sc-shimmer-card"><div className="sc-shimmer-line xl w-60" /></div>
              </div>
            )}
            {!loading && projects.map((project) => (
              <div
                key={project.id}
                style={{
                  border: '1px solid var(--border)',
                  borderRadius: '8px',
                  padding: '8px',
                  display: 'flex',
                  gap: '8px',
                  alignItems: 'center',
                  background: project.is_archived ? 'rgba(255,255,255,0.02)' : 'transparent',
                  opacity: project.is_archived ? 0.6 : 1,
                }}
              >
                <input
                  value={renameValueById[project.id] || ''}
                  onChange={(event) =>
                    setRenameValueById((prev) => ({
                      ...prev,
                      [project.id]: event.target.value,
                    }))
                  }
                  style={{
                    flex: 1,
                    border: '1px solid var(--border)',
                    background: 'var(--surface)',
                    color: 'var(--text)',
                    borderRadius: '8px',
                    padding: '6px 8px',
                    fontSize: '12px',
                    fontFamily: 'var(--font-mono)',
                  }}
                />
                <button className="btn-secondary" onClick={() => renameProject(project.id)} type="button" style={{ fontSize: '11px', padding: '6px 10px' }}>Rename</button>
                <button className="btn-secondary" onClick={() => toggleArchive(project)} type="button" style={{ fontSize: '11px', padding: '6px 10px' }}>
                  {project.is_archived ? 'Unarchive' : 'Archive'}
                </button>
                <button className="btn-secondary" onClick={() => deleteProject(project)} type="button" style={{ fontSize: '11px', padding: '6px 10px', color: '#ff6b6b' }}>Delete</button>
              </div>
            ))}
            {!loading && projects.length === 0 && (
              <p style={{ color: 'var(--muted)', fontSize: '12px', fontFamily: 'var(--font-mono)' }}>No projects yet. Create one above.</p>
            )}
          </div>

          <button
            onClick={onClose}
            className="btn-primary sc-modal-close"
            disabled={actionPending}
          >
            {actionPending ? (
              <>
                <span className="loading-ring" aria-hidden="true" />
                Working…
              </>
            ) : (
              'Done'
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
