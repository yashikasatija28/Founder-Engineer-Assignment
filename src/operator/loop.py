"""Operator loop — the core Goal → Understand → Plan → Execute → Observe → Adapt → Verify → Complete cycle."""
from __future__ import annotations

import json
import textwrap
from pathlib import Path
from typing import Any

from .state import RunState
from .tools import ToolRegistry, TOOL_DEFINITIONS
from .verify import verify_outcome, VerifyResult

# How many LLM turns before we give up
MAX_STEPS = 40

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are an Access Request Operator for a company. Your job is to process \
access requests end-to-end by navigating the company's internal web portal \
just like a human would — using browser tools to search, fill forms, and \
submit — then verify the outcome and return evidence.

## Browser-first workflow

Use browser tools for all portal interactions:
1. `browser_navigate(url)` — open portal pages
2. `browser_fill(label, value)` — fill form fields by their label text
3. `browser_click(text)` — click buttons by visible text
4. `browser_snapshot()` — read the current page
5. `browser_screenshot(name)` — save evidence

Use API tools only for structured lookups where the browser is slower:
- `search_employees(query)` / `search_systems(query)` — get clean IDs
- `get_request_status(request_id)` — confirm portal record
- `record_approval(...)` — record a human approval decision

## Rules you MUST follow

1. **Never guess.** If an employee name matches more than one person, call \
ask_human before submitting. If a system name is unclear, search before \
submitting.

2. **Never claim success without checking.** After submitting, call \
get_request_status to confirm. After an approval, check again.

3. **Stop for approval.** If the portal returns status 'pending_approval', \
call ask_human to get an approver name, then call record_approval, then \
verify the status changed to 'provisioned'.

4. **Complete the task.** When the status is 'provisioned', call \
complete_task with the request_id, outcome='success', and a summary.

5. **Capture evidence.** Call browser_screenshot at least once after \
provisioning to save a screenshot of the final portal record.

## Company context

{context}

## Portal URL

{portal_url}

