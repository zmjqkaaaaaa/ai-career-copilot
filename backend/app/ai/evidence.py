import hashlib
import json
import re

from app.core.errors import ApiError
from app.schemas.career import Anchor, CareerResult, Fact, GroundedCareerResult, GroundedSkill, OptimizationItem, SKILLS, StructuredResume
from app.services.resume_sections import ENTRY_SECTIONS
from app.services.practice_evidence import find_practice

EMAIL = re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", re.I)
PHONE = re.compile(r"(?<!\d)(?:\+?86[ -]?)?1[3-9]\d(?:[ -]?\d){8}(?!\d)|(?<!\d)(?:\+\d{1,3}[ -])?\(?\d{3}\)?[ -]\d{3}[ -]\d{4}(?!\d)")
IDENTITY = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")
LINK = re.compile(r"(?:https?://|www\.)[^\s，。；、<>]+", re.I)
PERSONAL_LINE = re.compile(r"(?im)(^|[|｜])\s*(?:姓名|现居|住址|地址|通讯地址|联系电话|联系人|电话|邮箱|微信|身份证|name|address|phone|email)\s*[：:]\s*[^\n|｜]+")

def redact_text(text: str) -> str:
    text = PERSONAL_LINE.sub(lambda match: f"{match.group(1)}[已脱敏]", text)
    for pattern in (EMAIL, PHONE, IDENTITY, LINK):
        text = pattern.sub("[已脱敏]", text)
    return text

def redact_blocks(blocks: list[dict], hidden: list[int] = ()) -> list[dict]:
    allowed = {block["number"] for block in blocks}
    if set(hidden) - allowed:
        raise ApiError(422, "INVALID_HIDDEN_BLOCK", "选中的段落已不在当前解析版本")
    return [{**block, "text": redact_text(block["text"])} for block in blocks if block["number"] not in hidden]

def anchor_exists(anchor: Anchor | None, lookup: dict[int, str]) -> bool:
    return anchor is not None and anchor.quote in lookup.get(anchor.block_number, "")

def lookup_blocks(blocks: list[dict]) -> dict[int, str]:
    return {block["number"]: block["text"] for block in blocks}

