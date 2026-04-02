import type { GatewayEvent } from '@/types';
import { AGENT_META } from '@/constants';
import { extractGatewayText, truncate, formatRelativeTime } from '@/utils';

interface GatewayChatCardProps {
  event: GatewayEvent;
  compact?: boolean;
}

const KIND_ICON: Record<string, string> = {
  thinking: '💭',
  tool:     '🔧',
  message:  '💬',
  event:    '📡',
};

/** Extract tool name from a tool-kind gateway event payload */
function extractToolName(payload: unknown): string | null {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return null;
  const p = payload as Record<string, unknown>;
  // Common shapes: {tool: "name"}, {name: "name"}, {function: {name: "name"}}
  if (typeof p.tool === 'string') return p.tool;
  if (typeof p.name === 'string') return p.name;
  if (p.function && typeof (p.function as Record<string, unknown>).name === 'string') {
    return (p.function as Record<string, unknown>).name as string;
  }
  if (p.tool_use && typeof (p.tool_use as Record<string, unknown>).name === 'string') {
    return (p.tool_use as Record<string, unknown>).name as string;
  }
  return null;
}

export function GatewayChatCard({ event, compact = false }: GatewayChatCardProps) {
  const agent = AGENT_META[event.agent_id as keyof typeof AGENT_META];
  const agentName  = agent?.name  || event.agent_id.toUpperCase();
  const agentColor = agent?.color || '#888';
  const agentEmoji = agent?.emoji || '🤖';

  const kindIcon = KIND_ICON[event.kind] ?? '📡';
  const toolName = event.kind === 'tool' ? extractToolName(event.payload) : null;

  // Text content
  const rawText = extractGatewayText(event.payload);
  const content = rawText || event.summary || null;
  const maxLength = compact ? 100 : 300;
  const displayContent = content ? truncate(content, maxLength) : null;

  // For tool events without displayable text, at least show the tool name
  const isToolOnly = event.kind === 'tool' && !displayContent && toolName;

  if (!displayContent && !isToolOnly) return null;

  const isVeryRecent = event.received_at &&
    (Date.now() - new Date(event.received_at).getTime()) < 12_000;

  return (
    <div
      className={`gateway-chat-card gateway-chat-card--${event.kind}${isVeryRecent ? ' gateway-chat-card--live' : ''}`}
      style={{
        borderRadius: '8px',
        padding: compact ? '7px 10px' : '10px 14px',
        marginBottom: '5px',
        borderLeft: `3px solid ${agentColor}`,
        background: event.kind === 'thinking' ? 'var(--bg-secondary, #f5f4f0)' : 'var(--bg-primary, #fff)',
        border: `1px solid var(--border, #e8e6df)`,
        borderLeftColor: agentColor,
        borderLeftWidth: '3px',
      }}
    >
      {/* Header row */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: displayContent ? '4px' : 0 }}>
        <span style={{ fontSize: compact ? '0.85rem' : '1rem' }}>{agentEmoji}</span>
        <span style={{ fontSize: '0.75rem', fontWeight: 600, color: agentColor, flexShrink: 0 }}>
          {agentName}
        </span>
        <span style={{ fontSize: '0.68rem', color: '#aaa' }}>{kindIcon}</span>
        {toolName && (
          <span style={{
            fontSize: '0.65rem',
            background: '#f3f4f6',
            color: '#374151',
            padding: '1px 6px',
            borderRadius: '99px',
            fontFamily: 'var(--font-mono)',
            maxWidth: '140px',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}>
            {toolName}
          </span>
        )}
        {isVeryRecent && (
          <span className="gateway-chat-card__live-dot" style={{
            width: '6px', height: '6px', borderRadius: '50%',
            background: agentColor, marginLeft: 'auto', flexShrink: 0,
            animation: 'liveBlip 1.2s ease-in-out infinite',
          }} />
        )}
        {!isVeryRecent && event.received_at && (
          <span style={{ fontSize: '0.65rem', color: '#aaa', marginLeft: 'auto', flexShrink: 0 }}>
            {formatRelativeTime(event.received_at)}
          </span>
        )}
      </div>

      {/* Content */}
      {displayContent && (
        <div style={{
          fontSize: compact ? '0.72rem' : '0.82rem',
          color: event.kind === 'thinking' ? 'var(--text-secondary, #5f5e5a)' : 'var(--text-primary, #1a1916)',
          lineHeight: 1.45,
          fontStyle: event.kind === 'thinking' ? 'italic' : 'normal',
          wordBreak: 'break-word',
        }}>
          {displayContent}
        </div>
      )}

      {isToolOnly && (
        <div style={{ fontSize: compact ? '0.7rem' : '0.78rem', color: '#6b7280' }}>
          Llamando herramienta…
        </div>
      )}
    </div>
  );
}
