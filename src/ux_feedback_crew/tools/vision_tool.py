from crewai.tools import tool
from google import genai
from dotenv import load_dotenv
from PIL import Image
from pathlib import Path
import os
import io
import json
import re
import requests

load_dotenv()

OUTPUT_DIR = Path("data/outputs")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _extract_json(text: str) -> dict:
    """
    Extract the first valid JSON object from model output.
    """
    text = text.strip()

    # Removing the code fences if present
    if "```" in text:
        text = re.split(r"```(?:json)?", text)[1].strip()

    # Try direct parse
    try:
        return json.loads(text)
    except Exception:
        pass

    # Try to find JSON substring
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            pass

    raise ValueError("No valid JSON found in model output")


@tool("analyze_ui_screenshot")
def analyze_ui_screenshot(image_path: str) -> str:
    """
    Analyze a mobile UI screenshot and extract structured UX information.

    Args:
        image_path: Path to the screenshot image file.

    Returns:
        JSON string describing UI components, layout, colors, typography, and UX patterns.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set in .env")

    client = genai.Client(api_key=api_key)

    # img = Image.open(image_path)
    # img_bytes = io.BytesIO()
    # img.save(img_bytes, format=img.format or "PNG")
    # 🔹 Support both local path and S3 URL
    if image_path.startswith("http"):
        response = requests.get(image_path)
        response.raise_for_status()
        img = Image.open(io.BytesIO(response.content))
    else:
        img = Image.open(image_path)

    img_bytes = io.BytesIO()
    img.save(img_bytes, format=img.format or "PNG")

    prompt = """
Analyze this mobile UI screenshot and extract detailed information.

Return ONLY valid JSON in this structure:

{
  "screen_type": "...",
  "components": [...],
  "layout_structure": "...",
  "color_scheme": {...},
  "typography": {...},
  "spacing_and_density": {...},
  "accessibility_observations": [...],
  "notable_patterns": [...]
}
"""

    last_error = None

    for attempt in range(2):  # 🔒 one retry for stability
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[prompt, img]
        )

        raw = response.text.strip()

        try:
            parsed = _extract_json(raw)
            break
        except Exception as e:
            last_error = e
            print("⚠ Vision output parsing failed — retrying once...")
    else:
        raise ValueError("Vision model did not return valid JSON after retry")

    path = OUTPUT_DIR / "vision.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(parsed, f, indent=2, ensure_ascii=False)

    print(f"✓ Vision analysis saved → {path}")
    return json.dumps(parsed)
