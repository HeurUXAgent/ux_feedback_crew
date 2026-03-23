import os
import json
import re
from pathlib import Path
from dotenv import load_dotenv
from crewai.tools import tool
from src.utils.context_guard import truncate_text

import vertexai
from vertexai.generative_models import GenerativeModel

load_dotenv()

OUTPUT_DIR = Path("data/outputs")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Use the ENDPOINT path (not the model resource path)
model_name = "projects/heuruxagent/locations/us-central1/endpoints/2041925583931179008"

vertexai.init(
    project="heuruxagent",
    location="us-central1"
)


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def _normalize_inputs(vision_analysis: str, heuristic_evaluation: str) -> tuple[str, str]:
    """
    Defensively normalize tool inputs.

    CrewAI agents sometimes pass a JSON array or a nested dict instead of two
    plain strings.  This function handles every shape we have observed in the
    logs and always returns two plain JSON strings.
    """
    try:
        parsed = json.loads(vision_analysis)
    except (json.JSONDecodeError, TypeError):
        # Both args are already plain strings — nothing to do
        return vision_analysis, heuristic_evaluation

    # ── Shape 1: agent wrapped everything in an array ──────────────────────
    # e.g. [{"vision_analysis": "...", "heuristic_evaluation": "..."}, {...}]
    if isinstance(parsed, list):
        first  = parsed[0] if len(parsed) > 0 else {}
        second = parsed[1] if len(parsed) > 1 else {}

        va = first.get("vision_analysis", json.dumps(first))
        he = first.get(
            "heuristic_evaluation",
            second.get("heuristic_evaluation", heuristic_evaluation)
        )
        return va, he

    # ── Shape 2: agent stuffed everything into a single dict ───────────────
    # e.g. {"vision_analysis": "...", "heuristic_evaluation": "...",
    #        "overall_ux_score": 60, "feedback_report": {...}, ...}
    if isinstance(parsed, dict):
        va = parsed.get("vision_analysis", vision_analysis)
        he = parsed.get("heuristic_evaluation", heuristic_evaluation)
        return va, he

    # Fallback — return as-is
    return vision_analysis, heuristic_evaluation


def _extract_json(text: str) -> dict:
    """
    Extract the first valid JSON object from model output.
    Handles markdown code fences and stray conversational text.
    """
    text = text.strip()

    # Strip markdown code fences if present
    if "```" in text:
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        if match:
            text = match.group(1).strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Fall back: find first {...} block
    match = re.search(r"(\{[\s\S]*\})", text)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError as e:
            raise ValueError(f"Found JSON-like string but could not parse: {e}")

    raise ValueError("No valid JSON found in model output")


def _to_markdown(feedback_data: dict) -> str:
    """
    Convert the structured feedback JSON into a human-readable Markdown report.
    """
    md = "# 📋 UX Feedback Report\n\n---\n\n"

    # Summary block
    if "summary" in feedback_data:
        s = feedback_data["summary"]
        md += "## 📊 Summary\n"
        md += f"- **Total Issues:** {s.get('total_issues', 0)}\n"
        md += f"- **High Priority:** {s.get('high', 0)}\n"
        md += f"- **Medium Priority:** {s.get('medium', 0)}\n"
        md += f"- **Low Priority:** {s.get('low', 0)}\n"
        md += f"- **Estimated Effort:** {s.get('estimated_total_effort', 'N/A')}\n\n---\n\n"

    # Quick wins
    if feedback_data.get("quick_wins"):
        md += "## ⚡ Quick Wins\n\n"
        for w in feedback_data["quick_wins"]:
            md += (
                f"- **{w.get('change', 'N/A')}** — "
                f"{w.get('impact', 'N/A')} "
                f"(Effort: {w.get('effort', 'N/A')})\n"
            )
        md += "\n---\n\n"

    # UX score
    if "ux_score" in feedback_data:
        score = feedback_data["ux_score"]
        md += "## 🎯 Overall UX Score\n"
        md += f"- **Score:** {score.get('score', 'N/A')} / 100\n"
        md += f"- **Grade:** {score.get('grade', 'N/A')}\n"
        md += f"- **Severity Level:** {score.get('severity', 'N/A')}\n"
        md += f"- **Reason:** {score.get('reasoning', 'N/A')}\n\n---\n\n"

    # Detailed recommendations
    md += "## 🔧 Detailed Recommendations\n\n"
    for item in feedback_data.get("feedback_items", []):
        md += f"### {item.get('title', 'Recommendation')}\n"
        md += (
            f"**Priority:** {item.get('priority', 'N/A')} | "
            f"**Effort:** {item.get('effort_estimate', 'N/A')}\n\n"
        )
        md += f"**Why it matters:**\n{item.get('why_it_matters', 'N/A')}\n\n"
        md += "**Implementation Steps:**\n"
        steps = item.get("what_to_do", [])
        if isinstance(steps, list):
            for step in steps:
                md += f"- {step}\n"
        else:
            md += f"- {steps}\n"
        md += f"\n**Wireframe changes:** {item.get('wireframe_changes', 'N/A')}\n\n---\n\n"

    return md


