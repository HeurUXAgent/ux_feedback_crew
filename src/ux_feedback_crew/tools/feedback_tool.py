import os
import json
import re
from pathlib import Path
from dotenv import load_dotenv
from crewai.tools import tool
from src.utils.context_guard import truncate_text

load_dotenv()

OUTPUT_DIR = Path("data/outputs")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

model_name = "projects/75094798515/locations/us-central1/endpoints/4869200987501363200"

import vertexai
from vertexai.generative_models import GenerativeModel

vertexai.init(project="heuruxagent", location="us-central1")


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _extract_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```json\s*|^```\s*|```$", "", text, flags=re.IGNORECASE | re.MULTILINE).strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            pass
    raise ValueError("No valid JSON found in model output")


# ─── Key alias remapping (runs before Pydantic) ───────────────────────────────

STEP_KEY_ALIASES = (
    "actionable_steps",
    "how_to_fix",
    "action_steps",
    "technical_steps",
    "steps",
    "action_items",
)

def _remap_keys(data: dict) -> dict:
    """Remap known key aliases to canonical names before validation."""
    for item in data.get("feedback_items", []):
        # Steps
        if "what_to_do" not in item:
            for alias in STEP_KEY_ALIASES:
                if alias in item:
                    item["what_to_do"] = item.pop(alias)
                    break
        # Why
        if "why_it_matters" not in item and "why" in item:
            item["why_it_matters"] = item.pop("why")

    # ux_score as flat number at root
    if "ux_score" not in data and "overall_ux_score" in data:
        data["ux_score"] = {
            "score": data.pop("overall_ux_score"),
            "grade": "N/A",
        }
    elif "ux_score" in data and isinstance(data["ux_score"], (int, float)):
        data["ux_score"] = {
            "score": data["ux_score"],
            "grade": "N/A",
        }

    return data


# ─── Pydantic validation ──────────────────────────────────────────────────────

from pydantic import BaseModel, validator
from typing import List, Optional


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
        if v is None:
            return []
        if isinstance(v, str):
            return [v] if v.strip() else []
        if isinstance(v, list):
            return [str(s) for s in v if str(s).strip()]
        return []

    @validator("effort_estimate", pre=True, always=True)
    def norm_effort(cls, v):
        return str(v).strip() if v else "N/A"

    @validator("why_it_matters", pre=True, always=True)
    def norm_why(cls, v):
        return str(v).strip() if v else ""

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
        # model trained on 0-10 -> normalize to 0-100 for frontend
        if v <= 10:
            return round(v * 10, 1)
        return round(v, 1)

    @validator("grade", pre=True, always=True)
    def norm_grade(cls, v):
        return str(v).strip() if v else "N/A"


class _FeedbackReport(BaseModel):
    feedback_items: List[_FeedbackItem] = []
    ux_score: Optional[_UXScore] = None

    @validator("feedback_items", pre=True, always=True)
    def norm_items(cls, v):
        return v if isinstance(v, list) else []

    def to_frontend_dict(self) -> dict:
        """
        Serialize to exactly what Flutter's _ParseResult.tryParse expects.
        Summary counts are recomputed from actual items so they're always correct.
        """
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


# ─── Markdown converter ───────────────────────────────────────────────────────

def convert_feedback_to_markdown(report: _FeedbackReport) -> str:
    d = report.to_frontend_dict()
    md = "# UX Feedback Report\n\n---\n\n"

    # Summary
    s = d.get("summary", {})
    if s:
        md += "## Summary\n\n"
        md += f"> {s['total_issues']} issues found -- "
        md += f"High: {s['high']} / Medium: {s['medium']} / Low: {s['low']}\n\n---\n\n"

    # UX Score
    sc = d.get("ux_score")
    if sc:
        md += "## Overall UX Score\n\n"
        md += f"> {sc['score']} / 100 -- Grade: {sc['grade'].upper()}\n\n---\n\n"

    # Items grouped by priority
    grouped = {"high": [], "medium": [], "low": []}
    for item in report.feedback_items:
        grouped[item.priority].append(item)

    priority_config = [
        ("high",   "High Priority",   "HIGH"),
        ("medium", "Medium Priority", "MEDIUM"),
        ("low",    "Low Priority",    "LOW"),
    ]

    md += "## Detailed Recommendations\n\n"
    for key, section_title, tag in priority_config:
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


# ─── Tool ─────────────────────────────────────────────────────────────────────

@tool("generate_feedback")
def generate_feedback(vision_analysis: str, heuristic_evaluation: str, evaluation_id: str = "") -> str:
    """
    Convert UX violations into developer-friendly feedback JSON and save report.
    Also estimate an overall UX score from 0-10 based on the severity and number of usability issues.

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

    prompt = f"""
TASK: Convert UX violations into structured UX feedback.

You are a UX expert. Based on the given inputs, generate a structured JSON report.

VISION ANALYSIS:
{vision_analysis}

HEURISTIC EVALUATION:
{heuristic_evaluation}

Return ONLY valid JSON. No explanations. No markdown. No extra text.

Use EXACTLY this structure:

{{
  "feedback_items": [
    {{
      "title": "...",
      "priority": "high|medium|low",
      "effort_estimate": "low|medium|high",
      "why_it_matters": "...",
      "what_to_do": ["step 1", "step 2"],
      "wireframe_changes": "..."
    }}
  ],
  "ux_score": {{
    "score": 7.5,
    "grade": "A|B|C|D|F"
  }},
  "summary": {{
    "total_issues": 10,
    "high": 2,
    "medium": 5,
    "low": 3
  }}
}}

STRICT RULES:

1. Do NOT include any fields other than:
   - feedback_items
   - ux_score
   - summary

2. Each feedback item MUST include:
   - title
   - priority
   - effort_estimate
   - why_it_matters
   - what_to_do (array of strings)
   - wireframe_changes

3. "what_to_do" MUST always be a list of strings. Never rename it.

4. Keep recommendations practical and UI-specific.

5. Avoid generic phrases like "apply best practices".

6. UX score MUST be between 0-10 (can include decimals).

7. Grade mapping:
   - 8.5-10 -> A
   - 7-8.4 -> B
   - 5-6.9 -> C
   - 3-4.9 -> D
   - <3 -> F

8. Summary counts MUST match feedback_items exactly.

9. DO NOT wrap JSON in ``` or add any explanation.

