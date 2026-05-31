# Architecture Diagram

This diagram shows the high-level flow between the React frontend, Django API, runtime orchestration, data persistence, and Discord channel integrations.

```mermaid
flowchart LR
    U[Operator in Browser]
    F[Frontend\nReact + Vite]
    A[Backend API\nDjango + DRF]

    subgraph APPS[Backend Apps]
        AG[agents]
        RU[runs]
        ME[messaging]
        MO[monitoring]
        CO[common]
    end

    subgraph RUNTIME[Services Runtime]
        LW[langgraph_workflow]
        LR[llm_client]
        FR[final_responder]
        AR[artifacts]
        TR[tool_registry]
        WT[workflow_templates]
    end

    subgraph CHANNELS[Services Channels]
        DC[discord.py bot]
        WH[discord webhook]
        DS[discord startup and control]
    end

    DB[(SQLite\nrun, message, approval, and metrics data)]
    LA[(Artifact Logs\nlogs/artifacts)]
    DI[Discord]

    U --> F
    F -->|REST API calls| A

    A --> AG
    A --> RU
    A --> ME
    A --> MO
    A --> CO

    RU --> LW
    LW --> LR
    LW --> TR
    LW --> AR
    LW --> FR
    RU --> WT

    AG --> DB
    RU --> DB
    ME --> DB
    MO --> DB

    AR --> LA

    A -->|bot status/start/stop + webhook endpoint| DS
    DS --> DC
    DS --> WH
    WH --> DI
    DC <-->|two-way messages| DI

    DI -->|inbound messages| A
```

## Notes

- Workflow execution is orchestrated through LangGraph nodes and state transitions.
- Inter-agent communication is run-state based and persisted in the database.
- Discord can operate in webhook mode or bot mode, both mediated by backend channel services.
