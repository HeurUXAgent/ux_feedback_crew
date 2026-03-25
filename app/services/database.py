import os
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

evaluations_collection = db["evaluations"]

# Indexes
evaluations_collection.create_index([("user_id", DESCENDING)])
evaluations_collection.create_index([("evaluation_id", DESCENDING)], unique=True)
evaluations_collection.create_index([("timestamps.created_at", DESCENDING)])
evaluations_collection.create_index([("status", DESCENDING)])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _detect_screen_type(vision_text: str) -> str:
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
        for keyword in keywords:
            pattern = rf"{keyword}.*?(\d+)\s*/?\s*10"
            match = re.search(pattern, raw_text.lower(), re.DOTALL)
            if match:
                scores[key] = int(match.group(1))
                break
        if key not in scores:
            scores[key] = None
    return scores


def _parse_feedback_report(raw_text: str) -> dict:
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
        elif line.startswith(("-", "•", "*", "–")) or (
            len(line) > 2 and line[0].isdigit() and line[1] in (".", ")")
        ):
            content = line.lstrip("-•*–0123456789.) ").strip()
            if content:
                if current_section == "issues":
                    issues.append(content)
                elif current_section == "suggestions":
                    suggestions.append(content)

    return {
        "issues_detected": issues,
        "suggestions": suggestions,
    }


def _compute_ux_score(scores: dict) -> Optional[float]:
    valid = [v for v in scores.values() if v is not None]
    if not valid:
        return None
    return round(sum(valid) / len(valid), 2)


def _build_history_preview(screen_type: str, issues: list, ux_score: Optional[float], preview_image_url: Optional[str] = None) -> dict:
    issues_count = len(issues)
    title = f"{screen_type.title()} Screen Evaluation" if screen_type != "unknown" else "UI Evaluation"
    subtitle = f"{issues_count} issue{'s' if issues_count != 1 else ''} found"

    return {
        "title": title,
        "subtitle": subtitle,
        "issues_count": issues_count,
        "top_issues": issues[:3],
        "ux_score": ux_score,
        "preview_image_url": preview_image_url,
    }


def create_evaluation_document(
    evaluation_id: str,
    user_id: str,
    screenshot_url: str,
) -> bool:
    doc = {
        "evaluation_id": evaluation_id,
        "user_id": user_id,
        "input": {
            "screenshot_url": screenshot_url,
            "screen_type": "unknown",
            "uploaded_at": _now(),
        },
        "status": "processing",
        "outputs": None,
        "history_preview": None,
        "regenerations": [],
        "error": None,
        "timestamps": {
            "created_at": _now(),
            "completed_at": None,
            "updated_at": _now(),
            "pipeline_duration_seconds": None,
        },
    }

    evaluations_collection.insert_one(doc)
    return True


def complete_evaluation(
    evaluation_id: str,
    tasks_output: list,
    pipeline_duration_seconds: float,
    preview_image_url: Optional[str] = None,
) -> bool:
    vision_raw = str(tasks_output[0].raw) if len(tasks_output) > 0 else ""
    heuristic_raw = str(tasks_output[1].raw) if len(tasks_output) > 1 else ""
    feedback_raw = str(tasks_output[2].raw) if len(tasks_output) > 2 else ""
    wireframe_html = str(tasks_output[3].raw) if len(tasks_output) > 3 else ""

    screen_type = _detect_screen_type(vision_raw)
    heuristic_scores = _parse_heuristic_scores(heuristic_raw)
    feedback_structured = _parse_feedback_report(feedback_raw)
    ux_score = _compute_ux_score(heuristic_scores)

    history_preview = _build_history_preview(
        screen_type=screen_type,
        issues=feedback_structured["issues_detected"],
        ux_score=ux_score,
        preview_image_url=preview_image_url,
    )

    evaluations_collection.update_one(
        {"evaluation_id": evaluation_id},
        {
            "$set": {
                "input.screen_type": screen_type,
                "status": "completed",
                "outputs": {
                    "vision_raw": vision_raw,
                    "heuristics_raw": heuristic_raw,
                    "feedback_raw": feedback_raw,
                    "wireframe_html": wireframe_html,
                    "heuristic_scores": heuristic_scores,
                    "feedback_structured": feedback_structured,
                    "ux_score": ux_score,
                    "preview_image_url": preview_image_url,
                },
                "history_preview": history_preview,
                "error": None,
                "timestamps.completed_at": _now(),
                "timestamps.updated_at": _now(),
                "timestamps.pipeline_duration_seconds": round(pipeline_duration_seconds, 2),
            }
        }
    )
    return True


