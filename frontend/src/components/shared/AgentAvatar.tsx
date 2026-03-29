import { AGENT_META } from '@/constants';

type AgentId = 'arch' | 'byte' | 'pixel';

interface AgentAvatarProps {
  agentId: AgentId;
  showName?: boolean;
  size?: 'sm' | 'md' | 'lg';
}

export function AgentAvatar({ agentId, showName = true, size = 'md' }: AgentAvatarProps) {
  const meta = AGENT_META[agentId as keyof typeof AGENT_META];
  
  if (!meta) {
    return <span className="agent-avatar unknown">?</span>;
  }

  const sizeMap = {
    sm: { emoji: '1rem', name: '0.75rem' },
    md: { emoji: '1.5rem', name: '0.875rem' },
    lg: { emoji: '2rem', name: '1rem' },
  };

  return (
    <span className="agent-avatar" style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem' }}>
      <span style={{ fontSize: sizeMap[size].emoji }}>{meta.emoji}</span>
      {showName && (
        <span style={{ 
          fontSize: sizeMap[size].name, 
          fontWeight: 600,
          color: meta.color 
        }}>
          {meta.name}
        </span>
      )}
    </span>
  );
}
