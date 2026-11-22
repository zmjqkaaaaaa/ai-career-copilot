from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from app.schemas.job import JobCreate, Schema, Short

Status = Literal["wishlist", "applied", "written_test", "interview_1", "interview_2",
                 "hr_interview", "offer", "rejected", "withdrawn"]
Note = Annotated[str, Field(max_length=1000)]
Text = Annotated[str, Field(min_length=1, max_length=400)]
Positive = Annotated[int, Field(gt=0)]


class JobMetadata(Schema):
    industry: Short | None = None
    education: Short | None = None
    major: Short | None = None
    experience: Short | None = None
    skills: list[Short] = Field(default_factory=list, max_length=30)
    duties: Note | None = None
    requirements_text: Note | None = None
    source: Short | None = None
    published_at: date | None = None
    source_status: Literal["unknown", "open", "closed", "unavailable"] = "unknown"


class JobCapture(JobCreate):
    job_description: Annotated[str, Field(max_length=12000)] = ""

    @model_validator(mode="after")
    def require_source(self):
        self.job_description = self.job_description.strip()
        if len(self.job_description) < 10 and not self.source_url:
            raise ValueError("请填写至少 10 字的 JD 或保存招聘原链接")
        return self


class JobImport(JobCapture):
    metadata: JobMetadata | None = None


class JobPatch(Schema):
    favorite: bool | None = None
    metadata: JobMetadata | None = None
    job: JobCapture | None = None


class ResumeSelection(Schema):
    content_id: Positive
    target_job_id: Positive | None = None


class ResumeVersionInput(Schema):
    request_id: UUID
    version_name: Short
    change_summary: Annotated[str, Field(min_length=1, max_length=1000)]
    block_numbers: list[Positive] = Field(min_length=1, max_length=300)
    optimization_ids: list[Positive] = Field(default_factory=list, max_length=100)
    confirmed: Literal[True]


class ResumeVersionCreate(ResumeVersionInput, ResumeSelection):
    pass


class ApplicationFields(Schema):
    channel: Short | None = None
    applied_at: AwareDatetime | None = None
    resume_version_id: Positive | None = None
    valid_submission: bool = True
    notes: Note | None = None
    next_action: Note | None = None
    contact: Short | None = None
    feedback: Note | None = None
    rejection_reason: Note | None = None


class ApplicationCreate(ApplicationFields):
    job_id: Positive
    request_id: UUID
    job_match_id: Positive | None = None


class ApplicationPatch(ApplicationFields):
    revision: Positive


class StatusUpdate(Schema):
    request_id: UUID
    revision: Positive
    status: Status
    notes: Note | None = None
    applied_at: AwareDatetime | None = None


class ScheduleFields(Schema):
    scheduled_at: AwareDatetime
    timezone: Annotated[str, Field(min_length=1, max_length=80)]
    duration: int = Field(default=60, ge=5, le=480)
    interview_round: Literal["interview_1", "interview_2", "hr_interview", "other"]
    interview_type: Literal["online", "onsite", "phone", "other"]
    location_or_url: Note | None = None
    preparation_notes: Note | None = None
    result: Literal["scheduled", "pending", "passed", "failed", "cancelled"] = "scheduled"
    retrospective: Note | None = None


class ScheduleCreate(ScheduleFields):
    application_id: Positive
    request_id: UUID


class SchedulePatch(ScheduleFields):
    revision: Positive


class Period(Schema):
    start: date | None = None
    end: date | None = None


class StrategyRequest(Period):
    approval: str = Field(pattern=r"^\d{10}\.[a-f0-9]{64}$")


class StrategyResult(Schema):
    current_state: Text
    observations: list[Text] = Field(max_length=5)
    inferences: list[Text] = Field(max_length=5)
    hypotheses: list[Text] = Field(max_length=5)
    priority_actions: list[Text] = Field(min_length=1, max_length=5)
    next_goal: Text
