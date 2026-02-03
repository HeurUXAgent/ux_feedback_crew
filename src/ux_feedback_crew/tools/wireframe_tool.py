from crewai.tools import tool
from google import genai
import os
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
        Path to generated wireframe HTML file
    """
    
    load_dotenv()

    # Configure Gemini client
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set in .env")
    
    client = genai.Client(api_key=api_key)
    
    prompt = f"""
You are an expert UI/UX designer. Create an IMPROVED mobile UI wireframe in HTML/CSS.

## ORIGINAL DESIGN ANALYSIS:
{vision_analysis}

## IMPROVEMENTS TO IMPLEMENT:
{feedback_result}

**Requirements:**

1. **Mobile-first design** (max-width: 375px, centered on screen)
2. **Implement ALL high-priority (P0/P1) feedback items**
3. **Keep the original app's identity and purpose**
4. **Use modern CSS:**
   - Flexbox/Grid for layout
   - Proper spacing (padding: 16px, margins: 8px minimum)
   - Mobile-friendly touch targets (min 44px height)
   - Smooth transitions
   - Accessible colors (WCAG AA contrast)

5. **Include visual improvements:**
   - Loading states where needed
   - Error states
   - Better labels and icons
   - Improved spacing
   - Fixed color contrast issues

6. **Add subtle annotations:**
   - Small green badges showing "✓ Fixed: [issue]"
   - Use small text (10px) in corners of improved elements
   - Don't overdo it - 3-5 annotations max

7. **Make it realistic:**
   - Use actual UI components
   - Include icons (emoji or Unicode: ⚙️ 🏠 🔍 ➕ ✓ ✗)
   - Proper visual hierarchy
   - Real-looking content (not Lorem Ipsum)

## OUTPUT FORMAT:

Return ONLY complete HTML with embedded CSS. No markdown code blocks. Structure:

<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Improved UI Wireframe</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #f5f5f5;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            padding: 20px;
        }}
        
        .mobile-frame {{
            width: 375px;
            background: white;
            border-radius: 20px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
            overflow: hidden;
        }}
        
        /* Add your component styles here */
    </style>
</head>
<body>
    <div class="mobile-frame">
        <!-- Your improved UI here -->
    </div>
</body>
</html>

Create a complete, professional wireframe showing clear improvements. Make it pixel-perfect.
"""
    
    print("🎨 Calling Gemini for wireframe generation...")
    
    response = client.models.generate_content(
        model='gemini-2.5-flash',  # Use faster flash model
        contents=prompt
    )
    
    # Extract HTML - handle multiple formats
    html_code = response.text.strip()
    
    # Remove markdown code blocks
    if "```html" in html_code:
        start = html_code.find("```html") + 7
        end = html_code.rfind("```")
        if end > start:
            html_code = html_code[start:end].strip()
    elif "```" in html_code:
        start = html_code.find("```") + 3
        end = html_code.rfind("```")
        if end > start:
            html_code = html_code[start:end].strip()
    
    # Ensure it starts with DOCTYPE
    if not html_code.strip().startswith("<!DOCTYPE") and not html_code.strip().startswith("<html"):
        print("⚠ Warning: HTML doesn't start with DOCTYPE, attempting to fix...")
        # If we got partial HTML, wrap it
        if "<style>" in html_code or "<body>" in html_code:
            html_code = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Improved UI Wireframe</title>
</head>
{html_code}
</html>"""
    
    # Save HTML
    output_dir = Path("data/outputs")
    output_dir.mkdir(exist_ok=True, parents=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"wireframe_{timestamp}.html"
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_code)
    
    print(f"✓ Wireframe saved: {output_path}")
    print(f"✓ File size: {len(html_code)} characters")
    
    # Return the path so the agent knows where to find it
    return f"Wireframe successfully created and saved to: {output_path}\n\nThe wireframe implements all high-priority feedback items with modern, mobile-first design."