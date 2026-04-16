from pydantic import BaseModel, Field, validator
from typing import List, Optional, Union

class FeedbackItem(BaseModel):
    title: str = "Untitled Recommendation"
    priority: str = "low"
    effort_estimate: str = "N/A"
    why_it_matters: str = ""
    what_to_do: List[str] = []
    wireframe_changes: Optional[str] = None

    @validator("priority", pre=True, always=True)
    def normalize_priority(cls, v):
        if not v:
            return "low"
        v = str(v).lower().strip()
        return v if v in ("high", "medium", "low") else "low"

    @validator("what_to_do", pre=True, always=True)
    def normalize_steps(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [v] if v.strip() else []
        if isinstance(v, list):
            return [str(s) for s in v if str(s).strip()]
        return []

    @validator("effort_estimate", pre=True, always=True)
    def normalize_effort(cls, v):
        return str(v).strip() if v else "N/A"

    @validator("why_it_matters", pre=True, always=True)
    def normalize_why(cls, v):
        return str(v).strip() if v else ""

    @validator("wireframe_changes", pre=True, always=True)
    def normalize_wireframe(cls, v):
        if not v or str(v).strip() in ("", "N/A", "null", "None"):
            return None
        return str(v).strip()


class UXScore(BaseModel):
    score: float = 0.0
    grade: str = "N/A"

    @validator("score", pre=True, always=True)
    def normalize_score(cls, v):
        try:
            v = float(v)
        except (TypeError, ValueError):
            return 0.0
        # Model trained on 0–10 scale — normalize to 0–100 for frontend
        if v <= 10:
            return round(v * 10, 1)
        return round(v, 1)

    @validator("grade", pre=True, always=True)
    def normalize_grade(cls, v):
        return str(v).strip() if v else "N/A"

class FeedbackSummary(BaseModel):
    total_issues: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0

    @validator("*", pre=True, always=True)
    def coerce_int(cls, v):
        try:
            return int(v)
        except (TypeError, ValueError):
            return 0

class FeedbackReport(BaseModel):
    feedback_items: List[FeedbackItem] = []
    ux_score: Optional[UXScore] = None
    summary: Optional[FeedbackSummary] = None

    @validator("feedback_items", pre=True, always=True)
    def normalize_items(cls, v):
        if not isinstance(v, list):
            return []
        return v

    def recompute_summary(self) -> "FeedbackReport":
        """
        Recalculate summary counts from actual feedback_items
        so they always match reality regardless of what the model returned.
        """
        items = self.feedback_items
        high   = sum(1 for i in items if i.priority == "high")
        medium = sum(1 for i in items if i.priority == "medium")
        low    = sum(1 for i in items if i.priority == "low")
        self.summary = FeedbackSummary(
            total_issues=len(items),
            high=high,
            medium=medium,
            low=low,
        )
        return self

    def to_frontend_dict(self) -> dict:
        """
        Serialize to a dict that matches exactly what Flutter's
        _ParseResult.tryParse expects.
        """
        return {
            "feedback_items": [
                {
                    "title":             item.title,
                    "priority":          item.priority,
                    "effort_estimate":   item.effort_estimate,
                    "why_it_matters":    item.why_it_matters,
                    "what_to_do":        item.what_to_do,
                    "wireframe_changes": item.wireframe_changes,
                }
                for item in self.feedback_items
            ],
            "ux_score": {
                "score": self.ux_score.score,
                "grade": self.ux_score.grade,
            } if self.ux_score else None,
            "summary": {
                "total_issues": self.summary.total_issues,
                "high":         self.summary.high,
                "medium":       self.summary.medium,
                "low":          self.summary.low,
            } if self.summary else None,
        }