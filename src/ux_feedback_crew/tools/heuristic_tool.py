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


from google.genai import types # Add this import at the top

@tool("evaluate_heuristics")
def evaluate_heuristics(vision_analysis: str) -> str:
    """
    Evaluate UI design against Nielsen's heuristics and return structured JSON.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set")

    client = genai.Client(api_key=api_key)

    # Normalize input
    try:
        if isinstance(vision_analysis, str):
            vision_data = json.loads(vision_analysis)
        else:
            vision_data = vision_analysis
    except Exception as e:
        return json.dumps({"error": f"Invalid vision_analysis input: {str(e)}"})

    # Compress vision input
    vision_data = compress_vision(vision_data)
    vision_str = truncate_text(json.dumps(vision_data), 6000)

    heuristics_path = Path(__file__).parent.parent / "config" / "nielsen_heuristics.json"
    heuristics_list = json.loads(heuristics_path.read_text()).get("heuristics", []) if heuristics_path.exists() else []

    prompt = f"""
    TASK: Evaluate this mobile UI against Nielsen's 10 Usability Heuristics
    UI ANALYSIS: {vision_str}
    HEURISTICS: {json.dumps(heuristics_list)}

    Return ONLY JSON in this format:
    {{
      "violations":[],
      "strengths":[],
      "overall_score":0,
      "summary":""
    }}
    """

    parsed = None
    # Correcting the generate_content call for the Google GenAI SDK
    for _ in range(2):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig( # Correct way to pass config in new SDK
                    max_output_tokens=1500,
                    temperature=0.2,
                    response_mime_type="application/json" # Forces JSON output
                )
            )
            raw = response.text.strip()
            parsed = _extract_json(raw)
            break
        except Exception as e:
            print(f"⚠ Heuristic attempt failed: {e}")
            continue

    if not parsed:
        return json.dumps({"error": "Model failed to return valid JSON after retries."})

    compressed = compress_heuristics(parsed)
    path = OUTPUT_DIR / "heuristics.json"
    path.write_text(json.dumps(compressed, indent=2, ensure_ascii=False))

    return json.dumps(compressed)
