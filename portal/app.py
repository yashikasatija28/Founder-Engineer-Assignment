"""Internal Access Portal — FastAPI application.

Run with:
    uvicorn portal.app:app --reload --port 8000

Exposes both HTML pages (for human use / Playwright screenshots) and a
/api/* JSON layer (used by the operator tools).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from contextlib import asynccontextmanager
from fastapi import FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from portal.database import get_conn, init_db, new_id, now_iso
from portal.policy import (
    PolicyError,
    evaluate_request,
    find_employee,
    find_system,
    get_employee,
    get_system,
)

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Access Portal", version="1.0.0", lifespan=lifespan)

_TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

_STATIC_DIR = Path(__file__).parent / "static"
_STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


# ===========================================================================
# HTML pages
# ===========================================================================


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM access_requests").fetchone()[0]
        pending = conn.execute("SELECT COUNT(*) FROM access_requests WHERE status='pending_approval'").fetchone()[0]
        provisioned = conn.execute("SELECT COUNT(*) FROM access_requests WHERE status='provisioned'").fetchone()[0]
        rejected = conn.execute("SELECT COUNT(*) FROM access_requests WHERE status='rejected'").fetchone()[0]
        recent = conn.execute("SELECT * FROM access_requests ORDER BY created_at DESC LIMIT 8").fetchall()
    stats = {
        "total": total, "pending": pending,
        "provisioned": provisioned, "rejected": rejected,
        "recent": [dict(r) for r in recent],
    }
    return templates.TemplateResponse(request, "index.html", {"stats": stats})


@app.get("/employees", response_class=HTMLResponse)
def employees_page(request: Request, q: str = ""):
    results = find_employee(q) if q else []
    return templates.TemplateResponse(request, "employees.html", {"q": q, "results": results})


@app.get("/systems", response_class=HTMLResponse)
def systems_page(request: Request, q: str = ""):
    results = find_system(q) if q else []
    return templates.TemplateResponse(request, "systems.html", {"q": q, "results": results})


@app.get("/requests/new", response_class=HTMLResponse)
def new_request_page(
    request: Request,
    employee_id: str = "",
    system_id: str = "",
    role: str = "",
):
    employee = get_employee(employee_id) if employee_id else None
    system = get_system(system_id) if system_id else None
    return templates.TemplateResponse(request, "request_new.html", {
        "employee": employee,
        "system": system,
        "prefill_role": role,
        "error": None,
    })


@app.post("/requests/new", response_class=HTMLResponse)
def submit_request_form(
    request: Request,
    employee_id: str = Form(...),
    system_id: str = Form(...),
    role: str = Form(...),
    justification: str = Form(""),
):
    employee = get_employee(employee_id)
    system = get_system(system_id)
    try:
        status = evaluate_request(employee_id, system_id, role)
    except PolicyError as exc:
        return templates.TemplateResponse(request, "request_new.html", {
            "employee": employee,
            "system": system,
            "prefill_role": role,
            "error": str(exc),
        }, status_code=422)

    req_id = new_id()
    ts = now_iso()
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO access_requests
               (id, employee_id, employee_name, system_id, system_name,
                role, justification, status, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                req_id,
                employee_id,
                employee["name"],
                system_id,
                system["name"],
                role,
                justification,
                status,
                ts,
                ts,
            ),
        )
        conn.execute(
            "INSERT INTO audit_log (request_id,action,actor,detail,created_at) VALUES (?,?,?,?,?)",
            (req_id, "created", "portal", f"status={status}", ts),
        )

    return RedirectResponse(f"/requests/{req_id}", status_code=303)


@app.get("/requests/{req_id}", response_class=HTMLResponse)
def request_detail_page(request: Request, req_id: str):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM access_requests WHERE id=?", (req_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Request not found")
        approvals = conn.execute(
            "SELECT * FROM approval_events WHERE request_id=? ORDER BY created_at",
            (req_id,),
        ).fetchall()
        audit = conn.execute(
            "SELECT * FROM audit_log WHERE request_id=? ORDER BY created_at",
            (req_id,),
        ).fetchall()
    return templates.TemplateResponse(request, "request_detail.html", {
        "req": dict(row),
        "approvals": [dict(a) for a in approvals],
        "audit": [dict(a) for a in audit],
    })


@app.get("/approvals", response_class=HTMLResponse)
def approvals_page(request: Request):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM access_requests WHERE status='pending_approval' ORDER BY created_at DESC"
        ).fetchall()
    return templates.TemplateResponse(request, "approvals.html", {"rows": [dict(r) for r in rows]})


@app.post("/approvals/{req_id}/approve", response_class=HTMLResponse)
def approve_form(
    request: Request,
    req_id: str,
    approved_by: str = Form(...),
    comment: str = Form(""),
):
    _do_approval(req_id, "approved", approved_by, comment)
    return RedirectResponse(f"/requests/{req_id}", status_code=303)


@app.post("/approvals/{req_id}/reject", response_class=HTMLResponse)
def reject_form(
    request: Request,
    req_id: str,
    approved_by: str = Form(...),
    comment: str = Form(""),
):
    _do_approval(req_id, "rejected", approved_by, comment)
    return RedirectResponse(f"/requests/{req_id}", status_code=303)


# ===========================================================================
# JSON API  (/api/*)
# ===========================================================================


class SubmitRequest(BaseModel):
    employee_id: str
    system_id: str
    role: str
    justification: Optional[str] = ""


class ApprovalRequest(BaseModel):
    approved_by: str
    comment: Optional[str] = ""


@app.get("/api/employees/search")
def api_search_employees(q: str = Query(..., min_length=1)):
    return {"results": find_employee(q)}


@app.get("/api/systems/search")
def api_search_systems(q: str = Query(..., min_length=1)):
    return {"results": find_system(q)}


@app.post("/api/requests")
def api_submit_request(body: SubmitRequest):
    employee = get_employee(body.employee_id)
    system = get_system(body.system_id)

    try:
        status = evaluate_request(body.employee_id, body.system_id, body.role)
    except PolicyError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    req_id = new_id()
    ts = now_iso()
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO access_requests
               (id, employee_id, employee_name, system_id, system_name,
                role, justification, status, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                req_id,
                body.employee_id,
                employee["name"],
                body.system_id,
                system["name"],
                body.role,
                body.justification,
                status,
                ts,
                ts,
            ),
        )
        conn.execute(
            "INSERT INTO audit_log (request_id,action,actor,detail,created_at) VALUES (?,?,?,?,?)",
            (req_id, "created", "api", f"status={status}", ts),
        )

    return {
        "id": req_id,
        "status": status,
        "employee_name": employee["name"],
        "system_name": system["name"],
        "role": body.role,
        "message": (
            "Request submitted and provisioned automatically."
            if status == "provisioned"
            else "Request submitted. Awaiting approval before provisioning."
        ),
    }


@app.get("/api/requests/{req_id}")
def api_get_request(req_id: str):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM access_requests WHERE id=?", (req_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Request not found")
        approvals = conn.execute(
            "SELECT * FROM approval_events WHERE request_id=? ORDER BY created_at",
            (req_id,),
        ).fetchall()
        audit = conn.execute(
            "SELECT * FROM audit_log WHERE request_id=? ORDER BY created_at",
            (req_id,),
        ).fetchall()
    return {
        **dict(row),
        "approvals": [dict(a) for a in approvals],
        "audit": [dict(a) for a in audit],
    }


@app.get("/api/approvals")
def api_list_pending_approvals():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM access_requests WHERE status='pending_approval' ORDER BY created_at DESC"
        ).fetchall()
    return {"results": [dict(r) for r in rows]}


@app.post("/api/requests/{req_id}/approve")
def api_approve(req_id: str, body: ApprovalRequest):
    return _do_approval(req_id, "approved", body.approved_by, body.comment or "")


@app.post("/api/requests/{req_id}/reject")
def api_reject(req_id: str, body: ApprovalRequest):
    return _do_approval(req_id, "rejected", body.approved_by, body.comment or "")


@app.get("/api/stats")
def api_stats():
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM access_requests").fetchone()[0]
        pending = conn.execute("SELECT COUNT(*) FROM access_requests WHERE status='pending_approval'").fetchone()[0]
        provisioned = conn.execute("SELECT COUNT(*) FROM access_requests WHERE status='provisioned'").fetchone()[0]
        rejected = conn.execute("SELECT COUNT(*) FROM access_requests WHERE status='rejected'").fetchone()[0]
    return {"total": total, "pending": pending, "provisioned": provisioned, "rejected": rejected}


# ===========================================================================
# Shared helper
# ===========================================================================


def _do_approval(req_id: str, action: str, approved_by: str, comment: str) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM access_requests WHERE id=?", (req_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Request not found")
        if row["status"] not in ("pending_approval",):
            raise HTTPException(
                status_code=409,
                detail=f"Request is already in status '{row['status']}' and cannot be actioned.",
            )

        new_status = "provisioned" if action == "approved" else "rejected"
        ts = now_iso()
        event_id = new_id()

        conn.execute(
            "UPDATE access_requests SET status=?, updated_at=? WHERE id=?",
            (new_status, ts, req_id),
        )
        conn.execute(
            """INSERT INTO approval_events
               (id, request_id, action, approved_by, comment, created_at)
               VALUES (?,?,?,?,?,?)""",
            (event_id, req_id, action, approved_by, comment, ts),
        )
        conn.execute(
            "INSERT INTO audit_log (request_id,action,actor,detail,created_at) VALUES (?,?,?,?,?)",
            (req_id, action, approved_by, comment, ts),
        )

    return {
        "id": req_id,
        "status": new_status,
        "approved_by": approved_by,
        "comment": comment,
    }
