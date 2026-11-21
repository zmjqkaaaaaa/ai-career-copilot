"""Evaluate only synthesized job descriptions against the configured provider."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
from app.ai.provider import Provider
from app.core.config import get_settings
from app.services.job_matching_service import score
from app.services.job_parser import parse_jd
from job_cases import CASES

def evaluate(case):
    name, expected, person, assessments, reference = case
    jd = "虚构岗位：AI 产品实习生。负责用户调研。\n" + "。\n".join(row["quote"] for row in expected) + "。"
    provider = Provider(get_settings())
    try:
        parsed = parse_jd(provider, {"job_description": jd})
        actual = {(row["quote"].strip("。"), row["importance"]) for row in parsed["requirements"]}
        result = score(expected, person, assessments)
        return {"case": name, "matched_requirements": sum((row["quote"], row["importance"]) in actual for row in expected),
                "expected_requirements": len(expected), "duty_found": bool(parsed["duties"]),
                "score": result["overall_score"], "coverage": result["evidence_coverage"],
                "reference": reference, "scoring_passed": (result["overall_score"], result["evidence_coverage"]) == reference}
    except Exception as exc:
        return {"case": name, "error": getattr(exc, "code", type(exc).__name__)}
    finally:
        provider.close()

if __name__ == "__main__":
    destination = Path(sys.argv[1])
    destination.parent.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(3) as pool:
        results = list(pool.map(evaluate, CASES))
    destination.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(results, ensure_ascii=True))
    sys.exit(any("error" in row for row in results))
