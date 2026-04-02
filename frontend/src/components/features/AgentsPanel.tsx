import { useMemoryStore, useGatewayStore, useModelsStore } from '@/store';
import { StatusBadge } from '@/components/shared';
import { AGENT_META, STATUS_ES } from '@/constants';
import { extractGatewayText, truncate, formatRelativeTime } from '@/utils';
import { useUIStore } from '@/store';
import './AgentsPanel.css';

const KIND_ICON: Record<string, string> = {
  thinking: '💭',
  tool:     '🔧',
  message:  '💬',
};

function extractToolName(payload: unknown): string | null {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return null;
  const p = payload as Record<string, unknown>;
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

export function AgentsPanel() {
  const agents      = useMemoryStore((s) => s.agents);
  const tasks       = useMemoryStore((s) => s.tasks);
  const gatewayEvents = useGatewayStore((s) => s.events);
  const modelConfig = useModelsStore((s) => s.config);
  const setActiveTab = useUIStore((s) => s.setActiveTab);

  const agentList = Object.entries(agents);

  const getLatestEvents = (agentId: string) =>
    gatewayEvents
      .filter((e) => e.agent_id === agentId)
      .sort((a, b) => new Date(b.received_at).getTime() - new Date(a.received_at).getTime())
      .slice(0, 3);

  const getTaskTitle = (taskId: string | null | undefined): string | null => {
    if (!taskId) return null;
    const task = tasks.find((t) => t.id === taskId);
    return task?.title ?? null;
  };

  const getAgentModel = (agentId: string) => {
    const modelId = modelConfig?.agents?.[agentId]?.model
      || AGENT_META[agentId as keyof typeof AGENT_META]?.model;
    const available = modelConfig?.available?.find((m) => m.qualified === modelId);
    return { model: modelId || 'N/A', provider: available?.provider || '' };
  };

  return (
    <div className="agents-panel">
      <div className="panel-header">
        <h3>🤖 Agentes del Squad</h3>
        <span className="agent-count">{agentList.length} activos</span>
      </div>

      <div className="agents-list">
        {agentList.map(([agentId, agent]) => {
          const meta = AGENT_META[agentId as keyof typeof AGENT_META];
          if (!meta) return null;

          const recentEvents = getLatestEvents(agentId);
          const latestEvent  = recentEvents[0] ?? null;
          const taskTitle    = getTaskTitle(agent.current_task);
          const modelInfo    = getAgentModel(agentId);

          const isLive = latestEvent &&
            (Date.now() - new Date(latestEvent.received_at).getTime()) < 15_000;

          const activitySummary = (() => {
            if (!latestEvent) return null;
            if (latestEvent.kind === 'tool') {
              const tool = extractToolName(latestEvent.payload);
              return tool ? `🔧 ${tool}` : '🔧 herramienta';
            }
            const text = extractGatewayText(latestEvent.payload) || latestEvent.summary;
            if (!text) return null;
            return `${KIND_ICON[latestEvent.kind] ?? '💬'} ${truncate(text, 90)}`;
          })();

          return (
            <div
              key={agentId}
              className={`agent-item ${isLive ? 'agent-item--live' : ''}`}
              style={{ borderLeftColor: meta.color, borderLeftWidth: '3px', borderLeftStyle: 'solid' }}
            >
              {/* Header */}
              <div className="agent-header">
                <div className="agent-info">
                  <span className="agent-emoji">{meta.emoji}</span>
                  <div className="agent-name-group">
                    <span className="agent-name" style={{ color: meta.color }}>{meta.name}</span>
                    <span className="agent-role">{meta.rol}</span>
                  </div>
                </div>
                <div className="agent-header-right">
                  <StatusBadge status={agent.status || 'idle'} />
                  {isLive && <span className="agent-live-dot" style={{ background: meta.color }} />}
                </div>
              </div>

              {/* Model */}
              <div className="agent-model">
                <code className="agent-model-code">{modelInfo.model}</code>
                {modelInfo.provider && (
                  <span className="agent-model-provider">· {modelInfo.provider}</span>
                )}
              </div>

              {/* Current task */}
              {taskTitle && (
                <div className="agent-current-task">
                  <span className="agent-task-label">Tarea:</span>
                  <span className="agent-task-title">{taskTitle}</span>
                </div>
              )}

              {/* Live activity from gateway */}
              {activitySummary && (
                <div className={`agent-activity-line ${isLive ? 'agent-activity-line--live' : ''}`}>
                  <span className="agent-activity-text">{activitySummary}</span>
                  {latestEvent && (
                    <span className="agent-activity-time">
                      {formatRelativeTime(latestEvent.received_at)}
                    </span>
                  )}
                </div>
              )}

              {/* No activity yet */}
              {!activitySummary && !taskTitle && agent.status === 'idle' && (
                <div className="agent-idle-hint">
                  {STATUS_ES['idle']} · esperando trabajo
                </div>
              )}

              {/* Steer hint */}
              <div className="agent-steer-hint">
                <button
                  className="agent-steer-link"
                  type="button"
                  onClick={() => setActiveTab('tasks')}
                >
                  @{agentId} para enviar instrucción directa desde la barra inferior
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {agentList.length === 0 && (
        <div className="empty-state">
          <p>No hay agentes activos</p>
        </div>
      )}
    </div>
  );
}
