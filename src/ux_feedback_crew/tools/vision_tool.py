from crewai.tools import tool
from google import genai
from dotenv import load_dotenv
from PIL import Image
from pathlib import Path
from datetime import datetime
import os
import io
import json

# Load environment variables at the top
load_dotenv()

@tool("analyze_ui_screenshot")
def analyze_ui_screenshot(image_path: str) -> str:
    """
    Analyzes a mobile UI screenshot and extracts detailed information about
    components, layout, colors, typography, and accessibility.

    Args:
        image_path: Path to the mobile UI screenshot to analyze

    Returns:
        JSON string with comprehensive UI analysis
    """

    # Configure Gemini client
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set in .env")
    client = genai.Client(api_key=api_key)

    # Validate image exists
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image not found: {image_path}")

    # Load image
    img = Image.open(image_path)

    # Enhanced prompt with stricter JSON requirements
    prompt = """
Analyze this mobile UI screenshot in extreme detail.

You MUST return ONLY valid JSON (no markdown, no code blocks, no explanations).

Required structure:

{
  "screen_type": "specific screen type (e.g., login, home, profile, product listing)",
  "app_category": "e.g., e-commerce, social media, productivity",
  "components": [
    {
      "type": "button/text_input/image/label/icon/card/list_item/header/footer/etc",
      "text": "exact visible text if any",
      "position": "top-left/top-center/top-right/middle/bottom/etc",
      "color": "describe color (hex if possible)",
      "size": "small/medium/large",
      "function": "what this component does"
    }
  ],
  "layout_structure": {
    "type": "single-column/multi-column/grid/list",
    "sections": ["header", "content", "footer"],
    "visual_hierarchy": "describe what draws attention first"
  },
  "color_scheme": {
    "primary_colors": ["list main brand colors"],
    "background": "background color description",
    "text_colors": ["dark text", "light text"],
    "accent_colors": ["highlight colors"]
  },
  "typography": {
    "heading_sizes": "describe heading sizes (e.g., large 24px, medium 18px)",
    "body_text_size": "describe body text size (e.g., 14-16px)",
    "font_weights": ["bold", "regular", "light"],
    "text_hierarchy": "describe how text creates hierarchy"
  },
  "spacing_and_density": {
    "overall_density": "tight/comfortable/spacious",
    "element_spacing": "small/medium/large gaps between elements",
    "padding": "describe padding around elements",
    "whitespace_usage": "minimal/balanced/generous"
  },
  "accessibility_observations": [
    "list specific accessibility issues like contrast, touch targets, labels"
  ],
  "notable_patterns": [
    "list UI patterns used (e.g., bottom navigation, cards, tabs)"
  ],
  "strengths": [
    "what this UI does well"
  ],
  "initial_concerns": [
    "obvious UX issues you notice"
  ]
}

Be extremely detailed. Count all components. Note every color. Describe exact positions.
Return ONLY the JSON object, nothing else.
"""

    print("🔍 Calling Gemini Vision for UI analysis...")
    
    # Gemini model call
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[
            prompt,
            img  # Pass PIL Image directly
        ]
    )

    # Extract text output
    result_text = response.text.strip()

    # Remove markdown code blocks if present
    if result_text.startswith("```json"):
        result_text = result_text[7:]
    elif result_text.startswith("```"):
        result_text = result_text[3:]
    if result_text.endswith("```"):
        result_text = result_text[:-3]

    result_text = result_text.strip()
    
    # Save to JSON file
    output_dir = Path("data/outputs")
    output_dir.mkdir(exist_ok=True, parents=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"vision_analysis_{timestamp}.json"
    
    try:
        # Parse to validate JSON and pretty print
        json_data = json.loads(result_text)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, indent=2, ensure_ascii=False)
        
        print(f"✓ Vision analysis saved: {output_path}")
        print(f"✓ Screen type: {json_data.get('screen_type', 'unknown')}")
        print(f"✓ Components found: {len(json_data.get('components', []))}")
        
    except json.JSONDecodeError as e:
        print(f"⚠ JSON validation error: {e}")
        # Save raw text anyway
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(result_text)
    
    return result_text