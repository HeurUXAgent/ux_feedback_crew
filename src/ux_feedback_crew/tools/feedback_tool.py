import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from crewai.tools import tool
import vertexai
from vertexai.generative_models import GenerativeModel

from src.utils.context_guard import truncate_text

load_dotenv()

# -----------------------------
# Config
# -----------------------------
PROJECT_ID = os.getenv("VERTEX_PROJECT_ID", "heuruxagent")
LOCATION = os.getenv("VERTEX_LOCATION", "us-central1")
MODEL_NAME = os.getenv(
    "GEMINI_FEEDBACK_MODEL",
    "projects/75094798515/locations/us-central1/endpoints/3613259641418416128",
)

OUTPUT_DIR = Path("data/outputs")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

vertexai.init(project=PROJECT_ID, location=LOCATION)


# -----------------------------
# Helpers: cleaning / extraction
# -----------------------------
def _strip_code_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```json\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^```\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _clean_raw_output(text: str) -> str:
    """
    Removes common Crew/agent wrappers and code fences.
    """
    text = (text or "").strip()
    text = _strip_code_fences(text)

    # Remove leading "Agent: ..."
    text = re.sub(r"^\s*Agent:\s.*?\n", "", text, flags=re.IGNORECASE)

    # If model/agent wrapped JSON after "Final Answer:", keep only that part
    if "Final Answer:" in text:
        text = text.split("Final Answer:", 1)[1].strip()

    return text.strip()


def _extract_first_balanced_json_object(text: str) -> dict:
    """
    Extract the first balanced JSON object from a string.
    Safer than greedy regex.
    """
    text = _clean_raw_output(text)

    # First try direct parse
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    start = text.find("{")
    if start == -1:
        raise ValueError("No JSON object start found")

    depth = 0
    in_string = False
    escape = False

    for i in range(start, len(text)):
        ch = text[i]

        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = text[start : i + 1]
                data = json.loads(candidate)
                if isinstance(data, dict):
                    return data
                raise ValueError("Balanced JSON candidate is not an object")

    raise ValueError("No balanced JSON object found")


def _extract_json(text: str) -> dict:
    return _extract_first_balanced_json_object(text)


# -----------------------------
# Helpers: scoring / buckets
# -----------------------------
def _normalize_priority(value) -> str:
    if not value:
        return "low"
    p = str(value).strip().lower()
    if p in {"critical", "urgent"}:
        return "high"
    if p in {"high", "medium", "low"}:
        return p
    return "low"


def _normalize_effort(value) -> str:
    if not value:
        return "N/A"
    v = str(value).strip().lower()
    if v in {"small", "easy", "quick"}:
        return "low"
    if v in {"moderate", " متوسط", "average"}:
        return "medium"
    if v in {"complex", "hard", "large"}:
        return "high"
    return str(value).strip()


def _score_to_grade_100(score: int) -> str:
    if score >= 85:
        return "excellent"
    if score >= 70:
        return "good"
    if score >= 50:
        return "average"
    return "poor"


def _score_to_severity_100(score: int) -> str:
    if score >= 75:
        return "low"
    if score >= 50:
        return "moderate"
    return "high"


def _normalize_score(raw_score) -> int:
    """
    Returns score on 0-100 scale.
    Accepts 0-10 or 0-100.
    """
    if raw_score is None:
        return 0

    try:
        score = float(raw_score)
    except Exception:
        return 0

    if score <= 10:
        score *= 10

    score = int(round(score))
    return max(0, min(score, 100))


def _ensure_list_of_strings(value) -> list[str]:
    if value is None:
        return []

    if isinstance(value, str):
        s = value.strip()
        return [s] if s else []

    if isinstance(value, list):
        out = []
        for item in value:
            if item is None:
                continue
            txt = str(item).strip()
            if txt:
                out.append(txt)
        return out

    txt = str(value).strip()
    return [txt] if txt else []


