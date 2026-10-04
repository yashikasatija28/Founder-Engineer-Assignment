"""Full Playwright browser session — navigate, fill, click, snapshot, screenshot.

The agent uses these tools to drive the portal like a human would.
Playwright is required for navigation tools; if not installed they fall back
to a clear error so the operator can switch to API tools instead.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Browser session — one persistent browser across all tool calls
# ---------------------------------------------------------------------------

class BrowserSession:
    """Manages a single Playwright browser page for the duration of a run."""

    def __init__(self, headless: bool = False) -> None:
        self._headless = headless
        self._pw = None
        self._browser = None
        self._page = None

    def _ensure(self) -> None:
        if self._page is not None:
            return
        try:
            from playwright.sync_api import sync_playwright  # type: ignore
        except ImportError:
            raise RuntimeError(
                "Playwright is not installed. Run: playwright install chromium"
            )
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            headless=self._headless,
            slow_mo=120,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )
        self._page = self._browser.new_page(viewport={"width": 1280, "height": 900})

    # ── Navigation ──────────────────────────────────────────────────────────

    def navigate(self, url: str) -> dict:
        """Go to *url* and return a structured snapshot of the page."""
        self._ensure()
        self._page.goto(url, wait_until="networkidle", timeout=20_000)
        return self._snapshot()

    # ── Snapshot ────────────────────────────────────────────────────────────

    def snapshot(self) -> dict:
        """Return a structured snapshot of the current page."""
        self._ensure()
        return self._snapshot()

    def _snapshot(self) -> dict:
        """Extract structured data from the current page via JS evaluation."""
        try:
            data = self._page.evaluate("""() => {
                const txt = el => (el ? el.innerText.trim() : '');
                const result = {
                    url: window.location.href,
                    title: document.title,
                    headings: [],
                    paragraphs: [],
                    badges: [],
                    forms: [],
                    tables: [],
                    links: []
                };

                document.querySelectorAll('h1,h2,h3').forEach(h => {
                    const t = txt(h);
                    if (t) result.headings.push(t);
                });

                document.querySelectorAll('.badge').forEach(b => {
                    const t = txt(b);
                    if (t) result.badges.push(t);
                });

                document.querySelectorAll('p,.alert,.timeline-title,.timeline-meta,.info-value,.stat-value').forEach(el => {
                    const t = txt(el);
                    if (t && t.length > 1) result.paragraphs.push(t);
                });

                document.querySelectorAll('form').forEach(form => {
                    const fields = [];
                    form.querySelectorAll('input,textarea,select').forEach(inp => {
                        let labelText = '';
                        if (inp.id) {
                            const lbl = document.querySelector('label[for="' + inp.id + '"]');
                            if (lbl) labelText = txt(lbl);
                        }
                        if (!labelText) {
                            const prev = inp.previousElementSibling;
                            if (prev && prev.tagName === 'LABEL') labelText = txt(prev);
                        }
                        if (!labelText) {
                            const parent = inp.closest('.form-group');
                            if (parent) {
                                const lbl = parent.querySelector('label');
                                if (lbl) labelText = txt(lbl);
                            }
                        }
                        fields.push({
                            name: inp.name || inp.id || '',
                            type: inp.type || 'text',
                            label: labelText || inp.placeholder || inp.name || '',
                            value: inp.value || '',
                            placeholder: inp.placeholder || ''
                        });
                    });
                    const buttons = [];
                    form.querySelectorAll('button,input[type=submit]').forEach(btn => {
                        const t = txt(btn) || btn.value;
                        if (t) buttons.push(t);
                    });
                    if (fields.length || buttons.length) {
                        result.forms.push({
                            action: form.action,
                            method: form.method,
                            fields: fields,
                            buttons: buttons
                        });
                    }
                });

                document.querySelectorAll('table').forEach(tbl => {
                    const rows = [];
                    tbl.querySelectorAll('tr').forEach(tr => {
                        const cells = [];
                        tr.querySelectorAll('th,td').forEach(c => { const t = txt(c); if (t) cells.push(t); });
                        if (cells.length) rows.push(cells);
                    });
                    if (rows.length) result.tables.push(rows);
                });

                document.querySelectorAll('a[href]').forEach(a => {
                    const t = txt(a);
                    if (t && !t.match(/^\\s*$/)) result.links.push({text: t, href: a.href});
                });

                return result;
            }""")
            return data
        except Exception as exc:
            return {
                "url": self._page.url,
                "title": self._page.title(),
                "error": f"Snapshot failed: {exc}",
                "text": self._page.inner_text("body")[:2000],
            }

    # ── Interaction ──────────────────────────────────────────────────────────

    def click(self, text_or_selector: str) -> dict:
        """Click an element by its visible text or CSS selector."""
        self._ensure()
        try:
            # Try visible text (button or link)
            self._page.get_by_text(text_or_selector, exact=False).first.click(timeout=5_000)
        except Exception:
            try:
                self._page.click(text_or_selector, timeout=5_000)
            except Exception as exc:
                return {"error": f"Could not click '{text_or_selector}': {exc}"}
        self._page.wait_for_load_state("networkidle", timeout=10_000)
        return self._snapshot()

    def fill(self, label_or_selector: str, value: str) -> dict:
        """Fill a form field identified by its label text or CSS selector."""
        self._ensure()
        try:
            self._page.get_by_label(label_or_selector, exact=False).fill(value)
        except Exception:
            try:
                self._page.fill(label_or_selector, value)
            except Exception as exc:
                return {"error": f"Could not fill '{label_or_selector}': {exc}"}
        return {"filled": True, "field": label_or_selector, "value": value}

    def screenshot(self, name: str, evidence_dir: str) -> dict:
        """Take a full-page screenshot and save to *evidence_dir*/<name>.png."""
        self._ensure()
        out_dir = Path(evidence_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = str(out_dir / f"{name}.png")
        try:
            self._page.screenshot(path=path, full_page=True)
            return {"screenshot": path, "url": self._page.url}
        except Exception as exc:
            return {"error": str(exc)}

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def close(self) -> None:
        if self._browser:
            self._browser.close()
        if self._pw:
            self._pw.stop()
        self._page = None
        self._browser = None
        self._pw = None


# ---------------------------------------------------------------------------
# Standalone evidence capture (no persistent session needed)
# ---------------------------------------------------------------------------

def capture_evidence(url: str, name: str, evidence_dir: str) -> dict:
    """Open *url* in a headless browser, take a screenshot, save to evidence dir."""
    out_dir = Path(evidence_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path = str(out_dir / f"{name}.png")

    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except ImportError:
        return {"notice": "Playwright not installed — screenshot skipped.", "url": url}

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox"],
            )
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.goto(url, timeout=15_000, wait_until="networkidle")
            page.screenshot(path=screenshot_path, full_page=True)
            browser.close()
        return {"screenshot": screenshot_path, "url": url}
    except Exception as exc:
        return {"error": f"Screenshot failed: {exc}", "url": url}
