"""
hitl_manager.py

Simple threading.Event-based HITL session manager.
crew.py calls wait_for_feedback() to block the pipeline thread.
main.py calls submit_feedback() from the /submit-feedback endpoint to unblock it.
"""

import threading
import logging

logger = logging.getLogger("hitl_manager")

_sessions: dict[str, dict] = {}


def create_session(evaluation_id: str):
    """Call before pipeline starts."""
    _sessions[evaluation_id] = {
        "event": threading.Event(),
        "rating": None,
        "suggestion": "",
    }
    logger.info(f"[HITL] Session created: {evaluation_id}")


def wait_for_feedback(evaluation_id: str, timeout: int = 300) -> dict:
    """
    Called from crew.py callback. Blocks until submit_feedback() fires.
    Returns {"rating": ..., "suggestion": ...}
    """
    session = _sessions.get(evaluation_id)
    if not session:
        logger.warning(f"[HITL] No session for {evaluation_id} — auto-approving")
        return {"rating": "agree", "suggestion": ""}

    logger.info(f"[HITL] Waiting for user feedback | evaluation={evaluation_id}")
    received = session["event"].wait(timeout=timeout)

    if not received:
        logger.warning(f"[HITL] Timeout after {timeout}s — auto-approving")
        return {"rating": "agree", "suggestion": ""}

    result = {"rating": session["rating"], "suggestion": session["suggestion"]}
    logger.info(f"[HITL] Received | rating={result['rating']}")
    return result


def submit_feedback(evaluation_id: str, rating: str, suggestion: str) -> bool:
    """
    Called from POST /submit-feedback to unblock wait_for_feedback().
    """
    session = _sessions.get(evaluation_id)
    if not session:
        logger.warning(f"[HITL] No session to unblock for {evaluation_id}")
        return False

    session["rating"] = rating
    session["suggestion"] = suggestion
    session["event"].set()
    logger.info(f"[HITL] Thread unblocked | evaluation={evaluation_id} rating={rating}")
    return True


def cleanup_session(evaluation_id: str):
    _sessions.pop(evaluation_id, None)
    logger.info(f"[HITL] Session cleaned: {evaluation_id}")