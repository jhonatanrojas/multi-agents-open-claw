import { Outlet } from 'react-router-dom';
import { Header } from '@/components/shared';
import { useDevSquadInit } from '@/hooks';
import './Layout.css';

export function Layout() {
  // Initialize all data sources
  const { isConnected, gatewayConnected } = useDevSquadInit();
  
  return (
    <div className="layout">
      <Header 
        title="🤖 Dev Squad"
        subtitle="Equipo multiagente de programación — OpenClaw Portal"
      />
      
      {/* Connection indicators */}
      <div className="connection-bar">
        <div className="connection-item">
          <span 
            className="connection-dot"
            style={{ background: isConnected ? '#639922' : '#e24b4a' }}
          />
          <span>SSE {isConnected ? 'OK' : 'Offline'}</span>
        </div>
        <div className="connection-item">
          <span 
            className="connection-dot"
            style={{ background: gatewayConnected ? '#639922' : '#e24b4a' }}
          />
          <span>Gateway {gatewayConnected ? 'OK' : 'Offline'}</span>
        </div>
      </div>
      
      <main className="main-content">
        <Outlet />
      </main>
    </div>
  );
}