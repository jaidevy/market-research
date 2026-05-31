# Documentation of Understanding

**Project:** AI Agent Orchestration Platform
**Author:** Jaidev Yadav
**Repository layout:** Django backend, React + Vite frontend, LangGraph runtime, SQLite persistence, Discord channel

Architecture, design decisions, and technical direction are mine. Coding was carried out with GPT-5.5  under my direction. I reviewed, corrected, and steered every implementation decision.

---

## 1. Problem Understanding

The challenge is to build a local-first platform where a user can:

- create AI agents and configure their behavior (role, prompt, tools, channels, skills, memory, limits, guardrails)
- compose agents into collaborative workflows with conditional edges and feedback loops
- execute those workflows on a real runtime that invokes real tools
- interact with at least one agent through an external messaging channel (Discord)
- manage, observe, and debug everything from a web UI

Success means a reproducible local demo where multiple agents collaborate end to end, persist their work, and respond through Discord, all visible in the UI.

## 2. At a Glance

| Area | Choice | Reason |
|---|---|---|
| Frontend | React + Vite | Fast dev loop, simple operator console |
| Backend | Django + DRF | Single coherent API surface and ORM |
| Runtime | LangGraph | Explicit node/edge/state with conditional routing and loops |
| Persistence | SQLite | Zero-setup local-first demo |
| Channel | Discord (webhook + bot) | Required external conversational surface |
| Process model | Single Django process, in-process runtime | Easier to demo and debug |

## 3. Architecture

Full diagram: [docs/architecture-diagram.md](docs/architecture-diagram.md)

Layered responsibilities:

- **UI layer** ([frontend/](frontend/)) — visual operator console for agents, templates, runs, approvals, conversations, Discord controls, monitoring.
- **API layer** ([backend/apps/](backend/apps/)) — DRF apps for `agents`, `runs`, `messaging`, `monitoring`, `common`.
- **Runtime layer** ([backend/services/runtime/](backend/services/runtime/)) — LangGraph workflow execution, tool registry, LLM client, final responder, artifact logging.
- **Channel layer** ([backend/services/channels/](backend/services/channels/)) — Discord webhook and bot gateway with start/stop control.
- **Persistence layer** — SQLite tables for agents, runs, run steps, runtime events, inter-agent messages, approvals, conversations, token/cost ledger.

Communication model (state-based, not peer chat):

1. A run is created from a workflow template and an objective.
2. LangGraph executes nodes through explicit state transitions.
3. Each node persists structured output as a run step (status, payload, tool I/O).
4. Downstream nodes read prior step outputs from shared run state.
5. The final responder composes the user-facing result from accumulated artifacts and delivers it to the originating channel.

This keeps execution inspectable, deterministic, and testable.

## 4. Requirement Coverage (Mapped to the Rubric)

### 4.1 Agent CRUD and configuration

- Endpoints: `GET/POST /api/agents/`, `GET/PATCH/DELETE /api/agents/{id}/`, `POST /api/agents/seed-system/`
- Configurable fields: role, system prompt, model, tools, channels, skills, limits, memory profile, guardrails
- Seeded system agents include `ConciergeAgent`, `ResearchPlannerAgent`, and supporting roles in [backend/services/runtime/workflow_templates.py](backend/services/runtime/workflow_templates.py)

### 4.2 Workflow templates with conditions and feedback loops

- Endpoints: `GET /api/workflow-templates/`, `PUT /api/workflow-templates/{id}/`, `POST /api/workflow-templates/seed-defaults/`, `GET /api/workflow-templates/compatibility/`
- Seeded templates include: `evidence-first-research`, `quality-review-loop`, `support-triage-policy`, `discord-channel-trigger`, `blog-outline-strategy`, `blog-source-research`, `blog-editorial-review`, `blog-guardrail-preview`
- Templates model node-level agents, allowed tools, conditional edges, and review loops (for example, quality review routes back before publish)

### 4.3 Real runtime execution

- Sync and async execution: `POST /api/workflow-templates/{id}/run/`, `POST /api/workflow-templates/{id}/run-async/`
- Orchestrated in [backend/services/runtime/langgraph_workflow.py](backend/services/runtime/langgraph_workflow.py)
- Tool execution via [backend/services/runtime/tool_registry.py](backend/services/runtime/tool_registry.py) with tools such as `web_search`, `read_url`, `knowledge_base_search`, `memory_read`, `memory_write`, `write_artifact`, `ticket_create`, `send_channel_message`, `discord_rw`
- Run control: `GET /api/runs/`, `GET /api/runs/{id}/`, `POST /api/runs/{id}/stop/`

### 4.4 Async communication and persisted history

- Async workflow progression with persisted `InterAgentMessage`, `RunStep`, `RuntimeEvent`, and `ChannelConversation` records
- Endpoints: `GET /api/messages/?run_id={id}`, `GET /api/conversations/`, `DELETE /api/conversations/{id}/delete/`, `GET /api/approvals/`, `PATCH /api/approvals/{id}/`
- Full timeline is visible in the UI

### 4.5 External messaging channel (Discord)

- Provider modes via `DISCORD_PROVIDER`:
  - `agent_tool` — local record-only (default, no external send)
  - `webhook` — outbound posts via `DISCORD_WEBHOOK_URL`
  - `bot` — persistent `discord.py` gateway for two-way delivery
