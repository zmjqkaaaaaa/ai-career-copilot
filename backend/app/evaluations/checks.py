"""Grade model replies against independent fixture labels and production guards."""
import re

from app.ai.evidence import anchor_exists, lookup_blocks, validate_extraction, validate_optimizations
from app.core.errors import ApiError
from app.schemas.career import StructuredResume
from app.schemas.discovery import PRD_FIELDS
from app.services.competitor_analysis_service import grounded_claim
from app.services.interview_evaluation_service import evaluate, excerpt
from app.services.job_matching_service import score
from app.services.job_parser import grounded_requirements, normalize_text
from app.services.learning_workflow import evidence_review
from app.services.pain_point_service import validate_pains
from app.services.project_recommendation_service import rank_projects


def contains_any(text, choices):
    return any(term.casefold() in text.casefold() for term in choices)


def resume_extraction(case, output):
    blocks = case.payload["blocks"]
    lookup = lookup_blocks(blocks)
    facts = [fact for key in StructuredResume.model_fields for fact in getattr(output, key)]
    required = case.expected["facts"]

    def field_hits(result):
        return sum(any(term.casefold() in item.original.casefold() for item in getattr(result, key))
                   for key, term in required.items())

    try:
        guarded, _ = validate_extraction(output.model_copy(deep=True), blocks)
    except ApiError as exc:
        if exc.code != "MODEL_EVIDENCE_INVALID":
            raise
        guarded = StructuredResume()
    hits = field_hits(guarded)
    return {"all_expected_fields_recovered": hits == len(required),
            "resume_facts_grounded": bool(facts) and all(fact.original == fact.source.quote and anchor_exists(fact.source, lookup)
                                                        for fact in facts if fact.source) and all(fact.source for fact in facts),
            "unsupported_fact_absent": all(not getattr(output, field) for field in case.expected["empty"])}, {
        "expected_fields": len(required), "grounded_fields_recovered": hits, "output_fact_count": len(facts),
    }


def resume_optimization(case, output):
    blocks = case.payload["blocks"]
    lookup = lookup_blocks(blocks)
    items = output.suggestions
    grounded = [item for item in items if anchor_exists(item.original, lookup)]
    guarded = validate_optimizations(grounded, blocks)
    terms = case.expected
    return {"optimization_quotes_grounded": bool(items) and len(grounded) == len(items),
            "unsupported_scope_absent": not any(contains_any(item.rewritten, terms["forbidden"]) for item in items),
            "usable_grounded_change": any(terms["retain"] in item.rewritten and not item.needs_evidence for item in guarded)}, {
        "output_suggestions": len(items), "grounded_suggestions": len(grounded),
        "guarded_or_withheld": len(items) - sum(not item.needs_evidence for item in guarded),
    }


def job_matching(case, output):
    source = case.payload["job_description"]
    expected = case.expected["requirements"]
    requirements = grounded_requirements(output.requirements, source)
    normal = {normalize_text(row.quote): row.importance for row in requirements}
    matches = sum(normal.get(normalize_text(quote)) == kind for quote, kind in expected.items())
    scored = score([row.model_dump() for row in requirements], case.expected["person"], {})
    hard = any(normalize_text(row["quote"]) == normalize_text(case.expected["must_fail"]) and row["status"] == "unmet"
               for row in scored["hard_flags"])
    return {"jd_quotes_grounded": bool(output.requirements) and all(
                normalize_text(row.quote) and normalize_text(row.quote) in normalize_text(source) for row in output.requirements),
            "jd_importance_preserved": matches == len(expected), "hard_gate_detected": hard}, {
        "expected_requirements": len(expected), "recovered_requirements": matches,
        "blocking_requirements": len(scored["hard_flags"]),
    }


def pain_discovery(case, output):
    messages = case.payload["messages"]
    sources = {item["id"]: item["text"] for item in messages}
    evidence = [entry for pain in output.pain_points for entry in pain.evidence]
    grounded = validate_pains(output.model_copy(deep=True), messages)
    return {"pain_present": bool(output.pain_points),
            "pain_quotes_grounded": bool(evidence) and all(
                entry.kind != "market_inference" and entry.detail in sources.get(entry.message_id, "") for entry in evidence),
            "reference_event_recovered": any(entry.message_id == case.expected["required_id"]
                                             for pain in grounded.pain_points for entry in pain.evidence),
            "retains_hypothesis_status": bool(output.pain_points) and all(
                pain.validation_status == "hypothesis" for pain in output.pain_points)}, {"claims": len(evidence)}


def competitor_research(case, output):
    sources = {row["id"]: row for row in case.payload["sources"]}
    claims = [getattr(row, key) for row in output.competitors
              for key in type(row).model_fields if key not in {"product_name", "official_source"} and getattr(row, key) is not None]
    claims += output.market_findings
    grounded = [item for claim in claims if (item := grounded_claim(claim.model_copy(deep=True), sources))]
    return {"competitor_claims_grounded": bool(claims) and len(grounded) == len(claims)
            and all(set(item["sources"]) == set(claim.sources) for item, claim in zip(grounded, claims)),
            "supported_feature_present": any(row.features and contains_any(row.features.text, case.expected["feature"])
                                             for row in output.competitors),
            "official_attribution_correct": all(row.official_source is None or
                                                sources.get(row.official_source, {}).get("source_type") == "official"
                                                for row in output.competitors)}, {
        "claims": len(claims), "grounded_claims": len(grounded),
    }


