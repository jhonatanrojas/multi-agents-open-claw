import type { GatewayEvent } from '@/types';
import { AGENT_META } from '@/constants';
import { truncate } from '@/utils';

interface GatewayChatCardProps {
  event: GatewayEvent;
  compact?: boolean;
}

export function GatewayChatCard({ event, compact = false }: GatewayChatCardProps) {
  const agent = AGENT_META[event.agent_id as keyof typeof AGENT_META];
  const agentName = agent?.name || event.agent_id.toUpperCase();
  const agentColor = agent?.color || '#888';
  const agentEmoji = agent?.emoji || '🤖';

  // Extract message content from payload
  const getMessageContent = () => {
    const payload = event.payload as Record<string, unknown>;
    if (typeof payload.content === 'string') {
      return payload.content;
    }
    if (typeof payload.text === 'string') {
      return payload.text;
    }
    if (Array.isArray(payload.content)) {
      // Handle array of content blocks
      return payload.content
        .filter((block): block is Record<string, unknown> => typeof block === 'object' && block !== null)
        .map((block) => {
          if (block.type === 'text' && typeof block.text === 'string') {
            return block.text;
          }
          return '';
        })
        .join('');
    }
    return null;
  };

  const content = getMessageContent();
  const maxLength = compact ? 120 : 300;
  const displayContent = content ? truncate(content, maxLength) : null;

  if (!displayContent) return null;

  return (
    <div
      className="gateway-chat-card"
      style={{
        backgroundColor: '#252536',
        borderRadius: '8px',
        padding: compact ? '8px 12px' : '12px 16px',
        marginBottom: '6px',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '8px' }}>
        <span style={{ fontSize: compact ? '1rem' : '1.2rem' }}>{agentEmoji}</span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ 
            fontWeight: 600, 
            fontSize: '0.8rem', 
            color: agentColor,
            marginBottom: '4px'
          }}>
            {agentName}
          </div>
          <div
            style={{
              fontSize: compact ? '0.75rem' : '0.85rem',
              color: event.kind === 'thinking' ? '#888' : '#ddd',
              lineHeight: 1.4,
              fontStyle: event.kind === 'thinking' ? 'italic' : 'normal',
            }}
          >
            {displayContent}
          </div>
        </div>
      </div>
    </div>
  );
}
