from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task
from src.ws_manager import safe_emit
from .tools import (
    analyze_ui_screenshot,
    evaluate_heuristics,
    generate_feedback,
    create_wireframe
)

@CrewBase
class UxFeedbackCrew():
    agents_config = 'config/agents.yaml'
    tasks_config = 'config/tasks.yaml'


    def __init__(self, client_id: str):
        self.client_id = client_id

    def step_callback(self, step_name: str, step_number: int):
        def callback(_output):
            safe_emit(
                self.client_id,
                f"Completed: {step_name}",
                step_number
            )
        return callback

    @agent
    def vision_analyst(self) -> Agent:
        return Agent(
            config=self.agents_config['vision_analyst'],
            tools=[analyze_ui_screenshot],
            verbose=True,
            allow_delegation=False
        )

    @agent
    def heuristic_evaluator(self) -> Agent:
        return Agent(
            config=self.agents_config['heuristic_evaluator'],
            tools=[evaluate_heuristics],
            verbose=True,
            allow_delegation=False
        )

    @agent
    def feedback_specialist(self) -> Agent:
        return Agent(
            config=self.agents_config['feedback_specialist'],
            tools=[generate_feedback],
            verbose=True,
            allow_delegation=False
        )

    @agent
    def wireframe_designer(self) -> Agent:
        return Agent(
            config=self.agents_config['wireframe_designer'],
            tools=[create_wireframe],
            verbose=True,
            allow_delegation=False
        )

    @task
    def analyze_ui(self) -> Task:
        return Task(
            config=self.tasks_config['analyze_ui'],
            callback=self.step_callback("Vision Analysis", 1),
            )

    @task
    def evaluate_heuristics(self) -> Task:
        return Task(
            config=self.tasks_config['evaluate_heuristics'],
            callback=self.step_callback("Heuristic Evaluation", 2),
        )

    @task
    def generate_feedback(self) -> Task:
        return Task(
            config=self.tasks_config['generate_feedback'],
            callback=self.step_callback("Feedback Generation", 3),
        )

    @task
    def create_wireframe(self) -> Task:
        return Task(
            config=self.tasks_config['create_wireframe'],
            callback=self.step_callback("Wireframe Creation", 4),)

    @crew
    def full_flow_crew(self) -> Crew:
        return Crew(
            agents=[
                self.vision_analyst(),
                self.heuristic_evaluator(),
                self.feedback_specialist(),
                self.wireframe_designer()
            ],
            tasks=[
                self.analyze_ui(),
                self.evaluate_heuristics(),
                self.generate_feedback(),
                self.create_wireframe()
            ],
            process=Process.sequential, 
            verbose=True
        )
    
    # function to handle progress updates
    def create_step_callback(client_id: str, step_name: str, step_number: int):
        import asyncio
        def callback(output):
            # This runs when the task completes
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(
                manager.send_progress(client_id, f"Finished: {step_name}", step_number)
            )
        return callback
