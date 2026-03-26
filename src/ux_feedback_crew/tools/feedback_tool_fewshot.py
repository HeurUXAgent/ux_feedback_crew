from crewai.tools import tool
from google import genai
import json
import os
import re
from pathlib import Path
from dotenv import load_dotenv
from src.utils.context_guard import truncate_text
from src.ux_feedback_crew.few_shot_examples import EXAMPLES

load_dotenv()

OUTPUT_DIR = Path("data/outputs")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

model_name = os.getenv("GEMINI_FEEDBACK_MODEL")


def _extract_json(text: str) -> dict:
    text = text.strip()

    # Remove markdown code fences safely
    text = re.sub(
        r"^```json\s*|^```\s*|```$",
        "",
        text.strip(),
        flags=re.IGNORECASE | re.MULTILINE,
    ).strip()

    # Try direct parse
    try:
        return json.loads(text)
    except Exception:
        pass

    # Fallback: extract first JSON object
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            pass

    raise ValueError("No valid JSON found in model output")


def _normalize_feedback(data: dict) -> dict:
    for item in data.get("feedback_items", []):
        alias_keys = (
            "actionable_steps",
            "how_to_fix",
            "action_steps",
            "technical_steps",
            "steps",
        )

        if "what_to_do" not in item:
            for alias in alias_keys:
                if alias in item:
                    item["what_to_do"] = item.pop(alias)
                    break

        if "what_to_do" in item and isinstance(item["what_to_do"], str):
            item["what_to_do"] = [item["what_to_do"]]

        if "what_to_do" not in item:
            item["what_to_do"] = []

        if "priority" not in item or not item["priority"]:
            item["priority"] = "low"
        else:
            item["priority"] = str(item["priority"]).lower().strip()

        if "effort_estimate" not in item or not item["effort_estimate"]:
            item["effort_estimate"] = "medium"

        if "why_it_matters" not in item:
            item["why_it_matters"] = item.pop("why", "") or ""

        if "wireframe_changes" not in item:
            item["wireframe_changes"] = ""

    items = data.get("feedback_items", [])
    high = sum(1 for i in items if i.get("priority") == "high")
    medium = sum(1 for i in items if i.get("priority") == "medium")
    low = sum(1 for i in items if i.get("priority") == "low")

    if "summary" not in data or not isinstance(data["summary"], dict):
        data["summary"] = {}

    data["summary"]["total_issues"] = len(items)
    data["summary"]["high"] = high
    data["summary"]["medium"] = medium
    data["summary"]["low"] = low

    if "ux_score" not in data or not isinstance(data["ux_score"], dict):
        data["ux_score"] = {
            "score": 0,
            "grade": "F"
        }

    return data


def convert_feedback_to_markdown(feedback_data: dict) -> str:
    md = "# 📋 UX Feedback Report\n\n---\n\n"

    if "summary" in feedback_data and isinstance(feedback_data["summary"], dict):
        s = feedback_data["summary"]
        md += "## 📊 Summary\n\n"
        md += f"> 🔢 **{s.get('total_issues', 0)} issues found** — "
        md += f"🔴 {s.get('high', 0)} High · "
        md += f"🟡 {s.get('medium', 0)} Medium · "
        md += f"🟢 {s.get('low', 0)} Low\n\n---\n\n"

    if "ux_score" in feedback_data and isinstance(feedback_data["ux_score"], dict):
        score = feedback_data["ux_score"].get("score", 0)
        grade = feedback_data["ux_score"].get("grade", "N/A")
        md += "## 🎯 Overall UX Score\n\n"
        md += f"> ### {score} / 10 — {grade}\n\n---\n\n"

    items = feedback_data.get("feedback_items", [])
    grouped = {"high": [], "medium": [], "low": []}
    for item in items:
        p = (item.get("priority") or "low").lower()
        grouped.setdefault(p, []).append(item)

    md += "## 🔧 Detailed Recommendations\n\n"

    for key, label in [
        ("high", "🔴 High Priority"),
        ("medium", "🟡 Medium Priority"),
        ("low", "🟢 Low Priority"),
    ]:
        bucket = grouped.get(key, [])
        if not bucket:
            continue

        md += f"### {label}\n\n"
        for item in bucket:
            md += f"#### {item.get('title', 'Recommendation')}\n\n"
            md += f"**Why it matters**\n\n{item.get('why_it_matters', '')}\n\n"
            md += f"**What to do**\n\n"

            steps = item.get("what_to_do", [])
            if isinstance(steps, list):
                for i, step in enumerate(steps, 1):
                    md += f"{i}. {step}\n"
            else:
                md += f"1. {steps}\n"

            md += f"\n**Wireframe changes**\n\n{item.get('wireframe_changes', '')}\n\n---\n\n"

    return md


