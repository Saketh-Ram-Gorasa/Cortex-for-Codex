'use client';

import React, { useEffect, useState } from 'react';

interface ProjectItem {
  id: string;
  name: string;
  visibility: 'private' | 'team';
  is_archived: boolean;
}

interface ProjectSelectorProps {
  token: string;
  backendUrl: string;
  selectedProjectId: string | null;
  onChange: (projectId: string | null) => void;
}

export default function ProjectSelector({
  token,
  backendUrl,
  selectedProjectId,
  onChange,
}: ProjectSelectorProps) {
  const [projects, setProjects] = useState<ProjectItem[]>([]);

  useEffect(() => {
    const loadProjects = async () => {
      try {
        const response = await fetch(`${backendUrl}/api/v1/projects`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!response.ok) {
          return;
        }
        const data = await response.json() as { projects?: ProjectItem[] };
        const visibleProjects = (data.projects || []).filter((project) => !project.is_archived);
        setProjects(visibleProjects);

        if (visibleProjects.length > 0 && !selectedProjectId) {
          onChange(visibleProjects[0].id);
        }
      } catch {
        setProjects([]);
      }
    };

    if (token) {
      loadProjects();
    }
  }, [backendUrl, token, selectedProjectId, onChange]);

  return (
    <select
      value={selectedProjectId || ''}
      onChange={(event) => onChange(event.target.value || null)}
      style={{
        border: '1px solid var(--border)',
        background: 'var(--surface)',
        color: 'var(--text)',
        borderRadius: '8px',
        padding: '8px 10px',
        fontSize: '12px',
        minWidth: '180px',
      }}
    >
      {projects.length === 0 ? (
        <option value="">No Projects</option>
      ) : (
        projects.map((project) => (
          <option key={project.id} value={project.id}>
            {project.name}
          </option>
        ))
      )}
    </select>
  );
}
