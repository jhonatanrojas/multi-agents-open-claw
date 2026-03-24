import { useState, useEffect, useRef } from "react";

const API = "http://localhost:8080";
const MINIVERSE_URL = "https://miniverse-public-production.up.railway.app";

const AGENT_META = {
  arch: { name: "ARCH", role: "Coordinator", model: "claude-opus-4", emoji: "🗂️", color: "#7F77DD" },
  byte: { name: "BYTE", role: "Programmer",  model: "claude-sonnet-4", emoji: "💻", color: "#1D9E75" },
  pixel: { name: "PIXEL", role: "Designer",   model: "claude-sonnet-4", emoji: "🎨", color: "#D85A30" },
};

const STATUS_COLOR = {
  working:  { bg: "#EAF3DE", text: "#3B6D11", dot: "#639922" },
  thinking: { bg: "#EEEDFE", text: "#3C3489", dot: "#7F77DD" },
  speaking: { bg: "#E1F5EE", text: "#0F6E56", dot: "#1D9E75" },
  idle:     { bg: "#F1EFE8", text: "#5F5E5A", dot: "#888780" },
  error:    { bg: "#FCEBEB", text: "#791F1F", dot: "#E24B4A" },
  sleeping: { bg: "#E6F1FB", text: "#0C447C", dot: "#378ADD" },
  offline:  { bg: "#F1EFE8", text: "#888780", dot: "#B4B2A9" },
};

const TASK_COLOR = {
  pending:     { bg: "#F1EFE8", text: "#5F5E5A" },
  in_progress: { bg: "#EEEDFE", text: "#3C3489" },
  done:        { bg: "#EAF3DE", text: "#3B6D11" },
  error:       { bg: "#FCEBEB", text: "#791F1F" },
};

function StatusBadge({ state }) {
  const c = STATUS_COLOR[state] || STATUS_COLOR.offline;
  return (
    <span style={{ background: c.bg, color: c.text, fontSize: 11, fontWeight: 500,
      padding: "2px 8px", borderRadius: 20, display: "inline-flex", alignItems: "center", gap: 4 }}>
      <span style={{ width: 6, height: 6, borderRadius: "50%", background: c.dot, display: "inline-block" }} />
      {state || "offline"}
    </span>
  );
}

function AgentCard({ id, memAgent }) {
  const meta = AGENT_META[id];
  const status = memAgent?.status || "offline";
  const c = STATUS_COLOR[status] || STATUS_COLOR.offline;
  const [pulse, setPulse] = useState(false);

  useEffect(() => {
    setPulse(true);
    const t = setTimeout(() => setPulse(false), 600);
    return () => clearTimeout(t);
  }, [status, memAgent?.current_task]);

  return (
    <div style={{
      background: "var(--color-background-primary)",
      border: `0.5px solid var(--color-border-tertiary)`,
      borderTop: `3px solid ${meta.color}`,
      borderRadius: "var(--border-radius-lg)",
      padding: "1rem 1.25rem",
      transition: "all 0.3s ease",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 10 }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 2 }}>
            <span style={{ fontSize: 18 }}>{meta.emoji}</span>
            <span style={{ fontWeight: 500, fontSize: 15 }}>{meta.name}</span>
          </div>
          <div style={{ fontSize: 12, color: "var(--color-text-secondary)" }}>{meta.role}</div>
        </div>
        <StatusBadge state={status} />
      </div>

      <div style={{ fontSize: 12, color: "var(--color-text-secondary)", marginBottom: 8 }}>
        <span style={{
          background: "var(--color-background-secondary)",
          padding: "1px 6px", borderRadius: 4, fontSize: 11, fontFamily: "var(--font-mono)"
        }}>{meta.model}</span>
      </div>

      {memAgent?.current_task && (
        <div style={{
          fontSize: 12, color: "var(--color-text-secondary)",
          background: "var(--color-background-secondary)",
          padding: "6px 8px", borderRadius: 6, marginTop: 6,
          borderLeft: `2px solid ${meta.color}`,
          opacity: pulse ? 0.7 : 1, transition: "opacity 0.3s",
        }}>
          Task: <span style={{ color: "var(--color-text-primary)", fontWeight: 500 }}>{memAgent.current_task}</span>
        </div>
      )}

      {memAgent?.last_seen && (
        <div style={{ fontSize: 11, color: "var(--color-text-tertiary)", marginTop: 8 }}>
          Last seen: {new Date(memAgent.last_seen).toLocaleTimeString()}
        </div>
      )}
    </div>
  );
}

