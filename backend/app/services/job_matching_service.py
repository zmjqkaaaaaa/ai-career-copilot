from decimal import Decimal, ROUND_HALF_UP
from datetime import date
import re
from sqlalchemy import select

from app.ai.evidence import lookup_blocks
from app.core.errors import ApiError
from app.core.job_scoring import DIMENSIONS, EVIDENCE, IMPORTANCE_WEIGHT, VERSION, WEIGHTS
from app.models.career import CareerAnalysis
from app.models.resume import Resume, ResumeContent
from app.models.user_profile import UserProfile
from app.services.career import read_analysis
from app.services.job_availability import compare_weekly_availability, resume_weekly_availability
from app.services.job_context_evidence import contextual_evidence, needs_interview_evidence
from app.services.job_parser import normalize_text
from app.services.practice_evidence import PRACTICE_TERMS, find_practice, term_pattern
from app.services.resume_education import degree_rank, enrollment_lines
from app.services.skill_gap_service import resume_evidence_suggestion

ALIASES = {"产品需求分析": "产品思维", "编写sql": "sql", "数据处理": "数据分析",
           "prompt": "prompt engineering", "提示词工程": "prompt engineering", "人工智能": "ai技术理解"}
PRACTICE_LIMIT = re.compile(r"熟练|精通|独立|至少|[0-9一二三四五六七八九十]+(?:个)?[年月周]|实习经历|实习经验|正式工作|全职|上线|生产环境|\b(?:advanced|expert)\b", re.I)

def skill_key(name: str) -> str:
    key = re.sub(r"\s+", "", normalize_text(name))
    return re.sub(r"\s+", "", ALIASES.get(key, key))


def confirmed_sources(facts: dict, blocks: list[dict], groups: tuple[str, ...]) -> list[dict]:
    lookup = lookup_blocks(blocks)
    evidence = []
    for group in groups:
        for fact in facts.get(group, []):
            source = fact.get("source")
            if not source:
                continue
            number, quote = source["block_number"], source["quote"]
            if fact["original"] == quote and quote in lookup.get(number, ""):
                evidence.append({"block_number": number, "quote": quote})
    return evidence


def confirmed_practice(facts: dict, blocks: list[dict]) -> list[dict]:
    return confirmed_sources(facts, blocks, ("projects", "internships", "other_experiences"))


def related_practice(requirement: dict, person: dict) -> list[dict]:
    name = requirement["name"]
    return find_practice(name, person.get("practice", []), (skill_key(name),))


def requirement_checks(requirement: dict, person: dict) -> list[dict]:
    if requirement["kind"] not in {"skill", "experience"}:
        return []
    quote = normalize_text(requirement["quote"])
    if re.search(r"或者|二选一|之一|任选|或|\bor\b", quote):
        return []  # Do not silently turn alternatives into cumulative conditions.
    checks = []
    for name, aliases in PRACTICE_TERMS.items():
        if name in {"产品思维", "ai 技术理解", "prompt engineering"}:
            # This broad category overlaps with specific activities.
            continue
        if any(term_pattern(term).search(quote) for term in (name, *aliases)):
            sources = related_practice({"name": name}, person)
            checks.append({"name": name.upper() if name == "prd" else name, "sources": sources})
    return checks


def interpretation(kind, status, evidence, checks):
    missing = "、".join(check["name"] for check in checks if not check["sources"])
    if len(checks) > 1 and missing and status == "partial":
        return f"这条 JD 包含多项要求，仍缺少以下项目或实习证据：{missing}。"
    if status == "unmet":
        return "现有信息与条件存在明确冲突，投递前应优先核对这一项。"
    if kind == "availability":
        if status == "matched":
            return "简历自述的每周实习天数达到这条 JD 的最低要求。"
        if status == "partial":
            return "每周实习天数达到要求，JD 中的其他到岗条件还需核对。"
        return "需要核对每周到岗天数、可连续实习时长和开始日期。"
    if status.startswith("pending"):
        return "当前资料没有足够的证据判断这条要求。先核对简历是否漏写相关经历或限定条件。"
    if evidence == "resume_supported":
        return "已确认的简历中有对应实践。" if status == "matched" else "简历有相关实践，这条要求还有条件需要核对。"
    if evidence == "inferred":
        return "相关经历可用于举例。请核实个人承担的工作、交付物，以及它是否达到 JD 要求的范围。"
    if status == "partial":
        return "已有相关能力的自述。请补充能证明熟练度、独立承担程度或实际使用范围的材料。"
    return "现有资料支持这项要求。面试时可准备说明具体做法和验证材料。"


