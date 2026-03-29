import { useState } from 'react';

interface StartProjectFormProps {
  onSubmit: (data: {
    brief: string;
    repo_url?: string;
    repo_name?: string;
    branch?: string;
    allow_init?: boolean;
  }) => void;
  loading?: boolean;
}

export function StartProjectForm({ onSubmit, loading = false }: StartProjectFormProps) {
  const [brief, setBrief] = useState('');
  const [repoUrl, setRepoUrl] = useState('');
  const [repoName, setRepoName] = useState('');
  const [branch, setBranch] = useState('main');
  const [allowInit, setAllowInit] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!brief.trim()) return;
    
    onSubmit({
      brief: brief.trim(),
      repo_url: repoUrl.trim() || undefined,
      repo_name: repoName.trim() || undefined,
      branch: branch.trim() || undefined,
      allow_init: allowInit,
    });
  };

  return (
    <form
      onSubmit={handleSubmit}
      style={{
        backgroundColor: '#1e1e2e',
        borderRadius: '12px',
        padding: '20px',
      }}
    >
      <h3
        style={{
          margin: '0 0 16px 0',
          fontSize: '1rem',
          fontWeight: 600,
          color: '#ddd',
        }}
      >
        🚀 Nuevo Proyecto
      </h3>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
        {/* Brief */}
        <div>
          <label
            style={{
              display: 'block',
              fontSize: '0.8rem',
              color: '#888',
              marginBottom: '4px',
            }}
          >
            Descripción del proyecto *
          </label>
          <textarea
            value={brief}
            onChange={(e) => setBrief(e.target.value)}
            placeholder="Ej: Crear una API REST para gestión de usuarios con autenticación JWT..."
            rows={3}
            required
            style={{
              width: '100%',
              padding: '10px',
              fontSize: '0.85rem',
              backgroundColor: '#252536',
              color: '#ddd',
              border: '1px solid #3a3a5a',
              borderRadius: '6px',
              resize: 'vertical',
              fontFamily: 'inherit',
              boxSizing: 'border-box',
            }}
          />
        </div>

        {/* Repo URL */}
        <div>
          <label
            style={{
              display: 'block',
              fontSize: '0.8rem',
              color: '#888',
              marginBottom: '4px',
            }}
          >
            URL del repositorio
          </label>
          <input
            type="url"
            value={repoUrl}
            onChange={(e) => setRepoUrl(e.target.value)}
            placeholder="https://github.com/user/repo"
            style={{
              width: '100%',
              padding: '10px',
              fontSize: '0.85rem',
              backgroundColor: '#252536',
              color: '#ddd',
              border: '1px solid #3a3a5a',
              borderRadius: '6px',
              boxSizing: 'border-box',
            }}
          />
        </div>

        {/* Repo Name & Branch */}
        <div style={{ display: 'flex', gap: '12px' }}>
          <div style={{ flex: 1 }}>
            <label
              style={{
                display: 'block',
                fontSize: '0.8rem',
                color: '#888',
                marginBottom: '4px',
              }}
            >
              Nombre del repo
            </label>
            <input
              type="text"
              value={repoName}
              onChange={(e) => setRepoName(e.target.value)}
              placeholder="mi-proyecto"
              style={{
                width: '100%',
                padding: '10px',
                fontSize: '0.85rem',
                backgroundColor: '#252536',
                color: '#ddd',
                border: '1px solid #3a3a5a',
                borderRadius: '6px',
                boxSizing: 'border-box',
              }}
            />
          </div>
          <div style={{ flex: 1 }}>
            <label
              style={{
                display: 'block',
                fontSize: '0.8rem',
                color: '#888',
                marginBottom: '4px',
              }}
            >
              Rama
            </label>
            <input
              type="text"
              value={branch}
              onChange={(e) => setBranch(e.target.value)}
              placeholder="main"
              style={{
                width: '100%',
                padding: '10px',
                fontSize: '0.85rem',
                backgroundColor: '#252536',
                color: '#ddd',
                border: '1px solid #3a3a5a',
                borderRadius: '6px',
                boxSizing: 'border-box',
              }}
            />
          </div>
        </div>

        {/* Allow Init */}
        <label
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            fontSize: '0.85rem',
            color: '#aaa',
            cursor: 'pointer',
          }}
        >
          <input
            type="checkbox"
            checked={allowInit}
            onChange={(e) => setAllowInit(e.target.checked)}
            style={{ width: '16px', height: '16px' }}
          />
          Permitir inicializar repositorio
        </label>

        {/* Submit */}
        <button
          type="submit"
          disabled={loading || !brief.trim()}
          style={{
            padding: '12px',
            fontSize: '0.9rem',
            fontWeight: 600,
            backgroundColor: loading ? '#3a3a5a' : '#4a3a8a',
            color: loading ? '#888' : '#fff',
            border: 'none',
            borderRadius: '8px',
            cursor: loading ? 'not-allowed' : 'pointer',
            transition: 'background-color 0.2s',
          }}
        >
          {loading ? 'Desplegando...' : '🚀 Desplegar proyecto'}
        </button>
      </div>
    </form>
  );
}
