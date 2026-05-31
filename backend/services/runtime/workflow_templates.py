from __future__ import annotations

from typing import Any
from django.db import connection


def seed_generic_workflow_assets() -> dict[str, Any]:
    from apps.agents.models import Agent, Skill, Tool
    from apps.messaging.models import ApprovalTicket, ChannelConversation, InterAgentMessage
    from apps.monitoring.models import TokenCostLedger
    from apps.runs.models import WorkflowTemplate

    demo_tool_names = {str(spec["name"]) for spec in GENERIC_WORKFLOW_TOOLS}
    demo_skill_names = {str(spec["name"]) for spec in GENERIC_WORKFLOW_SKILLS}
    demo_agent_names = {str(spec["name"]) for spec in GENERIC_WORKFLOW_AGENTS}
    demo_template_names = {str(spec["name"]) for spec in GENERIC_WORKFLOW_TEMPLATES}

    for spec in GENERIC_WORKFLOW_TOOLS:
        defaults = {key: value for key, value in spec.items() if key != "name"}
        defaults["is_system"] = True
        defaults["is_active"] = True
        Tool.objects.update_or_create(name=spec["name"], defaults=defaults)

    for spec in GENERIC_WORKFLOW_SKILLS:
        defaults = {key: value for key, value in spec.items() if key != "name"}
        defaults["is_active"] = True
        Skill.objects.update_or_create(
            name=spec["name"],
            defaults=defaults,
        )

    for spec in GENERIC_WORKFLOW_AGENTS:
        defaults = {key: value for key, value in spec.items() if key != "name"}
        defaults["is_active"] = True
        Agent.objects.update_or_create(name=spec["name"], defaults=defaults)

    templates = []
    for spec in GENERIC_WORKFLOW_TEMPLATES:
        template, _ = WorkflowTemplate.objects.update_or_create(
            name=spec["name"],
            defaults={key: value for key, value in spec.items() if key != "name"},
        )
        templates.append(template)

    # Keep DB/UI strictly aligned to seeded demo assets only.
    Tool.objects.exclude(name__in=demo_tool_names).delete()
    Skill.objects.exclude(name__in=demo_skill_names).delete()
    WorkflowTemplate.objects.exclude(name__in=demo_template_names).delete()

    extra_agent_ids = list(Agent.objects.exclude(name__in=demo_agent_names).values_list("id", flat=True))
    if extra_agent_ids:
        InterAgentMessage.objects.filter(from_agent_id__in=extra_agent_ids).update(from_agent=None)
        InterAgentMessage.objects.filter(to_agent_id__in=extra_agent_ids).update(to_agent=None)
        ApprovalTicket.objects.filter(requested_by_id__in=extra_agent_ids).update(requested_by=None)
        TokenCostLedger.objects.filter(agent_id__in=extra_agent_ids).update(agent=None)
        ChannelConversation.objects.filter(target_agent_id__in=extra_agent_ids).delete()

        # Legacy table from prior architecture can still block deletion in SQLite.
        placeholders = ",".join(["%s"] * len(extra_agent_ids))
        with connection.cursor() as cursor:
            cursor.execute(
                f"DELETE FROM workflows_workflownode WHERE agent_id IN ({placeholders})",
                extra_agent_ids,
            )

        Agent.objects.filter(id__in=extra_agent_ids).delete()

    return {
        "tools": len(GENERIC_WORKFLOW_TOOLS),
        "skills": len(GENERIC_WORKFLOW_SKILLS),
        "agents": len(GENERIC_WORKFLOW_AGENTS),
        "templates": templates,
    }


