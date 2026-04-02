import { useState, useEffect, useCallback, useRef } from 'react';
import { Outlet, Navigate } from 'react-router-dom';
import { Header } from '@/components/shared';
import { QuickActions, FilePreview, GatewayChatCard } from '@/components/features';
import { useDevSquadInit } from '@/hooks';
import { useUIStore, useGatewayStore, useFilesStore, selectAllChats, useAuthStore } from '@/store';
import './ThreePanelLayout.css';

const STORAGE_KEY_LEFT = 'devsquad:left-panel-collapsed';
const STORAGE_KEY_RIGHT = 'devsquad:right-panel-width';

const TAB_SHORTCUTS: Record<string, string> = {
  '1': 'tasks',
  '2': 'projects',
  '3': 'models',
  '4': 'gateway',
  '5': 'files',
  '6': 'log',
  '7': 'miniverse',
};

export function ThreePanelLayout() {
  // =====================
  // ALL HOOKS MUST BE CALLED BEFORE ANY CONDITIONAL RETURNS
  // =====================
  
  // Auth state
  const { isAuthenticated, sessionChecked, checkSession } = useAuthStore();
  
  // Initialize data sources (always call, even if redirecting)
  const { isConnected, gatewayConnected } = useDevSquadInit();
  
  // Stores
  const activeTab = useUIStore((state) => state.activeTab);
  const setActiveTab = useUIStore((state) => state.setActiveTab);
  const selectedFilePath = useUIStore((state) => state.selectedFilePath);
  const selectedPreview = useFilesStore((state) => state.previewContent);
  const gatewayState = useGatewayStore();
  const chatEvents = selectAllChats(gatewayState);
  
  // Local state
  const [leftCollapsed, setLeftCollapsed] = useState(() => {
    if (typeof window === 'undefined') return false;
    return localStorage.getItem(STORAGE_KEY_LEFT) === 'true';
  });
  
  const [rightWidth, setRightWidth] = useState(() => {
    if (typeof window === 'undefined') return 360;
    const saved = localStorage.getItem(STORAGE_KEY_RIGHT);
    return saved ? parseInt(saved, 10) : 360;
  });
  
  const isResizing = useRef(false);
  const containerRef = useRef<HTMLDivElement>(null);
  
  // Check session on mount
  useEffect(() => {
    if (!sessionChecked) {
      checkSession();
    }
  }, [sessionChecked, checkSession]);
  
  // Persist left panel state
  useEffect(() => {
    localStorage.setItem(STORAGE_KEY_LEFT, String(leftCollapsed));
  }, [leftCollapsed]);
  
  // Persist right panel width
  useEffect(() => {
    localStorage.setItem(STORAGE_KEY_RIGHT, String(rightWidth));
  }, [rightWidth]);
  
  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Don't trigger if typing in input/textarea
      if (e.target instanceof HTMLInputElement || 
          e.target instanceof HTMLTextAreaElement ||
          e.target instanceof HTMLSelectElement) {
        return;
      }
      
      const tab = TAB_SHORTCUTS[e.key];
      if (tab) {
        e.preventDefault();
        setActiveTab(tab as typeof activeTab);
      }
    };
    
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [setActiveTab, activeTab]);
  
  // Right panel resize handlers
  const handleMouseDown = useCallback(() => {
    isResizing.current = true;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  }, []);
  
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isResizing.current || !containerRef.current) return;
      
      const containerRect = containerRef.current.getBoundingClientRect();
      const newWidth = containerRect.right - e.clientX;
      
      // Clamp between 240 and 480
      if (newWidth >= 240 && newWidth <= 480) {
        setRightWidth(newWidth);
      }
    };
    
    const handleMouseUp = () => {
      isResizing.current = false;
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
    
    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
    
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, []);
  
  // =====================
  // CONDITIONAL RETURNS (AFTER ALL HOOKS)
  // =====================
  
  // Redirect to login if not authenticated
  if (sessionChecked && !isAuthenticated) {
    const currentPath = typeof window !== 'undefined' ? window.location.pathname : '/';
    const isDevsquad = currentPath.startsWith('/devsquad');
    return <Navigate to={isDevsquad ? '/devsquad/login' : '/login'} replace />;
  }
  
  // Show loading while checking session
  if (!sessionChecked) {
    return (
      <div className="three-panel-layout loading">
        <div className="loading-spinner">
          <div className="spinner" />
          <p>Verificando sesión...</p>
        </div>
      </div>
    );
  }
  
  // =====================
  // RENDER
  // =====================
  
  const renderRightPanel = () => {
    switch (activeTab) {
      case 'files':
        return (
          <div className="right-panel-content">
            <div className="right-panel-header">
              <span>📄 Vista Previa</span>
            </div>
            <FilePreview 
              path={selectedFilePath || ''} 
              content={selectedPreview}
              loading={false}
            />
          </div>
        );
      
      case 'gateway':
        return (
          <div className="right-panel-content">
            <div className="right-panel-header">
              <span>💬 Chat Reciente</span>
            </div>
            <div className="gateway-chats">
              {chatEvents.slice(0, 6).map((event, i) => (
                <GatewayChatCard key={i} event={event} compact />
              ))}
            </div>
          </div>
        );
      
      case 'miniverse':
        return (
          <div className="right-panel-content">
            <div className="right-panel-header">
              <span>🌐 Miniverse</span>
            </div>
            <div className="miniverse-status">
              <p style={{ color: '#666', fontSize: '0.8rem', padding: '12px' }}>
                Abre el servidor Miniverse en otra pestaña para ver el mundo pixel.
              </p>
            </div>
          </div>
        );
      
      default:
        return (
          <div className="right-panel-content">
            <div className="right-panel-header">
              <span>💬 Actividad en vivo</span>
            </div>
            <div className="gateway-chats">
              {chatEvents.length === 0 ? (
                <div className="empty-hint">
                  <span>📡</span>
                  <p>Los mensajes de los agentes aparecerán aquí</p>
                </div>
              ) : (
                chatEvents.slice(0, 8).map((event, i) => (
                  <GatewayChatCard key={i} event={event} compact />
                ))
              )}
            </div>
          </div>
        );
    }
  };
  
  return (
    <div className="three-panel-layout" ref={containerRef}>
      {/* Header */}
      <header className="layout-header">
        <Header 
          title="🤖 Dev Squad"
          subtitle="Equipo multiagente de programación"
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
      </header>
      
      {/* Three-panel layout */}
      <div className="layout-body">
        {/* Left sidebar - Quick Actions */}
        <aside 
          className={`layout-sidebar layout-sidebar-left ${leftCollapsed ? 'collapsed' : ''}`}
        >
          {!leftCollapsed && <QuickActions />}
          
          {/* Collapse toggle */}
          <button 
            className="collapse-toggle left"
            onClick={() => setLeftCollapsed(!leftCollapsed)}
            title={leftCollapsed ? 'Expandir panel' : 'Colapsar panel'}
          >
            {leftCollapsed ? '→' : '←'}
          </button>
        </aside>
        
        {/* Main content */}
        <main className="layout-main">
          <Outlet />
        </main>
        
        {/* Resize handle */}
        <div 
          className="resize-handle"
          onMouseDown={handleMouseDown}
        />
        
        {/* Right sidebar */}
        <aside 
          className="layout-sidebar layout-sidebar-right"
          style={{ width: rightWidth }}
        >
          {renderRightPanel()}
        </aside>
      </div>
    </div>
  );
}