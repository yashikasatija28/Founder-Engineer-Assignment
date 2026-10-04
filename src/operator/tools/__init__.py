"""Tool registry — maps tool names to callables and exposes OpenAI function schemas."""
from __future__ import annotations

from typing import Any, Callable

from .files import read_company_file
from .portal_api import (
    search_employees,
    search_systems,
    submit_access_request,
    get_request_status,
    list_pending_approvals,
    record_approval,
)
from .browser import BrowserSession, capture_evidence
from .human import ask_human

# ---------------------------------------------------------------------------
# OpenAI tool schemas
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "read_company_file",
            "description": (
                "Read a company context file (SOP, employee directory, system catalog, "
                "access matrix). Pass the filename relative to the company/ directory."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "Filename within company/."}
                },
                "required": ["filename"],
            },
        },
    },
    # ── Browser navigation tools ──────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "browser_navigate",
            "description": (
                "Navigate the browser to a URL and return a structured snapshot of the page "
                "(headings, forms, tables, badges, links). Use this to open the portal home, "
                "search pages, and request detail pages."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Full URL to navigate to."}
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_snapshot",
            "description": "Get a structured snapshot of the current browser page without navigating.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_fill",
            "description": (
                "Fill a form field on the current browser page. Identify the field by its "
                "visible label text (e.g. 'Employee ID', 'Role', 'Your Name')."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "label": {"type": "string", "description": "Visible label of the form field."},
                    "value": {"type": "string", "description": "Value to type into the field."},
                },
                "required": ["label", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_click",
            "description": (
                "Click a button or link on the current browser page by its visible text "
                "(e.g. 'Submit Request', 'Search', 'Approve & Provision')."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Visible text of the element to click."}
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_screenshot",
            "description": "Take a full-page screenshot of the current browser page and save it as evidence.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Filename stem, e.g. 'final_status'."}
                },
                "required": ["name"],
            },
        },
    },
    # ── API tools (structured data, status checks) ────────────────────────
    {
        "type": "function",
        "function": {
            "name": "search_employees",
            "description": "Search the portal employee directory via API. Returns structured list with IDs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Name, ID, or email fragment."}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_systems",
            "description": "Search the portal system catalog via API. Returns structured list with IDs and roles.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Name, ID, or description fragment."}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_access_request",
            "description": (
                "Submit a new access request via the portal API. The portal enforces policy. "
                "Only call when employee_id and system_id are confirmed unambiguous."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "employee_id": {"type": "string"},
                    "system_id": {"type": "string"},
                    "role": {"type": "string"},
                    "justification": {"type": "string"},
                },
                "required": ["employee_id", "system_id", "role", "justification"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_request_status",
            "description": "Retrieve the current status and full record of an access request by its ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "request_id": {"type": "string"}
                },
                "required": ["request_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_pending_approvals",
            "description": "List all access requests currently awaiting human approval.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "record_approval",
            "description": (
                "Record a human approval for a pending request. Call this only after "
                "ask_human has confirmed the approver's name and consent."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "request_id": {"type": "string"},
                    "approved_by": {"type": "string"},
                    "comment": {"type": "string"},
                },
                "required": ["request_id", "approved_by", "comment"],
            },
        },
    },
    # ── Human and task tools ──────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "ask_human",
            "description": (
                "Pause and ask a human for clarification or approval. Use when a person "
                "name is ambiguous, a system name doesn't resolve, or an approval is needed."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "context": {"type": "string"},
                },
                "required": ["question", "context"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "complete_task",
            "description": (
                "Signal task completion. Call only after confirming the portal status is "
                "'provisioned'. Include the portal request ID and a summary."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "request_id": {"type": "string"},
                    "outcome": {"type": "string", "enum": ["success", "failed"]},
                    "summary": {"type": "string"},
                },
                "required": ["request_id", "outcome", "summary"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

class ToolRegistry:
    def __init__(
        self,
        company_dir: str,
        portal_url: str,
        evidence_dir: str,
        state: Any,
        browser: BrowserSession | None = None,
    ) -> None:
        self._company_dir = company_dir
        self._portal_url = portal_url
        self._evidence_dir = evidence_dir
        self._state = state
        self._browser = browser or BrowserSession(headless=False)

    def execute(self, name: str, arguments: dict) -> Any:
        dispatch: dict[str, Callable] = {
            # Company files
            "read_company_file": lambda: read_company_file(
                self._company_dir, arguments["filename"]
            ),
            # Browser navigation
            "browser_navigate": lambda: self._browser.navigate(arguments["url"]),
            "browser_snapshot": lambda: self._browser.snapshot(),
            "browser_fill": lambda: self._browser.fill(arguments["label"], arguments["value"]),
            "browser_click": lambda: self._browser.click(arguments["text"]),
            "browser_screenshot": lambda: self._browser.screenshot(
                arguments["name"], self._evidence_dir
            ),
            # Portal API
            "search_employees": lambda: search_employees(
                self._portal_url, arguments["query"]
            ),
            "search_systems": lambda: search_systems(
                self._portal_url, arguments["query"]
            ),
            "submit_access_request": lambda: submit_access_request(
                self._portal_url,
                arguments["employee_id"],
                arguments["system_id"],
                arguments["role"],
                arguments.get("justification", ""),
            ),
            "get_request_status": lambda: get_request_status(
                self._portal_url, arguments["request_id"]
            ),
            "list_pending_approvals": lambda: list_pending_approvals(self._portal_url),
            "record_approval": lambda: record_approval(
                self._portal_url,
                arguments["request_id"],
                arguments["approved_by"],
                arguments.get("comment", ""),
            ),
            # Human / task
            "ask_human": lambda: ask_human(
                arguments["question"],
                arguments.get("context", ""),
                self._state,
            ),
            "capture_evidence": lambda: capture_evidence(
                arguments["url"],
                arguments["name"],
                self._evidence_dir,
            ),
            "complete_task": lambda: self._complete_task(arguments),
        }

        fn = dispatch.get(name)
        if fn is None:
            return {"error": f"Unknown tool: {name}"}
        try:
            result = fn()
            if name == "submit_access_request" and isinstance(result, dict) and "id" in result:
                self._state.portal_request_id = result["id"]
                self._state.portal_request_status = result.get("status")
            if name == "get_request_status" and isinstance(result, dict):
                self._state.portal_request_status = result.get("status")
            return result
        except Exception as exc:
            return {"error": str(exc), "tool": name}

    def _complete_task(self, arguments: dict) -> dict:
        self._state.portal_request_id = arguments.get("request_id", self._state.portal_request_id)
        self._state.outcome = arguments.get("outcome", "success")
        return {
            "acknowledged": True,
            "outcome": arguments.get("outcome"),
            "summary": arguments.get("summary"),
        }
