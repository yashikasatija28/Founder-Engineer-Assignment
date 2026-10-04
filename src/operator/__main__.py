"""CLI entry point.

Usage:
    python -m operator run company/requests/01-grant-acme-access.md
    python -m operator run company/requests/01-grant-acme-access.md --portal http://localhost:8000
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Make sure the project root is on sys.path when run with python -m operator
_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv

load_dotenv()


def main() -> None:
    parser = argparse.ArgumentParser(description="Access Request Operator")
    sub = parser.add_subparsers(dest="command")

    run_p = sub.add_parser("run", help="Process an access request")
    run_p.add_argument("request", help="Path to the request markdown file")
    run_p.add_argument(
        "--portal",
        default=os.environ.get("PORTAL_URL", "http://localhost:8000"),
        help="Portal base URL",
    )
    run_p.add_argument(
        "--company-dir",
        default=os.environ.get("COMPANY_DIR", "company"),
        help="Company context directory",
    )
    run_p.add_argument(
        "--runs-dir",
        default="runs",
        help="Directory to store run artefacts",
    )

    args = parser.parse_args()

    if args.command == "run":
        _run(args)
    else:
        parser.print_help()


def _run(args: argparse.Namespace) -> None:
    from src.operator.state import RunState, make_run_dir
    from src.operator.llm import LLMClient
    from src.operator.loop import OperatorLoop

    runs_root = Path(args.runs_dir)
    run_dir = make_run_dir(runs_root)
    state = RunState(run_dir)

    print(f"[RUN] {run_dir.name}")
    print(f"      Request : {args.request}")
    print(f"      Portal  : {args.portal}")

    llm = LLMClient()
    loop = OperatorLoop(
        state=state,
        llm=llm,
        portal_url=args.portal,
        company_dir=args.company_dir,
    )

    result = loop.run(args.request)
    sys.exit(0 if (result is None or result.passed) else 1)


if __name__ == "__main__":
    main()