def candidate(db, user_id: int, content_id: int, analysis_id: int | None) -> dict:
    content = db.scalar(select(ResumeContent).join(Resume).where(
        ResumeContent.id == content_id, Resume.user_id == user_id, Resume.parse_status != "deleting",
        ResumeContent.confirmed.is_(True),
    ).with_for_update())
    if content is None:
        raise ApiError(404, "JOB_CANDIDATE_NOT_FOUND", "未找到已确认的简历版本")
    statement = select(CareerAnalysis.id).where(CareerAnalysis.user_id == user_id, CareerAnalysis.content_id == content_id)
    selected = db.scalar(statement.where(CareerAnalysis.id == analysis_id)) if analysis_id else db.scalar(statement.order_by(CareerAnalysis.id.desc()).limit(1))
    if analysis_id and not selected:
        raise ApiError(404, "JOB_ANALYSIS_NOT_FOUND", "未找到与该简历版本一致的职业画像")
    report = read_analysis(db, user_id, selected, None)["report"] if selected else {}
    profile = db.scalar(select(UserProfile).where(UserProfile.user_id == user_id))
    # 个人档案和已确认简历的明确陈述只构成自述。
    skills = {skill_key(skill["name"]): skill for skill in report.get("skills", []) if skill["status"] in EVIDENCE}
    facts = content.structured_data or {}
    blocks = content.model_blocks or []
    declarations = [(value, "个人档案") for value in (profile.skills if profile else [])]
    declarations.extend((fact.get("normalized") or fact["original"], fact["original"]) for fact in facts.get("skills", []) if fact.get("source"))
    for name, source in declarations:
        key = skill_key(name)
        if key not in skills or skills[key]["status"] == "inferred":
            skills[key] = {"status": "self_reported", "level": "自述", "sources": [{"quote": source if source != "个人档案" else name, "location": source == "个人档案" and source or "结构化简历"}]}
    experience = [fact["original"] for group in ("projects", "internships")
                  for fact in facts.get(group, []) if fact.get("source")]
    if profile:
        experience.extend(entry["title"] for group in (profile.project_experience, profile.internship_experience)
                          for entry in group if entry.get("title"))
    return {"analysis_id": selected, "skills": skills,
            "education": [fact["original"] for fact in facts.get("education", []) if fact.get("source")],
            "degrees": [profile.undergraduate_degree] if profile and profile.undergraduate_degree else [],
            "majors": [value for value in (profile.undergraduate_major, profile.graduate_major) if value] if profile else [],
            "experience": experience,
            "practice": confirmed_practice(facts, blocks),
            "academic_evidence": confirmed_sources(facts, blocks, ("education",)),
            "internship_evidence": confirmed_sources(facts, blocks, ("internships",)),
            "weekly_availability": resume_weekly_availability(blocks),
            "graduation_year": profile.graduation_year if profile else None,
            "assessment_year": date.today().year}

