import { usePauseProject, useResumeProject } from '@/api';
import { Panel, Badge } from '@/components/shared';
import { useMemoryStore, useUIStore } from '@/store';
import './QuickActions.css';

export function QuickActions() {
  const project = useMemoryStore((state) => state.project);
  const setProjectViewMode = useUIStore((state) => state.setProjectViewMode);

  const pauseMutation  = usePauseProject();
  const resumeMutation = useResumeProject();

  return (
    <div className="quick-actions">
      <Panel title="Control de proyecto">
        {project ? (
          <div className="project-controls">
            <div className="project-status">
              <Badge variant={project.status === 'active' ? 'success' : 'warning'}>
                {project.status}
              </Badge>
              <span className="project-name">{project.name}</span>
            </div>

            <div className="action-buttons">
              {project.status === 'active' && (
                <button
                  className="btn-outline"
                  onClick={() => pauseMutation.mutate({ pause_running: true })}
                  disabled={pauseMutation.isPending}
                >
                  Pausar proyecto
                </button>
              )}
              {(project.status === 'paused' || project.can_resume) && (
                <button
                  className="btn-primary"
                  onClick={() => resumeMutation.mutate({ resume_all_failed: true })}
                  disabled={resumeMutation.isPending}
                >
                  Reanudar
                </button>
              )}
            </div>
          </div>
        ) : (
          <div className="no-project-actions">
            <p className="no-project-text">Sin proyecto activo</p>
            <button
              className="btn-primary"
              onClick={() => setProjectViewMode('new')}
            >
              Nuevo proyecto
            </button>
          </div>
        )}
      </Panel>

      <div className="quick-actions__hint">
        <span>💡</span>
        <p>Usa la barra inferior para crear proyectos, ampliar o dirigir agentes</p>
      </div>
    </div>
  );
}
