import { useState, useEffect, useRef } from 'react';
import { useGatewayStore } from '@/store';
import type { GatewayEvent } from '@/types';
import { extractGatewayText } from '@/utils';
import './ActivityStream.css';

interface AgentActivity {
  agentId: string;
  content: string;
  kind: string;
  timestamp: Date;
  isTyping: boolean;
}

function isChatEvent(event: GatewayEvent): boolean {
  return String(event.event || '').trim().toLowerCase() === 'chat';
}

function AgentActivityCard({ activity }: { activity: AgentActivity; index: number }) {
  const [displayedContent, setDisplayedContent] = useState('');
  const [isAnimating, setIsAnimating] = useState(activity.isTyping);
  const contentRef = useRef(activity.content);
  
  // Typewriter effect
  useEffect(() => {
    if (!activity.isTyping || !activity.content) {
      setDisplayedContent(activity.content);
      setIsAnimating(false);
      return;
    }
    
    // Start from where we left off if same content
    const fullContent = activity.content;
    let currentIndex = displayedContent.length;
    
    if (contentRef.current !== fullContent) {
      currentIndex = 0;
      contentRef.current = fullContent;
    }
    
    if (currentIndex >= fullContent.length) {
      setDisplayedContent(fullContent);
      setIsAnimating(false);
      return;
    }
    
    setIsAnimating(true);
    
    const interval = setInterval(() => {
      currentIndex++;
      setDisplayedContent(fullContent.slice(0, currentIndex));
      
      if (currentIndex >= fullContent.length) {
        clearInterval(interval);
        setIsAnimating(false);
      }
    }, 20);
    
    return () => clearInterval(interval);
  }, [activity.content, activity.isTyping]);
  
  const getKindStyle = (kind: string) => {
    switch (kind?.toLowerCase()) {
      case 'thinking':
        return 'thinking';
      case 'tool':
        return 'tool';
      case 'message':
      case 'chat':
        return 'message';
      default:
        return 'default';
    }
  };
  
  const formatTime = (date: Date) => {
    return date.toLocaleTimeString('es', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  };
  
  const truncateContent = (text: string, maxLines = 4) => {
    const lines = text.split('\n').slice(0, maxLines);
    return lines.join('\n');
  };
  
  return (
    <div className={`agent-activity-card ${getKindStyle(activity.kind)}`}>
      <div className="activity-header">
        <span className="activity-agent">{activity.agentId}</span>
        <span className="activity-time">{formatTime(activity.timestamp)}</span>
        {isAnimating && <span className="typing-indicator">●●●</span>}
      </div>
      <div className="activity-content">
        <pre>{truncateContent(displayedContent)}</pre>
      </div>
    </div>
  );
}

export function ActivityStream() {
  const events = useGatewayStore((s) => s.events);
  
  // Get latest activity per agent
  const [activities, setActivities] = useState<AgentActivity[]>([]);
  
  useEffect(() => {
    // Group events by agent and get latest for each
    const latestByAgent = new Map<string, GatewayEvent>();
    
    for (const event of events) {
      if (!isChatEvent(event)) continue;
      
      const existing = latestByAgent.get(event.agent_id);
      if (!existing || new Date(event.received_at) > new Date(existing.received_at)) {
        latestByAgent.set(event.agent_id, event);
      }
    }
    
    // Convert to AgentActivity
    const newActivities: AgentActivity[] = [];
    for (const [agentId, event] of latestByAgent) {
      const content = extractGatewayText(event.payload) || event.summary || event.event || '';
      
      newActivities.push({
        agentId,
        content,
        kind: String(event.kind || 'message'),
        timestamp: new Date(event.received_at),
        isTyping: false, // Could detect in real-time if needed
      });
    }
    
    // Sort by timestamp descending
    newActivities.sort((a, b) => b.timestamp.getTime() - a.timestamp.getTime());
    
    setActivities(newActivities);
  }, [events]);
  
  if (activities.length === 0) {
    return (
      <div className="activity-stream-empty">
        <span>🤖</span>
        <p>Sin actividad reciente</p>
        <small>Los eventos de los agentes aparecerán aquí</small>
      </div>
    );
  }
  
  return (
    <div className="activity-stream">
      <div className="activity-header-bar">
        <span className="activity-count">{activities.length} agente{activities.length !== 1 ? 's' : ''}</span>
        <span className="activity-live">● EN VIVO</span>
      </div>
      <div className="activity-list">
        {activities.slice(0, 6).map((activity, i) => (
          <AgentActivityCard key={activity.agentId} activity={activity} index={i} />
        ))}
      </div>
    </div>
  );
}