GENERIC_WORKFLOW_TOOLS: list[dict[str, Any]] = [
    {
        "name": "web_search",
        "description": "Search the web for research context via Google News RSS.",
        "category": "research",
        "capabilities": ["read"],
        "config_schema": {"query": "string"},
    },
    {
        "name": "memory_read",
        "description": "Read persisted workflow or agent memory.",
        "category": "memory",
        "capabilities": ["read"],
        "config_schema": {"key": "string"},
    },
    {
        "name": "memory_write",
        "description": "Write persisted workflow or agent memory.",
        "category": "memory",
        "capabilities": ["write"],
        "config_schema": {"key": "string", "value": "object"},
    },
    {
        "name": "read_url",
        "description": "Read text content from a public URL for research context.",
        "category": "research",
        "capabilities": ["read"],
        "config_schema": {"url": "string"},
    },
    {
        "name": "write_artifact",
        "description": "Write a workflow artifact under the local artifact directory.",
        "category": "research",
        "capabilities": ["write"],
        "config_schema": {"path": "string", "content": "string"},
    },
    {
        "name": "knowledge_base_search",
        "description": "Search the local demo knowledge base for support or policy context.",
        "category": "research",
        "capabilities": ["read"],
        "config_schema": {"query": "string"},
    },
    {
        "name": "ticket_create",
        "description": "Create a local support ticket artifact for human follow-up.",
        "category": "communication",
        "capabilities": ["write"],
        "config_schema": {"summary": "string", "priority": "string"},
    },
    {
        "name": "discord_rw",
        "description": "Read inbound Discord messages and write replies through the active Discord bot or webhook.",
        "category": "communication",
        "capabilities": ["read", "write"],
        "config_schema": {"trigger": "string", "message": "string"},
    },
    {
        "name": "send_channel_message",
        "description": "Prepare a generic outbound channel message for UI/local workflow traces.",
        "category": "communication",
        "capabilities": ["write"],
        "config_schema": {"message": "string", "channel": "string"},
    },
]


GENERIC_WORKFLOW_SKILLS: list[dict[str, Any]] = [
    {
        "name": "evidence-first-research",
        "description": "Ground research briefs in cited tool evidence and flag missing sources.",
        "category": "procedure",
        "trigger": "research_brief",
        "priority": 20,
        "requires_tools": ["web_search"],
        "output_schema": "research_brief",
        "abort_on_fail": False,
        "markdown": (
            "## Evidence-First Research\n"
            "Use web and URL evidence before writing conclusions. Separate observed facts, "
            "uncertainties, and recommended next checks."
        ),
    },
    {
        "name": "quality-review-loop",
        "description": "Review outputs for missing evidence, unsupported claims, and escalation needs.",
        "category": "policy",
        "trigger": "review",
        "priority": 30,
        "requires_tools": [],
        "output_schema": "quality_review",
        "abort_on_fail": False,
        "markdown": (
            "## Quality Review Loop\n"
            "Mark outputs incomplete when they lack evidence, omit the user objective, or require "
            "human escalation. Return specific reasons and a pass/fail decision."
        ),
    },
    {
        "name": "support-triage-policy",
        "description": "Classify support requests by urgency, issue type, and human-escalation need.",
        "category": "procedure",
        "trigger": "support",
        "priority": 25,
        "requires_tools": ["knowledge_base_search"],
        "output_schema": "support_triage",
        "abort_on_fail": False,
        "markdown": (
            "## Support Triage Policy\n"
            "Classify urgency, identify missing customer/account details, retrieve policy context, "
            "draft a clear reply, and escalate billing/refund disputes for human review."
        ),
    },
    {
        "name": "discord-channel-trigger",
        "description": "Route Discord messages to the intended workflow or guide the user to the correct workflow choice.",
        "category": "procedure",
        "trigger": "discord",
        "priority": 10,
        "requires_tools": ["discord_rw"],
        "output_schema": "discord_workflow_routing_decision",
        "abort_on_fail": False,
        "markdown": (
            "## Discord Channel Trigger\n"
            "1. Listen for inbound Discord messages from the bot gateway or webhook.\n"
            "2. Identify whether the user intends to run a workflow, check status, approve/reject a pending step, or needs help choosing a workflow.\n"
            "3. If the intended workflow is clear, ask for confirmation before triggering it; if it is unclear, guide the user with the available workflow options and what each one does.\n"
            "4. Trigger only the confirmed matching workflow, wait for the workflow to complete, and send the final workflow answer back to the originating Discord user or channel.\n"
            "5. If the user asks for status or approval, relay the current status or approval options instead of starting a new workflow."
        ),
    },
    {
        "name": "blog-outline-strategy",
        "description": "Design a clear blog structure, audience angle, and section flow before drafting.",
        "category": "procedure",
        "trigger": "blog_outline",
        "priority": 35,
        "requires_tools": ["memory_read", "memory_write"],
        "output_schema": "blog_outline",
        "abort_on_fail": False,
        "markdown": (
            "## Blog Outline Strategy\n"
            "Define target audience, search intent, core thesis, and section-by-section outline before writing. "
            "Keep the structure practical and outcome-focused."
        ),
    },
    {
        "name": "blog-source-research",
        "description": "Gather timely, relevant web evidence that supports the blog narrative.",
        "category": "procedure",
        "trigger": "blog_research",
        "priority": 36,
        "requires_tools": ["web_search"],
        "output_schema": "blog_research_notes",
        "abort_on_fail": False,
        "markdown": (
            "## Blog Source Research\n"
            "Collect current and credible sources, pull supporting facts, and flag uncertainty or gaps that need clarification."
        ),
    },
    {
        "name": "blog-editorial-review",
        "description": "Review for clarity, flow, and publish readiness.",
        "category": "policy",
        "trigger": "blog_review",
        "priority": 37,
        "requires_tools": [],
        "output_schema": "blog_review_decision",
        "abort_on_fail": False,
        "markdown": (
            "## Blog Editorial Review\n"
            "Check coherence, claim support, readability, and actionability. "
            "Set ready_to_publish=true only when the draft is clear, complete, and compliant with guardrails."
        ),
    },
    {
        "name": "blog-guardrail-preview",
        "description": "Validate draft guardrails and prepare a concise preview before publish.",
        "category": "policy",
        "trigger": "blog_review",
        "priority": 38,
        "requires_tools": [],
        "output_schema": "blog_guardrail_preview",
        "abort_on_fail": False,
        "markdown": (
            "## Blog Guardrail And Preview\n"
            "Run a strict guardrail check against harmful tone, explicit wording, and unsupported direct quotations. "
            "Return clear violations when present. Also produce a short publish-preview summary that can be shown "
            "before final publish. If any guardrail fails, set ready_to_publish=false."
        ),
    },
]


