from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Short = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
Medium = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=400)]
Long = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1200)]
SkillName = Literal[
    "产品思维", "商业分析", "行业理解", "数据分析", "用户研究", "Python", "SQL", "LLM",
    "Prompt Engineering", "RAG", "Agent", "API", "AI Coding", "AI 技术理解", "项目实践", "表达能力",
]
SKILLS = {
    "产品思维": "专业能力", "商业分析": "专业能力", "行业理解": "专业能力", "数据分析": "专业能力",
    "用户研究": "专业能力", "Python": "技术能力", "SQL": "技术能力", "LLM": "技术能力",
    "Prompt Engineering": "技术能力", "RAG": "技术能力", "Agent": "技术能力", "API": "技术能力",
    "AI Coding": "技术能力", "AI 技术理解": "技术能力", "项目实践": "项目实践", "表达能力": "表达能力",
}

class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid")

class Block(Schema):
    number: int
    location: str
    text: str

class Anchor(Schema):
    block_number: int = Field(ge=1, le=500, strict=True)
    quote: Long

class Fact(Schema):
    original: Long
    normalized: Medium | None = None
    source: Anchor | None = None
    status: Literal["extracted", "uncertain", "user_confirmed"] = "extracted"

class StructuredResume(Schema):
    education: list[Fact] = Field(default_factory=list, max_length=15)
    internships: list[Fact] = Field(default_factory=list, max_length=15)
    projects: list[Fact] = Field(default_factory=list, max_length=15)
    skills: list[Fact] = Field(default_factory=list, max_length=35)
    certificates: list[Fact] = Field(default_factory=list, max_length=15)
    competitions: list[Fact] = Field(default_factory=list, max_length=15)
    languages: list[Fact] = Field(default_factory=list, max_length=15)
    other_experiences: list[Fact] = Field(default_factory=list, max_length=15)

class AnalysisPoint(Schema):
    title: Short
    reason: Medium
    sources: list[Anchor] = Field(default_factory=list, max_length=3)

class AssessedSkill(Schema):
    name: SkillName
    level: Literal["基础", "有实践迹象", "有较强实践迹象", "未评估"]
    status: Literal["verified", "self_reported", "inferred", "unknown"]
    reason: Medium
    sources: list[Anchor] = Field(default_factory=list, max_length=3)

class CareerResult(Schema):
    summary: AnalysisPoint
    education: list[AnalysisPoint] = Field(default_factory=list, max_length=8)
    project_practice: list[AnalysisPoint] = Field(default_factory=list, max_length=8)
    skills: list[AssessedSkill] = Field(default_factory=list, max_length=16)
    strengths: list[AnalysisPoint] = Field(default_factory=list, max_length=8)
    gaps: list[AnalysisPoint] = Field(default_factory=list, max_length=8)
    directions: list[AnalysisPoint] = Field(default_factory=list, max_length=6)
    recommended_projects: list[AnalysisPoint] = Field(default_factory=list, max_length=6)
    next_steps: list[AnalysisPoint] = Field(default_factory=list, max_length=8)

class OptimizationItem(Schema):
    section: Literal["结构", "内容", "真实性"]
    original: Anchor
    rewritten: Long
    reason: Medium
    interview_question: Medium
    needs_evidence: bool

class OptimizationResult(Schema):
    suggestions: list[OptimizationItem] = Field(default_factory=list, max_length=10)

class Trigger(Schema):
    retry: bool = False

class ParseTrigger(Trigger):
    reparse: bool = False

class ModelTrigger(Trigger):
    accept_external_processing: bool = False
    provider_host: Short | None = None

class ExtractTrigger(ModelTrigger):
    content_id: int = Field(gt=0)
    hidden_blocks: list[Annotated[int, Field(gt=0, le=500)]] = Field(default_factory=list, max_length=500)

class ContentEdit(Schema):
    content_id: int = Field(gt=0)
    structured_data: StructuredResume

class AnalyzeRequest(ModelTrigger):
    resume_id: int = Field(gt=0)
    content_id: int = Field(gt=0)
    target_direction: Short

class OptimizeRequest(ModelTrigger):
    content_id: int = Field(gt=0)
    target_direction: Short

class ConfirmOptimization(Schema):
    text: Long

class ModelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

class ResumeRead(ModelRead):
    id: int
    original_filename: str
    file_type: str
    file_size: int
    parse_status: str
    parse_error: str | None
    created_at: datetime
    updated_at: datetime

class JobRead(ModelRead):
    id: int
    resume_id: int
    kind: str
    state: str
    attempt: int
    result_id: int | None
    error_code: str | None

class ContentRead(ModelRead):
    id: int
    resume_id: int
    version: int
    parser_version: str
    blocks: list[Block]
    model_blocks: list[Block] | None
    structured_data: StructuredResume | None
    confirmed: bool
    metadata_json: dict | None

class AnalysisRead(ModelRead):
    id: int
    content_id: int
    target_direction: str
    model_name: str
    prompt_version: str
    created_at: datetime

class OptimizationRead(ModelRead):
    id: int
    content_id: int
    original_content: str
    optimized_content: str
    optimization_reason: str
    interview_question: str
    section: str
    needs_evidence: bool
    block_number: int
    confirmed_text: str | None
    confirmed_at: datetime | None
    created_at: datetime
