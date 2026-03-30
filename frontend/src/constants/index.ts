// Agent IDs
export const AGENT_IDS = {
  ARCH: 'arch',
  BYTE: 'byte',
  PIXEL: 'pixel',
} as const;

// Agent metadata
export const AGENT_META = {
  arch: {
    name: 'ARCH',
    rol: 'Coordinador',
    model: 'nvidia/z-ai/glm5',
    emoji: '🗂️',
    color: '#7F77DD',
  },
  byte: {
    name: 'BYTE',
    rol: 'Programador',
    model: 'nvidia/moonshotai/kimi-k2.5',
    emoji: '💻',
    color: '#1D9E75',
  },
  pixel: {
    name: 'PIXEL',
    rol: 'Diseñador',
    model: 'nvidia/moonshotai/kimi-k2.5',
    emoji: '🎨',
    color: '#D85A30',
  },
} as const;

// Status colors
export const STATUS_COLOR = {
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
} as const;

export const TASK_COLOR = {
  pending: { bg: '#F1EFE8', text: '#5F5E5A' },
  in_progress: { bg: '#EEEDFE', text: '#3C3489' },
  paused: { bg: '#FFF2D8', text: '#9A5B00' },
  done: { bg: '#EAF3DE', text: '#3B6D11' },
  error: { bg: '#FCEBEB', text: '#791F1F' },
} as const;

// Status translations (Spanish)
export const STATUS_ES: Record<string, string> = {
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
  in_progress: 'en progreso',
  done: 'completado',
  pending: 'pendiente',
};

// API constants
// Default to the same-origin proxy; allow override for non-browser tooling.
const DEFAULT_API_BASE = '/devsquad/api';
export const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim() || DEFAULT_API_BASE;
export const CONTEXT_DOC_PATH = '/var/www/openclaw-multi-agents/shared/CONTEXT.md';
export const MODEL_SELECTION_KEY = 'devsquad:model-selection:v1';
export const LOG_MAX = 200;
export const LOG_AGENT_LIMIT = 5;
