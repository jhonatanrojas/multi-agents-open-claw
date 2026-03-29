interface FilePreviewProps {
  path: string;
  content?: string | null;
  loading?: boolean;
  error?: string | null;
  onClose?: () => void;
}

export function FilePreview({ path, content, loading = false, error, onClose }: FilePreviewProps) {
  const filename = path.split('/').pop() || path;

  const getLanguageClass = () => {
    const ext = filename.split('.').pop()?.toLowerCase();
    const langMap: Record<string, string> = {
      ts: 'language-typescript', tsx: 'language-typescript',
      js: 'language-javascript', jsx: 'language-javascript',
      vue: 'language-html', php: 'language-php',
      py: 'language-python', rb: 'language-ruby',
      md: 'language-markdown', json: 'language-json',
      css: 'language-css', scss: 'language-scss',
      html: 'language-html', yaml: 'language-yaml',
      yml: 'language-yaml', sql: 'language-sql',
    };
    return langMap[ext || ''] || 'language-text';
  };

  if (!path) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          height: '200px',
          backgroundColor: '#1a1a2e',
          borderRadius: '8px',
          color: '#666',
          fontSize: '0.9rem',
        }}
      >
        Selecciona un archivo para ver su contenido
      </div>
    );
  }

  return (
    <div
      className="file-preview"
      style={{
        backgroundColor: '#1a1a2e',
        borderRadius: '8px',
        overflow: 'hidden',
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '8px 12px',
          backgroundColor: '#252538',
          borderBottom: '1px solid #333',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ fontSize: '0.8rem', color: '#888' }}>📄</span>
          <span style={{ fontSize: '0.85rem', color: '#ccc', fontWeight: 500 }}>
            {filename}
          </span>
        </div>
        {onClose && (
          <button
            onClick={onClose}
            style={{
              padding: '4px 8px',
              fontSize: '0.75rem',
              backgroundColor: 'transparent',
              color: '#888',
              border: '1px solid #444',
              borderRadius: '4px',
              cursor: 'pointer',
            }}
          >
            ✕
          </button>
        )}
      </div>

      {/* Content */}
      <div style={{ maxHeight: '400px', overflow: 'auto' }}>
        {loading ? (
          <div
            style={{
              padding: '24px',
              textAlign: 'center',
              color: '#888',
            }}
          >
            Cargando...
          </div>
        ) : error ? (
          <div
            style={{
              padding: '24px',
              textAlign: 'center',
              color: '#e55',
            }}
          >
            Error: {error}
          </div>
        ) : content ? (
          <pre
            className={getLanguageClass()}
            style={{
              margin: 0,
              padding: '12px 16px',
              fontSize: '0.8rem',
              lineHeight: 1.5,
              color: '#d4d4d4',
              backgroundColor: 'transparent',
              overflowX: 'auto',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-all',
            }}
          >
            {content}
          </pre>
        ) : (
          <div
            style={{
              padding: '24px',
              textAlign: 'center',
              color: '#666',
            }}
          >
            Sin contenido
          </div>
        )}
      </div>
    </div>
  );
}
