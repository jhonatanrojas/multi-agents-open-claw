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
  const normalizedStatus = (project.status || '').toLowerCase();
  const isHistorical = normalizedStatus === 'deleted' || normalizedStatus === 'archived';

  const getStatusColor = () => {
    switch (normalizedStatus) {
      case 'active': return '#639922';
      case 'paused': return '#D48A00';
      case 'completed': return '#1D9E75';
      case 'failed': return '#E24B4A';
      case 'deleted':
      case 'archived':
        return '#7A7A7A';
      default: return '#888';
    }
  };

  const displayStatus = isHistorical ? 'histórico' : project.status;
  const hasRuntimeTaskCounts =
    Boolean(project.task_counts && project.task_counts.total > 0);
  const displayTaskTotal = hasRuntimeTaskCounts
    ? project.task_counts!.total
    : project.task_count_snapshot ?? 0;
  const displayTaskDone = hasRuntimeTaskCounts
    ? project.task_counts!.done
    : (isHistorical && displayTaskTotal > 0 ? displayTaskTotal : 0);
  const hasDeploySnapshot =
    Boolean(project.deploy_phase_name || project.deploy_task_title || project.deploy_host);

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
        cursor: onSelect ? 'pointer' : 'default',
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
            {displayStatus}
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
        {hasDeploySnapshot && (
          <div
            style={{
              marginBottom: '6px',
              padding: '8px 10px',
              borderRadius: '6px',
              border: '1px solid #34344a',
              background: '#1c1c2a',
            }}
          >
            <div style={{ fontSize: '0.68rem', color: '#8f8fa8', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
              Fase 5 · despliegue histórico
            </div>
            {project.deploy_phase_name && (
              <div style={{ fontSize: '0.78rem', color: '#ddd', marginTop: '3px', fontWeight: 600 }}>
                {project.deploy_phase_name}
              </div>
            )}
            {project.deploy_task_title && (
              <div style={{ fontSize: '0.74rem', color: '#b0b0c0', marginTop: '2px' }}>
                {project.deploy_task_title}
              </div>
            )}
            {project.deploy_host && (
              <div style={{ fontSize: '0.72rem', color: '#7f7f95', marginTop: '2px' }}>
                Host: {project.deploy_host}
              </div>
            )}
          </div>
        )}
        {hasRuntimeTaskCounts && (
          <div style={{ fontSize: '0.75rem', color: '#666' }}>
            {displayTaskDone}/{displayTaskTotal} tareas completadas
          </div>
        )}
        {!hasRuntimeTaskCounts && project.task_count_snapshot ? (
          <div style={{ fontSize: '0.75rem', color: '#666' }}>
            {project.task_count_snapshot} tareas registradas en el snapshot
          </div>
        ) : null}
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
