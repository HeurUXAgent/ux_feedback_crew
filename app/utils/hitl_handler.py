"""
hitl_handler.py

Patches builtins.input at import time.
Stores the agent output from the task callback so it can be sent
to Flutter for display in the review dialog.
"""

import builtins
import threading
import logging
from src.ws_manager import safe_emit

logger = logging.getLogger("hitl_handler")

_original_input = builtins.input

_context: dict = {
    "evaluation_id": None,
    "client_id": None,
}

_sessions: dict[str, dict] = {}


def _patched_input(prompt=""):
    evaluation_id = _context.get("evaluation_id")
    client_id     = _context.get("client_id")

    if not evaluation_id or not client_id:
        logger.warning("[HITL] No active context — console fallback")
        return _original_input(prompt)

    session = _sessions.get(evaluation_id)
    if not session:
        logger.warning(f"[HITL] No session for {evaluation_id} — returning ''")
        return ""

    # Second call after disagree/modify — return "" to exit CrewAI loop
    if session.get("reviewed_once"):
        logger.info(f"[HITL] Second input() call — returning '' to exit loop")
        session["reviewed_once"] = False
        return ""

    session["event"].clear()
    session["feedback"] = None

    # Send the feedback report content FIRST so Flutter can display it
    agent_output = session.get("agent_output", "")
    if agent_output:
        # Send as a separate WS message with HITL_OUTPUT: prefix
        # Flutter parses this to populate the dialog text
        safe_emit(client_id, f"HITL_OUTPUT:{agent_output[:3000]}", 55)

    # Then send HITL_REQUIRED to trigger the dialog
    safe_emit(client_id, "HITL_REQUIRED", 55)
    logger.info(f"[HITL] Sent output + HITL_REQUIRED | evaluation={evaluation_id}")
    logger.info("[HITL] Blocking pipeline thread...")

    received = session["event"].wait(timeout=300)

    if not received:
        logger.warning("[HITL] Timeout — returning '' to exit loop")
        return ""

    rating   = session.get("rating", "agree")
    feedback = session.get("feedback", "")
    logger.info(f"[HITL] Unblocked | rating={rating}")

    if rating == "agree":
        session["reviewed_once"] = False
        return ""   # Enter key equivalent — CrewAI exits loop
    else:
        session["reviewed_once"] = True
        return feedback  # CrewAI reruns task, then input() returns "" next time


# ── Patch at import time ──
builtins.input = _patched_input
logger.info("[HITL] builtins.input patched globally")


# ─── Public API ───────────────────────────────────────────────────────────────

def register_hitl_session(evaluation_id: str):
    _sessions[evaluation_id] = {
        "event": threading.Event(),
        "feedback": None,
        "rating": None,
        "agent_output": "",
        "reviewed_once": False,
    }
    logger.info(f"[HITL] Session registered: {evaluation_id}")


def store_agent_output(evaluation_id: str, output: str):
    """
    Called from crew.py task callback BEFORE human_input=True triggers input().
    Stores the feedback report so _patched_input() can send it to Flutter.
    """
    session = _sessions.get(evaluation_id)
    if session:
        session["agent_output"] = output
        logger.info(f"[HITL] Agent output stored ({len(output)} chars)")


def set_active_context(evaluation_id: str, client_id: str):
    _context["evaluation_id"] = evaluation_id
    _context["client_id"]     = client_id
    logger.info(f"[HITL] Context set: {evaluation_id} | client: {client_id}")


def clear_active_context():
    _context["evaluation_id"] = None
    _context["client_id"]     = None
    logger.info("[HITL] Context cleared")


def submit_human_feedback(evaluation_id: str, rating: str, suggestion: str) -> bool:
    session = _sessions.get(evaluation_id)
    if not session:
        logger.warning(f"[HITL] No waiting session for {evaluation_id}")
        return False

    if rating == "agree":
        feedback_text = ""
    elif rating == "disagree":
        feedback_text = f"The feedback needs improvement. Reviewer comment: {suggestion or 'No comment'}"
    else:
        feedback_text = f"Please modify the feedback. Required changes: {suggestion or 'No comment'}"

    session["rating"]   = rating
    session["feedback"] = feedback_text
    session["event"].set()
    logger.info(f"[HITL] Thread unblocked | evaluation={evaluation_id} rating={rating}")
    return True


def cleanup_hitl_session(evaluation_id: str):
    _sessions.pop(evaluation_id, None)
    logger.info(f"[HITL] Session cleaned: {evaluation_id}")