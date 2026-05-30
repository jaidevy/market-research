export function HomeView({
  readyScore,
  agents,
  busy,
  onRefreshSummary,
}) {
  return (
    <>
      <section className="stats-grid">
        <article className="card stat"><span>Readiness</span><strong>{readyScore}/3</strong></article>
        <article className="card stat"><span>Agents</span><strong>{agents.length}</strong></article>
        <article className="card stat"><span>Runtime</span><strong>LangGraph</strong></article>
      </section>

      <section className="card daily-board home-daily-board">
        <div className="section-head">
          <h3>Platform Scope</h3>
          <button className="secondary" type="button" onClick={onRefreshSummary} disabled={busy}>Refresh</button>
        </div>
        <div className="stats-grid daily-stats">
          <article className="card stat"><span>Agent CRUD</span><strong>Ready</strong></article>
          <article className="card stat"><span>Workflow Templates</span><strong>2+</strong></article>
          <article className="card stat"><span>External Channel</span><strong>Discord</strong></article>
          <article className="card stat"><span>Monitoring</span><strong>Live</strong></article>
        </div>
        <div className="home-matrix-grid">
          <article className="card matrix-card">
            <h4>Required Capabilities</h4>
            <div className="matrix-list">
              <div className="matrix-row"><span>Visual management</span><strong>Agents / Tools / Skills</strong></div>
              <div className="matrix-row"><span>Runtime execution</span><strong>LangGraph</strong></div>
              <div className="matrix-row"><span>Async communication</span><strong>Persisted messages</strong></div>
            </div>
          </article>
          <article className="card matrix-card">
            <h4>Demo Path</h4>
            <div className="matrix-list">
              <div className="matrix-row"><span>Seed</span><strong>Default workflows</strong></div>
              <div className="matrix-row"><span>Run</span><strong>Research or support workflow</strong></div>
              <div className="matrix-row"><span>Inspect</span><strong>Logs, cost, messages</strong></div>
            </div>
          </article>
        </div>
      </section>
    </>
  );
}