# ---------------------------------------------------------------------------
# TOOL
# ---------------------------------------------------------------------------

@tool("generate_feedback")
def generate_feedback(vision_analysis: str, heuristic_evaluation: str = "") -> str:
    """
    Convert UX violations into developer-friendly feedback JSON and save a report.
    Estimates an overall UX score from 0-100 based on severity and number of issues.

    Args:
        vision_analysis: JSON string from the vision tool (or a wrapped payload
                         from the agent — normalized automatically).
        heuristic_evaluation: JSON string from the heuristic tool.

    Returns:
        JSON string containing structured feedback recommendations.
    """

    # ── 1. Normalize whatever shape the agent decided to send ──────────────
    vision_analysis, heuristic_evaluation = _normalize_inputs(
        vision_analysis, heuristic_evaluation
    )

    # ── 2. Truncate to avoid blowing the context window ────────────────────
    vision_analysis      = truncate_text(vision_analysis,      6000)
    heuristic_evaluation = truncate_text(heuristic_evaluation, 6000)

    # ── 3. Build the prompt ────────────────────────────────────────────────
    prompt = f"""
TASK: Convert UX violations into developer-friendly feedback.

VISION ANALYSIS:
{vision_analysis}

HEURISTIC EVALUATION:
{heuristic_evaluation}

Return ONLY valid JSON — no markdown fences, no explanation — in this exact structure:
{{
  "feedback_items": [
    {{
      "title": "...",
      "priority": "high|medium|low",
      "effort_estimate": "...",
      "why_it_matters": "...",
      "what_to_do": ["step 1", "step 2"],
      "wireframe_changes": "..."
    }}
  ],
  "quick_wins": [
    {{
      "change": "...",
      "impact": "...",
      "effort": "..."
    }}
  ],
  "ux_score": {{
    "score": 0,
    "grade": "excellent|good|average|poor",
    "severity": "low|moderate|high",
    "reasoning": "short explanation"
  }},
  "summary": {{
    "total_issues": 0,
    "high": 0,
    "medium": 0,
    "low": 0,
    "estimated_total_effort": "Low|Medium|High"
  }},
  "implementation_order": ["..."]
}}
"""

    # ── 4. Call the fine-tuned Vertex AI model (with retry) ────────────────
    model = GenerativeModel(model_name)
    raw_text = ""
    last_error = None

    for attempt in range(2):
        try:
            response = model.generate_content(
                prompt,
                generation_config={
                    "max_output_tokens": 4096,   # bumped up — 2048 truncates complex JSON
                    "temperature": 0.2,
                }
            )
            raw_text = (response.text or "").strip()
        except Exception as e:
            print(f"⚠ Vertex AI call failed (attempt {attempt + 1}): {e}")
            return json.dumps({"error": f"Vertex AI call failed: {str(e)}"})

        try:
            parsed_data = _extract_json(raw_text)
            break                               # success — exit retry loop
        except Exception as e:
            last_error = e
            print(f"⚠ JSON parsing failed (attempt {attempt + 1}): {e} — retrying...")
    else:
        print(f"✗ Could not parse feedback JSON after 2 attempts: {last_error}")
        return json.dumps({
            "error": "Could not parse JSON from model output",
            "raw_snippet": raw_text[:300]
        })

    # ── 5. Persist outputs ─────────────────────────────────────────────────
    json_path = OUTPUT_DIR / "feedback.json"
    md_path   = OUTPUT_DIR / "feedback.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(parsed_data, f, indent=2, ensure_ascii=False)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(_to_markdown(parsed_data))

    print(f"✓ Feedback saved → {json_path}, {md_path}")

    return json.dumps(parsed_data)