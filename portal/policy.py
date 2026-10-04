"""Portal-side policy enforcement.

Mirrors the rules in company/access_matrix.json so the portal is the
authoritative source of truth and a wrong agent action cannot silently
succeed.
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any

_BASE = Path(__file__).parent.parent / "company"


def _load(filename: str) -> Any:
    with open(_BASE / filename, encoding="utf-8") as fh:
        return json.load(fh)


def get_employees() -> list[dict]:
    return _load("employees.json")


def get_systems() -> list[dict]:
    return _load("systems.json")


def get_matrix() -> dict:
    return _load("access_matrix.json")


def find_employee(query: str) -> list[dict]:
    """Case-insensitive substring search across name, id, email."""
    q = query.lower()
    return [
        e for e in get_employees()
        if q in e["name"].lower()
        or q in e["id"].lower()
        or q in e["email"].lower()
    ]


def find_system(query: str) -> list[dict]:
    """Case-insensitive substring search across name, id, description."""
    q = query.lower()
    return [
        s for s in get_systems()
        if q in s["name"].lower()
        or q in s["id"].lower()
        or q in s["description"].lower()
    ]


def get_employee(employee_id: str) -> dict | None:
    for e in get_employees():
        if e["id"] == employee_id:
            return e
    return None


def get_system(system_id: str) -> dict | None:
    for s in get_systems():
        if s["id"] == system_id:
            return s
    return None


class PolicyError(ValueError):
    """Raised when a request violates policy."""


def evaluate_request(
    employee_id: str,
    system_id: str,
    role: str,
) -> str:
    """Return the initial status for a new access request.

    Returns:
        'provisioned'     — auto-approved, no human review needed.
        'pending_approval' — valid request but requires human sign-off.

    Raises:
        PolicyError — invalid employee, system, role, or department.
    """
    employee = get_employee(employee_id)
    if employee is None:
        raise PolicyError(f"Employee '{employee_id}' not found in directory.")

    system = get_system(system_id)
    if system is None:
        raise PolicyError(f"System '{system_id}' not found in catalog.")

    if role not in system["allowed_roles"]:
        raise PolicyError(
            f"Role '{role}' is not a permitted role for {system['name']}. "
            f"Allowed roles: {system['allowed_roles']}"
        )

    matrix = get_matrix()
    rule = matrix.get(system_id)
    if rule is None:
        # No matrix entry → treat as requires approval
        return "pending_approval"

    allowed_depts = rule.get("allowed_departments", [])
    if allowed_depts and employee["department"] not in allowed_depts:
        raise PolicyError(
            f"Employee department '{employee['department']}' is not permitted "
            f"to access {system['name']}. Allowed departments: {allowed_depts}"
        )

    if role in rule.get("auto_approve_roles", []):
        return "provisioned"

    # Confidential flag or explicit approval-required role
    return "pending_approval"
