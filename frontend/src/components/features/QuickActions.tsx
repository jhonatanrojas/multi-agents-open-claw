import { useState } from 'react';
import { useSendSteer, usePauseProject, useResumeProject } from '@/api';
import { Panel, Badge } from '@/components/shared';
import { useMemoryStore, useModelsStore, useUIStore } from '@/store';
import './QuickActions.css';

export function QuickActions() {
  const project = useMemoryStore((state) => state.project);
  const modelsConfig = useModelsStore((state) => state.config);
  const setActiveTab = useUIStore((state) => state.setActiveTab);
  const setProjectViewMode = useUIStore((state) => state.setProjectViewMode);
  
  const steerMutation = useSendSteer();
  const pauseMutation = usePauseProject();
  const resumeMutation = useResumeProject();
  
  const [steerAgent, setSteerAgent] = useState('arch');
  const [steerMessage, setSteerMessage] = useState('');
  const [showSteer, setShowSteer] = useState(false);
  
  const agents = modelsConfig?.agents || {};
  
  return (
    <div className="quick-actions">
      {/* Project controls */}
      <Panel title="Control de proyecto">
        {project ? (
          <div className="project-controls">
            <div className="project-status">
              <Badge variant={project.status === 'active' ? 'success' : 'warning'}>
                {project.status}
              </Badge>
              <span className="project-name">{project.name}</span>
            </div>
            
            <div className="action-buttons">
              {project.status === 'active' && (
                <button 
                  className="btn-outline"
                  onClick={() => pauseMutation.mutate({ pause_running: true })}
                  disabled={pauseMutation.isPending}
                >
                  Pausar proyecto
                </button>
              )}
              {(project.status === 'paused' || project.can_resume) && (
                <button 
                  className="btn-primary"
                  onClick={() => resumeMutation.mutate({ resume_all_failed: true })}
                  disabled={resumeMutation.isPending}
                >
                  Reanudar
                </button>
              )}
            </div>
          </div>
        ) : (
          <div className="no-project-actions">
            <p className="no-project-text">Sin proyecto activo</p>
            <button
              className="btn-primary"
              onClick={() => {
                setProjectViewMode('new');
                setActiveTab('tasks');
              }}
            >
              Nuevo proyecto
            </button>
          </div>
        )}
      </Panel>
      
      {/* Steer agent */}
      <Panel title="Enviar instrucción">
        {showSteer ? (
          <div className="steer-form">
            <select 
              value={steerAgent}
              onChange={(e) => setSteerAgent(e.target.value)}
              className="steer-select"
            >
              {Object.entries(agents).map(([agentId, config]) => (
                <option key={agentId} value={agentId}>
                  {agentId.toUpperCase()} - {config.model}
                </option>
              ))}
            </select>
            
            <textarea
              value={steerMessage}
              onChange={(e) => setSteerMessage(e.target.value)}
              placeholder="Escribe la instrucción..."
              className="steer-textarea"
              rows={3}
            />
            
            <div className="steer-actions">
              <button 
                className="btn-primary"
                onClick={() => {
                  steerMutation.mutate({
                    agentId: steerAgent,
                    message: steerMessage,
                  });
                  setSteerMessage('');
                  setShowSteer(false);
                }}
                disabled={!steerMessage || steerMutation.isPending}
              >
                Enviar
              </button>
              <button 
                className="btn-outline"
                onClick={() => setShowSteer(false)}
              >
                Cancelar
              </button>
            </div>
          </div>
        ) : (
          <button 
            className="btn-primary full-width"
            onClick={() => setShowSteer(true)}
          >
            Nueva instrucción
          </button>
        )}
      </Panel>
    </div>
  );
}
