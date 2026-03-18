"""
hitl_handler.py

WHY PREVIOUS APPROACHES FAILED
────────────────────────────────
With human_input=True, CrewAI's internal order is:

    agent runs → input("") called → [task callback]

• builtins.input patch runs at the right time but session["agent_output"]
  is always empty because store_agent_output() (called from the task
  callback) hasn't fired yet.

• Patching Task._handle_human_input failed silently — the method name
  differs across CrewAI versions.

THE FIX: CALL STACK INSPECTION
────────────────────────────────
When CrewAI calls input(""), we are inside its execution stack.
The agent result object is already sitting on a frame above us as a
local variable (called 'result', 'task_output', or similar depending on
version). We walk up the call stack with inspect.currentframe() and
grab it directly — zero dependency on any CrewAI internal method name.

Full flow after fix:
  1. feedback_specialist runs → produces TaskOutput
  2. CrewAI calls input("")   ← _patched_input fires
       ├─ _get_output_from_callstack() walks frames, finds result.raw  ✓
       ├─ store_agent_output()  → session["agent_output"] set          ✓
       ├─ sends HITL_OUTPUT:{json} over WS
       ├─ sends HITL_REQUIRED over WS
       └─ blocks on threading.Event (timeout 300s)
  3. React receives HITL_REQUIRED → opens Panel iframe
  4. Panel GET /hitl-content/{id} → 200 ✓
  5. User submits → POST /submit-feedback → event.set()
  6. _patched_input unblocks → returns "" (agree) or suggestion text
  7. Task callback fires (store_agent_output call there is now a no-op)
"""

import builtins
import inspect
import threading
import logging
import json
import time
from src.ws_manager import safe_emit

logger = logging.getLogger("hitl_handler")

_original_input = builtins.input

_context: dict = {
    "evaluation_id": None,
    "client_id": None,
}

