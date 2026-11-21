import re
from sqlalchemy import select

from app.core.errors import ApiError
from app.core.job_scoring import DIMENSIONS, EVIDENCE, VERSION, WEIGHTS
from app.models.career import CareerAnalysis
from app.models.resume import Resume, ResumeContent
from app.models.user_profile import UserProfile
from app.services.career import read_analysis
from app.services.job_parser import normalize_text

ALIASES = {"产品需求分析": "产品思维", "编写sql": "sql", "数据处理": "数据分析",
           "prompt": "prompt engineering", "提示词工程": "prompt engineering", "人工智能": "ai技术理解"}

def skill_key(name: str) -> str:
    key = re.sub(r"\s+", "", normalize_text(name))
    return re.sub(r"\s+", "", ALIASES.get(key, key))

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
            "graduation_year": profile.graduation_year if profile else None}

def degree_rank(text: str) -> int | None:
    for index, tokens in reversed(list(enumerate((("大专","专科"),("本科","学士"),("硕士","研究生"),("博士",)), 1))):
        if any(token in text for token in tokens):
            return index
    return None

def compare_requirement(requirement: dict, person: dict, assessment: str | None):
    if assessment == "not_capable":
        return "unmet", "self_reported", [{"quote": "用户明确标记为不具备或不符合"}]
    if assessment in {"not_provided", "no_evidence"}:
        return "pending_" + assessment, "unknown", []
    kind = requirement["kind"]
    quote = requirement["quote"]
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
    if kind == "skill":
        skill = person.get("skills", {}).get(skill_key(requirement["name"]))
        if skill and skill["status"] in EVIDENCE:
            advanced = bool(re.search(r"熟练|精通|独立完成|advanced|expert", quote, re.I))
            partial = advanced and skill["level"] in {"基础", "自述"}
            return ("partial" if partial else "matched"), skill["status"], skill["sources"]
    if kind == "experience":
        matching = [value for value in person.get("experience", []) if normalize_text(requirement["name"]) == normalize_text(value)]
        if matching and not re.search(r"\d|至少|以上|全职", quote):
            return "matched", "self_reported", [{"quote": value} for value in matching]
    return "pending_not_provided", "unknown", []

def score(requirements: list[dict], person: dict, assessments: dict[int, str]) -> dict:
    rows = []
    for index, requirement in enumerate(requirements):
        status, evidence, sources = compare_requirement(requirement, person, assessments.get(index))
        dimension = DIMENSIONS.get(requirement["category"], requirement["category"])
        factor = {"matched": 1, "partial": .5, "unmet": 0}.get(status)
        points = None if factor is None else factor * EVIDENCE[evidence]
        rows.append({**requirement, "ordinal": index, "status": status, "evidence_status": evidence,
                     "sources": sources, "dimension": dimension, "points": points})
    dimensions = {}
    for name, weight in WEIGHTS.items():
        required = [row for row in rows if row["dimension"] == name and row["importance"] == "required"]
        rated = [row["points"] for row in required if row["points"] is not None]
        dimensions[name] = {"weight": weight, "score": round(100 * sum(rated) / len(rated), 2) if rated else None,
                            "required": len(required), "rated": len(rated)}
    scored = [item for item in dimensions.values() if item["score"] is not None]
    applicable = [item for item in dimensions.values() if item["required"]]
    overall = sum(item["weight"] * item["score"] for item in scored) / sum(item["weight"] for item in scored) if scored else None
    coverage = (100 * sum(item["weight"] * item["rated"] / item["required"] for item in applicable)
                / sum(item["weight"] for item in applicable)) if applicable else None
    hard = [row for row in rows if row["importance"] == "required"
            and (row["status"] != "matched" or row["evidence_status"] == "inferred")]
    conflicts = [row for row in hard if row["status"] == "unmet"]
    verdict = "当前匹配较低，建议先补足关键能力" if conflicts else "建议补充准备后投递" if hard or overall is None or overall < 70 else "可以尝试投递"
    return {"version": VERSION, "overall_score": round(overall, 2) if overall is not None else None,
            "evidence_coverage": round(coverage, 2) if coverage is not None else None,
            "dimensions": dimensions, "requirements": rows, "hard_flags": hard, "verdict": verdict}
