from crewai.tools import tool
from google import genai
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

OUTPUT_DIR = Path("data/outputs/current")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

@tool("create_wireframe")
def create_wireframe(vision_analysis: str, feedback_result: str) -> str:
    """
    Generate an improved UI wireframe based on UX feedback.

    Args:
        vision_analysis: JSON string from vision tool.
        feedback_result: JSON string from feedback tool.

    Returns:
        HTML string representing the improved UI wireframe.
    """
    if not feedback_result or len(feedback_result.strip()) < 50:
        raise ValueError("Wireframe generation blocked — feedback missing or invalid")

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set")

    client = genai.Client(api_key=api_key)

    prompt = f"""
You are an expert UI/UX designer.

ORIGINAL DESIGN:
{vision_analysis}

IMPROVEMENTS TO IMPLEMENT:
{feedback_result}

**Requirements:**

1. **Mobile-first design** (max-width: 375px, scale up for display)
2. **Implement ALL feedback suggestions:**
   - Fix color contrast issues
   - Adjust typography sizes
   - Improve spacing and layout
   - Add missing UI elements (loading indicators, labels, etc.)
   - Fix inconsistencies

3. **Use modern CSS:**
   - Flexbox/Grid for layout
   - Proper spacing (padding, margins)
   - Mobile-friendly touch targets (min 44px)
   - Smooth transitions and hover states

4. **Include annotations:**
   - Add small labels showing what was improved
   - Use a subtle annotation style (small text, muted color)

5. **Make it realistic but clean:**
   - Use actual UI components (buttons, cards, inputs)
   - Include icons (use emoji or Unicode symbols)
   - Proper visual hierarchy

Return ONLY a single HTML document (no markdown).
"""

    response = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents=prompt
    )

    html = response.text.strip()
    if "```" in html:
        html = html.split("```")[1].strip()

    path = OUTPUT_DIR / "wireframe.html"
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"✓ Wireframe saved → {path}")
    return html
