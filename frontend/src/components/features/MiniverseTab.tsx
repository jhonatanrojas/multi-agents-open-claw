import { useState, useEffect } from 'react';
import { fetchMiniverse } from '@/api/client';
import { useMiniverseStore } from '@/store';
import './MiniverseTab.css';

interface MiniverseTabProps {
  /** Altura del componente */
  height?: number;
}

export function MiniverseTab({ height = 500 }: MiniverseTabProps) {
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const snapshot = useMiniverseStore((s) => s.snapshot);
  const setSnapshot = useMiniverseStore((s) => s.setSnapshot);
  
  useEffect(() => {
    const loadSnapshot = async () => {
      setIsLoading(true);
      setError(null);
      
      try {
        const data = await fetchMiniverse();
        setSnapshot(data);
      } catch (e) {
        setError(String(e));
      } finally {
        setIsLoading(false);
      }
    };
    
    loadSnapshot();
  }, []);
  
  // Loading state
  if (isLoading) {
    return (
      <div className="miniverse-tab">
        <div className="miniverse-loading" style={{ height }}>
          <div className="spinner">🌐</div>
          <p>Cargando Miniverse...</p>
        </div>
      </div>
    );
  }
  
  // Error state
  if (error) {
    return (
      <div className="miniverse-tab">
        <div className="miniverse-disconnected" style={{ height }}>
          <div className="icon">⚠️</div>
          <h3>Error al cargar Miniverse</h3>
          <p>{error}</p>
          <button 
            className="retry-btn"
            onClick={() => {
              setIsLoading(true);
              setError(null);
              fetchMiniverse(true).then(setSnapshot).catch(e => setError(String(e))).finally(() => setIsLoading(false));
            }}
          >
            Reintentar
          </button>
        </div>
      </div>
    );
  }
  
  // Get world URL from snapshot
  const worldUrl = snapshot?.ui?.url || snapshot?.links?.world || snapshot?.world?.ui_url;
  const isEmbeddable = snapshot?.ui?.embeddable !== false;
  const worldInfo = snapshot?.world?.info || {};
  const agentsData = snapshot?.world?.agents || {};
  
  // Extract agent counts
  const onlineAgents = typeof agentsData === 'object' && agentsData !== null && 'online' in agentsData 
    ? Number((agentsData as Record<string, unknown>).online) || 0 
    : 0;
  const totalAgents = typeof agentsData === 'object' && agentsData !== null && 'total' in agentsData 
    ? Number((agentsData as Record<string, unknown>).total) || 0 
    : 0;
  const worldName = typeof worldInfo === 'object' && worldInfo !== null && 'world' in worldInfo 
    ? String((worldInfo as Record<string, unknown>).world) 
    : '';
  
  // Connected with iframe
  if (worldUrl && isEmbeddable) {
    return (
      <div className="miniverse-tab">
        <div className="miniverse-frame" style={{ height }}>
          <iframe
            src={worldUrl}
            title="Miniverse World"
            sandbox="allow-scripts allow-same-origin allow-forms"
          />
        </div>
        <div className="miniverse-info">
          <span className="dot connected">●</span>
          <span>Conectado a {worldUrl}</span>
          {worldName && (
            <>
              <span>|</span>
              <span>Mundo: {worldName}</span>
            </>
          )}
          {onlineAgents > 0 && (
            <>
              <span>|</span>
              <span>{onlineAgents}/{totalAgents} agentes</span>
            </>
          )}
        </div>
      </div>
    );
  }
  
  // Not embeddable or blocked
  const blockedBy = snapshot?.ui?.blocked_by || [];
  const message = blockedBy.length > 0 
    ? `El iframe está bloqueado por: ${blockedBy.join(', ')}` 
    : 'El servidor Miniverse no está disponible o no permite embedding.';
  
  return (
    <div className="miniverse-tab">
      <div className="miniverse-disconnected" style={{ height }}>
        <div className="icon">🌐</div>
        <h3>Miniverse no disponible</h3>
        <p>{message}</p>
        <code>MINIVERSE_URL=http://127.0.0.1:9999</code>
        <div className="docs-link">
          <a 
            href="https://www.minivrs.com/docs" 
            target="_blank" 
            rel="noopener noreferrer"
          >
            Ver documentación →
          </a>
        </div>
      </div>
    </div>
  );
}