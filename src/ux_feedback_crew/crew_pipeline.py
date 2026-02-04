from ux_feedback_crew.crew import UxFeedbackCrew

def run_full_ux_pipeline(image_path: str, client_id: str):
    inputs = {
        "screenshot_path": image_path
    }

    crew_instance = UxFeedbackCrew(client_id)
    crew = crew_instance.full_flow_crew()
    result = crew.kickoff(inputs=inputs)
    
    report = str(result.tasks_output[2].raw)
    wireframe = str(result.tasks_output[3].raw)

    return report, wireframe