def build_few_shot_prompt(vision_analysis: str, heuristic_evaluation: str) -> str:
    examples_block = ""

    for i, ex in enumerate(EXAMPLES, start=1):
        examples_block += f"""
=== EXAMPLE {i}: {ex["name"]} ===

VISION ANALYSIS:
{ex["vision_analysis"]}

HEURISTIC EVALUATION:
{ex["heuristic_evaluation"]}

EXPECTED JSON OUTPUT:
{ex["expected_output"]}

"""

    prompt = f"""
TASK: Convert UX violations into structured, developer-friendly UX feedback.

You are a senior UX feedback specialist.
Learn the expected structure, tone, severity logic, and recommendation style from the examples below.

{examples_block}

=== REAL INPUT ===

VISION ANALYSIS:
{vision_analysis}

HEURISTIC EVALUATION:
{heuristic_evaluation}

Return ONLY JSON in this exact structure:

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
    "score": 0,
    "grade": "A|B|C|D|F"
  }},
  "summary": {{
    "total_issues": 0,
    "high": 0,
    "medium": 0,
    "low": 0
  }}
}}

Rules:
1. Return valid JSON only.
2. Do not wrap JSON in markdown or code fences.
3. "what_to_do" must always be a list of strings.
4. Keep recommendations specific, practical, and UI-focused.
5. Base feedback only on the provided input.
6. Summary counts must exactly match feedback_items.
7. Keep UX score on a 0-10 scale.
"""
    return prompt.strip()


@tool("generate_feedback_fewshot")
def generate_feedback_fewshot(
    vision_analysis: str,
    heuristic_evaluation: str,
    evaluation_id: str = "") -> str:
    """
    Generate developer-friendly UX feedback using few-shot prompting.
    Returns markdown, and saves both JSON and markdown files.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set")

    client = genai.Client(api_key=api_key)

    vision_analysis = truncate_text(vision_analysis, 6000)
    heuristic_evaluation = truncate_text(heuristic_evaluation, 6000)

    prompt = build_few_shot_prompt(
        vision_analysis=vision_analysis,
        heuristic_evaluation=heuristic_evaluation,
    )

    last_error = None

    for _ in range(2):
        response = client.models.generate_content(
            model=model_name,
            contents=prompt
        )
        raw = response.text.strip()

        try:
            parsed = _extract_json(raw)
            break
        except Exception as e:
            last_error = e
            print("Feedback parsing failed — retrying once...")
    else:
        raise ValueError(f"Feedback model did not return valid JSON: {last_error}")

    parsed = _normalize_feedback(parsed)

    file_id = evaluation_id if evaluation_id else "fewshot_latest"

    json_path = OUTPUT_DIR / f"feedback_{file_id}.json"
    md_path = OUTPUT_DIR / f"feedback_{file_id}.md"

    json_path.write_text(json.dumps(parsed, indent=2, ensure_ascii=False), encoding="utf-8")

    md_content = convert_feedback_to_markdown(parsed)
    md_path.write_text(md_content, encoding="utf-8")

    print(f"✓ Few-shot feedback saved → {json_path}")
    print(f"✓ Few-shot markdown saved → {md_path}")

    return json.dumps(parsed)