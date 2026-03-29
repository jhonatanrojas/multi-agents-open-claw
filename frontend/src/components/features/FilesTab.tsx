import { useEffect } from 'react';
import { Panel } from '@/components/shared';
import { FileTree } from './files/FileTree';
import { FilePreview } from './FilePreview';
import { useFilesStore, useUIStore } from '@/store';
import { fetchFiles } from '@/api/client';
import './FilesTab.css';

export function FilesTab() {
  const snapshot = useFilesStore((s) => s.snapshot);
  const previewContent = useFilesStore((s) => s.previewContent);
  const previewLoading = useFilesStore((s) => s.previewLoading);
  const previewError = useFilesStore((s) => s.previewError);
  const selectedFilePath = useUIStore((s) => s.selectedFilePath);
  const setFilesScope = useUIStore((s) => s.setFilesScope);
  const filesScope = useUIStore((s) => s.filesScope);
  
  // Fetch files on mount
  useEffect(() => {
    fetchFiles().then((snapshot) => {
      useFilesStore.getState().setSnapshot(snapshot);
    }).catch((e) => {
      useFilesStore.getState().setError(String(e));
    });
  }, []);
  
  // Count files
  const fileCount = (snapshot?.files_produced?.length || 0) + 
                    (snapshot?.progress_files?.length || 0);
  
  return (
    <div className="files-tab">
      {/* File tree */}
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
