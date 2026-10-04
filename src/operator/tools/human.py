"""Tool: ask_human — pauses the operator and prompts for human input via stdin.

In test mode the state object provides a scripted answer queue so tests can
run without a real human.
"""
from __future__ import annotations

from typing import Any


def ask_human(question: str, context: str, state: Any) -> dict:
    """Ask a human a question, return their answer.

    If *state* has a non-empty `_scripted_answers` list the first item is
    popped and returned without blocking — used by tests.
    """
    scripted: list = getattr(state, "_scripted_answers", [])
    if scripted:
        answer = scripted.pop(0)
        clarification = {
            "question": question,
            "context": context,
            "answer": answer,
            "source": "scripted",
        }
        state.human_clarifications.append(clarification)
        print(f"\n[HUMAN asked] {question}")
        print(f"[SCRIPTED answer] {answer}\n")
        return {"answer": answer, "source": "scripted"}

    # Live mode — block for real input
    print("\n" + "=" * 60)
    print("OPERATOR NEEDS HUMAN INPUT")
    print("=" * 60)
    if context:
        print(f"Context:\n{context}\n")
    print(f"Question: {question}")
    print("-" * 60)
    answer = input("Your answer: ").strip()
    print("=" * 60 + "\n")

    clarification = {
        "question": question,
        "context": context,
        "answer": answer,
        "source": "human",
    }
    state.human_clarifications.append(clarification)
    state.save()
    return {"answer": answer, "source": "human"}
