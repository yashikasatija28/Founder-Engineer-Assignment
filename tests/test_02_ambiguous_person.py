"""Scenario 2 — Ambiguous person.

Request: Give Priya (no surname) editor access to Marketing Hub.
- Search returns two employees: Priya Sharma (E001) and Priya Kapoor (E002).
- Operator must ask_human to disambiguate before submitting.
- Human answers with E002 (Priya Kapoor, Finance).
- Marketing Hub is not confidential, editor is auto-approved.
- Verifier confirms provisioned with E002.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from src.operator.llm import LLMResponse
from src.operator.loop import OperatorLoop
from src.operator.state import RunState

REQUEST = str(Path(__file__).parent.parent / "company" / "requests" / "02-ambiguous-person.md")


class _AmbiguousDriver:
    def __init__(self, portal_url: str, state) -> None:
        self._portal_url = portal_url
        self._state = state
        self._index = 0

    def _tc(self, name, **args):
        return {"id": f"call_{uuid.uuid4().hex[:8]}", "name": name, "arguments": args}

    def chat(self, messages, tools):
        step = self._index
        self._index += 1
        req_id = self._state.portal_request_id or "__PLACEHOLDER__"

        turns = {
            0: [self._tc("search_employees", query="Priya")],
            1: [self._tc("ask_human",
                         question="The name 'Priya' matches two employees: E001 Priya Sharma (Consulting) and E002 Priya Kapoor (Finance). Which employee should receive access to Marketing Hub?",
                         context="Request: editor access to Marketing Hub for 'Priya'.")],
            2: [self._tc("search_systems", query="Marketing Hub")],
            3: [self._tc("submit_access_request",
                         employee_id="E002",
                         system_id="SYS002",
                         role="editor",
                         justification="Campaign calendar update for Q1.")],
            4: [self._tc("get_request_status", request_id=req_id)],
            5: [self._tc("complete_task",
                         request_id=req_id,
                         outcome="success",
                         summary="Provisioned editor access to Marketing Hub for Priya Kapoor (E002).")],
        }

        turn_tcs = turns.get(step)
        if turn_tcs is None:
            return LLMResponse(content="Done.", tool_calls=[], stop_reason="stop")
        return LLMResponse(content=None, tool_calls=turn_tcs, stop_reason="tool_calls")


def test_ambiguous_person_disambiguated(portal_url, run_dir, company_dir, headless_browser):
    state = RunState(run_dir)
    state.goal = {
        "expected_employee_id": "E002",
        "expected_system_id": "SYS002",
        "expected_role": "editor",
        "expected_status": "provisioned",
        "requires_approval": False,
    }
    # Scripted human answer: which Priya
    state._scripted_answers = ["E002 — Priya Kapoor from Finance"]

    driver = _AmbiguousDriver(portal_url, state)
    loop = OperatorLoop(state=state, llm=driver, portal_url=portal_url, company_dir=company_dir, browser=headless_browser)
    result = loop.run(REQUEST)

    assert result is not None
    assert result.passed, result.summary()
    assert state.outcome == "success"

    # Human interaction was recorded
    assert len(state.human_clarifications) == 1
    assert "Priya" in state.human_clarifications[0]["question"]
