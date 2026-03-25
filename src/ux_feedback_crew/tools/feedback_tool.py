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

model_name = "projects/75094798515/locations/us-central1/endpoints/3613259641418416128"

import vertexai
from vertexai.generative_models import GenerativeModel

vertexai.init(project="heuruxagent", location="us-central1")


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _extract_json(text: str) -> dict:
    """Strip markdown fences and extract the first valid JSON object."""
    text = text.strip()
    # Remove ```json ... ``` or ``` ... ``` fences
    text = re.sub(
        r"^```[a-zA-Z]*\s*", "", text, flags=re.IGNORECASE | re.MULTILINE
    )
    text = re.sub(r"```\s*$", "", text, flags=re.MULTILINE).strip()

    # Direct parse
    try:
        return json.loads(text)
    except Exception:
        pass

    # Grab the outermost { ... } block
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            pass

    raise ValueError("No valid JSON found in model output")


# ── All known aliases for the "steps" field ───────────────────────────────────
_STEP_KEY_ALIASES = (
    "what_to_do",           # canonical
    "actionable_steps",
    "how_to_fix",
    "action_steps",
    "technical_steps",
    "steps",
    "developer_steps",      # Image 1
    "recommendations",      # Image 2
    "technical_solution",   # Image 3
    "implementation_steps",
    "fixes",
    "suggestions",
)

# ── All known aliases for "effort_estimate" ───────────────────────────────────
_EFFORT_KEY_ALIASES = (
    "effort_estimate",      # canonical
    "effort",               # Image 3
    "effort_level",
    "implementation_effort",
)

# ── Fields that are NOT part of our schema — strip them silently ──────────────
_ITEM_ALLOWED_KEYS = {
    "title",
    "priority",
    "effort_estimate",
    "why_it_matters",
    "what_to_do",
    "wireframe_changes",
}


def _normalize_item(item: dict) -> dict:
    """
    Normalize a single feedback item to match the canonical schema regardless
    of which key aliases the model chose to use.
    """
    # ── 1. Resolve steps → what_to_do ────────────────────────────────────────
    if "what_to_do" not in item:
        for alias in _STEP_KEY_ALIASES[1:]:       # skip canonical itself
            if alias in item:
                item["what_to_do"] = item.pop(alias)
                break

    # Ensure what_to_do is always a list of strings
    raw_steps = item.get("what_to_do")
    if raw_steps is None:
        item["what_to_do"] = []
    elif isinstance(raw_steps, str):
        item["what_to_do"] = [raw_steps] if raw_steps.strip() else []
    elif isinstance(raw_steps, list):
        # Each element could itself be a dict (seen in some outputs)
        normalized: list[str] = []
        for s in raw_steps:
            if isinstance(s, str):
                normalized.append(s)
            elif isinstance(s, dict):
                # Flatten dict step to a readable string
                parts = []
                for key in ("step", "action", "description", "details"):
                    if s.get(key):
                        parts.append(str(s[key]))
                normalized.append(" — ".join(parts) if parts else str(s))
        item["what_to_do"] = normalized
    else:
        item["what_to_do"] = [str(raw_steps)]

    # ── 2. Resolve effort_estimate ────────────────────────────────────────────
    if "effort_estimate" not in item:
        for alias in _EFFORT_KEY_ALIASES[1:]:
            if alias in item:
                item["effort_estimate"] = item.pop(alias)
                break

    if not item.get("effort_estimate"):
        item["effort_estimate"] = "N/A"
    else:
        # Normalise to low / medium / high / N/A
        effort_raw = str(item["effort_estimate"]).strip().lower()
        if effort_raw in ("low", "medium", "high"):
            item["effort_estimate"] = effort_raw
        # Otherwise keep the raw string (could be "2 days", etc.)

    # ── 3. Priority ───────────────────────────────────────────────────────────
    priority_raw = str(item.get("priority") or "low").strip().lower()
    item["priority"] = priority_raw if priority_raw in ("high", "medium", "low") else "low"

    # ── 4. why_it_matters (alias: "why", "description", "rationale") ─────────
    if not item.get("why_it_matters"):
        for alias in ("why", "description", "rationale", "reason"):
            if item.get(alias):
                item["why_it_matters"] = str(item[alias])
                break
        else:
            item["why_it_matters"] = ""

    # ── 5. wireframe_changes default ──────────────────────────────────────────
    if "wireframe_changes" not in item or item["wireframe_changes"] is None:
        item["wireframe_changes"] = None

    # ── 6. Strip unknown keys ─────────────────────────────────────────────────
    for key in list(item.keys()):
        if key not in _ITEM_ALLOWED_KEYS:
            del item[key]

    return item


