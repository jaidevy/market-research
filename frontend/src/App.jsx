import { useEffect, useMemo, useState } from "react";
import { request } from "./api/client";
import { CrudSubHeader } from "./components/CrudSubHeader";
import { GlobalHeader } from "./components/GlobalHeader";
import {
  agentTemplates,
  initialAgentEditor,
  initialSkillEditor,
  initialToolEditor,
} from "./state/editorState";
import { HomeView } from "./views/HomeView";

const jsonText = (value) => JSON.stringify(value, null, 2);

const textFromValue = (value, fallbackText = "") => {
  if (value === null || value === undefined) {
    return fallbackText;
  }
  if (typeof value === "string") {
    return value;
  }
  if (Array.isArray(value) || typeof value === "object") {
    return jsonText(value);
  }
  return String(value);
};

const parseJsonOrText = (text, fallback) => {
  const raw = String(text || "").trim();
  if (!raw) {
    return fallback;
  }
  try {
    return JSON.parse(raw);
  } catch {
    return raw;
  }
};

const parseJsonSafely = (text) => {
  if (!text || !String(text).trim()) {
    return null;
  }
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
};

const skillCategories = ["general", "policy", "procedure", "output"];

const skillTriggerPresets = [
  "always",
  "pre_run",
  "post_run",
  "approval_required",
  "channel:discord",
];

const skillPriorityPresets = [10, 25, 50, 100, 200];

/** Convert a plain object to an editable [{key, value}] array. */
const objToPairs = (obj) =>
  Object.entries(obj || {}).map(([key, value]) => ({ key, value: String(value) }));

/** Convert [{key, value}] pairs back to a plain object, skipping empty keys. */
const pairsToObj = (pairs) =>
  Object.fromEntries((pairs || []).filter((p) => p.key.trim()).map((p) => [p.key.trim(), p.value]));

const coerceConditionValue = (value) => {
  const text = String(value ?? "").trim();
  if (text === "true") return true;
  if (text === "false") return false;
  if (text !== "" && !Number.isNaN(Number(text))) return Number(text);
  return value;
};

/** Convert a config-schema object ({key: typeString}) to pairs. */
const schemaToPairs = (obj) =>
  Object.entries(obj || {}).map(([key, type]) => ({ key, type: String(type) }));

/** Convert schema pairs back to {key: typeString}. */
const pairsToSchema = (pairs) =>
  Object.fromEntries((pairs || []).filter((p) => p.key.trim()).map((p) => [p.key.trim(), p.type || "string"]));

const parseAgentLogLine = (line) => {
  const text = String(line || "").trim();
  const matched = text.match(/^\[(.*?)\]\s+\[(.*?)\]\s+\[(.*?)\]\s+(.*)$/);
  if (!matched) {
    return null;
  }
  return {
    time: matched[1],
    channel: matched[2],
    run: matched[3],
    body: matched[4],
  };
};

const extractAgentLogFields = (body) => {
  const text = String(body || "").trim();
  const fields = {};
  const regex = /(\w+)=((?:"(?:\\.|[^"\\])*")|\S+)/g;
  let matched;
  while ((matched = regex.exec(text)) !== null) {
    const key = matched[1];
    let value = matched[2] || "";
    if (value.startsWith('"') && value.endsWith('"')) {
      value = value.slice(1, -1).replace(/\\"/g, '"');
    }
    fields[key] = value;
  }
  return fields;
};

const humanizeStageName = (channel) => {
  const raw = String(channel || "");
  if (!raw.startsWith("AGENT:")) {
    return raw;
  }
  const stage = raw.slice("AGENT:".length).replace(/_/g, " ");
  return stage.replace(/\b\w/g, (ch) => ch.toUpperCase());
};

const readableAgentLogLine = (rawLine) => {
  const parsed = parseAgentLogLine(rawLine);
  if (!parsed) {
    return String(rawLine || "").trim();
  }

  const runLabel = parsed.run.replace(/^run=/i, "Run ");
  const body = String(parsed.body || "").trim();
  const lowerBody = body.toLowerCase();

  if (parsed.channel.startsWith("TOKENS:")) {
    return "";
  }

  if (parsed.channel === "SYSTEM") {
    if (lowerBody.includes("run started")) {
      return `${parsed.time} | System | ${runLabel} started`;
    }
    if (lowerBody.includes("workflow completed")) {
      return `${parsed.time} | System | ${runLabel} completed workflow execution`;
    }
    if (lowerBody.includes("run completed")) {
      return `${parsed.time} | System | ${runLabel} completed`;
    }
    return `${parsed.time} | System | ${runLabel} | ${body}`;
  }

  if (parsed.channel.startsWith("AGENT:")) {
    const stage = humanizeStageName(parsed.channel);
    if (lowerBody === "started") {
      return `${parsed.time} | ${stage} | ${runLabel} started this stage`;
    }
    if (lowerBody === "completed") {
      return `${parsed.time} | ${stage} | ${runLabel} completed this stage`;
    }

    const fields = extractAgentLogFields(body);
    const parts = [];

    if (fields.decision) parts.push(`Decision: ${fields.decision}`);
    if (fields.status) parts.push(`Status: ${fields.status}`);
    if (fields.review_state) parts.push(`Review state: ${fields.review_state.replace(/_/g, " ")}`);
    if (fields.direction) parts.push(`Direction: ${fields.direction}`);
    if (fields.option_side) parts.push(`Variant: ${fields.option_side}`);
    if (fields.confidence) parts.push(`Confidence: ${fields.confidence}`);
    if (fields.provider) parts.push(`Provider: ${fields.provider}`);
    if (fields.model) parts.push(`Model: ${fields.model}`);
    if (fields.tool_calls) parts.push(`Tool calls: ${fields.tool_calls}`);
    if (fields.ticket_status && fields.ticket_status !== "none") parts.push(`Ticket status: ${fields.ticket_status}`);
    if (fields.ticket_id) parts.push(`Ticket ID: ${fields.ticket_id}`);
    if (fields.runtime_allowed) parts.push(`Runtime allowed: ${fields.runtime_allowed}`);
    if (fields.channel_open) parts.push(`Channel open: ${fields.channel_open}`);
    if (fields.output) parts.push(`Output: ${fields.output}`);
    if (fields.reasoning) parts.push(`Reasoning: ${fields.reasoning}`);
    if (fields.thinking) parts.push(`Thinking: ${fields.thinking}`);
    if (fields.summary) parts.push(`Analysis: ${fields.summary}`);

    if (!parts.length) {
      return `${parsed.time} | ${stage} | ${runLabel} | ${body}`;
    }
    return `${parsed.time} | ${stage} | ${runLabel} | ${parts.join(". ")}`;
  }

  if (parsed.channel === "WORKFLOW") {
    return `${parsed.time} | Workflow | ${runLabel} | ${body}`;
  }

  return `${parsed.time} | ${parsed.channel} | ${runLabel} | ${body}`;
};

const timeFromIso = (value) => {
  if (!value) {
    return "--:--:--";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "--:--:--";
  }
  return date.toLocaleTimeString("en-IN", {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
};

const summarizeTalkPayload = (payload) => {
  if (!payload || typeof payload !== "object") {
    return "message exchanged";
  }
  const candidates = [payload.summary, payload.message, payload.text, payload.note, payload.reason];
  for (const candidate of candidates) {
    const text = String(candidate || "").trim();
    if (text) {
      return text;
    }
  }
  const json = jsonText(payload);
  if (json.length > 120) {
    return `${json.slice(0, 117)}...`;
  }
  return json;
};

const readableAgentTalkLine = (row) => {
  const runLabel = row?.run ? `Run ${row.run}` : "Run -";
  const fromAgent = row?.from_agent ? `Agent#${row.from_agent}` : "system";
  const toAgent = row?.to_agent ? `Agent#${row.to_agent}` : "broadcast";
  const status = String(row?.status || "sent").toUpperCase();
  const summary = summarizeTalkPayload(row?.payload);
  return `${timeFromIso(row?.created_at)} | Talk | ${runLabel} | ${fromAgent} -> ${toAgent} | ${status} | ${summary}`;
};

const rowsFromPayload = (data) => {
  if (Array.isArray(data)) {
    return data;
  }
  if (Array.isArray(data?.results)) {
    return data.results;
  }
  if (Array.isArray(data?.items)) {
    return data.items;
  }
  return [];
};

const csvToList = (text) =>
  String(text || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);

const parseSkillsPayload = (value) => {
  if (Array.isArray(value)) {
    return value.map((item) => String(item || "").trim()).filter(Boolean);
  }

  if (value && typeof value === "object") {
    if (Array.isArray(value.skills)) {
      return value.skills.map((item) => String(item || "").trim()).filter(Boolean);
    }
    return Object.values(value).map((item) => String(item || "").trim()).filter(Boolean);
  }

  const raw = String(value || "").trim();
  if (!raw) {
    return [];
  }

  try {
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) {
      return parsed.map((item) => String(item || "").trim()).filter(Boolean);
    }
    if (parsed && typeof parsed === "object") {
      if (Array.isArray(parsed.skills)) {
        return parsed.skills.map((item) => String(item || "").trim()).filter(Boolean);
      }
      return Object.values(parsed).map((item) => String(item || "").trim()).filter(Boolean);
    }
  } catch {
    // Fall through to freeform parsing for markdown or comma/newline lists.
  }

  return raw
    .split(/\r?\n|,/)
    .map((item) => item.replace(/^[-*]\s*/, "").trim())
    .filter(Boolean);
};

const skillNamesFromValue = (value) => [...new Set(parseSkillsPayload(value))];

const skillsTextFromValue = (value) => jsonText(skillNamesFromValue(value));

const humanizeActivityEvent = (event) => {
  const value = String(event || "activity").replace(/_/g, " ").trim();
  return value ? value[0].toUpperCase() + value.slice(1) : "Activity";
};

const humanizeActivityAgent = (agent) => {
  return String(agent || "copilot").replace(/_/g, " ").trim();
};

const summarizeActivityRow = (row) => {
  const eventName = String(row?.event || "").trim();
  const detail = String(row?.detail || "").trim();

  // Convert router debug detail into readable status text.
  if (/\bintent=\S+/i.test(detail) && /\bconfidence=\S+/i.test(detail)) {
    const pairs = {};
    detail.replace(/(\w+)=([^\s]+)/g, (_, key, value) => {
      pairs[String(key || "").toLowerCase()] = String(value || "");
      return "";
    });
    const intent = String(pairs.intent || "general").toLowerCase();
    const mode = String(pairs.mode || "single_agent").replace(/_/g, " ").toLowerCase();
    const symbol = String(pairs.symbol || "none").toUpperCase();
    const confidence = Number.parseFloat(String(pairs.confidence || "0"));
    const confidencePct = Number.isFinite(confidence) ? Math.round(confidence * 100) : 0;
    return `Route selected: ${intent} (${mode}), symbol ${symbol}, confidence ${confidencePct}%.`;
  }

  if (eventName === "intent_resolution") {
    return "Classified the request and decided a clarification is needed.";
  }
  if (eventName === "intent_routed" || eventName === "route_selected") {
    return "Chose the best route for this request.";
  }
  if (eventName === "model_dispatch") {
    return "Started model-backed analysis.";
  }
  if (eventName === "session_memory_read") {
    return detail || "Loaded session context for follow-up routing.";
  }
  if (eventName === "session_memory_write") {
    return detail || "Saved latest symbol and intent into session memory.";
  }
  if (eventName === "tool_request") {
    return detail.replace(/^tool request:\s*/i, "Used tool: ");
  }
  if (eventName === "tool_response") {
    return detail.replace(/^tool response:\s*/i, "Received tool result: ");
  }
  if (eventName === "agent_tool_intent") {
    return detail.replace(/^tool intent:\s*/i, "Prepared tool action: ");
  }
  if (eventName === "analysis_error") {
    return `Analysis failed: ${detail}`;
  }
  if (detail) {
    return detail;
  }
  return humanizeActivityEvent(row?.event);
};

const activityToneFromRow = (row) => {
  const eventName = String(row?.event || "").trim().toLowerCase();
  const detail = String(row?.detail || "").trim().toLowerCase();

  if (eventName.includes("error") || detail.includes("failed") || detail.includes("error")) {
    return "error";
  }
  if (detail.includes("completed") || detail.includes("done") || eventName.includes("done")) {
    return "done";
  }
  if (detail.includes("started") || detail.includes("working") || eventName.includes("thinking") || eventName.includes("routing")) {
    return "active";
  }
  return "info";
};

const activityTitleFromRow = (row) => {
  const eventName = String(row?.event || "").trim();
  if (!eventName) {
    return "Activity";
  }
  if (eventName === "thinking") {
    return "Reasoning";
  }
  if (eventName === "routing") {
    return "Routing";
  }
  if (eventName === "activity") {
    return "Execution";
  }
  return humanizeActivityEvent(eventName);
};

const dedupeActivityRows = (rows) => {
  const normalized = Array.isArray(rows) ? rows : [];
  const deduped = [];
  let lastSignature = "";

  normalized.forEach((row) => {
    const title = activityTitleFromRow(row);
    const agent = humanizeActivityAgent(row?.agent);
    const summary = summarizeActivityRow(row);
    const signature = `${title}|${agent}|${summary}`;
    if (signature === lastSignature) {
      return;
    }
    deduped.push(row);
    lastSignature = signature;
  });

  return deduped;
};

const compactActivityItems = (rows) => {
  const dedupedRows = dedupeActivityRows(rows);
  const items = [];
  let previousAgent = "";

  dedupedRows.forEach((row) => {
    const currentAgent = humanizeActivityAgent(row?.agent);
    if (previousAgent && currentAgent && previousAgent !== currentAgent) {
      items.push({
        kind: "switch",
        fromAgent: previousAgent,
        toAgent: currentAgent,
      });
    }
    items.push({
      kind: "step",
      row,
    });
    previousAgent = currentAgent;
  });

  return items;
};

const listTextFromStored = (value) => {
  if (Array.isArray(value)) {
    return value.map((item) => String(item || "").trim()).filter(Boolean).join("\n");
  }

  const parsed = parseJsonSafely(value);
  if (Array.isArray(parsed)) {
    return parsed.map((item) => String(item || "").trim()).filter(Boolean).join("\n");
  }

  return String(value || "")
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean)
    .join("\n");
};

const listStoreFromInput = (value) => jsonText(
  String(value || "")
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean)
);

const updateObjectText = (text, updater) => {
  const parsed = parseJsonSafely(text);
  const base = parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
  return jsonText(updater(base));
};

/**
 * Given a list of selected skill names, return the union of all tools
 * required by those skills as tool objects (with capabilities) ready for
 * the agent's `tools` field. Falls back gracefully when a tool isn't in
 * the library yet.
 */
const deriveToolsFromSkills = (selectedSkillNames, allSkills, allTools) => {
  const toolMap = new Map(allTools.map((t) => [t.name, t]));
  const requiredToolNames = new Set(
    selectedSkillNames.flatMap((skillName) => {
      const skill = allSkills.find((s) => s.name === skillName);
      return Array.isArray(skill?.requires_tools) ? skill.requires_tools : [];
    })
  );
  return [...requiredToolNames].map((name) => {
    const tool = toolMap.get(name);
    return tool
      ? { name: tool.name, capabilities: [...(tool.capabilities || [])] }
      : { name, capabilities: [] };
  });
};

const deriveWorkflowNodeBindingsFromAgent = (agentName, allAgents) => {
  const selectedAgent = allAgents.find((agent) => String(agent?.name || "") === String(agentName || ""));
  if (!selectedAgent) {
    return { tools: [], skills: [] };
  }

  const boundTools = Array.isArray(selectedAgent.tools)
    ? [...new Set(selectedAgent.tools
      .map((tool) => {
        if (typeof tool === "string") return tool;
        if (tool && typeof tool === "object" && tool.name) return String(tool.name);
        return "";
      })
      .map((name) => String(name || "").trim())
      .filter(Boolean))]
    : [];

  const boundSkills = [...new Set(parseSkillsPayload(selectedAgent.skills).map((name) => String(name || "").trim()).filter(Boolean))];
  return { tools: boundTools, skills: boundSkills };
};

const skillPreviewThemeMap = {
  general: {
    bg: "linear-gradient(135deg, #f8fafc 0%, #eef2ff 100%)",
    border: "#cbd5e1",
    shadow: "0 18px 40px rgba(148, 163, 184, 0.22)",
  },
  policy: {
    bg: "linear-gradient(135deg, #fff7ed 0%, #ffedd5 100%)",
    border: "#fdba74",
    shadow: "0 18px 40px rgba(249, 115, 22, 0.18)",
  },
  procedure: {
    bg: "linear-gradient(135deg, #ecfeff 0%, #cffafe 100%)",
    border: "#67e8f9",
    shadow: "0 18px 40px rgba(6, 182, 212, 0.18)",
  },
  output: {
    bg: "linear-gradient(135deg, #faf5ff 0%, #ede9fe 100%)",
    border: "#c4b5fd",
    shadow: "0 18px 40px rgba(139, 92, 246, 0.18)",
  },
  ingestion: {
    bg: "linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%)",
    border: "#93c5fd",
    shadow: "0 18px 40px rgba(59, 130, 246, 0.18)",
  },
  memory: {
    bg: "linear-gradient(135deg, #f5f3ff 0%, #ede9fe 100%)",
    border: "#c4b5fd",
    shadow: "0 18px 40px rgba(124, 58, 237, 0.18)",
  },
  quality: {
    bg: "linear-gradient(135deg, #fff1f2 0%, #ffe4e6 100%)",
    border: "#fda4af",
    shadow: "0 18px 40px rgba(244, 63, 94, 0.18)",
  },
  support: {
    bg: "linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%)",
    border: "#86efac",
    shadow: "0 18px 40px rgba(34, 197, 94, 0.18)",
  },
  research: {
    bg: "linear-gradient(135deg, #f0fdfa 0%, #ccfbf1 100%)",
    border: "#5eead4",
    shadow: "0 18px 40px rgba(20, 184, 166, 0.18)",
  },
  communication: {
    bg: "linear-gradient(135deg, #fefce8 0%, #fef3c7 100%)",
    border: "#fcd34d",
    shadow: "0 18px 40px rgba(245, 158, 11, 0.18)",
  },
  monitoring: {
    bg: "linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%)",
    border: "#cbd5e1",
    shadow: "0 18px 40px rgba(100, 116, 139, 0.18)",
  },
};

const getSkillPreviewTheme = (category, abortOnFail) => {
  const resolvedCategory = String(category || "general").toLowerCase();
  const baseTheme = skillPreviewThemeMap[resolvedCategory] || skillPreviewThemeMap.general;

  if (!abortOnFail) {
    return baseTheme;
  }

  return {
    bg: `linear-gradient(135deg, ${baseTheme.border}22 0%, ${baseTheme.border}11 100%), ${baseTheme.bg}`,
    border: "#ef4444",
    shadow: "0 22px 44px rgba(239, 68, 68, 0.18)",
  };
};

const IconActionButton = ({ icon, label, tone = "slate", className = "", type = "button", ...props }) => (
  <button
    {...props}
    type={type}
    className={`icon-action-button icon-action-${tone}${className ? ` ${className}` : ""}`}
    aria-label={label}
    title={label}
    data-tooltip={label}
  >
    <span aria-hidden="true">{icon}</span>
  </button>
);

