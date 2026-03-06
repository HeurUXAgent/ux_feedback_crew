from ux_feedback_crew.crew import UxFeedbackCrew

def run_full_ux_pipeline(image_path: str, client_id: str):
    if image_path.startswith("http"):
        image_source = image_path  # S3 URL
    else:
        image_source = image_path

    inputs = {
        "screenshot_path": image_source
    }

    crew_instance = UxFeedbackCrew(client_id)
    crew = crew_instance.full_flow_crew()
    result = crew.kickoff(inputs=inputs)
    
    report = str(result.tasks_output[2].raw)
    wireframe = str(result.tasks_output[3].raw)

    return report, wireframe
