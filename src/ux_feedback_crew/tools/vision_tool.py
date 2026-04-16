from crewai.tools import tool
from google import genai
from google.genai.types import GenerateContentConfig
from dotenv import load_dotenv
from PIL import Image
from pathlib import Path
import os
import io
import json
import requests

load_dotenv()

OUTPUT_DIR = Path("data/outputs")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

model_name = os.getenv("GEMINI_VISION_MODEL")

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY not set in .env")

client = genai.Client(api_key=api_key)

VISION_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "screen_type": {"type": "STRING"},
        "components": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "name": {"type": "STRING"},
                    "type": {"type": "STRING"},
                    "details": {"type": "STRING"},
                },
                "required": ["name", "type", "details"],
            },
        },
        "layout_structure": {"type": "STRING"},
        "color_scheme": {
            "type": "OBJECT",
            "properties": {
                "primary_colors": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                },
                "secondary_colors": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                },
            },
            "required": ["primary_colors", "secondary_colors"],
        },
        "typography": {"type": "STRING"},
        "spacing_and_density": {"type": "STRING"},
        "accessibility_observations": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
        },
        "notable_patterns": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
        },
    },
    "required": [
        "screen_type",
        "components",
        "layout_structure",
        "color_scheme",
        "typography",
        "spacing_and_density",
        "accessibility_observations",
        "notable_patterns",
    ],
}


@tool("analyze_ui_screenshot")
def analyze_ui_screenshot(image_path: str) -> str:
    """
    Analyze a mobile UI screenshot and extract structured UX information.

    Args:
        image_path: Path or URL to the screenshot image.

    Returns:
        JSON string describing UI structure and UX-relevant observations.
    """
    if image_path.startswith("http"):
        response = requests.get(image_path, timeout=30)
        response.raise_for_status()
        img = Image.open(io.BytesIO(response.content))
    else:
        img = Image.open(image_path)

    prompt = """
Analyze this mobile UI screenshot and return a concise structured JSON description.

Rules:
- Be concise but useful for heuristic evaluation.
- Include only major UI components, not every tiny icon unless important.
- Keep component details short.
- Return only JSON.
"""

    raw_text = ""
    try:
        response = client.models.generate_content(
            model=model_name,
            contents=[prompt, img],
            config=GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=VISION_SCHEMA,
                max_output_tokens=1800,
                temperature=0.1,
            ),
        )
        raw_text = (response.text or "").strip()
        parsed = json.loads(raw_text)
    except Exception as e:
        raise ValueError(f"Vision model did not return valid structured JSON: {e}")

    path = OUTPUT_DIR / "vision.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(parsed, f, indent=2, ensure_ascii=False)

    print(f"✓ Vision analysis saved → {path}")
    return json.dumps(parsed, ensure_ascii=False)