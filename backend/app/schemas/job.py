from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StringConstraints, field_validator

Short = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
Quote = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
Dimension = Literal["education","product","ai","data","practice","industry"]
Category = Literal["education","product","ai","programming","data","practice","industry","communication"]
Kind = Literal["skill","degree","major","graduation_year","availability","experience"]
Importance = Literal["required","preferred","optional","unknown"]

class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid")

class JobCreate(Schema):
    position_name: Short
    company_name: Short | None = None
    location: Short | None = None
    job_type: Literal["internship","full_time","other"] | None = None
    salary_range: Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)] | None = None
    source_url: HttpUrl | None = Field(default=None, max_length=1000)
    job_description: Annotated[str, StringConstraints(strip_whitespace=True, min_length=10, max_length=12000)]

    @field_validator("source_url")
    @classmethod
    def public_link(cls, url):
        if url and (url.username is not None or url.password is not None):
            raise ValueError("招聘链接不能包含账号或密码")
        return url

class Requirement(Schema):
    name: Short
    category: Category
    kind: Kind
    importance: Importance
    quote: Quote

class JDResult(Schema):
    position_name: Short | None = None
    department: Short | None = None
    company_name: Short | None = None
    location: Short | None = None
    job_type: Short | None = None
    duties: list[Quote] = Field(default_factory=list, max_length=20)
    requirements: list[Requirement] = Field(default_factory=list, max_length=40)

class RequirementEdit(Schema):
    revision: int = Field(ge=1)
    requirements: list[Requirement] = Field(max_length=40)

class ModelRequest(Schema):
    accept_external_processing: bool = False
    provider_host: Short
    retry: bool = False

class MatchRequest(Schema):
    content_id: int = Field(gt=0)
    analysis_id: int | None = Field(default=None, gt=0)
    revision: int = Field(ge=1)
    assessments: dict[int, Literal["not_provided","no_evidence","not_capable"]] = Field(default_factory=dict, max_length=40)

class Advice(Schema):
    rationale: Quote
    resume_focus: list[Quote] = Field(max_length=5)
    interview_focus: list[Quote] = Field(max_length=5)
    projects: list[Quote] = Field(max_length=5)
    next_steps: list[Quote] = Field(max_length=6)
