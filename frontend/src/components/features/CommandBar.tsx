import { useState, useRef, useEffect } from 'react';
import { useStartProject, useExtendProject, useSendSteer, useRepos } from '@/api';
import type { RepoLocal, RepoGitHub } from '@/api';
import { useMemoryStore, useModelsStore, useUIStore } from '@/store';
import { useToast } from '@/store';
import { replyClarification } from '@/api/client';
import './CommandBar.css';

type Mode = 'new' | 'extend' | 'steer' | 'clarify';

const MAX_STEER = 140;

/** Detects @agentname at the start of text and returns the agent key, or null. */
function detectAgentPrefix(text: string, agentKeys: string[]): string | null {
  if (!text.startsWith('@')) return null;
  const lower = text.toLowerCase();
  for (const key of agentKeys) {
    const prefix = `@${key}`;
    if (lower.startsWith(prefix) && (text.length === prefix.length || text[prefix.length] === ' ')) {
      return key;
    }
  }
  return null;
}

/** Strips @agent prefix from steer text */
function stripAgentPrefix(text: string): string {
  return text.replace(/^@\w+\s*/, '');
}

const PLACEHOLDER: Record<Mode, string> = {
  new:     'Describe tu proyecto... ej: Crear una API REST con autenticación JWT',
  extend:  'Nueva tarea o funcionalidad · escribe @arch, @byte o @pixel para dirigir un agente',
  steer:   'Instrucción directa para el agente (máx. 140 caracteres)',
  clarify: 'Escribe tu respuesta a la aclaración...',
};

/** Extracts a project name from the brief (first sentence or first 50 chars) */
function extractProjectName(brief: string): string {
  const cleaned = brief.trim();
  // Try to get first sentence (up to first ., !, ? or newline)
  const firstSentence = cleaned.split(/[.!?\n]/)[0]?.trim() || cleaned;
  // Limit to 80 characters
  return firstSentence.length > 80 ? firstSentence.slice(0, 77) + '...' : firstSentence;
}

