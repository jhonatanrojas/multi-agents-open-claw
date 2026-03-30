import { useState } from 'react';
import { replyClarification } from '@/api/client';
import { useMemoryStore } from '@/store';
import type { Blocker } from '@/types';

function isRelevantBlocker(blocker: Blocker, projectId: string, projectCreatedAt?: string): boolean {
  if ((blocker as { resolved?: boolean }).resolved) {
    return false;
  }

  const blockerProjectId = String((blocker as { project_id?: string }).project_id || '').trim();
  if (projectId && blockerProjectId) {
    return blockerProjectId === projectId;
  }

  const blockerTaskId = String(blocker.task_id || '').trim();
  if (projectId && blockerTaskId) {
    return true;
  }

  const blockerTs = String((blocker as { ts?: string }).ts || '').trim();
  if (projectId && projectCreatedAt && blockerTs) {
    return blockerTs >= projectCreatedAt;
  }

  return !projectId;
}

function extractBriefFromBlocker(blocker?: Blocker): string | undefined {
  const text = String(blocker?.msg || '').trim();
  if (!text) {
    return undefined;
  }

  const match = text.match(/Brief:\s*([\s\S]*?)(?:\n\s*Preguntas:|\n\s*Respuesta esperada:|\n\s*Siguiente paso:|$)/i);
  return (match?.[1] || '').trim() || undefined;
}

export function BlockersBar() {
  const blockers = useMemoryStore((state) => state.blockers);
  const project = useMemoryStore((state) => state.project);
  const pending = project?.pending_clarification;
  const projectId = String(project?.id || '').trim();
  const projectCreatedAt = String(project?.created_at || '').trim();
  const visibleBlockers = blockers.filter((blocker) => isRelevantBlocker(blocker, projectId, projectCreatedAt));
  const clarificationBlocker = visibleBlockers.find(
    (blocker) => Array.isArray(blocker.questions) && blocker.questions.length > 0
  );
  const pendingActive = Boolean((pending && !pending.resolved) || clarificationBlocker);
  const activeQuestions =
    Array.isArray(pending?.questions) && pending.questions.length > 0
      ? pending.questions
      : clarificationBlocker?.questions || [];
  const activeBrief = pending?.original_brief || extractBriefFromBlocker(clarificationBlocker);

  const [reply, setReply] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [status, setStatus] = useState<{ tone: 'ok' | 'error' | 'muted'; text: string } | null>(null);

  if (visibleBlockers.length === 0 && !pendingActive) {
    return null;
  }

  const handleReply = async () => {
    const text = reply.trim();
    if (!text) {
      setStatus({ tone: 'error', text: 'Escribe una aclaración antes de enviar.' });
      return;
    }

    setIsSending(true);
    setStatus({ tone: 'muted', text: 'Enviando aclaración y reanudando planificación...' });

    try {
      const data = await replyClarification({
        reply: text,
        auto_resume: true,
        source: 'dashboard',
      });
      setReply('');
      setStatus({ tone: 'ok', text: data.message || 'Aclaración registrada.' });
    } catch (error) {
      setStatus({ tone: 'error', text: String(error) });
    } finally {
      setIsSending(false);
    }
  };

  return (
    <div
      className="blockers-bar"
      style={{
        padding: '12px 16px',
        backgroundColor: '#3a2a2a',
        borderRadius: '8px',
        borderLeft: '3px solid #e24b4a',
        marginBottom: '16px',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          marginBottom: '8px',
        }}
      >
        <span style={{ fontSize: '1rem' }}>🚫</span>
        <span
          style={{
            fontWeight: 600,
            fontSize: '0.85rem',
            color: '#e88',
          }}
        >
          Bloqueadores activos ({visibleBlockers.length + (pendingActive ? 1 : 0)})
        </span>
      </div>

      {pendingActive && (
        <div
          style={{
            marginBottom: '12px',
            padding: '12px',
            borderRadius: '8px',
            backgroundColor: '#422c2c',
            border: '1px solid #f0b9b9',
            display: 'grid',
            gap: '10px',
          }}
        >
          <div>
            <div style={{ fontWeight: 700, color: '#ffd2d2', marginBottom: '4px' }}>
              🧭 Aclaración pendiente
            </div>
            <div style={{ color: '#f0c1c1', fontSize: '0.8rem', lineHeight: 1.5 }}>
              {activeBrief || 'El proyecto necesita una respuesta para continuar la planificación.'}
            </div>
          </div>

          {activeQuestions.length > 0 && (
            <ul style={{ margin: 0, paddingLeft: '20px', color: '#f4d0d0', fontSize: '0.8rem' }}>
              {activeQuestions.map((question, index) => (
                <li key={index} style={{ marginBottom: '4px' }}>
                  {question}
                </li>
              ))}
            </ul>
          )}

          <textarea
            value={reply}
            onChange={(event) => setReply(event.target.value)}
            placeholder="Escribe la aclaración concreta..."
            rows={4}
            style={{
              width: '100%',
              padding: '10px 12px',
              borderRadius: '8px',
              border: '1px solid #f0b9b9',
              backgroundColor: '#fff',
              color: '#1a1916',
              fontSize: '0.85rem',
              resize: 'vertical',
            }}
          />

          <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
            <button
              type="button"
              onClick={handleReply}
              disabled={isSending || !reply.trim()}
              style={{
                padding: '8px 14px',
                borderRadius: '6px',
                border: 'none',
                backgroundColor: isSending || !reply.trim() ? '#5b4650' : '#e24b4a',
                color: '#fff',
                fontSize: '0.82rem',
                cursor: isSending || !reply.trim() ? 'not-allowed' : 'pointer',
                fontWeight: 600,
              }}
            >
              {isSending ? 'Enviando...' : 'Responder y reanudar'}
            </button>
            <span
              style={{
                color:
                  status?.tone === 'ok'
                    ? '#8dcf7d'
                    : status?.tone === 'error'
                      ? '#ffb2b2'
                      : '#f0c1c1',
                fontSize: '0.75rem',
              }}
            >
              {status?.text || 'La respuesta se guardará y ARCH retomará la planificación.'}
            </span>
          </div>
        </div>
      )}

      <ul
        style={{
          margin: 0,
          paddingLeft: '24px',
          fontSize: '0.8rem',
          color: '#caa',
        }}
      >
        {visibleBlockers.map((blocker: Blocker, i: number) => (
          <li key={i} style={{ marginBottom: '4px' }}>
            <span style={{ fontWeight: 600, color: '#e99' }}>{blocker.source}:</span>{' '}
            {blocker.msg}
          </li>
        ))}
      </ul>
    </div>
  );
}