GENERIC_WORKFLOW_AGENTS: list[dict[str, Any]] = [
    {
        "name": "ConciergeAgent",
        "role": "Always-On Discord Concierge",
        "description": "Receives external Discord messages and triggers the support workflow.",
        "system_prompt": "Stay reachable through Discord, acknowledge inbound messages, trigger the configured workflow, and relay the final answer.",
        "tools": ["discord_rw", "send_channel_message"],
        "channels": ["discord", "internal"],
        "skills": ["discord-channel-trigger"],
        "schedule": {"mode": "always_on"},
        "limits": {"max_daily_runs": 100},
        "is_active": True,
    },
    {
        "name": "ResearchPlannerAgent",
        "role": "Research Planner",
        "description": "Clarifies research objectives and breaks them into executable subtasks.",
        "system_prompt": "Plan concise, evidence-first research workflows from the user objective.",
        "tools": ["memory_read", "memory_write"],
        "channels": ["ui", "discord", "internal"],
        "skills": ["evidence-first-research"],
        "is_active": True,
    },
    {
        "name": "WebResearchAgent",
        "role": "Web Researcher",
        "description": "Gathers external context and source snippets.",
        "system_prompt": "Use web tools to gather evidence and summarize source relevance.",
        "tools": ["web_search", "read_url", "memory_read", "memory_write"],
        "channels": ["ui", "discord", "internal"],
        "skills": ["evidence-first-research"],
        "is_active": True,
    },
    {
        "name": "SummarizerAgent",
        "role": "Brief Writer",
        "description": "Produces concise user-facing summaries and artifacts.",
        "system_prompt": "Turn gathered evidence into clear, concise final deliverables.",
        "tools": ["write_artifact", "send_channel_message"],
        "channels": ["ui", "discord", "internal"],
        "skills": ["evidence-first-research"],
        "is_active": True,
    },
    {
        "name": "QualityReviewAgent",
        "role": "Quality Reviewer",
        "description": "Checks outputs for evidence coverage and unsupported claims.",
        "system_prompt": "Review workflow outputs and decide whether another evidence pass is needed.",
        "tools": [],
        "channels": ["ui", "internal"],
        "skills": ["quality-review-loop"],
        "is_active": True,
    },
    {
        "name": "SupportTriageAgent",
        "role": "Support Triage Specialist",
        "description": "Classifies support requests by issue type and urgency.",
        "system_prompt": "Classify support requests and identify escalation needs.",
        "tools": ["memory_read", "memory_write"],
        "channels": ["ui", "discord", "internal"],
        "skills": ["support-triage-policy"],
        "is_active": True,
    },
    {
        "name": "KnowledgeBaseAgent",
        "role": "Knowledge Base Researcher",
        "description": "Retrieves relevant support policy context.",
        "system_prompt": "Search local knowledge base context before drafting support answers.",
        "tools": ["knowledge_base_search"],
        "channels": ["ui", "discord", "internal"],
        "skills": ["support-triage-policy"],
        "is_active": True,
    },
    {
        "name": "ResponseDraftAgent",
        "role": "Support Response Writer",
        "description": "Drafts user-facing support responses.",
        "system_prompt": "Draft helpful, concise support responses grounded in policy context.",
        "tools": ["send_channel_message", "discord_rw"],
        "channels": ["ui", "discord", "internal"],
        "skills": ["support-triage-policy"],
        "is_active": True,
    },
    {
        "name": "EscalationAgent",
        "role": "Escalation Gatekeeper",
        "description": "Creates human handoff tickets when a workflow needs review.",
        "system_prompt": "Escalate billing, refund, safety, or high-risk requests to a human.",
        "tools": ["ticket_create", "send_channel_message"],
        "channels": ["ui", "discord", "internal"],
        "skills": ["support-triage-policy", "quality-review-loop"],
        "is_active": True,
    },
    {
        "name": "BlogPlannerAgent",
        "role": "Blog Strategy Planner",
        "description": "Defines blog objective, audience focus, and section outline.",
        "system_prompt": "Create a practical blog plan with a clear reader promise and a strong section structure.",
        "tools": ["memory_read", "memory_write"],
        "channels": ["ui", "internal"],
        "skills": ["blog-outline-strategy"],
        "is_active": True,
    },
    {
        "name": "BlogResearchAgent",
        "role": "Blog Source Researcher",
        "description": "Collects supporting evidence and source context for the draft.",
        "system_prompt": "Gather relevant and recent evidence that strengthens the planned blog narrative.",
        "tools": ["web_search", "memory_write"],
        "channels": ["ui", "internal"],
        "skills": ["blog-source-research"],
        "is_active": True,
    },
    {
        "name": "BlogWriterAgent",
        "role": "Long-form Blog Writer",
        "description": "Drafts the blog article from plan and research context.",
        "system_prompt": "Write a high-quality, reader-friendly blog draft grounded in supplied research context.",
        "tools": ["write_artifact"],
        "channels": ["ui", "internal"],
        "skills": ["blog-outline-strategy", "blog-source-research"],
        "guardrails": [
            "Never use explicit words.",
            "Never be rude.",
            "Do not directly quote someone.",
        ],
        "is_active": True,
    },
    {
        "name": "BlogEditorAgent",
        "role": "Editorial Reviewer",
        "description": "Reviews draft quality and determines publish readiness.",
        "system_prompt": "Review draft quality, resolve weak spots, and decide whether the draft is ready to publish.",
        "tools": [],
        "channels": ["ui", "internal"],
        "skills": ["blog-editorial-review", "blog-guardrail-preview"],
        "is_active": True,
    },
    {
        "name": "BlogPublisherAgent",
        "role": "Blog Publisher",
        "description": "Prepares and publishes the final blog output artifact and user message.",
        "system_prompt": "Produce the final publish-ready blog output and communicate completion clearly.",
        "tools": ["write_artifact", "send_channel_message"],
        "channels": ["ui", "internal"],
        "skills": ["blog-editorial-review", "blog-guardrail-preview"],
        "guardrails": [
            "Never use explicit words.",
            "Never be rude.",
            "Do not directly quote someone.",
        ],
        "is_active": True,
    },
]