def _normalize_feedback(data: dict) -> dict:
    """
    Normalize the top-level feedback dict so the Flutter frontend always
    receives a consistent structure, regardless of which variant the model
    returned.
    """
    # ── Normalize feedback_items ──────────────────────────────────────────────
    raw_items = data.get("feedback_items", [])
    if not isinstance(raw_items, list):
        raw_items = []
    data["feedback_items"] = [
        _normalize_item(item)
        for item in raw_items
        if isinstance(item, dict)
    ]
    items = data["feedback_items"]

    # ── Normalize ux_score ────────────────────────────────────────────────────
    # Three variants observed:
    #   (a) { "ux_score": { "score": 7.5, "grade": "B" } }          ← correct
    #   (b) { "overall_ux_score": 70 }                               ← Image 3
    #   (c) { "ux_score": 70 }                                       ← bare int

    def _build_score_obj(raw_score) -> dict:
        score_int = 0
        try:
            score_int = int(float(str(raw_score)))
        except (ValueError, TypeError):
            pass
        if score_int <= 10:           # 0-10 scale → 0-100
            score_int = score_int * 10
        score_int = max(0, min(100, score_int))
        return {
            "score": score_int,
            "grade": _score_to_grade(score_int),
            "severity": _score_to_severity(score_int),
            "reasoning": (
                data.get("summary", "")
                if isinstance(data.get("summary"), str)
                else ""
            ),
        }

    if "ux_score" not in data:
        raw = data.pop("overall_ux_score", None)
        data["ux_score"] = _build_score_obj(raw if raw is not None else 50)
    elif isinstance(data["ux_score"], (int, float)):
        data["ux_score"] = _build_score_obj(data["ux_score"])
    elif isinstance(data["ux_score"], dict):
        s = data["ux_score"]
        raw_s = s.get("score", 0)
        try:
            score_int = int(float(str(raw_s)))
        except (ValueError, TypeError):
            score_int = 0
        if score_int <= 10:
            score_int = score_int * 10
        score_int = max(0, min(100, score_int))
        s["score"] = score_int
        if "grade" not in s:
            s["grade"] = _score_to_grade(score_int)
        if "severity" not in s:
            s["severity"] = _score_to_severity(score_int)
        if "reasoning" not in s:
            s["reasoning"] = ""

    # ── Normalize summary ─────────────────────────────────────────────────────
    # Recalculate counts from actual items so they are always accurate.
    high   = sum(1 for i in items if i.get("priority") == "high")
    medium = sum(1 for i in items if i.get("priority") == "medium")
    low    = sum(1 for i in items if i.get("priority") == "low")

    existing_summary = data.get("summary")

    if isinstance(existing_summary, dict):
        # Overwrite counts with ground-truth values
        existing_summary["total_issues"] = len(items)
        existing_summary["high"]         = high
        existing_summary["medium"]       = medium
        existing_summary["low"]          = low
        existing_summary.setdefault("estimated_total_effort", "N/A")
    elif isinstance(existing_summary, str) and existing_summary.strip():
        # Keep the narrative string — Flutter handles both formats
        pass
    else:
        data["summary"] = {
            "total_issues": len(items),
            "high":   high,
            "medium": medium,
            "low":    low,
            "estimated_total_effort": "N/A",
        }

    # ── Strip any top-level keys outside our schema ───────────────────────────
    _TOP_ALLOWED = {"feedback_items", "ux_score", "summary"}
    for key in list(data.keys()):
        if key not in _TOP_ALLOWED:
            del data[key]

    return data


