import { useMemoryStore } from '@/store';
import './Header.css';

interface HeaderProps {
  title?: string;
  subtitle?: string;
}

export function Header({ 
  title = '🤖 Dev Squad', 
  subtitle = 'Equipo multiagente de programación — OpenClaw Portal' 
}: HeaderProps) {
  const isConnected = useMemoryStore((state) => state.isConnected);
  
  return (
    <div className="header">
      <div>
        <h2>{title}</h2>
        <div className="header-subtitle">{subtitle}</div>
      </div>
      <ConnectionStatus connected={isConnected} />
    </div>
  );
}

function ConnectionStatus({ connected }: { connected: boolean }) {
  return (
    <div className="connection-status">
      <span 
        className="connection-dot"
        style={{ background: connected ? '#639922' : '#e24b4a' }}
      />
      <span className="connection-label">
        {connected ? 'Conectado' : 'Desconectado'}
      </span>
    </div>
  );
}