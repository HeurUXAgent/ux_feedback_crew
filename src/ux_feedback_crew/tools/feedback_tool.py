import json
from crewai.tools import tool


@tool("generate_feedback")
def generate_feedback(vision_analysis: str, heuristic_evaluation: str) -> str:
    """
    Prepares structured UX analysis input for the feedback agent.

    The agent's LLM will transform this into developer-friendly
    recommendations and structured JSON output.
    """

    try:
        vision_data = json.loads(vision_analysis)
    except Exception:
        vision_data = vision_analysis

    try:
        heuristic_data = json.loads(heuristic_evaluation)
    except Exception:
        heuristic_data = heuristic_evaluation

    structured_input = {
        "vision_analysis": vision_data,
        "heuristic_evaluation": heuristic_data
    }

    prompt_context = f"""
You are a senior UX consultant.

Using the analysis below, generate **developer-friendly UX feedback**.

Return ONLY valid JSON with the following structure:

{{
  "feedback_items": [
    {{
      "title": "Short issue title",
      "priority": "high | medium | low",
      "effort_estimate": "low | medium | high",
      "why_it_matters": "Explain the UX impact",
      "what_to_do": ["implementation step 1", "implementation step 2"],
      "wireframe_changes": "Suggested UI layout improvement"
    }}
  ],
  "quick_wins": [
    {{
      "change": "small improvement",
      "impact": "why it helps",
      "effort": "low | medium | high"
    }}
  ],
  "ux_score": {{
    "score": 0,
    "grade": "excellent | good | average | poor",
    "severity": "low | moderate | high",
    "reasoning": "short explanation"
  }},
  "summary": {{
    "total_issues": 0,
    "high": 0,
    "medium": 0,
    "low": 0,
    "estimated_total_effort": "Low | Medium | High"
  }},
  "implementation_order": ["step1", "step2"]
}}

UX ANALYSIS DATA:
{json.dumps(structured_input, indent=2)}
"""

    return prompt_context