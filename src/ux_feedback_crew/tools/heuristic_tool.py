from crewai.tools import tool
from google import genai
from google.genai.types import GenerateContentConfig
import json
import os
from pathlib import Path
from dotenv import load_dotenv
from src.utils.context_guard import compress_vision, truncate_text

load_dotenv()

OUTPUT_DIR = Path("data/outputs")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

model_name = os.getenv("GEMINI_HEURISTIC_MODEL")

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY not set")

client = genai.Client(api_key=api_key)

HEURISTIC_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "violations": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "heuristic_id": {"type": "INTEGER"},
                    "name": {"type": "STRING"},
                    "observation": {"type": "STRING"},
                },
                "required": ["heuristic_id", "name", "observation"],
            },
        },
        "strengths": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "heuristic_id": {"type": "INTEGER"},
                    "name": {"type": "STRING"},
                    "observation": {"type": "STRING"},
                },
                "required": ["heuristic_id", "name", "observation"],
            },
        },
        "overall_score": {"type": "NUMBER"},
        "summary": {"type": "STRING"},
    },
    "required": ["violations", "strengths", "overall_score", "summary"],
}


@tool("evaluate_heuristics")
def evaluate_heuristics(vision_analysis: str) -> str:
    """
    Evaluate UI design against Nielsen's heuristics and return structured JSON.

    Args:
        vision_analysis: JSON string of vision analysis.

    Returns:
        JSON string containing violations, strengths, overall UX score, and summary.
    """
    vision_data = json.loads(vision_analysis)
    vision_data = compress_vision(vision_data)
    vision_analysis = truncate_text(json.dumps(vision_data, ensure_ascii=False), 3500)

    heuristics_path = Path(__file__).parent.parent / "config" / "nielsen_heuristics.json"
    if heuristics_path.exists():
        heuristics_list = json.loads(heuristics_path.read_text(encoding="utf-8")).get("heuristics", [])
    else:
        heuristics_list = []

    prompt = f"""
TASK: Evaluate this mobile UI against Nielsen's 10 Usability Heuristics.

UI ANALYSIS:
{vision_analysis}

HEURISTICS:
{json.dumps(heuristics_list, ensure_ascii=False)}

Rules:
- Focus only on meaningful issues and strengths.
- Keep observations concise.
- overall_score must be from 0 to 100.
- Return only JSON.
"""

    try:
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=HEURISTIC_SCHEMA,
                max_output_tokens=1600,
                temperature=0.1,
            ),
        )
        raw_text = (response.text or "").strip()
        parsed = json.loads(raw_text)
    except Exception as e:
        raise ValueError(f"Heuristic model did not return valid structured JSON: {e}")

    path = OUTPUT_DIR / "heuristics.json"
    path.write_text(json.dumps(parsed, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"✓ Heuristics saved → {path}")

    return json.dumps(parsed, ensure_ascii=False)