const platformTitle = "AI Agent Orchestration Platform";

const viewHeaderMeta = {
  home: { kicker: "Landing", title: "Agent Platform Overview" },
  agents: { kicker: "Agents", title: "Agent Registry" },
  skills: { kicker: "Skills", title: "Skill Studio and Contracts" },
  workflows: { kicker: "Workflows", title: "LangGraph Workflow Builder" },
  tools: { kicker: "Tools", title: "Tool Library and Capability Surface" },
};

const viewLabels = {
  home: "Home",
  agents: "Agents",
  skills: "Skills",
  workflows: "Workflows",
  tools: "Tools",
};

export function GlobalHeader({ currentView, busy, onRefresh }) {
  const headerMeta = viewHeaderMeta[currentView] || viewHeaderMeta.home;
  const activeViewLabel = viewLabels[currentView] || "Home";

  return (
    <header className="topbar card">
      <div>
        <p className="kicker">{headerMeta.kicker}</p>
        <h2>{headerMeta.title}</h2>
        <p className="topbar-context">{platformTitle}</p>
      </div>
      <div className="topbar-actions">
        <span className="chip chip-neutral">{activeViewLabel}</span>
        <span className="chip">LangGraph Runtime</span>
        <button className="secondary" type="button" onClick={onRefresh} disabled={busy}>
          Refresh
        </button>
      </div>
    </header>
  );
}