def approved_text_digest(blocks: list[dict]) -> str:
    return hashlib.sha256(json.dumps(blocks, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

def local_resume_facts(blocks: list[dict], sections=None) -> StructuredResume:
    result = StructuredResume()
    for block in blocks:
        group = block.get("section")
        if group not in StructuredResume.model_fields or (sections is not None and group not in sections):
            continue
        facts = getattr(result, group)
        values = re.split(r"[、，,；;\n]", block["text"]) if group == "skills" else [block["text"]]
        for value in values:
            quote = value.strip()
            if len(facts) >= (35 if group == "skills" else 15):
                break
            if not quote or not any(char.isalnum() for char in quote.replace("[已脱敏]", "")):
                continue
            facts.append(Fact(original=quote, source=Anchor(block_number=block["number"], quote=quote)))
    return result


def validate_extraction(result: StructuredResume, blocks: list[dict]) -> tuple[StructuredResume, int]:
    lookup = lookup_blocks(blocks)
    local = local_resume_facts(blocks, ENTRY_SECTIONS)
    grouped_blocks = {fact.source.block_number for group in ENTRY_SECTIONS for fact in getattr(local, group)}
    rejected = 0
    valid_count = 0
    for field in StructuredResume.model_fields:
        valid = getattr(local, field)
        for fact in getattr(result, field):
            if fact.source and anchor_exists(fact.source, lookup) and fact.original == fact.source.quote:
                if field in ENTRY_SECTIONS and fact.source.block_number in grouped_blocks:
                    continue  # An exact, complete source entry is already preserved under its heading.
                status = "uncertain" if fact.status == "uncertain" else "extracted"
                if len(valid) < (35 if field == "skills" else 15):
                    valid.append(fact.model_copy(update={"status": status, "normalized": redact_text(fact.normalized) if fact.normalized else None}))
            else:
                rejected += 1
        setattr(result, field, valid)
        valid_count += len(valid)
    if rejected and not valid_count:
        raise ApiError(502, "MODEL_EVIDENCE_INVALID", "模型未返回可以核对的原文引文")
    return result, rejected

def confirm_facts(facts: StructuredResume, blocks: list[dict]) -> StructuredResume:
    lookup = lookup_blocks(blocks)
    for field in StructuredResume.model_fields:
        updated = []
        for fact in getattr(facts, field):
            source = fact.source if fact.source and fact.original == fact.source.quote and anchor_exists(fact.source, lookup) else None
            updated.append(fact.model_copy(update={"status": "user_confirmed", "source": source}))
        setattr(facts, field, updated)
    return facts

def facts_for_model(facts: dict) -> dict:
    # Manually added claims stay visible locally until they can be tied to a resume source.
    return {
        group: [{"original": fact["original"], "source": fact["source"]} for fact in items if fact["source"]]
        for group, items in facts.items()
    }

def validate_analysis(report: CareerResult, blocks: list[dict]) -> GroundedCareerResult:
    lookup = lookup_blocks(blocks)
    report.summary.sources = [source for source in report.summary.sources if anchor_exists(source, lookup)]
    if not report.summary.sources:
        report.summary.reason = "当前报告只展示能定位到简历原文的背景依据和待补充证据。"
    for category in ("education", "project_practice", "strengths", "gaps", "directions", "recommended_projects", "next_steps"):
        items = getattr(report, category)
        for point in items:
            point.sources = [source for source in point.sources if anchor_exists(source, lookup)]
        if category in ("education", "project_practice", "strengths"):
            setattr(report, category, [point for point in items if point.sources])

    project_quotes = [{"block_number": block["number"], "quote": block["text"]}
                      for block in blocks if block.get("section") in {"projects", "internships", "other_experiences"}]
    assessments = {}
    for skill in report.skills:
        matches = [source for source in skill.sources if anchor_exists(source, lookup)]
        if not matches or skill.status in {"unknown", "verified"} or skill.level == "未评估":
            continue
        status = skill.status
        if status == "self_reported" and not any(skill.name.casefold() in source.quote.casefold() for source in matches):
            status = "inferred"
        assessments.setdefault(skill.name, GroundedSkill.model_validate(
            {**skill.model_dump(), "status": status, "sources": matches}))
    for name in SKILLS:
        if sources := find_practice(name, project_quotes):
            assessments[name] = GroundedSkill(name=name, level="有实践迹象", status="resume_supported",
                                              reason="简历项目或经历中写明了相关行动。", sources=sources)
    skills = [assessments.get(name) or GroundedSkill(
        name=name, level="未评估", status="unknown", reason="当前简历没有足够的可核对证据。",
    ) for name in SKILLS]
    return GroundedCareerResult.model_validate({**report.model_dump(exclude={"skills"}), "skills": skills})

def validate_optimizations(items: list[OptimizationItem], blocks: list[dict]) -> list[OptimizationItem]:
    lookup = lookup_blocks(blocks)
    validated = []
    numbers = re.compile(r"\d+(?:[.,]\d+)*%?")
    for item in items:
        if not anchor_exists(item.original, lookup):
            continue
        invented_number = not set(numbers.findall(item.rewritten)) <= set(numbers.findall(item.original.quote))
        invented_scope = any(
            word in item.rewritten and word not in item.original.quote
            for word in ("主导", "独立完成", "上线", "获奖", "全权负责", "商业化", "营收", "转化率", "客户增长")
        )
        if invented_number or invented_scope:
            item = item.model_copy(update={
                "rewritten": item.original.quote, "needs_evidence": True,
                "reason": "改写中有原句无法核对的数字或职责，请先补充可核对的事实。",
            })
        validated.append(item)
    if items and not validated:
        raise ApiError(502, "MODEL_EVIDENCE_INVALID", "优化建议无法定位到简历原文")
    return validated