_sessions: dict[str, dict] = {}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _clean_json(raw: str) -> str:
    """Strip markdown fences; return compact JSON or raw string on failure."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = [l for l in cleaned.split("\n") if not l.strip().startswith("```")]
        cleaned = "\n".join(lines).strip()
    try:
        return json.dumps(json.loads(cleaned))
    except json.JSONDecodeError:
        return cleaned


def _get_output_from_callstack() -> str:
    """
    Walk up the Python call stack from inside _patched_input and look for
    a local variable that looks like a CrewAI TaskOutput.

    CrewAI stores the result under different names across versions:
      'result', 'task_output', 'output', 'human_feedback'
    We check all of them and take the first one with a non-empty .raw attr.
    Also handles plain string variables as a last resort.
    """
    frame = inspect.currentframe()
    try:
        checked = 0
        while frame is not None:
            local_vars = frame.f_locals
            checked += 1

            # Priority: objects with a .raw attribute (CrewAI TaskOutput)
            for var_name in ("result", "task_output", "output", "agent_output",
                             "task_result", "final_answer"):
                val = local_vars.get(var_name)
                if val is not None and hasattr(val, "raw") and val.raw:
                    logger.info(
                        f"[HITL] Found output in frame {checked} "
                        f"as '{var_name}' (type={type(val).__name__})"
                    )
                    return str(val.raw)

            # Fallback: plain string variables that look like JSON feedback
            for var_name in ("result", "output", "task_output"):
                val = local_vars.get(var_name)
                if isinstance(val, str) and len(val) > 50:
                    logger.info(
                        f"[HITL] Found string output in frame {checked} as '{var_name}'"
                    )
                    return val

            frame = frame.f_back

        logger.warning(f"[HITL] Call stack walk ({checked} frames) found no output")
        return ""
    finally:
        del frame  # avoid reference cycles


# ─── Patched builtins.input ───────────────────────────────────────────────────

def _patched_input(prompt=""):
    evaluation_id = _context.get("evaluation_id")
    client_id     = _context.get("client_id")

    # Not a HITL context — fall through to real input()
    if not evaluation_id or not client_id:
        logger.warning("[HITL] No active context — console fallback")
        return _original_input(prompt)

    session = _sessions.get(evaluation_id)
    if not session:
        logger.warning(f"[HITL] No session for {evaluation_id} — returning ''")
        return ""

    # Second call after disagree/modify rerun → exit CrewAI's loop
    if session.get("reviewed_once"):
        logger.info("[HITL] Second input() call — returning '' to exit loop")
        session["reviewed_once"] = False
        return ""

    session["event"].clear()
    session["feedback"] = None

    # ── KEY FIX: pull output from call stack right now ──────────────────────
    agent_output = session.get("agent_output", "")  # set by task callback if lucky

    if not agent_output:
        logger.info("[HITL] agent_output not yet in session — scanning call stack...")
        raw = _get_output_from_callstack()
        if raw:
            store_agent_output(evaluation_id, raw)
            agent_output = session.get("agent_output", "")
    # ────────────────────────────────────────────────────────────────────────

    if agent_output:
        logger.info(f"[HITL] Sending HITL_OUTPUT ({len(agent_output)} chars) to React")
        safe_emit(client_id, f"HITL_OUTPUT:{agent_output}", 55)
        time.sleep(0.2)  # ensure frames arrive in order before dialog trigger
    else:
        logger.warning(
            "[HITL] Could not retrieve agent output from call stack. "
            "Panel will open without content."
        )

    safe_emit(client_id, "HITL_REQUIRED", 60)
    logger.info(f"[HITL] Sent HITL_REQUIRED | evaluation={evaluation_id}")
    logger.info("[HITL] Pipeline thread blocking (timeout=300s)...")

    received = session["event"].wait(timeout=300)

    if not received:
        logger.warning("[HITL] Timeout (300s) — auto-approving to unblock pipeline")
        return ""

    rating   = session.get("rating", "agree")
    feedback = session.get("feedback", "")
    logger.info(f"[HITL] Unblocked | rating={rating}")

    if rating == "agree":
        session["reviewed_once"] = False
        return ""
    else:
        session["reviewed_once"] = True
        return feedback


# ─── Install patch ────────────────────────────────────────────────────────────

builtins.input = _patched_input
logger.info("[HITL] builtins.input patched globally")


# ─── Public API ───────────────────────────────────────────────────────────────

def register_hitl_session(evaluation_id: str):
    _sessions[evaluation_id] = {
        "event":         threading.Event(),
        "feedback":      None,
        "rating":        None,
        "agent_output":  "",
        "reviewed_once": False,
    }
    logger.info(f"[HITL] Session registered: {evaluation_id}")


def store_agent_output(evaluation_id: str, raw_output: str):
    """
    Store cleaned agent JSON in the session.

    Called from two places:
      1. _patched_input → _get_output_from_callstack()  ← primary, fires first
      2. crew.py task callback                           ← backup, fires after input()
    The "already set" guard ensures the second call is a no-op.
    """
    session = _sessions.get(evaluation_id)
    if not session:
        logger.warning(f"[HITL] store_agent_output: no session for {evaluation_id}")
        return
    if session.get("agent_output"):
        logger.debug("[HITL] store_agent_output: already set, skipping overwrite")
        return
    cleaned = _clean_json(raw_output)
    session["agent_output"] = cleaned
    logger.info(f"[HITL] Agent output stored ({len(cleaned)} chars)")


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
        logger.warning(f"[HITL] submit_human_feedback: no session for {evaluation_id}")
        return False

    if rating == "agree":
        feedback_text = ""
    elif rating == "disagree":
        feedback_text = (
            f"Rejected. Please revise. "
            f"Reviewer comment: {suggestion or 'No comment provided'}"
        )
    else:
        feedback_text = (
            f"Needs modification. Required changes: {suggestion or 'No comment provided'}"
        )

    session["rating"]   = rating
    session["feedback"] = feedback_text
    session["event"].set()
    logger.info(f"[HITL] Thread unblocked | evaluation={evaluation_id} rating={rating}")
    return True


def cleanup_hitl_session(evaluation_id: str):
    _sessions.pop(evaluation_id, None)
    logger.info(f"[HITL] Session cleaned: {evaluation_id}")