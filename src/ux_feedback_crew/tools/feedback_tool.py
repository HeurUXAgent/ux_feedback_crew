import os
import json
from pathlib import Path
from dotenv import load_dotenv
from crewai.tools import tool
from src.utils.context_guard import truncate_text

from google import genai
from google.genai.types import GenerateContentConfig, HttpOptions
from pydantic import BaseModel, validator
from typing import List, Optional

load_dotenv()

OUTPUT_DIR = Path("data/outputs")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

model_name = "projects/75094798515/locations/us-central1/endpoints/4869200987501363200"

# ── New google-genai client pointing at Vertex AI ─────────────────────────────
client = genai.Client(
    vertexai=True,
    project="heuruxagent",
    location="us-central1",
)

# ── Response schema enforced at API level ─────────────────────────────────────
# This tells the model exactly what JSON to produce.
# enum fields mean the model literally cannot output anything else.
RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "feedback_items": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "title": {
                        "type": "STRING",
                        "description": "Short title of the UX issue."
                    },
                    "priority": {
                        "type": "STRING",
                        "enum": ["high", "medium", "low"],
                        "description": "Severity of the issue."
                    },
                    "effort_estimate": {
                        "type": "STRING",
                        "enum": ["low", "medium", "high"],
                        "description": "Estimated implementation effort."
                    },
                    "why_it_matters": {
                        "type": "STRING",
                        "description": "Why this issue affects the user experience."
                    },
                    "what_to_do": {
                        "type": "ARRAY",
                        "items": {"type": "STRING"},
                        "description": "List of concrete implementation steps."
                    },
                    "wireframe_changes": {
                        "type": "STRING",
                        "nullable": True,
                        "description": "Description of the visual change needed in the wireframe."
                    },
                },
                "required": [
                    "title",
                    "priority",
                    "effort_estimate",
                    "why_it_matters",
                    "what_to_do",
                ],
            },
        },
        "ux_score": {
            "type": "OBJECT",
            "properties": {
                "score": {
                    "type": "NUMBER",
                    "description": "UX score between 0.0 and 10.0."
                },
                "grade": {
                    "type": "STRING",
                    "enum": ["A", "B", "C", "D", "F"],
                    "description": "Grade: A(8.5-10), B(7-8.4), C(5-6.9), D(3-4.9), F(<3)."
                },
            },
            "required": ["score", "grade"],
        },
        "summary": {
            "type": "OBJECT",
            "properties": {
                "total_issues": {"type": "INTEGER"},
                "high":         {"type": "INTEGER"},
                "medium":       {"type": "INTEGER"},
                "low":          {"type": "INTEGER"},
            },
            "required": ["total_issues", "high", "medium", "low"],
        },
    },
    "required": ["feedback_items", "ux_score", "summary"],
}


# ── Pydantic validation (safety net after API response) ───────────────────────

class _FeedbackItem(BaseModel):
    title: str = "Untitled Recommendation"
    priority: str = "low"
    effort_estimate: str = "N/A"
    why_it_matters: str = ""
    what_to_do: List[str] = []
    wireframe_changes: Optional[str] = None

    @validator("priority", pre=True, always=True)
    def norm_priority(cls, v):
        v = str(v).lower().strip() if v else "low"
        return v if v in ("high", "medium", "low") else "low"

    @validator("what_to_do", pre=True, always=True)
    def norm_steps(cls, v):
        if v is None: return []
        if isinstance(v, str): return [v] if v.strip() else []
        if isinstance(v, list): return [str(s) for s in v if str(s).strip()]
        return []

    @validator("wireframe_changes", pre=True, always=True)
    def norm_wireframe(cls, v):
        if not v or str(v).strip() in ("", "N/A", "null", "None"):
            return None
        return str(v).strip()


class _UXScore(BaseModel):
    score: float = 0.0
    grade: str = "N/A"

    @validator("score", pre=True, always=True)
    def norm_score(cls, v):
        try:
            v = float(v)
        except (TypeError, ValueError):
            return 0.0
        # model trained on 0-10, normalize to 0-100 for Flutter
        return round(v * 10, 1) if v <= 10 else round(v, 1)


class _FeedbackReport(BaseModel):
    feedback_items: List[_FeedbackItem] = []
    ux_score: Optional[_UXScore] = None

    def to_frontend_dict(self) -> dict:
        items = self.feedback_items
        high   = sum(1 for i in items if i.priority == "high")
        medium = sum(1 for i in items if i.priority == "medium")
        low    = sum(1 for i in items if i.priority == "low")
        return {
            "feedback_items": [
                {
                    "title":             i.title,
                    "priority":          i.priority,
                    "effort_estimate":   i.effort_estimate,
                    "why_it_matters":    i.why_it_matters,
                    "what_to_do":        i.what_to_do,
                    "wireframe_changes": i.wireframe_changes,
                }
                for i in items
            ],
            "ux_score": {
                "score": self.ux_score.score,
                "grade": self.ux_score.grade,
            } if self.ux_score else None,
            "summary": {
                "total_issues": len(items),
                "high":         high,
                "medium":       medium,
                "low":          low,
            },
        }


def _validate(raw: dict) -> _FeedbackReport:
    try:
        return _FeedbackReport(**raw)
    except Exception as e:
        print(f"[Pydantic] Validation error: {e}")
        return _FeedbackReport()


# ── Markdown converter ────────────────────────────────────────────────────────

