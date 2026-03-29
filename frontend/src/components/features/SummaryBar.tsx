import { useMemoryStore } from '@/store';
import type { Task } from '@/types';

interface SummaryBarProps {
  className?: string;
}

export function SummaryBar({ className = '' }: SummaryBarProps) {
  const project = useMemoryStore((state) => state.project);
  const tasks = useMemoryStore((state) => state.tasks);

  // Calculate stats
  const totalTasks = tasks.length;
  const doneTasks = tasks.filter((t: Task) => t.status === 'done').length;
  const errorTasks = tasks.filter((t: Task) => t.status === 'error').length;
  const inProgressTasks = tasks.filter((t: Task) => t.status === 'in_progress').length;

  return (
    <div
      className={`summary-bar ${className}`}
      style={{
        display: 'flex',
        gap: '16px',
        padding: '12px 16px',
        backgroundColor: '#1e1e2e',
        borderRadius: '8px',
        fontSize: '0.8rem',
      }}
    >
      {/* Project status */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
        <span style={{ color: '#888' }}>📁</span>
        <span style={{ color: project ? '#ddd' : '#666' }}>
          {project ? project.name : 'Sin proyecto'}
        </span>
      </div>

      {/* Task stats */}
      <div style={{ display: 'flex', gap: '12px', marginLeft: 'auto' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
          <span style={{ color: '#888' }}>📋</span>
          <span style={{ color: '#888' }}>{doneTasks}/{totalTasks}</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
          <span style={{ color: '#7F77DD' }}>●</span>
          <span style={{ color: '#7F77DD' }}>{inProgressTasks}</span>
        </div>
        {errorTasks > 0 && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <span style={{ color: '#e24b4a' }}>●</span>
            <span style={{ color: '#e24b4a' }}>{errorTasks}</span>
          </div>
        )}
      </div>

      {/* Preview & Context status */}
      <div style={{ display: 'flex', gap: '8px', marginLeft: '16px', paddingLeft: '16px', borderLeft: '1px solid #333' }}>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '4px',
            padding: '2px 8px',
            backgroundColor: project?.preview_url ? '#2a4a3a' : '#333',
            borderRadius: '4px',
            color: project?.preview_url ? '#8dc' : '#666',
            fontSize: '0.7rem',
          }}
        >
          👁️ {project?.preview_url ? 'Preview OK' : 'Sin preview'}
        </div>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '4px',
            padding: '2px 8px',
            backgroundColor: '#333',
            borderRadius: '4px',
            color: '#666',
            fontSize: '0.7rem',
          }}
        >
          📝 Context
        </div>
      </div>
    </div>
  );
}
