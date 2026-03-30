import { useState } from 'react';
import { useMemoryStore } from '@/store';
import {
  useDeleteProject,
  useExtendProject,
  usePauseProject,
  useResumeProject,
  useRetryPlanning,
} from '@/api';
import { Panel, ProgressBar, Badge } from '@/components/shared';
import type { Task } from '@/types';
import './ProjectBar.css';

export function ProjectBar() {
  const project = useMemoryStore((state) => state.project);
  const tasks = useMemoryStore((state) => state.tasks);
  
  const pauseMutation = usePauseProject();
  const resumeMutation = useResumeProject();
  const retryPlanningMutation = useRetryPlanning();
  const extendProjectMutation = useExtendProject();
  const deleteMutation = useDeleteProject();
  const [extensionBrief, setExtensionBrief] = useState('');
  const [autoResume, setAutoResume] = useState(true);
  const [extensionFeedback, setExtensionFeedback] = useState<{
    type: 'success' | 'error';
    text: string;
  } | null>(null);
  
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
  const normalizedProjectStatus = String(project.status || '').toLowerCase();
  const isDeliveredProject = normalizedProjectStatus === 'delivered' || normalizedProjectStatus === 'completed';
  const canRetryPlanning =
    project.orchestrator?.status === 'error' && project.orchestrator?.phase === 'planning';

  const handleExtendProject = () => {
    const brief = extensionBrief.trim();
    if (!brief) {
      setExtensionFeedback({
        type: 'error',
        text: 'Describe la nueva característica o modificación antes de agregarla.',
      });
      return;
    }

    setExtensionFeedback(null);
    extendProjectMutation.mutate(
      {
        brief,
        project_id: project.id,
        auto_resume: autoResume,
        source: 'dashboard',
      },
      {
        onSuccess: (data) => {
          setExtensionBrief('');
          setExtensionFeedback({
            type: 'success',
            text: `${data.message}: ${data.task_id} · ${data.task_title}`,
          });
          window.setTimeout(() => setExtensionFeedback(null), 4000);
        },
        onError: (error) => {
          setExtensionFeedback({
            type: 'error',
            text: `No se pudo agregar la extensión: ${String(error)}`,
          });
        },
      }
    );
  };
  
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
          {canRetryPlanning && (
            <button
              className="btn-primary"
              onClick={() => retryPlanningMutation.mutate()}
              disabled={retryPlanningMutation.isPending}
              title="Vuelve a ejecutar la planificación del proyecto actual"
            >
              {retryPlanningMutation.isPending ? 'Reintentando...' : 'Reintentar planificación'}
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

      <div className="project-extension">
        <div className="project-extension-header">
          <div>
            <div className="project-extension-title">Extender proyecto</div>
            <div className="project-extension-subtitle">
              {isDeliveredProject
                ? 'El proyecto está entregado. Esta acción lo reabre en la misma memoria y encola una nueva tarea sin crear otro proyecto.'
                : 'Agrega una nueva característica o modificación al proyecto actual sin crear un proyecto nuevo.'}
            </div>
          </div>
          <Badge variant={isDeliveredProject ? 'warning' : 'info'}>
            {isDeliveredProject ? 'Reabrir' : 'Extensión'}
          </Badge>
        </div>

        <textarea
          className="input-field project-extension-textarea"
          value={extensionBrief}
          onChange={(e) => {
            setExtensionBrief(e.target.value);
            setExtensionFeedback(null);
          }}
          placeholder="Ej: Agregar autenticación JWT, documentar el flujo del coordinador o mejorar el selector de modelos."
          rows={4}
        />

        <label className="project-extension-toggle">
          <input
            type="checkbox"
            checked={autoResume}
            onChange={(e) => setAutoResume(e.target.checked)}
          />
          Reanudar automáticamente al encolar la extensión
        </label>

        {extensionFeedback && (
          <div className={`project-extension-feedback ${extensionFeedback.type}`}>
            {extensionFeedback.text}
          </div>
        )}

        <div className="form-actions project-extension-actions">
          <button
            type="button"
            className="btn-primary"
            onClick={handleExtendProject}
            disabled={extendProjectMutation.isPending || !extensionBrief.trim()}
          >
            {extendProjectMutation.isPending
              ? 'Encolando...'
              : autoResume
                ? 'Agregar y reanudar'
                : 'Agregar extensión'}
          </button>
        </div>
      </div>
    </div>
  );
}