def project_recommendation(case, output):
    try:
        projects = rank_projects(output, case.payload["weekly_hours"])
    except ApiError as exc:
        if exc.code != "DISCOVERY_PROJECTS_TOO_SIMILAR":
            raise
        projects = []
    options = output.projects
    return {"different_projects": len(projects) >= case.expected["min_distinct"],
            "has_budget_fit": any(item["estimated_hours"] <= case.expected["weeks"] * case.payload["weekly_hours"] for item in projects),
            "feasibility_risk_present": all(bool(item.risks and item.deliverable) for item in options)}, {
        "projects": len(options), "distinct_directions": len({item.direction for item in options}),
    }


def prd(case, output):
    sections = output.sections
    acceptance = sections.get("acceptance", "")
    return {"required_prd_sections": set(sections) == set(PRD_FIELDS),
            "acceptance_has_fixture_numbers": all(re.search(rf"\b{number}\b|(?<!\d){number}(?!\d)", acceptance)
                                                    for number in case.expected["acceptance"]),
            "assumptions_visible": contains_any(sections.get("risks", ""), case.expected["risks"])}, {
        "expected_sections": len(PRD_FIELDS), "found_sections": len(set(sections) & set(PRD_FIELDS)),
    }


def code_explanation(case, output):
    evidence = {item["id"] for item in case.payload["evidence"]}
    factual = [item for item in output.sections if item.status in {"observed", "inferred"}]
    text = " ".join([output.overview] + [item.explanation for item in factual])
    return {"code_references_grounded": bool(factual) and all(item.references and set(item.references) <= evidence for item in factual),
            "call_chain_explained": all(symbol in text for symbol in case.expected["function_names"])
            and contains_any(text, ["调用", "call"]) and set(ref for item in factual for ref in item.references) == evidence,
            "empty_input_behavior": contains_any(text, case.expected["sentinels"]),
            "unsupported_effect_absent": not contains_any(text, case.expected["forbidden"])}, {
        "factual_sections": len(factual), "referenced_sections": sum(bool(item.references) for item in factual),
    }


def interview(case, output):
    answer = case.payload["answer"]
    rated = [item for item in output.ratings if item.level is not None]
    allowed = {item["key"] for item in case.payload["rubric"]}
    assessed = evaluate(case.expected["answer_type"], output, answer)
    asked_followup = output.action in {"follow_up", "probe_error"}
    return {"interview_scores_have_quotes": bool(rated) and all(
                item.dimension in allowed and excerpt(item.quote, answer) for item in rated),
            "grounded_score_for_correct_answer": assessed["score"] is not None and
                                                 assessed["score"] >= case.expected["score_min_when_scored"],
            "followup_anchored_when_present": not asked_followup or bool(
                excerpt(output.followup_quote, answer) and output.followup_reason and output.next_question),
            "actionable_practice_present": bool(output.exercise and output.acceptance)}, {
        "score": assessed["score"], "coverage": assessed["coverage"], "rated_dimensions": len(rated),
    }


def teaching(case, output):
    text = output.explanation + " " + output.example
    expected = case.expected
    return {"sql_granularity_correct": contains_any(text, expected["key_terms"])
            and contains_any(text, expected["entity"]) and not contains_any(text, expected["forbidden"]),
            "comprehension_question_present": bool(output.question and contains_any(output.question, ["岗位", "主键", "去重", "DISTINCT"])),
            "practical_next_step_present": bool(output.next_step and output.example),
            "no_unsupplied_resource_urls": not contains_any(" ".join(output.model_dump().values()), ["http://", "https://"])}, {}


def homework_evaluation(case, output):
    material = case.payload
    rated = [item for item in output.ratings if item.level is not None]
    reviewed = evidence_review(output, material)
    return {"homework_scores_have_quotes": bool(rated) and all(
                item.criterion in material["rubric"] and excerpt(item.quote, material["content"]) for item in rated),
            "failed_fixture_requires_revision": reviewed["status"] == "needs_revision",
            "feedback_recognizes_fixed_fixture": str(case.expected["expected"]) in " ".join(output.errors + [output.revision])}, {
        "fixture_expected": case.expected["expected"], "fixture_observed": case.expected["observed"], "score": reviewed["score"],
    }


def job_strategy(case, output):
    text = " ".join([output.current_state, *output.observations, *output.inferences, *output.hypotheses,
                     *output.priority_actions, output.next_goal])
    # A warning that a rate cannot be inferred is an uncertainty statement, not a rate claim.
    groups = [text for text in [output.current_state, *output.observations, *output.inferences] if not
              contains_any(text, ["不能", "无法", "不足以", "不宜", "不应", "不可", "尚不能"])]
    return {"no_unsupported_small_sample_judgment": not contains_any(" ".join(groups), case.expected["forbidden"]),
            "small_sample_disclosed": contains_any(text, ["样本", "数据有限", "记录较少", "仅一条", "仅 1 条"]),
            "collect_more_data_action": contains_any(" ".join(output.priority_actions), ["记录", "补记", "补录", "收集", "积累"])}, {
        "sample_size": case.payload["summary"]["valid"], "recommended_actions": len(output.priority_actions),
    }


CHECKS = {function.__name__: function for function in (
    resume_extraction, resume_optimization, job_matching, pain_discovery, competitor_research, project_recommendation,
    prd, code_explanation, interview, teaching, homework_evaluation, job_strategy,
)}
