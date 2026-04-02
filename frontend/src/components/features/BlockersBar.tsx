import { useMemoryStore } from '@/store';
import type { Blocker } from '@/types';

function isRelevantBlocker(blocker: Blocker, projectId: string, projectCreatedAt?: string): boolean {
  if ((blocker as { resolved?: boolean }).resolved) return false;

  // Skip clarification blockers — handled by CommandBar
  if (Array.isArray(blocker.questions) && blocker.questions.length > 0) return false;

  const blockerProjectId = String(blocker.project_id || '').trim();
  if (projectId && blockerProjectId) return blockerProjectId === projectId;

  const blockerTaskId = String(blocker.task_id || '').trim();
  if (projectId && blockerTaskId) return true;

  const blockerTs = String(blocker.ts || '').trim();
  if (projectId && projectCreatedAt && blockerTs) return blockerTs >= projectCreatedAt;

  return !projectId;
}

export function BlockersBar() {
  const blockers         = useMemoryStore((state) => state.blockers);
  const project          = useMemoryStore((state) => state.project);
  const projectId        = String(project?.id || '').trim();
  const projectCreatedAt = String(project?.created_at || '').trim();

  const visibleBlockers = blockers.filter((b) =>
    isRelevantBlocker(b, projectId, projectCreatedAt)
  );

  if (visibleBlockers.length === 0) return null;

  return (
    <div
      className="blockers-bar"
      style={{
        padding: '10px 14px',
        backgroundColor: '#3a2a2a',
        borderRadius: '8px',
        borderLeft: '3px solid #e24b4a',
        marginBottom: '12px',
        display: 'flex',
        flexDirection: 'column',
        gap: '6px',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
        <span>🚫</span>
        <span style={{ fontWeight: 600, fontSize: '0.82rem', color: '#e88' }}>
          {visibleBlockers.length} bloqueador{visibleBlockers.length !== 1 ? 'es' : ''} activo{visibleBlockers.length !== 1 ? 's' : ''}
        </span>
      </div>
      <ul style={{ margin: 0, paddingLeft: '20px', fontSize: '0.78rem', color: '#caa' }}>
        {visibleBlockers.map((blocker: Blocker, i: number) => (
          <li key={i} style={{ marginBottom: '2px' }}>
            <span style={{ fontWeight: 600, color: '#e99' }}>{blocker.source}:</span>{' '}
            {blocker.msg}
          </li>
        ))}
      </ul>
    </div>
  );
}
