"""
hitl_handler.py

Bridges CrewAI's human_input=True with FastAPI.
Instead of waiting for console input, it:
1. Sends the agent output to Flutter via WebSocket
2. Waits for the human reviewer to submit feedback via /submit-feedback
3. Returns that feedback to CrewAI to continue the pipeline
"""

import threading
import time
import logging
from src.ws_manager import safe_emit

logger = logging.getLogger(__name__)

# Global store: evaluation_id -> threading.Event + feedback result
_hitl_events: dict[str, dict] = {}


def register_hitl_session(evaluation_id: str):
    """Call this before starting the pipeline for a given evaluation."""
    _hitl_events[evaluation_id] = {
        "event": threading.Event(),
        "feedback": None,
    }


def wait_for_human_feedback(evaluation_id: str, agent_name: str, agent_output: str, client_id: str, timeout: int = 300) -> str:
    """
    Called by CrewAI's human input handler.
    Sends the agent output to Flutter and blocks until reviewer submits feedback.
    
    Args:
        evaluation_id: The current job ID
        agent_name: Which agent is waiting (e.g. "feedback_specialist")
        agent_output: What the agent produced
        client_id: WebSocket client ID for Flutter
        timeout: How long to wait in seconds (default 5 mins)
    
    Returns:
        Human feedback string to inject back into CrewAI
    """
    session = _hitl_events.get(evaluation_id)
    if not session:
        logger.warning(f"No HITL session found for {evaluation_id}, skipping human input")
        return "Approved"

    # Reset event for this round
    session["event"].clear()
    session["feedback"] = None

    # Notify Flutter via WebSocket that human review is needed
    safe_emit(
        client_id,
        f"HITL_REQUIRED:{agent_name}",  # Flutter listens for this prefix
        50 if agent_name == "feedback_specialist" else 75
    )

    logger.info(f"[HITL] Waiting for human feedback on '{agent_name}' for evaluation {evaluation_id}")

    # Block until feedback arrives or timeout
    received = session["event"].wait(timeout=timeout)

    if not received:
        logger.warning(f"[HITL] Timeout waiting for feedback on {evaluation_id}, continuing with approval")
        return "Approved - no reviewer response within timeout"

    feedback = session["feedback"] or "Approved"
    logger.info(f"[HITL] Received feedback for {evaluation_id}: {feedback}")
    return feedback


def submit_human_feedback(evaluation_id: str, rating: str, suggestion: str):
    """
    Called by FastAPI's /submit-feedback endpoint.
    Unblocks the waiting pipeline with the reviewer's input.
    """
    session = _hitl_events.get(evaluation_id)
    if not session:
        logger.warning(f"[HITL] No waiting session for {evaluation_id}")
        return False

    # Format feedback for CrewAI context
    if rating == "agree":
        feedback_text = "Approved. The output looks correct, proceed."
    elif rating == "disagree":
        feedback_text = f"Rejected. Please revise. Reviewer comment: {suggestion or 'No specific comment provided'}"
    else:  # modify
        feedback_text = f"Partially approved with modifications needed: {suggestion or 'No specific comment provided'}"

    session["feedback"] = feedback_text
    session["event"].set()  # Unblock the waiting pipeline
    return True


def cleanup_hitl_session(evaluation_id: str):
    """Call after pipeline completes to free memory."""
    _hitl_events.pop(evaluation_id, None)