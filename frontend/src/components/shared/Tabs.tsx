import './Tabs.css';

export type TabId = 'tasks' | 'agents' | 'log' | 'gateway' | 'files' | 'miniverse' | 'projects' | 'models';

interface TabsProps {
  tabs: Array<{ id: TabId; label: string }>;
  activeTab: TabId;
  onTabChange: (tab: TabId) => void;
}

export function Tabs({ tabs, activeTab, onTabChange }: TabsProps) {
  return (
    <div className="tabs">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          className={`tab-btn ${activeTab === tab.id ? 'active' : ''}`}
          onClick={() => onTabChange(tab.id)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}