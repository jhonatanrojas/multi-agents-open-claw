import { useEffect, useRef } from 'react';
import type { LogEntry } from '@/types';
import { fmtTime } from '@/utils';

interface LogFeedProps {
  log: LogEntry[];
  maxLines?: number;
  compact?: boolean;
}

export function LogFeed({ log, maxLines = 80, compact = false }: LogFeedProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new entries arrive
  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [log]);

  const displayLog = log.slice(-maxLines);

  return (
    <div
      ref={containerRef}
      className="log-feed"
      style={{
        fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
        fontSize: compact ? '0.7rem' : '0.8rem',
        lineHeight: 1.5,
        backgroundColor: '#1a1a2e',
        color: '#e0e0e0',
        padding: compact ? '8px' : '12px',
        borderRadius: '6px',
        maxHeight: compact ? '200px' : '400px',
        overflowY: 'auto',
        overflowX: 'hidden',
        wordBreak: 'break-word' as const,
      }}
    >
      {displayLog.length === 0 ? (
        <div style={{ color: '#888', fontStyle: 'italic' }}>
          Sin entradas de log
        </div>
      ) : (
        displayLog.map((entry, i) => (
          <div
            key={`${entry.ts}-${i}`}
            style={{
              display: 'flex',
              gap: '8px',
              marginBottom: compact ? '2px' : '4px',
              opacity: 1 - (displayLog.length - 1 - i) * 0.01, // Fade older entries
            }}
          >
            <span style={{ color: '#888', flexShrink: 0 }}>
              [{fmtTime(entry.ts)}]
            </span>
            <span
              style={{
                color: getAgentColor(entry.agent),
                flexShrink: 0,
                fontWeight: 600,
              }}
            >
              {entry.agent.toUpperCase()}
            </span>
            <span style={{ color: '#ccc' }}>{entry.msg}</span>
          </div>
        ))
      )}
    </div>
  );
}

function getAgentColor(agent: string): string {
  const colors: Record<string, string> = {
    arch: '#7F77DD',
    byte: '#1D9E75',
    pixel: '#D85A30',
  };
  return colors[agent] || '#888';
}
