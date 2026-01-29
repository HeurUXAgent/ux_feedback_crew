# app/crew_pipeline.py
import sys
from pathlib import Path

# Important: This allows app to see the src directory
sys.path.append(str(Path(__file__).parent.parent))

from src.ux_feedback_crew.crew import UxFeedbackCrew

def run_evaluation_pipeline(image_path: str):
    inputs = {'screenshot_path': image_path} # Matches your vision tool input
    crew_instance = UxFeedbackCrew()
    result = crew_instance.evaluation_crew().kickoff(inputs=inputs)
    return result.raw

def run_wireframe_pipeline(evaluation_report: str):
    # This input key must match what your wireframe_designer expects in tasks.yaml
    inputs = {'feedback_report': evaluation_report} 
    crew_instance = UxFeedbackCrew()
    result = crew_instance.wireframe_crew().kickoff(inputs=inputs)
    return result.raw