# -----------------------------
# Normalization
# -----------------------------
def _normalize_feedback(data: dict) -> dict:
    raw_items = data.get("feedback_items", [])
    if not isinstance(raw_items, list):
        raw_items = []

    normalized_items = []

    for item in raw_items:
        if not isinstance(item, dict):
            continue

        title = str(item.get("title") or "Recommendation").strip()

        priority = _normalize_priority(
            item.get("priority")
            or item.get("severity_level")
            or item.get("impact")
        )

        effort = _normalize_effort(
            item.get("effort_estimate")
            or item.get("effort")
            or item.get("implementation_effort")
            or item.get("severity")
            or "N/A"
        )

        why_it_matters = (
            item.get("why_it_matters")
            or item.get("description")
            or item.get("issue")
            or item.get("problem")
            or item.get("why")
            or ""
        )
        why_it_matters = str(why_it_matters).strip()

        what_to_do = (
            item.get("what_to_do")
            or item.get("developer_steps")
            or item.get("recommendations")
            or item.get("technical_solution")
            or item.get("actionable_steps")
            or item.get("how_to_fix")
            or item.get("action_steps")
            or item.get("technical_steps")
            or item.get("steps")
            or []
        )
        what_to_do = _ensure_list_of_strings(what_to_do)

        wireframe_changes = (
            item.get("wireframe_changes")
            or item.get("component")
            or item.get("affected_component")
            or item.get("ui_element")
            or item.get("technical_solution")
            or None
        )
        if wireframe_changes is not None:
            wireframe_changes = str(wireframe_changes).strip() or None

        normalized_items.append(
            {
                "title": title,
                "priority": priority,
                "effort_estimate": effort,
                "why_it_matters": why_it_matters,
                "what_to_do": what_to_do,
                "wireframe_changes": wireframe_changes,
            }
        )

    # ---- score normalization ----
    score_value = None
    summary_reasoning = ""

    if isinstance(data.get("ux_score"), dict):
        ux_score_obj = data["ux_score"]
        score_value = ux_score_obj.get("score")
        summary_reasoning = str(
            ux_score_obj.get("reasoning")
            or ux_score_obj.get("summary")
            or ""
        ).strip()
    elif data.get("ux_score") is not None:
        score_value = data.get("ux_score")
    elif data.get("overall_ux_score") is not None:
        score_value = data.get("overall_ux_score")

    score_100 = _normalize_score(score_value)

    if not summary_reasoning:
        if isinstance(data.get("summary"), str):
            summary_reasoning = data.get("summary", "").strip()
        elif isinstance(data.get("overall_summary"), str):
            summary_reasoning = data.get("overall_summary", "").strip()

    ux_score = {
        "score": score_100,
        "grade": _score_to_grade_100(score_100),
        "severity": _score_to_severity_100(score_100),
        "reasoning": summary_reasoning,
    }

    # ---- summary normalization ----
    high = sum(1 for i in normalized_items if i["priority"] == "high")
    medium = sum(1 for i in normalized_items if i["priority"] == "medium")
    low = sum(1 for i in normalized_items if i["priority"] == "low")

    summary = data.get("summary")
    if isinstance(summary, dict):
        normalized_summary = {
            "total_issues": len(normalized_items),
            "high": high,
            "medium": medium,
            "low": low,
            "estimated_total_effort": str(
                summary.get("estimated_total_effort", "N/A")
            ),
        }
    else:
        normalized_summary = {
            "total_issues": len(normalized_items),
            "high": high,
            "medium": medium,
            "low": low,
            "estimated_total_effort": "N/A",
        }

    normalized = {
        "feedback_items": normalized_items,
        "ux_score": ux_score,
        "summary": normalized_summary,
    }

    return normalized


# -----------------------------
# Markdown conversion
# -----------------------------
def convert_feedback_to_markdown(feedback_data: dict) -> str:
    md = "# 📋 UX Feedback Report\n\n---\n\n"

    summary = feedback_data.get("summary", {})
    if isinstance(summary, dict):
        total = summary.get("total_issues", 0)
        high = summary.get("high", 0)
        med = summary.get("medium", 0)
        low = summary.get("low", 0)
        effort = summary.get("estimated_total_effort", "N/A")

        md += "## 📊 Summary\n\n"
        md += f"> 🔢 **{total} issues found** — 🔴 {high} High · 🟡 {med} Medium · 🟢 {low} Low\n"
        md += f"> ⏱ Estimated Effort: **{effort}**\n\n---\n\n"

    ux_score = feedback_data.get("ux_score", {})
    if isinstance(ux_score, dict):
        score = ux_score.get("score", 0)
        grade = str(ux_score.get("grade", "N/A")).upper()
        severity = ux_score.get("severity", "N/A")
        reasoning = ux_score.get("reasoning", "")

        md += "## 🎯 Overall UX Score\n\n"
        md += f"> ### {score} / 100 — {grade}\n"
        md += f"> **Severity:** {severity}\n\n"
        if reasoning:
            md += f"{reasoning}\n\n"
        md += "---\n\n"

    items = feedback_data.get("feedback_items", [])
    grouped = {"high": [], "medium": [], "low": []}
    for item in items:
        grouped.setdefault(item.get("priority", "low"), []).append(item)

    md += "## 🔧 Detailed Recommendations\n\n"

    sections = [
        ("high", "🔴 High Priority", "HIGH"),
        ("medium", "🟡 Medium Priority", "MEDIUM"),
        ("low", "🟢 Low Priority", "LOW"),
    ]

    for key, heading, tag in sections:
        bucket = grouped.get(key, [])
        if not bucket:
            continue

        md += f"### {heading}\n\n"
        for item in bucket:
            title = item.get("title", "Recommendation")
            effort = item.get("effort_estimate", "N/A")
            why = item.get("why_it_matters", "")
            steps = item.get("what_to_do", [])
            wf = item.get("wireframe_changes") or "N/A"

            md += f"#### `[{tag}]` {title}\n\n"
            md += f"> ⏱ Effort: **{effort}**\n\n"

            if why:
                md += f"**💬 Why it matters**\n\n{why}\n\n"

            md += "**🛠 Implementation Steps**\n\n"
            if steps:
                for i, step in enumerate(steps, 1):
                    md += f"{i}. {step}\n"
            else:
                md += "1. No implementation steps provided.\n"

            md += f"\n**✏️ Wireframe Changes**\n\n{wf}\n\n---\n\n"

    return md