def compare_requirement(requirement: dict, person: dict, assessment: str | None):
    if assessment == "not_capable":
        return "unmet", "self_reported", [{"quote": "用户明确标记为不具备或不符合"}]
    if assessment in {"not_provided", "no_evidence"}:
        return "pending_" + assessment, "unknown", []
    kind = requirement["kind"]
    quote = requirement["quote"]
    if kind == "availability":
        return compare_weekly_availability(quote, person.get("weekly_availability", []))
    if kind == "graduation_year":
        years = [int(year) for year in re.findall(r"20\d{2}", quote)]
        year = person.get("graduation_year")
        if year and years and "毕业" in quote and len(years) <= 2:
            if len(years) == 2:
                matches = min(years) <= year <= max(years) if re.search(r"至|到|[-–—~]", quote) else year in years
            elif re.search(r"之后|以后|及以后", quote):
                matches = year >= years[0]
            elif re.search(r"之前|以前|及以前", quote):
                matches = year <= years[0]
            else:
                matches = year == years[0]
            return ("matched" if matches else "unmet"), "self_reported", [{"quote": f"个人档案预计毕业 {year} 年"}]
    if kind == "degree":
        values = person.get("degrees", []) + person.get("education", [])
        ranks = [rank for value in values if (rank := degree_rank(value)) is not None]
        minimum = degree_rank(quote)
        if minimum and ranks:
            qualifiers = [term for term in ("全日制", "统招", "应届") if term in quote]
            if "在读" in quote and not re.search(r"在读.{0,8}或.{0,8}毕业|毕业.{0,8}或.{0,8}在读", quote):
                academic = person.get("academic_evidence") or [{"quote": value} for value in person.get("education", [])]
                year = person.get("assessment_year", date.today().year)
                enrolled = [{**source, "quote": line} for source in academic
                            for line in enrollment_lines(source["quote"], year)
                            if (degree_rank(line) or 0) >= minimum and all(term in line for term in qualifiers)]
                if enrolled:
                    return "matched", "resume_supported", enrolled
                return "pending_no_evidence", "unknown", academic or [{"quote": value} for value in values]
            if qualifiers and not any(all(term in value for term in qualifiers) for value in values):
                return "pending_no_evidence", "unknown", [{"quote": value} for value in values]
            if re.search(r"已获得|已取得|取得.*学位|毕业证|已毕业", quote):
                if any(minimum <= (degree_rank(value) or 0) and re.search(r"已毕业|已取得|已获得", value)
                       and "或已毕业" not in value for value in values):
                    return "matched", "self_reported", [{"quote": value} for value in values]
            elif max(ranks) >= minimum:
                return "matched", "self_reported", [{"quote": value} for value in values]
            elif any("最高学历" in value for value in values):
                return "unmet", "self_reported", [{"quote": value} for value in values]
            elif person.get("degrees") and "研究生" not in "".join(person["degrees"]):
                # A lower qualification alone cannot rule out additional qualifications.
                return "pending_no_evidence", "unknown", [{"quote": value} for value in values]
    if kind == "major":
        majors = person.get("majors", [])
        direct = [major for major in majors if normalize_text(major) in normalize_text(quote)]
        if direct:
            return "matched", "self_reported", [{"quote": value} for value in direct]
    related = related_practice(requirement, person) if kind in {"skill", "experience"} else []
    if related and not PRACTICE_LIMIT.search(quote) and not needs_interview_evidence(requirement):
        return "matched", "resume_supported", related
    if kind == "skill":
        skill = person.get("skills", {}).get(skill_key(requirement["name"]))
        if skill and skill["status"] in EVIDENCE:
            advanced = bool(re.search(r"熟练|精通|独立完成|advanced|expert", quote, re.I))
            partial = (advanced and skill["level"] in {"基础", "自述"}) or (
                skill["status"] != "verified" and bool(PRACTICE_LIMIT.search(quote)))
            return ("partial" if partial else "matched"), skill["status"], skill["sources"]
    if kind == "experience":
        matching = [value for value in person.get("experience", []) if normalize_text(requirement["name"]) == normalize_text(value)]
        if matching and not re.search(r"\d|至少|以上|全职", quote):
            return "matched", "self_reported", [{"quote": value} for value in matching]
    if related:
        return "partial", "inferred", related
    return "pending_not_provided", "unknown", []

