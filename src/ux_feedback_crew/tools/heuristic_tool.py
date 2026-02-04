from crewai.tools import tool
from google import genai
import json
import os
import re
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

OUTPUT_DIR = Path("data/outputs/current")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _extract_json(text: str) -> dict:
    """
    Extract the first valid JSON object from model output.
    """
    text = text.strip()

    if "```" in text:
        text = re.split(r"```(?:json)?", text)[1].strip()

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


@tool("evaluate_heuristics")
def evaluate_heuristics(vision_analysis: str) -> str:
    """
    Evaluate UI design against Nielsen's heuristics and return structured JSON.

    Args:
        vision_analysis: JSON string of vision analysis

    Returns:
        JSON string containing violations, strengths, and overall UX score.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set")

    client = genai.Client(api_key=api_key)

    heuristics_path = Path(__file__).parent.parent / "config" / "nielsen_heuristics.json"
    if heuristics_path.exists():
        heuristics_list = json.loads(heuristics_path.read_text()).get("heuristics", [])
    else:
        heuristics_list = []

    prompt = f"""
TASK: Evaluate this mobile UI against Nielsen's 10 Usability Heuristics and WCAG2 guidelines. 
Identify specific violations and strengths, and provide an overall UX score (1-10).

UI ANALYSIS:
{vision_analysis}

NIELSEN HEURISTICS:
{json.dumps(heuristics_list, indent=2)}

Return ONLY valid JSON:

{{
  "violations": [
    {{
      "heuristic_id": 1,
      "heuristic_name": "...",
      "severity": "high|medium|low",
      "issue": "...",
      "affected_components": ["..."],
      "improvement_suggestion": "...",
      "user_impact": "..."
    }}
  ],
  "strengths": [
    {{
      "heuristic_id": 4,
      "heuristic_name": "...",
      "observation": "...",
      "components": ["..."]
    }}
  ],
  "overall_score": 7.5,
  "summary": "..."
}}
"""

    last_error = None

    for _ in range(2):
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        raw = response.text.strip()

        try:
            parsed = _extract_json(raw)
            break
        except Exception as e:
            last_error = e
            print("⚠ Heuristic parsing failed — retrying once...")
    else:
        raise ValueError("Heuristic model did not return valid JSON")

    path = OUTPUT_DIR / "heuristics.json"
    path.write_text(json.dumps(parsed, indent=2, ensure_ascii=False))
    print(f"✓ Heuristics saved → {path}")

    return json.dumps(parsed)
