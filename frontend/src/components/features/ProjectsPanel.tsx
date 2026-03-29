import { useState } from 'react';
import { ProjectItem } from './ProjectItem';
import { EmptyState } from '@/components/shared';
import type { Project } from '@/types';

type Scope = 'all' | 'active' | 'finished';

interface ProjectsPanelProps {
  projects: Project[];
  activeProjectId?: string;
  onSelect?: (project: Project) => void;
  onPause?: (projectId: string) => void;
  onResume?: (projectId: string) => void;
  onDelete?: (projectId: string) => void;
}

export function ProjectsPanel({
  projects,
  activeProjectId,
  onSelect,
  onPause,
  onResume,
  onDelete,
}: ProjectsPanelProps) {
  const [scope, setScope] = useState<Scope>('all');

  const filteredProjects = projects.filter((p) => {
    if (scope === 'all') return true;
    if (scope === 'active') return p.status === 'active' || p.status === 'paused';
    if (scope === 'finished') return p.status === 'completed' || p.status === 'failed';
    return true;
  });

  return (
    <div className="projects-panel">
      {/* Scope Toolbar */}
      <div
        style={{
          display: 'flex',
          gap: '8px',
          marginBottom: '16px',
          padding: '8px',
          backgroundColor: '#1e1e2e',
          borderRadius: '8px',
        }}
      >
        {(['all', 'active', 'finished'] as Scope[]).map((s) => (
          <button
            key={s}
            onClick={() => setScope(s)}
            style={{
              padding: '6px 12px',
              fontSize: '0.8rem',
              backgroundColor: scope === s ? '#3a3a5a' : 'transparent',
              color: scope === s ? '#fff' : '#888',
              border: 'none',
              borderRadius: '6px',
              cursor: 'pointer',
              textTransform: 'capitalize' as const,
            }}
          >
            {s === 'all' ? 'Todos' : s === 'active' ? 'Activos' : 'Terminados'}
          </button>
        ))}
      </div>

      {/* Project List */}
      {filteredProjects.length === 0 ? (
        <EmptyState
          message={
            scope === 'all'
              ? 'No hay proyectos todavía'
              : scope === 'active'
              ? 'No hay proyectos activos'
              : 'No hay proyectos terminados'
          }
          icon="📁"
        />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {filteredProjects.map((project) => (
            <ProjectItem
              key={project.id}
              project={project}
              isActive={project.id === activeProjectId}
              onSelect={onSelect}
              onPause={onPause}
              onResume={onResume}
              onDelete={onDelete}
            />
          ))}
        </div>
      )}
    </div>
  );
}
