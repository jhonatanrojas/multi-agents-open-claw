import { useState } from 'react';
import type { AvailableModel } from '@/types';
import { AgentAvatar } from '@/components/shared';

type LocalAgentId = 'arch' | 'byte' | 'pixel';

interface ModelSelectProps {
  agentId: LocalAgentId;
  currentModel?: string;
  availableModels: AvailableModel[];
  onChange: (agentId: LocalAgentId, model: string) => void;
  onTest?: (model: string) => void;
}

export function ModelSelect({
  agentId,
  currentModel,
  availableModels,
  onChange,
  onTest,
}: ModelSelectProps) {
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<'ok' | 'error' | null>(null);

  const handleTest = async () => {
    if (!currentModel || !onTest) return;
    setTesting(true);
    setTestResult(null);
    
    try {
      await onTest(currentModel);
      setTestResult('ok');
    } catch {
      setTestResult('error');
    } finally {
      setTesting(false);
      setTimeout(() => setTestResult(null), 3000);
    }
  };

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '12px',
        padding: '12px 16px',
        backgroundColor: '#252536',
        borderRadius: '8px',
      }}
    >
      <AgentAvatar agentId={agentId} showName size="sm" />

      <select
        value={currentModel || ''}
        onChange={(e) => onChange(agentId, e.target.value)}
        style={{
          flex: 1,
          padding: '8px 12px',
          fontSize: '0.85rem',
          backgroundColor: '#1e1e2e',
          color: '#ddd',
          border: '1px solid #3a3a5a',
          borderRadius: '6px',
          cursor: 'pointer',
        }}
      >
        <option value="">Seleccionar modelo...</option>
        {availableModels.map((model) => (
          <option key={model.qualified} value={model.qualified}>
            {model.name || model.qualified}
          </option>
        ))}
      </select>

      {onTest && currentModel && (
        <button
          onClick={handleTest}
          disabled={testing}
          style={{
            padding: '6px 12px',
            fontSize: '0.75rem',
            backgroundColor:
              testResult === 'ok'
                ? '#2a4a2a'
                : testResult === 'error'
                ? '#4a2a2a'
                : '#3a3a5a',
            color: testResult === 'ok' ? '#8c8' : testResult === 'error' ? '#e88' : '#aaa',
            border: 'none',
            borderRadius: '4px',
            cursor: testing ? 'not-allowed' : 'pointer',
          }}
          title="Probar disponibilidad del modelo"
        >
          {testing ? '⏳' : testResult === 'ok' ? '✓' : testResult === 'error' ? '✗' : '🧪'}
        </button>
      )}
    </div>
  );
}
