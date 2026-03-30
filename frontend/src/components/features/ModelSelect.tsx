import { useState } from 'react';
import type { AvailableModel } from '@/types';
import { AgentAvatar } from '@/components/shared';

type LocalAgentId = 'arch' | 'byte' | 'pixel';

interface ModelSelectProps {
  agentId: LocalAgentId;
  currentModel?: string;
  availableModels: AvailableModel[];
  onChange: (agentId: LocalAgentId, model: string) => void;
  onTest?: (model: string) => Promise<{
    ok: boolean;
    model: string;
    status?: string;
    elapsed_ms?: number;
    message?: string;
    error?: string;
  }>;
}

export function ModelSelect({
  agentId,
  currentModel,
  availableModels,
  onChange,
  onTest,
}: ModelSelectProps) {
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{
    ok: boolean;
    model: string;
    status?: string;
    elapsed_ms?: number;
    message?: string;
    error?: string;
  } | null>(null);
  const selectedModel = availableModels.find((model) => model.qualified === currentModel);

  const formatProvider = (provider?: string) => {
    if (!provider) return 'proveedor desconocido';
    return provider;
  };

  const getTestTone = () => {
    if (!testResult) return 'neutral';
    if (testResult.ok) return 'success';
    if (testResult.status === 'insufficient_balance' || testResult.status === 'rate_limit') return 'warning';
    return 'error';
  };

  const getTestLabel = () => {
    if (!testResult) return 'Sin probar';
    if (testResult.ok) return `Disponible${testResult.elapsed_ms ? ` · ${testResult.elapsed_ms} ms` : ''}`;
    if (testResult.status === 'insufficient_balance') return 'Saldo insuficiente';
    if (testResult.status === 'rate_limit') return 'Rate limit';
    if (testResult.status === 'not_found') return 'Modelo no encontrado';
    if (testResult.status === 'no_api_key') return 'Sin API key';
    if (testResult.status === 'auth_error') return 'Error de autenticación';
    if (testResult.status === 'timeout') return 'Timeout';
    return testResult.message || testResult.error || 'Error';
  };

  const handleTest = async () => {
    if (!currentModel || !onTest) return;
    setTesting(true);
    setTestResult(null);
    
    try {
      const result = await onTest(currentModel);
      setTestResult(result);
    } catch (error) {
      setTestResult({
        ok: false,
        model: currentModel,
        status: 'error',
        message: String(error),
      });
    } finally {
      setTesting(false);
    }
  };

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '8px',
        padding: '12px 16px',
        backgroundColor: '#252536',
        borderRadius: '8px',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '12px',
        }}
      >
        <AgentAvatar agentId={agentId} showName size="sm" />
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: '2px',
            minWidth: 0,
          }}
        >
          <span style={{ fontSize: '0.75rem', color: '#aaa', textTransform: 'uppercase' }}>
            Proveedor
          </span>
          <span style={{ fontSize: '0.9rem', color: '#fff', fontWeight: 600 }}>
            {formatProvider(selectedModel?.provider)}
          </span>
        </div>
      </div>

      <select
        value={currentModel || ''}
        onChange={(e) => {
          setTestResult(null);
          onChange(agentId, e.target.value);
        }}
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
            {model.name || model.qualified} ({formatProvider(model.provider)})
          </option>
        ))}
      </select>

      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          flexWrap: 'wrap',
        }}
      >
        {onTest && currentModel && (
          <button
            onClick={handleTest}
            disabled={testing}
            style={{
              padding: '6px 12px',
              fontSize: '0.75rem',
              backgroundColor:
                getTestTone() === 'success'
                  ? '#2a4a2a'
                  : getTestTone() === 'warning'
                  ? '#4a3a1a'
                  : getTestTone() === 'error'
                  ? '#4a2a2a'
                  : '#3a3a5a',
              color:
                getTestTone() === 'success'
                  ? '#8c8'
                  : getTestTone() === 'warning'
                  ? '#f2c96d'
                  : getTestTone() === 'error'
                  ? '#e88'
                  : '#aaa',
              border: 'none',
              borderRadius: '4px',
              cursor: testing ? 'not-allowed' : 'pointer',
            }}
            title="Probar disponibilidad del modelo"
          >
            {testing ? '⏳' : testResult?.ok ? '✓' : testResult ? '↻' : '🧪'}
          </button>
        )}

        {testResult && (
          <span
            style={{
              fontSize: '0.75rem',
              color:
                getTestTone() === 'success'
                  ? '#8c8'
                  : getTestTone() === 'warning'
                  ? '#f2c96d'
                  : '#e88',
            }}
            title={testResult.error || testResult.message || ''}
          >
            {getTestLabel()}
          </span>
        )}
      </div>
    </div>
  );
}
