'use client';

import React, { useEffect, useState, useRef, useCallback } from 'react';

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
  const [loading, setLoading] = useState(false);
  const hasAutoSelected = useRef(false);
  const hasBootstrappedDefault = useRef(false);

  const stableOnChange = useCallback(onChange, [onChange]);
  const stableOnNameChange = useCallback(onSelectedNameChange || (() => {}), [onSelectedNameChange]);

  const normalizeName = (name: string) => name.toLowerCase().replace(/[\s\-_]/g, '');

  const createDefaultSecondCortexProject = useCallback(async (): Promise<ProjectItem | null> => {
    try {
      const createRes = await fetch(`${backendUrl}/api/v1/projects`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          name: 'SecondCortex',
          slug: 'secondcortex',
          visibility: 'private',
        }),
      });

      if (!createRes.ok) {
        return null;
      }

      const created = (await createRes.json()) as ProjectItem;
      return created;
    } catch {
      return null;
    }
  }, [backendUrl, token]);

  useEffect(() => {
    const loadProjects = async () => {
      setLoading(true);
      try {
        const response = await fetch(`${backendUrl}/api/v1/projects`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!response.ok) {
          setLoading(false);
          return;
        }
        const data = await response.json() as { projects?: ProjectItem[] };
        let visibleProjects = (data.projects || []).filter((project) => !project.is_archived);

        let scProject = visibleProjects.find((p) => normalizeName(p.name).includes('secondcortex'));
        if (!scProject && !hasBootstrappedDefault.current) {
          hasBootstrappedDefault.current = true;
          const created = await createDefaultSecondCortexProject();
          if (created && !created.is_archived) {
            visibleProjects = [created, ...visibleProjects.filter((p) => p.id !== created.id)];
            scProject = created;
          }
        }

        setProjects(visibleProjects);

        // If user already selected something valid, just sync the name
        if (selectedProjectId) {
          const match = visibleProjects.find((p) => p.id === selectedProjectId);
          if (match) {
            stableOnNameChange(match.name);
            return;
          }
        }

        // Auto-select only once: find a "secondcortex"-like project
        if (!hasAutoSelected.current && visibleProjects.length > 0) {
          hasAutoSelected.current = true;

          if (scProject) {
            stableOnChange(scProject.id);
            stableOnNameChange(scProject.name);
          } else {
            // Don't auto-select a random project — default to "All Projects"
            stableOnChange(null);
            stableOnNameChange(null);
          }
        }
      } catch {
        setProjects([]);
        stableOnNameChange(null);
      } finally {
        setLoading(false);
      }
    };

    if (token) {
      loadProjects();
    }
  }, [backendUrl, token, refreshKey, selectedProjectId, stableOnChange, stableOnNameChange]);

  const handleSelectChange = (nextValue: string) => {
    if (nextValue === '__all__' || !nextValue) {
      stableOnChange(null);
      stableOnNameChange(null);
    } else {
      stableOnChange(nextValue);
      const match = projects.find((p) => p.id === nextValue);
      stableOnNameChange(match?.name || null);
    }
  };

  return (
    <select
      value={selectedProjectId || '__all__'}
      onChange={(event) => handleSelectChange(event.target.value)}
      className={`sc-navbar-select ${loading ? 'sc-shimmer-card' : ''}`}
      disabled={loading}
      aria-busy={loading}
    >
      <option value="__all__">All Projects</option>
      {projects.map((project) => (
        <option key={project.id} value={project.id}>
          {project.name}
        </option>
      ))}
    </select>
  );
}