RETURN ONLY JSON.
"""

    # Generate
    model = GenerativeModel(model_name)
    try:
        response = model.generate_content(
            prompt,
            generation_config={
                "max_output_tokens": 2048,  # bumped -- 1024 too low for full reports
                "temperature": 0.1,
            }
        )
    except Exception as e:
        return json.dumps({"error": f"Model call failed: {e}", "feedback_items": []})

    raw_text = (response.text or "").strip()

    print("=== FEEDBACK MODEL ===", model_name)
    print("=== RAW OUTPUT (first 1000 chars) ===")
    print(raw_text[:1000])

    # Extract raw dict
    try:
        raw_dict = _extract_json(raw_text)
    except Exception as e:
        print(f"[JSON] Parse error: {e}")
        return json.dumps({"error": "Could not parse model output", "feedback_items": []})

    # Remap key aliases
    raw_dict = _remap_keys(raw_dict)

    # Validate with Pydantic
    report = _validate(raw_dict)

    # Serialize to clean frontend dict
    frontend_dict = report.to_frontend_dict()

    # Save files
    file_id   = evaluation_id if evaluation_id else "latest"
    json_path = OUTPUT_DIR / f"feedback_{file_id}.json"
    md_path   = OUTPUT_DIR / f"feedback_{file_id}.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(frontend_dict, f, indent=2, ensure_ascii=False)

    md_content = convert_feedback_to_markdown(report)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    print(f"Saved -> {json_path} | {md_path}")

    # Return JSON string -- FastAPI parses this directly, no file needed
    return json.dumps(frontend_dict, ensure_ascii=False)