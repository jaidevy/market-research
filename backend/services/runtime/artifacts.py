from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def run_artifact_dir(run_id: int | str) -> Path:
    path = Path("logs") / "artifacts" / "agentic_graph" / f"run_{run_id}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_node_artifact(*, run_id: int | str, node_key: str, payload: dict[str, Any]) -> str:
    safe_node_key = "".join(
        ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in str(node_key or "node")
    )
    path = run_artifact_dir(run_id) / f"{safe_node_key}.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2, default=str),
        encoding="utf-8",
    )
    return str(path)


def write_final_artifact(*, run_id: int | str, text: str) -> str:
    path = run_artifact_dir(run_id) / "final_response.md"
    path.write_text(str(text or ""), encoding="utf-8")
    return str(path)