# -----------------------------
# Prompt
# -----------------------------
def _build_prompt(vision_analysis: str, heuristic_evaluation: str) -> str:
    return f"""
TASK: Convert the UX evaluation into a structured developer-friendly feedback report.

You are a senior UX expert and frontend implementation advisor.

VISION ANALYSIS:
{vision_analysis}

HEURISTIC EVALUATION:
{heuristic_evaluation}

Return ONLY valid JSON.
Do NOT include markdown.
Do NOT include code fences.
Do NOT include explanations.
Do NOT include 'Agent:' or 'Final Answer:'.
Do NOT include any text before or after the JSON.

Use EXACTLY this structure:

{{
  "feedback_items": [
    {{
      "title": "Short issue title",
      "priority": "high|medium|low",
      "effort_estimate": "low|medium|high",
      "why_it_matters": "Why this issue matters to UX",
      "what_to_do": [
        "Concrete implementation step 1",
        "Concrete implementation step 2"
      ],
      "wireframe_changes": "Short note about what should visually change"
    }}
  ],
  "ux_score": {{
    "score": 7.5,
    "grade": "A|B|C|D|F"
  }},
  "summary": {{
    "total_issues": 3,
    "high": 1,
    "medium": 1,
    "low": 1
  }}
}}

STRICT RULES:
1. feedback_items must be an array
2. what_to_do must always be an array of strings
3. score must be between 0 and 10
4. keep recommendations practical and implementation-oriented
5. summary counts must match the number of feedback_items exactly
6. use only the keys shown above
7. return JSON only
""".strip()


# -----------------------------
# Tool
# -----------------------------
@tool("generate_feedback")
def generate_feedback(
    vision_analysis: str,
    heuristic_evaluation: str,
    evaluation_id: str = "",
) -> str:
    """
    Generate developer-friendly structured UX feedback.

    Returns:
        A normalized JSON string only.
    """
    vision_analysis = truncate_text(vision_analysis or "", 6000)
    heuristic_evaluation = truncate_text(heuristic_evaluation or "", 6000)

    prompt = _build_prompt(vision_analysis, heuristic_evaluation)
    model = GenerativeModel(MODEL_NAME)

    try:
        response = model.generate_content(
            prompt,
            generation_config={
                "max_output_tokens": 2048,
                "temperature": 0.1,
            },
        )
    except Exception as e:
        raise RuntimeError(f"Error calling feedback model: {e}") from e

    raw_text = (response.text or "").strip()

    print("=== FEEDBACK MODEL ===")
    print(MODEL_NAME)
    print("=== RAW FEEDBACK OUTPUT (first 1500 chars) ===")
    print(raw_text[:1500])

    try:
        parsed_data = _extract_json(raw_text)
        normalized_data = _normalize_feedback(parsed_data)
    except Exception as e:
        print("=== FAILED RAW OUTPUT ===")
        print(raw_text[:3000])
        raise ValueError(f"Could not parse/normalize feedback JSON: {e}") from e

    print("=== NORMALIZED FEEDBACK OUTPUT (first 1500 chars) ===")
    print(json.dumps(normalized_data, indent=2, ensure_ascii=False)[:1500])

    file_id = evaluation_id if evaluation_id else "latest"

    json_path = OUTPUT_DIR / f"feedback_{file_id}.json"
    md_path = OUTPUT_DIR / f"feedback_{file_id}.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(normalized_data, f, indent=2, ensure_ascii=False)

    markdown = convert_feedback_to_markdown(normalized_data)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(markdown)

    print(f"✓ Saved normalized feedback JSON to: {json_path}")
    print(f"✓ Saved feedback markdown to: {md_path}")

    # IMPORTANT: always return JSON string only
    return json.dumps(normalized_data, ensure_ascii=False)