function TaskRow({ task }) {
  const agent = AGENT_META[task.agent];
  const tc = TASK_COLOR[task.status] || TASK_COLOR.pending;
  return (
    <div style={{ padding: "8px 0", borderBottom: "0.5px solid var(--color-border-tertiary)", fontSize: 13 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 11,
          color: "var(--color-text-secondary)", minWidth: 52 }}>{task.id}</span>
        <span style={{ flex: 1, color: "var(--color-text-primary)" }}>{task.title}</span>
        <span style={{ fontSize: 11, display: "flex", alignItems: "center", gap: 4,
          color: agent?.color, fontWeight: 500, minWidth: 56 }}>
          {agent?.emoji} {agent?.name}
        </span>
        <span style={{ background: tc.bg, color: tc.text, fontSize: 11, fontWeight: 500,
          padding: "2px 8px", borderRadius: 20, minWidth: 72, textAlign: "center" }}>
          {task.status}
        </span>
      </div>
      {task.skills?.length > 0 && (
        <div style={{
          marginLeft: 62,
          marginTop: 4,
          fontSize: 11,
          color: "var(--color-text-tertiary)",
          lineHeight: 1.5,
        }}>
          Skills: {task.skills.join(" · ")}
        </div>
      )}
    </div>
  );
}

function LogFeed({ log }) {
  const ref = useRef(null);
  useEffect(() => { if (ref.current) ref.current.scrollTop = ref.current.scrollHeight; }, [log]);

  const agentColor = (a) => AGENT_META[a]?.color || "#888780";

  return (
    <div ref={ref} style={{
      height: 180, overflowY: "auto", fontFamily: "var(--font-mono)",
      fontSize: 11, lineHeight: 1.7,
      background: "var(--color-background-secondary)",
      borderRadius: "var(--border-radius-md)", padding: "8px 12px",
    }}>
      {log.length === 0 && (
        <span style={{ color: "var(--color-text-tertiary)" }}>No events yet...</span>
      )}
      {[...log].reverse().slice(0, 60).map((entry, i) => (
        <div key={i} style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
          <span style={{ color: "var(--color-text-tertiary)", flexShrink: 0 }}>
            {new Date(entry.ts).toLocaleTimeString()}
          </span>
          <span style={{ color: agentColor(entry.agent), flexShrink: 0, minWidth: 36 }}>[{entry.agent}]</span>
          <span style={{ color: "var(--color-text-primary)" }}>{entry.msg}</span>
        </div>
      ))}
    </div>
  );
}

