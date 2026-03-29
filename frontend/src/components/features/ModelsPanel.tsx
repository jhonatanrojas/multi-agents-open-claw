import { useState } from 'react';
import { ModelSelect } from './ModelSelect';
import type { AvailableModel, ModelConfig } from '@/types';

type AgentId = 'arch' | 'byte' | 'pixel';

interface ModelsPanelProps {
  modelConfig: ModelConfig | null;
  availableModels: AvailableModel[];
  onSave: (agents: Record<AgentId, { model: string }>) => void;
  onTestModel?: (model: string) => Promise<void>;
}

export function ModelsPanel({
  modelConfig,
  availableModels,
  onSave,
  onTestModel,
}: ModelsPanelProps) {
  const [selections, setSelections] = useState<Record<AgentId, string>>({
    arch: modelConfig?.agents?.arch?.model || 'nvidia/z-ai/glm5',
    byte: modelConfig?.agents?.byte?.model || 'nvidia/moonshotai/kimi-k2.5',
    pixel: modelConfig?.agents?.pixel?.model || 'nvidia/moonshotai/kimi-k2.5',
  });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const handleChange = (agentId: AgentId, model: string) => {
    setSelections((prev) => ({ ...prev, [agentId]: model }));
    setSaved(false);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await onSave({
        arch: { model: selections.arch },
        byte: { model: selections.byte },
        pixel: { model: selections.pixel },
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } finally {
      setSaving(false);
    }
  };

  const agents: AgentId[] = ['arch', 'byte', 'pixel'];

  return (
    <div className="models-panel">
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: '8px',
          marginBottom: '16px',
        }}
      >
        {agents.map((agentId) => (
          <ModelSelect
            key={agentId}
            agentId={agentId}
            currentModel={selections[agentId]}
            availableModels={availableModels}
            onChange={handleChange}
            onTest={onTestModel}
          />
        ))}
      </div>

      <button
        onClick={handleSave}
        disabled={saving || saved}
        style={{
          width: '100%',
          padding: '12px',
          fontSize: '0.9rem',
          fontWeight: 600,
          backgroundColor: saved ? '#2a4a2a' : saving ? '#3a3a5a' : '#4a4a7a',
          color: saved ? '#8c8' : '#fff',
          border: 'none',
          borderRadius: '8px',
          cursor: saving || saved ? 'not-allowed' : 'pointer',
          transition: 'background-color 0.2s',
        }}
      >
        {saving ? 'Guardando...' : saved ? '✓ Guardado' : '💾 Guardar Modelos'}
      </button>
    </div>
  );
}
