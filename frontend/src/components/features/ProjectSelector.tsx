import { useMemoryStore } from '@/store';
import './ProjectSelector.css';

interface ProjectSelectorProps {
  selectedProjectId: string | null;
  onSelect: (projectId: string | null) => void;
}

export function ProjectSelector({ selectedProjectId, onSelect }: ProjectSelectorProps) {
  const projects = useMemoryStore((s) => s.projects);
  const activeProject = useMemoryStore((s) => s.project);
  
  // Use selected or active project
  const currentId = selectedProjectId || activeProject?.id || null;
  const currentProject = projects.find(p => p.id === currentId);
  
  return (
    <div className="project-selector">
      <div className="selector-header">
        <span className="selector-title">Proyecto activo</span>
        {currentProject && (
          <span className="selector-status">
            {currentProject.status === 'running' ? '🟢' : '⚪'} {currentProject.status}
          </span>
        )}
      </div>
      
      <div className="selector-actions">
        {/* Project dropdown */}
        {projects.length > 0 && (
          <select 
            className="project-dropdown"
            value={currentId || ''}
            onChange={(e) => {
              const value = e.target.value;
              onSelect(value || null);
            }}
          >
            <option value="">-- Nuevo Proyecto --</option>
            {projects.map(p => (
              <option key={p.id} value={p.id}>
                {p.name} ({p.status})
              </option>
            ))}
          </select>
        )}
        
        {/* New project button */}
        <button 
          className="new-project-btn"
          onClick={() => onSelect(null)}
        >
          + Nuevo Proyecto
        </button>
      </div>
      
      {/* Current project info */}
      {currentProject && (
        <div className="current-project-info">
          <div className="project-name">{currentProject.name}</div>
          <div className="project-meta">
            {currentProject.description && (
              <span className="project-desc">{currentProject.description}</span>
            )}
            {currentProject.repo_path && (
              <span className="project-repo">📁 {currentProject.repo_path}</span>
            )}
            {currentProject.branch && (
              <span className="project-branch">🔀 {currentProject.branch}</span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}