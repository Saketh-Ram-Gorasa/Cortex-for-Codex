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
  const [newProjectName, setNewProjectName] = useState('');
  const [renameValueById, setRenameValueById] = useState<Record<string, string>>({});

  const loadProjects = async () => {
    const response = await fetch(`${backendUrl}/api/v1/projects`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok) {
      return;
    }
    const data = await response.json() as { projects?: ProjectItem[] };
    const list = data.projects || [];
    setProjects(list);
    setRenameValueById(Object.fromEntries(list.map((project) => [project.id, project.name])));
  };

  useEffect(() => {
    loadProjects().catch(() => undefined);
  }, []);

  const createProject = async () => {
    if (!newProjectName.trim()) {
      return;
    }
    const response = await fetch(`${backendUrl}/api/v1/projects`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ name: newProjectName.trim() }),
    });
    if (!response.ok) {
      return;
    }
    setNewProjectName('');
    await loadProjects();
    onProjectsChanged();
  };

  const renameProject = async (projectId: string) => {
    const nextName = (renameValueById[projectId] || '').trim();
    if (!nextName) {
      return;
    }
    const response = await fetch(`${backendUrl}/api/v1/projects/${projectId}`, {
      method: 'PATCH',
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ name: nextName }),
    });
    if (!response.ok) {
      return;
    }
    await loadProjects();
    onProjectsChanged();
  };

  const toggleArchive = async (project: ProjectItem) => {
    const endpoint = project.is_archived ? 'unarchive' : 'archive';
    const response = await fetch(`${backendUrl}/api/v1/projects/${project.id}/${endpoint}`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok) {
      return;
    }
    await loadProjects();
    onProjectsChanged();
  };

  return (
    <div className="sc-dashboard-panel" style={{ marginBottom: '16px' }}>
      <div className="sc-dashboard-panel-inner" style={{ display: 'block' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
          <h2 className="sc-dashboard-h2" style={{ margin: 0 }}>My Projects</h2>
          <button className="btn-secondary" onClick={onClose} type="button">Close</button>
        </div>

        <div style={{ display: 'flex', gap: '8px', marginBottom: '12px' }}>
          <input
            value={newProjectName}
            onChange={(event) => setNewProjectName(event.target.value)}
            placeholder="New project name"
            style={{
              flex: 1,
              border: '1px solid var(--border)',
              background: 'var(--surface)',
              color: 'var(--text)',
              borderRadius: '8px',
              padding: '8px 10px',
              fontSize: '12px',
            }}
          />
          <button className="btn-primary" onClick={createProject} type="button">Create</button>
        </div>

        <div style={{ display: 'grid', gap: '8px' }}>
          {projects.map((project) => (
            <div
              key={project.id}
              style={{
                border: '1px solid var(--border)',
                borderRadius: '8px',
                padding: '8px',
                display: 'flex',
                gap: '8px',
                alignItems: 'center',
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
                }}
              />
              <button className="btn-secondary" onClick={() => renameProject(project.id)} type="button">Rename</button>
              <button className="btn-secondary" onClick={() => toggleArchive(project)} type="button">
                {project.is_archived ? 'Unarchive' : 'Archive'}
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
