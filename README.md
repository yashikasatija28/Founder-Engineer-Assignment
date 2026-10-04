# Access Request Operator

A narrow AI operator prototype that turns a short company access request into a verified provisioning outcome.

It demonstrates the core autonomy loop:

```
Goal → Understand → Plan → Execute → Observe → Adapt → Verify → Complete
```

## What it does

Given a request like *"Give Raj read access to the Acme folder"*, the operator:

1. Reads company context (SOP, employee directory, system catalog, access matrix).
2. Searches the portal for the right employee and system.
3. Recovers gracefully when a system name does not match exactly ("Acme folder" → searches "Acme" → finds "Acme Client Workspace").
4. Stops and asks a human when a name is ambiguous (two employees named "Priya").
5. Submits the access request through the portal, which enforces the same policy rules.
6. Detects `pending_approval` status, asks a human for approval, then records it.
7. Independently verifies the portal record matches the intended outcome.
8. Writes a summary and screenshot evidence.

## Scenarios

| # | Request file | What it tests |
|---|---|---|
| 1 | `company/requests/01-grant-acme-access.md` | Happy path + required approval (Acme is confidential) |
| 2 | `company/requests/02-ambiguous-person.md` | Ambiguous person — operator must ask human |
| 3 | `company/requests/03-bad-system-name.md` | Bad system name — operator searches and recovers |

---

## Quick start

### 1. Install dependencies

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. (Optional) Install Playwright for browser screenshots

```powershell
playwright install chromium
```

If Playwright is not installed the operator still works; screenshot capture is skipped gracefully.

### 3. Start the portal

```powershell
uvicorn portal.app:app --reload --port 8000
```

Open [http://localhost:8000](http://localhost:8000) to browse the portal manually.

### 4. Configure environment

```powershell
copy .env.example .env
# Edit .env and set OPENAI_API_KEY
```

### 5. Run an access request (live LLM)

```powershell
python -m src.operator run company/requests/01-grant-acme-access.md
python -m src.operator run company/requests/02-ambiguous-person.md
python -m src.operator run company/requests/03-bad-system-name.md
```

Run artefacts are saved under `runs/<timestamp>/`:

```
runs/20261004T150000_abc123/
├── state.json          # Current operator state
├── trace.jsonl         # Step-by-step trace of every LLM call and tool result
├── summary.md          # Human-readable outcome summary
└── evidence/
    └── final_status.png
```

---

## Run scripted tests (no API key needed)

```powershell
pytest -v
```

The tests use a `ScriptedDriver` that replays a fixed sequence of tool calls so the full loop — including ambiguity detection, approval gate, and independent verification — runs without an OpenAI key.

---

## Architecture

```
company/                    Company context (read-only)
├── sop_access.md           Standard operating procedure
├── employees.json          Employee directory
├── systems.json            System catalog
├── access_matrix.json      Permitted roles per system and department
└── requests/               Demo request files

portal/                     Internal access portal (FastAPI + SQLite)
├── app.py                  Routes: HTML pages + /api/* JSON layer
├── database.py             SQLite helpers
└── policy.py               Policy enforcement (mirrors access_matrix.json)

src/operator/               The AI operator
├── loop.py                 Main agent loop (understand → plan → execute → verify)
├── state.py                Run state, persisted to disk after every step
├── llm.py                  OpenAI client + ScriptedDriver for tests
├── verify.py               Independent verifier — separate from execution
└── tools/
    ├── files.py            read_company_file
    ├── portal_api.py       search_employees, search_systems, submit, approve, …
    ├── browser.py          capture_evidence (Playwright screenshots)
    └── human.py            ask_human (stdin or scripted for tests)

tests/
├── conftest.py             Shared fixtures (portal server, tmp dirs)
├── test_01_happy_path.py   Scenario 1 — approval required
├── test_02_ambiguous_person.py  Scenario 2 — ambiguous name
└── test_03_bad_system_name.py   Scenario 3 — bad system name
```

### Control loop

```
┌─────────────────────────────────────────────────────────┐
│  LLM proposes tool calls                                │
│  Tool layer executes them (never bypasses policy)       │
│  Results fed back into conversation                     │
│  Loop continues until complete_task is called           │
│                                                         │
│  Independent verifier runs AFTER complete_task:         │
│  ─ re-fetches portal record                             │
│  ─ compares status, employee, system, role              │
│  ─ checks approval event exists if required             │
│  ─ if mismatch → loop continues, not declared done      │
└─────────────────────────────────────────────────────────┘
```

### Policy enforcement (two layers)

1. **Operator tools** — `portal_api.py` submits via the portal's `/api/requests` endpoint.  
2. **Portal** — `portal/policy.py` evaluates `evaluate_request()` server-side and returns the correct status. A wrong agent action cannot silently succeed — the portal is the authority.

### Human-in-the-loop

The `ask_human` tool blocks the loop and prints to stdout. Two situations force it:

- **Ambiguous identity** — multiple employees match the name in the request.
- **Approval required** — the portal returns `pending_approval`; the operator must obtain an approver's name and call `record_approval`.

In test mode `state._scripted_answers` provides pre-loaded answers so tests run without a human.

---

## Design decisions

| Decision | Rationale |
|---|---|
| Narrow scope (one workflow) | Reliable completion of one real workflow beats a broad simulation of many |
| Portal enforces policy | Agent cannot bypass rules by constructing a direct DB call |
| Verifier is independent | Model cannot declare success — a separate check confirms it |
| ScriptedDriver for tests | Tests the loop mechanics deterministically without an API key |
| HTTP API not raw browser | More reliable for the PoC; Playwright is used for evidence screenshots only |
| Run trace + state.json | Supports inspection, resume, and post-mortem analysis |
