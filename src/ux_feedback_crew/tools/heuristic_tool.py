from crewai.tools import tool
from google import genai
import json
import os
import re
from pathlib import Path
from dotenv import load_dotenv
from src.utils.context_guard import compress_vision, compress_heuristics, truncate_text

load_dotenv()

OUTPUT_DIR = Path("data/outputs")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
model_name = os.getenv("GEMINI_HEURISTIC_MODEL")


def _extract_json(text: str) -> dict:
    text = text.strip()

    text = re.sub(r"^```json\s*|^```\s*|```$", "", text.strip(), flags=re.IGNORECASE | re.MULTILINE).strip()

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

    # compress vision input
    vision_data = json.loads(vision_analysis)
    vision_data = compress_vision(vision_data)
    vision_analysis = truncate_text(json.dumps(vision_data), 6000)

    heuristics_path = Path(__file__).parent.parent / "config" / "nielsen_heuristics.json"
    if heuristics_path.exists():
        heuristics_list = json.loads(heuristics_path.read_text()).get("heuristics", [])
    else:
        heuristics_list = []

    prompt = f"""
TASK: Evaluate this mobile UI against Nielsen's 10 Usability Heuristics

UI ANALYSIS:
{vision_analysis}

HEURISTICS:
{json.dumps(heuristics_list)}

Return ONLY JSON:

{{
  "violations":[{{}}],
  "strengths":[{{}}],
  "overall_score":0,
  "summary":""
}}
"""

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
            print("⚠ Heuristic parsing failed — retrying once...")
    else:
        raise ValueError("Heuristic model did not return valid JSON")

    path = OUTPUT_DIR / "heuristics.json"
    path.write_text(json.dumps(parsed, indent=2, ensure_ascii=False))
    print(f"✓ Heuristics saved → {path}")

    return json.dumps(parsed)
