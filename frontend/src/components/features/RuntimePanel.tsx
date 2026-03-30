import { useMemo, type CSSProperties } from 'react';
import { useCleanupRuntime, useRuntime } from '@/api';
import type { RuntimeProcess } from '@/types';

function formatElapsed(seconds?: number): string {
  if (typeof seconds !== 'number' || Number.isNaN(seconds) || seconds < 0) {
    return '';
  }
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}m ${secs}s`;
}

function renderRoleLabel(role: RuntimeProcess['role']): string {
  switch (role) {
    case 'primary':
      return 'Primaria';
    case 'lock':
      return 'Lock';
    default:
      return 'Duplicada';
  }
}

function processBadgeColor(role: RuntimeProcess['role']): { bg: string; text: string } {
  switch (role) {
    case 'primary':
      return { bg: '#EAF3DE', text: '#3B6D11' };
    case 'lock':
      return { bg: '#EEEDFE', text: '#3C3489' };
    default:
      return { bg: '#FCEBEB', text: '#791F1F' };
  }
}

function pickCmdline(cmdline: string | unknown): string {
  if (typeof cmdline === 'string') return cmdline;
  if (Array.isArray(cmdline)) return cmdline.join(' ');
  return '';
}

function renderStatusLabel(status?: string): string {
  const normalized = String(status || '').trim().toLowerCase();
  switch (normalized) {
    case 'starting':
      return 'Iniciando';
    case 'executing':
    case 'running':
    case 'working':
      return 'En ejecución';
    case 'blocked':
      return 'Bloqueada';
    case 'paused':
      return 'Pausada';
    case 'planning':
      return 'Planificando';
    case 'review':
      return 'En revisión';
    case 'error':
      return 'Error';
    case 'idle':
      return 'Inactiva';
    default:
      return normalized ? normalized[0].toUpperCase() + normalized.slice(1) : 'Desconocido';
  }
}

function renderPhaseLabel(phase?: string): string {
  const normalized = String(phase || '').trim().toLowerCase();
  switch (normalized) {
    case 'planning':
      return 'Planificación';
    case 'execution':
      return 'Ejecución';
    case 'review':
      return 'Revisión';
    case 'paused':
      return 'Pausada';
    default:
      return normalized ? normalized[0].toUpperCase() + normalized.slice(1) : '';
  }
}

interface RuntimePanelProps {
  compact?: boolean;
}

export function RuntimePanel({ compact = false }: RuntimePanelProps) {
  const { data, isLoading, isError, error, refetch } = useRuntime();
  const cleanupMutation = useCleanupRuntime();
  const runtime = data?.runtime;
  const processes = runtime?.processes || [];
  const duplicates = runtime?.duplicates || [];
  const issues = runtime?.issues || [];
  const primaryPid = runtime?.primary_pid;
  const lockPid = runtime?.lockfile?.pid;
  const projectOrchestrator = runtime?.project_orchestrator;
  const cleanupAvailable = Boolean(runtime?.cleanup_available);

  const summary = useMemo(() => {
    return [
      `${processes.length} proceso${processes.length === 1 ? '' : 's'}`,
      `${duplicates.length} duplicada${duplicates.length === 1 ? '' : 's'}`,
      `PID lock ${lockPid ?? 'N/A'}`,
    ];
  }, [duplicates.length, lockPid, processes.length]);

  const handleCleanup = () => {
    cleanupMutation.mutate('duplicates', {
      onSuccess: () => {
        refetch();
      },
    });
  };

  const handleRefresh = () => {
    refetch();
  };

  if (isLoading) {
    return (
      <div className="runtime-panel" style={panelStyle}>
        <Header count={0} />
        <div className="empty" style={emptyStyle}>
          Cargando runtime...
        </div>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="runtime-panel" style={panelStyle}>
        <Header count={0} />
        <div className="empty" style={emptyStyle}>
          No se pudo cargar el runtime: {String(error)}
        </div>
      </div>
    );
  }

  const renderProcess = (proc: RuntimeProcess) => {
    const badge = processBadgeColor(proc.role);
    return (
      <div key={`${proc.pid}-${proc.role}`} style={processRowStyle}>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={processTitleStyle}>
            <span>P{proc.pid}</span>
            <span style={{ ...processBadgeStyle, background: badge.bg, color: badge.text }}>
              {renderRoleLabel(proc.role)}
            </span>
            {proc.is_lock_pid && <span style={tagStyle}>lockfile</span>}
            {proc.is_mem_pid && <span style={tagStyle}>MEMORY</span>}
          </div>
          <div style={processMetaStyle}>{pickCmdline(proc.cmdline)}</div>
        </div>
        {formatElapsed(proc.elapsed_sec) && (
          <span style={secondaryBadgeStyle}>{formatElapsed(proc.elapsed_sec)}</span>
        )}
      </div>
    );
  };

  const projectOrchestratorBadge = projectOrchestrator
    ? (() => {
        const status = String(projectOrchestrator.status || '').toLowerCase();
        switch (status) {
          case 'error':
            return { bg: '#FCEBEB', text: '#791F1F' };
          case 'blocked':
            return { bg: '#FFF5D8', text: '#845B00' };
          case 'paused':
            return { bg: '#EEEDFE', text: '#3C3489' };
          case 'planning':
          case 'starting':
            return { bg: '#EAF3DE', text: '#3B6D11' };
          case 'executing':
          case 'running':
          case 'working':
            return { bg: '#DFF3FF', text: '#0B5F8A' };
          default:
            return { bg: '#3a3a5a', text: '#ddd' };
        }
      })()
    : null;

  return (
    <div className="runtime-panel" style={panelStyle}>
      <div style={panelHeadStyle}>
        <div>
          <div style={sectionLabelStyle}>Ejecuciones</div>
          <div style={subtitleStyle}>
            Detecta el proceso primario, duplicados y locks obsoletos.
          </div>
        </div>
        <div style={summaryWrapStyle}>
          {summary.map((item) => (
            <span key={item} style={summaryBadgeStyle}>
              {item}
            </span>
          ))}
          <span style={summaryBadgeStyle}>Primary PID {primaryPid ?? 'N/A'}</span>
        </div>
      </div>

      {projectOrchestrator && (
        <div style={activeExecutionStyle}>
          <div style={sectionLabelStyle}>Ejecución activa</div>
          <div style={processTitleStyle}>
            <span>{projectOrchestrator.pid ? `P${projectOrchestrator.pid}` : 'PID N/A'}</span>
            <span
              style={{
                ...processBadgeStyle,
                background: projectOrchestratorBadge?.bg,
                color: projectOrchestratorBadge?.text,
              }}
            >
              {renderStatusLabel(projectOrchestrator.status)}
            </span>
            {projectOrchestrator.phase && <span style={tagStyle}>{renderPhaseLabel(projectOrchestrator.phase)}</span>}
            {projectOrchestrator.task_id && <span style={tagStyle}>{projectOrchestrator.task_id}</span>}
          </div>
          <div style={processMetaStyle}>
            {projectOrchestrator.detail || 'La ejecución activa del proyecto no tiene un detalle adicional.'}
          </div>
          {projectOrchestrator.updated_at && (
            <div style={footerNoteStyle}>Actualizado: {projectOrchestrator.updated_at}</div>
          )}
        </div>
      )}

      {issues.length > 0 ? (
        <div style={issuesWrapStyle}>
          {issues.map((item) => (
            <span key={item} style={issueBadgeStyle}>
              {item}
            </span>
          ))}
        </div>
      ) : (
        <div style={emptyStyle}>No hay ejecuciones duplicadas detectadas.</div>
      )}

      <div style={actionsStyle}>
        {cleanupAvailable && (
          <button
            type="button"
            className="btn-outline"
            onClick={handleCleanup}
            disabled={cleanupMutation.isPending}
          >
            {cleanupMutation.isPending ? 'Limpiando...' : '🧹 Limpiar duplicados'}
          </button>
        )}
        <button type="button" className="btn-outline" onClick={handleRefresh} disabled={isLoading}>
          Refrescar
        </button>
      </div>

      {processes.length > 0 ? (
        <div style={listStyle}>{processes.map(renderProcess)}</div>
      ) : (
        <div style={emptyStyle}>No se detectaron procesos de orquestador activos.</div>
      )}

      {!compact && duplicates.length > 0 && (
        <div style={footerNoteStyle}>
          Se detectaron {duplicates.length} duplicada{duplicates.length === 1 ? '' : 's'}.
        </div>
      )}
    </div>
  );
}

function Header({ count }: { count: number }) {
  return (
    <div style={panelHeadStyle}>
      <div>
        <div style={sectionLabelStyle}>Ejecuciones</div>
        <div style={subtitleStyle}>Detecta el proceso primario, duplicados y locks obsoletos.</div>
      </div>
      <div style={summaryWrapStyle}>
        <span style={summaryBadgeStyle}>{count} proceso{count === 1 ? '' : 's'}</span>
      </div>
    </div>
  );
}

const panelStyle: CSSProperties = {
  backgroundColor: '#1e1e2e',
  borderRadius: '8px',
  padding: '12px 16px',
  display: 'grid',
  gap: '12px',
};

const panelHeadStyle: CSSProperties = {
  display: 'flex',
  alignItems: 'flex-start',
  justifyContent: 'space-between',
  gap: '10px',
  flexWrap: 'wrap',
};

const sectionLabelStyle: CSSProperties = {
  fontSize: '0.75rem',
  textTransform: 'uppercase',
  letterSpacing: '.08em',
  color: '#888',
  marginBottom: '4px',
};

const subtitleStyle: CSSProperties = {
  fontSize: '0.85rem',
  color: '#bbb',
  lineHeight: 1.5,
};

const summaryWrapStyle: CSSProperties = {
  display: 'flex',
  gap: '8px',
  flexWrap: 'wrap',
  alignItems: 'center',
};

const activeExecutionStyle: CSSProperties = {
  display: 'grid',
  gap: '8px',
  padding: '12px',
  borderRadius: '10px',
  border: '1px solid #4a4a6a',
  background: 'linear-gradient(180deg, rgba(127,119,221,0.08), rgba(30,30,46,0.95))',
};

const summaryBadgeStyle: CSSProperties = {
  fontSize: '0.72rem',
  padding: '2px 8px',
  borderRadius: '999px',
  backgroundColor: '#3a3a5a',
  color: '#ddd',
};

const issueBadgeStyle: CSSProperties = {
  fontSize: '0.72rem',
  padding: '2px 8px',
  borderRadius: '999px',
  backgroundColor: '#FFF2D8',
  color: '#9A5B00',
};

const issuesWrapStyle: CSSProperties = {
  display: 'flex',
  gap: '8px',
  flexWrap: 'wrap',
};

const actionsStyle: CSSProperties = {
  display: 'flex',
  gap: '8px',
  flexWrap: 'wrap',
  alignItems: 'center',
};

const listStyle: CSSProperties = {
  display: 'grid',
  gap: '6px',
};

const processRowStyle: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: '12px',
  padding: '10px 12px',
  backgroundColor: '#252536',
  borderRadius: '6px',
};

const processTitleStyle: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: '8px',
  flexWrap: 'wrap',
  fontSize: '0.85rem',
  color: '#ddd',
  fontWeight: 500,
};

const processMetaStyle: CSSProperties = {
  fontSize: '0.7rem',
  color: '#888',
  marginTop: '4px',
  wordBreak: 'break-all',
};

const processBadgeStyle: CSSProperties = {
  fontSize: '0.7rem',
  padding: '2px 8px',
  borderRadius: '4px',
};

const secondaryBadgeStyle: CSSProperties = {
  fontSize: '0.7rem',
  padding: '2px 8px',
  borderRadius: '4px',
  backgroundColor: '#4a3a2a',
  color: '#da8',
  flexShrink: 0,
};

const tagStyle: CSSProperties = {
  ...secondaryBadgeStyle,
  backgroundColor: '#3a3a5a',
  color: '#ddd',
};

const emptyStyle: CSSProperties = {
  border: '1px dashed #444',
  borderRadius: '8px',
  padding: '10px 12px',
  color: '#888',
  fontSize: '0.85rem',
  backgroundColor: '#252536',
};

const footerNoteStyle: CSSProperties = {
  fontSize: '0.75rem',
  color: '#888',
};