def fail_evaluation(evaluation_id: str, error: str) -> bool:
    evaluations_collection.update_one(
        {"evaluation_id": evaluation_id},
        {
            "$set": {
                "status": "failed",
                "error": error,
                "timestamps.completed_at": _now(),
                "timestamps.updated_at": _now(),
            }
        }
    )
    return True


def get_evaluation(evaluation_id: str) -> Optional[dict]:
    return evaluations_collection.find_one(
        {"evaluation_id": evaluation_id},
        {"_id": 0}
    )


def get_user_evaluations(user_id: str, limit: int = 20) -> list:
    projection = {
        "_id": 0,
        "evaluation_id": 1,
        "status": 1,
        "input.screenshot_url": 1,
        "input.screen_type": 1,
        "history_preview": 1,
        "timestamps.created_at": 1,
        "timestamps.completed_at": 1,
    }

    cursor = (
        evaluations_collection.find({"user_id": user_id}, projection)
        .sort("timestamps.created_at", DESCENDING)
        .limit(limit)
    )
    return list(cursor)


def get_evaluations_for_analysis(limit: int = 200) -> list:
    cursor = (
        evaluations_collection.find({"status": "completed"}, {"_id": 0})
        .sort("timestamps.created_at", DESCENDING)
        .limit(limit)
    )
    return list(cursor)


def update_wireframe(
    evaluation_id: str,
    new_wireframe: str,
    feedback_comment: str,
    wireframe_comment: str,
    regenerated_by: str,
    new_feedback: Optional[str] = None,
):
    evaluation = evaluations_collection.find_one({"evaluation_id": evaluation_id}, {"_id": 0})
    if not evaluation:
        return False

    current_outputs = evaluation.get("outputs", {}) or {}
    current_regenerations = evaluation.get("regenerations", []) or []

    feedback_raw = new_feedback if new_feedback else current_outputs.get("feedback_raw", "")
    feedback_structured = _parse_feedback_report(feedback_raw)
    ux_score = current_outputs.get("ux_score")
    screen_type = evaluation.get("input", {}).get("screen_type", "unknown")
    preview_image_url = current_outputs.get("preview_image_url")

    new_version = len(current_regenerations) + 1

    history_preview = _build_history_preview(
        screen_type=screen_type,
        issues=feedback_structured["issues_detected"],
        ux_score=ux_score,
        preview_image_url=preview_image_url,
    )

    update_fields = {
        "outputs.wireframe_html": new_wireframe,
        "history_preview": history_preview,
        "timestamps.updated_at": _now(),
    }

    if new_feedback:
        update_fields["outputs.feedback_raw"] = new_feedback
        update_fields["outputs.feedback_structured"] = feedback_structured

    evaluations_collection.update_one(
        {"evaluation_id": evaluation_id},
        {
            "$set": update_fields,
            "$push": {
                "regenerations": {
                    "version": new_version,
                    "feedback_comment": feedback_comment,
                    "wireframe_comment": wireframe_comment,
                    "regenerated_by": regenerated_by,
                    "feedback_raw": feedback_raw,
                    "wireframe_html": new_wireframe,
                    "created_at": _now(),
                }
            },
        }
    )
    return True