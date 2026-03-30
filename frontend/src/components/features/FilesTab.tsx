import { useEffect } from 'react';
import { Panel } from '@/components/shared';
import { FileTree } from './files/FileTree';
import { FilePreview } from './FilePreview';
import { useFilesStore, useMemoryStore, useUIStore } from '@/store';
import { fetchFiles } from '@/api/client';
import './FilesTab.css';

export function FilesTab() {
  const projectId = useMemoryStore((s) => s.project?.id || null);
  const snapshot = useFilesStore((s) => s.snapshot);
  const error = useFilesStore((s) => s.error);
  const previewContent = useFilesStore((s) => s.previewContent);
  const previewLoading = useFilesStore((s) => s.previewLoading);
  const previewError = useFilesStore((s) => s.previewError);
  const selectedFilePath = useUIStore((s) => s.selectedFilePath);
  const setFilesScope = useUIStore((s) => s.setFilesScope);
  const filesScope = useUIStore((s) => s.filesScope);
  
  // Refresh files whenever the active project changes.
  useEffect(() => {
    const filesStore = useFilesStore.getState();
    const uiStore = useUIStore.getState();

    if (!projectId) {
      filesStore.clear();
      uiStore.setSelectedFilePath(null);
      filesStore.setPreviewLoading(false);
      return;
    }

    let cancelled = false;
    filesStore.clear();
    uiStore.setSelectedFilePath(null);
    filesStore.setPreviewLoading(false);
    filesStore.setLoading(true);

    fetchFiles()
      .then((snapshot) => {
        if (!cancelled) {
          filesStore.setSnapshot(snapshot);
        }
      })
      .catch((e) => {
        if (!cancelled) {
          filesStore.setError(String(e));
        }
      })
      .finally(() => {
        if (!cancelled) {
          filesStore.setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [projectId]);
  
  // Count files
  const fileCount = (snapshot?.files_produced?.length || 0) + 
                    (snapshot?.progress_files?.length || 0);
  
  return (
    <div className="files-tab">
      {error ? (
        <Panel title="Archivos" subtitle="Error de carga">
          <div className="file-tree-empty">
            <p>No se pudieron cargar los archivos: {error}</p>
          </div>
        </Panel>
      ) : (
        <Panel 
          title="Archivos" 
          subtitle={`${fileCount} archivos`}
          actions={
            <div className="scope-filter">
              <button
                className={`filter-btn ${filesScope === 'running' ? 'active' : ''}`}
                onClick={() => setFilesScope('running')}
              >
                Running
              </button>
              <button
                className={`filter-btn ${filesScope === 'finished' ? 'active' : ''}`}
                onClick={() => setFilesScope('finished')}
              >
                Finished
              </button>
              <button
                className={`filter-btn ${filesScope === 'all' ? 'active' : ''}`}
                onClick={() => setFilesScope('all')}
              >
                All
              </button>
            </div>
          }
        >
          <FileTree />
        </Panel>
      )}
      
      {/* File preview in right panel */}
      {selectedFilePath && (
        <FilePreview 
          path={selectedFilePath}
          content={previewContent}
          loading={previewLoading}
          error={previewError}
        />
      )}
    </div>
  );
}
