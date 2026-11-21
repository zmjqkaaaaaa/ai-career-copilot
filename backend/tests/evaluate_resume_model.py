"""Measure reference phrase recovery and evidence checks against the configured live API."""
from concurrent.futures import ThreadPoolExecutor
import argparse
import json
from pathlib import Path

from app.ai.evidence import facts_for_model, redact_blocks, validate_analysis, validate_extraction, validate_optimizations
from app.ai.prompts import ANALYZE, EXTRACT, OPTIMIZE
from app.ai.provider import Provider
from app.core.config import get_settings
from app.core.errors import ApiError
from app.schemas.career import CareerResult, OptimizationResult, StructuredResume
from app.services.resume_parser import parse_resume
from resume_fixtures import cases, write_case

def evaluate(case: dict, directory: Path) -> dict:
    path = write_case(case, directory)
    blocks = redact_blocks(parse_resume(path, case["format"]))
    provider = Provider(get_settings())
    result = {"id": case["id"], "persona": case["persona"]}
    try:
        raw = provider.generate(EXTRACT, {"blocks": blocks}, StructuredResume)
        structured, dropped = validate_extraction(raw, blocks)
        criteria = {"education": [case["education"].split("|")[0].split("｜")[0].strip()],
                    **{group: case[group] for group in ("skills", "projects", "internships")}}
        fields = {}
        for group, expected in criteria.items():
            text = " ".join(item.original + " " + (item.normalized or "") for item in getattr(structured, group)).casefold()
            fields[group] = {
                "matched": sum(item.casefold() in text for item in expected), "expected": len(expected),
                "unexpected_nonempty": not expected and bool(text),
            }
        result.update(fields=fields, invalid_quotes_dropped=dropped)
        if case["id"][:2] in {"02", "08", "10"}:
            payload = {"blocks": blocks, "facts": facts_for_model(structured.model_dump(mode="json")), "target_direction": "AI 产品经理"}
            report = validate_analysis(provider.generate(ANALYZE, payload, CareerResult), blocks)
            expected_sql = "self_reported" if "SQL" in case["skills"] else "unknown"
            sql_status = next(skill.status for skill in report.skills if skill.name == "SQL")
            result["career"] = {"sql_expected": expected_sql, "sql_status": sql_status,
                                "verified": sum(skill.status == "verified" for skill in report.skills)}
            raw_optimizations = provider.generate(OPTIMIZE, payload, OptimizationResult)
            validated = validate_optimizations(raw_optimizations.suggestions, blocks)
            result["optimization"] = {"suggestions": len(validated),
                                      "requires_evidence": sum(item.needs_evidence for item in validated),
                                      "withheld": len(raw_optimizations.suggestions) - len(validated),
                                      "changed_by_guard": sum(item.reason.startswith("改写中有原句无法核对") for item in validated)}
    except ApiError as exc:
        result["error"] = exc.code
    except Exception as exc:
        result["error"] = type(exc).__name__
    finally:
        provider.close()
    return result

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda case: evaluate(case, args.output.parent / "fixtures"), cases()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    totals = {group: [sum(row.get("fields", {}).get(group, {}).get(key, 0) for row in results)
                      for key in ("matched", "expected", "unexpected_nonempty")]
              for group in ("education", "skills", "projects", "internships")}
    print(json.dumps({"model": get_settings().llm_model, "10_cases": totals,
                      "reviewed": [row for row in results if row.get("career") or row.get("error")],
                      "checked_quotes_dropped": sum(row.get("invalid_quotes_dropped", 0) for row in results)}, ensure_ascii=True))
    if any("error" in row for row in results):
        raise SystemExit(1)

if __name__ == "__main__":
    main()
