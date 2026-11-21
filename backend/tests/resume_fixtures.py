from pathlib import Path
import argparse
import json

from docx import Document
from reportlab.pdfgen import canvas

DATA = Path(__file__).resolve().parent / "fixtures" / "resume_cases.json"

def cases() -> list[dict]:
    return json.loads(DATA.read_text(encoding="utf-8"))

def write_case(case: dict, destination: Path) -> Path:
    path = destination / f"{case['id']}.{case['format']}"
    destination.mkdir(parents=True, exist_ok=True)
    is_pdf = case["format"] == "pdf"
    groups = [
        ("Education" if is_pdf else "教育", [case["education"]]),
        ("Skills" if is_pdf else "技能", case["skills"]),
        ("Projects" if is_pdf else "项目", case["projects"]),
        ("Internships" if is_pdf else "实习", case["internships"]),
    ]
    contact = "Email: candidate@example.com"
    if is_pdf:
        pdf = canvas.Canvas(str(path))
        y = 790
        pdf.setFont("Helvetica", 12)
        for line in [contact, *(f"{group}: {', '.join(items)}" for group, items in groups if items), case["extra"]]:
            # Short lines make repeated extraction deterministic across PDF viewers.
            pdf.drawString(60, y, line)
            y -= 34
        pdf.save()
    else:
        document = Document()
        document.add_paragraph(contact)
        table = document.add_table(rows=0, cols=2)
        for group, items in groups:
            if items:
                row = table.add_row()
                row.cells[0].text, row.cells[1].text = group, "、".join(items)
        document.add_paragraph(case["extra"])
        document.save(path)
    return path

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate ten synthetic resumes for automated tests.")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    for case in cases():
        write_case(case, args.output)
    print(f"Generated {len(cases())} PDF/DOCX fixtures.")
