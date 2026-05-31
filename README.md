# AI Agent Orchestration Platform 

Local-first platform for configuring AI agents, connecting them into collaborative workflows, executing those workflows on a real runtime, and exposing at least one conversational channel through Discord.

This project is structured for the hiring challenge and focuses on:

- real workflow execution
- persisted agent-to-agent and channel messages
- visual management in a React web UI
- reproducible local setup for demo and evaluation

## Author

**Jaidev Yadav**

## What Is Implemented

### Core capabilities

- Agent CRUD with runtime-facing fields (role, prompt, tools, channels, skills, limits, memory profile)
- Tool and Skill CRUD with compatibility checks
- Workflow template CRUD plus seeded default templates
- LangGraph-based workflow execution (sync and async)
- Persisted run steps, runtime events, inter-agent messages, approvals, and conversations
- Discord ingress path that triggers workflow execution and records inbound and outbound timeline
- Bot gateway controls for two-way Discord mode

### Default templates

- Research Brief Workflow
  - plan task
  - gather context
  - draft brief
  - quality review loop
- Customer Support Triage Workflow
  - classify request
  - lookup policy/context
  - draft response
  - escalate when required

## Architecture

### Backend

- Framework: Django + Django REST Framework
- Runtime: LangGraph
- Persistence: SQLite (local-first)

Main backend slices:

1. backend/apps/agents
2. backend/apps/runs
3. backend/apps/messaging
4. backend/apps/monitoring
5. backend/services/runtime
6. backend/services/channels

### Frontend

- Framework: React + Vite
- Purpose: visual operator console for agents, tools, skills, templates, runs, approvals, conversations, Discord controls, and metrics

## Why LangGraph

LangGraph is used because the challenge requires collaborative workflows with conditions and feedback loops. It provides explicit graph nodes, edges, conditional routing, and state transitions while keeping orchestration logic inspectable and testable.

## How Agents Communicate

Agents in this platform do not communicate as direct peer-to-peer chat sessions. Communication is workflow-mediated through shared run state and persisted step outputs.

High-level flow:

1. A workflow run is created with an objective.
2. The orchestrator executes agents as ordered graph nodes.
3. Each node writes structured output (status, payload, tool usage) to persisted run steps.
4. Downstream nodes read prior step outputs from the same run context.
5. The final responder composes a user-facing result from accumulated artifacts.

This state-based communication model keeps execution traceable, deterministic, and debuggable.

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+

### One-command run (recommended)

```bash
make setup-full
make migrate
make run-full
```

Expected local URLs:

- Backend: <http://127.0.0.1:8010>
- Frontend: <http://127.0.0.1:5173>

### Manual run

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]

cd backend
python manage.py makemigrations
python manage.py migrate
python manage.py runserver 127.0.0.1:8010
```

In another shell:

```bash
cd frontend
npm install
npm run dev
```

## API Surface

### Agents, tools, skills

- POST /api/agents/
- GET /api/agents/
- GET /api/agents/{id}/
- PATCH /api/agents/{id}/
- DELETE /api/agents/{id}/
- POST /api/agents/seed-system/

- GET /api/tools/
- GET /api/tools/compatibility/
- GET /api/skills/

### Workflow runs and templates

- GET /api/runs/
- GET /api/runs/{id}/
- POST /api/runs/{id}/stop/
- POST /api/runs/unified/run/ (legacy endpoint intentionally removed in demo build; returns 410)

- GET /api/workflow-templates/
- PUT /api/workflow-templates/{id}/
- POST /api/workflow-templates/seed-defaults/
- GET /api/workflow-templates/compatibility/
- POST /api/workflow-templates/{id}/run/
- POST /api/workflow-templates/{id}/run-async/

### Messaging and approvals

- GET /api/messages/?run_id={id}
- GET /api/conversations/
- DELETE /api/conversations/{id}/delete/
- GET /api/approvals/
- PATCH /api/approvals/{id}/

### Monitoring

- GET /api/metrics/runs?run_id={id}

### Discord channel endpoints

- POST /api/channels/discord/webhook
- GET /api/channels/discord/bot/status
- POST /api/channels/discord/bot/start
- POST /api/channels/discord/bot/stop

## Discord Integration

Three provider modes are supported through DISCORD_PROVIDER:

- agent_tool (default): local record-only, no external send
- webhook: outbound posts to Discord incoming webhook
- bot: persistent discord.py gateway for two-way delivery

### Webhook mode

Set:

- DISCORD_PROVIDER=webhook
- DISCORD_WEBHOOK_URL=...
- optional DISCORD_WEBHOOK_USERNAME=...
- optional DISCORD_WEBHOOK_SECRET=...

### Bot mode

Set:

- DISCORD_BOT_TOKEN=...
- DISCORD_PROVIDER=bot
- optional DISCORD_BOT_AUTOSTART=true
- optional DISCORD_BOT_TARGET_AGENT=ConciergeAgent

## Demo Script (Evaluator-Friendly)

1. Start backend and frontend.
2. Open Workflows UI and click Seed Defaults.
3. Show both default templates and their nodes, edges, and conditions.
4. Edit one node or edge and save.
5. Run a workflow.
6. Show run steps, inter-agent messages, approvals (if generated), and runtime metrics.
7. Open Discord panel and send a test message through webhook or bot mode.
8. Show conversation timeline and linked run metadata.

## Testing and Quality

### Run tests

From repository root:

```bash
make test
```

Or from backend for targeted suite:

```bash
cd backend
python -m pytest tests/test_message_delivery.py
```

### Lint and type checks

```bash
make lint
make typecheck
```

## Submission Notes

- Runtime behavior is real and persisted: runs, steps, messages, events, and metrics are written to DB.
- The system is local-first and can be demonstrated without cloud dependencies.
- The architecture keeps clear boundaries between UI, runtime orchestration, and persistence.

## Repository Layout

```text
backend/
  config/
  apps/
    agents/
    runs/
    messaging/
    monitoring/
    common/
  services/
    runtime/
    channels/
frontend/
  src/
    api/
    components/
    styles/
    App.jsx
    main.jsx
scripts/
  run_full.py
```
