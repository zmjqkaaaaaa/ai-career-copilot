from datetime import date
from typing import Literal

from pydantic import BaseModel


class SkillSummary(BaseModel):
    verified: int
    self_reported: int
    inferred: int
    unknown: int


class Gap(BaseModel):
    name: str
    status: str


class MatchSummary(BaseModel):
    id: int
    job_id: int
    position: str
    gaps: list[Gap]


class Recommendation(BaseModel):
    id: int
    session_id: int
    name: str
    selected: bool


class TodayTask(BaseModel):
    id: int
    title: str
    minutes: int
    status: str


class InterviewSummary(BaseModel):
    session_id: int
    target: str
    score: float | None
    answered: int
    weakness: str | None


class NextAction(BaseModel):
    kind: Literal["application", "learning", "interview", "matching", "profile", "exploration"]
    text: str
    application_id: int | None = None


class Dashboard(BaseModel):
    day: date
    target_position: str | None
    profile_complete: bool
    skills: SkillSummary
    match: MatchSummary | None
    projects: list[Recommendation]
    tasks: list[TodayTask]
    interview: InterviewSummary | None
    applications: dict[str, int]
    next_action: NextAction