def round_score(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def score(requirements: list[dict], person: dict, assessments: dict[int, str]) -> dict:
    rows = []
    for index, requirement in enumerate(requirements):
        assessment = assessments.get(index)
        status, evidence, sources = compare_requirement(requirement, person, assessment)
        note = None
        if assessment is None and (status.startswith("pending") or evidence == "inferred"):
            relevant, note = contextual_evidence(requirement, person)
            if relevant:
                status, evidence, sources = "partial", "inferred", relevant
            elif status.startswith("pending") and needs_interview_evidence(requirement):
                status = "pending_interview"
                note = "这项行为或动机需要通过面试举例确认。当前简历不足以直接判断。"
        checks = requirement_checks(requirement, person) if not assessment else []
        if len(checks) > 1:
            if status == "matched" and any(not check["sources"] for check in checks):
                status = "partial"
            if status != "matched" and all(check["sources"] for check in checks) and not PRACTICE_LIMIT.search(requirement["quote"]):
                status, evidence = "matched", "resume_supported"
            if status.startswith("pending") and any(check["sources"] for check in checks):
                status, evidence = "partial", "inferred"
            sources = [*sources]
            for check in checks:
                sources.extend(source for source in check["sources"] if source not in sources)
        dimension = DIMENSIONS.get(requirement["category"], requirement["category"])
        factor = {"matched": 1, "partial": .5}.get(status, 0)
        points = factor * EVIDENCE.get(evidence, 0)
        if requirement["kind"] == "degree" and "在读" in requirement["quote"] and status.startswith("pending") and sources:
            note = "已有学历相关资料。此 JD 还要求当前在读，需要单独核对在校状态。"
        rows.append({**requirement, "ordinal": index, "status": status, "evidence_status": evidence,
                     "sources": sources[:5], "dimension": dimension, "points": points, "checks": checks,
                     "resume_suggestion": resume_evidence_suggestion(requirement, status),
                     "interpretation": note or interpretation(requirement["kind"], status, evidence, checks)})
    dimensions = {}
    applicable_weight = Decimal(0)
    weighted_points = Decimal(0)
    covered_weight = Decimal(0)
    for name, weight in WEIGHTS.items():
        entries = [(row, IMPORTANCE_WEIGHT[row["importance"]]) for row in rows if row["dimension"] == name]
        rated = [priority for row, priority in entries if not row["status"].startswith("pending")]
        denominator = sum(priority for _, priority in entries)
        dimension_score = None
        effective_weight = Decimal(0)
        if denominator:
            # Soft-only dimensions have less influence, even if they contain many requirements.
            strongest = max(priority for _, priority in entries)
            effective_weight = Decimal(weight * strongest) / IMPORTANCE_WEIGHT["required"]
            mean = sum(Decimal(str(row["points"])) * priority for row, priority in entries) / denominator
            dimension_score = round_score(100 * mean)
            applicable_weight += effective_weight
            weighted_points += effective_weight * mean
            covered_weight += effective_weight * sum(rated) / denominator
        dimensions[name] = {"weight": weight, "effective_weight": float(effective_weight), "score": dimension_score,
                            "required": sum(row["importance"] == "required" for row, _ in entries),
                            "total": len(entries), "rated": len(rated)}
    overall = round_score(100 * weighted_points / applicable_weight) if applicable_weight else None
    coverage = round_score(100 * covered_weight / applicable_weight) if applicable_weight else None
    hard = [row for row in rows if row["importance"] == "required"
            and (row["status"] != "matched" or row["evidence_status"] == "inferred")]
    conflicts = [row for row in hard if row["status"] == "unmet"]
    if conflicts:
        verdict = "当前匹配较低，建议先补足关键能力"
    elif hard:
        verdict = "建议先核对报告中尚未满足或缺证的硬性要求"
    elif any(row["importance"] == "required" for row in rows):
        verdict = "现有材料支持硬性要求，可以尝试投递"
    else:
        verdict = "无硬性要求，按报告中的条件与证据准备投递" if rows else "请先核对 JD 的岗位要求"
    return {"version": VERSION, "score_method": "priority_weighted_evidence", "overall_score": overall,
            "evidence_coverage": coverage,
            "dimensions": dimensions, "requirements": rows, "hard_flags": hard, "verdict": verdict}
