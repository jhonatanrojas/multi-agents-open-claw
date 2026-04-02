import { useMemoryStore } from '@/store';
import { usePauseProject, useResumeProject } from '@/api';
import { Panel, TaskRow, SectionLabel, EmptyState } from '@/components/shared';
import { ProjectBar } from './ProjectBar';
import type { Task } from '@/types';
import './TasksList.css';

export function TasksList() {
  const project = useMemoryStore((state) => state.project);
  const tasks = useMemoryStore((state) => state.tasks);
  
  const pauseMutation = usePauseProject();
  const resumeMutation = useResumeProject();
  
  // Filter tasks for current project
  // If task has project_id, filter by it
  // If task has no project_id, include if it's the only project or was created recently
  const projectId = project?.id;
  const projectTasks = tasks.filter((t: Task) => {
    // If task has project_id, match exactly
    if (t.project_id) {
      return t.project_id === projectId;
    }
    // If no project_id, check if it matches current project by other means
    // (e.g., recently created when this project is active)
    // For now, include all tasks without project_id when there's an active project
    return projectId !== undefined;
  });
  
  // Group tasks by status
  const activeTasks = projectTasks.filter((t: Task) => 
    ['in_progress', 'planned', 'pending'].includes(t.status)
  );
  const completedTasks = projectTasks.filter((t: Task) => t.status === 'done');
  const failedTasks = projectTasks.filter((t: Task) => 
    ['error', 'paused', 'blocked'].includes(t.status)
  );
  
  return (
    <div className="tasks-list">
      {/* Project bar */}
      <ProjectBar />
      
      {/* Project name header */}
      {project && (
        <div className="tasks-project-header">
          <h3>📋 Tareas de: {project.name}</h3>
          <span className="task-count">{projectTasks.length} tareas</span>
        </div>
      )}
      
      {/* No tasks state */}
      {projectTasks.length === 0 && project && (
        <Panel>
          <EmptyState>
            Este proyecto aún no tiene tareas.
            {project.status === 'delivered' && (
              <><br/>El proyecto fue marcado como entregado sin tareas persistidas en memoria.</>
            )}
            {project.status === 'blocked' && (
              <><br/>El proyecto está esperando clarificación para continuar.</>
            )}
          </EmptyState>
        </Panel>
      )}
      
      {/* Active tasks */}
      {activeTasks.length > 0 && (
        <Panel title="Tareas activas">
          <SectionLabel>
            {activeTasks.length} en curso
          </SectionLabel>
          {activeTasks.map((task: Task) => (
            <TaskRow
              key={task.id}
              task={task}
              onPause={task.status === 'in_progress' 
                ? (id: string) => pauseMutation.mutate({ task_id: id }) 
                : undefined
              }
              onResume={['pending', 'paused'].includes(task.status)
                ? (id: string) => resumeMutation.mutate({ task_id: id })
                : undefined
              }
            />
          ))}
        </Panel>
      )}
      
      {/* Failed/blocked tasks */}
      {failedTasks.length > 0 && (
        <Panel title="Tareas bloqueadas" subtitle="Requieren atención">
          {failedTasks.map((task: Task) => (
            <TaskRow
              key={task.id}
              task={task}
              onResume={(id: string) => resumeMutation.mutate({ task_id: id })}
            />
          ))}
        </Panel>
      )}
      
      {/* Completed tasks */}
      {completedTasks.length > 0 && (
        <Panel title="Completadas" subtitle={`${completedTasks.length} tareas`}>
          {completedTasks.slice(-10).map((task: Task) => (
            <TaskRow key={task.id} task={task} />
          ))}
        </Panel>
      )}
      
      {/* Empty state when no project */}
      {!project && (
        <Panel>
          <EmptyState>
            Selecciona o crea un proyecto para ver sus tareas.
          </EmptyState>
        </Panel>
      )}
    </div>
  );
}
