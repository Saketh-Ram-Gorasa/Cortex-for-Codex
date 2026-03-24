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
  refreshKey?: number;
  onSelectedNameChange?: (name: string | null) => void;
}

export default function ProjectSelector({
  token,
  backendUrl,
  selectedProjectId,
  onChange,
  refreshKey = 0,
  onSelectedNameChange,
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

        if (visibleProjects.length === 0) {
          onSelectedNameChange?.(null);
          if (selectedProjectId) {
            onChange(null);
          }
          return;
        }

        // If there's already a valid selection, keep it
        const selectedProject = visibleProjects.find((project) => project.id === selectedProjectId) || null;
        if (selectedProject) {
          onSelectedNameChange?.(selectedProject.name);
          return;
        }

        // Default to a project containing "secondcortex" in the name, or fallback to first
        const defaultProject =
          visibleProjects.find((p) => p.name.toLowerCase().includes('secondcortex')) ||
          visibleProjects[0];

        onChange(defaultProject.id);
        onSelectedNameChange?.(defaultProject.name);
      } catch {
        setProjects([]);
        onSelectedNameChange?.(null);
      }
    };

    if (token) {
      loadProjects();
    }
  }, [backendUrl, token, selectedProjectId, onChange, refreshKey, onSelectedNameChange]);

  const handleSelectChange = (nextProjectId: string) => {
    const normalizedId = nextProjectId || null;
    onChange(normalizedId);
    const selectedProject = projects.find((project) => project.id === normalizedId) || null;
    onSelectedNameChange?.(selectedProject?.name || null);
  };

  return (
    <select
      value={selectedProjectId || ''}
      onChange={(event) => handleSelectChange(event.target.value)}
      className="sc-navbar-select"
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
