import { useMemoryStore } from '@/store';
import { AgentCard } from '@/components/shared';
import type { LogEntry } from '@/types';
import './AgentsGrid.css';

export function AgentsGrid() {
  const agents = useMemoryStore((state) => state.agents);
  const log = useMemoryStore((state) => state.log);
  
  // Filter logs by agent
  const getAgentLogs = (agentId: string): Array<{ ts: string; msg: string }> => {
    return log
      .filter((entry: LogEntry) => entry.agent === agentId)
      .slice(-5)
      .map((entry: LogEntry) => ({ ts: entry.ts, msg: entry.msg }));
  };
  
  // Get latest chat for each agent (simplified)
  const latestChats: Record<string, null> = {};
  
  return (
    <div className="agents-grid">
      {Object.entries(agents).map(([agentId, agent]) => (
        <AgentCard
          key={agentId}
          agentId={agentId}
          agent={agent}
          latestChat={latestChats[agentId]}
          logs={getAgentLogs(agentId)}
        />
      ))}
    </div>
  );
}