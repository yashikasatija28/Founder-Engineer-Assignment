"""Run state — persisted to disk after every step so a run can be inspected."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class RunState:
    """Holds all mutable state for a single operator run."""

    def __init__(self, run_dir: Path) -> None:
        self.run_dir = run_dir
        self.run_dir.mkdir(parents=True, exist_ok=True)
        (self.run_dir / "evidence").mkdir(exist_ok=True)

        self._state_file = run_dir / "state.json"
        self._trace_file = run_dir / "trace.jsonl"

        # Mutable state
        self.run_id: str = run_dir.name
        self.request_file: str = ""
        self.goal: dict = {}
        self.plan: list[str] = []
        self.portal_request_id: str | None = None
        self.portal_request_status: str | None = None
        self.outcome: str = "in_progress"  # in_progress | success | failed
        self.human_clarifications: list[dict] = []
        self.step: int = 0
        self.messages: list[dict] = []  # full LLM conversation history

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self) -> None:
        payload = {
            "run_id": self.run_id,
            "request_file": self.request_file,
            "goal": self.goal,
            "plan": self.plan,
            "portal_request_id": self.portal_request_id,
            "portal_request_status": self.portal_request_status,
            "outcome": self.outcome,
            "human_clarifications": self.human_clarifications,
            "step": self.step,
        }
        self._state_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def append_trace(self, event_type: str, data: Any) -> None:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "step": self.step,
            "type": event_type,
            "data": data,
        }
        with self._trace_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")


def make_run_dir(runs_root: Path) -> Path:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "_" + uuid.uuid4().hex[:6]
    return runs_root / run_id
