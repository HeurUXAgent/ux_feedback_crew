import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from src.ux_feedback_crew.crew import UxFeedbackCrew

# def run_evaluation_pipeline(image_path: str):
#     inputs = {'screenshot_path': image_path}
#     crew_obj = UxFeedbackCrew()
#     result = crew_obj.evaluation_crew().kickoff(inputs=inputs)
    
#     # result.tasks_outputs[0] is the Vision Analysis
#     # result.raw is the final Feedback Report
#     return str(result.tasks_output[0]), result.raw

# def run_wireframe_pipeline(evaluation_report: str, original_analysis: str):
#     inputs = {
#         'feedback_report': evaluation_report,
#         'original_layout': original_analysis # The "Anchor" to stop hallucinations
#     }
#     crew_obj = UxFeedbackCrew()
#     result = crew_obj.wireframe_crew().kickoff(inputs=inputs)
#     return result.raw

def run_full_ux_pipeline(image_path: str):
    inputs = {'screenshot_path': image_path}
    crew_obj = UxFeedbackCrew()
    
    # Kicks off the crew (added 'full_flow_crew' to crew.py)
    result = crew_obj.full_flow_crew().kickoff(inputs=inputs)
    
    # Accessing results using the singular 'tasks_output' list
    report = str(result.tasks_output[2].raw)
    wireframe = str(result.tasks_output[3].raw)
    
    return report, wireframe