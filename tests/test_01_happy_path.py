"""Scenario 1 — Happy path with required approval.

Request: Give Priya Sharma (E001) read access to Acme Client Workspace (SYS001).
- Acme Client Workspace is confidential — requires approval.
- Agent submits → portal returns 'pending_approval'.
- Agent calls ask_human to get approver name.
- Agent calls record_approval.
- Agent calls get_request_status → 'provisioned'.
- Agent calls complete_task.
- Verifier confirms provisioned + approval event exists.
"""
from __future__ import annotations

from pathlib import Path

from src.operator.llm import ScriptedDriver
from src.operator.loop import OperatorLoop
from src.operator.state import RunState


REQUEST = str(Path(__file__).parent.parent / "company" / "requests" / "01-grant-acme-access.md")


def _make_script(portal_url: str) -> list:
    return [
        # Turn 1: search for employee
        [{"name": "search_employees", "arguments": {"query": "Priya Sharma"}}],
        # Turn 2: search for system
        [{"name": "search_systems", "arguments": {"query": "Acme Client Workspace"}}],
        # Turn 3: submit request
        [{
            "name": "submit_access_request",
            "arguments": {
                "employee_id": "E001",
                "system_id": "SYS001",
                "role": "read",
                "justification": "Q4 Acme engagement — joining the team for client document review.",
            },
        }],
        # Turn 4: ask human for approval
        [{
            "name": "ask_human",
            "arguments": {
                "question": "Request REQ_ID is pending approval. Please provide your name to approve it.",
                "context": "Priya Sharma requested read access to Acme Client Workspace. Confidential system — approval required.",
            },
        }],
        # Turn 5: record the approval
        # (request_id will be injected by test — we use a placeholder; the loop
        #  passes the actual state.portal_request_id when executing the tool)
        [{
            "name": "record_approval",
            "arguments": {
                "request_id": "__PLACEHOLDER__",
                "approved_by": "Sarah Miles",
                "comment": "Approved for Q4 engagement.",
            },
        }],
        # Turn 6: verify status
        [{"name": "get_request_status", "arguments": {"request_id": "__PLACEHOLDER__"}}],
        # Turn 7: capture evidence
        [{
            "name": "capture_evidence",
            "arguments": {
                "name": "final_status",
                "url": f"{portal_url}/requests/__PLACEHOLDER__",
            },
        }],
        # Turn 8: complete
        [{
            "name": "complete_task",
            "arguments": {
                "request_id": "__PLACEHOLDER__",
                "outcome": "success",
                "summary": "Provisioned read access to Acme Client Workspace for Priya Sharma after approval by Sarah Miles.",
            },
        }],
        "stop",
    ]


class _InjectingDriver:
    """Wraps ScriptedDriver and replaces __PLACEHOLDER__ with the actual request ID."""

    def __init__(self, portal_url: str, state) -> None:
        self._portal_url = portal_url
        self._state = state
        self._turns = _make_script(portal_url)
        self._index = 0

    def chat(self, messages, tools):
        from src.operator.llm import ScriptedDriver, LLMResponse
        import json, uuid

        if self._index >= len(self._turns):
            return LLMResponse(content="Done.", tool_calls=[], stop_reason="stop")

        turn = self._turns[self._index]
        self._index += 1

        if turn == "stop" or not turn:
            return LLMResponse(content="Done.", tool_calls=[], stop_reason="stop")

        req_id = self._state.portal_request_id or "__PLACEHOLDER__"

        def _fix(v):
            if isinstance(v, str):
                return v.replace("__PLACEHOLDER__", req_id)
            return v

        tool_calls = []
        for tc in turn:
            fixed_args = {k: _fix(v) for k, v in tc.get("arguments", {}).items()}
            tool_calls.append({
                "id": f"call_{uuid.uuid4().hex[:8]}",
                "name": tc["name"],
                "arguments": fixed_args,
            })

        return LLMResponse(content=None, tool_calls=tool_calls, stop_reason="tool_calls")


def test_happy_path_provisioned(portal_url, run_dir, company_dir, headless_browser):
    state = RunState(run_dir)
    # Pre-load goal so verifier can check it
    state.goal = {
        "expected_employee_id": "E001",
        "expected_system_id": "SYS001",
        "expected_role": "read",
        "expected_status": "provisioned",
        "requires_approval": True,
    }
    # Scripted human answer: approver name
    state._scripted_answers = ["Sarah Miles"]

    driver = _InjectingDriver(portal_url, state)
    loop = OperatorLoop(state=state, llm=driver, portal_url=portal_url, company_dir=company_dir, browser=headless_browser)
    result = loop.run(REQUEST)

    assert result is not None, "Verifier should have run"
    assert result.passed, result.summary()
    assert state.outcome == "success"

    # Confirm approval event exists in DB
    record = result.portal_record
    assert any(a["action"] == "approved" for a in record.get("approvals", []))
