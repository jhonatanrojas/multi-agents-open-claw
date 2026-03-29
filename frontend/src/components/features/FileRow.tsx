interface FileRowProps {
  path: string;
  onView?: (path: string) => void;
  onDownload?: (path: string) => void;
  isSelected?: boolean;
}

export function FileRow({ path, onView, onDownload, isSelected = false }: FileRowProps) {
  const filename = path.split('/').pop() || path;
  const ext = filename.split('.').pop() || '';
  
  const getExtIcon = () => {
    const icons: Record<string, string> = {
      ts: '🔷', tsx: '⚛️', js: '🟨', jsx: '⚡',
      vue: '💚', php: '🐘', py: '🐍', rb: '💎',
      md: '📝', json: '📋', css: '🎨', scss: '🎨',
      html: '🌐', yaml: '⚙️', yml: '⚙️', xml: '📄',
      txt: '📄', env: '🔐', sql: '🗃️',
    };
    return icons[ext] || '📄';
  };

  const handleView = () => onView?.(path);
  const handleDownload = () => onDownload?.(path);

  return (
    <div
      className="file-row"
      onClick={handleView}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        padding: '8px 12px',
        backgroundColor: isSelected ? '#2a2a4a' : 'transparent',
        borderRadius: '4px',
        cursor: 'pointer',
        transition: 'background-color 0.15s',
      }}
      onMouseEnter={(e) => {
        if (!isSelected) e.currentTarget.style.backgroundColor = '#252540';
      }}
      onMouseLeave={(e) => {
        if (!isSelected) e.currentTarget.style.backgroundColor = 'transparent';
      }}
    >
      <span style={{ fontSize: '0.9rem' }}>{getExtIcon()}</span>
      <span
        style={{
          flex: 1,
          fontSize: '0.85rem',
          color: '#ccc',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}
        title={path}
      >
        {filename}
      </span>
      <div style={{ display: 'flex', gap: '4px' }}>
        <button
          onClick={(e) => { e.stopPropagation(); handleView(); }}
          style={{
            padding: '2px 8px',
            fontSize: '0.7rem',
            backgroundColor: '#3a3a5a',
            color: '#aaa',
            border: 'none',
            borderRadius: '4px',
            cursor: 'pointer',
          }}
        >
          Ver
        </button>
        <button
          onClick={(e) => { e.stopPropagation(); handleDownload(); }}
          style={{
            padding: '2px 8px',
            fontSize: '0.7rem',
            backgroundColor: '#2a4a3a',
            color: '#8dc',
            border: 'none',
            borderRadius: '4px',
            cursor: 'pointer',
          }}
        >
          ↓
        </button>
      </div>
    </div>
  );
}
