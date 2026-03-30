import { useState } from 'react';
import { useMemoryStore, useGatewayStore, useModelsStore } from '@/store';
import { sendSteer } from '@/api/client';
import { StatusBadge } from '@/components/shared';
import { AGENT_META } from '@/constants';
import './AgentsPanel.css';

export function AgentsPanel() {
  const agents = useMemoryStore((s) => s.agents);
  const gatewayEvents = useGatewayStore((s) => s.events);
  const modelConfig = useModelsStore((s) => s.config);
  
  // Selected agent for steer
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [steerMessage, setSteerMessage] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [sendStatus, setSendStatus] = useState<{ ok: boolean; message: string } | null>(null);
  
  const MAX_CHARS = 500;
  
  // Get latest gateway event for each agent
  const getLatestEvent = (agentId: string) => {
    const agentEvents = gatewayEvents
      .filter(e => e.agent_id === agentId)
      .sort((a, b) => new Date(b.received_at).getTime() - new Date(a.received_at).getTime());
    return agentEvents[0] || null;
  };
  
  const handleSendSteer = async () => {
    if (!selectedAgent || !steerMessage.trim()) return;
    
    setIsSending(true);
    setSendStatus(null);
    
    try {
      await sendSteer(selectedAgent, steerMessage);
      setSendStatus({ ok: true, message: 'Instrucción enviada' });
      setSteerMessage('');
      setTimeout(() => {
        setSelectedAgent(null);
        setSendStatus(null);
      }, 2000);
    } catch (e) {
      setSendStatus({ ok: false, message: String(e) });
    } finally {
      setIsSending(false);
    }
  };
  
  const agentList = Object.entries(agents);

  const getAgentModelInfo = (agentId: string) => {
    const selectedModelId = modelConfig?.agents?.[agentId]?.model || AGENT_META[agentId as keyof typeof AGENT_META]?.model;
    const selectedModel = modelConfig?.available?.find((model) => model.qualified === selectedModelId);
    return {
      model: selectedModelId || 'N/A',
      provider: selectedModel?.provider || 'desconocido',
    };
  };
  
  return (
    <div className="agents-panel">
      <div className="panel-header">
        <h3>🤖 Agentes del Squad</h3>
        <span className="agent-count">{agentList.length} activos</span>
      </div>
      
      {/* Agent list */}
      <div className="agents-list">
        {agentList.map(([agentId, agent]) => {
          const meta = AGENT_META[agentId as keyof typeof AGENT_META];
          if (!meta) return null;
          
          const latestEvent = getLatestEvent(agentId);
          const isSelected = selectedAgent === agentId;
          const modelInfo = getAgentModelInfo(agentId);
          
          return (
            <div 
              key={agentId}
              className={`agent-item ${isSelected ? 'selected' : ''}`}
              style={{ borderLeftColor: meta.color }}
            >
              <div className="agent-header">
                <div className="agent-info">
                  <span className="agent-emoji">{meta.emoji}</span>
                  <span className="agent-name">{meta.name}</span>
                  <span className="agent-role">{meta.rol}</span>
                </div>
                <StatusBadge status={agent.status || 'idle'} />
              </div>
              
              <div className="agent-model">
                <code>{modelInfo.model}</code>
                <span className="agent-model-provider">· {modelInfo.provider}</span>
              </div>
              
              {/* Latest activity */}
              {latestEvent && (
                <div className="agent-activity">
                  <span className="activity-kind">{latestEvent.kind}</span>
                  <span className="activity-time">
                    {new Date(latestEvent.received_at).toLocaleTimeString()}
                  </span>
                </div>
              )}
              
              {/* Steer button */}
              <button 
                className="steer-btn"
                onClick={() => setSelectedAgent(isSelected ? null : agentId)}
              >
                {isSelected ? 'Cancelar' : '💬 Enviar instrucción'}
              </button>
              
              {/* Steer form */}
              {isSelected && (
                <div className="steer-form">
                  <div className="steer-header">
                    <span>Enviar instrucción a {meta.name}</span>
                    <span className="char-count">{steerMessage.length}/{MAX_CHARS}</span>
                  </div>
                  <textarea
                    value={steerMessage}
                    onChange={(e) => setSteerMessage(e.target.value.slice(0, MAX_CHARS))}
                    placeholder="Escribe tu instrucción aquí..."
                    rows={4}
                    disabled={isSending}
                  />
                  
                  {sendStatus && (
                    <div className={`send-status ${sendStatus.ok ? 'success' : 'error'}`}>
                      {sendStatus.message}
                    </div>
                  )}
                  
                  <div className="steer-actions">
                    <button 
                      className="cancel-btn"
                      onClick={() => setSelectedAgent(null)}
                      disabled={isSending}
                    >
                      Cancelar
                    </button>
                    <button 
                      className="send-btn"
                      onClick={handleSendSteer}
                      disabled={isSending || !steerMessage.trim()}
                    >
                      {isSending ? 'Enviando...' : 'Enviar'}
                    </button>
                  </div>
                </div>
              )}
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
