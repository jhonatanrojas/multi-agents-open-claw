import type { ReactNode } from 'react';
import './Panel.css';

interface PanelProps {
  children: ReactNode;
  title?: string;
  subtitle?: string;
  className?: string;
  actions?: ReactNode;
}

export function Panel({ children, title, subtitle, className = '', actions }: PanelProps) {
  return (
    <div className={`panel ${className}`}>
      {(title || actions) && (
        <div className="panel-header">
          <div>
            {title && <div className="panel-title">{title}</div>}
            {subtitle && <div className="panel-subtitle">{subtitle}</div>}
          </div>
          {actions && <div className="panel-actions">{actions}</div>}
        </div>
      )}
      <div className="panel-content">
        {children}
      </div>
    </div>
  );
}

// Section label helper
export function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <div className="section-label">{children}</div>
  );
}

// Empty state helper
interface EmptyStateProps {
  children?: ReactNode;
  message?: string;
  icon?: string;
}

export function EmptyState({ children, message, icon = '📭' }: EmptyStateProps) {
  return (
    <div className="empty-state">
      {icon && <span style={{ fontSize: '2.5rem', opacity: 0.5 }}>{icon}</span>}
      {message && <p style={{ margin: '8px 0 0 0', fontSize: '0.9rem', color: '#888', maxWidth: '280px', textAlign: 'center' as const }}>{message}</p>}
      {children}
    </div>
  );
}