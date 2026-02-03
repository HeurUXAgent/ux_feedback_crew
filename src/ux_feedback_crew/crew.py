from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task
from pydantic import BaseModel
from typing import List, Dict, Any
from .tools import (
    analyze_ui_screenshot,
    evaluate_heuristics,
    generate_feedback,
    create_wireframe
)

# Pydantic models for structured output
class VisionAnalysisOutput(BaseModel):
    """Schema for vision analysis output"""
    screen_type: str
    components: List[Dict[str, Any]]
    layout_structure: Dict[str, Any]
    color_scheme: Dict[str, Any]
    typography: Dict[str, Any]
    spacing_and_density: Dict[str, Any]
    accessibility_observations: List[str]
    notable_patterns: List[str]


class HeuristicEvaluationOutput(BaseModel):
    """Schema for heuristic evaluation output"""
    violations: List[Dict[str, Any]]
    strengths: List[Dict[str, Any]]
    ux_score: float
    total_violations: int


class FeedbackOutput(BaseModel):
    """Schema for feedback output"""
    feedback_items: List[Dict[str, Any]]
    quick_wins: List[Dict[str, Any]]
    summary: Dict[str, Any]


@CrewBase
class UxFeedbackCrew():
    """UX Feedback Crew - Optimized Multi-Agent System"""
    
    agents_config = 'config/agents.yaml'
    tasks_config = 'config/tasks.yaml'

    @agent
    def vision_analyst(self) -> Agent:
        """Analyzes UI screenshots using vision tool"""
        return Agent(
            config=self.agents_config['vision_analyst'],
            tools=[analyze_ui_screenshot],
            verbose=True,
            allow_delegation=False,
            max_iter=3
        )
    
    @agent
    def heuristic_evaluator(self) -> Agent:
        """Evaluates against heuristics using evaluation tool"""
        return Agent(
            config=self.agents_config['heuristic_evaluator'],
            tools=[evaluate_heuristics],
            verbose=True,
            allow_delegation=False,
            max_iter=3
        )
    
    @agent
    def feedback_specialist(self) -> Agent:
        """Generates developer-friendly feedback"""
        return Agent(
            config=self.agents_config['feedback_specialist'],
            tools=[generate_feedback],
            verbose=True,
            allow_delegation=False,
            max_iter=3
        )
    
    @agent
    def wireframe_designer(self) -> Agent:
        """Creates improved wireframes"""
        return Agent(
            config=self.agents_config['wireframe_designer'],
            tools=[create_wireframe],
            verbose=True,
            allow_delegation=False,
            max_iter=2
        )
    
    @task
    def analyze_ui(self) -> Task:
        """Vision analysis task"""
        return Task(
            config=self.tasks_config['analyze_ui']
            # Removed output_json - let it return string
        )
    
    @task
    def evaluate_heuristics(self) -> Task:
        """Heuristic evaluation task"""
        return Task(
            config=self.tasks_config['evaluate_heuristics']
            # Removed output_json - let it return string
        )
    
    @task
    def generate_feedback(self) -> Task:
        """Feedback generation task"""
        return Task(
            config=self.tasks_config['generate_feedback']
            # Removed output_json - let it return string
        )
    
    @task
    def create_wireframe(self) -> Task:
        """Wireframe creation task"""
        return Task(
            config=self.tasks_config['create_wireframe'],
            output_file='data/outputs/wireframe.html'
        )
    
    @crew
    def crew(self) -> Crew:
        """Main crew - use this method"""
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
            verbose=True,
            memory=False,
            max_rpm=20,
            full_output=True
        )
    
    # ALIAS for backward compatibility with existing code
    def full_flow_crew(self) -> Crew:
        """
        Alias for crew() - for backward compatibility
        This allows old code calling .full_flow_crew() to work
        """
        return self.crew()