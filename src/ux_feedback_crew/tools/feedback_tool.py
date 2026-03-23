import os
import json
import re
import io
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from PIL import Image
from crewai.tools import tool
from src.utils.context_guard import truncate_text

load_dotenv()

OUTPUT_DIR = Path("data/outputs")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
# model_name = "vertex_ai/projects/heuruxagent/locations/us-central1/endpoints/2041925583931179008"
model_name ="projects/75094798515/locations/us-central1/endpoints/6160467443161497600"
# model_name = os.getenv("GEMINI_FEEDBACK_MODEL")

import vertexai
from vertexai.generative_models import GenerativeModel


vertexai.init(
    project="heuruxagent",
    location="us-central1"
)

# --- HELPER METHODS ---

def _extract_json(text: str) -> dict:
    text = text.strip()

    # Remove markdown code fences safely
    text = re.sub(r"^```json\s*|^```\s*|```$", "", text.strip(), flags=re.IGNORECASE | re.MULTILINE).strip()

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


def convert_feedback_to_markdown(feedback_data: dict) -> str:
    """
    Converts the structured JSON feedback into a clean Markdown report.
    """
    md = "# 📋 UX Feedback Report\n\n---\n\n"

    if "summary" in feedback_data:
        s = feedback_data["summary"]
        md += f"## 📊 Summary\n"
        md += f"- **Total Issues:** {s.get('total_issues', 0)}\n"
        md += f"- **High Priority:** {s.get('high', 0)}\n"
        md += f"- **Medium Priority:** {s.get('medium', 0)}\n"
        md += f"- **Low Priority:** {s.get('low', 0)}\n"
        md += f"- **Estimated Effort:** {s.get('estimated_total_effort', 'N/A')}\n\n---\n\n"

    if feedback_data.get("quick_wins"):
        md += "## ⚡ Quick Wins\n\n"
        for w in feedback_data["quick_wins"]:
            md += f"- **{w.get('change', 'N/A')}** — {w.get('impact', 'N/A')} (Effort: {w.get('effort', 'N/A')})\n"
        md += "\n---\n\n"
    
    if "ux_score" in feedback_data:
        score = feedback_data["ux_score"]

        md += "## 🎯 Overall UX Score\n"
        md += f"- **Score:** {score.get('score', 'N/A')} / 100\n"
        md += f"- **Grade:** {score.get('grade', 'N/A')}\n"
        md += f"- **Severity Level:** {score.get('severity', 'N/A')}\n"
        md += f"- **Reason:** {score.get('reasoning', 'N/A')}\n\n---\n\n"

    md += "## 🔧 Detailed Recommendations\n\n"
    for item in feedback_data.get("feedback_items", []):
        md += f"### {item.get('title', 'Recommendation')}\n"
        md += f"**Priority:** {item.get('priority', 'N/A')} | **Effort:** {item.get('effort_estimate', 'N/A')}\n\n"
        md += f"**Why it matters:**\n{item.get('why_it_matters', 'N/A')}\n\n"
        md += "**Implementation Steps:**\n"
        steps = item.get('what_to_do', [])
        if isinstance(steps, list):
            for step in steps:
                md += f"- {step}\n"
        else:
            md += f"- {steps}\n"
        md += f"\n**Wireframe changes:** {item.get('wireframe_changes', 'N/A')}\n\n---\n\n"

    return md


@tool("generate_feedback")
def generate_feedback(vision_analysis: str, heuristic_evaluation: str) -> str:
    """
    Convert UX violations into developer-friendly feedback JSON and save report.
    Also estimate an overall UX score from 0–100 based on the severity and number of usability issues.

    Args:
        vision_analysis: JSON string from vision tool.
        heuristic_evaluation: JSON string from heuristic tool.

    Returns:
        JSON string containing structured feedback recommendations.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set")
    
    vision_analysis = truncate_text(vision_analysis, 6000)
    heuristic_evaluation = truncate_text(heuristic_evaluation, 6000)

    client = genai.Client(
        vertexai=True, 
        project="heuruxagent", # From your log: projects/heuruxagent
        location="us-central1"
    )

    prompt = f"""
TASK: Convert UX violations into developer-friendly feedback.

VISION ANALYSIS:
{vision_analysis}

HEURISTIC EVALUATION:
{heuristic_evaluation}

Return ONLY valid JSON in this structure:
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
    "total_issues": 10,
    "high": 2,
    "medium": 5,
    "low": 3,
    "estimated_total_effort": "Medium"
  }},
  "implementation_order": ["..."]
}}
"""
    
    print("=== FEEDBACK MODEL NAME ===", model_name)
    print("=== RAW FEEDBACK OUTPUT START ===")
    print(raw_text[:2000])
    print("=== RAW FEEDBACK OUTPUT END ===")

    # Generate content
    model = GenerativeModel(model_name)

    try:
        response = model.generate_content(
    prompt,
    generation_config={
        "max_output_tokens": 2048,
        "temperature": 0.2
    }
)
    except Exception as e:
        return json.dumps({"error": str(e)})
    
    raw_text = (response.text or "").strip()
    
    # Extract and parse using the helper above
    try:
        parsed_data = _extract_json(raw_text)
    except Exception as e:
        return json.dumps({"error": str(e)})

    raw_text = (response.text or "").strip()

    print("=== FEEDBACK MODEL NAME ===", model_name)
    print("=== RAW FEEDBACK OUTPUT START ===")
    print(raw_text[:2000])
    print("=== RAW FEEDBACK OUTPUT END ===")

    try:
        parsed_data = _extract_json(raw_text)
    except Exception as e:
        print(f"Error parsing feedback JSON: {e}")
        return f"Error: Could not parse JSON. Raw output: {raw_text[:200]}"

    json_path = OUTPUT_DIR / "feedback.json"
    md_path = OUTPUT_DIR / "feedback.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(parsed_data, f, indent=2, ensure_ascii=False)

    md_content = convert_feedback_to_markdown(parsed_data)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    print(f"✓ Feedback saved → {json_path}, {md_path}")

    return md_content 