import { create } from 'zustand';
import type { GatewayEvent, GatewayStatus } from '@/types';

interface GatewayState {
  // Data
  status: GatewayStatus;
  events: GatewayEvent[];
  
  // Actions
  setSnapshot: (snapshot: { status: GatewayStatus; events: GatewayEvent[] }) => void;
  addEvent: (event: GatewayEvent) => void;
  setStatus: (status: Partial<GatewayStatus>) => void;
  clearEvents: () => void;
  reset: () => void;
}

// Dedupe helper - creates a unique fingerprint for each event
function eventFingerprint(event: GatewayEvent): string {
  return `${event.agent_id}|${event.session_key}|${event.event}|${event.kind}|${event.seq ?? ''}|${event.stateVersion ?? ''}`;
}

function isChatEvent(event: GatewayEvent): boolean {
  return String(event.event || '').trim().toLowerCase() === 'chat';
}

// Dedupe events array
function dedupeEvents(events: GatewayEvent[]): GatewayEvent[] {
  const seen = new Set<string>();
  const result: GatewayEvent[] = [];
  
  for (const event of events) {
    const key = eventFingerprint(event);
    if (!seen.has(key)) {
      seen.add(key);
      result.push(event);
    }
  }
  
  return result;
}

const initialState = {
  status: {
    connected: false,
    last_error: undefined,
    last_event_at: undefined,
    url: undefined,
  } as GatewayStatus,
  events: [] as GatewayEvent[],
};

export const useGatewayStore = create<GatewayState>((set, get) => ({
  // Initial state
  ...initialState,
  
  // Actions
  setSnapshot: (snapshot) => set({
    status: snapshot.status,
    events: dedupeEvents(snapshot.events).slice(-200), // Keep max 200
  }),
  
  addEvent: (event) => {
    const current = get().events;
    const key = eventFingerprint(event);
    const seen = new Set(current.map(eventFingerprint));
    
    if (seen.has(key)) return; // Skip duplicates
    
    set({
      events: dedupeEvents([...current, event]).slice(-200),
      status: {
        ...get().status,
        connected: true,
        last_error: undefined,
        last_event_at: event.received_at,
      },
    });
  },
  
  setStatus: (statusUpdate) => set((state) => ({
    status: { ...state.status, ...statusUpdate },
  })),
  
  clearEvents: () => set({ events: [] }),
  
  reset: () => set(initialState),
}));

// Selector helpers
export const selectLatestChatsByAgent = (agentId: string) => {
  return (state: GatewayState) => {
    const agentEvents = state.events
      .filter((e) => e.agent_id === agentId && isChatEvent(e))
      .sort((a, b) => 
        new Date(b.received_at).getTime() - new Date(a.received_at).getTime()
      );
    return agentEvents[0] || null;
  };
};

export const selectAllChats = (state: GatewayState) => {
  const chatsByAgent = new Map<string, GatewayEvent>();
  
  const chatEvents = state.events
    .filter((e) => isChatEvent(e))
    .sort((a, b) => 
      new Date(b.received_at).getTime() - new Date(a.received_at).getTime()
    );
  
  for (const event of chatEvents) {
    const key = event.agent_id || event.session_key || 'unknown';
    if (!chatsByAgent.has(key)) {
      chatsByAgent.set(key, event);
    }
  }
  
  return Array.from(chatsByAgent.values());
};
