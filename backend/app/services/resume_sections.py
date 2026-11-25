"""Keep the source text and group entries using explicit resume headings."""
import re

HEADINGS = {
    "教育经历": "education", "教育背景": "education", "教育": "education", "education": "education",
    "实习经历": "internships", "实习经验": "internships", "实习": "internships", "internships": "internships",
    "项目经历": "projects", "项目经验": "projects", "项目": "projects", "projects": "projects",
    "专业技能": "skills", "技术能力": "skills", "技能": "skills", "skills": "skills",
    "荣誉证书": "certificates", "证书": "certificates", "语言能力": "languages", "竞赛经历": "competitions",
    "竞赛与荣誉": "competitions", "工作经历": "other_experiences", "工作经验": "other_experiences",
    "其他信息": None, "其他经历": None, "个人简介": None, "自我评价": None,
    "校园经历": None, "在校经历": None, "社会实践": None, "志愿经历": None, "代表性研究": None,
}
ENTRY_SECTIONS = {"education", "internships", "projects", "other_experiences"}
DATE = r"(?:19|20)\d{2}\s*[./年\-]\s*(?:0?[1-9]|1[0-2])\s*月?"
DATE_RANGE = re.compile(rf"{DATE}\s*(?:[-–—~～]|至|到)\s*(?:{DATE}|至今|现在|present)\s*$", re.I)
INLINE_SKILLS = re.compile(r"^\s*[•●▪\uf09f]?\s*(?:技术能力|专业技能|技能)\s*[：:]\s*(\S.*)$")
EDUCATION_HEADER = re.compile(r"^[\w ·]{1,50}(?:大学|学院|学校)(?:[（(][^）)]{1,24}[）)])?$")
BULLETS = ("•", "●", "▪", "-", "\uf09f", "")
INTERNSHIP_ROLE = re.compile(r"[（(]实习[）)]|实习生|实习工程师")
MAX_QUOTE_LENGTH = 1200


def split_section_blocks(parts):
    section = None
    lines = []
    location = None
    dated_entry = False
    awaiting_education_dates = False

    def flush():
        value = "\n".join(lines).strip()
        lines.clear()
        if value:
            group = section
            if section == "other_experiences" and dated_entry and INTERNSHIP_ROLE.search(value.split("\n", 1)[0]):
                group = "internships"
            for start in range(0, len(value), MAX_QUOTE_LENGTH):
                if chunk := value[start:start + MAX_QUOTE_LENGTH].strip():
                    yield location, chunk, group

    for part_location, text in parts:
        if not dated_entry:
            yield from flush()
        for line in text.splitlines():
            heading = line.strip().rstrip("：:").strip().casefold()
            dated_line = section in ENTRY_SECTIONS and DATE_RANGE.search(line) and not line.lstrip().startswith(BULLETS)
            institution = section == "education" and EDUCATION_HEADER.fullmatch(re.split(r"\s{2,}", line.strip(), 1)[0])
            if heading in HEADINGS:
                yield from flush()
                yield part_location, line.strip(), None
                section = HEADINGS[heading]
                dated_entry = False
                awaiting_education_dates = False
                location = part_location
                continue
            if section not in ENTRY_SECTIONS and (skills := INLINE_SKILLS.match(line)):
                yield from flush()
                yield part_location, line[:skills.start(1)].strip(), None
                yield part_location, skills[1].strip(), "skills"
                continue
            if institution or dated_line:
                if institution or not awaiting_education_dates:
                    yield from flush()
                dated_entry = True
            if not lines:
                location = part_location
            lines.append(line)
            if line.strip():
                awaiting_education_dates = bool(institution and not dated_line)
    yield from flush()
