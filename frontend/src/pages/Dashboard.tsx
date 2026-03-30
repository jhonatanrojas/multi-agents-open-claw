import { useState, useEffect } from 'react';
import { useUIStore, useMemoryStore, useModelsStore } from '@/store';
import { useStartProject } from '@/api';
import { Tabs, type TabId } from '@/components/shared';
import { TasksList } from '@/components/features/TasksList';
import { ProjectBar } from '@/components/features/ProjectBar';
import { ProjectsPanel } from '@/components/features/ProjectsPanel';
import { ProjectSelector } from '@/components/features/ProjectSelector';
import { StartProjectForm } from '@/components/features/StartProjectForm';
import { AgentsPanel } from '@/components/features/AgentsPanel';
import { LogTab } from '@/components/features/LogTab';
import { GatewayTab } from '@/components/features/GatewayTab';
import { FilesTab } from '@/components/features/FilesTab';
import { MiniverseTab } from '@/components/features/MiniverseTab';
import { ModelsPanel } from '@/components/features/ModelsPanel';
import { BlockersBar } from '@/components/features/BlockersBar';
import { SummaryBar } from '@/components/features/SummaryBar';
import type { Project } from '@/types';
import './Dashboard.css';

const TABS: Array<{ id: TabId; label: string }> = [
  { id: 'projects', label: '📁 Proyectos' },
  { id: 'tasks', label: '📋 Tareas' },
  { id: 'agents', label: '🤖 Agentes' },
  { id: 'models', label: '⚙️ Modelos' },
  { id: 'gateway', label: '🔌 Gateway' },
  { id: 'files', label: '📄 Archivos' },
  { id: 'log', label: '📝 Log' },
  { id: 'miniverse', label: '🌐 Miniverse' },
];

export function Dashboard() {
  const activeTab = useUIStore((state) => state.activeTab);
  const setActiveTab = useUIStore((state) => state.setActiveTab);
  const project = useMemoryStore((state) => state.project);
  const projects = useMemoryStore((state) => state.projects);
  const modelConfig = useModelsStore((state) => state.config);
  const availableModels = modelConfig?.available || [];
  
  // View mode: 'new' for new project, 'view' for viewing existing
  const [viewMode, setViewMode] = useState<'new' | 'view'>('new');
  
  // Status message
  const [statusMessage, setStatusMessage] = useState<{ type: 'success' | 'error' | 'warning'; text: string } | null>(null);
  
  // Check for duplicate active projects
  const checkDuplicateProject = (brief: string): Project | null => {
    const normalizedBrief = brief.trim().toLowerCase();
    return projects.find(p => 
      p.status !== 'completed' && 
      p.status !== 'failed' &&
      p.description?.toLowerCase().includes(normalizedBrief.slice(0, 50))
    ) || null;
  };
  
  // Start project mutation with success callback
  const startProjectMutation = useStartProject({
    onSuccess: (data) => {
      // Show success message
      setStatusMessage({ 
        type: 'success', 
        text: data.message || 'Proyecto iniciado correctamente' 
      });
      
      // The state will be refreshed automatically by SSE or polling
      // Switch to project view after a short delay
      setTimeout(() => {
        setViewMode('view');
        setActiveTab('tasks');
        setStatusMessage(null);
      }, 2000);
    },
    onError: (error) => {
      setStatusMessage({ 
        type: 'error', 
        text: `Error: ${String(error)}` 
      });
    },
  });
  
  // Determine if we're viewing a project
  const isViewingProject = viewMode === 'view' && project;
  
  // Set initial tab based on mode
  useEffect(() => {
    if (viewMode === 'new' && activeTab !== 'projects' && activeTab !== 'models') {
      setActiveTab('projects');
    }
  }, [viewMode, activeTab, setActiveTab]);

  const handleProjectSelect = (p: Project | null) => {
    if (p) {
      setViewMode('view');
      setActiveTab('tasks');
    } else {
      setViewMode('new');
    }
  };

  return (
    <div className="dashboard">
      {/* Project Selector - Always visible */}
      <ProjectSelector 
        selectedProjectId={isViewingProject ? project?.id || null : null}
        onSelect={(id) => {
          if (id) {
            const p = projects.find(proj => proj.id === id);
            if (p) handleProjectSelect(p);
          } else {
            setViewMode('new');
          }
        }}
      />
      
      {/* Status message */}
      {statusMessage && (
        <div className={`status-message ${statusMessage.type}`}>
          {statusMessage.type === 'success' ? '✅' : '❌'} {statusMessage.text}
        </div>
      )}
      
      {/* Content based on mode */}
      {isViewingProject ? (
        <>
          {/* Project info */}
          <ProjectBar />
          <SummaryBar />
          <BlockersBar />
          
          {/* Tab Navigation */}
          <Tabs
            tabs={TABS}
            activeTab={activeTab}
            onTabChange={setActiveTab}
          />
          
          {/* Tab Content */}
          <div className="dashboard-content">
            {activeTab === 'projects' && (
              <ProjectsPanel
                projects={projects}
                activeProjectId={project?.id}
                onSelect={handleProjectSelect}
              />
            )}
            
            {activeTab === 'tasks' && <TasksList />}
            
            {activeTab === 'agents' && <AgentsPanel />}
            
            {activeTab === 'models' && (
              <div style={{ maxWidth: '600px' }}>
                <ModelsPanel
                  modelConfig={modelConfig}
                  availableModels={availableModels}
                  onSave={(agents) => console.log('Save models:', agents)}
                />
              </div>
            )}
            
            {activeTab === 'gateway' && <GatewayTab />}
            {activeTab === 'files' && <FilesTab />}
            {activeTab === 'log' && <LogTab />}
            {activeTab === 'miniverse' && <MiniverseTab />}
          </div>
        </>
      ) : (
        /* New Project View */
        <div className="new-project-view">
          <div className="new-project-header">
            <h2>Crear Nuevo Proyecto</h2>
            <p>Inicia un nuevo proyecto describiendo lo que necesitas</p>
          </div>
          
          <div className="new-project-form-container">
            <StartProjectForm
              loading={startProjectMutation.isPending}
              onSubmit={(data) => {
                // Check for duplicate active project
                const duplicate = checkDuplicateProject(data.brief);
                if (duplicate) {
                  setStatusMessage({ 
                    type: 'warning', 
                    text: `Ya existe un proyecto activo similar: "${duplicate.name}". ¿Deseas continuar?` 
                  });
                  // Still allow submission after warning
                }
                
                startProjectMutation.mutate({
                  brief: data.brief,
                  repo_url: data.repo_url,
                  repo_name: data.repo_name,
                  branch: data.branch,
                  allow_init_repo: data.allow_init,
                });
              }}
            />
          </div>
          
          {/* Recent Projects */}
          {projects.length > 0 && (
            <div className="recent-projects">
              <h3>Proyectos recientes</h3>
              <div className="recent-projects-list">
                {projects.slice(0, 5).map(p => (
                  <button
                    key={p.id}
                    className="recent-project-card"
                    onClick={() => handleProjectSelect(p)}
                  >
                    <span className="recent-project-name">{p.name}</span>
                    <span className="recent-project-status">{p.status}</span>
                  </button>
                ))}
              </div>
            </div>
          )}
          
          {/* Models config (always available) */}
          <div className="models-section">
            <h3>Configuración de Modelos</h3>
            <div style={{ maxWidth: '600px' }}>
              <ModelsPanel
                modelConfig={modelConfig}
                availableModels={availableModels}
                onSave={(agents) => console.log('Save models:', agents)}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}