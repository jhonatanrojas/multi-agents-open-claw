import type { Project } from '@/types';

interface ProjectItemProps {
  project: Project;
  isActive?: boolean;
  onSelect?: (project: Project) => void;
  onPause?: (projectId: string) => void;
  onResume?: (projectId: string) => void;
  onDelete?: (projectId: string) => void;
}

export function ProjectItem({
  project,
  isActive = false,
  onSelect,
  onPause,
  onResume,
  onDelete,
}: ProjectItemProps) {
  const getStatusColor = () => {
    switch (project.status) {
      case 'active': return '#639922';
      case 'paused': return '#D48A00';
      case 'completed': return '#1D9E75';
      case 'failed': return '#E24B4A';
      default: return '#888';
    }
  };

  return (
    <div
      className="project-item"
      onClick={() => onSelect?.(project)}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '12px',
        padding: '12px 16px',
        backgroundColor: isActive ? '#2a2a4a' : '#252536',
        borderRadius: '8px',
        cursor: 'pointer',
        borderLeft: `3px solid ${getStatusColor()}`,
        transition: 'background-color 0.15s',
      }}
    >
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
          <span style={{ fontWeight: 600, color: '#ddd' }}>{project.name}</span>
          <span
            style={{
              padding: '2px 8px',
              fontSize: '0.7rem',
              borderRadius: '10px',
              backgroundColor: getStatusColor() + '33',
              color: getStatusColor(),
              textTransform: 'capitalize' as const,
            }}
          >
            {project.status}
          </span>
        </div>
        {project.description && (
          <p
            style={{
              margin: '0 0 6px 0',
              fontSize: '0.8rem',
              color: '#888',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {project.description}
          </p>
        )}
        {project.task_counts && (
          <div style={{ fontSize: '0.75rem', color: '#666' }}>
            {project.task_counts.done}/{project.task_counts.total} tareas completadas
          </div>
        )}
      </div>

      <div style={{ display: 'flex', gap: '4px' }} onClick={(e) => e.stopPropagation()}>
        {project.status === 'active' && onPause && (
          <button
            onClick={() => onPause(project.id)}
            style={{
              padding: '4px 10px',
              fontSize: '0.75rem',
              backgroundColor: '#4a3a2a',
              color: '#da8',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer',
            }}
          >
            ⏸
          </button>
        )}
        {project.status === 'paused' && onResume && (
          <button
            onClick={() => onResume(project.id)}
            style={{
              padding: '4px 10px',
              fontSize: '0.75rem',
              backgroundColor: '#2a4a3a',
              color: '#8dc',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer',
            }}
          >
            ▶
          </button>
        )}
        {onDelete && (
          <button
            onClick={() => onDelete(project.id)}
            style={{
              padding: '4px 10px',
              fontSize: '0.75rem',
              backgroundColor: '#4a2a2a',
              color: '#e88',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer',
            }}
          >
            🗑
          </button>
        )}
      </div>
    </div>
  );
}
