import { create } from 'zustand';
import type { MiniverseSnapshot, MiniverseEvent } from '@/types';

interface MiniverseState {
  // Data
  snapshot: MiniverseSnapshot | null;
  isLoading: boolean;
  error: string | null;
  lastFetched: string | null;
  
  // Actions
  setSnapshot: (snapshot: MiniverseSnapshot) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  addEvent: (event: MiniverseEvent) => void;
  reset: () => void;
}

// Build a local mock snapshot when offline
function buildLocalMockSnapshot(reason: string): MiniverseSnapshot {
  return {
    world: {
      gridCols: 12,
      gridRows: 8,
      floor: [
        ['grass', 'grass', 'grass', 'grass', 'path', 'path', 'path', 'path', 'grass', 'grass', 'grass', 'grass'],
        ['grass', 'grass', 'grass', 'path', 'path', 'path', 'path', 'path', 'path', 'grass', 'grass', 'grass'],
        ['grass', 'grass', 'path', 'path', 'path', 'path', 'path', 'path', 'path', 'path', 'grass', 'grass'],
        ['grass', 'grass', 'path', 'path', 'path', 'desk', 'desk', 'path', 'path', 'path', 'grass', 'grass'],
        ['grass', 'path', 'path', 'path', 'path', 'desk', 'desk', 'path', 'path', 'path', 'path', 'grass'],
        ['grass', 'path', 'path', 'path', 'path', 'path', 'path', 'path', 'path', 'path', 'path', 'grass'],
        ['grass', 'grass', 'path', 'path', 'path', 'path', 'path', 'path', 'path', 'grass', 'grass', 'grass'],
        ['grass', 'grass', 'grass', 'grass', 'path', 'path', 'path', 'path', 'grass', 'grass', 'grass', 'grass'],
      ],
      props: [
        {
          id: 'wooden_desk_single',
          x: 5,
          y: 3,
          w: 2,
          h: 2,
          layer: 'below',
          anchors: [
            { name: 'desk_0_0', ox: 0.5, oy: 1.1, type: 'work' },
            { name: 'desk_0_1', ox: 1.4, oy: 1.1, type: 'work' },
          ],
        },
        {
          id: 'coffee_machine',
          x: 9,
          y: 1,
          w: 1,
          h: 1.5,
          layer: 'above',
          anchors: [
            { name: 'coffee_0_0', ox: 0.5, oy: 1, type: 'social' },
            { name: 'coffee_0_1', ox: 0.9, oy: 1, type: 'utility' },
          ],
        },
      ],
      citizens: [
        { agentId: 'main', name: 'MAIN', sprite: 'rio', position: 'coffee_0_1', type: 'agent' },
        { agentId: 'pixel', name: 'PIXEL', sprite: 'nova', position: 'desk_0_0', type: 'agent' },
        { agentId: 'byte', name: 'BYTE', sprite: 'dexter', position: 'desk_0_1', type: 'agent' },
        { agentId: 'arch', name: 'ARCH', sprite: 'morty', position: 'coffee_0_0', type: 'agent' },
      ],
      events: [
        { id: 'mock-1', type: 'thinking', agent: 'arch', message: 'Mock local activo.' },
        { id: 'mock-2', type: 'message', agent: 'main', message: 'MAIN observa el mundo local.' },
      ],
      info: {
        world: 'Miniverse local mock',
        status: 'active',
        grid: { cols: 12, rows: 8 },
        agents: { online: 4, total: 4 },
        theme: 'cozy-startup',
      },
    },
    meta: {
      source: 'local-mock',
      fallback: 'local-mock',
      error: reason,
      stale: true,
    },
  };
}

const initialState = {
  snapshot: null as MiniverseSnapshot | null,
  isLoading: false,
  error: null as string | null,
  lastFetched: null as string | null,
};

export const useMiniverseStore = create<MiniverseState>((set, get) => ({
  // Initial state
  ...initialState,
  
  // Actions
  setSnapshot: (snapshot) => set({
    snapshot,
    isLoading: false,
    error: null,
    lastFetched: new Date().toISOString(),
  }),
  
  setLoading: (loading) => set({ isLoading: loading }),
  
  setError: (error) => set({
    error,
    isLoading: false,
    snapshot: get().snapshot || buildLocalMockSnapshot(error || 'offline'),
  }),
  
  addEvent: (event) => {
    const current = get().snapshot;
    if (!current) return;
    
    const currentEvents = current.world.events || [];
    
    set({
      snapshot: {
        ...current,
        world: {
          ...current.world,
          events: [...currentEvents.slice(-49), event], // Keep max 50
        },
      },
    });
  },
  
  reset: () => set(initialState),
}));

// Selector for citizens with resolved positions
export const selectCitizensWithPositions = (state: MiniverseState) => {
  const world = state.snapshot?.world;
  if (!world) return [];
  
  const props = world.props || [];
  const citizens = world.citizens || [];
  
  const anchors = new Map<string, { x: number; y: number }>();
  
  for (const prop of props) {
    for (const anchor of prop.anchors) {
      anchors.set(anchor.name, {
        x: prop.x + anchor.ox,
        y: prop.y + anchor.oy,
      });
    }
  }
  
  return citizens.map((citizen) => {
    const pos = anchors.get(citizen.position);
    return {
      ...citizen,
      resolvedX: pos?.x ?? 0,
      resolvedY: pos?.y ?? 0,
    };
  });
};
