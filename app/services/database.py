import os
import json
import re
from pymongo import MongoClient, DESCENDING
from dotenv import load_dotenv
from datetime import datetime, timezone
from typing import Optional

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME", "heuruxagent_db")

client = MongoClient(MONGO_URI)
db = client[DB_NAME]

# ─── Collections ──────────────────────────────────────────────────────────────
evaluations_collection = db["evaluations"]

# ─── Indexes ──────────────────────────────────────────────────────────────────
evaluations_collection.create_index([("user_id", DESCENDING)])
evaluations_collection.create_index([("evaluation_id", DESCENDING)], unique=True)
evaluations_collection.create_index([("timestamps.created_at", DESCENDING)])
evaluations_collection.create_index([("status", DESCENDING)])


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _detect_screen_type(vision_text: str) -> str:
    """
    Basic screen type detection from vision agent output.
    Can be improved with more keywords over time.
    """
    text = vision_text.lower()
    if any(w in text for w in ["login", "sign in", "password", "email"]):
        return "login"
    if any(w in text for w in ["dashboard", "analytics", "chart", "overview"]):
        return "dashboard"
    if any(w in text for w in ["cart", "checkout", "product", "price", "buy"]):
        return "ecommerce"
    if any(w in text for w in ["profile", "account", "settings"]):
        return "profile"
    return "unknown"


def _parse_heuristic_scores(raw_text: str) -> dict:
    """
    Attempts to extract numeric heuristic scores from the heuristic agent output.
    Falls back to None for any score it can't find.
    Designed to be resilient — will never crash the pipeline.
    """
    score_keys = {
        "visibility_of_system_status": ["visibility", "system status"],
        "match_with_real_world": ["match", "real world", "metaphor"],
        "user_control": ["user control", "freedom", "undo"],
        "consistency": ["consistency", "standards"],
        "error_prevention": ["error prevention", "error"],
        "recognition_over_recall": ["recognition", "recall"],
        "flexibility": ["flexibility", "efficiency", "shortcuts"],
        "aesthetic_design": ["aesthetic", "minimalist", "design"],
        "error_recovery": ["error recovery", "recovery", "help users"],
        "accessibility": ["accessibility", "wcag", "contrast"],
    }

    scores = {}
    for key, keywords in score_keys.items():
        # Look for patterns like "Score: 7" or "7/10" near the keyword
        for keyword in keywords:
            pattern = rf"{keyword}.*?(\d+)\s*/?\s*10"
            match = re.search(pattern, raw_text.lower())
            if match:
                scores[key] = int(match.group(1))
                break
        if key not in scores:
            scores[key] = None  # Not found — don't guess

    return scores


def _parse_feedback_report(raw_text: str) -> dict:
    """
    Attempts to extract structured issues and suggestions from feedback agent output.
    Returns raw_text plus any structured lists found.
    """
    issues = []
    suggestions = []

    lines = raw_text.split("\n")
    current_section = None

    for line in lines:
        line = line.strip()
        lower = line.lower()

        if any(w in lower for w in ["issue", "problem", "violation", "finding"]):
            current_section = "issues"
        elif any(w in lower for w in ["suggestion", "recommendation", "improvement", "fix"]):
            current_section = "suggestions"
        elif line.startswith(("-", "•", "*", "–")) or (len(line) > 2 and line[0].isdigit() and line[1] in (".", ")")):
            content = line.lstrip("-•*–0123456789.) ").strip()
            if content:
                if current_section == "issues":
                    issues.append(content)
                elif current_section == "suggestions":
                    suggestions.append(content)

    return {
        "issues_detected": issues,
        "suggestions": suggestions,
        "raw_text": raw_text,
    }


def _compute_ux_score(scores: dict) -> Optional[float]:
    """
    Computes overall UX score as average of available heuristic scores.
    Returns None if no scores were parsed.
    """
    valid = [v for v in scores.values() if v is not None]
    if not valid:
        return None
    return round(sum(valid) / len(valid), 2)


# ─── Core Save Function ───────────────────────────────────────────────────────

def create_evaluation_document(
    evaluation_id: str,
    user_id: str,
    screenshot_url: str,
) -> bool:
    """
    Creates an evaluation document in 'processing' state when pipeline starts.
    Call this immediately after S3 upload.
    """
    doc = {
        "evaluation_id": evaluation_id,
        "user_id": user_id,
        "input": {
            "screenshot_url": screenshot_url,
            "screen_type": "unknown",       # updated after vision analysis
            "uploaded_at": _now(),
        },
        "status": "processing",
        "ai_results": None,                 # populated when pipeline completes
        "hitl_feedback": {
            "review_status": "pending",
            "responses": [],
        },
        "timestamps": {
            "created_at": _now(),
            "completed_at": None,
            "pipeline_duration_seconds": None,
        },
    }

    evaluations_collection.insert_one(doc)
    return True


