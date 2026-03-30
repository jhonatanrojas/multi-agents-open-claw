import { useEffect, useState } from 'react';
import { ModelSelect } from './ModelSelect';
import type { AvailableModel, ModelConfig } from '@/types';

type AgentId = 'arch' | 'byte' | 'pixel';

interface ModelsPanelProps {
  modelConfig: ModelConfig | null;
  availableModels: AvailableModel[];
  isLoading?: boolean;
  onSave: (agents: Record<AgentId, string>) => Promise<void> | void;
  onTestModel?: (model: string) => Promise<{
    ok: boolean;
    model: string;
    status?: string;
    elapsed_ms?: number;
    message?: string;
    error?: string;
  }>;
}

export function ModelsPanel({
  modelConfig,
  availableModels,
  isLoading = false,
  onSave,
  onTestModel,
}: ModelsPanelProps) {
  const getSelectionsFromConfig = () => ({
    arch: modelConfig?.agents?.arch?.model || '',
    byte: modelConfig?.agents?.byte?.model || '',
    pixel: modelConfig?.agents?.pixel?.model || '',
  });
  const [selections, setSelections] = useState<Record<AgentId, string>>({
    ...getSelectionsFromConfig(),
  });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    setSelections(getSelectionsFromConfig());
    setSaved(false);
    setSaveError(null);
  }, [
    modelConfig?.agents?.arch?.model,
    modelConfig?.agents?.byte?.model,
    modelConfig?.agents?.pixel?.model,
  ]);

  const handleChange = (agentId: AgentId, model: string) => {
    setSelections((prev) => ({ ...prev, [agentId]: model }));
    setSaved(false);
    setSaveError(null);
  };

  const handleSave = async () => {
    if (isLoading || !modelConfig) {
      setSaveError('La configuración de modelos todavía se está cargando.');
      return;
    }

    setSaving(true);
    setSaveError(null);
    try {
      await onSave({
        arch: selections.arch,
        byte: selections.byte,
        pixel: selections.pixel,
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (error) {
      setSaveError(String(error));
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

      {isLoading && (
        <div style={{ fontSize: '0.8rem', color: '#f2c96d' }}>
          Cargando configuración de modelos...
        </div>
      )}

      {saveError && (
        <div style={{ fontSize: '0.8rem', color: '#e88' }}>
          {saveError}
        </div>
      )}

      <button
        type="button"
        onClick={handleSave}
        disabled={saving || saved || isLoading || !modelConfig}
        style={{
          width: '100%',
          padding: '12px',
          fontSize: '0.9rem',
          fontWeight: 600,
          backgroundColor: saved ? '#2a4a2a' : saving ? '#3a3a5a' : '#4a4a7a',
          color: saved ? '#8c8' : '#fff',
          border: 'none',
          borderRadius: '8px',
          cursor: saving || saved || isLoading || !modelConfig ? 'not-allowed' : 'pointer',
          transition: 'background-color 0.2s',
        }}
      >
        {saving ? 'Guardando...' : saved ? '✓ Guardado' : isLoading ? 'Cargando...' : '💾 Guardar Modelos'}
      </button>
    </div>
  );
}