Work step-by-step. After each tool call, read the result carefully before \
deciding what to do next. The portal URL structure is:
- /employees?q=<name>  — search employees
- /systems?q=<name>    — search systems
- /requests/new        — new request form (fields: Employee ID, System ID, Role, Justification)
- /requests/<id>       — request detail and approval form
- /approvals           — list pending approvals
"""


# ---------------------------------------------------------------------------
# Context loader
# ---------------------------------------------------------------------------

def _load_context(company_dir: str) -> str:
    base = Path(company_dir)
    parts: list[str] = []

    # Access matrix (most important for the model)
    matrix_path = base / "access_matrix.json"
    if matrix_path.exists():
        parts.append("### Access Matrix\n```json\n" + matrix_path.read_text() + "\n```")

    # System list (compact)
    systems_path = base / "systems.json"
    if systems_path.exists():
        systems = json.loads(systems_path.read_text())
        lines = []
        for s in systems:
            conf = " [CONFIDENTIAL — always requires approval]" if s.get("confidential") else ""
            lines.append(f"- {s['id']}: {s['name']}{conf} | roles: {s['allowed_roles']}")
        parts.append("### Systems\n" + "\n".join(lines))

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Evidence writer
# ---------------------------------------------------------------------------

def _write_summary(state: RunState, verify_result: VerifyResult | None) -> Path:
    summary_path = state.run_dir / "summary.md"
    lines = [
        f"# Run Summary — {state.run_id}",
        "",
        f"**Request file:** `{state.request_file}`",
        f"**Outcome:** {state.outcome}",
        "",
    ]

    if state.goal:
        lines += ["## Goal", "```json", json.dumps(state.goal, indent=2), "```", ""]

    if state.portal_request_id:
        lines += [
            "## Portal Record",
            f"- Request ID: `{state.portal_request_id}`",
            f"- Status: `{state.portal_request_status}`",
            "",
        ]

    if state.human_clarifications:
        lines += ["## Human Interactions"]
        for h in state.human_clarifications:
            lines += [
                f"- **Q:** {h['question']}",
                f"  **A:** {h['answer']}",
            ]
        lines.append("")

    if verify_result:
        lines += ["## Verification", verify_result.summary(), ""]

    evidence_dir = state.run_dir / "evidence"
    screenshots = list(evidence_dir.glob("*.png"))
    if screenshots:
        lines += ["## Screenshots"]
        for s in screenshots:
            lines.append(f"- `{s.name}`")
        lines.append("")

    summary_path.write_text("\n".join(lines), encoding="utf-8")
    return summary_path


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

class OperatorLoop:
    def __init__(
        self,
        state: RunState,
        llm: Any,
        portal_url: str,
        company_dir: str,
        browser: Any = None,
    ) -> None:
        self.state = state
        self.llm = llm
        self.portal_url = portal_url
        self.company_dir = company_dir
        self._owns_browser = browser is None
        from .tools.browser import BrowserSession
        _browser = browser if browser is not None else BrowserSession(headless=False)
        self.tools = ToolRegistry(
            company_dir=company_dir,
            portal_url=portal_url,
            evidence_dir=str(state.run_dir / "evidence"),
            state=state,
            browser=_browser,
        )

    def run(self, request_path: str) -> VerifyResult | None:
        state = self.state
        state.request_file = request_path

        request_text = Path(request_path).read_text(encoding="utf-8")
        context = _load_context(self.company_dir)

        system_msg = SYSTEM_PROMPT.format(
            context=context,
            portal_url=self.portal_url,
        )

        messages: list[dict] = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": f"Process this access request:\n\n{request_text}"},
        ]
        state.messages = messages
        state.save()

        verify_result: VerifyResult | None = None

        for step in range(MAX_STEPS):
            state.step = step
            state.append_trace("llm_call", {"step": step, "message_count": len(messages)})

            response = self.llm.chat(messages, TOOL_DEFINITIONS)
            state.append_trace("llm_response", {
                "stop_reason": response.stop_reason,
                "content": response.content,
                "tool_calls": [{"name": tc["name"]} for tc in response.tool_calls],
            })

            # Add assistant message
            assistant_msg: dict = {"role": "assistant"}
            if response.content:
                assistant_msg["content"] = response.content
            if response.tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(tc["arguments"]),
                        },
                    }
                    for tc in response.tool_calls
                ]
            messages.append(assistant_msg)

            # No more tool calls — LLM thinks it's done
            if response.stop_reason == "stop":
                print("\n[LOOP] Model stopped without calling complete_task.")
                break

            # Execute each tool call
            task_completed = False
            for tc in response.tool_calls:
                name = tc["name"]
                args = tc["arguments"]
                print(f"\n[TOOL] {name}({json.dumps(args, ensure_ascii=False)[:120]})")

                result = self.tools.execute(name, args)
                state.save()
                state.append_trace("tool_result", {"name": name, "result": result})

                print(f"       -> {json.dumps(result, ensure_ascii=False, default=str)[:200]}")

                # Add tool result to messages
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": json.dumps(result, default=str),
                    }
                )

                if name == "complete_task":
                    task_completed = True

            if task_completed:
                # Run independent verification
                if state.portal_request_id:
                    print("\n[VERIFY] Running independent verification...")
                    verify_result = verify_outcome(
                        self.portal_url,
                        state.portal_request_id,
                        state.goal,
                    )
                    print(verify_result.summary())
                    state.append_trace("verify", {
                        "passed": verify_result.passed,
                        "checks": verify_result.checks,
                    })

                    if not verify_result.passed:
                        # Verification failed — give the model another chance
                        messages.append(
                            {
                                "role": "user",
                                "content": (
                                    "Independent verification FAILED.\n"
                                    + verify_result.summary()
                                    + "\nPlease investigate and fix the issue."
                                ),
                            }
                        )
                        state.outcome = "in_progress"
                        continue  # Continue the loop
                    else:
                        state.outcome = "success"
                else:
                    state.outcome = "success"
                break

        summary_path = _write_summary(state, verify_result)
        state.save()

        print(f"\n[DONE] Run complete. Outcome: {state.outcome}")
        print(f"       Summary: {summary_path}")
        if verify_result:
            print(f"       Verification: {'PASSED' if verify_result.passed else 'FAILED'}")

        return verify_result
