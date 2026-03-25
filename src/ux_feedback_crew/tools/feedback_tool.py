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
from vertexai.generative_models import GenerativeModel, GenerationConfig
from vertexai.generative_models import Schema, Type

vertexai.init(project="heuruxagent", location="us-central1")


# ─── Response schema (constrained decoding) ───────────────────────────────────
# Enforced at the token level — the model physically cannot generate keys or
# enum values that are not listed here.

RESPONSE_SCHEMA = Schema(
    type=Type.OBJECT,
    required=["feedback_items", "ux_score", "summary"],
    properties={
        "feedback_items": Schema(
            type=Type.ARRAY,
            items=Schema(
                type=Type.OBJECT,
                required=[
                    "title",
                    "priority",
                    "effort_estimate",
                    "why_it_matters",
                    "what_to_do",
                    "wireframe_changes",
                ],
                properties={
                    "title":            Schema(type=Type.STRING),
                    "priority":         Schema(
                                            type=Type.STRING,
                                            enum=["high", "medium", "low"],
                                        ),
                    "effort_estimate":  Schema(
                                            type=Type.STRING,
                                            enum=["low", "medium", "high"],
                                        ),
                    "why_it_matters":   Schema(type=Type.STRING),
                    "what_to_do":       Schema(
                                            type=Type.ARRAY,
                                            items=Schema(type=Type.STRING),
                                        ),
                    "wireframe_changes": Schema(type=Type.STRING),
                },
            ),
        ),
        "ux_score": Schema(
            type=Type.OBJECT,
            required=["score", "grade"],
            properties={
                "score": Schema(type=Type.NUMBER),        # 0–10, decimals OK
                "grade": Schema(
                    type=Type.STRING,
                    enum=["A", "B", "C", "D", "F"],
                ),
            },
        ),
        "summary": Schema(
            type=Type.OBJECT,
            required=["total_issues", "high", "medium", "low"],
            properties={
                "total_issues":           Schema(type=Type.INTEGER),
                "high":                   Schema(type=Type.INTEGER),
                "medium":                 Schema(type=Type.INTEGER),
                "low":                    Schema(type=Type.INTEGER),
                "estimated_total_effort": Schema(
                    type=Type.STRING,
                    enum=["low", "medium", "high", "N/A"],
                ),
            },
        ),
    },
)

GENERATION_CONFIG = GenerationConfig(
    response_mime_type="application/json",
    response_schema=RESPONSE_SCHEMA,
    max_output_tokens=1024,
    temperature=0.1,
)

