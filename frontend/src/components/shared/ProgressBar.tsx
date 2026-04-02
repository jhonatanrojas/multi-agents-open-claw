import './ProgressBar.css';

interface ProgressBarProps {
  value: number; // 0-100
  color?: string;
  showLabel?: boolean;
  size?: 'sm' | 'md';
}

export function ProgressBar({ 
  value, 
  color = '#7F77DD',
  showLabel = true,
  size = 'md'
}: ProgressBarProps) {
  const clampedValue = Math.max(0, Math.min(100, value));
  
  return (
    <div className={`progress-container ${size}`}>
      {showLabel && (
        <div className="progress-header">
          <span className="progress-label">Progreso general</span>
          <span className="progress-value">{clampedValue}%</span>
        </div>
      )}
      <div className="progress-track">
        <div 
          className="progress-fill"
          style={{ 
            width: `${clampedValue}%`,
            background: clampedValue === 100 ? '#639922' : color
          }}
        />
      </div>
    </div>
  );
}

// Phase timeline component
interface PhaseProgressProps {
  phases: Array<{
    id: string;
    name: string;
    completed: number;
    total: number;
    active?: boolean;
  }>;
}

export function PhaseProgress({ phases }: PhaseProgressProps) {
  return (
    <div className="phases-timeline">
      {phases.map((phase) => {
        const pct = phase.total > 0 
          ? Math.round((phase.completed / phase.total) * 100) 
          : 0;
        const fillColor = phase.completed === phase.total && phase.total > 0
          ? '#639922'
          : phase.active
            ? '#7F77DD'
            : '#B4B2A9';
        
        return (
          <div key={phase.id} className="phase-item">
            <div 
              className="phase-name"
              style={{ 
                color: phase.active ? '#7F77DD' : 'var(--text-secondary)',
                fontWeight: phase.active ? 500 : 400
              }}
            >
              {phase.name}
            </div>
            <div className="phase-bar">
              <div 
                className="phase-fill"
                style={{ width: `${pct}%`, background: fillColor }}
              />
            </div>
            <div className="phase-count">
              {phase.completed}/{phase.total}
            </div>
          </div>
        );
      })}
    </div>
  );
}