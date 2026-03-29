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
  
  // Group tasks by status
  const activeTasks = tasks.filter((t: Task) => 
    ['in_progress', 'planned', 'pending'].includes(t.status)
  );
  const completedTasks = tasks.filter((t: Task) => t.status === 'done');
  const failedTasks = tasks.filter((t: Task) => 
    ['error', 'paused', 'blocked'].includes(t.status)
  );
  
  return (
    <div className="tasks-list">
      {/* Project bar */}
      <ProjectBar />
      
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
      
      {/* Empty state */}
      {tasks.length === 0 && !project && (
        <Panel>
          <EmptyState>
            No hay tareas activas. Inicia un proyecto para comenzar.
          </EmptyState>
        </Panel>
      )}
    </div>
  );
}