function PhaseTimeline({ phases, tasks }) {
  if (!phases?.length) return null;
  return (
    <div style={{ display: "flex", gap: 0, margin: "8px 0" }}>
      {phases.map((phase, i) => {
        const phaseTasks = tasks.filter(t => t.phase === phase.id);
        const done = phaseTasks.filter(t => t.status === "done").length;
        const total = phaseTasks.length;
        const pct = total ? Math.round((done / total) * 100) : 0;
        const active = phaseTasks.some(t => t.status === "in_progress");
        return (
          <div key={phase.id} style={{ flex: 1, position: "relative", paddingRight: i < phases.length - 1 ? 8 : 0 }}>
            <div style={{ fontSize: 11, color: active ? "#7F77DD" : "var(--color-text-secondary)",
              fontWeight: active ? 500 : 400, marginBottom: 4 }}>{phase.name || phase.id}</div>
            <div style={{ height: 4, background: "var(--color-background-secondary)",
              borderRadius: 4, overflow: "hidden" }}>
              <div style={{ height: "100%", width: `${pct}%`,
                background: done === total && total > 0 ? "#639922" : active ? "#7F77DD" : "#B4B2A9",
                transition: "width 0.5s ease", borderRadius: 4 }} />
            </div>
            <div style={{ fontSize: 10, color: "var(--color-text-tertiary)", marginTop: 3 }}>
              {done}/{total}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default function DevSquadDashboard() {
  const [memory, setMemory] = useState(null);
  const [brief, setBrief] = useState("");
  const [repoUrl, setRepoUrl] = useState("");
  const [repoName, setRepoName] = useState("");
  const [branchName, setBranchName] = useState("");
  const [allowInitRepo, setAllowInitRepo] = useState(false);
  const [starting, setStarting] = useState(false);
  const [activeTab, setActiveTab] = useState("tasks");
  const [connected, setConnected] = useState(false);

  // SSE connection
  useEffect(() => {
    const es = new EventSource(`${API}/api/stream`);
    es.onmessage = (e) => {
      try { setMemory(JSON.parse(e.data)); setConnected(true); } catch {}
    };
    es.onerror = () => setConnected(false);
    return () => es.close();
  }, []);

  const startProject = async () => {
    if (!brief.trim()) return;
    setStarting(true);
    try {
      await fetch(`${API}/api/project/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          brief,
          repo_url: repoUrl.trim() || null,
          repo_name: repoName.trim() || null,
          branch: branchName.trim() || null,
          allow_init_repo: allowInitRepo,
        }),
      });
      setBrief("");
      setRepoUrl("");
      setRepoName("");
      setBranchName("");
      setAllowInitRepo(false);
    } catch (e) { console.error(e); }
    setStarting(false);
  };

  const tasks = memory?.tasks || [];
  const agents = memory?.agents || {};
  const project = memory?.project || {};
  const plan = memory?.plan || {};
  const log = memory?.log || [];

  const taskStats = {
    total: tasks.length,
    done: tasks.filter(t => t.status === "done").length,
    inProgress: tasks.filter(t => t.status === "in_progress").length,
    pending: tasks.filter(t => t.status === "pending").length,
    error: tasks.filter(t => t.status === "error").length,
  };

  const overallPct = taskStats.total ? Math.round((taskStats.done / taskStats.total) * 100) : 0;

  return (
    <div style={{ padding: "1.5rem 1rem", maxWidth: 860, margin: "0 auto" }}>

      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 20, fontWeight: 500 }}>Dev Squad</h2>
          <div style={{ fontSize: 13, color: "var(--color-text-secondary)", marginTop: 2 }}>
            Multi-agent programming team
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ width: 7, height: 7, borderRadius: "50%",
            background: connected ? "#639922" : "#E24B4A", display: "inline-block" }} />
          <span style={{ fontSize: 12, color: "var(--color-text-secondary)" }}>
            {connected ? "Connected" : "Disconnected"}
          </span>
        </div>
      </div>

      {/* Agent Cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0,1fr))", gap: 12, marginBottom: 20 }}>
        {Object.entries(AGENT_META).map(([id]) => (
          <AgentCard key={id} id={id} memAgent={agents[id]} />
        ))}
      </div>

      {/* Project bar */}
      {project.name && (
        <div style={{
          background: "var(--color-background-primary)", border: "0.5px solid var(--color-border-tertiary)",
          borderRadius: "var(--border-radius-lg)", padding: "1rem 1.25rem", marginBottom: 16,
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 10 }}>
            <div>
              <div style={{ fontWeight: 500, fontSize: 14 }}>{project.name}</div>
              <div style={{ fontSize: 12, color: "var(--color-text-secondary)", marginTop: 2 }}>{project.description}</div>
              {(project.repo_path || project.branch || project.output_dir) && (
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8 }}>
                  {project.repo_path && (
                    <span style={{ fontSize: 11, padding: "2px 8px", borderRadius: 20, background: "var(--color-background-secondary)", color: "var(--color-text-secondary)" }}>
                      Repo: {project.repo_path}
                    </span>
                  )}
                  {project.branch && (
                    <span style={{ fontSize: 11, padding: "2px 8px", borderRadius: 20, background: "var(--color-background-secondary)", color: "var(--color-text-secondary)" }}>
                      Branch: {project.branch}
                    </span>
                  )}
                  {project.output_dir && (
                    <span style={{ fontSize: 11, padding: "2px 8px", borderRadius: 20, background: "var(--color-background-secondary)", color: "var(--color-text-secondary)" }}>
                      Output: {project.output_dir}
                    </span>
                  )}
                </div>
              )}
            </div>
            <StatusBadge state={project.status} />
          </div>

          {taskStats.total > 0 && (
            <>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                <div style={{ fontSize: 12, color: "var(--color-text-secondary)" }}>
                  Overall progress
                </div>
                <div style={{ fontSize: 13, fontWeight: 500 }}>{overallPct}%</div>
              </div>
              <div style={{ height: 6, background: "var(--color-background-secondary)", borderRadius: 6, overflow: "hidden", marginBottom: 12 }}>
                <div style={{ height: "100%", width: `${overallPct}%`,
                  background: overallPct === 100 ? "#639922" : "#7F77DD",
                  transition: "width 0.6s ease", borderRadius: 6 }} />
              </div>

              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                {[
                  { label: "Done", val: taskStats.done, bg: "#EAF3DE", tc: "#3B6D11" },
                  { label: "In progress", val: taskStats.inProgress, bg: "#EEEDFE", tc: "#3C3489" },
                  { label: "Pending", val: taskStats.pending, bg: "#F1EFE8", tc: "#5F5E5A" },
                  { label: "Errors", val: taskStats.error, bg: "#FCEBEB", tc: "#791F1F" },
                ].map(s => (
                  <div key={s.label} style={{ background: s.bg, color: s.tc,
                    fontSize: 11, padding: "3px 10px", borderRadius: 20, fontWeight: 500 }}>
                    {s.val} {s.label}
                  </div>
                ))}
              </div>

              {plan.phases?.length > 0 && (
                <div style={{ marginTop: 14 }}>
                  <div style={{ fontSize: 11, color: "var(--color-text-tertiary)", marginBottom: 6 }}>Phases</div>
                  <PhaseTimeline phases={plan.phases} tasks={tasks} />
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* Tabs */}
      <div style={{ display: "flex", gap: 0, borderBottom: "0.5px solid var(--color-border-tertiary)", marginBottom: 16 }}>
        {[["tasks", "Tasks"], ["log", "Event log"], ["files", "Files"]].map(([k, label]) => (
          <button key={k} onClick={() => setActiveTab(k)} style={{
            background: "none", border: "none", cursor: "pointer",
            padding: "8px 16px", fontSize: 13, fontWeight: activeTab === k ? 500 : 400,
            color: activeTab === k ? "var(--color-text-primary)" : "var(--color-text-secondary)",
            borderBottom: activeTab === k ? "2px solid var(--color-text-primary)" : "2px solid transparent",
            marginBottom: -1,
          }}>{label}</button>
        ))}
      </div>

      {activeTab === "tasks" && (
        <div style={{
          background: "var(--color-background-primary)", border: "0.5px solid var(--color-border-tertiary)",
          borderRadius: "var(--border-radius-lg)", padding: "0.75rem 1.25rem",
        }}>
          {tasks.length === 0 ? (
            <div style={{ color: "var(--color-text-tertiary)", fontSize: 13, padding: "12px 0" }}>
              No tasks yet — start a project below.
            </div>
          ) : tasks.map(t => <TaskRow key={t.id} task={t} />)}
        </div>
      )}

      {activeTab === "log" && <LogFeed log={log} />}

      {activeTab === "files" && (
        <div style={{
          background: "var(--color-background-primary)", border: "0.5px solid var(--color-border-tertiary)",
          borderRadius: "var(--border-radius-lg)", padding: "0.75rem 1.25rem",
        }}>
          {(memory?.files_produced || []).length === 0 ? (
            <div style={{ color: "var(--color-text-tertiary)", fontSize: 13, padding: "12px 0" }}>No files yet.</div>
          ) : (memory?.files_produced || []).map((f, i) => (
            <div key={i} style={{ fontFamily: "var(--font-mono)", fontSize: 12,
              padding: "5px 0", borderBottom: "0.5px solid var(--color-border-tertiary)",
              color: "var(--color-text-secondary)" }}>{f}</div>
          ))}
        </div>
      )}

      {/* Project input */}
      <div style={{
        background: "var(--color-background-primary)", border: "0.5px solid var(--color-border-secondary)",
        borderRadius: "var(--border-radius-lg)", padding: "1rem 1.25rem", marginTop: 20,
      }}>
        <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 8 }}>Assign a new project</div>
        <textarea
          value={brief}
          onChange={e => setBrief(e.target.value)}
          placeholder="Describe your project… e.g. 'Build a REST API for a blog with React frontend, FastAPI backend, and SQLite database'"
          rows={3}
          style={{ width: "100%", resize: "vertical", fontFamily: "var(--font-sans)",
            fontSize: 13, boxSizing: "border-box" }}
        />
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginTop: 10 }}>
          <input
            value={repoUrl}
            onChange={e => setRepoUrl(e.target.value)}
            placeholder="Optional repo URL"
            style={{ fontSize: 13, boxSizing: "border-box" }}
          />
          <input
            value={branchName}
            onChange={e => setBranchName(e.target.value)}
            placeholder="Optional branch name"
            style={{ fontSize: 13, boxSizing: "border-box" }}
          />
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginTop: 8 }}>
          <input
            value={repoName}
            onChange={e => setRepoName(e.target.value)}
            placeholder="Optional repo name"
            style={{ fontSize: 13, boxSizing: "border-box" }}
          />
          <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: "var(--color-text-secondary)" }}>
            <input
              type="checkbox"
              checked={allowInitRepo}
              onChange={e => setAllowInitRepo(e.target.checked)}
            />
            Initialize local repo if no URL is given
          </label>
        </div>
        <div style={{ fontSize: 11, color: "var(--color-text-tertiary)", marginTop: 8 }}>
          Leave the repo fields empty if you want ARCH to ask for approval over Telegram.
        </div>
        <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 10 }}>
          <button
            onClick={startProject}
            disabled={starting || !brief.trim()}
            style={{ padding: "6px 20px", fontSize: 13, cursor: brief.trim() ? "pointer" : "not-allowed",
              opacity: brief.trim() ? 1 : 0.5 }}>
            {starting ? "Starting…" : "Start project ↗"}
          </button>
        </div>
      </div>

      {/* Miniverse link */}
      <div style={{ marginTop: 14, fontSize: 12, color: "var(--color-text-tertiary)", textAlign: "center" }}>
        Watch agents live in the pixel world →{" "}
        <a href={MINIVERSE_URL} target="_blank" rel="noopener noreferrer"
          style={{ color: "var(--color-text-info)" }}>Miniverse world</a>
      </div>
    </div>
  );
}
