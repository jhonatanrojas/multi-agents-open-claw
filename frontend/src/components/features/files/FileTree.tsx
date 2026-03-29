import { useState, useMemo, useEffect, useRef } from 'react';
import { useFilesStore, useUIStore } from '@/store';
import { fetchFileView } from '@/api/client';
import './FileTree.css';

interface TreeNode {
  name: string;
  path: string;
  type: 'file' | 'directory';
  children?: TreeNode[];
  extension?: string;
  agent?: string;
  lastModified?: string;
  isNew?: boolean;
}

const EXT_ICONS: Record<string, string> = {
  py: '.py', ts: '.ts', tsx: '.tsx', js: '.js', jsx: '.jsx',
  md: '.md', json: '.json', css: '.css', html: '.html', yml: '.yml',
  yaml: '.yaml', txt: '.txt', sh: '.sh', bash: '.sh',
};

function getFileIcon(filename: string): string {
  const ext = filename.split('.').pop()?.toLowerCase() || '';
  return EXT_ICONS[ext] || '.' + ext;
}

function buildTree(files: Array<{ path: string; group?: string; agent?: string; last_modified?: string }>): TreeNode[] {
  const root: TreeNode[] = [];
  const dirs = new Map<string, TreeNode>();
  
  for (const file of files) {
    const parts = file.path.split('/');
    let currentLevel = root;
    let currentPath = '';
    
    for (let i = 0; i < parts.length; i++) {
      const part = parts[i];
      const isFile = i === parts.length - 1;
      currentPath = currentPath ? `${currentPath}/${part}` : part;
      
      if (isFile) {
        const ext = part.split('.').pop()?.toLowerCase() || '';
        currentLevel.push({
          name: part,
          path: file.path,
          type: 'file',
          extension: ext,
          agent: file.agent,
          lastModified: file.last_modified,
        });
      } else {
        if (!dirs.has(currentPath)) {
          const node: TreeNode = {
            name: part,
            path: currentPath,
            type: 'directory',
            children: [],
          };
          dirs.set(currentPath, node);
          currentLevel.push(node);
        }
        currentLevel = dirs.get(currentPath)!.children!;
      }
    }
  }
  
  // Sort: directories first, then files
  const sortNodes = (nodes: TreeNode[]) => {
    nodes.sort((a, b) => {
      if (a.type !== b.type) return a.type === 'directory' ? -1 : 1;
      return a.name.localeCompare(b.name);
    });
    for (const node of nodes) {
      if (node.children) sortNodes(node.children);
    }
  };
  sortTree(root);
  
  return root;
}

function sortTree(nodes: TreeNode[]) {
  nodes.sort((a, b) => {
    if (a.type !== b.type) return a.type === 'directory' ? -1 : 1;
    return a.name.localeCompare(b.name);
  });
  for (const n of nodes) {
    if (n.children) sortTree(n.children);
  }
}

interface TreeNodeProps {
  node: TreeNode;
  depth: number;
  defaultExpanded?: boolean;
}

function TreeNode({ node, depth, defaultExpanded = false }: TreeNodeProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const [isNew, setIsNew] = useState(node.isNew);
  const nodeRef = useRef<HTMLDivElement>(null);
  
  const setSelectedFilePath = useUIStore((s) => s.setSelectedFilePath);
  const selectedPath = useUIStore((s) => s.selectedFilePath);
  
  useEffect(() => {
    if (isNew) {
      const timer = setTimeout(() => setIsNew(false), 1500);
      return () => clearTimeout(timer);
    }
  }, [isNew]);
  
  const handleClick = () => {
    if (node.type === 'directory') {
      setExpanded(!expanded);
    } else {
      setSelectedFilePath(node.path);
      // Fetch file content for preview
      useFilesStore.getState().setPreviewLoading(true);
      fetchFileView(node.path).then((res) => {
        useFilesStore.getState().setPreviewContent(res.file?.content || '');
        useFilesStore.getState().setPreviewLoading(false);
      }).catch(() => {
        useFilesStore.getState().setPreviewContent(`Error loading ${node.path}`);
        useFilesStore.getState().setPreviewLoading(false);
      });
    }
  };
  
  return (
    <div className="tree-node" ref={nodeRef}>
      <div
        className={`tree-item ${node.type} ${selectedPath === node.path ? 'selected' : ''} ${isNew ? 'new-file' : ''}`}
        style={{ paddingLeft: `${depth * 16 + 8}px` }}
        onClick={handleClick}
      >
        {node.type === 'directory' ? (
          <>
            <span className={`tree-arrow ${expanded ? 'expanded' : ''}`}>▶</span>
            <span className="tree-icon">📁</span>
          </>
        ) : (
          <>
            <span className="tree-spacer" />
            <span className="tree-icon file-icon">{getFileIcon(node.name)}</span>
          </>
        )}
        <span className="tree-name">{node.name}</span>
        {node.agent && (
          <span className="tree-agent">{node.agent}</span>
        )}
      </div>
      
      {node.type === 'directory' && expanded && node.children && (
        <div className="tree-children">
          {node.children.map((child, i) => (
            <TreeNode key={i} node={child} depth={depth + 1} defaultExpanded={depth < 1} />
          ))}
        </div>
      )}
    </div>
  );
}

export function FileTree() {
  const snapshot = useFilesStore((s) => s.snapshot);
  const isLoading = useFilesStore((s) => s.isLoading);
  
  // Get all files from snapshot
  const allFiles = useMemo(() => {
    const files: Array<{ path: string; group?: string; agent?: string; last_modified?: string }> = [];
    
    // Add snapshot files if available
    if (snapshot?.files_produced) {
      for (const f of snapshot.files_produced) {
        files.push({ path: f });
      }
    }
    
    if (snapshot?.progress_files) {
      for (const f of snapshot.progress_files) {
        if (!files.some((x) => x.path === f)) {
          files.push({ path: f });
        }
      }
    }
    
    return files;
  }, [snapshot]);
  
  // Build tree
  const tree = useMemo(() => buildTree(allFiles), [allFiles]);
  
  if (isLoading) {
    return <div className="file-tree-loading">Cargando archivos...</div>;
  }
  
  if (allFiles.length === 0) {
    return (
      <div className="file-tree-empty">
        <p>No hay archivos producidos</p>
        <small>Los archivos aparecerán aquí cuando los agentes los creen</small>
      </div>
    );
  }
  
  return (
    <div className="file-tree">
      <div className="file-tree-header">
        <span className="file-count">{allFiles.length} archivos</span>
      </div>
      <div className="file-tree-content">
        {tree.map((node, i) => (
          <TreeNode key={i} node={node} depth={0} defaultExpanded={true} />
        ))}
      </div>
    </div>
  );
}