def _score_to_grade(score: int) -> str:
    if score >= 85: return "excellent"
    if score >= 70: return "good"
    if score >= 50: return "average"
    return "poor"


def _score_to_severity(score: int) -> str:
    if score >= 75: return "low"
    if score >= 50: return "moderate"
    return "high"


def convert_feedback_to_markdown(feedback_data: dict) -> str:
    md = "# 📋 UX Feedback Report\n\n---\n\n"

    # ── Summary ──
    if "summary" in feedback_data:
        s = feedback_data["summary"]
        if isinstance(s, dict):
            total  = s.get("total_issues", 0)
            high   = s.get("high", 0)
            med    = s.get("medium", 0)
            low    = s.get("low", 0)
            effort = s.get("estimated_total_effort", "N/A")
            md += "## 📊 Summary\n\n"
            md += f"> 🔢 **{total} issues found** — "
            md += f"🔴 {high} High · 🟡 {med} Medium · 🟢 {low} Low\n"
            md += f"> ⏱ Estimated Effort: **{effort}**\n\n---\n\n"
        elif isinstance(s, str) and s.strip():
            md += "## 📊 Summary\n\n"
            md += f"{s}\n\n---\n\n"

    # ── UX Score ──
    if "ux_score" in feedback_data:
        score_data = feedback_data["ux_score"]
        score     = score_data.get("score", 0)
        grade     = str(score_data.get("grade", "N/A")).upper()
        severity  = score_data.get("severity", "N/A")
        reasoning = score_data.get("reasoning", "N/A")
        md += "## 🎯 Overall UX Score\n\n"
        md += f"> ### {score} / 100 — {grade}\n"
        md += f"> **Severity:** {severity}\n\n"
        md += f"{reasoning}\n\n---\n\n"

    # ── Recommendations grouped by priority ──
    items = feedback_data.get("feedback_items", [])
    grouped = {"high": [], "medium": [], "low": []}
    for item in items:
        p = item.get("priority", "low")
        grouped.setdefault(p, []).append(item)

    priority_config = [
        ("high",   "🔴 High Priority",   "HIGH"),
        ("medium", "🟡 Medium Priority", "MEDIUM"),
        ("low",    "🟢 Low Priority",    "LOW"),
    ]

    md += "## 🔧 Detailed Recommendations\n\n"
    for key, section_title, tag in priority_config:
        bucket = grouped.get(key, [])
        if not bucket:
            continue
        md += f"### {section_title}\n\n"
        for item in bucket:
            title  = item.get("title", "Recommendation")
            effort = item.get("effort_estimate", "N/A")
            why    = item.get("why_it_matters", "N/A")
            steps  = item.get("what_to_do", [])
            wf     = item.get("wireframe_changes") or "N/A"

            md += f"#### `[{tag}]` {title}\n\n"
            md += f"> ⏱ Effort: **{effort}**\n\n"
            md += f"**💬 Why it matters**\n\n{why}\n\n"
            md += "**🛠 Implementation Steps**\n\n"
            for i, step in enumerate(steps, 1):
                md += f"{i}. {step}\n"
            md += f"\n**✏️ Wireframe Changes**\n\n{wf}\n\n---\n\n"

    return md


# ─── Tool ─────────────────────────────────────────────────────────────────────