GENERIC_WORKFLOW_TEMPLATES: list[dict[str, Any]] = [
    {
        "name": "Research Brief Workflow",
        "description": "Turn a user question into a sourced research brief with a review loop.",
        "version": "1.0",
        "input_schema": {"objective": "string"},
        "output_schema": {"brief": "string", "artifact_path": "string"},
        "default_agents": [
            "ResearchPlannerAgent",
            "WebResearchAgent",
            "SummarizerAgent",
            "QualityReviewAgent",
        ],
        "nodes": [
            {
                "key": "plan",
                "label": "Plan Research",
                "type": "agent",
                "agent": "ResearchPlannerAgent",
                "tools": ["memory_read"],
                "skills": ["evidence-first-research"],
                "objective": "Clarify the research objective and evidence needs.",
            },
            {
                "key": "web_research",
                "label": "Gather Web Evidence",
                "type": "agent",
                "agent": "WebResearchAgent",
                "tools": ["web_search"],
                "skills": ["evidence-first-research"],
                "objective": "Gather external context and source snippets.",
            },
            {
                "key": "summarize",
                "label": "Write Brief",
                "type": "agent",
                "agent": "SummarizerAgent",
                "tools": ["write_artifact"],
                "skills": ["evidence-first-research"],
                "objective": "Write the research brief artifact.",
            },
            {
                "key": "quality_review",
                "label": "Quality Review",
                "type": "agent",
                "agent": "QualityReviewAgent",
                "tools": [],
                "skills": ["quality-review-loop"],
                "objective": "Check whether the brief has enough evidence.",
            },
            {
                "key": "final",
                "label": "Final Response",
                "type": "final",
                "agent": "SummarizerAgent",
                "tools": ["send_channel_message"],
                "skills": ["evidence-first-research"],
                "objective": "Return the final research brief to the user.",
            },
        ],
        "edges": [
            {"from": "plan", "to": "web_research"},
            {"from": "web_research", "to": "summarize"},
            {"from": "summarize", "to": "quality_review"},
            {
                "from": "quality_review",
                "to": "web_research",
                "condition": {"field": "outputs.quality_review.enough_evidence", "op": "eq", "value": False},
            },
            {
                "from": "quality_review",
                "to": "final",
                "condition": {"field": "outputs.quality_review.enough_evidence", "op": "eq", "value": True},
            },
        ],
        "is_active": True,
    },
    {
        "name": "Customer Support Triage Workflow",
        "description": "Classify a support request, retrieve policy context, draft a reply, and escalate when needed.",
        "version": "1.0",
        "input_schema": {"objective": "string", "customer_id": "string"},
        "output_schema": {"reply": "string", "ticket_id": "string"},
        "default_agents": [
            "SupportTriageAgent",
            "KnowledgeBaseAgent",
            "ResponseDraftAgent",
            "EscalationAgent",
        ],
        "nodes": [
            {
                "key": "triage",
                "label": "Triage Request",
                "type": "agent",
                "agent": "SupportTriageAgent",
                "tools": ["memory_read"],
                "skills": ["support-triage-policy"],
                "objective": "Classify issue type, urgency, and escalation need.",
            },
            {
                "key": "knowledge_base",
                "label": "Retrieve Policy",
                "type": "agent",
                "agent": "KnowledgeBaseAgent",
                "tools": ["knowledge_base_search"],
                "skills": ["support-triage-policy"],
                "objective": "Find relevant policy context.",
            },
            {
                "key": "draft_response",
                "label": "Draft Response",
                "type": "agent",
                "agent": "ResponseDraftAgent",
                "tools": [],
                "skills": ["support-triage-policy"],
                "objective": "Draft a concise customer response.",
            },
            {
                "key": "escalation",
                "label": "Escalation Gate",
                "type": "agent",
                "agent": "EscalationAgent",
                "tools": ["ticket_create"],
                "skills": ["support-triage-policy", "quality-review-loop"],
                "objective": "Create a human handoff ticket when required.",
            },
            {
                "key": "reply",
                "label": "Send Reply",
                "type": "final",
                "agent": "ResponseDraftAgent",
                "tools": ["discord_rw"],
                "skills": ["support-triage-policy"],
                "objective": "Return the response to the user.",
            },
        ],
        "edges": [
            {"from": "triage", "to": "knowledge_base"},
            {"from": "knowledge_base", "to": "draft_response"},
            {"from": "draft_response", "to": "escalation"},
            {"from": "escalation", "to": "reply"},
        ],
        "is_active": True,
    },
    {
        "name": "Blog Writer Workflow",
        "description": "Plan, research, draft, review, and publish a long-form blog post end-to-end.",
        "version": "1.0",
        "input_schema": {"objective": "string", "channel": "string"},
        "output_schema": {"blog_post": "string", "artifact_path": "string"},
        "default_agents": [
            "BlogPlannerAgent",
            "BlogResearchAgent",
            "BlogWriterAgent",
            "BlogEditorAgent",
            "BlogPublisherAgent",
        ],
        "nodes": [
            {
                "key": "blog_plan",
                "label": "Plan Blog",
                "type": "agent",
                "agent": "BlogPlannerAgent",
                "tools": ["memory_read", "memory_write"],
                "skills": ["blog-outline-strategy"],
                "objective": "Define audience, thesis, outline, and narrative approach for the blog.",
            },
            {
                "key": "blog_research",
                "label": "Research Sources",
                "type": "agent",
                "agent": "BlogResearchAgent",
                "tools": ["web_search", "memory_write"],
                "skills": ["blog-source-research"],
                "objective": "Collect supporting external evidence and source snippets.",
            },
            {
                "key": "blog_draft",
                "label": "Write Draft",
                "type": "agent",
                "agent": "BlogWriterAgent",
                "tools": ["write_artifact"],
                "skills": ["blog-outline-strategy", "blog-source-research"],
                "objective": "Draft the full blog article with clear sections and actionable takeaways.",
            },
            {
                "key": "blog_review",
                "label": "Editorial Review",
                "type": "agent",
                "agent": "BlogEditorAgent",
                "tools": [],
                "skills": ["blog-editorial-review", "blog-guardrail-preview"],
                "objective": "Review draft quality, enforce guardrails, and prepare preview guidance.",
            },
            {
                "key": "blog_decision",
                "label": "Editorial Decision",
                "type": "decision",
                "agent": "BlogEditorAgent",
                "tools": [],
                "skills": ["blog-editorial-review", "blog-guardrail-preview"],
                "objective": "Decide whether to loop back for revision or continue to publish.",
            },
            {
                "key": "blog_publish",
                "label": "Publish Final",
                "type": "final",
                "agent": "BlogPublisherAgent",
                "tools": ["write_artifact", "send_channel_message"],
                "skills": ["blog-editorial-review", "blog-guardrail-preview"],
                "objective": "Publish and return the final blog post.",
            },
        ],
        "edges": [
            {"from": "blog_plan", "to": "blog_research"},
            {"from": "blog_research", "to": "blog_draft"},
            {"from": "blog_draft", "to": "blog_review"},
            {"from": "blog_review", "to": "blog_decision"},
            {
                "from": "blog_decision",
                "to": "blog_draft",
                "feedback_loop": True,
                "condition": {"field": "outputs.blog_review.ready_to_publish", "op": "eq", "value": False},
            },
            {
                "from": "blog_decision",
                "to": "blog_publish",
                "condition": {"field": "outputs.blog_review.ready_to_publish", "op": "eq", "value": True},
            },
        ],
        "is_active": True,
    },
]
