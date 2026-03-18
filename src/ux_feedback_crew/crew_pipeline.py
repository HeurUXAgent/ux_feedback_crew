from ux_feedback_crew.crew import UxFeedbackCrew


def run_full_ux_pipeline_raw(image_path: str, client_id: str, evaluation_id: str = ""):
    """
    Runs the full CrewAI pipeline and returns the raw result object.
    No HITL blocking — pipeline runs to completion.
    HITL feedback is collected post-execution via Flutter UI.
    """
    crew_instance = UxFeedbackCrew(client_id=client_id, evaluation_id=evaluation_id)
    crew = crew_instance.full_flow_crew()
    result = crew.kickoff(inputs={"screenshot_path": image_path})
    return result