- Control plane: `POST /api/channels/discord/webhook`, `GET /api/channels/discord/bot/status`, `POST /api/channels/discord/bot/start`, `POST /api/channels/discord/bot/stop`
- Implementation: [backend/services/channels/discord.py](backend/services/channels/discord.py), [backend/services/channels/discord_bot.py](backend/services/channels/discord_bot.py), [backend/services/channels/discord_startup.py](backend/services/channels/discord_startup.py)

### 4.6 Monitoring and observability

- Run metrics endpoint: `GET /api/metrics/runs?run_id={id}`
- Persisted runtime events, approvals, artifacts, conversation history
- Artifact logs written to [logs/artifacts/](logs/artifacts/) for run-level traceability
- Token/cost ledger via `TokenCostLedger`

## 5. Validation Evidence

Critical-path tests under [backend/tests/](backend/tests/):

| Concern | Test file |
|---|---|
| Agent CRUD and API | [test_agent_crud.py](backend/tests/test_agent_crud.py) |
| LangGraph workflow execution | [test_langgraph_workflows.py](backend/tests/test_langgraph_workflows.py) |
| Agentic graph runtime | [test_agentic_graph_runtime.py](backend/tests/test_agentic_graph_runtime.py) |
| Message delivery | [test_message_delivery.py](backend/tests/test_message_delivery.py) |
| Discord channel flow | [test_discord_flow.py](backend/tests/test_discord_flow.py) |
| LLM service wiring | [test_llm_service.py](backend/tests/test_llm_service.py), [test_runtime_llm_client.py](backend/tests/test_runtime_llm_client.py) |
| URL/service wiring | [test_urls.py](backend/tests/test_urls.py) |

Run all tests:

```bash
make test
```

Demo walkthrough: [VIDEO_DEMO_SCRIPT_7MIN.md](VIDEO_DEMO_SCRIPT_7MIN.md)

## 6. Technical Decisions and Tradeoffs

### 6.1 Why LangGraph

LangGraph provides explicit graph nodes, edges, conditional routing, and shared state — a direct fit for the required collaborative workflows with feedback loops. It keeps orchestration inspectable and testable, unlike opaque chain-style frameworks. I have used LangGraph in previous work and chose it here with confidence rather than evaluating it for the first time; that familiarity let me direct implementation precisely and review the runtime code with full context.

### 6.2 Why Django + DRF

A single backend gives one coherent surface for configuration, runtime control, persistence, messaging, and monitoring. ORM, migrations, admin, and serializers reduce custom plumbing and accelerate the demo path. Django is my default backend choice; I am fluent here.

### 6.3 Why SQLite

The challenge requires a local-first, single-command setup. SQLite removes infrastructure prerequisites and produces deterministic, reproducible runs for evaluators.

### 6.4 State-based agent communication

Agents communicate by reading and writing structured run-step state instead of opening direct peer chats. This guarantees every interaction is persisted, ordered, and auditable, which is critical for a real runtime claim.

### 6.5 Discord provider abstraction

Three provider modes let the same orchestration code run with no external dependency (`agent_tool`), outbound-only (`webhook`), or full two-way (`bot`). This keeps the demo robust across environments.

### 6.6 Frontend approach

React + Vite was the right choice for a fast local operator console. I can read and follow the frontend code without difficulty, but frontend engineering is not my primary domain. I relied on GPT-5.5 and structured Copilot prompting workflows to keep the UI implementation coherent. The architectural boundaries between UI, API, and runtime are my decisions; the component-level implementation leaned on AI assistance more than the backend did.

## 7. Scope Boundaries

In scope and delivered:

- end-to-end local runtime with real tool calls
- configurable agents, tools, skills, and workflow templates
- Discord integration with persisted conversation timeline
- monitoring, approvals, and run metrics
- critical-path tests and reproducible setup

Intentionally out of scope for the challenge:

- production-grade deployment hardening
- multi-tenant auth and RBAC
- external cloud orchestration

## 8. Known Limitations and Next Steps

Known limitations:

- SQLite is unsuitable for high-throughput production
- observability is sized for evaluation, not enterprise telemetry
- some provider integrations are placeholder-friendly to keep local runs deterministic

Next practical upgrades:

1. Move persistence to PostgreSQL with a deployment-safe settings profile.
2. Add auth, RBAC, and multi-tenant boundaries.
3. Expand retry policies, dead-letter handling, and trace correlation across nodes.
4. Add per-node cost and latency analytics on top of the existing token ledger.

## 9. Development Environment

This project was developed in VS Code using GitHub Copilot in agent mode (GPT-5.5). Structured prompting workflows shaped the development process across different concerns:

- **Diagnosis** — disciplined reproduce-minimise-hypothesise-fix loop for hard bugs and regressions
- **Design discussion** — comparing options and sharpening constraints before committing to implementation
- **TDD** — red-green-refactor loop for runtime and messaging critical paths
- **Evals** — baseline vs candidate behavior checks for runtime execution changes
- **Release readiness** — pre-submission correctness, wiring, and demo reproducibility checks

The AI was given explicit baseline rules: async-first Python, explicit signal path, minimal branching, no dead code, and no compatibility shims.

## 10. How to Reproduce

```bash
make setup-full
make migrate
make run-full
```

- Backend: <http://127.0.0.1:8010>
- Frontend: <http://127.0.0.1:5173>

Then in the UI: seed defaults, run a workflow, observe the run timeline, and send a Discord message to confirm the round trip.
