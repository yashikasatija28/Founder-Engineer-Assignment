"""LLM client wrapper.

Supports:
  - Live OpenAI / compatible API via OPENAI_API_KEY + OPENAI_BASE_URL env vars.
  - ScriptedDriver for deterministic tests without an API key.
"""
from __future__ import annotations

import json
import os
import uuid
from typing import Any


# ---------------------------------------------------------------------------
# Response container
# ---------------------------------------------------------------------------

class LLMResponse:
    def __init__(
        self,
        content: str | None,
        tool_calls: list[dict],
        stop_reason: str,
    ) -> None:
        self.content = content
        self.tool_calls = tool_calls  # [{"id": ..., "name": ..., "arguments": {...}}]
        self.stop_reason = stop_reason  # "tool_calls" | "stop"


# ---------------------------------------------------------------------------
# Live client
# ---------------------------------------------------------------------------

class LLMClient:
    """Wraps the OpenAI client for tool-calling conversations."""

    def __init__(self) -> None:
        from openai import OpenAI  # type: ignore

        kwargs: dict[str, Any] = {"api_key": os.environ.get("OPENAI_API_KEY", "no-key")}
        base_url = os.environ.get("OPENAI_BASE_URL")
        if base_url:
            kwargs["base_url"] = base_url
        self._client = OpenAI(**kwargs)
        self._model = os.environ.get("OPENAI_MODEL", "gpt-4o")

    def chat(self, messages: list[dict], tools: list[dict]) -> LLMResponse:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )
        choice = response.choices[0]
        msg = choice.message

        tool_calls = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append(
                    {"id": tc.id, "name": tc.function.name, "arguments": args}
                )

        return LLMResponse(
            content=msg.content,
            tool_calls=tool_calls,
            stop_reason="tool_calls" if tool_calls else "stop",
        )


# ---------------------------------------------------------------------------
# Scripted driver — for tests
# ---------------------------------------------------------------------------

class ScriptedDriver:
    """Replays a fixed sequence of tool-call turns for deterministic testing.

    Each item in *script* is either:
      - A list of tool-call dicts: [{"name": ..., "arguments": {...}}, ...]
      - The string "stop" to simulate the LLM ending the conversation.
    """

    def __init__(self, script: list) -> None:
        self._script = list(script)
        self._index = 0

    def chat(self, messages: list[dict], tools: list[dict]) -> LLMResponse:  # noqa: ARG002
        if self._index >= len(self._script):
            return LLMResponse(content="Script exhausted.", tool_calls=[], stop_reason="stop")

        turn = self._script[self._index]
        self._index += 1

        if turn == "stop" or not turn:
            return LLMResponse(content="Done.", tool_calls=[], stop_reason="stop")

        tool_calls = [
            {
                "id": f"call_{uuid.uuid4().hex[:8]}",
                "name": tc["name"],
                "arguments": tc.get("arguments", {}),
            }
            for tc in turn
        ]
        return LLMResponse(content=None, tool_calls=tool_calls, stop_reason="tool_calls")
