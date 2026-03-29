import type { Task } from '@/types';
import { StatusBadge, Badge } from './Badge';
import { AGENT_META } from '@/constants';
import './TaskRow.css';

interface TaskRowProps {
  task: Task;
  onPause?: (taskId: string) => void;
  onResume?: (taskId: string) => void;
}

export function TaskRow({ task, onPause, onResume }: TaskRowProps) {
  const meta = AGENT_META[task.agent as keyof typeof AGENT_META];
  const canPause = task.status === 'in_progress';
  const canRetry = ['error', 'pending', 'paused', 'in_progress'].includes(task.status) || 
                   task.retryable || 
                   (task.failure_count || 0) > 0;
  
  return (
    <div className="task-row">
      <div className="task-meta">
        <span className="task-id">{task.id}</span>
        <span className="task-title">{task.title}</span>
        
        {/* Agent */}
        {meta && (
          <span 
            className="task-agent"
            style={{ color: meta.color }}
          >
            {meta.emoji} {meta.name}
          </span>
        )}
        
        {/* Status */}
        <StatusBadge status={task.status} />
        
        {/* Preview status */}
        {task.preview_url && (
          <Badge variant={task.preview_status === 'running' ? 'success' : 'default'}>
            Preview {task.preview_status || 'stopped'}
          </Badge>
        )}
        
        {/* Actions */}
        {task.preview_url && (
          <a 
            className="btn-outline"
            href={task.preview_url}
            target="_blank"
            rel="noreferrer"
          >
            Abrir preview
          </a>
        )}
        
        {canPause && onPause && (
          <button 
            className="btn-outline"
            onClick={() => onPause(task.id)}
          >
            Pausar
          </button>
        )}
        
        {canRetry && onResume && (
          <button 
            className="btn-outline"
            onClick={() => onResume(task.id)}
          >
            Reanudar
          </button>
        )}
      </div>
      
      {/* Secondary info */}
      {task.agent && (
        <div className="task-skills">
          Co-piloto: {meta?.name || task.agent}
          {task.preview_url && ` · ${task.preview_url}`}
        </div>
      )}
      
      {/* Failure count */}
      {task.failure_count && task.failure_count > 0 && (
        <div className="task-skills">
          Intentos fallidos: {task.failure_count}
          {task.suggested_agent && (
            <> · sugerido: {AGENT_META[task.suggested_agent as keyof typeof AGENT_META]?.name || task.suggested_agent}</>
          )}
        </div>
      )}
      
      {/* Skills */}
      {task.skills && task.skills.length > 0 && (
        <div className="task-skills">
          Habilidades: {task.skills.join(' · ')}
        </div>
      )}
    </div>
  );
}