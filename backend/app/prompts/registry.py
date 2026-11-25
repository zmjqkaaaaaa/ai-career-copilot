"""Catalog current prompt contracts without changing what production sends."""
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Mapping

from pydantic import BaseModel

from app.ai import code_project_prompts as code
from app.ai import discovery_prompts as discovery
from app.ai import interview_prompts as interview
from app.ai import job_strategy_prompts as strategy
from app.ai import learning_prompts as learning
from app.ai import prompts as resume
from app.ai.provider import Prompt
from app.schemas import application as app_schema
from app.schemas import career as career_schema
from app.schemas import code_project as code_schema
from app.schemas import discovery as discovery_schema
from app.schemas import interview as interview_schema
from app.schemas import job as job_schema
from app.schemas import learning as learning_schema
from app.services.job_parser import JD_PROMPT, JD_PROMPT_V1
from app.services.skill_gap_service import ADVICE_PROMPT, ADVICE_PROMPT_V1

ROOT = Path(__file__).resolve().parent
TYPES = {"array": list, "object": dict, "string": str, "integer": int, "boolean": bool, "any": object}


def fingerprint(payload):
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True, ensure_ascii=False, allow_nan=False)
    return sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Definition:
    module: str
    prompt: Prompt
    output: type[BaseModel]
    required: tuple[tuple[str, str], ...]

    def validate_payload(self, payload: Mapping):
        for key, kind in self.required:
            if key not in payload or (kind != "any" and type(payload[key]) is not TYPES[kind]):
                raise ValueError(f"{self.prompt.name}: expected {kind} field {key}")
        fingerprint(payload)

    def manifest(self):
        return {
            "prompt_name": self.prompt.name, "module": self.module, "version": self.prompt.version,
            "system_prompt": self.prompt.instruction, "example": json.loads(self.prompt.example),
            "user_template": "serialise the payload as a JSON object",
            "input_schema": {"type": "object", "required": [key for key, _ in self.required],
                             "properties": {key: {"type": kind} if kind != "any" else {} for key, kind in self.required}},
            "output_schema": self.output.model_json_schema(),
            "model_config": {"profile": "existing Provider environment configuration"},
        }


def define(module, prompt, output, **required):
    return Definition(module, prompt, output, tuple(required.items()))


DEFINITIONS = (
    define("resume", resume.EXTRACT_V1, career_schema.StructuredResume, blocks="array"),
    define("resume", resume.EXTRACT, career_schema.StructuredResume, blocks="array"),
    define("resume", resume.ANALYZE_V1, career_schema.CareerResult, blocks="array", facts="object", target_direction="string"),
    define("resume", resume.ANALYZE, career_schema.CareerResult, blocks="array", facts="object", target_direction="string"),
    define("resume", resume.OPTIMIZE, career_schema.OptimizationResult, blocks="array", facts="object", target_direction="string"),
    define("job_matching", JD_PROMPT_V1, job_schema.JDResult, job_description="string"),
    define("job_matching", JD_PROMPT, job_schema.JDResult, job_description="string"),
    define("job_matching", ADVICE_PROMPT_V1, job_schema.Advice, decision="string", requirements="array"),
    define("job_matching", ADVICE_PROMPT, job_schema.Advice, decision="string", requirements="array"),
    define("discovery", discovery.TURN, discovery_schema.Turn, messages="array", mode="string"),
    define("discovery", discovery.PAIN, discovery_schema.PainResult, messages="array"),
    define("market_research", discovery.RESEARCH, discovery_schema.ResearchResult, topic="string", sources="array"),
    define("discovery", discovery.OPPORTUNITY, discovery_schema.Opportunity, pain="object", evidence="object", dimensions="object"),
    define("discovery", discovery.RECOMMEND, discovery_schema.Projects, opportunity="object", pain="object", background="object"),
    define("discovery", discovery.PRD, discovery_schema.PrdModel, project="object", opportunity="object"),
    define("code_analysis", code.ARCHITECTURE, code_schema.LessonOutput, evidence="array"),
    define("code_analysis", code.EXPLAIN, code_schema.LessonOutput, evidence="array"),
    define("code_analysis", code.CHAT, code_schema.LessonOutput, evidence="array", question="string"),
    define("code_analysis", code.QUIZ, code_schema.QuizOutput, evidence="array", dimension="string"),
    define("code_analysis", code.GRADE, code_schema.GradeOutput, quiz="object", answer="string"),
    define("interview", interview.START, interview_schema.QuestionDraft, target="string", stage="string", sources="array"),
    define("interview", interview.TURN, interview_schema.EvaluationDraft, target="string", stage="string", answer="string", rubric="array", sources="array"),
    define("learning", learning.LESSON, learning_schema.LessonOutput, topic="string", mode="string", message="string"),
    define("learning", learning.EVALUATION, learning_schema.EvaluationOutput, content="string", rubric="array", static="object"),
    define("learning", learning.PATH, learning_schema.LessonOutput, target="string", modules="array", weekly_minutes="integer"),
    define("job_strategy", strategy.STRATEGY_PROMPT, app_schema.StrategyResult, summary="object",
           sample_insufficient="boolean", minimum_sample="integer"),
)


class PromptRegistry:
    def __init__(self, definitions=DEFINITIONS, *, lock_path=ROOT / "baseline.json"):
        self.metadata = json.loads(lock_path.read_text(encoding="utf-8"))
        self.by_key = {(row.prompt.name, row.prompt.version): row for row in definitions}
        entries = self.metadata["versions"]
        pins = {(row["prompt_name"], row["version"]): row for row in entries}
        if len(pins) != len(entries) or len(self.by_key) != len(definitions) or self.by_key.keys() != pins.keys():
            raise ValueError("Prompt registry definitions and version metadata differ")
        self.active = self.metadata["active"]
        if self.active.keys() != {name for name, _ in self.by_key}:
            raise ValueError("Prompt registry active versions are incomplete")
        for name, version in self.active.items():
            self.get(name, version)
        for key, row in self.by_key.items():
            if fingerprint(row.manifest()) != pins[key]["sha256"]:
                raise ValueError(f"Prompt contract changed without a registry version update: {key}")

    def get(self, name, version=None):
        return self.by_key[(name, version or self.active[name])]

    def history(self, name):
        return [record for record in self.metadata["versions"] if record["prompt_name"] == name]

    def inventory(self):
        return [{**self.get(item["prompt_name"], item["version"]).manifest(), **item,
                 "active": self.active[item["prompt_name"]] == item["version"]}
                for item in self.metadata["versions"]]
