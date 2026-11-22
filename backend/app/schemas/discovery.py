from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StringConstraints

Short = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=180)]
Note = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1200)]
Mode = Literal["guided", "assisted"]
Step = Literal["turn", "pain", "research", "opportunity", "recommend", "prd"]
EvidenceKind = Literal["experience", "observation", "hearsay", "market_inference"]

class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid")

class SessionInput(Schema):
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
    mode: Mode = "guided"
    direction: Short | None = None
    weekly_hours: int | None = Field(default=None, ge=1, le=80)

class SessionCreate(SessionInput):
    job_match_id: int | None = Field(default=None, gt=0)
    application_id: int | None = Field(default=None, gt=0)

class Interest(Schema):
    name: Short
    category: Literal["行业", "场景", "技术", "经历", "优势", "探索方向"]
    origin: Literal["stated", "inferred"]
    evidence_message_id: int | None = None
    reason: Note
    confidence: Literal["low", "medium", "high"] = "low"

class Turn(Schema):
    reply: Note
    questions: list[Short] = Field(default_factory=list, max_length=2)
    learning_note: Note
    interests: list[Interest] = Field(default_factory=list, max_length=8)

class Evidence(Schema):
    kind: EvidenceKind
    detail: Note
    message_id: int | None = None

class Pain(Schema):
    pain_point_name: Short
    target_user: Short
    scenario: Note
    user_problem: Note
    current_solution: Note | None = None
    frequency: Short | None = None
    severity: Short | None = None
    validation_status: Literal["hypothesis", "user_reviewed", "interview_reported"] = "hypothesis"
    evidence: list[Evidence] = Field(default_factory=list, max_length=10)
    confidence: Literal["low", "medium", "high"] = "low"
    interview_target: Short | None = None
    interview_questions: list[Short] = Field(default_factory=list, max_length=6)
    demand_signal: Note | None = None

class PainResult(Schema):
    pain_points: list[Pain] = Field(default_factory=list, max_length=4)

class SourceInput(Schema):
    url: HttpUrl
    title: Short
    excerpt: Note
    source_type: Literal["official", "third_party", "user_review", "unclassified"] = "unclassified"

class Claim(Schema):
    text: Note
    sources: list[int] = Field(default_factory=list, max_length=5)
    evidence_excerpt: Note | None = None

class Competitor(Schema):
    product_name: Short
    official_source: int | None = None
    positioning: Claim | None = None
    target_users: Claim | None = None
    features: Claim | None = None
    scenarios: Claim | None = None
    experience: Claim | None = None
    technology: Claim | None = None
    business_model: Claim | None = None
    advantages: Claim | None = None
    limitations: Claim | None = None
    differentiation: Claim | None = None

class ResearchResult(Schema):
    competitors: list[Competitor] = Field(default_factory=list, max_length=8)
    market_findings: list[Claim] = Field(default_factory=list, max_length=6)

class Rating(Schema):
    dimension: str
    rating: int | None = Field(default=None, ge=0, le=4)
    basis: Literal["evidence", "user_hypothesis", "ai_inference", "unknown"]
    reason: Note
    references: list[str] = Field(default_factory=list, max_length=5)

class Opportunity(Schema):
    ratings: list[Rating] = Field(max_length=9)
    risks: list[Note] = Field(default_factory=list, max_length=6)
    differentiation: Note
    feasibility: Note
    validation_plan: Note

class Project(Schema):
    name: Short
    direction: Literal["workflow", "analysis", "copilot", "knowledge", "evaluation", "research"]
    background: Note
    target_user: Short
    pain: Note
    positioning: Note
    features: list[Short] = Field(min_length=1, max_length=5)
    ai_use: Note
    stack: list[Short] = Field(min_length=1, max_length=8)
    difficulty: Literal["入门", "中等", "进阶"]
    estimated_hours: int = Field(ge=1, le=400)
    learning: list[Short] = Field(min_length=1, max_length=6)
    role_alignment: Note
    differentiation: Note
    risks: list[Note] = Field(min_length=1, max_length=6)
    reason: Note
    deliverable: Short

class Projects(Schema):
    projects: list[Project] = Field(min_length=3, max_length=5)

PRD_FIELDS = {
    "background":"项目背景","positioning":"产品定位","target_users":"目标用户","persona":"用户画像",
    "pain":"用户痛点","scenarios":"使用场景","competitors":"竞品分析","opportunity":"产品机会",
    "value":"核心价值","mvp":"MVP 范围","features":"功能列表","flow":"核心用户流程","ai":"AI 能力设计",
    "data":"数据需求","feasibility":"技术可行性","acceptance":"验收标准","risks":"风险与待验证假设",
}

class PrdModel(Schema):
    title: Short
    sections: dict[str, Note] = Field(min_length=17, max_length=17)

class PrdEdit(Schema):
    title: Short
    content: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=18000)]
    version: int = Field(ge=1)

class ProjectEdit(Schema):
    favorite: bool | None = None
    selected: bool | None = None
    project: Project | None = None

class JobInput(Schema):
    kind: Step
    reference_id: int | None = Field(default=None, gt=0)
    research_id: int | None = Field(default=None, gt=0)
    message: Note | None = None
    queries: list[Short] = Field(default_factory=list, max_length=3)
    sources: list[SourceInput] = Field(default_factory=list, max_length=10)
    regenerate: bool = False

class JobSubmit(JobInput):
    approval: str = Field(min_length=64, max_length=64)
