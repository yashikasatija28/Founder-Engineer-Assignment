"""Shared test fixtures — starts the portal on a random port using FastAPI TestClient."""
from __future__ import annotations

import threading
import time
import uuid
from pathlib import Path

import pytest
import uvicorn


# ---------------------------------------------------------------------------
# Use an in-process TestClient for portal calls rather than a real server
# so tests work without any network setup.
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def portal_url(tmp_path_factory):
    """Start the portal on a free port, yield its base URL, then stop it."""
    import socket

    def _free_port() -> int:
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]

    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"

    # Override the DB path so tests get a fresh DB
    tmp_db = tmp_path_factory.mktemp("portal") / "test_portal.db"
    import portal.database as db_mod
    db_mod.DB_PATH = tmp_db

    from portal.app import app
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # Wait until the server is up
    for _ in range(30):
        try:
            import requests
            requests.get(base_url, timeout=1)
            break
        except Exception:
            time.sleep(0.2)

    yield base_url

    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture
def run_dir(tmp_path):
    d = tmp_path / "run"
    d.mkdir()
    return d


@pytest.fixture
def company_dir():
    return str(Path(__file__).parent.parent / "company")


@pytest.fixture
def headless_browser():
    """Provide a headless BrowserSession for tests (no visible window).
    Falls back gracefully if Playwright is not installed."""
    try:
        from src.operator.tools.browser import BrowserSession
        b = BrowserSession(headless=True)
        yield b
        b.close()
    except Exception:
        yield None
