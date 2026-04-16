import os
import json
import re
from pathlib import Path
from typing import List, Optional, Literal

from dotenv import load_dotenv
from crewai.tools import tool
from src.utils.context_guard import truncate_text
from pydantic import BaseModel, validator

# Vertex structured output is best used through google-genai.
from google import genai
from google.genai.types import GenerateContentConfig

load_dotenv()

OUTPUT_DIR = Path("data/outputs")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Tuned endpoint
model_name = "projects/75094798515/locations/us-central1/endpoints/1191994299567308800"

# Gen AI client for Vertex
client = genai.Client(
    vertexai=True,
    project="heuruxagent",
    location="us-central1",
)

# -----------------------------------------------------------------------------
# Response schema
# Keep this compact. Vertex structured output supports a subset of schema fields.
# -----------------------------------------------------------------------------
RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "feedback_items": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "title": {"type": "STRING"},
                    "priority": {
                        "type": "STRING",
                        "enum": ["high", "medium", "low"],
                    },
                    "effort_estimate": {
                        "type": "STRING",
                        "enum": ["low", "medium", "high"],
                    },
                    "why_it_matters": {"type": "STRING"},
                    "what_to_do": {
                        "type": "ARRAY",
                        "items": {"type": "STRING"},
                    },
                    "wireframe_changes": {
                        "type": "STRING",
                        "nullable": True,
                    },
                },
                "required": [
                    "title",
                    "priority",
                    "effort_estimate",
                    "why_it_matters",
                    "what_to_do",
                    "wireframe_changes",
                ],
            },
        },
        "ux_score": {
            "type": "OBJECT",
            "properties": {
                "score": {"type": "NUMBER"},
                "grade": {
                    "type": "STRING",
                    "enum": ["A", "B", "C", "D", "F"],
                },
            },
            "required": ["score", "grade"],
        },
        "summary": {
            "type": "OBJECT",
            "properties": {
                "total_issues": {"type": "INTEGER"},
                "high": {"type": "INTEGER"},
                "medium": {"type": "INTEGER"},
                "low": {"type": "INTEGER"},
            },
            "required": ["total_issues", "high", "medium", "low"],
        },
    },
    "required": ["feedback_items", "ux_score", "summary"],
}


# -----------------------------------------------------------------------------
# Pydantic safety net
# IMPORTANT:
# - Keep score in 0-10 internally.
# - Do not silently convert enum-like fields to "N/A" values outside schema.
# -----------------------------------------------------------------------------
class _FeedbackItem(BaseModel):
    title: str
    priority: Literal["high", "medium", "low"]
    effort_estimate: Literal["low", "medium", "high"]
    why_it_matters: str
    what_to_do: List[str]
    wireframe_changes: Optional[str] = None

    @validator("title", "why_it_matters", pre=True, always=True)
    def _clean_required_strings(cls, v):
        return str(v).strip() if v is not None else ""

    @validator("what_to_do", pre=True, always=True)
    def _clean_steps(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            v = [v]
        if isinstance(v, list):
            return [str(s).strip() for s in v if str(s).strip()]
        return []

    @validator("wireframe_changes", pre=True, always=True)
    def _clean_wireframe_changes(cls, v):
        if v is None:
            return None
        s = str(v).strip()
        return s if s else None


class _UXScore(BaseModel):
    score: float
    grade: Literal["A", "B", "C", "D", "F"]

    @validator("score", pre=True, always=True)
    def _clean_score(cls, v):
        try:
            score = float(v)
        except (TypeError, ValueError):
            score = 0.0

        # Keep backend JSON in 0-10 scale
        if score < 0:
            score = 0.0
        if score > 10:
            score = 10.0
        return round(score, 1)


class _Summary(BaseModel):
    total_issues: int
    high: int
    medium: int
    low: int

    @validator("total_issues", "high", "medium", "low", pre=True, always=True)
    def _clean_ints(cls, v):
        try:
            value = int(v)
        except (TypeError, ValueError):
            value = 0
        return max(0, value)


class _FeedbackReport(BaseModel):
    feedback_items: List[_FeedbackItem]
    ux_score: _UXScore
    summary: _Summary

    def to_frontend_dict(self) -> dict:
        # Recompute summary from actual items so counts always match
        items = self.feedback_items
        high = sum(1 for i in items if i.priority == "high")
        medium = sum(1 for i in items if i.priority == "medium")
        low = sum(1 for i in items if i.priority == "low")

        return {
            "feedback_items": [
                {
                    "title": i.title,
                    "priority": i.priority,
                    "effort_estimate": i.effort_estimate,
                    "why_it_matters": i.why_it_matters,
                    "what_to_do": i.what_to_do,
                    "wireframe_changes": i.wireframe_changes,
                }
                for i in items
            ],
            "ux_score": {
                # keep 0-10 in backend JSON
                "score": self.ux_score.score,
                "grade": self.ux_score.grade,
            },
            "summary": {
                "total_issues": len(items),
                "high": high,
                "medium": medium,
                "low": low,
            },
        }


def _validate_report(raw: dict) -> _FeedbackReport:
    return _FeedbackReport(**raw)


def _extract_json_loose(text: str) -> dict:
    """
    Fallback parser only for endpoint/schema fallback mode.
    Tries hard to recover JSON if the model adds code fences or extra text.
    """
    text = text.strip()
    text = re.sub(r"```json\s*|```", "", text, flags=re.IGNORECASE).strip()

    try:
        return json.loads(text)
    except Exception:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start:end + 1]
        return json.loads(candidate)

    raise ValueError("No valid JSON found in model output.")