FALLBACK_CONFIG = GenerationConfig(
    max_output_tokens=1024,
    temperature=0.1,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _extract_json(text: str) -> dict:
    """Strip markdown fences and extract the first valid JSON object."""
    text = text.strip()
    text = re.sub(r"^```[a-zA-Z]*\s*", "", text, flags=re.IGNORECASE | re.MULTILINE)
    text = re.sub(r"```\s*$", "", text, flags=re.MULTILINE).strip()
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


def _normalize_feedback(data: dict) -> dict:
    """
    Safety-net normalization that runs even after constrained decoding.
    This covers the fallback path where the endpoint ignores response_schema
    and produces free-form output with aliased or extra keys.
    """
    _STEP_ALIASES   = (
        "actionable_steps", "how_to_fix", "action_steps", "technical_steps",
        "steps", "developer_steps", "recommendations", "technical_solution",
        "implementation_steps", "fixes", "suggestions",
    )
    _EFFORT_ALIASES = ("effort", "effort_level", "implementation_effort")
    _WHY_ALIASES    = ("why", "description", "rationale", "reason")
    _ALLOWED_ITEM   = {
        "title", "priority", "effort_estimate",
        "why_it_matters", "what_to_do", "wireframe_changes",
    }

    # ── feedback_items ────────────────────────────────────────────────────────
    for item in data.get("feedback_items", []):

        # steps → what_to_do
        if "what_to_do" not in item:
            for alias in _STEP_ALIASES:
                if alias in item:
                    item["what_to_do"] = item.pop(alias)
                    break

        raw = item.get("what_to_do")
        if raw is None:
            item["what_to_do"] = []
        elif isinstance(raw, str):
            item["what_to_do"] = [raw] if raw.strip() else []
        elif isinstance(raw, list):
            flat = []
            for s in raw:
                if isinstance(s, str):
                    flat.append(s)
                elif isinstance(s, dict):
                    parts = [str(v) for k in ("step","action","description","details") if (v := s.get(k))]
                    flat.append(" — ".join(parts) if parts else str(s))
            item["what_to_do"] = flat
        else:
            item["what_to_do"] = [str(raw)]

        # effort_estimate
        if "effort_estimate" not in item:
            for alias in _EFFORT_ALIASES:
                if alias in item:
                    item["effort_estimate"] = item.pop(alias)
                    break
        if not item.get("effort_estimate"):
            item["effort_estimate"] = "N/A"

        # priority
        p = str(item.get("priority") or "low").strip().lower()
        item["priority"] = p if p in ("high", "medium", "low") else "low"

        # why_it_matters
        if not item.get("why_it_matters"):
            for alias in _WHY_ALIASES:
                if item.get(alias):
                    item["why_it_matters"] = str(item[alias])
                    break
            else:
                item["why_it_matters"] = ""

        # wireframe_changes
        item.setdefault("wireframe_changes", None)

        # strip unknown keys
        for k in list(item.keys()):
            if k not in _ALLOWED_ITEM:
                del item[k]

    # ── ux_score ──────────────────────────────────────────────────────────────
    def _build_score(raw) -> dict:
        try:
            v = int(float(str(raw)))
        except (ValueError, TypeError):
            v = 50
        if v <= 10:
            v *= 10
        v = max(0, min(100, v))
        return {
            "score":     v,
            "grade":     _score_to_grade(v),
            "severity":  _score_to_severity(v),
            "reasoning": "",
        }

    if "ux_score" not in data:
        data["ux_score"] = _build_score(data.pop("overall_ux_score", 50))
    elif isinstance(data["ux_score"], (int, float)):
        data["ux_score"] = _build_score(data["ux_score"])
    elif isinstance(data["ux_score"], dict):
        s = data["ux_score"]
        try:
            v = int(float(str(s.get("score", 50))))
        except (ValueError, TypeError):
            v = 50
        if v <= 10:
            v *= 10
        s["score"] = max(0, min(100, v))
        s.setdefault("grade",     _score_to_grade(s["score"]))
        s.setdefault("severity",  _score_to_severity(s["score"]))
        s.setdefault("reasoning", "")

    # ── summary ───────────────────────────────────────────────────────────────
    items  = data.get("feedback_items", [])
    high   = sum(1 for i in items if i.get("priority") == "high")
    medium = sum(1 for i in items if i.get("priority") == "medium")
    low    = sum(1 for i in items if i.get("priority") == "low")

    if isinstance(data.get("summary"), dict):
        data["summary"].update(
            total_issues=len(items), high=high, medium=medium, low=low
        )
        data["summary"].setdefault("estimated_total_effort", "N/A")
    elif isinstance(data.get("summary"), str) and data["summary"].strip():
        pass  # keep narrative; Flutter handles both
    else:
        data["summary"] = {
            "total_issues": len(items),
            "high": high, "medium": medium, "low": low,
            "estimated_total_effort": "N/A",
        }

    # strip unknown top-level keys
    for k in list(data.keys()):
        if k not in {"feedback_items", "ux_score", "summary"}:
            del data[k]

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

    if "summary" in feedback_data:
        s = feedback_data["summary"]
        if isinstance(s, dict):
            md += "## 📊 Summary\n\n"
            md += f"> 🔢 **{s.get('total_issues',0)} issues found** — "
            md += f"🔴 {s.get('high',0)} High · 🟡 {s.get('medium',0)} Medium · 🟢 {s.get('low',0)} Low\n"
            md += f"> ⏱ Estimated Effort: **{s.get('estimated_total_effort','N/A')}**\n\n---\n\n"
        elif isinstance(s, str) and s.strip():
            md += f"## 📊 Summary\n\n{s}\n\n---\n\n"

    if "ux_score" in feedback_data:
        sc = feedback_data["ux_score"]
        score = sc.get("score", 0)
        if isinstance(score, (int, float)) and score <= 10:
            score = int(score * 10)
        md += "## 🎯 Overall UX Score\n\n"
        md += f"> ### {score} / 100 — {str(sc.get('grade','N/A')).upper()}\n"
        md += f"> **Severity:** {sc.get('severity','N/A')}\n\n"
        if sc.get("reasoning"):
            md += f"{sc['reasoning']}\n\n"
        md += "---\n\n"

    items   = feedback_data.get("feedback_items", [])
    grouped: dict[str, list] = {"high": [], "medium": [], "low": []}
    for item in items:
        grouped.setdefault((item.get("priority") or "low").lower(), []).append(item)

    md += "## 🔧 Detailed Recommendations\n\n"
    for key, section_title, tag in [
        ("high",   "🔴 High Priority",   "HIGH"),
        ("medium", "🟡 Medium Priority", "MEDIUM"),
        ("low",    "🟢 Low Priority",    "LOW"),
    ]:
        bucket = grouped.get(key, [])
        if not bucket:
            continue
        md += f"### {section_title}\n\n"
        for item in bucket:
            steps = item.get("what_to_do", [])
            md += f"#### `[{tag}]` {item.get('title','Recommendation')}\n\n"
            md += f"> ⏱ Effort: **{item.get('effort_estimate','N/A')}**\n\n"
            md += f"**💬 Why it matters**\n\n{item.get('why_it_matters','N/A')}\n\n"
            md += "**🛠 Implementation Steps**\n\n"
            for i, step in enumerate(steps if isinstance(steps, list) else [steps], 1):
                md += f"{i}. {step}\n"
            wf = item.get("wireframe_changes") or "N/A"
            md += f"\n**✏️ Wireframe Changes**\n\n{wf}\n\n---\n\n"

    return md


# ─── Tool ─────────────────────────────────────────────────────────────────────

@tool("generate_feedback")
def generate_feedback(
    vision_analysis: str,
    heuristic_evaluation: str,
    evaluation_id: str = "",
) -> str:
    """
    Convert UX violations into developer-friendly feedback JSON and save report.
    Uses constrained decoding (response_schema) so the model output is always
    structurally valid — no key aliases, no rogue fields.

    Args:
        vision_analysis:      JSON string from vision tool.
        heuristic_evaluation: JSON string from heuristic tool.
        evaluation_id:        Optional ID used to name the saved files.

    Returns:
        Markdown string of the feedback report.
    """
    vision_analysis      = truncate_text(vision_analysis, 6000)
    heuristic_evaluation = truncate_text(heuristic_evaluation, 6000)

    # With response_schema active the prompt only needs to describe the TASK —
    # the schema enforces the output shape at the token level.
    prompt = f"""You are a senior UX engineer. Analyze the inputs below and produce a
structured UX feedback report.

VISION ANALYSIS:
{vision_analysis}

HEURISTIC EVALUATION:
{heuristic_evaluation}

Instructions:
- Identify every usability issue present in the inputs.
- For each issue create one feedback item with a clear action-oriented title.
- priority   → rate by user impact: high / medium / low.
- effort_estimate → implementation cost: low / medium / high.
- what_to_do → list of concrete, UI-specific steps. No generic phrases.
- wireframe_changes → exact visual change needed in the wireframe.
- ux_score.score → decimal 0–10 reflecting overall usability.
- summary counts must exactly match the feedback_items you produce.
"""

    model = GenerativeModel(model_name)
    response = None

    # ── Primary: constrained decoding ─────────────────────────────────────────
    try:
        response = model.generate_content(prompt, generation_config=GENERATION_CONFIG)
        print("[INFO] Used constrained decoding (response_schema)")
    except Exception as e:
        # Older or non-Gemini endpoints may not support response_schema.
        print(f"[WARN] response_schema unsupported ({e}), falling back to free-form...")

    # ── Fallback: free-form + normalization ────────────────────────────────────
    if response is None:
        # Append explicit schema instructions for the fallback path
        fallback_prompt = prompt + """
Return ONLY a valid JSON object. No markdown fences. No extra text.
Schema:
{
  "feedback_items": [{"title":"...","priority":"high|medium|low",
    "effort_estimate":"low|medium|high","why_it_matters":"...",
    "what_to_do":["step 1","step 2"],"wireframe_changes":"..."}],
  "ux_score": {"score": 7.5, "grade": "A|B|C|D|F"},
  "summary": {"total_issues":3,"high":1,"medium":1,"low":1,
               "estimated_total_effort":"low|medium|high"}
}
"""
        try:
            response = model.generate_content(
                fallback_prompt, generation_config=FALLBACK_CONFIG
            )
            print("[INFO] Used fallback free-form generation")
        except Exception as e2:
            return f"Error calling model: {e2}"

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

    # ── Normalize (always runs — safety net for fallback path) ────────────────
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