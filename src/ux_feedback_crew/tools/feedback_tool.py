import os
import json
import re
import io
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from PIL import Image
from crewai.tools import tool

load_dotenv()

OUTPUT_DIR = Path("data/outputs/current")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# --- HELPER METHODS ---

def _extract_json(text: str) -> dict:
    """
    Extract the first valid JSON object from model output.
    Cleans markdown code blocks and whitespace.
    """
    text = text.strip()

    # removing markdown code fences if they exist
    # This regex looks for ```json ... ``` or just ``` ... ```
    if "```" in text:
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        if match:
            text = match.group(1).strip()

    #  Parse the cleaned text directly
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # If direct parse fails, try to find the first { and last }
        # This helps if there is stray conversational text before or after the JSON
        match = re.search(r"(\{[\s\S]*\})", text)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError as e:
                raise ValueError(f"Found JSON-like string but could not parse: {e}")
        
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

    Args:
        vision_analysis: JSON string from vision tool.
        heuristic_evaluation: JSON string from heuristic tool.

    Returns:
        JSON string containing structured feedback recommendations.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set")

    client = genai.Client(api_key=api_key)

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

    # Generate content
    response = client.models.generate_content(
        model="gemini-2.0-flash", # Note: Changed to 2.0 unless you have specific access to a 2.5/3.0 preview
        contents=prompt
    )
    
    raw_text = response.text.strip()
    
    # Extract and parse using the helper above
    try:
        parsed_data = _extract_json(raw_text)
    except Exception as e:
        print(f"❌ Error parsing feedback JSON: {e}")
        return f"Error: Could not parse JSON. Raw output: {raw_text[:200]}"

    # Save the files
    json_path = OUTPUT_DIR / "feedback.json"
    md_path = OUTPUT_DIR / "feedback.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(parsed_data, f, indent=2, ensure_ascii=False)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(convert_feedback_to_markdown(parsed_data))

    print(f"✓ Feedback saved successfully → {json_path}, {md_path}")

    # Return for the next agent
    return json.dumps(parsed_data)