def convert_feedback_to_markdown(feedback_data: dict) -> str:
    md = "# 📋 UX Feedback Report\n\n---\n\n"

    if "summary" in feedback_data:
        s = feedback_data["summary"]
        if isinstance(s, dict):
            total = s.get("total_issues", 0)
            high = s.get("high", 0)
            med = s.get("medium", 0)
            low = s.get("low", 0)
            md += "## 📊 Summary\n\n"
            md += f"> 🔢 **{total} issues found** — "
            md += f"🔴 {high} High · 🟡 {med} Medium · 🟢 {low} Low\n\n---\n\n"

    if "ux_score" in feedback_data:
        score_data = feedback_data["ux_score"]
        score = score_data.get("score", 0)
        grade = str(score_data.get("grade", "N/A")).upper()

        # Convert only for display
        if isinstance(score, (int, float)):
            display_score = int(round(score * 10)) if score <= 10 else int(round(score))
        else:
            display_score = 0

        md += "## 🎯 Overall UX Score\n\n"
        md += f"> ### {display_score} / 100 — {grade}\n\n---\n\n"

    items = feedback_data.get("feedback_items", [])
    grouped = {"high": [], "medium": [], "low": []}
    for item in items:
        p = (item.get("priority") or "low").lower()
        grouped.setdefault(p, []).append(item)

    priority_config = [
        ("high", "🔴 High Priority", "HIGH"),
        ("medium", "🟡 Medium Priority", "MEDIUM"),
        ("low", "🟢 Low Priority", "LOW"),
    ]

    md += "## 🔧 Detailed Recommendations\n\n"
    for key, section_title, tag in priority_config:
        bucket = grouped.get(key, [])
        if not bucket:
            continue

        md += f"### {section_title}\n\n"
        for item in bucket:
            title = item.get("title", "Recommendation")
            effort = item.get("effort_estimate", "N/A")
            why = item.get("why_it_matters", "N/A")
            steps = item.get("what_to_do", [])
            wf = item.get("wireframe_changes") or "N/A"

            md += f"#### `[{tag}]` {title}\n\n"
            md += f"> ⏱ Effort: **{effort}**\n\n"
            md += f"**💬 Why it matters**\n\n{why}\n\n"
            md += "**🛠 Implementation Steps**\n\n"

            if isinstance(steps, list):
                for i, step in enumerate(steps, 1):
                    md += f"{i}. {step}\n"
            else:
                md += f"1. {steps}\n"

            md += f"\n**✏️ Wireframe Changes**\n\n{wf}\n\n---\n\n"

    return md


