import os
from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task
from .tools import (
    analyze_ui_screenshot,
    evaluate_heuristics,
    generate_feedback,
    save_feedback_report, # Add this
    create_wireframe
)


@CrewBase
class UxFeedbackCrew():
    """UX Feedback Crew - Multi-agent system for UI evaluation"""
    
    agents_config = 'config/agents.yaml'
    tasks_config = 'config/tasks.yaml'

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
            verbose=True
        )
    
    @agent
    def feedback_specialist(self) -> Agent:
        return Agent(
            config=self.agents_config['feedback_specialist'],
            tools=[generate_feedback, save_feedback_report],  # Both tools
            verbose=True
        )
    
    @agent
    def wireframe_designer(self) -> Agent:
        return Agent(
            config=self.agents_config['wireframe_designer'],
            tools=[create_wireframe],
            verbose=True
        )
    
    @task
    def analyze_ui(self) -> Task:
        return Task(config=self.tasks_config['analyze_ui'])
    
    @task
    def evaluate_heuristics(self) -> Task:
        return Task(config=self.tasks_config['evaluate_heuristics'])
    
    @task
    def generate_feedback(self) -> Task:
        return Task(config=self.tasks_config['generate_feedback'])
    
    @task
    def create_wireframe(self) -> Task:
        return Task(config=self.tasks_config['create_wireframe'])
    
    @crew
    def evaluation_crew(self) -> Crew:
        """Phase 1: Analysis, Heuristics, and Feedback"""
        return Crew(
            agents=[self.vision_analyst(), self.heuristic_evaluator(), self.feedback_specialist()],
            tasks=[self.analyze_ui(), self.evaluate_heuristics(), self.generate_feedback()],
            process=Process.sequential,
            verbose=True
        )

    @crew
    def wireframe_crew(self) -> Crew:
        """Phase 2: Wireframe Generation"""
        return Crew(
            agents=[self.wireframe_designer()],
            tasks=[self.create_wireframe()],
            process=Process.sequential,
            verbose=True
        )
    
    @crew
    def full_flow_crew(self) -> Crew:
        """The Complete FYP Pipeline: Analysis -> Heuristics -> Feedback -> Wireframe"""
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