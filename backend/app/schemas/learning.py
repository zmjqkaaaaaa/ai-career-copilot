from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PlanInput(Contract):
    weekly_minutes: int = Field(ge=15, le=1200)
    goal: str = Field(default="", max_length=200)
    interview_report_id: int | None = Field(default=None, gt=0)


class TopicInput(Contract):
    topic: str = Field(min_length=1, max_length=40)


class TaskInput(TopicInput):
    minutes: int = Field(ge=1, le=120)
    task_type: Literal["理论学习", "代码实践", "案例分析", "产品文档", "知识问答", "项目实战", "模拟面试", "错题复习"] | None = None


class TaskEdit(Contract):
    status: Literal["pending", "in_progress", "completed", "needs_revision"]
    actual_minutes: int | None = Field(default=None, ge=0, le=600)


class SessionInput(TopicInput):
    mode: str = Field(max_length=24)


class ResourceInput(TopicInput):
    title: str = Field(min_length=1, max_length=150)
    kind: Literal["official", "tutorial", "video", "project", "note"]
    url: HttpUrl | None = None
    text: str = Field(default="", max_length=8000)


class SubmissionInput(Contract):
    request_id: UUID
    kind: Literal["text", "markdown", "code", "github", "analysis", "prd"]
    content: str = Field(default="", max_length=12000)
    repository_url: str | None = Field(default=None, max_length=250)
    sample_outputs: dict[str, int] | None = Field(default=None, max_length=4)


class ReviewInput(Contract):
    kind: Literal["lesson", "evaluation", "path"]
    record_id: int = Field(gt=0)
    message: str = Field(default="", max_length=3000)
    approval: str | None = Field(default=None, pattern=r"^\d{10}\.[a-f0-9]{64}$")


class LessonOutput(Contract):
    explanation: str = Field(min_length=1, max_length=2400)
    example: str = Field(default="", max_length=2400)
    question: str = Field(min_length=1, max_length=450)
    next_step: str = Field(min_length=1, max_length=450)
    summary: str = Field(min_length=1, max_length=550)


class ReviewPoint(Contract):
    criterion: str = Field(max_length=60)
    quote: str = Field(default="", max_length=240)
    level: int | None = Field(default=None, ge=0, le=4)
    reason: str = Field(max_length=450)


class EvaluationOutput(Contract):
    ratings: list[ReviewPoint] = Field(max_length=12)
    correct: list[str] = Field(default_factory=list, max_length=5)
    errors: list[str] = Field(default_factory=list, max_length=5)
    missing: list[str] = Field(default_factory=list, max_length=5)
    revision: str = Field(min_length=1, max_length=650)
    next_step: str = Field(min_length=1, max_length=450)


class Answers(Contract):
    answers: dict[str, str] = Field(max_length=8)

