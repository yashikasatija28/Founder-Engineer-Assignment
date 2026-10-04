# Standard Operating Procedure — System Access Requests

**Document ID:** SOP-IT-001  
**Owner:** IT Security  
**Last updated:** 2026-09-01

---

## 1. Purpose

This procedure governs how employees request, approve, and provision access to company systems. All access grants must be traceable, role-appropriate, and reviewed by an authorised manager before provisioning when the system is classified as confidential.

---

## 2. Scope

All employees, contractors, and third parties requiring access to any system listed in the Company System Catalog.

---

## 3. Definitions

| Term | Meaning |
|------|---------|
| **Requester** | Person making the access request on behalf of a user |
| **User** | Employee who will receive access |
| **System Owner** | Manager responsible for a system |
| **Provisioner** | IT team member who grants access |
| **Confidential system** | Any system flagged `confidential: true` in the System Catalog |

---

## 4. Roles and Permissions

Each system defines a set of permitted roles. The Access Matrix (access_matrix.json) specifies:

- Which roles can be **auto-approved** (provisioned immediately without human review).
- Which roles always **require approval** regardless of other conditions.
- Which departments are **permitted** to access the system.

A request that does not match the matrix will be rejected. A request that matches but involves a confidential system or an approval-required role will be set to `pending_approval` until an authorised person records an approval.

---

## 5. Process Steps

### 5.1 Raise a Request

The requester must provide:
1. **Full name** of the user (employee ID preferred; disambiguate if multiple matches).
2. **System name** (exact name from the System Catalog; search if unsure).
3. **Role** being requested (must be a valid role for that system).
4. **Business justification** (1–3 sentences).

### 5.2 Policy Check

The portal automatically evaluates:
- Does the employee exist?
- Does the system exist?
- Is the role listed in the system's `allowed_roles`?
- Does the employee's department appear in `allowed_departments` for that system?
- Is the role in `auto_approve_roles` or `requires_approval_roles`?
- Is the system confidential?

If any check fails the request is either rejected (invalid data) or placed in `pending_approval` (valid data, requires human sign-off).

### 5.3 Approval

For requests in `pending_approval` an authorised approver must:
1. Review the request and justification.
2. Record an approval or rejection with a comment.

The portal transitions the status to `provisioned` or `rejected` accordingly.

### 5.4 Verification

After provisioning, the Provisioner (or automated operator) must verify:
- Portal record shows `provisioned`.
- Employee, system, and role match the original request.
- An approval event exists in the audit trail for approval-required requests.

---

## 6. Escalation

If the automated operator cannot determine the employee or system unambiguously it **must** stop and ask a human before proceeding. It must not guess.

---

## 7. Audit

Every state change is written to the audit log with actor, timestamp, and detail. Audit records are immutable.
