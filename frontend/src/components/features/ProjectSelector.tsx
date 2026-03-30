import { useMemoryStore } from '@/store';
import './ProjectSelector.css';

interface ProjectSelectorProps {
  selectedProjectId?: string | null;
  onSelect: (projectId: string | null) => void;
}

export function ProjectSelector({ selectedProjectId, onSelect }: ProjectSelectorProps) {
  const projects = useMemoryStore((s) => s.projects);
  const activeProject = useMemoryStore((s) => s.project);
  
  // Filter out deleted projects
  const visibleProjects = projects.filter(p => 
    p.status !== 'deleted' && p.status !== 'archived'
  );
  
  // Use the explicitly selected project when provided.
  const currentId = selectedProjectId !== undefined ? selectedProjectId : activeProject?.id || null;
  const currentProject = visibleProjects.find(p => p.id === currentId);
  
  return (
    <div className="project-selector">
      <div className="selector-header">
        <span className="selector-title">Proyecto activo</span>
        {currentProject && (
          <span className="selector-status">
            {currentProject.status === 'running' ? '🟢' : currentProject.status === 'blocked' ? '🟡' : '⚪'} {currentProject.status}
          </span>
        )}
      </div>
      
      <div className="selector-actions">
        {/* Project dropdown */}
        {visibleProjects.length > 0 && (
          <select 
            className="project-dropdown"
            value={currentId || ''}
            onChange={(e) => {
              const value = e.target.value;
              onSelect(value || null);
            }}
          >
            <option value="">-- Nuevo Proyecto --</option>
            {visibleProjects.map(p => (
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
