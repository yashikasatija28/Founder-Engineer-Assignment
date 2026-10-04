# Access Request Operator

> A narrow AI operator that turns a short, ambiguous company access request into a verified provisioning outcome — demonstrating the full autonomy loop end-to-end.

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Architecture](#architecture)
3. [Design Decisions](#design-decisions)
4. [Demo](#demo)
5. [Known Limitations](#known-limitations)
6. [What I Would Build Next](#what-i-would-build-next)
7. [Assumptions](#assumptions)
8. [Technologies Used](#technologies-used)

---

## Quick Start

### Prerequisites

- Python 3.10+
- An OpenAI-compatible API key (only needed for live LLM runs; tests work without one)

### 1. Install

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1          # Windows
# source .venv/bin/activate          # Mac/Linux
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure

```powershell
copy .env.example .env
# Edit .env — set OPENAI_API_KEY
```

### 3. Start the portal

```powershell
uvicorn portal.app:app --reload --port 8000
```

Open **http://localhost:8000** to browse the portal.

### 4. Run the operator (live LLM)

```powershell
# Scenario 1 — confidential system, approval required
python -m src.operator run company/requests/01-grant-acme-access.md

# Scenario 2 — ambiguous person name
python -m src.operator run company/requests/02-ambiguous-person.md

# Scenario 3 — bad system name that doesn't exist
python -m src.operator run company/requests/03-bad-system-name.md
```

Each run saves artefacts to `runs/<timestamp>/`:

```
runs/20261004T150000_abc123/
├── state.json       ← operator state after every step
├── trace.jsonl      ← full step-by-step trace
├── summary.md       ← outcome, approvals, verification result
└── evidence/
    └── final_status.png
```

### 5. Run scripted tests (no API key needed)

```powershell
pytest -v
```

All 3 scenarios run deterministically using a `ScriptedDriver` — no LLM required.

---

## Architecture

### The core loop

```
Request file
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  UNDERSTAND                                          │
│  Read company context (SOP, employees, systems,      │
│  access matrix). Build a structured system prompt.   │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│  PLAN → EXECUTE → OBSERVE  (tool-calling loop)       │
│                                                      │
│  LLM proposes tool call                              │
│       │                                              │
│       ▼                                              │
│  Tool layer executes (never bypasses portal policy)  │
│       │                                              │
│       ▼                                              │
│  Result fed back into conversation                   │
│       │                                              │
│       ├─── ambiguous? ──► ask_human (blocks loop)   │
│       ├─── pending?   ──► ask_human → record_approval│
│       └─── done?      ──► VERIFY                    │
└─────────────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│  VERIFY (independent, cannot be bypassed)            │
│  Re-fetches portal record, checks status/employee/   │
│  system/role/approval event against the goal.        │
│  Mismatch → loop continues. Match → COMPLETE.        │
└─────────────────────────────────────────────────────┘
                       │
                       ▼
              Evidence bundle + summary.md
```

### Component map

```
company/                    ← Company context (read-only files)
├── sop_access.md           ← Standard Operating Procedure
├── employees.json          ← Employee directory
├── systems.json            ← System catalog
├── access_matrix.json      ← Roles, departments, approval rules
└── requests/               ← 3 demo request files

portal/                     ← Internal access portal (FastAPI + SQLite)
├── app.py                  ← HTML pages + /api/* JSON layer
├── database.py             ← SQLite helpers
└── policy.py               ← evaluate_request() — server-side policy gate

src/operator/               ← The AI operator
├── loop.py                 ← Main agent loop
├── state.py                ← Run state (state.json + trace.jsonl)
├── llm.py                  ← OpenAI client + ScriptedDriver for tests
├── verify.py               ← Independent outcome verifier
└── tools/
    ├── browser.py          ← BrowserSession (navigate, fill, click, screenshot)
    ├── portal_api.py       ← HTTP API calls (search, submit, approve)
    ├── files.py            ← read_company_file
    └── human.py            ← ask_human (stdin / scripted)

tests/
├── conftest.py             ← Portal server fixture
├── test_01_happy_path.py   ← Scenario 1
├── test_02_ambiguous_person.py ← Scenario 2
└── test_03_bad_system_name.py  ← Scenario 3
```

### Two-layer policy enforcement

The portal policy is enforced in two places so the agent cannot bypass it:

| Layer | Where | What it does |
|---|---|---|
| Pre-flight | `portal/policy.py` → `evaluate_request()` | Validates employee, system, role, department; sets initial status |
| Portal API | `/api/requests` POST | Same check server-side; returns 422 if invalid |

A wrong agent action cannot silently succeed — the portal is the authority.

---

## Design Decisions

### 1. Narrow scope over broad simulation
> *"A narrow system that genuinely demonstrates autonomy is considerably more valuable than a broad prototype that only simulates it."*

The prototype solves exactly one workflow (access provisioning) with real side effects (a database record, a real portal, a real approval event). This is more valuable than a general desktop agent that simulates many workflows.

### 2. Model proposes. Portal decides. Verifier confirms.
Three independent actors check correctness:
- The LLM can only *suggest* tool calls — it has no direct DB access.
- The portal enforces policy and rejects invalid submissions.
- The verifier re-fetches the record after `complete_task` — the model cannot declare success by itself.

### 3. Hard stops for ambiguity — never guess
The `ask_human` tool blocks the loop. Two situations always trigger it:
- Multiple employees match the requested name.
- A system name does not resolve to a unique match.

This is a deliberate safety boundary: wrong provisioning is worse than a paused run.

### 4. Playwright for browser navigation — not raw API calls for the primary path
The live operator drives the portal through real browser pages (`browser_navigate`, `browser_fill`, `browser_click`) just like a human would — observable, visual, and testable. The HTTP API is used only for structured polling (`get_request_status`) and approval recording.

### 5. Scripted driver for deterministic testing
Tests use a `ScriptedDriver` that replays a fixed sequence of tool calls. This proves the loop mechanics (ambiguity detection, approval pause, verification) work correctly without an API key, without network calls, and without flakiness.

### 6. State persisted after every step
`state.json` and `trace.jsonl` are written after every tool call. This means:
- A reviewer can see exactly what the agent did and why.
- A run can be resumed after an interruption (foundation for fault tolerance).
- Evidence is available even if the run fails mid-way.

### 7. Approval is a first-class event — not a workaround
Rather than having the agent simulate human approval, the approval is recorded through the same portal UI a real manager would use. The approval event appears in the audit trail. The verifier checks for it. This makes the prototype honest about the human-in-the-loop boundary.

---

## Demo

### The 3 scenarios

| # | Request | What the operator must handle |
|---|---|---|
| 1 | `01-grant-acme-access.md` | Acme Client Workspace is confidential → portal returns `pending_approval` → operator pauses, asks for approval → records it → verifies `provisioned` |
| 2 | `02-ambiguous-person.md` | "Priya" matches 2 employees → operator **must** ask human before submitting |
| 3 | `03-bad-system-name.md` | "Acme folder" matches nothing → operator retries with "Acme" → finds `Acme Client Workspace` → continues |

### Running the scripted demo (no API key)

```powershell
# Start portal in one terminal
uvicorn portal.app:app --port 8000

# Run tests in another
pytest -v -s
```

Expected output per scenario:
```
[TOOL] search_employees(...)       -> found / multiple matches
[TOOL] search_systems(...)         -> found / empty (triggers retry)
[TOOL] submit_access_request(...)  -> pending_approval / provisioned
[HUMAN asked] ...
[SCRIPTED answer] ...
[TOOL] record_approval(...)        -> provisioned
[VERIFY] Running independent verification...
Verification PASSED
  [PASS] Status is 'provisioned'
  [PASS] Employee ID is '...'
  [PASS] System ID is '...'
  [PASS] Role is '...'
  [PASS] Approval event exists in audit trail
[DONE] Run complete. Outcome: success
```

### Portal UI

The portal runs at `http://localhost:8000` and shows:
- **Dashboard** — live stats (total, pending, provisioned, rejected), recent requests
- **Employee Directory** — searchable, with avatar and department
- **System Catalog** — card layout with confidential badge and role pills
- **New Request Form** — step-by-step guide, auto-resolves employee/system
- **Request Detail** — timeline audit trail, side-by-side approve/reject forms
- **Approvals** — pending requests with one-click review

---

## Known Limitations

| Limitation | Detail |
|---|---|
| **One workflow only** | Only handles access provisioning. Does not generalise to other company workflows. |
| **No persistent memory** | The operator starts fresh each run. It does not remember past runs or learn from them. |
| **No general desktop/app control** | The operator drives one specific portal, not arbitrary GUIs. General computer-use (clicking through Windows apps) is not implemented. |
| **Playwright headless blocked in some sandboxes** | Headless Chromium fails inside some restricted terminal environments (e.g. Cursor's sandboxed shell). It works normally in a regular terminal. |
| **Single-turn planning** | The LLM plans and executes in a flat conversation thread. There is no explicit separate planning phase or tree search. |
| **No retry budget per tool** | If a tool fails, the LLM decides whether to retry. There is no automatic exponential-backoff retry layer. |
| **Mock company data** | All employees, systems, and policies are synthetic demo data. No real HR or IT system is connected. |

---

## What I Would Build Next

Given additional time, roughly in priority order:

1. **General computer-use** — Replace the portal-specific browser tools with a general-purpose vision + action loop (e.g. screenshot → bounding-box element detection → click/type) so the operator can work on any web UI or desktop app.

2. **Persistent memory / context store** — A vector store of past runs, company SOPs, and resolved ambiguities so the agent improves over repeated use (e.g. "Priya" was disambiguated to E002 last time in the same context).

3. **Multi-step planning with explicit plan representation** — Before executing, produce a structured plan (JSON list of steps with success criteria per step) that is validated against the access matrix. This separates planning from execution and makes the plan auditable.

4. **Skill/playbook library** — Company-specific playbooks stored as structured documents (e.g. "how to onboard a new contractor", "how to request VPN access") that the operator selects and parameterises from the request, rather than re-planning from scratch each time.

5. **Real approval workflow integration** — Push the approval request to a real channel (Slack, email, Teams) and poll for a response, rather than blocking stdin.

6. **Fault tolerance and resumption** — Use the `state.json` checkpoint to resume interrupted runs automatically, with a maximum-retry policy per step.

7. **Evaluation harness** — A benchmark of 50+ diverse requests across difficulty levels (clear, ambiguous, policy violation, multi-step) to measure success rate, approval rate, and step count per run as the system evolves.

---

## Assumptions

1. **The portal is the authoritative system.** All access grants are mediated through the portal. The operator never writes to a database directly.

2. **Human approval is genuine.** When `ask_human` is called for an approval, a real person responds. The operator does not simulate approvals.

3. **Company context files are trusted.** The SOP, employee directory, system catalog, and access matrix are assumed to be correct and current. The operator does not validate them.

4. **One request at a time.** The operator processes one request file per run. Batch processing is not in scope.

5. **The request is in English.** No multilingual handling is implemented.

6. **OpenAI function calling is available.** The operator requires a model that supports tool/function calling (e.g. `gpt-4o`). It will not work with completion-only models.

7. **"Acme folder" is intentionally vague.** Scenario 3 assumes the requester used an informal name. This is the normal case — people don't look up system IDs before sending requests.

---

## Technologies Used

| Category | Technology | Why |
|---|---|---|
| **LLM** | OpenAI `gpt-4o` (or any OpenAI-compatible model) | Strong function-calling support, reliable JSON tool arguments |
| **Agent framework** | Custom (no LangChain / AutoGen) | Full control over the loop, state, and verification logic |
| **Portal** | FastAPI + Jinja2 + SQLite | Lightweight, real HTTP server with real DB — not a mock |
| **Browser automation** | Playwright (sync API) | Reliable cross-platform browser control with accessibility tree access |
| **HTTP client** | `requests` | Simple synchronous API calls for portal JSON endpoints |
| **Test framework** | pytest + `ScriptedDriver` (custom) | Deterministic end-to-end tests without an API key |
| **Environment** | `python-dotenv` | Keeps credentials out of source code |
| **Language** | Python 3.11 | Wide library support, readable for review |

### External services

- **OpenAI API** (or compatible) — only used during live `python -m src.operator run` invocations. All tests run offline.
- **Google Fonts** (Inter typeface) — loaded by the portal UI from CDN. The portal functions without it if offline.

### No real systems or credentials

All data is synthetic:
- Employees, systems, and policies are fictional demo data in `company/`.
- The portal is a local SQLite database created fresh each run.
- No real HR system, directory service, or IT ticketing system is connected.
- The `.env.example` file contains placeholder values only.