const NODE_TYPE_COLOR = {
  agent: { fill: "#dbeafe", stroke: "#3b82f6", text: "#1d4ed8" },
  tool: { fill: "#d1fae5", stroke: "#10b981", text: "#065f46" },
  decision: { fill: "#fef3c7", stroke: "#f59e0b", text: "#92400e" },
  final: { fill: "#ede9fe", stroke: "#8b5cf6", text: "#4c1d95" },
};
const NODE_W = 130;
const NODE_H = 56;
const H_GAP = 60;
const V_GAP = 56;

function layoutNodes(rawNodes, rawEdges) {
  if (!rawNodes.length) return [];
  const keys = rawNodes.map((n) => String(n.key || n.node_key || ""));
  const keySet = new Set(keys);
  // Build adjacency for topo sort
  const inDeg = Object.fromEntries(keys.map((k) => [k, 0]));
  const adj = Object.fromEntries(keys.map((k) => [k, []]));
  for (const edge of rawEdges) {
    const s = String(edge.from || "");
    const t = String(edge.to || "");
    if (keySet.has(s) && keySet.has(t) && s !== t) {
      adj[s].push(t);
      inDeg[t] = (inDeg[t] || 0) + 1;
    }
  }
  // Kahn's algorithm for layers
  const layer = Object.fromEntries(keys.map((k) => [k, 0]));
  const queue = keys.filter((k) => inDeg[k] === 0);
  let head = 0;
  while (head < queue.length) {
    const curr = queue[head++];
    for (const next of adj[curr]) {
      inDeg[next]--;
      layer[next] = Math.max(layer[next], layer[curr] + 1);
      if (inDeg[next] === 0) queue.push(next);
    }
  }
  // Group by layer
  const layerGroups = {};
  for (const k of keys) {
    const l = layer[k] || 0;
    if (!layerGroups[l]) layerGroups[l] = [];
    layerGroups[l].push(k);
  }
  const maxLayer = Math.max(...Object.keys(layerGroups).map(Number));
  const positions = {};
  for (let l = 0; l <= maxLayer; l++) {
    const group = layerGroups[l] || [];
    const totalW = group.length * NODE_W + (group.length - 1) * H_GAP;
    const startX = -totalW / 2 + NODE_W / 2;
    group.forEach((k, i) => {
      positions[k] = { x: startX + i * (NODE_W + H_GAP), y: l * (NODE_H + V_GAP) };
    });
  }
  return rawNodes.map((n) => {
    const k = String(n.key || n.node_key || "");
    return { ...n, _layoutX: positions[k]?.x ?? 0, _layoutY: positions[k]?.y ?? 0 };
  });
}

function WorkflowGraphPreview({ nodes, edges, onNodeClick }) {
  if (!nodes.length) {
    return <p className="subtle wf-graph-empty">No nodes yet. Add nodes in the Node Editor tab.</p>;
  }

  const edgeLabel = (edge) => {
    const condition = edge?.condition;
    if (!condition || typeof condition !== "object") {
      return "";
    }
    const field = String(condition.field || "").trim();
    const opRaw = String(condition.op || "eq").trim().toLowerCase();
    const op = opRaw === "eq" ? "=" : opRaw === "ne" ? "!=" : opRaw;
    const value = String(condition.value ?? "").trim();
    const fieldTail = field ? field.split(".").slice(-1)[0] : "condition";
    const text = `${fieldTail} ${op} ${value}`.trim();
    return text.length > 28 ? `${text.slice(0, 27)}…` : text;
  };

  const laid = layoutNodes(nodes, edges);
  const xs = laid.map((n) => n._layoutX);
  const ys = laid.map((n) => n._layoutY);
  const minX = Math.min(...xs) - NODE_W / 2 - 36;
  const maxX = Math.max(...xs) + NODE_W / 2 + 140;
  const minY = Math.min(...ys) - NODE_H / 2 - 40;
  const maxY = Math.max(...ys) + NODE_H / 2 + 44;
  const vw = maxX - minX;
  const vh = maxY - minY;
  const posMap = Object.fromEntries(laid.map((n) => [String(n.key || n.node_key || ""), n]));

  return (
    <div className="wf-graph-wrap">
      <svg
        className="wf-graph-svg"
        viewBox={`${minX} ${minY} ${vw} ${vh}`}
        aria-label="Workflow graph preview"
      >
        <defs>
          <marker id="arrowhead" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
            <polygon points="0 0, 8 3, 0 6" fill="#6b7fa3" />
          </marker>
          <marker id="arrowhead-fb" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
            <polygon points="0 0, 8 3, 0 6" fill="#f59e0b" />
          </marker>
        </defs>
        {edges.map((edge, i) => {
          const s = posMap[String(edge.from || "")];
          const t = posMap[String(edge.to || "")];
          if (!s || !t) return null;
          const isSelfLoop = String(edge.from || "") === String(edge.to || "");
          const isFb = Boolean(edge.feedback_loop) || t._layoutY <= s._layoutY;
          const laneOffset = 26 + (i % 3) * 16;
          let pathD = "";
          let labelX = 0;
          let labelY = 0;

          if (isSelfLoop) {
            const sx = s._layoutX + NODE_W / 2 - 10;
            const sy = s._layoutY - NODE_H / 2 + 8;
            const rx = 34;
            const ry = 24;
            pathD = `M${sx},${sy} C${sx + rx},${sy - ry} ${sx - rx},${sy - ry} ${sx - 2},${sy}`;
            labelX = sx;
            labelY = sy - ry - 6;
          } else if (isFb) {
            const sx = s._layoutX + NODE_W / 2;
            const sy = s._layoutY;
            const tx = t._layoutX + NODE_W / 2;
            const ty = t._layoutY;
            const laneX = Math.max(sx, tx) + laneOffset;
            pathD = `M${sx},${sy} C${laneX},${sy} ${laneX},${ty} ${tx},${ty}`;
            labelX = laneX + 6;
            labelY = (sy + ty) / 2;
          } else {
            const sx = s._layoutX;
            const sy = s._layoutY + NODE_H / 2;
            const tx = t._layoutX;
            const ty = t._layoutY - NODE_H / 2;
            const bend = Math.max(20, Math.min(44, Math.abs(tx - sx) * 0.25));
            pathD = `M${sx},${sy} C${sx},${sy + bend} ${tx},${ty - bend} ${tx},${ty}`;
            labelX = (sx + tx) / 2;
            labelY = (sy + ty) / 2 - 8;
          }

          const label = edgeLabel(edge);
          const textWidth = Math.max(28, label.length * 5.5);
          return (
            <g key={`edge-${i}`} className={isFb ? "wf-graph-edge wf-graph-edge-feedback" : "wf-graph-edge"}>
              <path
                d={pathD}
                fill="none"
                stroke={isFb ? "#f59e0b" : "#6b7fa3"}
                strokeWidth={isFb ? "1.8" : "1.5"}
                strokeDasharray={isFb ? "4 3" : undefined}
                markerEnd={isFb ? "url(#arrowhead-fb)" : "url(#arrowhead)"}
                opacity="0.9"
              />
              {label ? (
                <g className="wf-graph-edge-label" transform={`translate(${labelX}, ${labelY})`}>
                  <rect x={-textWidth / 2} y={-8} rx="4" ry="4" width={textWidth} height="16" />
                  <text textAnchor="middle" y="4">{label}</text>
                </g>
              ) : null}
            </g>
          );
        })}
        {laid.map((node) => {
          const k = String(node.key || node.node_key || "");
          const label = String(node.label || k || "?");
          const type = String(node.node_type || "agent");
          const tools = Array.isArray(node.tools) ? node.tools.map((tool) => String(tool || "").trim()).filter(Boolean) : [];
          const toolLine = tools.length ? `tools: ${tools.join(", ")}` : "tools: none";
          const colors = NODE_TYPE_COLOR[type] || { fill: "#f0f4fa", stroke: "#8b9cb3", text: "#374151" };
          const x = node._layoutX - NODE_W / 2;
          const y = node._layoutY - NODE_H / 2;
          const truncated = label.length > 14 ? label.slice(0, 13) + "…" : label;
          const truncatedTools = toolLine.length > 24 ? toolLine.slice(0, 23) + "…" : toolLine;
          return (
            <g
              key={k}
              className="wf-graph-node"
              role="button"
              tabIndex={0}
              aria-label={`Node: ${label}`}
              onClick={() => onNodeClick && onNodeClick(node)}
              onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onNodeClick && onNodeClick(node); } }}
            >
              <rect
                x={x} y={y} width={NODE_W} height={NODE_H}
                rx="8" ry="8"
                fill={colors.fill}
                stroke={colors.stroke}
                strokeWidth="1.6"
              />
              <text
                x={node._layoutX} y={node._layoutY - 12}
                textAnchor="middle"
                fontSize="11"
                fontWeight="700"
                fill={colors.text}
              >
                {truncated}
              </text>
              <text
                x={node._layoutX} y={node._layoutY + 2}
                textAnchor="middle"
                fontSize="9"
                fill={colors.text}
                opacity="0.72"
              >
                {type}
              </text>
              <text
                x={node._layoutX} y={node._layoutY + 14}
                textAnchor="middle"
                fontSize="8"
                fill={colors.text}
                opacity="0.65"
              >
                {truncatedTools}
              </text>
            </g>
          );
        })}
      </svg>
      <div className="wf-graph-legend">
        {Object.entries(NODE_TYPE_COLOR).map(([type, c]) => (
          <span key={type} className="wf-graph-legend-item">
            <span className="wf-graph-legend-dot" style={{ background: c.fill, borderColor: c.stroke }} />
            {type}
          </span>
        ))}
        <span className="wf-graph-legend-item wf-graph-legend-fb">
          <span className="wf-graph-legend-line wf-graph-legend-line-fb" />feedback
        </span>
      </div>
    </div>
  );
}

