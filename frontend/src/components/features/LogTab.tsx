import { useMemoryStore } from '@/store';
import { Panel, EmptyState, Badge } from '@/components/shared';
import { AGENT_META } from '@/constants';
import type { LogEntry } from '@/types';
import './LogTab.css';

export function LogTab() {
  const log = useMemoryStore((state) => state.log);
  
  // Group logs by time window
  const now = Date.now();
  const recentLogs = log.filter((entry: LogEntry) => {
    const logTime = new Date(entry.ts).getTime();
    return now - logTime < 3600000; // Last hour
  });
  
  return (
    <div className="log-tab">
      <Panel title="Log del sistema" subtitle={`${log.length} eventos`}>
        {recentLogs.length === 0 ? (
          <EmptyState>Sin eventos en la última hora.</EmptyState>
        ) : (
          <div className="log-list">
            {recentLogs.slice(-50).reverse().map((entry: LogEntry, i: number) => {
              const meta = entry.agent ? AGENT_META[entry.agent as keyof typeof AGENT_META] : null;
              
              return (
                <div key={i} className="log-entry">
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
                    <Badge variant="info">
                      {entry.msg?.split(':')[0] || 'info'}
                    </Badge>
                  </span>
                  <span className="log-message">
                    {entry.msg}
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