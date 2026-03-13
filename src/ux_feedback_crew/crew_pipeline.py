from ux_feedback_crew.crew import UxFeedbackCrew
from app.utils.hitl_handler import set_active_context, clear_active_context


def run_full_ux_pipeline_raw(image_path: str, client_id: str, evaluation_id: str):
    """
    builtins.input is already patched globally (at hitl_handler import time).
    We just set the active context so the patched input() knows which
    evaluation/client to handle when CrewAI calls it.
    """
    crew_instance = UxFeedbackCrew(client_id=client_id, evaluation_id=evaluation_id)
    crew = crew_instance.full_flow_crew()

    set_active_context(evaluation_id, client_id)
    try:
        result = crew.kickoff(inputs={"screenshot_path": image_path})
    finally:
        clear_active_context()

    return result