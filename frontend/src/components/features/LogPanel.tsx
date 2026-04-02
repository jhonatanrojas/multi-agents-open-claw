import { LogFeed } from '@/components/shared';
import { dedupeLog } from '@/utils';
import type { LogEntry } from '@/types';

interface LogPanelProps {
  log: LogEntry[];
  maxLines?: number;
}

export function LogPanel({ log, maxLines = 80 }: LogPanelProps) {
  const dedupedLog = dedupeLog(log);

  return (
    <div className="log-panel">
      <LogFeed log={dedupedLog} maxLines={maxLines} />
    </div>
  );
}