@tool("generate_feedback")
def generate_feedback(
    vision_analysis: str,
    heuristic_evaluation: str,
    evaluation_id: str = "",
) -> str:
    """
    Convert UX violations into developer-friendly feedback JSON and save report.

    Returns:
        JSON string of the validated feedback report.
    """
    vision_analysis = truncate_text(vision_analysis, 6000)
    heuristic_evaluation = truncate_text(heuristic_evaluation, 6000)

    prompt = f"""
TASK: Convert UX violations into structured UX feedback.

You are a UX expert. Based on the given inputs, generate a structured JSON report.

VISION ANALYSIS:
{vision_analysis}

HEURISTIC EVALUATION:
{heuristic_evaluation}

Rules:
- Keep recommendations practical and UI-specific.
- Avoid generic phrases like "apply best practices".
- UX score must be between 0.0 and 10.0.
- Grade mapping:
  - 8.5–10 → A
  - 7–8.4 → B
  - 5–6.9 → C
  - 3–4.9 → D
  - <3 → F
- Summary counts must match feedback_items exactly.
- what_to_do must always be a list of specific action steps.
"""

    print("=== FEEDBACK MODEL ===", model_name)

    raw_text = ""
    used_schema = True

    try:
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=RESPONSE_SCHEMA,
                max_output_tokens=2048,
                temperature=0.1,
            ),
        )
        raw_text = (response.text or "").strip()

    except Exception as e:
        error_msg = str(e)
        used_schema = False
        print(f"[ERROR] Structured-output call failed: {error_msg}")

        # Fallback for tuned endpoints that may reject response_schema
        if any(k in error_msg.lower() for k in ("400", "invalid", "response_schema", "unsupported")):
            print("[FALLBACK] Retrying without response_schema...")
            try:
                fallback_prompt = prompt + """

Return ONLY valid JSON.
Do not use markdown code fences.
Do not add explanation text.
Use exactly these top-level fields only:
- feedback_items
- ux_score
- summary
"""
                response = client.models.generate_content(
                    model=model_name,
                    contents=fallback_prompt,
                    config=GenerateContentConfig(
                        response_mime_type="application/json",
                        max_output_tokens=2048,
                        temperature=0.1,
                    ),
                )
                raw_text = (response.text or "").strip()
            except Exception as e2:
                print(f"[FALLBACK ERROR] {e2}")
                return json.dumps(
                    {
                        "error": f"Model call failed: {e2}",
                        "feedback_items": [],
                        "ux_score": {"score": 0.0, "grade": "F"},
                        "summary": {
                            "total_issues": 0,
                            "high": 0,
                            "medium": 0,
                            "low": 0,
                        },
                    },
                    ensure_ascii=False,
                )
        else:
            return json.dumps(
                {
                    "error": f"Model call failed: {error_msg}",
                    "feedback_items": [],
                    "ux_score": {"score": 0.0, "grade": "F"},
                    "summary": {
                        "total_issues": 0,
                        "high": 0,
                        "medium": 0,
                        "low": 0,
                    },
                },
                ensure_ascii=False,
            )

    print("=== USED RESPONSE SCHEMA ===", used_schema)
    print("=== RAW OUTPUT LENGTH ===", len(raw_text))
    print("=== RAW OUTPUT START ===")
    print(raw_text[:1000])
    print("=== RAW OUTPUT END ===")
    print(raw_text[-500:])

    try:
        if used_schema:
            raw_dict = json.loads(raw_text)
        else:
            raw_dict = _extract_json_loose(raw_text)

        report = _validate_report(raw_dict)
        frontend_dict = report.to_frontend_dict()

    except Exception as e:
        print(f"[VALIDATION ERROR] {e}")

        file_id = evaluation_id if evaluation_id else "latest"
        raw_path = OUTPUT_DIR / f"feedback_raw_{file_id}.txt"
        with open(raw_path, "w", encoding="utf-8") as f:
            f.write(raw_text)

        return json.dumps(
            {
                "error": "Could not parse or validate model output",
                "feedback_items": [],
                "ux_score": {"score": 0.0, "grade": "F"},
                "summary": {
                    "total_issues": 0,
                    "high": 0,
                    "medium": 0,
                    "low": 0,
                },
            },
            ensure_ascii=False,
        )

    file_id = evaluation_id if evaluation_id else "latest"
    json_path = OUTPUT_DIR / f"feedback_{file_id}.json"
    md_path = OUTPUT_DIR / f"feedback_{file_id}.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(frontend_dict, f, indent=2, ensure_ascii=False)

    md_content = convert_feedback_to_markdown(frontend_dict)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    print(f"✓ Saved → {json_path} | {md_path}")

    # IMPORTANT: return JSON, not markdown
    return json.dumps(frontend_dict, ensure_ascii=False)