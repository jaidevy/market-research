export const agentTemplates = {
  research: {
    role: "Research Planner",
    system_prompt: "You break user objectives into evidence-first research tasks and coordinate specialist agents.",
  },
  support: {
    role: "Support Triage Specialist",
    system_prompt: "You classify customer requests, search available knowledge, draft a response, and escalate when needed.",
  },
  concierge: {
    role: "Discord Channel Concierge",
    system_prompt:
      "You accept inbound Discord messages, trigger the configured workflow, and relay a concise structured reply back to the originating Discord channel.",
  },
};

export const initialAgentEditor = () => ({
  id: "",
  name: "",
  role: agentTemplates.research.role,
  description: "",
  model: "nvidia/nemotron-3-super-120b-a12b:free",
  system_prompt: agentTemplates.research.system_prompt,
  channelsText: "internal, discord",
  selectedTools: [],
  selectedSkills: [],
  skillsText: "",
  scheduleText: "{}",
  memoryProfileText: "{}",
  interactionRulesText: "[]",
  guardrailsText: '[{"mode":"strict"}]',
  limitsText: '{"max_daily_runs":25}',
  is_active: true,
});

export const initialToolEditor = () => ({
  id: "",
  name: "",
  description: "",
  category: "ingestion",
  capabilities: ["read"],
  configSchema: [], // [{key: string, type: string}]
  is_active: true,
  is_system: false,
});

export const initialSkillEditor = () => ({
  id: "",
  name: "",
  description: "",
  category: "general",
  trigger: "always",
  priority: 100,
  output_schema: "",
  abort_on_fail: false,
  selectedToolNames: [],
  markdown: "",
  is_active: true,
});

