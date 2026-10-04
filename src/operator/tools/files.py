"""Tool: read_company_file — reads a file from the company/ directory."""
from __future__ import annotations

import json
from pathlib import Path


def read_company_file(company_dir: str, filename: str) -> dict | str:
    """Return the file contents as a string (text) or parsed dict (JSON)."""
    base = Path(company_dir)
    # Prevent path traversal
    target = (base / filename).resolve()
    if not str(target).startswith(str(base.resolve())):
        return {"error": "Access denied: path traversal detected."}

    if not target.exists():
        # Try listing what IS available to help the model
        available = [p.relative_to(base).as_posix() for p in base.rglob("*") if p.is_file()]
        return {
            "error": f"File '{filename}' not found.",
            "available_files": available,
        }

    content = target.read_text(encoding="utf-8")

    if filename.endswith(".json"):
        try:
            return {"content": json.loads(content), "type": "json"}
        except json.JSONDecodeError:
            pass

    return {"content": content, "type": "text"}
