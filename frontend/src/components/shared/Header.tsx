import { useAuthStore } from '@/store';
import { useSSE } from '@/hooks/useSSE';
import './Header.css';

interface HeaderProps {
  title?: string;
  subtitle?: string;
}

export function Header({ 
  title = '🤖 Dev Squad', 
  subtitle = 'Equipo multiagente de programación — OpenClaw Portal' 
}: HeaderProps) {
  return (
    <div className="header">
      <div>
        <h2>{title}</h2>
        <div className="header-subtitle">{subtitle}</div>
      </div>
      <ConnectionStatus />
    </div>
  );
}

function ConnectionStatus() {
  const { connectionState, reconnectAttempt, maxReconnectAttempts } = useSSE({ enabled: false });
  const { isAuthenticated, isLoading } = useAuthStore();

  // Estados de conexión con iconos y colores
  const statusConfig = {
    connecting: {
      color: '#F5A623',
      bgColor: '#FFF8E6',
      text: 'Conectando...',
      icon: '⏳',
      showSpinner: true,
    },
    connected: {
      color: '#639922',
      bgColor: '#EAF3DE',
      text: 'Conectado',
      icon: '●',
      showSpinner: false,
    },
    reconnecting: {
      color: '#F5A623',
      bgColor: '#FFF8E6',
      text: `Reconectando ${reconnectAttempt}/${maxReconnectAttempts}...`,
      icon: '⟳',
      showSpinner: true,
    },
    disconnected: {
      color: '#E24B4A',
      bgColor: '#FCEBEB',
      text: 'Desconectado',
      icon: '○',
      showSpinner: false,
    },
  };

  // Mostrar estado de autenticación primero
  if (isLoading) {
    return (
      <div className="connection-status" style={{ background: '#F1EFE8' }}>
        <span className="connection-spinner" />
        <span className="connection-label">Verificando sesión...</span>
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <div className="connection-status" style={{ background: '#FCEBEB' }}>
        <span className="connection-dot" style={{ background: '#E24B4A' }} />
        <span className="connection-label">No autenticado</span>
      </div>
    );
  }

  const config = statusConfig[connectionState];

  return (
    <div 
      className="connection-status" 
      style={{ background: config.bgColor }}
      title={connectionState === 'reconnecting' ? `Intento ${reconnectAttempt} de ${maxReconnectAttempts}` : undefined}
    >
      {config.showSpinner ? (
        <span className="connection-spinner" style={{ borderColor: config.color }} />
      ) : (
        <span 
          className="connection-dot"
          style={{ 
            background: config.color,
            animation: connectionState === 'reconnecting' ? 'pulse 1s infinite' : undefined
          }}
        />
      )}
      <span className="connection-label" style={{ color: config.color }}>
        {config.icon} {config.text}
      </span>
      {connectionState === 'disconnected' && (
        <button 
          onClick={() => window.location.reload()} 
          className="connection-retry-btn"
        >
          Reconectar
        </button>
      )}
    </div>
  );
}