def convert_feedback_to_markdown(report: _FeedbackReport) -> str:
    d = report.to_frontend_dict()
    md = "# UX Feedback Report\n\n---\n\n"

    s = d.get("summary", {})
    if s:
        md += "## Summary\n\n"
        md += f"> {s['total_issues']} issues found -- "
        md += f"High: {s['high']} / Medium: {s['medium']} / Low: {s['low']}\n\n---\n\n"

    sc = d.get("ux_score")
    if sc:
        md += "## Overall UX Score\n\n"
        md += f"> {sc['score']} / 100 -- Grade: {sc['grade'].upper()}\n\n---\n\n"

    grouped = {"high": [], "medium": [], "low": []}
    for item in report.feedback_items:
        grouped[item.priority].append(item)

    md += "## Detailed Recommendations\n\n"
    for key, section_title, tag in [
        ("high",   "High Priority",   "HIGH"),
        ("medium", "Medium Priority", "MEDIUM"),
        ("low",    "Low Priority",    "LOW"),
    ]:
        bucket = grouped.get(key, [])
        if not bucket:
            continue
        md += f"### {section_title}\n\n"
        for item in bucket:
            md += f"#### [{tag}] {item.title}\n\n"
            md += f"> Effort: {item.effort_estimate}\n\n"
            md += f"**Why it matters**\n\n{item.why_it_matters}\n\n"
            md += "**Implementation Steps**\n\n"
            for i, step in enumerate(item.what_to_do, 1):
                md += f"{i}. {step}\n"
            if item.wireframe_changes:
                md += f"\n**Wireframe Changes**\n\n{item.wireframe_changes}\n"
            md += "\n---\n\n"
    return md


# ── Tool ──────────────────────────────────────────────────────────────────────

@tool("generate_feedback")
def generate_feedback(vision_analysis: str, heuristic_evaluation: str, evaluation_id: str = "") -> str:
    """
    Convert UX violations into developer-friendly feedback JSON and save report.

    Args:
        vision_analysis: JSON string from vision tool.
        heuristic_evaluation: JSON string from heuristic tool.
        evaluation_id: Optional ID used to name the saved files.

    Returns:
        JSON string of the validated feedback report.
        FastAPI parses this directly -- no file dependency.
    """
    vision_analysis      = truncate_text(vision_analysis, 6000)
    heuristic_evaluation = truncate_text(heuristic_evaluation, 6000)

    prompt = f"""You are a UX expert. Analyse the following UX evaluation inputs and generate a structured feedback report.

VISION ANALYSIS:
{vision_analysis}

HEURISTIC EVALUATION:
{heuristic_evaluation}

Rules:
- Keep recommendations practical and UI-specific.
- Avoid generic phrases like "apply best practices".
- UX score must be between 0.0 and 10.0.
- Grade: A(8.5-10), B(7-8.4), C(5-6.9), D(3-4.9), F(below 3).
- Summary counts must match feedback_items exactly.
- what_to_do must always be a list of specific action steps.
"""

    print("=== FEEDBACK MODEL ===", model_name)

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
        print(f"[ERROR] Model call failed: {error_msg}")

        # ── Fallback: response_schema not supported by this endpoint ──────────
        # If the fine-tuned endpoint rejects response_schema, retry without it.
        if "response_schema" in error_msg.lower() or "invalid" in error_msg.lower() or "400" in error_msg:
            print("[FALLBACK] Retrying without response_schema...")
            try:
                fallback_prompt = prompt + """

Return ONLY valid JSON with this exact structure, no markdown, no extra text:
{
  "feedback_items": [{"title": "...", "priority": "high|medium|low", "effort_estimate": "low|medium|high", "why_it_matters": "...", "what_to_do": ["step 1"], "wireframe_changes": "..."}],
  "ux_score": {"score": 7.5, "grade": "A|B|C|D|F"},
  "summary": {"total_issues": 1, "high": 0, "medium": 1, "low": 0}
}"""
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
                return json.dumps({"error": f"Model call failed: {e2}", "feedback_items": []})
        else:
            return json.dumps({"error": f"Model call failed: {error_msg}", "feedback_items": []})

    print("=== RAW OUTPUT (first 1000 chars) ===")
    print(raw_text[:1000])

    # ── Parse JSON ────────────────────────────────────────────────────────────
    try:
        raw_dict = json.loads(raw_text)
    except Exception:
        # Strip markdown fences if model added them despite instructions
        import re
        raw_text = re.sub(r"^```json\s*|^```\s*|```$", "", raw_text, flags=re.IGNORECASE | re.MULTILINE).strip()
        try:
            raw_dict = json.loads(raw_text)
        except Exception as e:
            print(f"[JSON] Parse error: {e}")
            return json.dumps({"error": "Could not parse model output", "feedback_items": []})

    # ── Validate with Pydantic ────────────────────────────────────────────────
    report = _validate(raw_dict)
    frontend_dict = report.to_frontend_dict()

    # ── Save files ────────────────────────────────────────────────────────────
    file_id   = evaluation_id if evaluation_id else "latest"
    json_path = OUTPUT_DIR / f"feedback_{file_id}.json"
    md_path   = OUTPUT_DIR / f"feedback_{file_id}.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(frontend_dict, f, indent=2, ensure_ascii=False)

    md_content = convert_feedback_to_markdown(report)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    print(f"Saved -> {json_path} | {md_path}")

    # Return JSON string -- FastAPI parses this directly
    return json.dumps(frontend_dict, ensure_ascii=False)