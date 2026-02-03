from crewai.tools import tool
from google import genai
import json
import os
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv


@tool("evaluate_heuristics")
def evaluate_heuristics(vision_analysis: str) -> str:
    """
    Evaluates UI designs against Nielsen's 10 Usability Heuristics using Gemini.
    
    Args:
        vision_analysis: JSON string of vision analysis results
        
    Returns:
        JSON string with violations, severity scores, and overall UX score
    """
    
    load_dotenv()
    
    # Configure Gemini
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set in .env")
    
    client = genai.Client(api_key=api_key)
    
    # Heuristics knowledge base
    heuristics_list = [
        {
            "id": 1,
            "name": "Visibility of system status",
            "description": "The design should always keep users informed about what is going on, through appropriate feedback within a reasonable amount of time.",
            "mobile_considerations": "Loading indicators, progress bars, active state indicators"
        },
        {
            "id": 2,
            "name": "Match between system and the real world",
            "description": "The design should speak the users' language. Use words, phrases, and concepts familiar to the user.",
            "mobile_considerations": "Familiar icons, natural language, platform conventions"
        },
        {
            "id": 3,
            "name": "User control and freedom",
            "description": "Users need a clearly marked 'emergency exit' to leave unwanted actions without going through an extended process.",
            "mobile_considerations": "Back buttons, cancel options, undo/redo, swipe gestures"
        },
        {
            "id": 4,
            "name": "Consistency and standards",
            "description": "Users should not have to wonder whether different words, situations, or actions mean the same thing.",
            "mobile_considerations": "Platform design guidelines (iOS/Android), consistent navigation patterns"
        },
        {
            "id": 5,
            "name": "Error prevention",
            "description": "Good error messages are important, but preventing problems from occurring is even better.",
            "mobile_considerations": "Input validation, confirmation dialogs, constraints, helpful defaults"
        },
        {
            "id": 6,
            "name": "Recognition rather than recall",
            "description": "Minimize the user's memory load by making elements, actions, and options visible.",
            "mobile_considerations": "Visible navigation, clear labels, search history, recent items"
        },
        {
            "id": 7,
            "name": "Flexibility and efficiency of use",
            "description": "Shortcuts and accelerators may speed up interaction for expert users.",
            "mobile_considerations": "Gestures, quick actions, shortcuts, personalization"
        },
        {
            "id": 8,
            "name": "Aesthetic and minimalist design",
            "description": "Interfaces should not contain information that is irrelevant or rarely needed.",
            "mobile_considerations": "Progressive disclosure, prioritized content, clean layouts"
        },
        {
            "id": 9,
            "name": "Help users recognize, diagnose, and recover from errors",
            "description": "Error messages should be expressed in plain language, precisely indicate the problem, and constructively suggest a solution.",
            "mobile_considerations": "Clear error messages, inline validation, recovery options"
        },
        {
            "id": 10,
            "name": "Help and documentation",
            "description": "It's best if the system doesn't need additional explanation. However, it may be necessary to provide documentation.",
            "mobile_considerations": "Onboarding, tooltips, contextual help, FAQs"
        }
    ]
    
    # Create evaluation prompt
    evaluation_prompt = f"""
You are a UX expert evaluating a mobile UI against Nielsen's 10 Usability Heuristics.

UI ANALYSIS TO EVALUATE:
{vision_analysis}

NIELSEN'S 10 USABILITY HEURISTICS:
{json.dumps(heuristics_list, indent=2)}

TASK: Carefully evaluate the UI and identify ALL violations.

For each violation:
1. Identify which heuristic (1-10) is violated
2. Assign severity: critical/high/medium/low
3. Describe the specific issue clearly
4. List affected UI components
5. Provide concrete improvement suggestions

Also identify 3-5 STRENGTHS (what the UI does well).

Calculate an overall UX score (0-100):
- Start at 100
- Deduct points: critical (-20), high (-10), medium (-5), low (-2)
- Add points for strengths (+5 each)

Return ONLY valid JSON (no markdown, no code blocks):

{{
  "violations": [
    {{
      "heuristic_id": 1,
      "heuristic_name": "Visibility of system status",
      "severity": "high",
      "issue": "No loading indicator when submitting form",
      "affected_components": ["submit button", "form"],
      "suggestions": ["Add spinner to button when tapped", "Show success/error toast"],
      "user_impact": "Users don't know if their action registered"
    }}
  ],
  "strengths": [
    {{
      "heuristic_id": 4,
      "heuristic_name": "Consistency and standards",
      "observation": "Follows platform conventions with bottom navigation",
      "components": ["navigation bar", "tab icons"]
    }}
  ],
  "ux_score": 65,
  "total_violations": 5,
  "severity_breakdown": {{
    "critical": 0,
    "high": 2,
    "medium": 2,
    "low": 1
  }},
  "summary": "Brief assessment of overall usability"
}}

Be thorough. Find 5-10 violations minimum. Be specific about components and solutions.
"""
    
    print("📊 Calling Gemini for heuristic evaluation...")
    
    # Call Gemini
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=evaluation_prompt
    )
    
    # Extract and clean JSON
    result_text = response.text.strip()
    
    # Remove markdown code blocks
    if result_text.startswith("```json"):
        result_text = result_text[7:]
    elif result_text.startswith("```"):
        result_text = result_text[3:]
    if result_text.endswith("```"):
        result_text = result_text[:-3]
    
    result_text = result_text.strip()
    
    # Validate JSON
    try:
        json_data = json.loads(result_text)
        
        # Save evaluation
        output_dir = Path("data/outputs")
        output_dir.mkdir(exist_ok=True, parents=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = output_dir / f"heuristic_evaluation_{timestamp}.json"
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, indent=2, ensure_ascii=False)
        
        print(f"✓ Heuristic evaluation saved: {output_path}")
        print(f"✓ Found {json_data.get('total_violations', 0)} violations")
        print(f"✓ UX Score: {json_data.get('ux_score', 0)}/100")
        
    except json.JSONDecodeError as e:
        print(f"⚠ JSON validation error: {e}")
        # Save raw text
        output_path = output_dir / f"heuristic_evaluation_{timestamp}.txt"
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(result_text)
    
    return result_text