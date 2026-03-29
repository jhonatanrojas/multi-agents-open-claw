import type { ReactNode } from 'react';
import './Badge.css';

interface BadgeProps {
  children: ReactNode;
  variant?: 'default' | 'success' | 'warning' | 'error' | 'info';
  style?: React.CSSProperties;
  className?: string;
}

const variantStyles: Record<string, React.CSSProperties> = {
  default: { background: '#F1EFE8', color: '#5F5E5A' },
  success: { background: '#EAF3DE', color: '#3B6D11' },
  warning: { background: '#FFF2D8', color: '#9A5B00' },
  error: { background: '#FCEBEB', color: '#791F1F' },
  info: { background: '#EEEDFE', color: '#3C3489' },
};

export function Badge({ 
  children, 
  variant = 'default', 
  style,
  className = '' 
}: BadgeProps) {
  return (
    <span 
      className={`badge ${className}`}
      style={{ ...variantStyles[variant], ...style }}
    >
      {children}
    </span>
  );
}

// Status badge with dot indicator
interface StatusBadgeProps {
  status: string;
  showDot?: boolean;
}

export function StatusBadge({ status, showDot = true }: StatusBadgeProps) {
  const statusColors: Record<string, { bg: string; text: string; dot: string }> = {
    working: { bg: '#EAF3DE', text: '#3B6D11', dot: '#639922' },
    thinking: { bg: '#EEEDFE', text: '#3C3489', dot: '#7F77DD' },
    speaking: { bg: '#E1F5EE', text: '#0F6E56', dot: '#1D9E75' },
    idle: { bg: '#F1EFE8', text: '#5F5E5A', dot: '#888780' },
    error: { bg: '#FCEBEB', text: '#791F1F', dot: '#E24B4A' },
    offline: { bg: '#F1EFE8', text: '#888780', dot: '#B4B2A9' },
    delivered: { bg: '#EAF3DE', text: '#3B6D11', dot: '#639922' },
    planned: { bg: '#EEEDFE', text: '#3C3489', dot: '#7F77DD' },
    blocked: { bg: '#FFF2D8', text: '#9A5B00', dot: '#D48A00' },
    paused: { bg: '#FFF2D8', text: '#9A5B00', dot: '#D48A00' },
    sleeping: { bg: '#F1EFE8', text: '#5F5E5A', dot: '#B4B2A9' },
    pending: { bg: '#F1EFE8', text: '#5F5E5A', dot: '#888780' },
    in_progress: { bg: '#EEEDFE', text: '#3C3489', dot: '#7F77DD' },
    done: { bg: '#EAF3DE', text: '#3B6D11', dot: '#639922' },
  };
  
  const colors = statusColors[status] || statusColors.idle;
  const label = translateStatus(status);
  
  return (
    <span 
      className="badge"
      style={{ background: colors.bg, color: colors.text }}
    >
      {showDot && (
        <span 
          className="badge-dot"
          style={{ background: colors.dot }}
        />
      )}
      {label}
    </span>
  );
}

// Spanish status translations
function translateStatus(status: string): string {
  const translations: Record<string, string> = {
    idle: 'inactivo',
    running: 'en ejecución',
    working: 'trabajando',
    thinking: 'pensando',
    speaking: 'hablando',
    error: 'error',
    offline: 'desconectado',
    delivered: 'entregado',
    planned: 'planificado',
    blocked: 'bloqueado',
    paused: 'pausado',
    sleeping: 'durmiendo',
    pending: 'pendiente',
    in_progress: 'en progreso',
    done: 'completado',
  };
  return translations[status] || status;
}