export function App() {
  const [agentEditor, setAgentEditor] = useState(initialAgentEditor);
  const [nodeDraft, setNodeDraft] = useState({
    node_key: "",
    node_type: "agent",
    label: "",
    objective: "",
    agent: "",
    toolsText: "",
    skillsText: "",
    configPairs: [],           // [{key: string, value: string}]
    x: 120,
    y: 80,
  });
  const [editingNodeIndex, setEditingNodeIndex] = useState(null); // null = add mode; number = edit mode
  const [edgeDraft, setEdgeDraft] = useState({
    source_node_key: "",
    target_node_key: "",
    conditionPairs: [],        // [{key: string, value: string}]
    feedbackLoop: false,
  });
  const [editingEdgeIndex, setEditingEdgeIndex] = useState(null); // null = add mode; number = edit mode
  const [workflowTemplates, setWorkflowTemplates] = useState([]);
  const [selectedWorkflowTemplateId, setSelectedWorkflowTemplateId] = useState("");
  const [workflowCrudView, setWorkflowCrudView] = useState("grid"); // "grid" | "editor"
  const [workflowSearch, setWorkflowSearch] = useState("");
  const [workflowStatusFilter, setWorkflowStatusFilter] = useState("all");
  const [workflowTemplateDraft, setWorkflowTemplateDraft] = useState({
    name: "",
    description: "",
    version: "1.0",
  });
  const [workflowBuilderMode, setWorkflowBuilderMode] = useState("basic"); // basic | advanced
  const [workflowEditorTab, setWorkflowEditorTab] = useState("node"); // node | edge
  const [workflowRunForm, setWorkflowRunForm] = useState({
    objective: "Research the latest developments in open-source AI agent frameworks and produce a short comparison brief.",
    customer_id: "Jaidev",
  });
  const [discordWebhookForm, setDiscordWebhookForm] = useState({
    body: "I cannot find my invoice. Can billing resend it?",
  });
  const [discordConversations, setDiscordConversations] = useState([]);
  const [discordBotStatus, setDiscordBotStatus] = useState(null);
  const [metricsRunId, setMetricsRunId] = useState("");
  const [isManualRunFocus, setIsManualRunFocus] = useState(false);
  const [isRunStreaming, setIsRunStreaming] = useState(false);
  const [isLiveLogsPaused, setIsLiveLogsPaused] = useState(false);
  const [out, setOut] = useState({});
  const [busy, setBusy] = useState(false);
  const [agents, setAgents] = useState([]);
  const [currentView, setCurrentView] = useState("workflowLauncher");
  const [runHistory, setRunHistory] = useState([]);
  const [toasts, setToasts] = useState([]);
  const [selectedAgentId, setSelectedAgentId] = useState("");
  const [agentView, setAgentView] = useState("grid"); // "grid" | "editor"
  const [agentSearch, setAgentSearch] = useState("");
  const [tools, setTools] = useState([]);
  const [toolView, setToolView] = useState("grid");
  const [toolSearch, setToolSearch] = useState("");
  const [toolCategoryFilter, setToolCategoryFilter] = useState("all");
  const [toolCapabilityFilter, setToolCapabilityFilter] = useState("all");
  const [toolStatusFilter, setToolStatusFilter] = useState("all");
  const [toolSort, setToolSort] = useState("category");
  const [toolEditor, setToolEditor] = useState(initialToolEditor);
  const [skills, setSkills] = useState([]);
  const [skillView, setSkillView] = useState("grid");
  const [skillSearch, setSkillSearch] = useState("");
  const [skillCategoryFilter, setSkillCategoryFilter] = useState("all");
  const [skillEditor, setSkillEditor] = useState(initialSkillEditor);
  const [isNavOpen, setIsNavOpen] = useState(false);

  const navItems = [
    // ── Monitor ──────────────────────────────────────────────────────
    { key: "home",       label: "Dashboard",      icon: "📊", group: "Monitor" },
    // ── Execute ──────────────────────────────────────────────────────
    { key: "workflowLauncher", label: "Launcher", icon: "▶", group: "Execute" },
    { key: "discordMessaging", label: "Discord Messaging", icon: "◆", group: "Execute" },
    // ── Configure ────────────────────────────────────────────────────
    { key: "workflowCrud", label: "Workflows", icon: "▦", group: "Configure" },
    { key: "agents",     label: "Agents",         icon: "🤖", group: "Configure" },
    { key: "skills",     label: "Skills",         icon: "⚡", group: "Configure" },
    { key: "tools",      label: "Tool Library",   icon: "🔧", group: "Configure" },
  ];

  const updateOut = (key, value) => {
    setOut((prev) => ({ ...prev, [key]: jsonText(value) }));
  };

  const humanizeKey = (key) => key.replace(/([a-z])([A-Z])/g, "$1 $2").replace(/^./, (s) => s.toUpperCase());

  const pushToast = (type, title, detail) => {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    setToasts((prev) => [...prev, { id, type, title, detail }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((toast) => toast.id !== id));
    }, 3600);
  };

  const hydrateAgents = async () => {
    const data = await request("GET", "/agents/");
    const rows = Array.isArray(data) ? data : data?.results || [];
    setAgents(rows);
    updateOut("agentList", data);
    return rows;
  };

  const hydrateTools = async () => {
    const data = await request("GET", "/tools/");
    const rows = Array.isArray(data) ? data : data?.results || [];
    setTools(rows);
    updateOut("toolList", data);
    return rows;
  };

  const hydrateSkills = async () => {
    const data = await request("GET", "/skills/");
    const rows = Array.isArray(data) ? data : data?.results || [];
    setSkills(rows);
    updateOut("skillList", data);
    return rows;
  };

  const hydrateWorkflowTemplates = async () => {
    const data = await request("GET", "/workflow-templates/");
    const rows = Array.isArray(data) ? data : data?.results || [];
    setWorkflowTemplates(rows);
    if (!selectedWorkflowTemplateId && rows.length) {
      setSelectedWorkflowTemplateId(String(rows[0].id));
    }
    updateOut("workflowTemplates", data);
    return rows;
  };

  const seedWorkflowTemplates = async () => {
    const data = await request("POST", "/workflow-templates/seed-defaults/", {});
    await Promise.all([hydrateWorkflowTemplates(), hydrateAgents(), hydrateTools(), hydrateSkills(), loadDiscordConversations(), loadDiscordStatus()]);
    return data;
  };

  const resetNodeDraft = () => {
    setNodeDraft({
      node_key: "",
      node_type: "agent",
      label: "",
      objective: "",
      agent: "",
      toolsText: "",
      skillsText: "",
      configPairs: [],
      x: 120,
      y: 80,
    });
    setEditingNodeIndex(null);
  };

  const resetEdgeDraft = () => {
    setEdgeDraft({
      source_node_key: "",
      target_node_key: "",
      conditionPairs: [],
      feedbackLoop: false,
    });
    setEditingEdgeIndex(null);
  };

  const loadNodeDraft = (node, index) => {
    const resolvedKey = String(node?.key || node?.node_key || "").trim();
    setNodeDraft({
      node_key: resolvedKey,
      node_type: String(node?.type || node?.node_type || "agent").trim() || "agent",
      label: String(node?.label || resolvedKey).trim(),
      objective: String(node?.objective || "").trim(),
      agent: String(node?.agent || "").trim(),
      toolsText: Array.isArray(node?.tools) ? node.tools.map((tool) => String(tool || "").trim()).filter(Boolean).join(", ") : "",
      skillsText: Array.isArray(node?.skills) ? node.skills.map((skill) => String(skill || "").trim()).filter(Boolean).join(", ") : "",
      configPairs: objToPairs(node?.config || {}),
      x: Number(node?.x ?? 120),
      y: Number(node?.y ?? 80),
    });
    setEditingNodeIndex(index);
    setWorkflowEditorTab("node");
  };

  const loadEdgeDraft = (edge, index) => {
    setEdgeDraft({
      source_node_key: String(edge?.from || "").trim(),
      target_node_key: String(edge?.to || "").trim(),
      conditionPairs: objToPairs(edge?.condition || {}),
      feedbackLoop: !!edge?.feedback_loop,
    });
    setEditingEdgeIndex(index);
    setWorkflowEditorTab("edge");
  };

  const saveWorkflowTemplate = async (template, changes) => {
    if (!template?.id) {
      throw new Error("Select a workflow template first.");
    }
    const payload = {
      name: template.name,
      description: template.description || "",
      version: template.version || "1.0",
      nodes: template.nodes || [],
      edges: template.edges || [],
      input_schema: template.input_schema || {},
      output_schema: template.output_schema || {},
      default_agents: template.default_agents || [],
      is_active: template.is_active !== false,
      ...changes,
    };
    const saved = await request("PUT", `/workflow-templates/${encodeURIComponent(template.id)}/`, payload);
    await hydrateWorkflowTemplates();
    return saved;
  };

  const createWorkflowTemplate = async () => {
    const name = String(workflowTemplateDraft.name || "").trim();
    if (!name) {
      throw new Error("Workflow name is required.");
    }
    const payload = {
      name,
      description: String(workflowTemplateDraft.description || "").trim(),
      version: String(workflowTemplateDraft.version || "1.0").trim() || "1.0",
      nodes: [
        {
          key: "start",
          label: "Start",
          type: "agent",
          agent: "ConciergeAgent",
          tools: [],
          skills: [],
          objective: "Start workflow execution.",
        },
      ],
      edges: [],
      input_schema: {},
      output_schema: {},
      default_agents: ["ConciergeAgent"],
      is_active: true,
    };
    const created = await request("POST", "/workflow-templates/", payload);
    await hydrateWorkflowTemplates();
    if (created?.id) {
      setSelectedWorkflowTemplateId(String(created.id));
    }
    setWorkflowTemplateDraft({ name: "", description: "", version: "1.0" });
    return created;
  };

  const saveWorkflowNode = async (template) => {
    const key = String(nodeDraft.node_key || "").trim();
    if (!key) {
      throw new Error("Node key is required.");
    }
    const agentName = String(nodeDraft.agent || "").trim();
    const bound = deriveWorkflowNodeBindingsFromAgent(agentName, agents);
    const manualTools = csvToList(nodeDraft.toolsText);
    const manualSkills = csvToList(nodeDraft.skillsText);
    const nextNode = {
      key,
      label: String(nodeDraft.label || key).trim(),
      type: String(nodeDraft.node_type || "agent").trim(),
      agent: agentName,
      // Auto-bind from selected agent unless a manual override is provided.
      tools: manualTools.length ? manualTools : bound.tools,
      skills: manualSkills.length ? manualSkills : bound.skills,
      objective: String(nodeDraft.objective || nodeDraft.label || key).trim(),
      config: pairsToObj(nodeDraft.configPairs),
      x: Number(nodeDraft.x || 0),
      y: Number(nodeDraft.y || 0),
    };
    const existingNodes = Array.isArray(template?.nodes) ? template.nodes : [];
    const nodes = editingNodeIndex !== null
      ? existingNodes.map((node, index) => (index === editingNodeIndex ? { ...node, ...nextNode } : node))
      : existingNodes.some((node) => String(node.key || node.node_key) === key)
        ? existingNodes.map((node) => String(node.key || node.node_key) === key ? { ...node, ...nextNode } : node)
        : [...existingNodes, nextNode];
    const saved = await saveWorkflowTemplate(template, { nodes });
    resetNodeDraft();
    return saved;
  };

  const saveWorkflowEdge = async (template) => {
    const source = String(edgeDraft.source_node_key || "").trim();
    const target = String(edgeDraft.target_node_key || "").trim();
    if (!source || !target) {
      throw new Error("Both source and target nodes are required.");
    }
    const condition = pairsToObj(edgeDraft.conditionPairs);
    if (Object.prototype.hasOwnProperty.call(condition, "value")) {
      condition.value = coerceConditionValue(condition.value);
    }
    const nextEdge = {
      from: source,
      to: target,
      ...(Object.keys(condition).length ? { condition } : {}),
      ...(edgeDraft.feedbackLoop ? { feedback_loop: true } : {}),
    };
    const currentEdges = Array.isArray(template?.edges) ? template.edges : [];
    const edges = editingEdgeIndex !== null
      ? currentEdges.map((edge, index) => (index === editingEdgeIndex ? nextEdge : edge))
      : [...currentEdges, nextEdge];
    const saved = await saveWorkflowTemplate(template, { edges });
    resetEdgeDraft();
    return saved;
  };

  const removeWorkflowNode = async (template, index) => {
    const existingNodes = Array.isArray(template?.nodes) ? template.nodes : [];
    const removed = existingNodes[index];
    const removedKey = String(removed?.key || removed?.node_key || "").trim();
    const nodes = existingNodes.filter((_, nodeIndex) => nodeIndex !== index);
    const edges = (Array.isArray(template?.edges) ? template.edges : []).filter((edge) => {
      const from = String(edge?.from || "").trim();
      const to = String(edge?.to || "").trim();
      return from !== removedKey && to !== removedKey;
    });
    if (editingNodeIndex === index) {
      resetNodeDraft();
    }
    return saveWorkflowTemplate(template, { nodes, edges });
  };

  const removeWorkflowEdge = async (template, index) => {
    if (editingEdgeIndex === index) {
      resetEdgeDraft();
    }
    const edges = (Array.isArray(template?.edges) ? template.edges : []).filter((_, edgeIndex) => edgeIndex !== index);
    return saveWorkflowTemplate(template, { edges });
  };

  const moveWorkflowNode = async (template, index, direction) => {
    const nodes = [...(Array.isArray(template?.nodes) ? template.nodes : [])];
    const nextIndex = index + direction;
    if (nextIndex < 0 || nextIndex >= nodes.length) {
      return null;
    }
    [nodes[index], nodes[nextIndex]] = [nodes[nextIndex], nodes[index]];
    return saveWorkflowTemplate(template, { nodes });
  };

  const moveWorkflowEdge = async (template, index, direction) => {
    const edges = [...(Array.isArray(template?.edges) ? template.edges : [])];
    const nextIndex = index + direction;
    if (nextIndex < 0 || nextIndex >= edges.length) {
      return null;
    }
    [edges[index], edges[nextIndex]] = [edges[nextIndex], edges[index]];
    return saveWorkflowTemplate(template, { edges });
  };

  const loadDiscordStatus = async () => {
    const status = await request("GET", "/channels/discord/bot/status");
    setDiscordBotStatus(status);
    updateOut("discordStatus", status);
    return status;
  };

  const loadDiscordConversations = async () => {
    const data = await request("GET", "/conversations/");
    const rows = rowsFromPayload(data).filter((row) => String(row.external_channel || "").toLowerCase() === "discord");
    setDiscordConversations(rows);
    updateOut("discordConversations", rows);
    return rows;
  };

  const sendDiscordWebhookMessage = async () => {
    const body = String(discordWebhookForm.body || "").trim();
    if (!body) {
      throw new Error("Discord message body is required.");
    }
    const result = await request("POST", "/channels/discord/webhook", {
      from: "jaidev",
      body,
      target_agent: "ConciergeAgent",
    });
    if (result?.run_id) {
      const runIdText = String(result.run_id);
      setIsManualRunFocus(false);
      setMetricsRunId(runIdText);
      const [metricsData, messagesData] = await Promise.all([
        request("GET", `/metrics/runs?run_id=${encodeURIComponent(runIdText)}`),
        request("GET", `/messages/?run_id=${encodeURIComponent(runIdText)}`),
      ]);
      updateOut("metrics", metricsData);
      updateOut("messages", messagesData);
    }
    await Promise.all([loadDiscordConversations(), loadRunHistory()]);
    return result;
  };

  const runSelectedWorkflowTemplate = async () => {
    const templateId = selectedWorkflowTemplateId || workflowTemplates[0]?.id;
    if (!templateId) {
      throw new Error("Seed or select a workflow template before running.");
    }
    setIsRunStreaming(true);
    try {
      const payload = {
        ...workflowRunForm,
        channel: "ui",
        trigger: "ui",
      };
      const result = await request("POST", `/workflow-templates/${encodeURIComponent(templateId)}/run-async/`, payload);
      const runId = result?.run?.id;
      if (runId !== undefined && runId !== null) {
        const runIdText = String(runId);
        setIsManualRunFocus(false);
        setMetricsRunId(runIdText);
        const [metricsData, messagesData] = await Promise.all([
          request("GET", `/metrics/runs?run_id=${encodeURIComponent(runIdText)}`),
          request("GET", `/messages/?run_id=${encodeURIComponent(runIdText)}`),
        ]);
        updateOut("metrics", metricsData);
        updateOut("messages", messagesData);
      }
      await loadRunHistory();
      return result;
    } finally {
      setIsRunStreaming(false);
    }
  };

  const loadRunHistory = async () => {
    const data = await request("GET", "/runs/");
    setRunHistory(rowsFromPayload(data));
    return data;
  };

  const stopRun = async (runId) => {
    await request("POST", `/runs/${encodeURIComponent(runId)}/stop/`);
    await loadRunHistory();
  };

  const focusRun = async (runId) => {
    const runIdText = String(runId || "").trim();
    if (!runIdText) {
      throw new Error("Run id is required to focus a run.");
    }
    setIsManualRunFocus(true);
    setMetricsRunId(runIdText);
    const [metricsData, messagesData] = await Promise.all([
      request("GET", `/metrics/runs?run_id=${encodeURIComponent(runIdText)}`),
      request("GET", `/messages/?run_id=${encodeURIComponent(runIdText)}`),
    ]);
    updateOut("metrics", metricsData);
    updateOut("messages", messagesData);
    return { focused_run_id: runIdText };
  };

  const deleteRun = async (runId) => {
    await request("DELETE", `/runs/${encodeURIComponent(runId)}/`);
    setRunHistory((prev) => prev.filter((r) => r.id !== runId && r.runId !== runId));
  };

  const withOut = async (key, action, options = {}) => {
    const trackBusy = options.trackBusy ?? true;
    const notifySuccess = options.notifySuccess ?? true;
    const notifyError = options.notifyError ?? true;
    if (trackBusy) {
      setBusy(true);
    }
    try {
      const data = await action();
      updateOut(key, data);
      if (notifySuccess) {
        pushToast("success", `${humanizeKey(key)} completed`, "Action finished successfully.");
      }
      return data;
    } catch (error) {
      const message = String(error.message || error);
      updateOut(key, { error: message });
      if (notifyError) {
        pushToast("error", `${humanizeKey(key)} failed`, message);
      }
      return null;
    } finally {
      if (trackBusy) {
        setBusy(false);
      }
    }
  };

  useEffect(() => {
    withOut("dashboardBoot", async () => {
      const [agentRows, toolRows, skillRows, workflowRows] = await Promise.all([
        hydrateAgents(),
        hydrateTools(),
        hydrateSkills(),
        hydrateWorkflowTemplates(),
      ]);
      return {
        agents: agentRows.length,
        tools: toolRows.length,
        skills: skillRows.length,
        workflows: workflowRows.length,
      };
    }, { trackBusy: false, notifySuccess: false, notifyError: false });
  }, []);

  useEffect(() => {
    if (["workflowLauncher", "workflowCrud", "discordMessaging"].includes(currentView)) {
      withOut("runHistory", loadRunHistory, { trackBusy: false, notifySuccess: false, notifyError: false });
      withOut("workflowTemplates", hydrateWorkflowTemplates, { trackBusy: false, notifySuccess: false, notifyError: false });
      withOut("discordStatus", loadDiscordStatus, { trackBusy: false, notifySuccess: false, notifyError: false });
      withOut("discordConversations", loadDiscordConversations, { trackBusy: false, notifySuccess: false, notifyError: false });
      withOut("agenticApprovals", () => request("GET", "/approvals/"), {
        trackBusy: false,
        notifySuccess: false,
        notifyError: false,
      });
      withOut("metrics", () => request("GET", `/metrics/runs${metricsRunId ? `?run_id=${encodeURIComponent(metricsRunId)}` : ""}`), {
        trackBusy: false,
        notifySuccess: false,
        notifyError: false,
      });
      withOut("messages", () => request("GET", `/messages/${metricsRunId ? `?run_id=${encodeURIComponent(metricsRunId)}` : ""}`), {
        trackBusy: false,
        notifySuccess: false,
        notifyError: false,
      });
    }
  }, [currentView, metricsRunId]);

  useEffect(() => {
    if (!["workflowLauncher", "workflowCrud"].includes(currentView) || isLiveLogsPaused || (!isRunStreaming && !metricsRunId)) {
      return undefined;
    }

    let cancelled = false;
    const terminalStatuses = new Set(["completed", "failed", "error", "rejected", "cancelled", "canceled"]);

    const poll = async () => {
      try {
        const runsData = await request("GET", "/runs/");
        if (cancelled) {
          return;
        }
        const rows = rowsFromPayload(runsData);
        setRunHistory(rows);

        const active =
          rows.find((row) => {
            const status = String(row?.status || "").toLowerCase();
            return status === "queued" || status === "running" || status === "pending" || status === "in_progress" || status === "in-progress";
          }) || rows[0];

        const activeStatus = String(active?.status || "").toLowerCase();
        const activeIsRunning =
          activeStatus === "queued" ||
          activeStatus === "running" ||
          activeStatus === "pending" ||
          activeStatus === "in_progress" ||
          activeStatus === "in-progress";

        const focusedRunId = isManualRunFocus ? String(metricsRunId || "").trim() : "";
        const hasFocusedRun = focusedRunId && rows.some((row) => String(row?.id ?? "") === focusedRunId);
        if (isManualRunFocus && !hasFocusedRun) {
          setIsManualRunFocus(false);
        }
        const liveActiveRunId =
          activeIsRunning && active?.id !== undefined && active?.id !== null
            ? String(active.id)
            : active?.id !== undefined && active?.id !== null
              ? String(active.id)
              : "";
        const activeRunId = hasFocusedRun ? focusedRunId : liveActiveRunId;
        if (!activeRunId) {
          return;
        }

        if (!hasFocusedRun) {
          setMetricsRunId(activeRunId);
        }
        const [metricsData, messagesData] = await Promise.all([
          request("GET", `/metrics/runs?run_id=${encodeURIComponent(activeRunId)}`),
          request("GET", `/messages/?run_id=${encodeURIComponent(activeRunId)}`),
        ]);
        if (cancelled) {
          return;
        }
        updateOut("metrics", metricsData);
        updateOut("messages", messagesData);

        if (terminalStatuses.has(String(active?.status || "").toLowerCase())) {
          setIsRunStreaming(false);
        }
      } catch {
        // Keep polling resilient while a run is active.
      }
    };

    poll();
    const timer = window.setInterval(poll, 1200);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [currentView, isRunStreaming, isLiveLogsPaused, metricsRunId, isManualRunFocus]);


  useEffect(() => {
    setIsNavOpen(false);
  }, [currentView]);

  useEffect(() => {
    const mediaQuery = window.matchMedia("(min-width: 981px)");
    const syncNavState = (event) => {
      if (event.matches) {
        setIsNavOpen(false);
      }
    };

    syncNavState(mediaQuery);
    if (typeof mediaQuery.addEventListener === "function") {
      mediaQuery.addEventListener("change", syncNavState);
      return () => mediaQuery.removeEventListener("change", syncNavState);
    }

    mediaQuery.addListener(syncNavState);
    return () => mediaQuery.removeListener(syncNavState);
  }, []);

  useEffect(() => {
    if (!isNavOpen) {
      return undefined;
    }

    const onKeyDown = (event) => {
      if (event.key === "Escape") {
        setIsNavOpen(false);
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isNavOpen]);

  const onTemplateChange = (template) => {
    const preset = agentTemplates[template];
    if (!preset) {
      return;
    }
    setAgentEditor((prev) => ({ ...prev, role: preset.role, system_prompt: preset.system_prompt }));
  };

  const loadAgentEditor = (agentId) => {
    const selected = agents.find((agent) => String(agent.id) === String(agentId));
    if (!selected) {
      return;
    }
    setSelectedAgentId(String(selected.id));
    setAgentEditor({
      id: String(selected.id),
      name: selected.name || "",
      role: selected.role || "",
      description: selected.description || "",
      model: selected.model || "nvidia/nemotron-3-super-120b-a12b:free",
      system_prompt: selected.system_prompt || "",
      channelsText: Array.isArray(selected.channels) ? selected.channels.join(", ") : "",
      selectedTools: Array.isArray(selected.tools) ? selected.tools : [],
      selectedSkills: skillNamesFromValue(selected.skills),
      skillsText: skillsTextFromValue(selected.skills),
      scheduleText: textFromValue(selected.schedule, "{}"),
      memoryProfileText: textFromValue(selected.memory_profile, "{}"),
      interactionRulesText: textFromValue(selected.interaction_rules, "[]"),
      guardrailsText: textFromValue(selected.guardrails, "[]"),
      limitsText: textFromValue(selected.limits, "{}"),
      is_active: !!selected.is_active,
    });
    setAgentView("editor");
  };

  const resetAgentEditor = () => {
    setSelectedAgentId("");
    setAgentEditor(initialAgentEditor());
  };

  const resetSkillEditor = () => {
    setSkillEditor(initialSkillEditor());
    setSkillView("grid");
  };

  const resetToolEditor = () => {
    setToolEditor(initialToolEditor());
    setToolView("grid");
  };

  const loadToolEditor = (toolId) => {
    const selected = tools.find((t) => String(t.id) === String(toolId));
    if (!selected) return;
    setToolEditor({
      id: String(selected.id),
      name: selected.name || "",
      description: selected.description || "",
      category: selected.category || "ingestion",
      capabilities: Array.isArray(selected.capabilities) ? selected.capabilities : [],
      configSchema: schemaToPairs(selected.config_schema),
      is_active: !!selected.is_active,
      is_system: !!selected.is_system,
    });
    setToolView("editor");
  };

  const upsertTool = async () => {
    const payload = {
      name: toolEditor.name,
      description: toolEditor.description,
      category: toolEditor.category,
      capabilities: toolEditor.capabilities,
      config_schema: pairsToSchema(toolEditor.configSchema),
      is_active: !!toolEditor.is_active,
    };
    const isUpdate = Boolean(toolEditor.id);
    const result = isUpdate
      ? await request("PATCH", `/tools/${toolEditor.id}/`, payload)
      : await request("POST", "/tools/", payload);
    await hydrateTools();
    if (result?.id) loadToolEditor(String(result.id));
    return result;
  };

  const deleteTool = async () => {
    if (!toolEditor.id) throw new Error("Select a tool to delete.");
    const deletedId = toolEditor.id;
    await request("DELETE", `/tools/${toolEditor.id}/`);
    await hydrateTools();
    resetToolEditor();
    return { deleted: true, id: deletedId };
  };

  const toggleAgentTool = (tool) => {
    setAgentEditor((prev) => {
      const already = prev.selectedTools.some((t) => t.name === tool.name);
      if (already) {
        return { ...prev, selectedTools: prev.selectedTools.filter((t) => t.name !== tool.name) };
      }
      return { ...prev, selectedTools: [...prev.selectedTools, { name: tool.name, capabilities: [...tool.capabilities] }] };
    });
  };

  const toggleAgentToolCap = (toolName, cap) => {
    setAgentEditor((prev) => ({
      ...prev,
      selectedTools: prev.selectedTools.map((t) => {
        if (t.name !== toolName) return t;
        const has = t.capabilities.includes(cap);
        return { ...t, capabilities: has ? t.capabilities.filter((c) => c !== cap) : [...t.capabilities, cap] };
      }),
    }));
  };

  const toggleAgentSkill = (skillName) => {
    setAgentEditor((prev) => {
      const already = prev.selectedSkills.includes(skillName);
      const nextSelected = already
        ? prev.selectedSkills.filter((name) => name !== skillName)
        : [...prev.selectedSkills, skillName];

      // Auto-derive tools from required skills' requires_tools
      const derivedTools = nextSelected.length
        ? deriveToolsFromSkills(nextSelected, skills, tools)
        : prev.selectedTools;

      return {
        ...prev,
        selectedSkills: nextSelected,
        skillsText: jsonText(nextSelected),
        selectedTools: derivedTools,
      };
    });
  };

  const upsertAgent = async () => {
    const normalizedSkills = agentEditor.selectedSkills.length
      ? agentEditor.selectedSkills
      : parseSkillsPayload(agentEditor.skillsText);
    const resolvedTools = normalizedSkills.length
      ? deriveToolsFromSkills(normalizedSkills, skills, tools)
      : agentEditor.selectedTools;
    const payload = {
      name: agentEditor.name,
      role: agentEditor.role,
      description: agentEditor.description,
      model: agentEditor.model,
      system_prompt: agentEditor.system_prompt,
      tools: resolvedTools,
      channels: csvToList(agentEditor.channelsText),
      schedule: parseJsonOrText(agentEditor.scheduleText, {}),
      memory_profile: parseJsonOrText(agentEditor.memoryProfileText, {}),
      skills: normalizedSkills,
      interaction_rules: parseJsonOrText(agentEditor.interactionRulesText, []),
      guardrails: parseJsonOrText(agentEditor.guardrailsText, []),
      limits: parseJsonOrText(agentEditor.limitsText, {}),
      is_active: !!agentEditor.is_active,
    };

    const isUpdate = Boolean(agentEditor.id);
    const result = isUpdate
      ? await request("PATCH", `/agents/${agentEditor.id}/`, payload)
      : await request("POST", "/agents/", payload);

    await hydrateAgents();
    if (result?.id) {
      loadAgentEditor(String(result.id));
    }
    return result;
  };

  const loadSkillEditor = (skillId) => {
    const selected = skills.find((skill) => String(skill.id) === String(skillId));
    if (!selected) {
      return;
    }
    setSkillEditor({
      id: String(selected.id),
      name: selected.name || "",
      description: selected.description || "",
      category: selected.category || "general",
      trigger: selected.trigger || "always",
      priority: selected.priority ?? 100,
      output_schema: selected.output_schema || "",
      abort_on_fail: !!selected.abort_on_fail,
      selectedToolNames: Array.isArray(selected.requires_tools) ? selected.requires_tools : [],
      markdown: selected.markdown || "",
      is_active: !!selected.is_active,
    });
    setSkillView("editor");
  };

  const toggleSkillTool = (toolName) => {
    setSkillEditor((prev) => {
      const already = prev.selectedToolNames.includes(toolName);
      return {
        ...prev,
        selectedToolNames: already
          ? prev.selectedToolNames.filter((name) => name !== toolName)
          : [...prev.selectedToolNames, toolName],
      };
    });
  };

  const upsertSkill = async () => {
    const payload = {
      name: skillEditor.name,
      description: skillEditor.description,
      category: skillEditor.category,
      trigger: skillEditor.trigger,
      priority: Number(skillEditor.priority),
      requires_tools: skillEditor.selectedToolNames,
      output_schema: skillEditor.output_schema,
      abort_on_fail: !!skillEditor.abort_on_fail,
      markdown: skillEditor.markdown,
      is_active: !!skillEditor.is_active,
    };

    const isUpdate = Boolean(skillEditor.id);
    const result = isUpdate
      ? await request("PATCH", `/skills/${skillEditor.id}/`, payload)
      : await request("POST", "/skills/", payload);
    await hydrateSkills();
    if (result?.id) {
      loadSkillEditor(String(result.id));
    }
    return result;
  };

  const createStarterSkills = async () => {
    const existingNames = new Set(skills.map((item) => String(item.name || "").trim()).filter(Boolean));
    const missing = starterSkillTemplates.filter((template) => !existingNames.has(template.name));
    if (missing.length === 0) {
      return { created: 0, skipped: starterSkillTemplates.length, names: [] };
    }

    const createdNames = [];
    for (const template of missing) {
      const result = await request("POST", "/skills/", template);
      if (result?.name) {
        createdNames.push(result.name);
      }
    }
    await hydrateSkills();
    return {
      created: createdNames.length,
      skipped: starterSkillTemplates.length - createdNames.length,
      names: createdNames,
    };
  };

  const deleteSkill = async () => {
    if (!skillEditor.id) {
      throw new Error("Select a skill to delete.");
    }
    const deletedId = skillEditor.id;
    await request("DELETE", `/skills/${skillEditor.id}/`);
    await hydrateSkills();
    resetSkillEditor();
    return { deleted: true, id: deletedId };
  };

  const deleteAgent = async () => {
    if (!agentEditor.id) {
      throw new Error("Select an agent to delete.");
    }
    const deletedId = agentEditor.id;
    await request("DELETE", `/agents/${agentEditor.id}/`);
    await hydrateAgents();
    resetAgentEditor();
    setAgentView("grid");
    return { deleted: true, id: deletedId };
  };

  const selectedAgent = useMemo(
    () => agents.find((agent) => String(agent.id) === String(selectedAgentId)) || null,
    [agents, selectedAgentId]
  );

  const deployAgent = async () => {
    if (!selectedAgent) {
      throw new Error("Select an agent before deploying.");
    }
    const result = await request("PATCH", `/agents/${selectedAgent.id}/`, { is_active: true });
    await hydrateAgents();
    return {
      deployed_agent_id: selectedAgent.id,
      status: "deployed",
      is_active: true,
      agent: result,
    };
  };

  const readyScore = useMemo(() => {
    let points = 0;
    if (agents.length) points += 1;
    if (tools.length) points += 1;
    if (skills.length) points += 1;
    return points;
  }, [agents.length, skills.length, tools.length]);

  const runIdOptions = useMemo(() => {
    const ids = new Set();
    for (const row of runHistory || []) {
      if (row?.id !== undefined && row?.id !== null && String(row.id).trim()) {
        ids.add(String(row.id));
      }
    }
    return Array.from(ids).sort((a, b) => Number(b) - Number(a));
  }, [runHistory]);

  const approvalsCount = useMemo(() => {
    const payload = parseJsonSafely(out.agenticApprovals);
    if (typeof payload?.count === "number") {
      return payload.count;
    }
    return rowsFromPayload(payload).length;
  }, [out.agenticApprovals]);

  const historyRows = useMemo(
    () =>
      (runHistory || []).slice(0, 12).map((row) => {
        const runId = row?.id;
        const runLabel = row?.run_name || "Workflow Run";
        const when = row?.finished_at || row?.updated_at || row?.created_at || row?.started_at;
        return {
          runId,
          runLabel,
          status: row?.status || "unknown",
          when,
        };
      }),
    [runHistory]
  );


  const metricsPayload = useMemo(() => parseJsonSafely(out.metrics) || null, [out.metrics]);
  const interAgentMessages = useMemo(() => rowsFromPayload(parseJsonSafely(out.messages) || []), [out.messages]);
  const agentLogLines = useMemo(() => {
    const rows = metricsPayload?.agent_logs;
    if (!Array.isArray(rows)) {
      return [];
    }
    return rows
      .map(readableAgentLogLine)
      .map((line) => String(line || "").trim())
      .filter(Boolean);
  }, [metricsPayload]);

  const agentTalkLines = useMemo(() => {
    if (!Array.isArray(interAgentMessages) || interAgentMessages.length === 0) {
      return [];
    }
    return [...interAgentMessages]
      .reverse()
      .map(readableAgentTalkLine)
      .filter(Boolean);
  }, [interAgentMessages]);

  const liveAgentLines = useMemo(() => {
    if (!agentTalkLines.length) {
      return agentLogLines;
    }
    return [...agentLogLines, ...agentTalkLines];
  }, [agentLogLines, agentTalkLines]);

  const liveStatusText = isLiveLogsPaused ? "Live Paused" : "Live On";

  const agentAchievements = useMemo(() => {
    const rows = metricsPayload?.agent_achievements;
    return Array.isArray(rows) ? rows : [];
  }, [metricsPayload]);

  const completeRunLog = useMemo(() => {
    const rows = metricsPayload?.complete_log;
    return Array.isArray(rows) ? rows : [];
  }, [metricsPayload]);

  const workflowResultPayload = useMemo(() => {
    if (metricsPayload?.workflow_result && Object.keys(metricsPayload.workflow_result).length) {
      return metricsPayload.workflow_result;
    }
    return metricsPayload?.run?.output_payload || {};
  }, [metricsPayload]);

  const formatRunDateTime = (value) => {
    if (!value) {
      return "time unavailable";
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return String(value);
    }
    return date.toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", hour12: true });
  };

  const compactJson = (value) => {
    if (!value || (typeof value === "object" && Object.keys(value).length === 0)) {
      return "{}";
    }
    return jsonText(value);
  };

  const listText = (value) => {
    if (!Array.isArray(value) || !value.length) {
      return "None";
    }
    return value.map((item) => String(item || "").trim()).filter(Boolean).join(", ") || "None";
  };


  const runStatusClass = (status) => {
    const value = String(status || "unknown").toLowerCase();
    if (["completed", "approved", "executed", "success"].includes(value)) {
      return "status-good";
    }
    if (["queued", "running", "pending", "in_progress", "in-progress"].includes(value)) {
      return "status-warn";
    }
    if (["failed", "error", "rejected", "cancelled", "canceled"].includes(value)) {
      return "status-bad";
    }
    return "status-neutral";
  };

  const renderTools = () => {
    if (toolView === "editor") {
      return (
        <section className="agent-editor-wrap themed-page-shell">
          <div className="editor-breadcrumb">
            <button type="button" className="back-btn" onClick={resetToolEditor}>← All Tools</button>
            <span className="breadcrumb-sep">/</span>
            <span className="breadcrumb-current">{toolEditor.id ? toolEditor.name || "Edit Tool" : "New Tool"}</span>
          </div>
          <div className="content-grid agents-grid">
            <article className="card">
              <h3>{toolEditor.id ? "Edit Tool" : "New Tool"}</h3>
              {toolEditor.is_system && (
                <p className="notice" style={{background:"var(--c-warn-bg,#fff8e1)",color:"var(--c-warn,#7a5800)",padding:"0.5rem 0.75rem",borderRadius:"6px",marginBottom:"0.75rem",fontSize:"0.85rem"}}>
                  🔒 System tool — managed by the platform. Read-only.
                </p>
              )}
              <form className="stack" onSubmit={(e) => { e.preventDefault(); if (!toolEditor.is_system) withOut("toolUpsert", upsertTool); }}>
                <label>Name<input value={toolEditor.name} onChange={(e) => setToolEditor((s) => ({ ...s, name: e.target.value }))} required disabled={toolEditor.is_system} /></label>
                <label>Description<textarea rows={3} value={toolEditor.description} onChange={(e) => setToolEditor((s) => ({ ...s, description: e.target.value }))} disabled={toolEditor.is_system} /></label>
                <label>Category
                  <select value={toolEditor.category} onChange={(e) => setToolEditor((s) => ({ ...s, category: e.target.value }))} disabled={toolEditor.is_system}>
                    {["ingestion","memory","research","communication","monitoring","productivity","support"].map((c) => (
                      <option key={c} value={c}>{c}</option>
                    ))}
                  </select>
                </label>
                <fieldset disabled={toolEditor.is_system}>
                  <legend>Capabilities</legend>
                  {["read","write","execute"].map((cap) => (
                    <label key={cap} style={{display:"inline-flex",alignItems:"center",gap:"0.35rem",marginRight:"1rem"}}>
                      <input type="checkbox" checked={toolEditor.capabilities.includes(cap)}
                        onChange={(e) => setToolEditor((s) => ({
                          ...s,
                          capabilities: e.target.checked
                            ? [...s.capabilities, cap]
                            : s.capabilities.filter((c) => c !== cap),
                        }))}
                      /> {cap}
                    </label>
                  ))}
                </fieldset>
                <fieldset disabled={toolEditor.is_system}>
                  <legend>Config Schema</legend>
                  {toolEditor.configSchema.map((pair, idx) => (
                    <div key={idx} className="inline" style={{marginBottom:"0.4rem"}}>
                      <input placeholder="key" value={pair.key}
                        onChange={(e) => setToolEditor((s) => {
                          const cs = [...s.configSchema]; cs[idx] = {...cs[idx], key: e.target.value}; return {...s, configSchema: cs};
                        })} style={{flex:2}} />
                      <select value={pair.type}
                        onChange={(e) => setToolEditor((s) => {
                          const cs = [...s.configSchema]; cs[idx] = {...cs[idx], type: e.target.value}; return {...s, configSchema: cs};
                        })}>
                        {["string","float","int","bool","list"].map((t) => <option key={t} value={t}>{t}</option>)}
                      </select>
                      <button type="button" className="secondary" onClick={() => setToolEditor((s) => ({
                        ...s, configSchema: s.configSchema.filter((_, i) => i !== idx)
                      }))}>✕</button>
                    </div>
                  ))}
                  <button type="button" className="secondary" onClick={() => setToolEditor((s) => ({
                    ...s, configSchema: [...s.configSchema, {key: "", type: "string"}]
                  }))}>+ Add field</button>
                </fieldset>
                <label style={{display:"inline-flex",alignItems:"center",gap:"0.5rem"}}>
                  <input type="checkbox" checked={toolEditor.is_active}
                    onChange={(e) => setToolEditor((s) => ({ ...s, is_active: e.target.checked }))} disabled={toolEditor.is_system} />
                  Active
                </label>
                <div className="inline">
                  <button type="submit" disabled={busy || toolEditor.is_system}>{toolEditor.id ? "Update Tool" : "Create Tool"}</button>
                  <button type="button" className="secondary" onClick={() => withOut("toolDelete", deleteTool)} disabled={busy || !toolEditor.id || toolEditor.is_system}>Delete</button>
                </div>
              </form>
            </article>
            <article className="card">
              <h3>Tool Preview</h3>
              <p className="subtle">Normalized JSON as it will be saved.</p>
              <pre>{jsonText({
                id: toolEditor.id || "new",
                name: toolEditor.name,
                description: toolEditor.description,
                category: toolEditor.category,
                capabilities: toolEditor.capabilities,
                config_schema: pairsToSchema(toolEditor.configSchema),
                is_active: toolEditor.is_active,
              })}</pre>
            </article>
          </div>
        </section>
      );
    }

    const categoryOptions = Array.from(new Set(tools.map((tool) => String(tool.category || "uncategorized")))).sort();

    const filtered = tools.filter((tool) => {
      const caps = Array.isArray(tool.capabilities) ? tool.capabilities.map((cap) => String(cap).toLowerCase()) : [];
      const searchHit =
        toolSearch === "" ||
        tool.name.toLowerCase().includes(toolSearch.toLowerCase()) ||
        (tool.description || "").toLowerCase().includes(toolSearch.toLowerCase()) ||
        (tool.category || "").toLowerCase().includes(toolSearch.toLowerCase());
      const categoryHit = toolCategoryFilter === "all" || String(tool.category || "uncategorized") === toolCategoryFilter;
      const capabilityHit = toolCapabilityFilter === "all" || caps.includes(toolCapabilityFilter.toLowerCase());
      const statusHit =
        toolStatusFilter === "all" ||
        (toolStatusFilter === "active" && !!tool.is_active) ||
        (toolStatusFilter === "inactive" && !tool.is_active);
      return searchHit && categoryHit && capabilityHit && statusHit;
    });

    const sorted = [...filtered].sort((left, right) => {
      if (toolSort === "name") {
        return String(left.name || "").localeCompare(String(right.name || ""));
      }
      if (toolSort === "name_desc") {
        return String(right.name || "").localeCompare(String(left.name || ""));
      }
      if (toolSort === "status") {
        return Number(Boolean(right.is_active)) - Number(Boolean(left.is_active));
      }
      const byCategory = String(left.category || "").localeCompare(String(right.category || ""));
      if (byCategory !== 0) {
        return byCategory;
      }
      return String(left.name || "").localeCompare(String(right.name || ""));
    });

    return (
      <section className="agent-list-wrap themed-page-shell">
        <CrudSubHeader title="Tools" meta={`${sorted.length} of ${tools.length} shown`}>
          <input className="search-input" placeholder="Search tools..." value={toolSearch} onChange={(e) => setToolSearch(e.target.value)} />
          <div className="tool-filters-row">
            <select className="toolbar-select" value={toolCategoryFilter} onChange={(e) => setToolCategoryFilter(e.target.value)}>
              <option value="all">All categories</option>
              {categoryOptions.map((category) => (
                <option key={category} value={category}>{category}</option>
              ))}
            </select>
            <select className="toolbar-select" value={toolCapabilityFilter} onChange={(e) => setToolCapabilityFilter(e.target.value)}>
              <option value="all">All capabilities</option>
              <option value="read">read</option>
              <option value="write">write</option>
            </select>
            <select className="toolbar-select" value={toolStatusFilter} onChange={(e) => setToolStatusFilter(e.target.value)}>
              <option value="all">All status</option>
              <option value="active">active</option>
              <option value="inactive">inactive</option>
            </select>
            <select className="toolbar-select" value={toolSort} onChange={(e) => setToolSort(e.target.value)}>
              <option value="category">Sort: category</option>
              <option value="name">Sort: name A-Z</option>
              <option value="name_desc">Sort: name Z-A</option>
              <option value="status">Sort: active first</option>
            </select>
          </div>
          <div className="tool-actions-row">
            <button type="button" className="secondary" onClick={() => withOut("toolList", hydrateTools)} disabled={busy}>Refresh</button>
            <button
              type="button"
              className="secondary"
              onClick={() => {
                setToolSearch("");
                setToolCategoryFilter("all");
                setToolCapabilityFilter("all");
                setToolStatusFilter("all");
                setToolSort("category");
              }}
              disabled={busy}
            >
              Clear
            </button>
            <button type="button" onClick={() => { resetToolEditor(); setToolView("editor"); }} disabled={busy}>+ Add Tool</button>
          </div>
        </CrudSubHeader>
        {sorted.length === 0 ? (
          <p className="agent-empty">No tools found for the current search and filter combination.</p>
        ) : (
          <div className="agent-card-grid">
            {sorted.map((tool) => (
              <div key={tool.id} className="agent-card tool-card tool-library-card">
                <div className="agent-card-header">
                  <span className={`tag tag-model tag-cat-${tool.category}`}>{tool.category}</span>
                  <span className={`status-dot ${tool.is_active ? "dot-active" : "dot-inactive"}`} title={tool.is_active ? "active" : "inactive"} />
                  <span className={tool.is_active ? "agent-badge badge-active" : "agent-badge badge-inactive"}>{tool.is_active ? "active" : "inactive"}</span>
                </div>
                <div className="agent-card-name">{tool.name}</div>
                <div className="agent-card-role tool-description" title={tool.description || ""}>{tool.description}</div>
                <div className="agent-card-meta">
                  {(Array.isArray(tool.capabilities) ? tool.capabilities : []).map((cap) => (
                    <span key={cap} className="tag">{cap}</span>
                  ))}
                </div>
                <div className="agent-card-footer">
                  <IconActionButton
                    icon="↗"
                    label={`Open tool ${tool.name}`}
                    tone="info"
                    className="card-open-action"
                    onClick={() => loadToolEditor(String(tool.id))}
                  />
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    );
  };

  const renderSkills = () => {
    const skillTheme = getSkillPreviewTheme(skillEditor.category, skillEditor.abort_on_fail);
    const skillMarkdownLines = String(skillEditor.markdown || "")
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean)
      .slice(0, 4);

    if (skillView === "editor") {
      return (
        <section className="agent-editor-wrap themed-page-shell">
          <div className="editor-breadcrumb">
            <button type="button" className="back-btn" onClick={resetSkillEditor}>← All Skills</button>
            <span className="breadcrumb-sep">/</span>
            <span className="breadcrumb-current">{skillEditor.id ? skillEditor.name || "Edit Skill" : "New Skill"}</span>
          </div>
          <div className="content-grid agents-grid">
            <article className="card">
              <h3>{skillEditor.id ? "Edit Skill" : "New Skill"}</h3>
              <form className="stack" onSubmit={(e) => { e.preventDefault(); withOut("skillUpsert", upsertSkill); }}>
                <label>Name<input value={skillEditor.name} onChange={(e) => setSkillEditor((s) => ({ ...s, name: e.target.value }))} required /></label>
                <label>Description<textarea rows={3} value={skillEditor.description} onChange={(e) => setSkillEditor((s) => ({ ...s, description: e.target.value }))} /></label>
                <div className="stack">
                  <span className="form-field-label">Category</span>
                  <div className="option-grid option-grid-4">
                    {skillCategories.map((category) => (
                      <button
                        key={category}
                        type="button"
                        className={skillEditor.category === category ? "option-tile option-tile-active" : "option-tile"}
                        onClick={() => setSkillEditor((s) => ({ ...s, category }))}
                      >
                        <strong>{category}</strong>
                        <span>{category === "policy" ? "Hard constraints" : category === "procedure" ? "Execution steps" : category === "output" ? "Delivery format" : "Flexible utility"}</span>
                      </button>
                    ))}
                  </div>
                </div>
                <div className="stack">
                  <span className="form-field-label">Trigger</span>
                  <div className="option-grid option-grid-5">
                    {skillTriggerPresets.map((preset) => (
                      <button
                        key={preset}
                        type="button"
                        className={skillEditor.trigger === preset ? "option-tile option-tile-active" : "option-tile"}
                        onClick={() => setSkillEditor((s) => ({ ...s, trigger: preset }))}
                      >
                        <strong>{preset}</strong>
                      </button>
                    ))}
                  </div>
                  <label>Custom Trigger
                    <input value={skillEditor.trigger} onChange={(e) => setSkillEditor((s) => ({ ...s, trigger: e.target.value }))} placeholder="always | approval_required | channel:discord" />
                  </label>
                </div>
                <div className="stack">
                  <span className="form-field-label">Priority</span>
                  <div className="option-grid option-grid-5">
                    {skillPriorityPresets.map((priority) => (
                      <button
                        key={priority}
                        type="button"
                        className={Number(skillEditor.priority) === priority ? "option-tile option-tile-active" : "option-tile"}
                        onClick={() => setSkillEditor((s) => ({ ...s, priority }))}
                      >
                        <strong>P{priority}</strong>
                        <span>{priority <= 20 ? "High precedence" : priority <= 40 ? "Runtime enforced" : "Fallback"}</span>
                      </button>
                    ))}
                  </div>
                  <label>Custom Priority
                    <input
                      type="number"
                      min="0"
                      value={skillEditor.priority}
                      onChange={(e) => setSkillEditor((s) => ({ ...s, priority: Number(e.target.value || 0) }))}
                    />
                  </label>
                </div>
                <label>Output Schema
                  <input value={skillEditor.output_schema} onChange={(e) => setSkillEditor((s) => ({ ...s, output_schema: e.target.value }))} placeholder="research_loop_summary" />
                </label>
                <div className="stack">
                  <span className="form-field-label">Abort On Fail</span>
                  <div className="option-grid option-grid-2">
                    <button
                      type="button"
                      className={!skillEditor.abort_on_fail ? "option-tile option-tile-active" : "option-tile"}
                      onClick={() => setSkillEditor((s) => ({ ...s, abort_on_fail: false }))}
                    >
                      <strong>Soft</strong>
                      <span>Continue with fallback behavior</span>
                    </button>
                    <button
                      type="button"
                      className={skillEditor.abort_on_fail ? "option-tile option-tile-active" : "option-tile"}
                      onClick={() => setSkillEditor((s) => ({ ...s, abort_on_fail: true }))}
                    >
                      <strong>Strict</strong>
                      <span>Stop when this skill fails</span>
                    </button>
                  </div>
                </div>

                <div className="tool-picker-label">
                  <details className="tool-picker-shell" open>
                    <summary className="tool-picker-summary">
                      <span className="form-field-label">Required Tools</span>
                      <span className="tool-picker-count">{skillEditor.selectedToolNames.length} selected</span>
                    </summary>
                    {tools.filter((tool) => tool.is_active).length === 0 && (
                      <p className="subtle">No active tools found. Create tools first.</p>
                    )}
                    <div className="tool-picker">
                      {tools.filter((tool) => tool.is_active).map((tool) => {
                        const selected = skillEditor.selectedToolNames.includes(tool.name);
                        const inputId = `skill-tool-${String(tool.name).replace(/[^a-zA-Z0-9_-]/g, "-")}`;
                        return (
                          <div
                            key={tool.name}
                            className={`tool-row${selected ? " tool-row-active" : ""}`}
                            onClick={() => toggleSkillTool(tool.name)}
                            role="button"
                            tabIndex={0}
                            onKeyDown={(event) => {
                              if (event.key === "Enter" || event.key === " ") {
                                event.preventDefault();
                                toggleSkillTool(tool.name);
                              }
                            }}
                          >
                            <div className="tool-check-label">
                              <input
                                id={inputId}
                                type="checkbox"
                                checked={selected}
                                onClick={(event) => event.stopPropagation()}
                                onChange={() => toggleSkillTool(tool.name)}
                              />
                              <div className="tool-info">
                                <label className="tool-name" htmlFor={inputId}>{tool.name}</label>
                                <span className="tool-desc">{tool.description || "No description"}</span>
                              </div>
                              <span className={`tag tag-cat-${tool.category}`}>{tool.category}</span>
                            </div>
                            <div className="tool-caps">
                              {(Array.isArray(tool.capabilities) ? tool.capabilities : []).map((capability) => (
                                <span key={`${tool.name}-${capability}`} className="cap-check">{capability}</span>
                              ))}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </details>
                </div>

                <label>Skill Markdown
                  <textarea
                    rows={10}
                    value={skillEditor.markdown}
                    onChange={(e) => setSkillEditor((s) => ({ ...s, markdown: e.target.value }))}
                    placeholder={'### Skill Objective\n- Define behavior\n- Define output sections\n- Define failure fallback'}
                    required
                  />
                </label>

                <label>Active
                  <select value={skillEditor.is_active ? "true" : "false"} onChange={(e) => setSkillEditor((s) => ({ ...s, is_active: e.target.value === "true" }))}>
                    <option value="true">true</option>
                    <option value="false">false</option>
                  </select>
                </label>

                <div className="inline">
                  <button type="submit" disabled={busy}>{skillEditor.id ? "Update Skill" : "Create Skill"}</button>
                  <button type="button" className="secondary" onClick={() => withOut("skillDelete", deleteSkill)} disabled={busy || !skillEditor.id}>Delete</button>
                </div>
              </form>
            </article>

            <article className="card">
              <h3>Skill Preview</h3>
              <div className="studio-canvas" style={{ background: skillTheme.bg, borderColor: skillTheme.border, boxShadow: skillTheme.shadow }}>
                <div className="studio-canvas-header">
                  <span className="tag tag-model">p{skillEditor.priority || 0}</span>
                  <span className={`tag tag-cat-${skillEditor.category || "general"}`}>{skillEditor.category || "general"}</span>
                  <span className="tag">{skillEditor.trigger || "always"}</span>
                </div>
                <h4>{skillEditor.name || "Untitled Skill"}</h4>
                <p>{skillEditor.description || "Describe what this skill enforces and when it should activate."}</p>
                <div className="studio-chip-row">
                  {(skillEditor.selectedToolNames || []).length ? skillEditor.selectedToolNames.map((toolName) => (
                    <span key={`preview-${toolName}`} className="tag">{toolName}</span>
                  )) : <span className="tag">No tools bound</span>}
                </div>
                <div className="studio-rule-list">
                  {skillMarkdownLines.length ? skillMarkdownLines.map((line, index) => (
                    <div key={`line-${index}`} className="studio-rule-item">{line}</div>
                  )) : <div className="studio-rule-item">Markdown instructions preview appears here live.</div>}
                </div>
              </div>
              <p className="subtle">Normalized JSON as it will be saved.</p>
              <pre>{jsonText({
                id: skillEditor.id || "new",
                name: skillEditor.name,
                description: skillEditor.description,
                category: skillEditor.category,
                trigger: skillEditor.trigger,
                priority: Number(skillEditor.priority || 0),
                requires_tools: skillEditor.selectedToolNames,
                output_schema: skillEditor.output_schema,
                abort_on_fail: skillEditor.abort_on_fail,
                markdown: skillEditor.markdown,
                is_active: skillEditor.is_active,
              })}</pre>
            </article>
          </div>
        </section>
      );
    }

    const filtered = skills.filter((skill) => {
      const searchHit =
        skillSearch === "" ||
        String(skill.name || "").toLowerCase().includes(skillSearch.toLowerCase()) ||
        String(skill.description || "").toLowerCase().includes(skillSearch.toLowerCase()) ||
        String(skill.trigger || "").toLowerCase().includes(skillSearch.toLowerCase());
      const categoryHit = skillCategoryFilter === "all" || String(skill.category || "general") === skillCategoryFilter;
      return searchHit && categoryHit;
    });

    return (
      <section className="agent-list-wrap themed-page-shell">
        <CrudSubHeader title="Skills" meta={`${filtered.length} of ${skills.length} shown`}>
          <input className="search-input" placeholder="Search skills..." value={skillSearch} onChange={(e) => setSkillSearch(e.target.value)} />
          <div className="tool-filters-row">
            <select className="toolbar-select" value={skillCategoryFilter} onChange={(e) => setSkillCategoryFilter(e.target.value)}>
              <option value="all">All categories</option>
              {skillCategories.map((category) => (
                <option key={category} value={category}>{category}</option>
              ))}
            </select>
          </div>
          <div className="tool-actions-row">
            <button type="button" className="secondary" onClick={() => withOut("skillList", hydrateSkills)} disabled={busy}>Refresh</button>
            <button type="button" className="secondary" onClick={() => withOut("starterSkills", createStarterSkills)} disabled={busy}>Load Starter Skills</button>
            <button type="button" className="secondary" onClick={() => { setSkillSearch(""); setSkillCategoryFilter("all"); }} disabled={busy}>Clear</button>
            <button type="button" onClick={() => { setSkillEditor(initialSkillEditor()); setSkillView("editor"); }} disabled={busy}>+ Add Skill</button>
          </div>
        </CrudSubHeader>

        {filtered.length === 0 ? (
          <p className="agent-empty">No skills found for the current search and filter combination.</p>
        ) : (
          <div className="agent-card-grid">
            {filtered.map((skill) => (
              <div key={skill.id} className="agent-card skill-card">
                <div className="agent-card-header">
                  <span className={`tag tag-cat-${skill.category || "general"}`}>{skill.category || "general"}</span>
                  <span className="tag tag-model">p{skill.priority ?? 100}</span>
                  <span className={`status-dot ${skill.is_active ? "dot-active" : "dot-inactive"}`} title={skill.is_active ? "active" : "inactive"} />
                  <span className={skill.is_active ? "agent-badge badge-active" : "agent-badge badge-inactive"}>{skill.is_active ? "active" : "inactive"}</span>
                </div>
                <div className="agent-card-name">{skill.name}</div>
                <div className="agent-card-role tool-description" title={skill.description || ""}>{skill.description || "No description"}</div>
                <div className="agent-card-meta">
                  <span className="tag">trigger: {skill.trigger || "always"}</span>
                  {(Array.isArray(skill.requires_tools) ? skill.requires_tools : []).slice(0, 2).map((toolName) => (
                    <span key={`${skill.id}-${toolName}`} className="tag">{toolName}</span>
                  ))}
                </div>
                <div className="agent-card-footer">
                  <IconActionButton
                    icon="↗"
                    label={`Open skill ${skill.name}`}
                    tone="success"
                    className="card-open-action"
                    onClick={() => loadSkillEditor(String(skill.id))}
                  />
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    );
  };

  const renderAgents = () => {
    const activeSkills = skills.filter((skill) => skill.is_active);
    const selectedSkillModels = activeSkills.filter((skill) => agentEditor.selectedSkills.includes(skill.name));
    const dominantCategory = selectedSkillModels[0]?.category || "general";
    const agentTheme = getSkillPreviewTheme(dominantCategory, false);

    if (agentView === "editor") {
      return (
        <section className="agent-editor-wrap themed-page-shell">
          <div className="editor-breadcrumb">
            <button type="button" className="back-btn" onClick={() => setAgentView("grid")}>← All Agents</button>
            <span className="breadcrumb-sep">/</span>
            <span className="breadcrumb-current">{agentEditor.id ? agentEditor.name || "Edit Agent" : "New Agent"}</span>
          </div>
          <div className="content-grid agents-grid">
            <article className="card">
              <h3>{agentEditor.id ? "Edit Agent" : "New Agent"}</h3>
              <form className="stack" onSubmit={(event) => { event.preventDefault(); withOut("agentUpsert", upsertAgent); }}>
                <label>Template
                  <select value="" onChange={(e) => onTemplateChange(e.target.value)}>
                    <option value="">Select a template</option>
                    <option value="research">Research Analyst</option>
                    <option value="support">Support Triage Specialist</option>
                    <option value="concierge">Concierge</option>
                  </select>
                </label>
                <label>Name<input value={agentEditor.name} onChange={(e) => setAgentEditor((s) => ({ ...s, name: e.target.value }))} required /></label>
                <label>Role<input value={agentEditor.role} onChange={(e) => setAgentEditor((s) => ({ ...s, role: e.target.value }))} required /></label>
                <label>Description<input value={agentEditor.description} onChange={(e) => setAgentEditor((s) => ({ ...s, description: e.target.value }))} placeholder="Short summary of what this agent does" /></label>
                <label>Model
                  <select value={agentEditor.model} onChange={(e) => setAgentEditor((s) => ({ ...s, model: e.target.value }))}>
                    <option value="nvidia/nemotron-3-super-120b-a12b:free">nvidia/nemotron-3-super-120b-a12b:free</option>
                    <option value="gpt-4.1-mini">gpt-4.1-mini</option>
                    <option value="gpt-4.1">gpt-4.1</option>
                    <option value="gpt-4o-mini">gpt-4o-mini</option>
                  </select>
                </label>
                <label>System Prompt<textarea rows={4} value={agentEditor.system_prompt} onChange={(e) => setAgentEditor((s) => ({ ...s, system_prompt: e.target.value }))} required /></label>
                <label>Channels (comma separated)<input value={agentEditor.channelsText} onChange={(e) => setAgentEditor((s) => ({ ...s, channelsText: e.target.value }))} placeholder="internal, discord" /></label>
                <div className="tool-picker-label">
                  <details className="tool-picker-shell" open={agentEditor.selectedSkills.length === 0}>
                    <summary className="tool-picker-summary">
                      <span className="form-field-label">Tools</span>
                      <span className="tool-picker-count">{agentEditor.selectedTools.length} selected</span>
                      {agentEditor.selectedSkills.length > 0 && (
                        <span className="subtle" style={{ fontSize: "0.75rem", marginLeft: "0.5rem" }}>auto-derived from skills</span>
                      )}
                    </summary>
                  {agentEditor.selectedSkills.length > 0 ? (
                    // Read-only derived tool list
                    <div className="tool-picker">
                      {agentEditor.selectedTools.length === 0
                        ? <p className="subtle">No tools required by selected skills.</p>
                        : agentEditor.selectedTools.map((tool) => {
                            const toolDetail = tools.find((t) => t.name === tool.name);
                            return (
                              <div key={tool.name} className="tool-row tool-row-active">
                                <div className="tool-check-label">
                                  <input type="checkbox" checked readOnly disabled />
                                  <div className="tool-info">
                                    <span className="tool-name">{tool.name}</span>
                                    <span className="tool-desc">{toolDetail?.description || "Required by skill"}</span>
                                  </div>
                                  {toolDetail && <span className={`tag tag-cat-${toolDetail.category}`}>{toolDetail.category}</span>}
                                </div>
                              </div>
                            );
                          })
                      }
                    </div>
                  ) : (
                    // Manual picker when no skills selected
                    <>
                    {tools.length === 0 && <p className="subtle">No tools in library. Go to the Tools screen to add tools.</p>}
                    <div className="tool-picker">
                      {tools.filter((t) => t.is_active).map((tool) => {
                        const sel = agentEditor.selectedTools.find((s) => s.name === tool.name);
                        const toolInputId = `agent-tool-${String(tool.name).replace(/[^a-zA-Z0-9_-]/g, "-")}`;
                        return (
                          <div
                            key={tool.name}
                            className={`tool-row${sel ? " tool-row-active" : ""}`}
                            onClick={() => toggleAgentTool(tool)}
                            role="button"
                            tabIndex={0}
                            onKeyDown={(event) => {
                              if (event.key === "Enter" || event.key === " ") {
                                event.preventDefault();
                                toggleAgentTool(tool);
                              }
                            }}
                          >
                            <div className="tool-check-label">
                              <input
                                id={toolInputId}
                                type="checkbox"
                                checked={!!sel}
                                onClick={(event) => event.stopPropagation()}
                                onChange={() => toggleAgentTool(tool)}
                              />
                              <div className="tool-info">
                                <label className="tool-name" htmlFor={toolInputId}>{tool.name}</label>
                                <span className="tool-desc">{tool.description}</span>
                              </div>
                              <span className={`tag tag-cat-${tool.category}`}>{tool.category}</span>
                            </div>
                            {sel && (
                              <div className="tool-caps" onClick={(event) => event.stopPropagation()}>
                                {tool.capabilities.map((cap) => (
                                  <label key={cap} className="cap-check">
                                    <input
                                      type="checkbox"
                                      checked={sel.capabilities.includes(cap)}
                                      onChange={() => toggleAgentToolCap(tool.name, cap)}
                                    />
                                    {cap}
                                  </label>
                                ))}
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                    </>
                  )}
                  </details>
                </div>
                <div className="tool-picker-label">
                  <details className="tool-picker-shell" open>
                    <summary className="tool-picker-summary">
                      <span className="form-field-label">Skills</span>
                      <span className="tool-picker-count">{agentEditor.selectedSkills.length} selected</span>
                    </summary>
                    {activeSkills.length === 0 && (
                      <p className="subtle">No active skills found. Create skills in Skill Studio first.</p>
                    )}
                    <div className="tool-picker">
                      {activeSkills.map((skill) => {
                        const selected = agentEditor.selectedSkills.includes(skill.name);
                        const skillInputId = `agent-skill-${String(skill.name).replace(/[^a-zA-Z0-9_-]/g, "-")}`;
                        return (
                          <div
                            key={skill.name}
                            className={`tool-row${selected ? " tool-row-active" : ""}`}
                            onClick={() => toggleAgentSkill(skill.name)}
                            role="button"
                            tabIndex={0}
                            onKeyDown={(event) => {
                              if (event.key === "Enter" || event.key === " ") {
                                event.preventDefault();
                                toggleAgentSkill(skill.name);
                              }
                            }}
                          >
                            <div className="tool-check-label">
                              <input
                                id={skillInputId}
                                type="checkbox"
                                checked={selected}
                                onClick={(event) => event.stopPropagation()}
                                onChange={() => toggleAgentSkill(skill.name)}
                              />
                              <div className="tool-info">
                                <label className="tool-name" htmlFor={skillInputId}>{skill.name}</label>
                                <span className="tool-desc">{skill.description || "No description"}</span>
                              </div>
                              <span className="tag tag-model">p{skill.priority ?? 100}</span>
                              <span className={`tag tag-cat-${skill.category || "general"}`}>{skill.category || "general"}</span>
                            </div>
                            <div className="tool-caps">
                              <span className="cap-check">trigger: {skill.trigger || "always"}</span>
                              {(Array.isArray(skill.requires_tools) ? skill.requires_tools : []).map((toolName) => (
                                <span key={`${skill.name}-${toolName}`} className="cap-check">needs: {toolName}</span>
                              ))}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </details>
                </div>
                <details>
                  <summary>Skills (raw JSON or Markdown)</summary>
                  <label>Skills (raw)
                    <textarea
                      rows={5}
                      value={agentEditor.skillsText}
                      onChange={(e) => setAgentEditor((s) => ({ ...s, skillsText: e.target.value, selectedSkills: skillNamesFromValue(e.target.value) }))}
                      placeholder={'["evidence-first-research", "quality-review-loop"]\n\n-or-\n\n- if evidence is missing, request another pass'}
                    />
                  </label>
                </details>
                <div className="quick-config-grid">
                  <label>Schedule Cadence
                    <select
                      value={(() => {
                        const parsed = parseJsonSafely(agentEditor.scheduleText);
                        return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? (parsed.cadence || "manual") : "manual";
                      })()}
                      onChange={(e) => setAgentEditor((s) => ({
                        ...s,
                        scheduleText: updateObjectText(s.scheduleText, (obj) => ({ ...obj, cadence: e.target.value })),
                      }))}
                    >
                      <option value="manual">manual</option>
                      <option value="realtime">realtime</option>
                      <option value="intraday">intraday</option>
                      <option value="end_of_day">end_of_day</option>
                    </select>
                  </label>
                  <label>Schedule Time (HH:MM)
                    <input
                      value={(() => {
                        const parsed = parseJsonSafely(agentEditor.scheduleText);
                        return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? (parsed.run_time || "") : "";
                      })()}
                      placeholder="09:30"
                      onChange={(e) => setAgentEditor((s) => ({
                        ...s,
                        scheduleText: updateObjectText(s.scheduleText, (obj) => {
                          const next = { ...obj };
                          const val = e.target.value.trim();
                          if (val) next.run_time = val;
                          else delete next.run_time;
                          return next;
                        }),
                      }))}
                    />
                  </label>
                  <label>Timezone
                    <input
                      value={(() => {
                        const parsed = parseJsonSafely(agentEditor.scheduleText);
                        return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? (parsed.timezone || "Asia/Kolkata") : "Asia/Kolkata";
                      })()}
                      onChange={(e) => setAgentEditor((s) => ({
                        ...s,
                        scheduleText: updateObjectText(s.scheduleText, (obj) => ({ ...obj, timezone: e.target.value || "Asia/Kolkata" })),
                      }))}
                    />
                  </label>
                </div>

                <div className="quick-config-grid">
                  <label>Memory Mode
                    <select
                      value={(() => {
                        const parsed = parseJsonSafely(agentEditor.memoryProfileText);
                        return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? (parsed.mode || "session") : "session";
                      })()}
                      onChange={(e) => setAgentEditor((s) => ({
                        ...s,
                        memoryProfileText: updateObjectText(s.memoryProfileText, (obj) => ({ ...obj, mode: e.target.value })),
                      }))}
                    >
                      <option value="session">session</option>
                      <option value="daily">daily</option>
                      <option value="rolling">rolling</option>
                    </select>
                  </label>
                  <label>Max Memory Items
                    <input
                      type="number"
                      min="1"
                      value={(() => {
                        const parsed = parseJsonSafely(agentEditor.memoryProfileText);
                        return parsed && typeof parsed === "object" && !Array.isArray(parsed) && parsed.max_items !== undefined ? String(parsed.max_items) : "";
                      })()}
                      placeholder="50"
                      onChange={(e) => setAgentEditor((s) => ({
                        ...s,
                        memoryProfileText: updateObjectText(s.memoryProfileText, (obj) => {
                          const next = { ...obj };
                          const val = e.target.value.trim();
                          if (val) next.max_items = Number(val);
                          else delete next.max_items;
                          return next;
                        }),
                      }))}
                    />
                  </label>
                  <label>Retention Days
                    <input
                      type="number"
                      min="1"
                      value={(() => {
                        const parsed = parseJsonSafely(agentEditor.memoryProfileText);
                        return parsed && typeof parsed === "object" && !Array.isArray(parsed) && parsed.retention_days !== undefined ? String(parsed.retention_days) : "";
                      })()}
                      placeholder="7"
                      onChange={(e) => setAgentEditor((s) => ({
                        ...s,
                        memoryProfileText: updateObjectText(s.memoryProfileText, (obj) => {
                          const next = { ...obj };
                          const val = e.target.value.trim();
                          if (val) next.retention_days = Number(val);
                          else delete next.retention_days;
                          return next;
                        }),
                      }))}
                    />
                  </label>
                </div>

                <label>Interaction Rules (one rule per line)
                  <textarea
                    rows={3}
                    value={listTextFromStored(agentEditor.interactionRulesText)}
                    onChange={(e) => setAgentEditor((s) => ({ ...s, interactionRulesText: listStoreFromInput(e.target.value) }))}
                    placeholder="Ask a clarifying question when the objective is ambiguous\nEscalate when the request requires human review"
                  />
                </label>

                <label>Guardrails (one rule per line)
                  <textarea
                    rows={3}
                    value={listTextFromStored(agentEditor.guardrailsText)}
                    onChange={(e) => setAgentEditor((s) => ({ ...s, guardrailsText: listStoreFromInput(e.target.value) }))}
                    placeholder="Reject requests that violate policy\nRequire human review for sensitive actions"
                  />
                </label>

                <div className="quick-config-grid">
                  <label>Max Daily Runs
                    <input
                      type="number"
                      min="1"
                      value={(() => {
                        const parsed = parseJsonSafely(agentEditor.limitsText);
                        return parsed && typeof parsed === "object" && !Array.isArray(parsed) && parsed.max_daily_runs !== undefined ? String(parsed.max_daily_runs) : "";
                      })()}
                      placeholder="25"
                      onChange={(e) => setAgentEditor((s) => ({
                        ...s,
                        limitsText: updateObjectText(s.limitsText, (obj) => {
                          const next = { ...obj };
                          const val = e.target.value.trim();
                          if (val) next.max_daily_runs = Number(val);
                          else delete next.max_daily_runs;
                          return next;
                        }),
                      }))}
                    />
                  </label>
                  <label>Max Concurrent Tasks
                    <input
                      type="number"
                      step="0.1"
                      min="0"
                      value={(() => {
                        const parsed = parseJsonSafely(agentEditor.limitsText);
                        return parsed && typeof parsed === "object" && !Array.isArray(parsed) && parsed.max_concurrent_tasks !== undefined ? String(parsed.max_concurrent_tasks) : "";
                      })()}
                      placeholder="5"
                      onChange={(e) => setAgentEditor((s) => ({
                        ...s,
                        limitsText: updateObjectText(s.limitsText, (obj) => {
                          const next = { ...obj };
                          const val = e.target.value.trim();
                          if (val) next.max_concurrent_tasks = Number(val);
                          else delete next.max_concurrent_tasks;
                          return next;
                        }),
                      }))}
                    />
                  </label>
                  <label>Max Queue Depth
                    <input
                      type="number"
                      min="1"
                      value={(() => {
                        const parsed = parseJsonSafely(agentEditor.limitsText);
                        return parsed && typeof parsed === "object" && !Array.isArray(parsed) && parsed.max_queue_depth !== undefined ? String(parsed.max_queue_depth) : "";
                      })()}
                      placeholder="5"
                      onChange={(e) => setAgentEditor((s) => ({
                        ...s,
                        limitsText: updateObjectText(s.limitsText, (obj) => {
                          const next = { ...obj };
                          const val = e.target.value.trim();
                          if (val) next.max_queue_depth = Number(val);
                          else delete next.max_queue_depth;
                          return next;
                        }),
                      }))}
                    />
                  </label>
                </div>

                <details>
                  <summary>Advanced Raw Config (JSON or Markdown)</summary>
                  <label>Schedule (raw)<textarea rows={3} value={agentEditor.scheduleText} onChange={(e) => setAgentEditor((s) => ({ ...s, scheduleText: e.target.value }))} /></label>
                  <label>Memory Profile (raw)<textarea rows={3} value={agentEditor.memoryProfileText} onChange={(e) => setAgentEditor((s) => ({ ...s, memoryProfileText: e.target.value }))} /></label>
                  <label>Interaction Rules (raw)<textarea rows={3} value={agentEditor.interactionRulesText} onChange={(e) => setAgentEditor((s) => ({ ...s, interactionRulesText: e.target.value }))} /></label>
                  <label>Guardrails (raw)<textarea rows={3} value={agentEditor.guardrailsText} onChange={(e) => setAgentEditor((s) => ({ ...s, guardrailsText: e.target.value }))} /></label>
                  <label>Limits (raw)<textarea rows={3} value={agentEditor.limitsText} onChange={(e) => setAgentEditor((s) => ({ ...s, limitsText: e.target.value }))} /></label>
                </details>
                <label>Active
                  <select value={agentEditor.is_active ? "true" : "false"} onChange={(e) => setAgentEditor((s) => ({ ...s, is_active: e.target.value === "true" }))}>
                    <option value="true">true</option>
                    <option value="false">false</option>
                  </select>
                </label>
                <div className="inline">
                  <button type="submit" disabled={busy}>{agentEditor.id ? "Update Agent" : "Create Agent"}</button>
                  <button type="button" className="secondary" onClick={() => withOut("agentDelete", deleteAgent)} disabled={busy || !agentEditor.id}>Delete</button>
                  <button type="button" className="accent" onClick={() => withOut("agentDeploy", deployAgent)} disabled={busy || !selectedAgent || !!selectedAgent.is_active}>Deploy</button>
                </div>
                <p className="subtle">Deploy status: {selectedAgent && selectedAgent.is_active ? "Deployed" : "Not deployed"}</p>
              </form>
            </article>
            <article className="card">
              <h3>Configuration Preview</h3>
              <div className="studio-canvas" style={{ background: agentTheme.bg, borderColor: agentTheme.border, boxShadow: agentTheme.shadow }}>
                <div className="studio-canvas-header">
                  <span className="tag tag-model">{agentEditor.model || "model"}</span>
                  <span className="tag">{csvToList(agentEditor.channelsText).join(", ") || "no channels"}</span>
                  <span className={`tag ${agentEditor.is_active ? "badge-active" : "badge-inactive"}`}>{agentEditor.is_active ? "active" : "inactive"}</span>
                </div>
                <h4>{agentEditor.name || "Untitled Agent"}</h4>
                <p>{agentEditor.role || "Assign a role to see the live agent identity here."}</p>
                <div className="studio-chip-row">
                  {selectedSkillModels.length ? selectedSkillModels.map((skill) => (
                    <span key={`agent-skill-preview-${skill.name}`} className={`tag tag-cat-${skill.category || "general"}`}>{skill.name}</span>
                  )) : <span className="tag">No skills selected</span>}
                </div>
                <div className="studio-chip-row">
                  {(agentEditor.selectedTools || []).length ? agentEditor.selectedTools.map((tool) => (
                    <span key={`agent-tool-preview-${tool.name}`} className="tag">{tool.name}</span>
                  )) : <span className="tag">No tools selected</span>}
                </div>
                <div className="studio-rule-list">
                  <div className="studio-rule-item">Tool dependencies satisfied via selected skills.</div>
                </div>
              </div>
              <p className="subtle">Normalized JSON as it will be saved.</p>
              <pre>{jsonText({
                id: agentEditor.id || "new",
                name: agentEditor.name,
                role: agentEditor.role,
                model: agentEditor.model,
                channels: csvToList(agentEditor.channelsText),
                tools: agentEditor.selectedTools,
                skills: agentEditor.selectedSkills.length ? agentEditor.selectedSkills : parseSkillsPayload(agentEditor.skillsText),
                schedule: parseJsonOrText(agentEditor.scheduleText, {}),
                memory_profile: parseJsonOrText(agentEditor.memoryProfileText, {}),
                interaction_rules: parseJsonOrText(agentEditor.interactionRulesText, []),
                guardrails: parseJsonOrText(agentEditor.guardrailsText, []),
                limits: parseJsonOrText(agentEditor.limitsText, {}),
                is_active: agentEditor.is_active,
              })}</pre>
            </article>
          </div>
        </section>
      );
    }

    // ── Grid view ──────────────────────────────────────────────────
    const filtered = agents.filter(
      (a) =>
        agentSearch === "" ||
        a.name.toLowerCase().includes(agentSearch.toLowerCase()) ||
        (a.role || "").toLowerCase().includes(agentSearch.toLowerCase())
    );

    return (
      <section className="agent-list-wrap themed-page-shell">
        <CrudSubHeader title="Agents" meta={`${filtered.length} of ${agents.length} shown`}>
          <input
            className="search-input"
            placeholder="Search by name or role..."
            value={agentSearch}
            onChange={(e) => setAgentSearch(e.target.value)}
          />
          <div className="tool-actions-row">
            <button type="button" className="secondary" onClick={() => withOut("agentList", hydrateAgents)} disabled={busy}>Refresh</button>
            <button type="button" onClick={() => { resetAgentEditor(); setAgentView("editor"); }}>+ Add Agent</button>
          </div>
        </CrudSubHeader>

        {filtered.length === 0 ? (
          <div className="agent-empty">
            <p>{agentSearch ? "No agents match your search." : "No agents yet — click + Add Agent to create one."}</p>
          </div>
        ) : (
          <div className="agent-card-grid">
            {filtered.map((agent) => (
              <article key={agent.id} className="agent-card agent-profile-card">
                <div className="agent-card-header">
                  <span className={`status-dot ${agent.is_active ? "dot-active" : "dot-inactive"}`} title={agent.is_active ? "Active" : "Inactive"} />
                  <span className="agent-card-id">#{agent.id}</span>
                  <span className={`agent-badge ${agent.is_active ? "badge-active" : "badge-inactive"}`}>{agent.is_active ? "Active" : "Inactive"}</span>
                </div>
                <div className="agent-card-name">{agent.name}</div>
                <div className="agent-card-role">{agent.role || <span className="subtle">No role</span>}</div>
                {agent.description && <div className="agent-card-desc tool-description" title={agent.description}>{agent.description}</div>}
                <div className="agent-card-meta">
                  <span className="tag tag-model">{agent.model || "nvidia/nemotron-3-super-120b-a12b:free"}</span>
                  {Array.isArray(agent.tools) && agent.tools.length > 0 && (
                    <span className="tag">{agent.tools.length} tool{agent.tools.length !== 1 ? "s" : ""}</span>
                  )}
                  {Array.isArray(agent.channels) && agent.channels.length > 0 && (
                    <span className="tag">{agent.channels.join(", ")}</span>
                  )}
                </div>
                <div className="agent-card-footer">
                  <IconActionButton
                    icon="↗"
                    label={`Open agent ${agent.name}`}
                    tone="info"
                    className="card-open-action"
                    onClick={() => loadAgentEditor(agent.id)}
                  />
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
    );
  };

  const renderOperations = () => null;

  const renderWorkflows = (mode = "launcher") => {
    const showCrud = mode === "crud";
    const showLauncher = mode === "launcher";
    const showDiscord = mode === "discord";
    const selectedTemplate = workflowTemplates.find((template) => String(template.id) === String(selectedWorkflowTemplateId)) || workflowTemplates[0] || null;
    const nodes = Array.isArray(selectedTemplate?.nodes) ? selectedTemplate.nodes : [];
    const edges = Array.isArray(selectedTemplate?.edges) ? selectedTemplate.edges : [];
    const focusedRunId = metricsRunId || runIdOptions[0] || "";
    const conciergeAgent = agents.find((agent) => String(agent.name || "") === "ConciergeAgent") || null;
    const latestDiscordConversation = discordConversations[0] || null;
    const latestDiscordMessages = Array.isArray(latestDiscordConversation?.messages) ? latestDiscordConversation.messages : [];
    const lastDiscordResult = parseJsonSafely(out.discordWebhook) || {};
    const discordDeliveryMode = String(lastDiscordResult.delivery_mode || (discordBotStatus?.running ? "discord_bot" : "local_record_only"));
    const discordExternallySent = Boolean(lastDiscordResult.externally_sent);
    const discordDeliveryLabel = (() => {
      if (discordDeliveryMode === "discord_bot") return "Live Discord bot delivery";
      if (discordDeliveryMode === "discord_webhook") return "Live Discord webhook delivery";
      if (discordDeliveryMode === "discord_bot_not_running") return "Bot configured but not running";
      if (discordDeliveryMode === "discord_webhook_failed") return "Webhook delivery failed";
      return "Local transcript only";
    })();
    const conditionText = (edge) => edge?.condition ? jsonText(edge.condition) : "always";

    const setWorkflowInput = (key, value) => {
      setWorkflowRunForm((prev) => ({ ...prev, [key]: value }));
    };

    const filteredWorkflowTemplates = workflowTemplates.filter((template) => {
      const searchHit =
        workflowSearch === "" ||
        String(template.name || "").toLowerCase().includes(workflowSearch.toLowerCase()) ||
        String(template.description || "").toLowerCase().includes(workflowSearch.toLowerCase());
      const statusHit =
        workflowStatusFilter === "all" ||
        (workflowStatusFilter === "active" && !!template.is_active) ||
        (workflowStatusFilter === "inactive" && !template.is_active);
      return searchHit && statusHit;
    });

    return (
      <section className="workflow-shell themed-page-shell">
        {showLauncher ? (
        <div className="workflow-hero-grid">
          <article className="card workflow-launch-card">
            <div className="section-head section-head-tight">
              <div>
                <p className="section-kicker">LangGraph</p>
                <h3>Workflow Launcher</h3>
              </div>
              <span className="composer-badge">{workflowTemplates.length ? `${workflowTemplates.length} templates` : "No templates"}</span>
            </div>
            <p className="subtle">Seed demo templates, choose a workflow, and run it directly from the UI. Discord messages now live on their own screen.</p>
            <div className="workflow-action-row">
              <button type="button" className="secondary" onClick={() => withOut("seedWorkflowTemplates", seedWorkflowTemplates)} disabled={busy}>Seed Defaults</button>
              <button type="button" className="secondary" onClick={() => withOut("workflowTemplates", hydrateWorkflowTemplates, { notifySuccess: false })} disabled={busy}>Refresh Templates</button>
            </div>
            <form className="stack" onSubmit={(event) => { event.preventDefault(); withOut("workflowRun", runSelectedWorkflowTemplate); }}>
              <label>Workflow Template
                <select value={selectedTemplate ? String(selectedTemplate.id) : ""} onChange={(event) => setSelectedWorkflowTemplateId(event.target.value)}>
                  {workflowTemplates.length ? workflowTemplates.map((template) => (
                    <option key={template.id} value={template.id}>{template.name}</option>
                  )) : <option value="">Seed templates first</option>}
                </select>
              </label>
              <label>Objective
                <textarea rows={4} value={workflowRunForm.objective} onChange={(event) => setWorkflowInput("objective", event.target.value)} />
              </label>
              <div className="ops-form-grid">
                <label>Customer ID
                  <input type="text" value={workflowRunForm.customer_id} onChange={(event) => setWorkflowInput("customer_id", event.target.value)} />
                </label>
                <label>Execution Channel
                  <input type="text" value="UI direct run" readOnly />
                </label>
              </div>
              <button className="accent" type="submit" disabled={busy || !selectedTemplate}>{busy ? "Running..." : "Run Workflow"}</button>
            </form>
          </article>

          <article className="card workflow-template-card">
            <div className="section-head section-head-tight">
              <div>
                <p className="section-kicker">Template</p>
                <h3>{selectedTemplate?.name || "No Template Selected"}</h3>
              </div>
              <span className={selectedTemplate?.is_active ? "chip" : "chip chip-neutral"}>{selectedTemplate?.is_active ? "Active" : "Inactive"}</span>
            </div>
            <p className="subtle">{selectedTemplate?.description || "Seed defaults to create the two demo workflows required by the challenge."}</p>
            <div className="workflow-stats-grid">
              <article className="overview-metric"><span>Nodes</span><strong>{nodes.length}</strong></article>
              <article className="overview-metric"><span>Edges</span><strong>{edges.length}</strong></article>
              <article className="overview-metric"><span>Agents</span><strong>{Array.isArray(selectedTemplate?.default_agents) ? selectedTemplate.default_agents.length : 0}</strong></article>
              <article className="overview-metric"><span>Version</span><strong>{selectedTemplate?.version || "-"}</strong></article>
            </div>
            <div className="workflow-node-list">
              {nodes.length ? nodes.map((node) => (
                <div key={node.key || node.node_key} className="workflow-node-row">
                  <strong>{node.label || node.key}</strong>
                  <span>{node.agent || "No agent"}</span>
                  <small>{(node.tools || []).join(", ") || "No tools"}</small>
                </div>
              )) : <p className="subtle">No nodes available.</p>}
            </div>
          </article>
        </div>
        ) : null}

        {showCrud ? (
          workflowCrudView === "grid" ? (
            <section className="agent-list-wrap themed-page-shell">
              <CrudSubHeader title="Workflows" meta={`${filteredWorkflowTemplates.length} of ${workflowTemplates.length} shown`}>
                <input
                  className="search-input"
                  placeholder="Search by name or description..."
                  value={workflowSearch}
                  onChange={(event) => setWorkflowSearch(event.target.value)}
                />
                <div className="tool-filters-row">
                  <select className="toolbar-select" value={workflowStatusFilter} onChange={(event) => setWorkflowStatusFilter(event.target.value)}>
                    <option value="all">All status</option>
                    <option value="active">active</option>
                    <option value="inactive">inactive</option>
                  </select>
                </div>
                <div className="tool-actions-row">
                  <button type="button" className="secondary" onClick={() => withOut("workflowTemplates", hydrateWorkflowTemplates, { notifySuccess: false })} disabled={busy}>Refresh</button>
                  <button type="button" className="secondary" onClick={() => withOut("seedWorkflowTemplates", seedWorkflowTemplates)} disabled={busy}>Seed Defaults</button>
                  <button
                    type="button"
                    onClick={() => {
                      setWorkflowTemplateDraft({ name: "", description: "", version: "1.0" });
                      setWorkflowCrudView("editor");
                    }}
                    disabled={busy}
                  >
                    + Add Workflow
                  </button>
                </div>
              </CrudSubHeader>

              {filteredWorkflowTemplates.length === 0 ? (
                <div className="agent-empty">
                  <p>No workflows match your search and filters.</p>
                </div>
              ) : (
                <div className="agent-card-grid">
                  {filteredWorkflowTemplates
                    .map((template) => {
                      const templateNodes = Array.isArray(template.nodes) ? template.nodes.length : 0;
                      const templateEdges = Array.isArray(template.edges) ? template.edges.length : 0;
                      return (
                        <article key={template.id} className="agent-card workflow-library-card">
                          <div className="agent-card-header">
                            <span className={`status-dot ${template.is_active ? "dot-active" : "dot-inactive"}`} title={template.is_active ? "Active" : "Inactive"} />
                            <span className="agent-card-id">#{template.id}</span>
                            <span className={`agent-badge ${template.is_active ? "badge-active" : "badge-inactive"}`}>{template.is_active ? "Active" : "Inactive"}</span>
                          </div>
                          <div className="agent-card-name">{template.name}</div>
                          <div className="agent-card-role tool-description" title={template.description || ""}>{template.description || "No description"}</div>
                          <div className="agent-card-meta">
                            <span className="tag">v{template.version || "1.0"}</span>
                            <span className="tag">{templateNodes} node{templateNodes !== 1 ? "s" : ""}</span>
                            <span className="tag">{templateEdges} edge{templateEdges !== 1 ? "s" : ""}</span>
                          </div>
                          <div className="agent-card-footer">
                            <IconActionButton
                              icon="↗"
                              label={`Open workflow ${template.name}`}
                              tone="info"
                              className="card-open-action"
                              onClick={() => {
                                setSelectedWorkflowTemplateId(String(template.id));
                                setWorkflowCrudView("editor");
                              }}
                            />
                          </div>
                        </article>
                      );
                    })}
                </div>
              )}
            </section>
          ) : (
            <section className="agent-editor-wrap themed-page-shell">
              <div className="editor-breadcrumb">
                <button type="button" className="back-btn" onClick={() => setWorkflowCrudView("grid")}>← All Workflows</button>
                <span className="breadcrumb-sep">/</span>
                <span className="breadcrumb-current">{selectedTemplate?.name || "Workflow Editor"}</span>
              </div>
              <article className="card workflow-template-card workflow-crud-card">
                <div className="section-head section-head-tight">
                  <div>
                    <p className="section-kicker">Workflow CRUD</p>
                    <h3>{selectedTemplate?.name || "No Template Selected"}</h3>
                  </div>
                  <span className={selectedTemplate?.is_active ? "chip" : "chip chip-neutral"}>{selectedTemplate?.is_active ? "Active" : "Inactive"}</span>
                </div>
                <p className="subtle">Manage workflow templates, nodes, edges, conditions, feedback loops, and agent/tool bindings.</p>
                <div className="workflow-crud-layout">
                  <section className="workflow-crud-column workflow-admin-column">
                    <details className="workflow-admin-details">
                      <summary>Template Management (Optional)</summary>
                      <div className="workflow-crud-panel">
                      <h4>Template Actions</h4>
                      <div className="workflow-action-row">
                        <IconActionButton icon="◎" label="Seed defaults" tone="success" onClick={() => withOut("seedWorkflowTemplates", seedWorkflowTemplates)} disabled={busy} />
                        <IconActionButton icon="⟳" label="Refresh templates" tone="info" onClick={() => withOut("workflowTemplates", hydrateWorkflowTemplates, { notifySuccess: false })} disabled={busy} />
                      </div>
                    </div>

                    <div className="workflow-crud-panel">
                      <h4>Create New Workflow</h4>
                      <div className="ops-form-grid">
                        <input
                          placeholder="workflow name"
                          value={workflowTemplateDraft.name}
                          onChange={(event) => setWorkflowTemplateDraft((prev) => ({ ...prev, name: event.target.value }))}
                        />
                        <input
                          placeholder="version (e.g. 1.0)"
                          value={workflowTemplateDraft.version}
                          onChange={(event) => setWorkflowTemplateDraft((prev) => ({ ...prev, version: event.target.value }))}
                        />
                      </div>
                      <textarea
                        rows={2}
                        placeholder="workflow description"
                        value={workflowTemplateDraft.description}
                        onChange={(event) => setWorkflowTemplateDraft((prev) => ({ ...prev, description: event.target.value }))}
                      />
                      <div className="workflow-action-row">
                        <IconActionButton
                          icon="+"
                          label="Create workflow"
                          tone="success"
                          onClick={() => withOut("workflowTemplateCreate", createWorkflowTemplate)}
                          disabled={busy}
                        />
                      </div>
                    </div>

                    <div className="workflow-crud-panel">
                      <h4>Template Selection</h4>
                      <label className="workflow-template-picker">Workflow Template
                        <select value={selectedTemplate ? String(selectedTemplate.id) : ""} onChange={(event) => setSelectedWorkflowTemplateId(event.target.value)}>
                          {workflowTemplates.length ? workflowTemplates.map((template) => (
                            <option key={template.id} value={template.id}>{template.name}</option>
                          )) : <option value="">Seed templates first</option>}
                        </select>
                      </label>
                      <p className="subtle">{selectedTemplate?.description || "Seed defaults to create the two demo workflows required by the challenge."}</p>
                    </div>

                    <div className="workflow-crud-panel">
                      <h4>Template Snapshot</h4>
                      <div className="workflow-stats-grid">
                        <article className="overview-metric"><span>Nodes</span><strong>{nodes.length}</strong></article>
                        <article className="overview-metric"><span>Edges</span><strong>{edges.length}</strong></article>
                        <article className="overview-metric"><span>Agents</span><strong>{Array.isArray(selectedTemplate?.default_agents) ? selectedTemplate.default_agents.length : 0}</strong></article>
                        <article className="overview-metric"><span>Version</span><strong>{selectedTemplate?.version || "-"}</strong></article>
                      </div>
                    </div>
                    </details>
                  </section>

                  <section className="workflow-crud-column workflow-edit-column">
                    <div className="workflow-crud-panel workflow-builder-panel">
                      <div className="workflow-form-header">
                        <h4>Visual Builder</h4>
                        <div className="workflow-edge-actions workflow-builder-head-actions">
                          <div className="workflow-mode-toggle" role="group" aria-label="Builder mode">
                            <button
                              type="button"
                              className={workflowBuilderMode === "basic" ? "chip" : "chip chip-neutral"}
                              onClick={() => setWorkflowBuilderMode("basic")}
                            >
                              Basic
                            </button>
                            <button
                              type="button"
                              className={workflowBuilderMode === "advanced" ? "chip" : "chip chip-neutral"}
                              onClick={() => setWorkflowBuilderMode("advanced")}
                            >
                              Advanced
                            </button>
                          </div>
                          <span className="chip">Node mode: {editingNodeIndex !== null ? "edit" : "add"}</span>
                          <span className="chip">Edge mode: {editingEdgeIndex !== null ? "edit" : "add"}</span>
                        </div>
                      </div>
                      <div className="workflow-editor-tabs" role="tablist" aria-label="Builder editor tab">
                        <button
                          type="button"
                          role="tab"
                          aria-selected={workflowEditorTab === "node"}
                          className={workflowEditorTab === "node" ? "workflow-editor-tab workflow-editor-tab-active" : "workflow-editor-tab"}
                          onClick={() => setWorkflowEditorTab("node")}
                        >
                          Node Editor
                        </button>
                        <button
                          type="button"
                          role="tab"
                          aria-selected={workflowEditorTab === "edge"}
                          className={workflowEditorTab === "edge" ? "workflow-editor-tab workflow-editor-tab-active" : "workflow-editor-tab"}
                          onClick={() => setWorkflowEditorTab("edge")}
                        >
                          Edge Editor
                        </button>
                        <button
                          type="button"
                          role="tab"
                          aria-selected={workflowEditorTab === "graph"}
                          className={workflowEditorTab === "graph" ? "workflow-editor-tab workflow-editor-tab-active" : "workflow-editor-tab"}
                          onClick={() => setWorkflowEditorTab("graph")}
                        >
                          Graph Preview
                        </button>
                      </div>
                      <p className="subtle">{workflowBuilderMode === "basic" ? "Basic mode shows only essential fields." : "Advanced mode exposes full controls for the selected editor tab."}</p>

                      {workflowEditorTab === "node" ? (
                        <>
                      <h5 className="workflow-subhead">Node Details</h5>
                      <div className="ops-form-grid workflow-form-grid">
                        <label className="workflow-field">
                          <span className="workflow-field-label">Node Key</span>
                          <input value={nodeDraft.node_key} onChange={(event) => setNodeDraft((prev) => ({ ...prev, node_key: event.target.value }))} />
                        </label>
                        <label className="workflow-field">
                          <span className="workflow-field-label">Node Label</span>
                          <input value={nodeDraft.label} onChange={(event) => setNodeDraft((prev) => ({ ...prev, label: event.target.value }))} />
                        </label>
                        <label className="workflow-field">
                          <span className="workflow-field-label">Objective</span>
                          <input value={nodeDraft.objective} onChange={(event) => setNodeDraft((prev) => ({ ...prev, objective: event.target.value }))} />
                        </label>
                        <label className="workflow-field">
                          <span className="workflow-field-label">Node Type</span>
                          <select value={nodeDraft.node_type} onChange={(event) => setNodeDraft((prev) => ({ ...prev, node_type: event.target.value }))}>
                            <option value="agent">agent</option>
                            <option value="tool">tool</option>
                            <option value="decision">decision</option>
                            <option value="final">final</option>
                          </select>
                        </label>
                        <label className="workflow-field">
                          <span className="workflow-field-label">Agent</span>
                          <select value={nodeDraft.agent} onChange={(event) => setNodeDraft((prev) => ({ ...prev, agent: event.target.value }))}>
                            <option value="">Select agent</option>
                            {agents.map((agent) => <option key={agent.id} value={agent.name}>{agent.name}</option>)}
                          </select>
                        </label>
                        <label className="workflow-field">
                          <span className="workflow-field-label">Tools Override</span>
                          <input value={nodeDraft.toolsText} onChange={(event) => setNodeDraft((prev) => ({ ...prev, toolsText: event.target.value }))} placeholder="optional" />
                        </label>
                        <label className="workflow-field">
                          <span className="workflow-field-label">Skills Override</span>
                          <input value={nodeDraft.skillsText} onChange={(event) => setNodeDraft((prev) => ({ ...prev, skillsText: event.target.value }))} placeholder="optional" />
                        </label>
                        {workflowBuilderMode === "advanced" ? (
                          <>
                            <label className="workflow-field">
                              <span className="workflow-field-label">Position X</span>
                              <input type="number" value={nodeDraft.x} onChange={(event) => setNodeDraft((prev) => ({ ...prev, x: Number(event.target.value || 0) }))} />
                            </label>
                            <label className="workflow-field">
                              <span className="workflow-field-label">Position Y</span>
                              <input type="number" value={nodeDraft.y} onChange={(event) => setNodeDraft((prev) => ({ ...prev, y: Number(event.target.value || 0) }))} />
                            </label>
                          </>
                        ) : null}
                      </div>
                      {workflowBuilderMode === "advanced" ? (
                        <div className="workflow-pairs-editor">
                          <strong>Node Config</strong>
                          {nodeDraft.configPairs.length ? nodeDraft.configPairs.map((pair, pairIndex) => (
                            <div key={`node-config-${pairIndex}`} className="workflow-pair-row">
                              <input
                                placeholder="key"
                                value={pair.key}
                                onChange={(event) => setNodeDraft((prev) => ({
                                  ...prev,
                                  configPairs: prev.configPairs.map((entry, index) => index === pairIndex ? { ...entry, key: event.target.value } : entry),
                                }))}
                              />
                              <input
                                placeholder="value"
                                value={pair.value}
                                onChange={(event) => setNodeDraft((prev) => ({
                                  ...prev,
                                  configPairs: prev.configPairs.map((entry, index) => index === pairIndex ? { ...entry, value: event.target.value } : entry),
                                }))}
                              />
                              <button
                                type="button"
                                className="icon-action-button icon-action-danger"
                                onClick={() => setNodeDraft((prev) => ({
                                  ...prev,
                                  configPairs: prev.configPairs.filter((_, index) => index !== pairIndex),
                                }))}
                                aria-label="Remove node config field"
                                title="Remove node config field"
                              >
                                ✕
                              </button>
                            </div>
                          )) : <p className="subtle">No custom config fields.</p>}
                          <IconActionButton
                            icon="+"
                            label="Add node config field"
                            tone="success"
                            onClick={() => setNodeDraft((prev) => ({ ...prev, configPairs: [...prev.configPairs, { key: "", value: "" }] }))}
                          />
                        </div>
                      ) : null}
                      <p className="subtle">Tools and skills auto-bind from the selected agent. Fill override fields only when needed.</p>
                      <div className="workflow-action-row">
                        <IconActionButton
                          icon={editingNodeIndex !== null ? "✓" : "+"}
                          label={editingNodeIndex !== null ? "Update node" : "Add node"}
                          tone="success"
                          onClick={() => withOut("workflowNodeSave", () => saveWorkflowNode(selectedTemplate))}
                          disabled={busy || !selectedTemplate}
                        />
                        <IconActionButton icon="⌫" label="Clear node form" tone="slate" onClick={resetNodeDraft} disabled={busy} />
                      </div>
                        </>
                      ) : null}

                      {workflowEditorTab === "edge" ? (
                        <>
                      <h5 className="workflow-subhead">Edge Transition</h5>
                      <div className="ops-form-grid workflow-form-grid">
                        <label className="workflow-field">
                          <span className="workflow-field-label">Source Node</span>
                          <select value={edgeDraft.source_node_key} onChange={(event) => setEdgeDraft((prev) => ({ ...prev, source_node_key: event.target.value }))}>
                            <option value="">Source node</option>
                            {nodes.map((node) => <option key={`source-${node.key || node.node_key}`} value={node.key || node.node_key}>{node.key || node.node_key}</option>)}
                          </select>
                        </label>
                        <label className="workflow-field">
                          <span className="workflow-field-label">Target Node</span>
                          <select value={edgeDraft.target_node_key} onChange={(event) => setEdgeDraft((prev) => ({ ...prev, target_node_key: event.target.value }))}>
                            <option value="">Target node</option>
                            {nodes.map((node) => <option key={`target-${node.key || node.node_key}`} value={node.key || node.node_key}>{node.key || node.node_key}</option>)}
                          </select>
                        </label>
                        <label className="workflow-toggle-row workflow-field workflow-field-wide">
                          <span className="workflow-field-label">Feedback Loop</span>
                          <span>
                            <input type="checkbox" checked={edgeDraft.feedbackLoop} onChange={(event) => setEdgeDraft((prev) => ({ ...prev, feedbackLoop: event.target.checked }))} />
                            Feedback loop
                          </span>
                        </label>
                      </div>
                      {workflowBuilderMode === "advanced" ? (
                        <div className="workflow-pairs-editor">
                          <strong>Edge Condition</strong>
                          {edgeDraft.conditionPairs.length ? edgeDraft.conditionPairs.map((pair, pairIndex) => (
                            <div key={`edge-condition-${pairIndex}`} className="workflow-pair-row">
                              <input
                                placeholder="key (field/op/value)"
                                value={pair.key}
                                onChange={(event) => setEdgeDraft((prev) => ({
                                  ...prev,
                                  conditionPairs: prev.conditionPairs.map((entry, index) => index === pairIndex ? { ...entry, key: event.target.value } : entry),
                                }))}
                              />
                              <input
                                placeholder="value"
                                value={pair.value}
                                onChange={(event) => setEdgeDraft((prev) => ({
                                  ...prev,
                                  conditionPairs: prev.conditionPairs.map((entry, index) => index === pairIndex ? { ...entry, value: event.target.value } : entry),
                                }))}
                              />
                              <button
                                type="button"
                                className="icon-action-button icon-action-danger"
                                onClick={() => setEdgeDraft((prev) => ({
                                  ...prev,
                                  conditionPairs: prev.conditionPairs.filter((_, index) => index !== pairIndex),
                                }))}
                                aria-label="Remove edge condition field"
                                title="Remove edge condition field"
                              >
                                ✕
                              </button>
                            </div>
                          )) : <p className="subtle">No edge condition set. Leave empty for always-on transition.</p>}
                          <div className="workflow-action-row">
                            <IconActionButton
                              icon="+"
                              label="Add condition field"
                              tone="success"
                              onClick={() => setEdgeDraft((prev) => ({ ...prev, conditionPairs: [...prev.conditionPairs, { key: "", value: "" }] }))}
                            />
                            <IconActionButton
                              icon="↺"
                              label="Use retry preset"
                              tone="info"
                              onClick={() => setEdgeDraft((prev) => ({ ...prev, conditionPairs: [{ key: "field", value: "outputs.quality_review.enough_evidence" }, { key: "op", value: "eq" }, { key: "value", value: "false" }] }))}
                            />
                          </div>
                        </div>
                      ) : null}
                      <div className="workflow-action-row">
                        <IconActionButton
                          icon={editingEdgeIndex !== null ? "✓" : "+"}
                          label={editingEdgeIndex !== null ? "Update edge" : "Add edge"}
                          tone="success"
                          onClick={() => withOut("workflowEdgeSave", () => saveWorkflowEdge(selectedTemplate))}
                          disabled={busy || !selectedTemplate}
                        />
                        <IconActionButton icon="⌫" label="Clear edge form" tone="slate" onClick={resetEdgeDraft} disabled={busy} />
                      </div>
                        </>
                      ) : null}

                      {workflowEditorTab === "graph" ? (
                        <WorkflowGraphPreview
                          nodes={nodes}
                          edges={edges}
                          onNodeClick={(node) => {
                            const idx = nodes.findIndex((n) => String(n.key || n.node_key) === String(node.key || node.node_key));
                            if (idx !== -1) loadNodeDraft(node, idx);
                          }}
                        />
                      ) : null}
                    </div>

                    <div className="workflow-lists-grid">
                      <div className="workflow-crud-panel workflow-nodes-panel">
                        <h4>Workflow Nodes</h4>
                        <p className="subtle">Click any row to load it into the builder for editing.</p>
                        <div className="workflow-node-list">
                          {nodes.length ? nodes.map((node, index) => {
                            const nodeKey = String(node.key || node.node_key || "").trim();
                            const isEditing = editingNodeIndex === index;
                            const nodeTools = Array.isArray(node.tools) ? node.tools : [];
                            const nodeSkills = Array.isArray(node.skills) ? node.skills : [];
                            return (
                              <div
                                key={nodeKey || `node-${index}`}
                                className={`workflow-node-row${isEditing ? " workflow-node-row-active" : ""}`}
                                role="button"
                                tabIndex={0}
                                onClick={(event) => {
                                  if (event.target instanceof Element && event.target.closest("button")) return;
                                  loadNodeDraft(node, index);
                                }}
                                onKeyDown={(event) => {
                                  if (event.key === "Enter" || event.key === " ") {
                                    event.preventDefault();
                                    loadNodeDraft(node, index);
                                  }
                                }}
                              >
                                <div className="workflow-row-head">
                                  <strong>{node.label || nodeKey}</strong>
                                  <span className="workflow-row-index">#{index + 1}</span>
                                </div>
                                <span>{node.agent || "No agent"}</span>
                                {isEditing ? (
                                  <>
                                    <small>{nodeTools.join(", ") || "No tools"}</small>
                                    <small>{nodeSkills.join(", ") || "No skills"}</small>
                                    <div className="workflow-row-actions">
                                      <button
                                        type="button"
                                        className="workflow-row-btn"
                                        onClick={() => withOut("workflowNodeReorder", () => moveWorkflowNode(selectedTemplate, index, -1), { notifySuccess: false })}
                                        disabled={busy || index === 0}
                                      >
                                        Up
                                      </button>
                                      <button
                                        type="button"
                                        className="workflow-row-btn"
                                        onClick={() => withOut("workflowNodeReorder", () => moveWorkflowNode(selectedTemplate, index, 1), { notifySuccess: false })}
                                        disabled={busy || index === nodes.length - 1}
                                      >
                                        Down
                                      </button>
                                      <button type="button" className="workflow-row-btn workflow-row-btn-primary" onClick={() => loadNodeDraft(node, index)} disabled={busy}>
                                        Edit
                                      </button>
                                      <button
                                        type="button"
                                        className="workflow-row-btn workflow-row-btn-danger"
                                        onClick={() => withOut("workflowNodeDelete", () => removeWorkflowNode(selectedTemplate, index))}
                                        disabled={busy}
                                      >
                                        Delete
                                      </button>
                                    </div>
                                  </>
                                ) : (
                                  <small className="workflow-row-collapsed-hint">Click to edit</small>
                                )}
                              </div>
                            );
                          }) : <p className="subtle">No nodes available.</p>}
                        </div>
                      </div>

                      <div className="workflow-crud-panel workflow-edge-list">
                        <h4>Conditions and Feedback Loops</h4>
                        <p className="subtle">Click any edge row to edit transition settings quickly.</p>
                        {edges.length ? edges.map((edge, index) => (
                          <div
                            key={`${edge.from}-${edge.to}-${index}`}
                            className={`workflow-edge-row${editingEdgeIndex === index ? " workflow-edge-row-active" : ""}`}
                            role="button"
                            tabIndex={0}
                            onClick={(event) => {
                              if (event.target instanceof Element && event.target.closest("button")) return;
                              loadEdgeDraft(edge, index);
                            }}
                            onKeyDown={(event) => {
                              if (event.key === "Enter" || event.key === " ") {
                                event.preventDefault();
                                loadEdgeDraft(edge, index);
                              }
                            }}
                          >
                            <div>
                              <div className="workflow-row-head">
                                <strong>{edge.from} → {edge.to}</strong>
                                <span className="workflow-row-index">#{index + 1}</span>
                              </div>
                              {editingEdgeIndex === index ? <small>{conditionText(edge)}</small> : <small className="workflow-row-collapsed-hint">Click to edit</small>}
                            </div>
                            {editingEdgeIndex === index ? (
                              <div className="workflow-row-actions">
                                {edge.feedback_loop || nodes.findIndex((node) => String(node.key || node.node_key) === String(edge.to)) < nodes.findIndex((node) => String(node.key || node.node_key) === String(edge.from)) ? <span className="chip">feedback</span> : null}
                                <button
                                  type="button"
                                  className="workflow-row-btn"
                                  onClick={() => withOut("workflowEdgeReorder", () => moveWorkflowEdge(selectedTemplate, index, -1), { notifySuccess: false })}
                                  disabled={busy || index === 0}
                                >
                                  Up
                                </button>
                                <button
                                  type="button"
                                  className="workflow-row-btn"
                                  onClick={() => withOut("workflowEdgeReorder", () => moveWorkflowEdge(selectedTemplate, index, 1), { notifySuccess: false })}
                                  disabled={busy || index === edges.length - 1}
                                >
                                  Down
                                </button>
                                <button type="button" className="workflow-row-btn workflow-row-btn-primary" onClick={() => loadEdgeDraft(edge, index)} disabled={busy}>
                                  Edit
                                </button>
                                <button
                                  type="button"
                                  className="workflow-row-btn workflow-row-btn-danger"
                                  onClick={() => withOut("workflowEdgeDelete", () => removeWorkflowEdge(selectedTemplate, index))}
                                  disabled={busy}
                                >
                                  Delete
                                </button>
                              </div>
                            ) : null}
                          </div>
                        )) : <p className="subtle">No edges available.</p>}
                      </div>
                    </div>
                  </section>
                </div>
              </article>
            </section>
          )
        ) : null}

        {showDiscord ? (
          <section className="card discord-panel">
            <div className="section-head">
              <div>
                <p className="section-kicker">External Channel</p>
                <h3>Discord Channel</h3>
                <span className="subtle">Send a message as jaidev. The concierge workflow routes it automatically and returns the reply in the same thread.</span>
              </div>
              <span className={conciergeAgent?.is_active ? "chip" : "chip chip-neutral"}>{conciergeAgent?.is_active ? "Concierge active" : "Seed defaults to activate"}</span>
            </div>
            <div className="discord-grid">
              <form className="stack" onSubmit={(event) => { event.preventDefault(); withOut("discordWebhook", sendDiscordWebhookMessage); }}>
                <div className="discord-status-row">
                  <span>User: jaidev</span>
                  <span>Routing: automatic</span>
                  <span>Entry agent: ConciergeAgent</span>
                </div>
                <label>Message
                  <textarea rows={3} value={discordWebhookForm.body} onChange={(event) => setDiscordWebhookForm((prev) => ({ ...prev, body: event.target.value }))} placeholder="Ask for research, support, or workflow analysis as jaidev." />
                </label>
                <div className="workflow-action-row">
                  <button type="submit" className="accent" disabled={busy}>{discordBotStatus?.running ? "Send Message" : "Run Message"}</button>
                  <button type="button" className="secondary" onClick={() => withOut("discordConversations", loadDiscordConversations, { notifySuccess: false })} disabled={busy}>Refresh Thread</button>
                  <button type="button" className="secondary" onClick={() => withOut("discordStatus", loadDiscordStatus, { notifySuccess: false })} disabled={busy}>Refresh Delivery</button>
                </div>
                <div className={discordExternallySent ? "discord-mode-banner discord-mode-live" : "discord-mode-banner"}>
                  <strong>{discordDeliveryLabel}</strong>
                  <span>{discordExternallySent ? "The reply was delivered outside the app as well." : "The full inbound and outbound thread is stored locally inside the app."}</span>
                </div>
                <div className="discord-status-row">
                  <span>Provider: {String((parseJsonSafely(out.discordWebhook) || {}).provider || "agent_tool")}</span>
                  <span>Bot: {discordBotStatus?.running ? "running" : "not running"}</span>
                  <span>Threads: {discordConversations.length}</span>
                </div>
              </form>
              <div className="discord-message-panel">
                <h4>{latestDiscordConversation ? `jaidev thread #${latestDiscordConversation.id}` : "No jaidev thread yet"}</h4>
                <div className="discord-message-list">
                  {latestDiscordMessages.length ? latestDiscordMessages.map((message) => (
                    <div key={message.id} className={`discord-message ${message.direction === "outbound" ? "discord-outbound" : "discord-inbound"}`}>
                      <strong>{message.direction === "outbound" ? "Agent" : latestDiscordConversation.external_user_id}</strong>
                      <p>{message.body}</p>
                      <small>{message.created_at}</small>
                    </div>
                  )) : <p className="subtle">Send a message to see the jaidev thread appear here.</p>}
                </div>
              </div>
            </div>
          </section>
        ) : null}

        {showLauncher ? (
        <div className="workflow-main-grid">
          <article className="card run-history-card">
            <div className="section-head">
              <div>
                <h3>Workflow Run History</h3>
                <span className="subtle">Focus a run to inspect metrics, events, and inter-agent messages.</span>
              </div>
              <button className="secondary" type="button" onClick={() => withOut("runHistory", loadRunHistory, { notifySuccess: false })} disabled={busy}>Refresh Runs</button>
            </div>
            <div className="analysis-table-wrap">
              <table className="analysis-table run-history-table">
                <thead>
                  <tr>
                    <th>Run</th>
                    <th>Workflow</th>
                    <th>Status</th>
                    <th>Timestamp</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {historyRows.length ? historyRows.map((run) => (
                    <tr key={`workflow-run-${run.runId}-${run.when || "na"}`}>
                      <td><strong>#{run.runId ?? "-"}</strong></td>
                      <td>{run.runLabel}</td>
                      <td><span className={`status-pill ${runStatusClass(run.status)}`}>{String(run.status || "unknown").toUpperCase()}</span></td>
                      <td>{run.when ? (() => { try { const date = new Date(run.when); return date.toLocaleString("en-IN", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", hour12: true }); } catch { return run.when; } })() : "timestamp unavailable"}</td>
                      <td>
                        <div className="table-action-cluster">
                          <IconActionButton
                            icon="◎"
                            label="Focus run"
                            tone="info"
                            onClick={() => withOut("focusRun", () => focusRun(run.runId), { notifySuccess: false })}
                            disabled={busy || !run.runId}
                          />
                          {run.status === "running" || run.status === "queued" ? (
                            <IconActionButton
                              icon="■"
                              label="Stop run"
                              tone="warning"
                              onClick={() => withOut("stopRun", () => stopRun(run.runId))}
                              disabled={busy || !run.runId}
                            />
                          ) : null}
                          <IconActionButton
                            icon="✕"
                            label="Delete run"
                            tone="danger"
                            onClick={() => withOut("deleteRun", () => deleteRun(run.runId))}
                            disabled={busy || !run.runId}
                          />
                        </div>
                      </td>
                    </tr>
                  )) : (
                    <tr><td colSpan={5} className="subtle">No workflow runs yet.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </article>

          <section className="card agent-achievements-panel ops-log-card">
            <div className="section-head">
              <div>
                <h3>Agent Achievements</h3>
                <span className="subtle">What each agent achieved, with complete run log and result for the focused workflow run.</span>
              </div>
              <div className="ops-log-head-right">
                <span className={isLiveLogsPaused ? "chip chip-neutral" : "chip"}>{liveStatusText}</span>
                <button className="secondary" type="button" onClick={() => setIsLiveLogsPaused((value) => !value)}>{isLiveLogsPaused ? "Resume" : "Pause"}</button>
              </div>
            </div>
            <div className="ops-log-meta">
              <span>{agentAchievements.length} agent result{agentAchievements.length !== 1 ? "s" : ""}</span>
              <span>{completeRunLog.length || liveAgentLines.length} log item{(completeRunLog.length || liveAgentLines.length) !== 1 ? "s" : ""}</span>
              <span>{focusedRunId ? `Tracking run #${focusedRunId}` : "Tracking latest run"}</span>
            </div>
            <div className="agent-achievement-list">
              {agentAchievements.length ? agentAchievements.map((item) => {
                const pickedTools = Array.isArray(item?.picked_tools) ? item.picked_tools : (item?.tools && typeof item.tools === "object" ? Object.keys(item.tools) : []);
                const pickedSkills = Array.isArray(item?.picked_skills) ? item.picked_skills : [];
                return (
                  <article className="agent-achievement-card" key={`achievement-${item.step_id || item.node_key}`}>
                    <div className="agent-achievement-head">
                      <div>
                        <strong>{item.agent || "Agent"}</strong>
                        <span>{item.node_label || item.node_key || "Workflow step"}</span>
                      </div>
                      <span className={`status-pill ${runStatusClass(item.status)}`}>{String(item.status || "unknown").toUpperCase()}</span>
                    </div>
                    <p>{item.summary || item.objective || "No achievement summary was recorded for this step."}</p>
                    {item.details ? <p className="agent-achievement-details">{item.details}</p> : null}
                    <div className="agent-capability-grid">
                      <div>
                        <span>Tools available</span>
                        <strong>{listText(item.available_tools)}</strong>
                      </div>
                      <div>
                        <span>Tools picked</span>
                        <strong>{listText(pickedTools)}</strong>
                      </div>
                      <div>
                        <span>Skills available</span>
                        <strong>{listText(item.available_skills)}</strong>
                      </div>
                      <div>
                        <span>Skills picked</span>
                        <strong>{listText(pickedSkills)}</strong>
                      </div>
                    </div>
                    <div className="agent-achievement-meta">
                      <span>Completed {formatRunDateTime(item.completed_at)}</span>
                      {item.confidence !== null && item.confidence !== undefined ? <span>Confidence {String(item.confidence)}</span> : null}
                      {pickedTools.length ? <span>Output from {pickedTools.join(", ")}</span> : null}
                    </div>
                    <details className="run-json-details">
                      <summary>Tool output</summary>
                      <pre>{compactJson(item.tools || {})}</pre>
                    </details>
                    <details className="run-json-details">
                      <summary>Full step result</summary>
                      <pre>{compactJson(item.result || item)}</pre>
                    </details>
                  </article>
                );
              }) : (
                <div className="agent-achievement-empty">No agent results are available yet. Run or focus a workflow to inspect each agent outcome.</div>
              )}
            </div>
            <details className="run-json-details run-log-details" open>
              <summary>Complete run log</summary>
              <div className="complete-run-log">
                {completeRunLog.length ? completeRunLog.map((row, index) => (
                  <div className="complete-run-log-row" key={`run-log-${row.time || index}-${index}`}>
                    <span>{timeFromIso(row.time)}</span>
                    <strong>{row.from_agent || row.node_key || row.kind || "Run"}</strong>
                    <p>{row.message || row.title || "Log item recorded."}</p>
                  </div>
                )) : (
                  <pre className="agent-log-pre">{liveAgentLines.length ? liveAgentLines.join("\n") : "No complete log yet. Run a workflow to persist node events and agent messages."}</pre>
                )}
              </div>
            </details>
            <details className="run-json-details">
              <summary>Run result payload</summary>
              <pre>{compactJson(workflowResultPayload)}</pre>
            </details>
          </section>
        </div>
        ) : null}
      </section>
    );
  };

  return (
    <main className={isNavOpen ? "console-shell nav-open" : "console-shell"}>
      <button
        type="button"
        className="nav-mobile-toggle"
        aria-expanded={isNavOpen}
        aria-controls="primary-navigation"
        onClick={() => setIsNavOpen((open) => !open)}
      >
        <span className="nav-mobile-toggle-icon" aria-hidden="true">☰</span>
        <span>{isNavOpen ? "Close" : "Menu"}</span>
      </button>
      <button
        type="button"
        className="nav-backdrop"
        aria-label="Close navigation"
        onClick={() => setIsNavOpen(false)}
      />
      <aside className={isNavOpen ? "nav-rail nav-rail-open" : "nav-rail"}>
        <div className="nav-rail-head">
          <div className="brand-block">
            <h1 className="brand">Agent Orchestrator</h1>
            <p className="rail-subtitle">Visual agents, workflows, and Discord runtime</p>
          </div>
          <button type="button" className="nav-close" aria-label="Close navigation" onClick={() => setIsNavOpen(false)}>
            ×
          </button>
        </div>
        <nav id="primary-navigation" className="rail-nav">
          {(() => {
            const rendered = [];
            let lastGroup = null;
            navItems.forEach((item) => {
              if (item.group !== lastGroup) {
                if (lastGroup !== null) {
                  rendered.push(<div key={`div-${item.group}`} className="nav-group-divider" />);
                }
                rendered.push(
                  <p key={`grp-${item.group}`} className="nav-group-label">{item.group}</p>
                );
                lastGroup = item.group;
              }
              rendered.push(
                <button
                  key={item.key}
                  className={item.key === currentView ? "nav-item active" : "nav-item"}
                  type="button"
                  onClick={() => {
                    setCurrentView(item.key);
                    setIsNavOpen(false);
                  }}
                >
                  <span className="nav-icon">{item.icon}</span>
                  <span className="nav-label">{item.label}</span>
                </button>
              );
            });
            return rendered;
          })()}
        </nav>
        <div className="nav-footer">
          <span className="chip">Local Runtime</span>
        </div>
      </aside>

      <section className="console-main">
        <div className="toast-stack" role="status" aria-live="polite">
          {toasts.map((toast) => (
            <div key={toast.id} className={toast.type === "error" ? "toast toast-error" : "toast toast-success"}>
              <div>
                <strong>{toast.title}</strong>
                <p>{toast.detail}</p>
              </div>
              <button className="toast-close" type="button" onClick={() => setToasts((prev) => prev.filter((entry) => entry.id !== toast.id))}>
                x
              </button>
            </div>
          ))}
        </div>

        {true ? (
          <GlobalHeader
            currentView={currentView}
            busy={busy}
            onRefresh={() =>
              withOut("dashboardRefresh", async () => {
                const [agentRows, toolRows, skillRows] = await Promise.all([
                  hydrateAgents(),
                  hydrateTools(),
                  hydrateSkills(),
                ]);
                return {
                  agents: agentRows.length,
                  tools: toolRows.length,
                  skills: skillRows.length,
                };
              })
            }
          />
        ) : null}

        {currentView === "home" ? (
          <HomeView
            readyScore={readyScore}
            agents={agents}
            busy={busy}
            onRefreshSummary={() => withOut("platformSummary", async () => Promise.all([hydrateWorkflowTemplates(), loadRunHistory()]), { notifySuccess: false })}
          />
        ) : null}
        {currentView === "agents" ? renderAgents() : null}
        {currentView === "skills" ? renderSkills() : null}
        {currentView === "tools" ? renderTools() : null}
        {currentView === "workflowLauncher" ? renderWorkflows("launcher") : null}
        {currentView === "workflowCrud" ? renderWorkflows("crud") : null}
        {currentView === "discordMessaging" ? renderWorkflows("discord") : null}

      </section>
    </main>
  );
}
