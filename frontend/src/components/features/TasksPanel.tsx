import { TaskRow } from '@/components/shared';
import { EmptyState } from '@/components/shared';
import type { Task } from '@/types';

interface TasksPanelProps {
  tasks: Task[];
  loading?: boolean;
}

export function TasksPanel({ tasks, loading = false }: TasksPanelProps) {
  if (loading) {
    return (
      <div className="tasks-panel">
        <div style={{ padding: '24px', textAlign: 'center', color: '#888' }}>
          Cargando tareas...
        </div>
      </div>
    );
  }

  if (!tasks || tasks.length === 0) {
    return (
      <div className="tasks-panel">
        <EmptyState 
          message="No hay tareas definidas para este proyecto" 
          icon="📋"
        />
      </div>
    );
  }

  return (
    <div className="tasks-panel">
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        {tasks.map((task) => (
          <TaskRow key={task.id} task={task} />
        ))}
      </div>
    </div>
  );
}
