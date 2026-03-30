import type { GatewayEvent } from '@/types';
import { AGENT_META } from '@/constants';
import { extractGatewayText, fmtTime } from '@/utils';

interface GatewayEventCardProps {
  event: GatewayEvent;
}

export function GatewayEventCard({ event }: GatewayEventCardProps) {
  const agent = AGENT_META[event.agent_id as keyof typeof AGENT_META];
  const agentName = agent?.name || event.agent_id.toUpperCase();
  const agentColor = agent?.color || '#888';

  const getEventIcon = () => {
    switch (event.kind) {
      case 'thinking': return '🤔';
      case 'tool': return '🔧';
      case 'message': return '💬';
      default: return '📨';
    }
  };

  const getEventLabel = () => {
    switch (event.kind) {
      case 'thinking': return 'Pensando';
      case 'tool': return 'Herramienta';
      case 'message': return 'Mensaje';
      default: return event.event;
    }
  };

  const getPreviewContent = () => {
    if (event.summary) return event.summary;
    if (event.payload && typeof event.payload === 'object') {
      const p = event.payload as Record<string, unknown>;
      if (p.tool) return `Usando: ${p.tool}`;
    }
    const text = extractGatewayText(event.payload);
    if (text) {
      return text.length > 100 ? text.slice(0, 100) + '...' : text;
    }
    return null;
  };

  const preview = getPreviewContent();

  return (
    <div
      className="gateway-event-card"
      style={{
        backgroundColor: '#1e1e2e',
        borderRadius: '8px',
        padding: '12px 16px',
        marginBottom: '8px',
        borderLeft: `3px solid ${agentColor}`,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
        <span style={{ fontSize: '0.9rem' }}>{getEventIcon()}</span>
        <span style={{ fontWeight: 600, color: agentColor }}>{agentName}</span>
        <span style={{ fontSize: '0.75rem', color: '#888' }}>{getEventLabel()}</span>
        <span style={{ fontSize: '0.7rem', color: '#666', marginLeft: 'auto' }}>
          {fmtTime(event.received_at)}
        </span>
      </div>
      {preview && (
        <div
          style={{
            fontSize: '0.8rem',
            color: '#ccc',
            fontFamily: 'ui-monospace, monospace',
            backgroundColor: '#2a2a3e',
            padding: '8px',
            borderRadius: '4px',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
          }}
        >
          {preview}
        </div>
      )}
    </div>
  );
}
