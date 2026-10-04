"""Tool implementations that call the portal JSON API via HTTP."""
from __future__ import annotations

import requests


def _get(portal_url: str, path: str, **params) -> dict:
    resp = requests.get(f"{portal_url}{path}", params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()


def _post(portal_url: str, path: str, body: dict) -> dict:
    resp = requests.post(f"{portal_url}{path}", json=body, timeout=10)
    try:
        data = resp.json()
    except Exception:
        data = {"raw": resp.text}
    if not resp.ok:
        detail = data.get("detail", resp.text) if isinstance(data, dict) else resp.text
        raise RuntimeError(f"Portal returned {resp.status_code}: {detail}")
    return data


def search_employees(portal_url: str, query: str) -> dict:
    return _get(portal_url, "/api/employees/search", q=query)


def search_systems(portal_url: str, query: str) -> dict:
    return _get(portal_url, "/api/systems/search", q=query)


def submit_access_request(
    portal_url: str,
    employee_id: str,
    system_id: str,
    role: str,
    justification: str,
) -> dict:
    return _post(
        portal_url,
        "/api/requests",
        {
            "employee_id": employee_id,
            "system_id": system_id,
            "role": role,
            "justification": justification,
        },
    )


def get_request_status(portal_url: str, request_id: str) -> dict:
    return _get(portal_url, f"/api/requests/{request_id}")


def list_pending_approvals(portal_url: str) -> dict:
    return _get(portal_url, "/api/approvals")


def record_approval(
    portal_url: str,
    request_id: str,
    approved_by: str,
    comment: str,
) -> dict:
    return _post(
        portal_url,
        f"/api/requests/{request_id}/approve",
        {"approved_by": approved_by, "comment": comment},
    )