def complete_evaluation(
    evaluation_id: str,
    tasks_output: list,
    pipeline_duration_seconds: float,
) -> bool:
    """
    Updates the evaluation document with all agent outputs after pipeline completes.
    Parses raw agent outputs into structured fields automatically.
    """
    vision_raw    = str(tasks_output[0].raw) if len(tasks_output) > 0 else ""
    heuristic_raw = str(tasks_output[1].raw) if len(tasks_output) > 1 else ""
    feedback_raw  = str(tasks_output[2].raw) if len(tasks_output) > 2 else ""
    wireframe_html = str(tasks_output[3].raw) if len(tasks_output) > 3 else ""

    # Parse structured data from raw outputs
    screen_type       = _detect_screen_type(vision_raw)
    heuristic_scores  = _parse_heuristic_scores(heuristic_raw)
    feedback_parsed   = _parse_feedback_report(feedback_raw)
    ux_score          = _compute_ux_score(heuristic_scores)

    evaluations_collection.update_one(
        {"evaluation_id": evaluation_id},
        {"$set": {
            "input.screen_type": screen_type,
            "status": "completed",
            "ai_results": {
                "vision_analysis": vision_raw,
                "heuristic_evaluation": {
                    "raw_text": heuristic_raw,
                    "scores": heuristic_scores,
                },
                "feedback_report": feedback_parsed,
                "improved_design": {
                    "html_code": wireframe_html,
                    "preview_image_url": None,   # can be set if you render + upload to S3
                },
                "ux_score": ux_score,
            },
            "timestamps.completed_at": _now(),
            "timestamps.pipeline_duration_seconds": round(pipeline_duration_seconds, 2),
        }}
    )
    return True


def fail_evaluation(evaluation_id: str, error: str) -> bool:
    """Marks evaluation as failed with error context."""
    evaluations_collection.update_one(
        {"evaluation_id": evaluation_id},
        {"$set": {
            "status": "failed",
            "error": error,
            "timestamps.completed_at": _now(),
        }}
    )
    return True


# ─── HITL Feedback ────────────────────────────────────────────────────────────

def save_hitl_response(
    evaluation_id: str,
    agent_name: str,
    ai_suggestion: str,
    user_action: str,           # "agree" | "disagree" | "modify"
    user_modified_suggestion: str,
    reviewed_by: str,
) -> bool:
    """
    Appends a single HITL response to the evaluation document.
    Also updates review_status to 'reviewed'.
    """
    response = {
        "agent": agent_name,
        "ai_suggestion": ai_suggestion,
        "user_action": user_action,
        "user_modified_suggestion": user_modified_suggestion,
        "reviewed_by": reviewed_by,
        "reviewed_at": _now(),
    }

    evaluations_collection.update_one(
        {"evaluation_id": evaluation_id},
        {
            "$push": {"hitl_feedback.responses": response},
            "$set":  {"hitl_feedback.review_status": "reviewed"},
        }
    )
    return True


# ─── Fetch Functions ──────────────────────────────────────────────────────────

def get_evaluation(evaluation_id: str) -> Optional[dict]:
    """Fetch single evaluation by ID. Excludes MongoDB _id."""
    return evaluations_collection.find_one(
        {"evaluation_id": evaluation_id},
        {"_id": 0}
    )


def get_user_evaluations(user_id: str, limit: int = 20) -> list:
    """
    Fetch evaluation history for a user.
    Returns lightweight list (no full html/raw text) for history screen.
    """
    projection = {
        "_id": 0,
        "evaluation_id": 1,
        "status": 1,
        "input": 1,
        "ai_results.ux_score": 1,
        "ai_results.feedback_report.issues_detected": 1,
        "hitl_feedback.review_status": 1,
        "timestamps": 1,
    }
    cursor = evaluations_collection.find(
        {"user_id": user_id},
        projection
    ).sort("timestamps.created_at", DESCENDING).limit(limit)

    return list(cursor)


def get_evaluations_for_analysis(limit: int = 200) -> list:
    """
    Fetch evaluations for your thesis analysis / dataset export.
    Returns all fields needed to measure HITL agreement rates.
    """
    cursor = evaluations_collection.find(
        {"status": "completed"},
        {"_id": 0}
    ).sort("timestamps.created_at", DESCENDING).limit(limit)

    return list(cursor)