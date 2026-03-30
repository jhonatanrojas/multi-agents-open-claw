import { useState, useEffect } from 'react';
import { useUIStore, useMemoryStore, useModelsStore } from '@/store';
import { useLoadProject, useRetryPlanning, useStartProject, useTestModel, useUpdateModels } from '@/api';
import { Tabs, type TabId } from '@/components/shared';
import { ProjectItem } from '@/components/features/ProjectItem';
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
import { RuntimePanel } from '@/components/features/RuntimePanel';
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
  const projectViewMode = useUIStore((state) => state.projectViewMode);
  const setProjectViewMode = useUIStore((state) => state.setProjectViewMode);
  const project = useMemoryStore((state) => state.project);
  const projects = useMemoryStore((state) => state.projects);
  const modelConfig = useModelsStore((state) => state.config);
  const modelsLoading = useModelsStore((state) => state.isLoading);
  const availableModels = modelConfig?.available || [];

  const visibleProjects = projects
    .filter((p) => p.status !== 'deleted' && p.status !== 'archived')
    .slice()
    .sort((a, b) => {
      const aTime = new Date(a.updated_at || a.created_at || 0).getTime();
      const bTime = new Date(b.updated_at || b.created_at || 0).getTime();
      return bTime - aTime;
    });
  const historicalProjects = projects
    .filter((p) => p.status === 'deleted' || p.status === 'archived')
    .slice()
    .sort((a, b) => {
      const aTime = new Date(a.updated_at || a.created_at || 0).getTime();
      const bTime = new Date(b.updated_at || b.created_at || 0).getTime();
      return bTime - aTime;
    });
  
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
        setProjectViewMode('view');
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

  const loadProjectMutation = useLoadProject();
  const retryPlanningMutation = useRetryPlanning();
  const testModelMutation = useTestModel();
  const updateModelsMutation = useUpdateModels();
  
  // Determine if we're viewing a project
  const isViewingProject = projectViewMode === 'view' && project;
  const canRetryPlanning =
    project?.orchestrator?.status === 'error' && project?.orchestrator?.phase === 'planning';
  
  // Set initial tab based on mode
  useEffect(() => {
    if (projectViewMode === 'new' && activeTab !== 'projects' && activeTab !== 'models') {
      setActiveTab('projects');
    }
  }, [projectViewMode, activeTab, setActiveTab]);

  const handleProjectSelect = (p: Project | null) => {
    if (p) {
      if (project?.id === p.id) {
        setProjectViewMode('view');
        setActiveTab('tasks');
        setStatusMessage(null);
        return;
      }

      loadProjectMutation.mutate(p.id, {
        onSuccess: () => {
          setProjectViewMode('view');
          setActiveTab('tasks');
          setStatusMessage(null);
        },
        onError: (error) => {
          setStatusMessage({
            type: 'error',
            text: `Error al cargar el proyecto: ${String(error)}`,
          });
        },
      });
    } else {
      setProjectViewMode('new');
      setStatusMessage(null);
    }
  };

  const handleTestModel = async (model: string) => {
    const result = await testModelMutation.mutateAsync(model);
    return {
      ...result,
      model,
    };
  };

  const handleSaveModels = async (agents: Record<'arch' | 'byte' | 'pixel', string>) => {
    try {
      const result = await updateModelsMutation.mutateAsync(agents);
      useModelsStore.getState().setConfig(result.config);
      setStatusMessage({
        type: 'success',
        text: 'Modelos guardados y persistidos en la configuración activa',
      });
      setTimeout(() => setStatusMessage(null), 2000);
    } catch (error) {
      setStatusMessage({
        type: 'error',
        text: `No se pudo guardar la configuración: ${String(error)}`,
      });
      throw error;
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
            setProjectViewMode('new');
          }
        }}
      />
      
      {/* Status message */}
      {statusMessage && (
        <div className={`status-message ${statusMessage.type}`}>
          {statusMessage.type === 'success' ? '✅' : '❌'} {statusMessage.text}
        </div>
      )}

      {!isViewingProject && project && canRetryPlanning && (
        <div className="status-message warning planning-retry-banner">
          <div className="planning-retry-copy">
            <strong>⚠️ Bloqueo de planificación</strong>
            <span>
              {project.orchestrator?.detail || 'La planificación falló. Puedes reintentarla desde aquí.'}
            </span>
          </div>
          <button
            className="btn-primary planning-retry-button"
            onClick={() =>
              retryPlanningMutation.mutate(undefined, {
                onSuccess: () => {
                  setStatusMessage({
                    type: 'success',
                    text: 'Replanificación iniciada correctamente',
                  });
                  setTimeout(() => setStatusMessage(null), 2000);
                },
                onError: (error) => {
                  setStatusMessage({
                    type: 'error',
                    text: `No se pudo reintentar la planificación: ${String(error)}`,
                  });
                },
              })
            }
            disabled={retryPlanningMutation.isPending}
          >
            {retryPlanningMutation.isPending ? 'Reintentando...' : 'Reintentar planificación'}
          </button>
        </div>
      )}

      <RuntimePanel />

      {/* Blockers should be visible both while creating and while viewing a project */}
      <BlockersBar />
      
      {/* Content based on mode */}
      {isViewingProject ? (
        <>
          {/* Project info */}
          <ProjectBar />
          <SummaryBar />
          
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
                isLoading={modelsLoading}
                onSave={handleSaveModels}
                onTestModel={handleTestModel}
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
          {visibleProjects.length > 0 && (
            <div className="recent-projects">
              <h3>Proyectos recientes</h3>
              <div className="recent-projects-list">
                {visibleProjects
                  .slice(0, 5)
                  .map(p => (
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

          {/* Historical Projects */}
          {historicalProjects.length > 0 && (
            <div className="historical-projects">
              <h3>Historial</h3>
              <p className="historical-projects-hint">
                Proyectos cerrados o eliminados con su snapshot final, incluyendo la fase de despliegue.
              </p>
              <div className="historical-projects-list">
                {historicalProjects.slice(0, 5).map((p) => (
                  <ProjectItem key={p.id} project={p} />
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
                onSave={handleSaveModels}
                onTestModel={handleTestModel}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
