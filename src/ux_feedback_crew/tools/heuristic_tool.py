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
    Evaluates UI designs against Nielsen's 10 Usability Heuristics and
    mobile UX best practices.
    
    Args:
        vision_analysis: JSON string of vision analysis results
        
    Returns:
        JSON string with violations, severity scores, and overall UX score
    """

    load_dotenv()
    
    # Load heuristics knowledge base
    heuristics_path = Path(__file__).parent.parent / "config" / "nielsen_heuristics.json"
    
    if heuristics_path.exists():
        with open(heuristics_path, 'r') as f:
            heuristics_data = json.load(f)
        heuristics_list = heuristics_data.get('heuristics', [])
    else:
        # Fallback heuristics
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
TASK: Evaluate this mobile UI against Nielsen's 10 Usability Heuristics

UI ANALYSIS TO EVALUATE:
{vision_analysis}

NIELSEN'S 10 USABILITY HEURISTICS:
{json.dumps(heuristics_list, indent=2)}

EVALUATION INSTRUCTIONS:
Carefully evaluate the UI analysis against each of Nielsen's heuristics. For each heuristic:
1. Check if the UI violates the principle
2. Assess severity: high (critical UX issue), medium (moderate impact), low (minor issue)
3. Identify which UI components are affected
4. Suggest specific improvements

Also identify STRENGTHS where the UI follows best practices well.

Return ONLY valid JSON with this structure:

{{
  "violations": [
    {{
      "heuristic_id": 1,
      "heuristic_name": "Visibility of system status",
      "severity": "high/medium/low",
      "issue": "Detailed description of the violation",
      "affected_components": ["component1", "component2"],
      "improvement_suggestion": "Specific, actionable recommendation",
      "user_impact": "How this affects the user experience"
    }}
  ],
  "strengths": [
    {{
      "heuristic_id": 4,
      "heuristic_name": "Consistency and standards",
      "observation": "What the UI does well",
      "components": ["component1", "component2"]
    }}
  ],
  "overall_score": 7.5,
  "summary": "Brief overall assessment of the UI's usability"
}}

SEVERITY GUIDELINES:
- HIGH: Major usability issue that will frustrate users and prevent task completion
- MEDIUM: Notable issue that degrades experience but doesn't block tasks
- LOW: Minor issue or improvement opportunity

Be thorough and specific. Provide actionable feedback.
"""
    
    print(f"✓ Loaded {len(heuristics_list)} heuristics for evaluation")
        
    return evaluation_prompt


