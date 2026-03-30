import { useMemoryStore } from '@/store';
import { Panel, EmptyState, Badge } from '@/components/shared';
import { AGENT_META } from '@/constants';
import type { LogEntry } from '@/types';
import './LogTab.css';

export function LogTab() {
  const log = useMemoryStore((state) => state.log);
  const visibleLogs = [...log].slice(-100).reverse();
  const isClarificationAck = (entry: LogEntry) =>
    entry.msg?.includes('Acuse de recibo:') || entry.msg?.includes('Aclaración recibida');
  
  return (
    <div className="log-tab">
      <Panel title="Log del sistema" subtitle={`${log.length} eventos`}>
        {visibleLogs.length === 0 ? (
          <EmptyState>Sin eventos registrados.</EmptyState>
        ) : (
          <div className="log-list">
            {visibleLogs.map((entry: LogEntry, i: number) => {
              const meta = entry.agent ? AGENT_META[entry.agent as keyof typeof AGENT_META] : null;
              const ack = isClarificationAck(entry);
              
              return (
                <div key={i} className={`log-entry${ack ? ' log-entry-ack' : ''}`}>
                  <span className="log-time">
                    {formatTime(entry.ts)}
                  </span>
                  {meta && (
                    <span 
                      className="log-agent"
                      style={{ color: meta.color }}
                    >
                      {meta.emoji}
                    </span>
                  )}
                  <span className="log-level">
                    <Badge variant={ack ? 'success' : 'info'}>
                      {entry.msg?.split(':')[0] || 'info'}
                    </Badge>
                  </span>
                  <span className="log-message">
                    {entry.msg}
                    {ack && (
                      <span className="log-ack-note">
                        Reanudación solicitada
                      </span>
                    )}
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </Panel>
    </div>
  );
}

function formatTime(iso: string): string {
  if (!iso) return '';
  try {
    const date = new Date(iso);
    return date.toLocaleTimeString('es-ES', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    });
  } catch {
    return iso;
  }
}
