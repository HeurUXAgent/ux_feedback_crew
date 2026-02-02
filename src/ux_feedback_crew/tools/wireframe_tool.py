from crewai.tools import tool
from google import genai
import os
import webbrowser
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv


@tool("create_wireframe")
def create_wireframe(vision_analysis: str, feedback_result: str) -> str:
    """
    Generates improved UI wireframes in HTML/CSS based on feedback.
    Creates interactive, exportable designs showing improvements.
    
    Args:
        vision_analysis: JSON string of vision analysis
        feedback_result: JSON string of feedback
        
    Returns:
        String with path to generated wireframe file
    """
    
    load_dotenv()

    # Configure Gemini client
    api_key = os.getenv('GEMINI_API_KEY')
    client = genai.Client(api_key=api_key)
    
    prompt = f"""
You are an expert UI/UX designer. Create an IMPROVED mobile UI wireframe in HTML/CSS based on the original design analysis and feedback.

## ORIGINAL DESIGN ANALYSIS

Create a COMPLETE, IMPROVED mobile UI wireframe as a single HTML file with embedded CSS.

## ORIGINAL DESIGN:
{vision_analysis}

## IMPROVEMENTS TO IMPLEMENT:
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

## OUTPUT FORMAT

Return ONLY the HTML code inside a single code block, like this:
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Improved Mobile UI Wireframe</title>
    <style>
        /* Your CSS here */
    </style>
</head>
<body>
    <!-- Your improved UI here -->
</body>
</html>

Create a complete, functional wireframe that clearly shows the improvements.
Make it look professional and polished.
"""
    
    response = client.models.generate_content(
        model='gemini-3-flash-preview',
        contents=prompt
    )
    
    # Extract HTML
    html_code = response.text.strip()
    if "```html" in html_code:
        start = html_code.find("```html") + 7
        end = html_code.find("```", start)
        html_code = html_code[start:end].strip()
    
    # Save HTML
    output_dir = Path("data/outputs")
    output_dir.mkdir(exist_ok=True, parents=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"wireframe_{timestamp}.html"
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_code)
    
    # # Automatically open the HTML file in the default browser
    # try:
    #     webbrowser.open(f'file://{output_path.absolute()}')
    #     print(f"✓ Wireframe opened in browser: {output_path}")
    # except Exception as e:
    #     print(f"⚠ Could not auto-open browser: {e}")
    
    return html_code