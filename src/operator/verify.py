"""Independent verifier — checks the portal record matches the intended goal.

This runs *after* the agent calls complete_task.  It is a separate step from
execution and cannot be bypassed by the model claiming success.
"""
from __future__ import annotations

import requests
from dataclasses import dataclass, field


@dataclass
class VerifyResult:
    passed: bool
    checks: list[dict] = field(default_factory=list)
    portal_record: dict = field(default_factory=dict)

    def summary(self) -> str:
        lines = [f"Verification {'PASSED' if self.passed else 'FAILED'}"]
        for c in self.checks:
            symbol = "[PASS]" if c["passed"] else "[FAIL]"
            lines.append(f"  {symbol} {c['description']}")
        return "\n".join(lines)


def verify_outcome(
    portal_url: str,
    request_id: str,
    goal: dict,
) -> VerifyResult:
    """Fetch the portal record and compare it to *goal*.

    *goal* keys (all optional):
      - expected_employee_id: str
      - expected_system_id: str
      - expected_role: str
      - expected_status: str  (default "provisioned")
      - requires_approval: bool  (if True, checks that an approval event exists)
    """
    checks: list[dict] = []

    # --- Fetch record ---
    try:
        resp = requests.get(f"{portal_url}/api/requests/{request_id}", timeout=10)
        resp.raise_for_status()
        record = resp.json()
    except Exception as exc:
        checks.append({"description": f"Could not fetch portal record: {exc}", "passed": False})
        return VerifyResult(passed=False, checks=checks)

    # --- Status ---
    expected_status = goal.get("expected_status", "provisioned")
    actual_status = record.get("status")
    checks.append(
        {
            "description": f"Status is '{expected_status}' (actual: '{actual_status}')",
            "passed": actual_status == expected_status,
        }
    )

    # --- Employee ---
    if "expected_employee_id" in goal:
        exp = goal["expected_employee_id"]
        act = record.get("employee_id")
        checks.append(
            {
                "description": f"Employee ID is '{exp}' (actual: '{act}')",
                "passed": act == exp,
            }
        )

    # --- System ---
    if "expected_system_id" in goal:
        exp = goal["expected_system_id"]
        act = record.get("system_id")
        checks.append(
            {
                "description": f"System ID is '{exp}' (actual: '{act}')",
                "passed": act == exp,
            }
        )

    # --- Role ---
    if "expected_role" in goal:
        exp = goal["expected_role"]
        act = record.get("role")
        checks.append(
            {
                "description": f"Role is '{exp}' (actual: '{act}')",
                "passed": act == exp,
            }
        )

    # --- Approval event ---
    if goal.get("requires_approval"):
        approvals = record.get("approvals", [])
        approved = any(a.get("action") == "approved" for a in approvals)
        checks.append(
            {
                "description": "Approval event exists in audit trail",
                "passed": approved,
            }
        )

    passed = all(c["passed"] for c in checks)
    return VerifyResult(passed=passed, checks=checks, portal_record=record)
