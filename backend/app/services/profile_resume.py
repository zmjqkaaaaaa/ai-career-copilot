from datetime import date
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.evidence import anchor_exists, lookup_blocks
from app.models.resume import Resume, ResumeContent
from app.schemas.career import StructuredResume
from app.schemas.profile import Experience, ProfileResumeDraft, ProfileWrite
from app.services.resume_education import YEAR_RANGE, degree_rank, enrollment_lines
from app.services.resume_sections import DATE_RANGE

SCHOOL = re.compile(r"^(?P<school>[\w ·]{2,48}?(?:大学|学院|学校))(?=[\s｜|：:（(]|$)")
MAJOR = re.compile(r"(?:专业\s*[：:]\s*|[　\t]|\s{2,})(?P<major>[^\d\n｜|]{2,50}?)(?:[　\t]|\s{2,}|$)")


def experience_draft(quotes: list[str]) -> list[Experience]:
    result = []
    for quote in quotes:
        title, _, details = quote.partition("\n")
        title = DATE_RANGE.sub("", YEAR_RANGE.sub("", title)).strip(" ·｜|")
        result.append(Experience(title=(title or quote)[:150], description=details or quote))
    return result


def resume_profile_draft(db: Session, user_id: int) -> ProfileResumeDraft | None:
    row = db.execute(select(Resume, ResumeContent).join(ResumeContent).where(
        Resume.user_id == user_id, Resume.parse_status != "deleting", ResumeContent.confirmed.is_(True),
    ).order_by(ResumeContent.id.desc()).limit(1)).first()
    if row is None:
        return None
    resume, content = row
    facts = StructuredResume.model_validate(content.structured_data or {})
    blocks = lookup_blocks(content.model_blocks or [])

    def quotes(group: str) -> list[str]:
        return [fact.original for fact in getattr(facts, group) if fact.source
                and fact.original == fact.source.quote and anchor_exists(fact.source, blocks)]

    education = quotes("education")
    education_fields = {}
    for quote in education:
        for line in quote.splitlines():
            rank = degree_rank(line)
            if not rank:
                continue
            prefix = "graduate" if rank >= 3 else "undergraduate"
            if school := SCHOOL.match(line):
                education_fields.setdefault(f"{prefix}_school", school["school"].strip())
            degree_tail = re.split(r"专科|大专|学士|本科|硕士|博士|研究生", line, maxsplit=1)[-1]
            if (major := MAJOR.search(degree_tail)) and major["major"].strip():
                education_fields.setdefault(f"{prefix}_major", major["major"].strip())
            if rank <= 2:
                education_fields.setdefault("undergraduate_degree", "本科" if rank == 2 else "专科")
    years = {int(years[2]) for quote in education for line in enrollment_lines(quote, date.today().year)
             if (years := YEAR_RANGE.search(line))}
    fields = ProfileWrite(**education_fields, graduation_year=next(iter(years)) if len(years) == 1 else None,
                          skills=list(dict.fromkeys(quote for quote in quotes("skills") if len(quote) <= 80))[:30],
                          internship_experience=experience_draft(quotes("internships")),
                          project_experience=experience_draft(quotes("projects")))
    return ProfileResumeDraft(resume_id=resume.id, content_id=content.id, filename=resume.original_filename,
                              version=content.version, education=education, fields=fields)
