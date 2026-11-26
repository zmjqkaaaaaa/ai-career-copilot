"""Compare explicit weekly internship days in the selected resume and JD."""
import re

WEEKLY_DAYS = re.compile(
    r"(?:每\s*[周週]|一\s*[周週])\s*"
    r"(?:(?:至少|不少于|不低于|超过|多于|可(?:以|保证)?|能|需(?:要)?|实习|到岗|出勤|工作)\s*){0,5}"
    r"(?P<days>[1-7１-７一二两兩三四五六七])\s*[天日]"
    r"(?:\s*(?:及以上|或以上|以上|起))?"
)
NUMBERS = dict(zip("一二两兩三四五六七", (1, 2, 2, 2, 3, 4, 5, 6, 7)))
MONTH_NUMBERS = {**NUMBERS, "八": 8, "九": 9, "十": 10, "十一": 11, "十二": 12}
INTERNSHIP_MONTHS = re.compile(
    r"(?:(?:可(?:以)?|至少|连续|持续)\s*(?:持续|连续)?\s*实习|实习(?:时长|周期)\s*[：:]?)\s*"
    r"(?P<minimum>至少|不少于|不低于|超过)?\s*"
    r"(?P<months>[0-9０-９]{1,2}|十[一二]?|[一二两兩三四五六七八九])\s*个?\s*月"
    r"(?P<above>\s*(?:及以上|或以上|以上|起))?"
)
DECLARATION = re.compile(r"可|能|实习安排|到岗安排|实习时间|到岗时间")
PREVIOUS_OR_UNCERTAIN = re.compile(r"曾|此前|之前|上段|过去|预计|计划|希望|争取|尚不确定|无法|不能|不可|未能|不保证|不一定|至少|不少于|不低于|以上|[~～—]|左右|约|至多|最多|仅")
OTHER_CONDITION = re.compile(
    r"[0-9０-９一二两三四五六七八九十]\s*(?:个?\s*月|周|天|日)|"
    r"[-~～—]|左右|以下|以内|届|开始日期|尽快|随时|立即|长期|全职|工作日|周末|[或至到]\s*[1-7一二两三四五六七]"
)


def weekly_days(match: re.Match) -> int:
    value = match["days"]
    return NUMBERS[value] if value in NUMBERS else int(value)


def resume_weekly_availability(blocks: list[dict]) -> list[dict]:
    statements = []
    for block in blocks:
        for clause in re.split(r"[；;。！!？?\n|｜，,]", block["text"]):
            if not DECLARATION.search(clause) or PREVIOUS_OR_UNCERTAIN.search(clause):
                continue
            for match in WEEKLY_DAYS.finditer(clause):
                if OTHER_CONDITION.match(clause[match.end():].lstrip()):
                    continue
                statement = {"days": weekly_days(match), "block_number": block["number"], "quote": match[0]}
                if statement not in statements:
                    statements.append(statement)
    return statements


def compare_weekly_availability(quote: str, statements: list[dict]):
    required = list(WEEKLY_DAYS.finditer(quote))
    if len(required) != 1 or not statements:
        return "pending_not_provided", "unknown", []
    match = required[0]
    surrounding = quote[:match.start()] + quote[match.end():]
    if re.search(r"最多|至多|不超过|少于|低于|固定|仅限|约|不要求|不需|无需|不必", surrounding):
        return "pending_no_evidence", "unknown", []
    minimum = weekly_days(match) + int(bool(re.search(r"超过|多于", match[0])))
    sources = [{"block_number": item["block_number"], "quote": item["quote"]} for item in statements[:3]]
    days = {item["days"] for item in statements}
    if len(days) != 1 or re.match(r"\s*(?:左右|以下|以内|[~～—-]|(?:至|到|或)\s*[1-7一二两三四五六七])", quote[match.end():]):
        return "pending_no_evidence", "unknown", sources
    if OTHER_CONDITION.search(surrounding) and re.search(r"或者|或", surrounding):
        return "pending_no_evidence", "unknown", sources
    if next(iter(days)) < minimum:
        return "unmet", "self_reported", sources
    status = "partial" if OTHER_CONDITION.search(surrounding) else "matched"
    return status, "self_reported", sources


def internship_months(match: re.Match) -> int:
    value = match["months"]
    return MONTH_NUMBERS[value] if value in MONTH_NUMBERS else int(value)


def resume_internship_duration(blocks: list[dict]) -> list[dict]:
    statements = []
    for block in blocks:
        for clause in re.split(r"[；;。！!？?\n|｜，,]", block["text"]):
            for match in INTERNSHIP_MONTHS.finditer(clause):
                surrounding = clause[:match.start()] + clause[match.end():]
                if PREVIOUS_OR_UNCERTAIN.search(surrounding) or re.search(r"上[一段]|上一份|历时|共计|累计|左右|以内|[-–～~]", surrounding):
                    continue
                lower_bound = bool(match["minimum"] or match["above"] or match[0].startswith("至少"))
                statement = {"months": internship_months(match) + int(match["minimum"] == "超过"),
                             "lower_bound": lower_bound, "block_number": block["number"], "quote": match[0]}
                if statement not in statements:
                    statements.append(statement)
    return statements


def compare_availability(quote: str, weekly: list[dict], durations: list[dict]):
    months = list(INTERNSHIP_MONTHS.finditer(quote))
    if not months:
        return compare_weekly_availability(quote, weekly)
    month = months[0]
    remaining = quote[:month.start()] + quote[month.end():]
    if len(months) != 1 or re.search(r"或|最多|至多|不超过|少于|低于|左右|以内|[-–～~]|不要求|无需", remaining):
        return "pending_no_evidence", "unknown", []
    minimum = internship_months(month) + int(month["minimum"] == "超过")
    sources = [{"block_number": item["block_number"], "quote": item["quote"]} for item in durations[:3]]
    limits = {item["months"] for item in durations}
    duration_status = "pending_no_evidence" if sources else "pending_not_provided"
    if len(limits) == 1:
        if next(iter(limits)) >= minimum:
            duration_status = "matched"
        elif not any(item["lower_bound"] for item in durations):
            duration_status = "unmet"
    if WEEKLY_DAYS.search(remaining):
        week_status, _, week_sources = compare_weekly_availability(remaining, weekly)
        sources.extend(week_sources)
        statuses = {duration_status, week_status}
        if "unmet" in statuses:
            return "unmet", "self_reported", sources
        if statuses == {"matched"}:
            return "matched", "self_reported", sources
        if statuses & {"matched", "partial"}:
            return "partial", "self_reported", sources
        return "pending_no_evidence" if sources else "pending_not_provided", "unknown", sources
    if duration_status == "matched" and OTHER_CONDITION.search(remaining):
        duration_status = "partial"
    return duration_status, "unknown" if duration_status.startswith("pending") else "self_reported", sources
