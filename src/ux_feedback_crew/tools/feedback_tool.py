import json
import re
from pathlib import Path
from crewai.tools import tool
import vertexai
from vertexai.generative_models import GenerativeModel

OUTPUT_DIR = Path("data/outputs")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

vertexai.init(
    project="heuruxagent",
    location="us-central1"
)

model = GenerativeModel(
    "projects/75094798515/locations/us-central1/models/178770695071727616@1"
)


def extract_json(text: str):
    text = text.strip()

    if "```" in text:
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        if match:
            text = match.group(1)

    try:
        return json.loads(text)
    except:
        match = re.search(r"(\{[\s\S]*\})", text)
        if match:
            return json.loads(match.group(1))
    raise ValueError("No valid JSON found")


@tool("generate_feedback")
def generate_feedback(vision_analysis: str, heuristic_evaluation: str) -> str:
    """
    Generate developer UX feedback JSON.
    """

    prompt = f"""
You are a senior UX expert.

Convert the analysis into structured UX feedback.

Return ONLY JSON.

VISION:
{vision_analysis}

HEURISTICS:
{heuristic_evaluation}

JSON FORMAT:

{{
 "feedback_items":[
   {{
     "title":"...",
     "priority":"high|medium|low",
     "why_it_matters":"...",
     "what_to_do":["step1","step2"]
   }}
 ],
 "ux_score":0
}}
"""

    try:
        response = model.generate_content(prompt)
        raw = response.text

        parsed = extract_json(raw)

        with open(OUTPUT_DIR / "feedback.json", "w") as f:
            json.dump(parsed, f, indent=2)

        return json.dumps(parsed)

    except Exception as e:
        return json.dumps({"error": str(e)})