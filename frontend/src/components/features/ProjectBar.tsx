import { useMemoryStore } from '@/store';
import { usePauseProject, useResumeProject, useDeleteProject } from '@/api';
import { Panel, ProgressBar, Badge } from '@/components/shared';
import type { Task } from '@/types';
import './ProjectBar.css';

export function ProjectBar() {
  const project = useMemoryStore((state) => state.project);
  const tasks = useMemoryStore((state) => state.tasks);
  
  const pauseMutation = usePauseProject();
  const resumeMutation = useResumeProject();
  const deleteMutation = useDeleteProject();
  
  if (!project) {
    return (
      <Panel title="Sin proyecto activo">
        <div className="no-project">
          <p>Sin proyecto en curso. Usa el formulario superior para desplegar uno nuevo.</p>
        </div>
      </Panel>
    );
  }
  
  // Calculate overall progress
  const completedTasks = tasks.filter((t: Task) => t.status === 'done').length;
  const totalTasks = tasks.length;
  const progress = totalTasks > 0 ? Math.round((completedTasks / totalTasks) * 100) : 0;
  
  return (
    <div className="project-bar">
      {/* Header */}
      <div className="project-header">
        <div>
          <div className="project-brief">{project.name}</div>
          {project.repo_path && (
            <div className="project-repo">
              <span>{project.repo_path}</span>
              {project.branch && (
                <span className="project-branch">{project.branch}</span>
              )}
            </div>
          )}
        </div>
        <div className="project-actions">
          <Badge variant="info">{project.status}</Badge>
          {project.status === 'active' && (
            <button 
              className="btn-outline"
              onClick={() => pauseMutation.mutate({ pause_running: true })}
              disabled={pauseMutation.isPending}
            >
              Pausar
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
          <button 
            className="btn-danger"
            onClick={() => deleteMutation.mutate(undefined as never)}
            disabled={deleteMutation.isPending}
          >
            Eliminar
          </button>
        </div>
      </div>
      
      {/* Progress */}
      <ProgressBar value={progress} />
      
      {/* Stats */}
      <div className="project-stats">
        <div className="stat">
          <span className="stat-value">{totalTasks}</span>
          <span className="stat-label">Tareas</span>
        </div>
        <div className="stat">
          <span className="stat-value">{completedTasks}</span>
          <span className="stat-label">Completadas</span>
        </div>
        <div className="stat">
          <span className="stat-value">{tasks.filter((t: Task) => t.status === 'in_progress').length}</span>
          <span className="stat-label">En progreso</span>
        </div>
        <div className="stat">
          <span className="stat-value">{tasks.filter((t: Task) => t.status === 'error').length}</span>
          <span className="stat-label">Errores</span>
        </div>
      </div>
    </div>
  );
}
