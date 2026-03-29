import { useState } from 'react';

interface CopilotTabProps {
  previewUrl?: string;
  contextContent?: string;
  onSteer?: (message: string) => void;
  onContextUpdate?: (section: string, content: string) => void;
  steerLoading?: boolean;
}

export function CopilotTab({
  previewUrl,
  contextContent,
  onSteer,
  onContextUpdate,
  steerLoading = false,
}: CopilotTabProps) {
  const [steerMessage, setSteerMessage] = useState('');
  const [selectedSection, setSelectedSection] = useState('all');
  const [editContent, setEditContent] = useState('');

  const handleSendSteer = () => {
    if (!steerMessage.trim()) return;
    onSteer?.(steerMessage.trim());
    setSteerMessage('');
  };

  const handleSaveContext = () => {
    if (!editContent.trim()) return;
    onContextUpdate?.(selectedSection, editContent.trim());
  };

  // Parse context sections
  const sections = contextContent
    ? contextContent.split(/(?=^## )/m).filter(Boolean)
    : [];

  return (
    <div className="copilot-tab">
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: '16px',
          height: 'calc(100vh - 200px)',
        }}
      >
        {/* Left Column: Preview + Steer */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {/* Preview */}
          <div
            style={{
              flex: 1,
              backgroundColor: '#1e1e2e',
              borderRadius: '12px',
              overflow: 'hidden',
              display: 'flex',
              flexDirection: 'column',
            }}
          >
            <div
              style={{
                padding: '12px 16px',
                backgroundColor: '#252536',
                borderBottom: '1px solid #333',
                fontSize: '0.85rem',
                color: '#888',
              }}
            >
              👁️ Vista Previa
            </div>
            <div style={{ flex: 1, position: 'relative' }}>
              {previewUrl ? (
                <iframe
                  src={previewUrl}
                  style={{
                    width: '100%',
                    height: '100%',
                    border: 'none',
                    backgroundColor: '#fff',
                  }}
                  title="Preview"
                />
              ) : (
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    height: '100%',
                    color: '#666',
                    fontSize: '0.9rem',
                  }}
                >
                  Sin vista previa disponible
                </div>
              )}
            </div>
          </div>

          {/* Steer Input */}
          <div
            style={{
              backgroundColor: '#1e1e2e',
              borderRadius: '12px',
              padding: '16px',
            }}
          >
            <div
              style={{
                fontSize: '0.85rem',
                color: '#888',
                marginBottom: '8px',
              }}
            >
              💬 Enviar guía a agente
            </div>
            <div style={{ display: 'flex', gap: '8px' }}>
              <input
                type="text"
                value={steerMessage}
                onChange={(e) => setSteerMessage(e.target.value)}
                placeholder="Escribe una instrucción..."
                maxLength={140}
                onKeyDown={(e) => e.key === 'Enter' && handleSendSteer()}
                style={{
                  flex: 1,
                  padding: '10px 12px',
                  fontSize: '0.85rem',
                  backgroundColor: '#252536',
                  color: '#ddd',
                  border: '1px solid #3a3a5a',
                  borderRadius: '6px',
                }}
              />
              <button
                onClick={handleSendSteer}
                disabled={steerLoading || !steerMessage.trim()}
                style={{
                  padding: '10px 16px',
                  fontSize: '0.85rem',
                  backgroundColor: steerLoading ? '#3a3a5a' : '#4a4a7a',
                  color: '#fff',
                  border: 'none',
                  borderRadius: '6px',
                  cursor: steerLoading ? 'not-allowed' : 'pointer',
                }}
              >
                {steerLoading ? '...' : '→'}
              </button>
            </div>
            <div
              style={{
                fontSize: '0.7rem',
                color: '#666',
                textAlign: 'right',
                marginTop: '4px',
              }}
            >
              {steerMessage.length}/140
            </div>
          </div>
        </div>

        {/* Right Column: Context Editor */}
        <div
          style={{
            backgroundColor: '#1e1e2e',
            borderRadius: '12px',
            padding: '16px',
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          <div
            style={{
              fontSize: '0.85rem',
              color: '#888',
              marginBottom: '12px',
            }}
          >
            📝 Editar CONTEXT.md
          </div>

          {/* Section Selector */}
          <select
            value={selectedSection}
            onChange={(e) => setSelectedSection(e.target.value)}
            style={{
              padding: '8px 12px',
              fontSize: '0.8rem',
              backgroundColor: '#252536',
              color: '#ddd',
              border: '1px solid #3a3a5a',
              borderRadius: '6px',
              marginBottom: '12px',
            }}
          >
            <option value="all">Todas las secciones</option>
            {sections.map((section, i) => {
              const title = section.split('\n')[0].replace(/^## /, '');
              return (
                <option key={i} value={i.toString()}>
                  {title || `Sección ${i + 1}`}
                </option>
              );
            })}
          </select>

          {/* Content Editor */}
          <textarea
            value={editContent}
            onChange={(e) => setEditContent(e.target.value)}
            placeholder="Contenido de la sección..."
            style={{
              flex: 1,
              padding: '12px',
              fontSize: '0.8rem',
              fontFamily: 'ui-monospace, monospace',
              backgroundColor: '#252536',
              color: '#ddd',
              border: '1px solid #3a3a5a',
              borderRadius: '6px',
              resize: 'none',
              minHeight: '200px',
            }}
          />

          {/* Save Button */}
          <button
            onClick={handleSaveContext}
            disabled={!editContent.trim()}
            style={{
              marginTop: '12px',
              padding: '10px',
              fontSize: '0.85rem',
              backgroundColor: '#2a4a3a',
              color: '#8dc',
              border: 'none',
              borderRadius: '6px',
              cursor: 'pointer',
            }}
          >
            💾 Guardar Cambios
          </button>
        </div>
      </div>
    </div>
  );
}
