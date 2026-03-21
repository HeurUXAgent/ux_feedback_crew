from ux_feedback_crew.crew import UxFeedbackCrew


def run_full_ux_pipeline_raw(image_path: str, client_id: str, evaluation_id: str = ""):
    """Full pipeline: Vision → Heuristics → Feedback → Wireframe."""
    crew_instance = UxFeedbackCrew(client_id=client_id, evaluation_id=evaluation_id)
    result = crew_instance.full_flow_crew().kickoff(
        inputs={"screenshot_path": image_path}
    )
    return result


def run_wireframe_regen_raw(
    client_id: str,
    evaluation_id: str,
    image_path: str,
    vision_analysis: str,
    heuristic_evaluation: str,
    original_feedback: str,
    feedback_user_comment: str,   
    wireframe_user_comment: str,  
):
    """
    Wireframe-only regeneration.
    Passes all context to the wireframe agent so it can produce
    an improved design incorporating the user's specific comments.
    """
    crew_instance = UxFeedbackCrew(client_id=client_id, evaluation_id=evaluation_id)
    result = crew_instance.wireframe_regen_crew().kickoff(inputs={
        "screenshot_path": image_path,
        "vision_analysis": vision_analysis,
        "heuristic_evaluation": heuristic_evaluation,
        "original_feedback": original_feedback,
        "feedback_user_comment": feedback_user_comment,
        "wireframe_user_comment": wireframe_user_comment,
    })
    return result