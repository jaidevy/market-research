const resolveApiBase = () => {
  const configured = (import.meta.env.VITE_API_BASE || "").trim();
  if (configured) {
    return configured.replace(/\/$/, "");
  }

  if (typeof window !== "undefined") {
    const { protocol, hostname, port } = window.location;
    if (port === "8010") {
      return `${window.location.origin}/api`;
    }
    return `${protocol}//${hostname}:8010/api`;
  }

  return "http://127.0.0.1:8010/api";
};

const API_BASE = resolveApiBase();

const parseJson = async (response) => {
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return response.json();
  }
  return { detail: await response.text() };
};

export const request = async (method, path, body) => {
  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method,
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch (error) {
    throw new Error(`Network error while calling ${API_BASE}${path}. Check backend host and port.`);
  }

  const data = await parseJson(response);
  if (!response.ok) {
    throw new Error(data.detail || JSON.stringify(data));
  }
  return data;
};

export const requestStream = async (path, body, onEvent) => {
  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch (error) {
    throw new Error(`Network error while calling ${API_BASE}${path}. Check backend host and port.`);
  }

  if (!response.ok) {
    const data = await parseJson(response);
    throw new Error(data.detail || JSON.stringify(data));
  }

  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error("Streaming response body is unavailable.");
  }

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) {
        continue;
      }
      try {
        const event = JSON.parse(trimmed);
        if (typeof onEvent === "function") {
          onEvent(event);
        }
      } catch {
        // Ignore malformed line and continue reading the stream.
      }
    }
  }

  const tail = buffer.trim();
  if (tail) {
    try {
      const event = JSON.parse(tail);
      if (typeof onEvent === "function") {
        onEvent(event);
      }
    } catch {
      // Ignore malformed trailing payload.
    }
  }
};
