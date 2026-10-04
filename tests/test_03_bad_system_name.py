"""Scenario 3 — Bad system name.

Request: Give Raj read access to the 'Acme folder'.
- search_systems('Acme folder') returns nothing.
- Operator searches 'Acme' → finds 'Acme Client Workspace' (SYS001).
- Raj (E003, Engineering) is in the allowed departments.
- Acme Client Workspace is confidential → pending_approval.
- Human approves.
- Verifier confirms provisioned.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from src.operator.llm import LLMResponse
from src.operator.loop import OperatorLoop
from src.operator.state import RunState

REQUEST = str(Path(__file__).parent.parent / "company" / "requests" / "03-bad-system-name.md")


class _BadNameDriver:
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
            0: [self._tc("search_employees", query="Raj")],
            # Search fails with exact name
            1: [self._tc("search_systems", query="Acme folder")],
            # Retry with shorter query
            2: [self._tc("search_systems", query="Acme")],
            # Submit with resolved system
            3: [self._tc("submit_access_request",
                         employee_id="E003",
                         system_id="SYS001",
                         role="read",
                         justification="Raj needs to review Acme client materials.")],
            # Pending approval — ask human
            4: [self._tc("ask_human",
                         question=f"Request {req_id} for Raj Patel (E003) to get read access to Acme Client Workspace is pending approval. Please provide your name to approve.",
                         context="Acme Client Workspace is confidential.")],
            # Record approval
            5: [self._tc("record_approval",
                         request_id=req_id,
                         approved_by="Nina Okafor",
                         comment="Approved — Raj is on the Acme engagement.")],
            # Check status
            6: [self._tc("get_request_status", request_id=req_id)],
            # Complete
            7: [self._tc("complete_task",
                         request_id=req_id,
                         outcome="success",
                         summary="Provisioned read access to Acme Client Workspace for Raj Patel. System name 'Acme folder' resolved to 'Acme Client Workspace' via search.")],
        }

        turn_tcs = turns.get(step)
        if turn_tcs is None:
            return LLMResponse(content="Done.", tool_calls=[], stop_reason="stop")
        return LLMResponse(content=None, tool_calls=turn_tcs, stop_reason="tool_calls")


def test_bad_system_name_resolved(portal_url, run_dir, company_dir, headless_browser):
    state = RunState(run_dir)
    state.goal = {
        "expected_employee_id": "E003",
        "expected_system_id": "SYS001",
        "expected_role": "read",
        "expected_status": "provisioned",
        "requires_approval": True,
    }
    # Scripted human answers: (1) approve, (2) approver name already in ask_human call
    state._scripted_answers = ["Nina Okafor"]

    driver = _BadNameDriver(portal_url, state)
    loop = OperatorLoop(state=state, llm=driver, portal_url=portal_url, company_dir=company_dir, browser=headless_browser)
    result = loop.run(REQUEST)

    assert result is not None
    assert result.passed, result.summary()
    assert state.outcome == "success"

    # Confirm system was resolved correctly despite bad initial name
    record = result.portal_record
    assert record["system_id"] == "SYS001"
    assert record["system_name"] == "Acme Client Workspace"
