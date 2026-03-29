import { useUIStore, useMemoryStore, useModelsStore } from '@/store';
import { useStartProject } from '@/api';
import { Tabs, type TabId } from '@/components/shared';
import { TasksList } from '@/components/features/TasksList';
import { ProjectBar } from '@/components/features/ProjectBar';
import { ProjectsPanel } from '@/components/features/ProjectsPanel';
import { StartProjectForm } from '@/components/features/StartProjectForm';
import { LogTab } from '@/components/features/LogTab';
import { GatewayTab } from '@/components/features/GatewayTab';
import { FilesTab } from '@/components/features/FilesTab';
import { MiniverseTab } from '@/components/features/MiniverseTab';
import { ModelsPanel } from '@/components/features/ModelsPanel';
import { BlockersBar } from '@/components/features/BlockersBar';
import { SummaryBar } from '@/components/features/SummaryBar';
import './Dashboard.css';

const TABS: Array<{ id: TabId; label: string }> = [
  { id: 'tasks', label: '📋 Tareas' },
  { id: 'projects', label: '📁 Proyectos' },
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
  const startProjectMutation = useStartProject();

  const hasProject = !!project;

  return (
    <div className="dashboard">
      {/* Summary Bar */}
      <SummaryBar />

      {/* Project Bar (when project exists) */}
      {hasProject && <ProjectBar />}

      {/* Blockers */}
      <BlockersBar />

      {/* Start Project Form (when no project) */}
      {!hasProject && (
        <div style={{ marginBottom: '16px' }}>
          <StartProjectForm
            loading={startProjectMutation.isPending}
            onSubmit={(data) => {
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
      )}

      {/* Tab Navigation */}
      <Tabs
        tabs={TABS}
        activeTab={activeTab}
        onTabChange={setActiveTab}
      />

      {/* Tab Content */}
      <div className="dashboard-content">
        {activeTab === 'tasks' && <TasksList />}
        
        {activeTab === 'projects' && (
          <ProjectsPanel
            projects={projects}
            activeProjectId={project?.id}
            onSelect={(p) => console.log('Select project:', p)}
          />
        )}

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
    </div>
  );
}
