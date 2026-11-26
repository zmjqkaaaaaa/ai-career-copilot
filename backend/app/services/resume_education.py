import re
from datetime import date

DEGREES = (("大专", "专科"), ("本科", "学士"), ("硕士", "研究生"), ("博士",))
YEAR_RANGE = re.compile(r"(?<!\d)(20\d{2})(?:[.年/-]\d{1,2}(?:月)?)?\s*(?:至|到|[-–—~～])\s*(20\d{2})(?!\d)")
COMPLETED = re.compile(r"已毕业|已结业|已退学|休学|不再在读|非在读|曾在读")
DATE_LINE = re.compile(r"^[ \t]*(?:就读时间\s*[：:]\s*)?20\d{2}")


def degree_rank(text: str) -> int | None:
    for index, labels in reversed(list(enumerate(DEGREES, 1))):
        if any(label in text for label in labels):
            return index
    return None


def enrollment_lines(text: str, year: int) -> list[str]:
    entries = []
    lines = text.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if not degree_rank(line) or COMPLETED.search(line):
            continue
        years = YEAR_RANGE.search(line)
        if not years and index + 1 < len(lines) and DATE_LINE.match(lines[index + 1]) and not COMPLETED.search(lines[index + 1]):
            # PDF date columns can appear on the next extracted line of the same entry.
            if next_years := YEAR_RANGE.search(lines[index + 1]):
                if not degree_rank(lines[index + 1]):
                    years = next_years
                    line += lines[index + 1]
        explicit = re.search(r"在读|在校|就读中|\d{2}\s*(?:至|到|[-–—])\s*(?:至今|现在)", line)
        if explicit or (years and int(years[1]) <= year < int(years[2])):
            entries.append(line.strip())
    return entries
