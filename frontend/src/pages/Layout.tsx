import { Outlet } from 'react-router-dom';
import { Header } from '@/components/shared';
import { LoginForm } from '@/components/auth';
import { useDevSquadInit, useAuth } from '@/hooks';
import './Layout.css';

export function Layout() {
  // Auth check
  const { isAuthenticated, isLoading: authLoading } = useAuth();
  
  // Initialize all data sources (only when authenticated)
  const { isConnected, gatewayConnected } = useDevSquadInit();
  
  // Show loading while checking session
  if (authLoading) {
    return (
      <div className="layout layout--loading">
        <div className="auth-loading">
          <div className="spinner-large"></div>
          <p>Checking authentication...</p>
        </div>
      </div>
    );
  }
  
  // Show login if not authenticated
  if (!isAuthenticated) {
    return <LoginForm />;
  }
  
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