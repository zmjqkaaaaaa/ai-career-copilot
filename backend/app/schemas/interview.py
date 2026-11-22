from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

Mode = Literal["resume", "project", "product", "technical", "combined"]
Stage = Literal["intro", "resume", "project", "product", "technical", "scenario", "reverse"]
Text = Annotated[str, Field(min_length=1, max_length=900)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class InterviewSetup(Contract):
    mode: Mode
    difficulty: Literal["beginner", "intermediate", "advanced"] = "beginner"
    style: Literal["coach", "hr", "technical"] = "coach"
    minutes: int = Field(default=15, ge=5, le=60)
    deep_followup: bool = True
    teaching: bool = False
    target: str | None = Field(default=None, min_length=1, max_length=150)
    resume_content_id: int | None = Field(default=None, gt=0)
    job_id: int | None = Field(default=None, gt=0)
    interview_schedule_id: int | None = Field(default=None, gt=0)
    application_id: int | None = Field(default=None, gt=0)
    recommendation_id: int | None = Field(default=None, gt=0)
    repository_id: int | None = Field(default=None, gt=0)
    commit: str | None = Field(default=None, pattern=r"^[a-f0-9]{40}$")
    stage_minutes: dict[Stage, Annotated[int, Field(ge=1, le=45)]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def verify_schedule(self):
        if (self.application_id or self.interview_schedule_id) and (self.job_id or self.resume_content_id):
            raise ValueError("使用投递或日程时，JD 和简历由投递记录决定")
        if self.commit and not self.repository_id:
            raise ValueError("提交版本需要对应仓库")
        if self.stage_minutes and (self.mode != "combined" or len(self.stage_minutes) != 7
                                   or sum(self.stage_minutes.values()) != self.minutes):
            raise ValueError("综合模式需填写七个阶段，合计等于总时长")
        if self.mode == "combined" and self.minutes < 7:
            raise ValueError("综合模式至少需要七分钟")
        return self


class InterviewCreate(InterviewSetup):
    request_id: UUID


class TurnInput(Contract):
    kind: Literal["start", "answer"]
    question_id: int | None = Field(default=None, gt=0)
    answer: str | None = Field(default=None, min_length=1, max_length=3500)

    @model_validator(mode="after")
    def validate_submission(self):
        if self.kind == "answer" and (not self.answer or not self.question_id):
            raise ValueError("请输入当前题的答案")
        if self.kind == "start" and (self.answer or self.question_id):
            raise ValueError("开始请求不包含答案")
        return self


class ApprovedTurn(TurnInput):
    approval: str = Field(pattern=r"^\d{10}\.[a-f0-9]{64}$")


class QuestionDraft(Contract):
    question: str = Field(min_length=1, max_length=360)
    knowledge_point: str = Field(min_length=1, max_length=100)
    basis: Literal["source", "scenario", "answer"]
    references: list[str] = Field(default_factory=list, max_length=4)
    hint: str | None = Field(default=None, max_length=240)


class Rating(Contract):
    dimension: str = Field(max_length=42)
    level: int | None = Field(default=None, ge=0, le=4)
    reason: Text
    quote: str | None = Field(default=None, max_length=350)


class EvaluationDraft(Contract):
    ratings: list[Rating] = Field(default_factory=list, max_length=16)
    strengths: list[Text] = Field(default_factory=list, max_length=3)
    missing: list[Text] = Field(default_factory=list, max_length=4)
    corrected_idea: Text
    answer_outline: list[Text] = Field(default_factory=list, max_length=5)
    exercise: Text
    acceptance: Text
    contribution_claim: str | None = Field(default=None, max_length=350)
    action: Literal["follow_up", "advance", "probe_error", "end_stage"] = "advance"
    followup_quote: str | None = Field(default=None, max_length=350)
    followup_reason: str | None = Field(default=None, max_length=350)
    next_question: QuestionDraft | None = None


class TrainingUpdate(Contract):
    state: Literal["todo", "done"]
