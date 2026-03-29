import { useState } from 'react';

interface Orchestrator {
  id: string;
  name: string;
  status: string;
  started_at: string;
  tasks: number;
}

interface RuntimePanelProps {
  orchestrators?: Orchestrator[];
  onCleanup?: () => void;
}

export function RuntimePanel({ orchestrators = [], onCleanup }: RuntimePanelProps) {
  const [cleaning, setCleaning] = useState(false);

  const handleCleanup = async () => {
    setCleaning(true);
    try {
      onCleanup?.();
    } finally {
      setCleaning(false);
    }
  };

  if (orchestrators.length === 0) {
    return (
      <div
        className="runtime-panel"
        style={{
          padding: '16px',
          backgroundColor: '#1e1e2e',
          borderRadius: '8px',
          textAlign: 'center',
        }}
      >
        <span style={{ fontSize: '2rem' }}>⚙️</span>
        <p style={{ margin: '8px 0 0 0', color: '#666', fontSize: '0.85rem' }}>
          Sin procesos de runtime activos
        </p>
      </div>
    );
  }

  return (
    <div
      className="runtime-panel"
      style={{
        backgroundColor: '#1e1e2e',
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
          padding: '12px 16px',
          backgroundColor: '#252536',
          borderBottom: '1px solid #333',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ fontSize: '0.9rem' }}>⚙️</span>
          <span style={{ fontWeight: 600, fontSize: '0.85rem', color: '#ddd' }}>
            Runtime Orchestrators
          </span>
        </div>
        <span
          style={{
            padding: '2px 8px',
            fontSize: '0.7rem',
            backgroundColor: '#3a3a5a',
            borderRadius: '10px',
            color: '#888',
          }}
        >
          {orchestrators.length}
        </span>
      </div>

      {/* List */}
      <div style={{ padding: '8px' }}>
        {orchestrators.map((orch) => (
          <div
            key={orch.id}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
              padding: '10px 12px',
              backgroundColor: '#252536',
              borderRadius: '6px',
              marginBottom: '6px',
            }}
          >
            <div
              style={{
                width: '8px',
                height: '8px',
                borderRadius: '50%',
                backgroundColor:
                  orch.status === 'running'
                    ? '#639922'
                    : orch.status === 'error'
                    ? '#e24b4a'
                    : '#888',
              }}
            />
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: '0.85rem', color: '#ddd', fontWeight: 500 }}>
                {orch.name}
              </div>
              <div style={{ fontSize: '0.7rem', color: '#666' }}>
                {orch.tasks} tareas · Iniciado {new Date(orch.started_at).toLocaleTimeString()}
              </div>
            </div>
            <span
              style={{
                fontSize: '0.7rem',
                padding: '2px 8px',
                borderRadius: '4px',
                backgroundColor:
                  orch.status === 'running' ? '#2a4a3a' : '#4a3a2a',
                color: orch.status === 'running' ? '#8dc' : '#da8',
              }}
            >
              {orch.status}
            </span>
          </div>
        ))}
      </div>

      {/* Cleanup button */}
      {orchestrators.length > 0 && (
        <div style={{ padding: '12px', borderTop: '1px solid #333' }}>
          <button
            onClick={handleCleanup}
            disabled={cleaning}
            style={{
              width: '100%',
              padding: '8px',
              fontSize: '0.8rem',
              backgroundColor: cleaning ? '#3a3a5a' : '#4a3a3a',
              color: cleaning ? '#888' : '#da8',
              border: 'none',
              borderRadius: '6px',
              cursor: cleaning ? 'not-allowed' : 'pointer',
            }}
          >
            {cleaning ? 'Limpiando...' : '🧹 Limpiar duplicados'}
          </button>
        </div>
      )}
    </div>
  );
}
