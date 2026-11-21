from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Step = Literal["analyze", "explain", "chat", "quiz", "grade"]
Dimension = Literal["overview", "stack", "structure", "functions", "api", "database", "ai", "debug", "extension"]


class Contract(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class ImportRequest(Contract):
    url: str = Field(min_length=1, max_length=240)
    recommendation_id: int | None = Field(default=None, gt=0)


class StudyRequest(Contract):
    commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    kind: Step
    file_id: int | None = Field(default=None, gt=0)
    symbol: str | None = Field(default=None, max_length=160)
    question: str | None = Field(default=None, max_length=1600)
    quiz_id: int | None = Field(default=None, gt=0)
    answer: str | None = Field(default=None, max_length=3500)
    dimension: Dimension | None = None
    mode: Literal["concept", "function", "flow", "choice", "debug", "architecture", "change"] | None = None


class StudySubmit(StudyRequest):
    approval: str = Field(min_length=65, max_length=100)


class CitationClaim(Contract):
    title: str = Field(min_length=1, max_length=160)
    explanation: str = Field(min_length=1, max_length=2200)
    status: Literal["observed", "inferred", "unknown", "suggestion"]
    references: list[int] = Field(default_factory=list, max_length=6)


class LessonOutput(Contract):
    overview: str = Field(min_length=1, max_length=1500)
    sections: list[CitationClaim] = Field(default_factory=list, max_length=12)
    missing: list[str] = Field(default_factory=list, max_length=8)
    exercises: list[str] = Field(default_factory=list, max_length=6)


class Criterion(Contract):
    label: str = Field(min_length=1, max_length=160)
    expected: str = Field(min_length=1, max_length=650)


class QuizOutput(Contract):
    question: str = Field(min_length=1, max_length=1000)
    concept: str = Field(min_length=1, max_length=160)
    expected_answer: str = Field(min_length=1, max_length=1400)
    rubric: list[Criterion] = Field(min_length=2, max_length=6)
    references: list[int] = Field(min_length=1, max_length=5)


class GradeItem(Contract):
    index: int = Field(ge=1, le=6)
    result: Literal["correct", "partial", "missing", "incorrect"]
    feedback: str = Field(min_length=1, max_length=700)


class GradeOutput(Contract):
    criteria: list[GradeItem] = Field(max_length=6)
    explanation: str = Field(min_length=1, max_length=1400)
    practice: str = Field(min_length=1, max_length=600)


class SelfReport(Contract):
    dimension: Dimension
    note: str = Field(min_length=1, max_length=600)