export function CommandBar() {
  const project  = useMemoryStore((state) => state.project);
  const blockers = useMemoryStore((state) => state.blockers);
  const agents   = useModelsStore((state) => state.config?.agents ?? {});
  const setActiveTab       = useUIStore((state) => state.setActiveTab);
  const setProjectViewMode = useUIStore((state) => state.setProjectViewMode);
  const { success, error: showError } = useToast();

  const hasProject = !!project;
  const agentKeys  = Object.keys(agents);

  // Detect pending clarification (from project state or blockers)
  const pending = project?.pending_clarification;
  const hasClarificationFromProject = Boolean(pending && !pending.resolved);
  const clarificationBlocker = blockers.find(
    (b) => Array.isArray(b.questions) && b.questions.length > 0
  );
  const needsClarification = hasClarificationFromProject || clarificationBlocker != null;

  const clarificationQuestions: string[] = hasClarificationFromProject && Array.isArray(pending?.questions)
    ? pending.questions
    : clarificationBlocker?.questions ?? [];

  // Mode
  const getDefaultMode = (): Mode => {
    if (needsClarification) return 'clarify';
    if (!hasProject) return 'new';
    return 'extend';
  };

  const [mode, setMode]         = useState<Mode>(getDefaultMode);
  const [text, setText]         = useState('');
  const [agentId, setAgentId]   = useState(() => agentKeys[0] ?? 'arch');
  const [autoResume, setAutoResume] = useState(true);
  const [gitOpen, setGitOpen]   = useState(false);
  const [repoUrl, setRepoUrl]   = useState('');
  const [repoName, setRepoName] = useState('');
  const [branch, setBranch]     = useState('main');
  const [allowInit, setAllowInit] = useState(false);
  const [clarifyLoading, setClarifyLoading] = useState(false);
  const [reposOpen, setReposOpen] = useState(false);

  // Repos query — only fetches when git panel is open
  const { data: reposData, isLoading: reposLoading } = useRepos(gitOpen);

  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-switch mode when context changes
  useEffect(() => {
    if (needsClarification) {
      setMode('clarify');
    } else if (!hasProject) {
      setMode('new');
    } else if (mode === 'clarify' || mode === 'new') {
      setMode('extend');
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [needsClarification, hasProject]);

  // Auto-resize textarea
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [text]);

  // Auto-detect @agent prefix → switch to steer mode
  useEffect(() => {
    if (mode !== 'extend' && mode !== 'steer') return;
    const detected = detectAgentPrefix(text, agentKeys);
    if (detected) {
      setMode('steer');
      setAgentId(detected);
    } else if (mode === 'steer' && !text.startsWith('@')) {
      setMode('extend');
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text]);

  // Keep agentId valid when agents change
  useEffect(() => {
    const keys = Object.keys(agents);
    if (keys.length && !agents[agentId]) setAgentId(keys[0]);
  }, [agents, agentId]);

  const startMutation = useStartProject({
    onSuccess: (data) => {
      success(data.message || 'Proyecto iniciado');
      setText('');
      setGitOpen(false);
      setRepoUrl(''); setRepoName(''); setBranch('main'); setAllowInit(false);
      setTimeout(() => { setProjectViewMode('view'); setActiveTab('tasks'); }, 1500);
    },
    onError: (err) => showError(String(err)),
  });

  const extendMutation = useExtendProject();
  const steerMutation  = useSendSteer();

  const isLoading =
    startMutation.isPending || extendMutation.isPending ||
    steerMutation.isPending || clarifyLoading;

  const steerMessage = mode === 'steer' ? stripAgentPrefix(text).trim() : '';

  const canSubmit = text.trim().length > 0 && !isLoading &&
    (mode !== 'steer' || (steerMessage.length > 0 && steerMessage.length <= MAX_STEER));

  const handleSubmit = async () => {
    const trimmed = text.trim();
    if (!trimmed) return;

    if (mode === 'clarify') {
      setClarifyLoading(true);
      try {
        const data = await replyClarification({ reply: trimmed, auto_resume: true, source: 'commandbar' });
        success(data.message || 'Aclaración registrada. ARCH retomará la planificación.');
        setText('');
      } catch (err) {
        showError(String(err));
      } finally {
        setClarifyLoading(false);
      }
    } else if (mode === 'new') {
      startMutation.mutate({
        name: extractProjectName(trimmed),
        description: trimmed,
        brief: trimmed,
        repo_url: repoUrl.trim() || undefined,
        repo_name: repoName.trim() || undefined,
        branch: branch.trim() || undefined,
        allow_init_repo: allowInit,
      });
    } else if (mode === 'extend') {
      extendMutation.mutate(
        { brief: trimmed, project_id: project?.id, auto_resume: autoResume, source: 'commandbar' },
        {
          onSuccess: (data) => {
            success(`${data.message} · ${data.task_title}`);
            setText('');
            if (autoResume) setActiveTab('tasks');
          },
          onError: (err) => showError(String(err)),
        }
      );
    } else {
      // steer
      if (!steerMessage) return;
      steerMutation.mutate(
        { agentId, message: steerMessage },
        {
          onSuccess: () => {
            success(`Instrucción enviada a ${agentId.toUpperCase()}`);
            setText('');
          },
          onError: (err) => showError(String(err)),
        }
      );
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      if (canSubmit) handleSubmit();
    }
  };

  const handleModeChange = (newMode: Mode) => {
    if (newMode === mode || newMode === 'clarify') return;
    if ((newMode === 'extend' || newMode === 'steer') && !hasProject) return;
    setMode(newMode);
    setText('');
  };

  const selectRepo = (name: string, url: string | null, defaultBranch: string) => {
    setRepoUrl(url ?? '');
    setRepoName(name);
    setBranch(defaultBranch || 'main');
    setReposOpen(false);
  };

  const agentEntries = Object.entries(agents);

  return (
    <div className={`command-bar command-bar--${mode}`}>

      {/* Inline clarification questions */}
      {mode === 'clarify' && clarificationQuestions.length > 0 && (
        <div className="command-bar__clarify-banner">
          <span className="command-bar__clarify-icon">🧭</span>
          <div className="command-bar__clarify-body">
            <p className="command-bar__clarify-title">
              El equipo necesita tu respuesta para continuar la planificación
            </p>
            <ul className="command-bar__clarify-questions">
              {clarificationQuestions.map((q, i) => (
                <li key={i}>{q}</li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {/* Toolbar: mode selector + contextual options */}
      <div className="command-bar__toolbar">
        <div className="command-bar__mode-group">
          {mode === 'clarify' ? (
            <span className="command-bar__pill active">💬 Aclaración pendiente</span>
          ) : (
            <>
              <button
                className={`command-bar__pill ${mode === 'new' ? 'active' : ''}`}
                onClick={() => handleModeChange('new')}
                type="button"
              >
                🚀 Nuevo
              </button>
              <button
                className={`command-bar__pill ${(mode === 'extend' || mode === 'steer') ? 'active' : ''} ${!hasProject ? 'disabled' : ''}`}
                onClick={() => hasProject && handleModeChange('extend')}
                type="button"
                title={!hasProject ? 'Necesitas un proyecto activo' : undefined}
              >
                {mode === 'steer' ? `🎯 → ${agentId.toUpperCase()}` : '➕ Ampliar'}
              </button>
            </>
          )}
        </div>

        <div className="command-bar__toolbar-right">
          {mode === 'steer' && agentEntries.length > 0 && (
            <select
              className="command-bar__agent-select"
              value={agentId}
              onChange={(e) => setAgentId(e.target.value)}
            >
              {agentEntries.map(([id]) => (
                <option key={id} value={id}>{id.toUpperCase()}</option>
              ))}
            </select>
          )}
          {mode === 'extend' && (
            <label className="command-bar__toggle-label">
              <input
                type="checkbox"
                checked={autoResume}
                onChange={(e) => setAutoResume(e.target.checked)}
              />
              Auto-reanudar
            </label>
          )}
          {mode === 'new' && (
            <button
              className={`command-bar__git-toggle ${gitOpen ? 'open' : ''}`}
              onClick={() => setGitOpen(!gitOpen)}
              type="button"
            >
              ⚙️ Git {gitOpen ? '▲' : '▼'}
            </button>
          )}
        </div>
      </div>

      {/* Git panel (collapsible) */}
      {mode === 'new' && gitOpen && (
        <div className="command-bar__git-panel">

          {/* Repo picker header */}
          <div className="command-bar__git-picker-header">
            <button
              className={`command-bar__git-picker-toggle ${reposOpen ? 'open' : ''}`}
              onClick={() => setReposOpen(!reposOpen)}
              type="button"
            >
              📂 {reposOpen ? 'Ocultar repositorios' : 'Seleccionar repositorio'}
              {repoName && !reposOpen && (
                <span className="command-bar__git-selected"> · {repoName}</span>
              )}
            </button>
          </div>

          {/* Repo list */}
          {reposOpen && (
            <div className="command-bar__repo-list">
              {reposLoading && (
                <div className="command-bar__repo-loading">Cargando repositorios...</div>
              )}

              {/* Local repos */}
              {(reposData?.local ?? []).length > 0 && (
                <div className="command-bar__repo-group">
                  <div className="command-bar__repo-group-label">📁 Locales</div>
                  {reposData!.local.map((r: RepoLocal) => (
                    <button
                      key={r.path}
                      className={`command-bar__repo-item ${repoName === r.name ? 'selected' : ''}`}
                      onClick={() => selectRepo(r.name, r.url, 'main')}
                      type="button"
                    >
                      <span className="command-bar__repo-name">{r.name}</span>
                      {r.url && (
                        <span className="command-bar__repo-url">{r.url.replace('https://github.com/', '')}</span>
                      )}
                    </button>
                  ))}
                </div>
              )}

              {/* GitHub repos */}
              {(reposData?.github ?? []).length > 0 && (
                <div className="command-bar__repo-group">
                  <div className="command-bar__repo-group-label">
                    ☁️ GitHub
                    {reposData?.has_github_token && (
                      <span className="command-bar__repo-badge">conectado</span>
                    )}
                  </div>
                  {reposData!.github.map((r: RepoGitHub) => (
                    <button
                      key={r.full_name}
                      className={`command-bar__repo-item ${repoName === r.name ? 'selected' : ''}`}
                      onClick={() => selectRepo(r.name, r.url, r.default_branch)}
                      type="button"
                    >
                      <span className="command-bar__repo-name">
                        {r.is_local && <span className="command-bar__repo-local-dot" title="Ya clonado localmente" />}
                        {r.name}
                        {r.private && <span className="command-bar__repo-private">privado</span>}
                      </span>
                      {r.description && (
                        <span className="command-bar__repo-url">{r.description}</span>
                      )}
                    </button>
                  ))}
                </div>
              )}

              {/* No token / no repos */}
              {!reposLoading && !reposData?.has_github_token && (reposData?.local ?? []).length === 0 && (
                <div className="command-bar__repo-empty">
                  No hay repos locales · Agrega GITHUB_TOKEN al .env para ver tus repos de GitHub
                </div>
              )}
              {!reposLoading && reposData?.github_error && (
                <div className="command-bar__repo-error">Error GitHub: {reposData.github_error}</div>
              )}
            </div>
          )}

          {/* Manual git fields */}
          <div className="command-bar__git-fields">
            <input
              type="url"
              className="command-bar__git-input"
              value={repoUrl}
              onChange={(e) => setRepoUrl(e.target.value)}
              placeholder="URL del repo  (https://github.com/...)"
            />
            <input
              type="text"
              className="command-bar__git-input"
              value={repoName}
              onChange={(e) => setRepoName(e.target.value)}
              placeholder="Nombre del repo"
            />
            <input
              type="text"
              className="command-bar__git-input command-bar__git-input--short"
              value={branch}
              onChange={(e) => setBranch(e.target.value)}
              placeholder="Rama (main)"
            />
            <label className="command-bar__git-check">
              <input
                type="checkbox"
                checked={allowInit}
                onChange={(e) => setAllowInit(e.target.checked)}
              />
              Inicializar si no existe
            </label>
          </div>
        </div>
      )}

      {/* Main input row */}
      <div className="command-bar__input-row">
        <textarea
          ref={textareaRef}
          className="command-bar__textarea"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={PLACEHOLDER[mode]}
          rows={1}
          maxLength={mode === 'steer' ? MAX_STEER : undefined}
        />

        <div className="command-bar__input-actions">
          {mode === 'steer' && (
            <span className={`command-bar__counter ${steerMessage.length > MAX_STEER ? 'over' : ''}`}>
              {steerMessage.length}/{MAX_STEER}
            </span>
          )}

          <button
            className="command-bar__send"
            onClick={handleSubmit}
            disabled={!canSubmit}
            type="button"
            title="Enviar (Ctrl+Enter)"
          >
            {isLoading ? <span className="command-bar__spinner" /> : '↵'}
          </button>
        </div>
      </div>

      <div className="command-bar__hint">
        {mode === 'new'     && 'Ctrl+Enter para desplegar · ⚙️ Git para vincular repositorio'}
        {mode === 'extend'  && 'Ctrl+Enter para encolar · escribe @arch @byte @pixel para dirigir un agente'}
        {mode === 'steer'   && `Ctrl+Enter para enviar instrucción a ${agentId.toUpperCase()}`}
        {mode === 'clarify' && 'Ctrl+Enter para responder y reanudar la planificación'}
      </div>
    </div>
  );
}