# The prompt uses a one-shot example so the model has a concrete pattern to
# follow, and explicit FORBIDDEN FIELDS so it stops inventing keys.
_PROMPT_TEMPLATE = """
TASK: Convert the UX analysis below into a structured JSON feedback report.

You are a senior UX engineer. Read the inputs carefully, then output ONLY a
single valid JSON object — no explanations, no markdown fences, no extra text.

═══════════════════════════════════════════════════════════
VISION ANALYSIS:
{vision_analysis}

HEURISTIC EVALUATION:
{heuristic_evaluation}
═══════════════════════════════════════════════════════════

OUTPUT SCHEMA (follow this exactly):

{{
  "feedback_items": [
    {{
      "title": "Short action-oriented title",
      "priority": "high",
      "effort_estimate": "medium",
      "why_it_matters": "One sentence explaining the user impact.",
      "what_to_do": [
        "Concrete step 1.",
        "Concrete step 2."
      ],
      "wireframe_changes": "What should change visually in the wireframe."
    }}
  ],
  "ux_score": {{
    "score": 7.5,
    "grade": "B"
  }},
  "summary": {{
    "total_issues": 3,
    "high": 1,
    "medium": 1,
    "low": 1,
    "estimated_total_effort": "medium"
  }}
}}

═══════════════════════════════════════════════════════════
STRICT RULES — violating any rule will make the output unusable:

1.  Return ONLY the JSON object above. No prose before or after it.
2.  Do NOT wrap the output in ```json or any other markdown fence.
3.  Every feedback item MUST contain these keys and NO others:
      title, priority, effort_estimate, why_it_matters,
      what_to_do, wireframe_changes
4.  FORBIDDEN FIELDS — never include these in a feedback item:
      description, heuristic_violation, heuristic_principle,
      developer_steps, actionable_steps, technical_steps,
      technical_solution, recommendations, how_to_fix,
      action_steps, steps, fixes, suggestions, component,
      severity, ux_score_impact, ux_research_details, rationale
5.  "priority"        → ONLY "high", "medium", or "low"
6.  "effort_estimate" → ONLY "low", "medium", or "high"
7.  "what_to_do"      → MUST be a JSON array of plain strings (never a dict,
                         never a nested object)
8.  "ux_score.score"  → decimal between 0 and 10 (e.g. 7.5)
9.  "summary" counts  → must exactly match the feedback_items you produce
10. Do NOT include "overall_ux_score" at the top level — use "ux_score" only
11. Keep recommendations practical and UI-specific; avoid generic phrases

RETURN ONLY JSON — NOTHING ELSE.
"""


@tool("generate_feedback")
def generate_feedback(
    vision_analysis: str,
    heuristic_evaluation: str,
    evaluation_id: str = "",
) -> str:
    """
    Convert UX violations into developer-friendly feedback JSON and save report.
    Also estimate an overall UX score from 0-100 based on the severity and
    number of usability issues.

    Args:
        vision_analysis:      JSON string from vision tool.
        heuristic_evaluation: JSON string from heuristic tool.
        evaluation_id:        Optional ID used to name the saved files.

    Returns:
        Markdown string of the feedback report.
    """
    vision_analysis      = truncate_text(vision_analysis, 6000)
    heuristic_evaluation = truncate_text(heuristic_evaluation, 6000)

    prompt = _PROMPT_TEMPLATE.format(
        vision_analysis=vision_analysis,
        heuristic_evaluation=heuristic_evaluation,
    )

    # ── Generate ──────────────────────────────────────────────────────────────
    model = GenerativeModel(model_name)
    try:
        response = model.generate_content(
            prompt,
            generation_config={
                "max_output_tokens": 1024,
                "temperature": 0.1,
            },
        )
    except Exception as e:
        return f"Error calling model: {e}"

    raw_text = (response.text or "").strip()

    print("=== FEEDBACK MODEL ===", model_name)
    print("=== RAW OUTPUT (first 1000 chars) ===")
    print(raw_text[:1000])

    # ── Parse ─────────────────────────────────────────────────────────────────
    try:
        parsed_data = _extract_json(raw_text)
    except Exception as e:
        print(f"JSON parse error: {e}")
        return f"Error: Could not parse JSON. Raw: {raw_text[:300]}"

    # ── Normalise inconsistent model output ───────────────────────────────────
    parsed_data = _normalize_feedback(parsed_data)

    # ── Persist ───────────────────────────────────────────────────────────────
    file_id   = evaluation_id if evaluation_id else "latest"
    json_path = OUTPUT_DIR / f"feedback_{file_id}.json"
    md_path   = OUTPUT_DIR / f"feedback_{file_id}.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(parsed_data, f, indent=2, ensure_ascii=False)

    md_content = convert_feedback_to_markdown(parsed_data)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    print(f"✓ Saved → {json_path} | {md_path}")

    return md_content