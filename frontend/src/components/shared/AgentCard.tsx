import { useState } from 'react';
import type { Agent } from '@/types';
import { StatusBadge } from './Badge';
import { AGENT_META } from '@/constants';
import { sendSteer } from '@/api/client';
import { useModelsStore } from '@/store';
import './AgentCard.css';

interface AgentCardProps {
  agentId: string;
  agent: Agent;
  latestChat?: {
    received_at: string;
    event: string;
    session_key?: string;
    message: string;
    kind: string;
  } | null;
  logs?: Array<{ ts: string; msg: string }>;
}

export function AgentCard({ agentId, agent, latestChat, logs }: AgentCardProps) {
  const meta = AGENT_META[agentId as keyof typeof AGENT_META];
  const modelConfig = useModelsStore((state) => state.config);
  if (!meta) return null;
  
  const status = agent.status || 'offline';
  const [isExpanded, setIsExpanded] = useState(false);
  const [steerMessage, setSteerMessage] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const [sendSuccess, setSendSuccess] = useState(false);
  
  const MAX_CHARS = 140;
  const remaining = MAX_CHARS - steerMessage.length;
  const selectedModelId = modelConfig?.agents?.[agentId]?.model || meta.model;
  const selectedModel = modelConfig?.available?.find((model) => model.qualified === selectedModelId);
  const provider = selectedModel?.provider || 'desconocido';
  
  const handleSend = async () => {
    if (!steerMessage.trim()) return;
    
    setIsSending(true);
    setSendError(null);
    setSendSuccess(false);
    
    try {
      await sendSteer(agentId, steerMessage);
      setSteerMessage('');
      setSendSuccess(true);
      setTimeout(() => {
        setIsExpanded(false);
        setSendSuccess(false);
      }, 1500);
    } catch (e) {
      setSendError(String(e));
    } finally {
      setIsSending(false);
    }
  };
  
  return (
    <div 
      className="agent-card"
      style={{ borderTop: `3px solid ${meta.color}` }}
    >
      {/* Header */}
      <div className="agent-card-header">
        <div>
          <div className="agent-card-name">
            <span className="agent-emoji">{meta.emoji}</span>
            <span className="agent-name">{meta.name}</span>
          </div>
          <div className="agent-role">{meta.rol}</div>
        </div>
        <StatusBadge status={status} />
      </div>
      
      {/* Model */}
      <div className="agent-model">
        <code>{selectedModelId}</code>
        <span className="agent-model-provider">· {provider}</span>
      </div>
      
      {/* Latest chat */}
      {latestChat ? (
        <div 
          className="agent-chat"
          style={{ borderLeftColor: meta.color }}
        >
          <div className="agent-chat-head">
            <div>
              <div className="agent-chat-label">Último chat</div>
              <div className="agent-chat-meta">
                <span>{formatTime(latestChat.received_at)}</span>
                <span>·</span>
                <span>{latestChat.event}</span>
                {latestChat.session_key && (
                  <>
                    <span>·</span>
                    <span>{latestChat.session_key}</span>
                  </>
                )}
              </div>
            </div>
            <GatewayPill kind={latestChat.kind} />
          </div>
          <div className="agent-chat-body">
            {truncate(latestChat.message, 200)}
          </div>
        </div>
      ) : (
        <div className="agent-chat-empty">
          Sin mensajes chat recientes del Gateway.
        </div>
      )}
      
      {/* Current task */}
      {agent.current_task && (
        <div 
          className="agent-task"
          style={{ borderLeftColor: meta.color }}
        >
          Tarea: <strong>{agent.current_task}</strong>
        </div>
      )}
      
      {/* Last seen */}
      {agent.last_seen && (
        <div className="agent-seen">
          Última actividad: {formatTime(agent.last_seen)}
        </div>
      )}
      
      {/* Recent logs */}
      {logs && logs.length > 0 && (
        <div className="agent-logs">
          <div className="agent-logs-title">Logs recientes</div>
          {logs.slice(-5).map((log, i) => (
            <div key={i} className="agent-log-item">
              <span className="agent-log-time">{formatTime(log.ts)}</span>
              <span>{log.msg}</span>
            </div>
          ))}
        </div>
      )}
      
      {/* Inline Steer Controls */}
      <div className="agent-steer-section">
        {!isExpanded ? (
          <button 
            className="steer-btn"
            onClick={() => setIsExpanded(true)}
          >
            💬 Steer
          </button>
        ) : (
          <div className="steer-expanded">
            <div className="steer-header">
              <span>Steer {meta.name}</span>
              <button 
                className="steer-close"
                onClick={() => {
                  setIsExpanded(false);
                  setSteerMessage('');
                  setSendError(null);
                }}
              >
                ×
              </button>
            </div>
            <textarea
              className="steer-input"
              placeholder={`Enviar mensaje a ${meta.name}...`}
              value={steerMessage}
              onChange={(e) => setSteerMessage(e.target.value.slice(0, MAX_CHARS))}
              rows={3}
            />
            <div className="steer-footer">
              <span className={`char-count ${remaining < 20 ? 'warning' : ''}`}>
                {remaining} / {MAX_CHARS}
              </span>
              <div className="steer-actions">
                {sendError && (
                  <span className="steer-error">{sendError}</span>
                )}
                {sendSuccess && (
                  <span className="steer-success">✓ Enviado</span>
                )}
                <button 
                  className="steer-send"
                  onClick={handleSend}
                  disabled={isSending || !steerMessage.trim()}
                >
                  {isSending ? 'Enviando...' : 'Enviar'}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// Helper components
function GatewayPill({ kind }: { kind: string }) {
  const colors: Record<string, { bg: string; text: string }> = {
    thinking: { bg: '#EEEDFE', text: '#3C3489' },
    tool: { bg: '#E1F5EE', text: '#0F6E56' },
    message: { bg: '#EAF3DE', text: '#3B6D11' },
  };
  const c = colors[kind] || { bg: '#F1EFE8', text: '#5F5E5A' };
  
  return (
    <span 
      className="gateway-pill"
      style={{ background: c.bg, color: c.text }}
    >
      {kind}
    </span>
  );
}

// Utilities
function formatTime(iso: string): string {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleTimeString('es-ES');
  } catch {
    return iso;
  }
}

function truncate(text: string, max: number): string {
  if (!text || text.length <= max) return text;
  return text.slice(0, max) + '…';
}
