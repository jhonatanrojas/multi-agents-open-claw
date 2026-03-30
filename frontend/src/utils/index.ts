import type { LogEntry, GatewayEvent } from '@/types';

/**
 * Escape HTML special characters to prevent XSS
 */
export function escapeHtml(value: unknown): string {
  if (value == null) return '';
  const str = String(value);
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

/**
 * Format ISO timestamp to time string (HH:MM:SS)
 */
export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return '--:--:--';
  try {
    const date = new Date(iso);
    return date.toLocaleTimeString('es-ES', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    });
  } catch {
    return '--:--:--';
  }
}

/**
 * Format ISO timestamp to date string (YYYY-MM-DD)
 */
export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '----';
  try {
    const date = new Date(iso);
    return date.toLocaleDateString('es-ES', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    });
  } catch {
    return '----';
  }
}

/**
 * Get Spanish label for status
 */
export function t(status: string): string {
  const labels: Record<string, string> = {
    // Agent statuses
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
    resumable: 'reanudable',
    sleeping: 'durmiendo',
    // Task statuses
    in_progress: 'en progreso',
    done: 'completado',
    pending: 'pendiente',
  };
  return labels[status] || status;
}

/**
 * Deduplicate log entries by timestamp + agent + message
 */
export function dedupeLog(log: LogEntry[]): LogEntry[] {
  const seen = new Set<string>();
  return log.filter((entry) => {
    const key = `${entry.ts}|${entry.agent}|${entry.msg}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

/**
 * Generate fingerprint for gateway event deduplication
 */
export function gatewayEventFingerprint(event: GatewayEvent): string {
  return `${event.agent_id}|${event.session_key}|${event.event}|${event.kind}|${event.seq}`;
}

/**
 * Deduplicate gateway events by fingerprint
 */
export function dedupeGatewayEvents(events: GatewayEvent[]): GatewayEvent[] {
  const seen = new Set<string>();
  return events.filter((event) => {
    const fp = gatewayEventFingerprint(event);
    if (seen.has(fp)) return false;
    seen.add(fp);
    return true;
  });
}

function parseJsonIfPossible(value: string): unknown | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  if (!(trimmed.startsWith('{') || trimmed.startsWith('['))) return null;
  try {
    return JSON.parse(trimmed);
  } catch {
    return null;
  }
}

function extractTextFromObject(value: Record<string, unknown>, depth = 0): string {
  if (depth > 4) return '';

  const stringKeys = ['text', 'content', 'message', 'summary', 'output', 'result', 'body'];
  for (const key of stringKeys) {
    const candidate = value[key];
    if (typeof candidate === 'string' && candidate.trim()) {
      return candidate.trim();
    }
  }

  const data = value.data;
  if (data && typeof data === 'object' && !Array.isArray(data)) {
    const nested = extractTextFromObject(data as Record<string, unknown>, depth + 1);
    if (nested) return nested;
  }

  const choices = value.choices;
  if (Array.isArray(choices)) {
    for (const choice of choices) {
      if (!choice || typeof choice !== 'object' || Array.isArray(choice)) continue;
      const nestedChoice = choice as Record<string, unknown>;
      const nested = extractTextFromObject(nestedChoice, depth + 1);
      if (nested) return nested;
      const message = nestedChoice.message;
      if (message && typeof message === 'object' && !Array.isArray(message)) {
        const nestedMessage = extractTextFromObject(message as Record<string, unknown>, depth + 1);
        if (nestedMessage) return nestedMessage;
      }
    }
  }

  const content = value.content;
  if (Array.isArray(content)) {
    const parts = content
      .map((block) => {
        if (!block || typeof block !== 'object' || Array.isArray(block)) return '';
        const nestedBlock = block as Record<string, unknown>;
        if (typeof nestedBlock.type === 'string' && nestedBlock.type !== 'text') {
          return '';
        }
        const text = nestedBlock.text;
        if (typeof text === 'string' && text.trim()) {
          return text.trim();
        }
        return extractTextFromObject(nestedBlock, depth + 1);
      })
      .filter(Boolean);
    if (parts.length > 0) {
      return parts.join(' ').trim();
    }
  }

  return '';
}

/**
 * Extract human-readable text from a gateway event payload.
 * Prefers nested text fields and avoids dumping raw JSON when possible.
 */
export function extractGatewayText(payload: unknown): string {
  if (payload == null) return '';

  if (typeof payload === 'string') {
    const trimmed = payload.trim();
    if (!trimmed) return '';

    const parsed = parseJsonIfPossible(trimmed);
    if (parsed && typeof parsed === 'object') {
      return extractGatewayText(parsed);
    }
    return trimmed;
  }

  if (Array.isArray(payload)) {
    const parts = payload
      .map((item) => extractGatewayText(item))
      .filter((part) => part.trim().length > 0);
    return parts.join(' ').trim();
  }

  if (typeof payload === 'object') {
    return extractTextFromObject(payload as Record<string, unknown>);
  }

  return String(payload).trim();
}

/**
 * Normalize preview status to known values
 */
export function normalizePreviewStatus(status: unknown): string {
  if (status === 'running' || status === 'stopped' || status === 'not_applicable') {
    return status;
  }
  return 'not_applicable';
}

/**
 * Truncate text with ellipsis
 */
export function truncate(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text;
  return text.slice(0, maxLength - 3) + '...';
}

/**
 * Format relative time (e.g., "hace 5 min")
 */
export function formatRelativeTime(iso: string | null | undefined): string {
  if (!iso) return '';
  try {
    const date = new Date(iso);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffSec = Math.floor(diffMs / 1000);
    const diffMin = Math.floor(diffSec / 60);
    const diffHour = Math.floor(diffMin / 60);

    if (diffSec < 60) return 'hace un momento';
    if (diffMin < 60) return `hace ${diffMin} min`;
    if (diffHour < 24) return `hace ${diffHour}h`;
    return fmtDate(iso);
  } catch {
    return '';
  }
}
