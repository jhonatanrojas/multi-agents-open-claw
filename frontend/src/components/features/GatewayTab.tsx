import { useGatewayStore } from '@/store';
import { Panel, EmptyState, Badge } from '@/components/shared';
import type { GatewayEvent } from '@/types';
import './GatewayTab.css';

export function GatewayTab() {
  const status = useGatewayStore((state) => state.status);
  const events = useGatewayStore((state) => state.events);
  
  return (
    <div className="gateway-tab">
      {/* Status */}
      <Panel title="Gateway Status">
        <div className="gateway-status">
          <div className="status-row">
            <span className="status-label">Conexión</span>
            <Badge variant={status.connected ? 'success' : 'error'}>
              {status.connected ? 'Conectado' : 'Desconectado'}
            </Badge>
          </div>
          {status.last_error && (
            <div className="status-row">
              <span className="status-label">Último error</span>
              <span className="status-value error">{status.last_error}</span>
            </div>
          )}
          {status.url && (
            <div className="status-row">
              <span className="status-label">URL</span>
              <span className="status-value">{status.url}</span>
            </div>
          )}
        </div>
      </Panel>
      
      {/* Events */}
      <Panel 
        title="Eventos" 
        subtitle={`${events.length} eventos`}
      >
        {events.length === 0 ? (
          <EmptyState>Sin eventos del gateway.</EmptyState>
        ) : (
          <div className="events-list">
            {events.slice(-100).reverse().map((event: GatewayEvent, i: number) => (
              <div key={i} className="event-row">
                <span className="event-time">
                  {formatTime(event.received_at)}
                </span>
                <span className="event-kind">
                  <Badge variant={getKindVariant(event.kind)}>
                    {event.kind}
                  </Badge>
                </span>
                <span className="event-agent">{event.agent_id || '-'}</span>
                <span className="event-message">
                  {truncate(event.summary || event.event, 100)}
                </span>
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}

function formatTime(iso: string): string {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleTimeString('es-ES');
  } catch {
    return iso;
  }
}

function truncate(text: string, max: number): string {
  if (!text || text.length <= max) return text || '';
  return text.slice(0, max) + '…';
}

function getKindVariant(kind: string): 'default' | 'success' | 'warning' | 'error' | 'info' {
  switch (kind) {
    case 'thinking': return 'info';
    case 'tool': return 'success';
    case 'message': return 'default';
    case 'error': return 'error';
    default: return 'default';
  }
}