from ux_feedback_crew.crew import UxFeedbackCrew

def run_full_ux_pipeline_raw(image_path: str, client_id: str, evaluation_id: str):
    """
    Runs the full CrewAI pipeline.
    Passes evaluation_id to crew so HITL handler can match feedback
    submissions to the correct waiting pipeline thread.
    Returns the raw CrewAI result object.
    """
    inputs = {
        "screenshot_path": image_path
    }

    crew_instance = UxFeedbackCrew(client_id=client_id, evaluation_id=evaluation_id)
    crew = crew_instance.full_flow_crew()
    result = crew.kickoff(inputs=inputs)

    return result


def run_full_ux_pipeline(image_path: str, client_id: str, evaluation_id: str = ""):
    """Legacy wrapper — returns (feedback_report, wireframe_output) as strings."""
    result = run_full_ux_pipeline_raw(image_path, client_id, evaluation_id)
    report = str(result.tasks_output[2].raw)
    wireframe = str(result.tasks_output[3].raw)
    return report, wireframe

# def run_full_ux_pipeline(image_path: str, client_id: str):
#     if image_path.startswith("http"):
#         image_source = image_path  # S3 URL
#     else:
#         image_source = image_path

#     inputs = {
#         "screenshot_path": image_source
#     }

#     crew_instance = UxFeedbackCrew(client_id)
#     crew = crew_instance.full_flow_crew()
#     result = crew.kickoff(inputs=inputs)
    
#     report = str(result.tasks_output[2].raw)
#     wireframe = str(result.tasks_output[3].raw)

#     return report, wireframe
