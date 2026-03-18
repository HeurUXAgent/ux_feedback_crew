from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task
from src.ws_manager import safe_emit
from .tools import (
    analyze_ui_screenshot,
    evaluate_heuristics,
    generate_feedback,
    create_wireframe,
)


@CrewBase
class UxFeedbackCrew():
    agents_config = 'config/agents.yaml'
    tasks_config  = 'config/tasks.yaml'

    def __init__(self, client_id: str, evaluation_id: str = ""):
        self.client_id     = client_id
        self.evaluation_id = evaluation_id

    def _progress(self, label: str, step: int):
        def callback(_output):
            safe_emit(self.client_id, f"Completed: {label}", step)
        return callback

    # ─── Agents ───────────────────────────────────────────────────────

    @agent
    def vision_analyst(self) -> Agent:
        return Agent(config=self.agents_config['vision_analyst'],
                     tools=[analyze_ui_screenshot], verbose=True, allow_delegation=False)

    @agent
    def heuristic_evaluator(self) -> Agent:
        return Agent(config=self.agents_config['heuristic_evaluator'],
                     tools=[evaluate_heuristics], verbose=True, allow_delegation=False)

    @agent
    def feedback_specialist(self) -> Agent:
        return Agent(config=self.agents_config['feedback_specialist'],
                     tools=[generate_feedback], verbose=True, allow_delegation=False)

    @agent
    def wireframe_designer(self) -> Agent:
        return Agent(config=self.agents_config['wireframe_designer'],
                     tools=[create_wireframe], verbose=True, allow_delegation=False)

    # ─── Tasks ────────────────────────────────────────────────────────

    @task
    def analyze_ui(self) -> Task:
        return Task(config=self.tasks_config['analyze_ui'],
                    callback=self._progress("Vision Analysis", 25))

    @task
    def evaluate_heuristics(self) -> Task:
        return Task(config=self.tasks_config['evaluate_heuristics'],
                    callback=self._progress("Heuristic Evaluation", 50))

    @task
    def generate_feedback(self) -> Task:
        return Task(config=self.tasks_config['generate_feedback'],
                    callback=self._progress("Feedback Generation", 75),
                    human_input=False)

    @task
    def create_wireframe(self) -> Task:
        return Task(config=self.tasks_config['create_wireframe'],
                    callback=self._progress("Wireframe Creation", 90))

    # ─── Crew 1: Full pipeline ─────────────────────────────────────────

    @crew
    def full_flow_crew(self) -> Crew:
        return Crew(
            agents=[self.vision_analyst(), self.heuristic_evaluator(),
                    self.feedback_specialist(), self.wireframe_designer()],
            tasks=[self.analyze_ui(), self.evaluate_heuristics(),
                   self.generate_feedback(), self.create_wireframe()],
            process=Process.sequential,
            verbose=True,
        )

    # ─── Crew 2: Wireframe-only regeneration ──────────────────────────
    # Runs ONLY the wireframe agent.
    # Context (vision, heuristics, feedback, user comments) is passed
    # via the inputs dict so the agent has full context to improve.

    def wireframe_regen_crew(self) -> Crew:
        return Crew(
            agents=[self.wireframe_designer()],
            tasks=[self.create_wireframe()],
            process=Process.sequential,
            verbose=True,
        )