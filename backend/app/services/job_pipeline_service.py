from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select

from app.core.errors import ApiError
from app.models.application import ApplicationStatusHistory, InterviewSchedule, JobApplication, ResumeVersion
from app.services.application_tracking_service import STATUSES
from app.services.resumes import utc_now

INTERVIEW_STAGES = {"interview_1", "interview_2", "hr_interview"}
MIN_SAMPLE = 5


def application_query(user_id):
    return select(JobApplication).where(JobApplication.user_id == user_id)


def period_bounds(period):
    start = period.start or date(2000, 1, 1)
    end = period.end or utc_now().date()
    if not date(1900, 1, 1) <= start <= end < date(9999, 12, 31):
        raise ApiError(422, "ANALYTICS_PERIOD_INVALID", "请选择有效的开始和结束日期")
    return start, end


def metrics(entries):
    sent = len(entries)
    valid = sum(item["valid"] for item in entries)
    keys = ("resume_passed", "written_test", "written_passed", "invited", "interview_decided", "interview_passed", "offer")
    results = {"submitted": sent, "valid": valid,
               **{key: sum(item["valid"] and item[key] for item in entries) for key in keys}}
    results["rates"] = {}
    for key, base in (("resume_passed", "valid"), ("written_passed", "written_test"),
                      ("invited", "valid"), ("interview_passed", "interview_decided"), ("offer", "valid")):
        numerator, denominator = results[key], results[base]
        results["rates"][key] = {"numerator": numerator, "denominator": denominator,
                                 "rate": round(numerator / denominator, 4) if denominator >= MIN_SAMPLE else None}
    return results


def analytics(db, user_id, period):
    start, end = period_bounds(period)
    lower = datetime.combine(start, time.min)
    upper = datetime.combine(end + timedelta(days=1), time.min)
    cohort = application_query(user_id).where(JobApplication.applied_at >= lower, JobApplication.applied_at < upper)
    applications = db.execute(cohort.with_only_columns(
        JobApplication.id, JobApplication.applied_at, JobApplication.resume_version_id,
        JobApplication.valid_submission, JobApplication.snapshot["position"].as_string().label("position"),
    )).mappings().all()
    ids = cohort.with_only_columns(JobApplication.id)
    history = defaultdict(set)
    for identifier, status in db.execute(select(ApplicationStatusHistory.application_id, ApplicationStatusHistory.new_status)
                                         .where(ApplicationStatusHistory.application_id.in_(ids)).distinct()):
        history[identifier].add(status)
    interviews = defaultdict(set)
    for identifier, outcome in db.execute(select(InterviewSchedule.application_id,
                                                 InterviewSchedule.details["result"].as_string()).where(
        InterviewSchedule.user_id == user_id, InterviewSchedule.application_id.in_(ids),
    ).distinct()):
        if outcome:
            interviews[identifier].add(outcome)
    version_ids = {row.resume_version_id for row in applications if row.resume_version_id is not None}
    names = dict(db.execute(select(ResumeVersion.id, ResumeVersion.version_name).where(
        ResumeVersion.user_id == user_id, ResumeVersion.id.in_(version_ids)
    )).all()) if version_ids else {}
    by_position, by_resume = defaultdict(list), defaultdict(list)
    trend = Counter()
    entries = []
    for row in applications:
        seen, outcomes = history[row.id], interviews[row.id]
        invited = bool(seen & INTERVIEW_STAGES or outcomes - {"cancelled"})
        entry = {
            "valid": row.valid_submission, "resume_passed": "written_test" in seen or invited,
            "written_test": "written_test" in seen, "written_passed": "written_test" in seen and invited,
            "invited": invited, "interview_decided": bool(outcomes & {"passed", "failed"}),
            "interview_passed": "passed" in outcomes, "offer": "offer" in seen,
        }
        entries.append(entry)
        by_position[row.position if row.position and row.position != "null" else "未知岗位"].append(entry)
        by_resume[row.resume_version_id].append(entry)
        trend[row.applied_at.date().isoformat()] += 1
    summary = metrics(entries)
    return {"start": start.isoformat(), "end": end.isoformat(), "summary": summary,
            "minimum_sample": MIN_SAMPLE, "sample_insufficient": summary["valid"] < MIN_SAMPLE,
            "trend": [{"date": key, "count": count} for key, count in sorted(trend.items())],
            "by_position": [{"label": key, **metrics(items)} for key, items in sorted(by_position.items())],
            "by_resume": [{"id": key, "label": names.get(key, "未选版本"), **metrics(items)}
                          for key, items in sorted(by_resume.items(), key=lambda group: group[0] or 0)]}


def board_query(user_id, limit):
    stmt = application_query(user_id)
    if limit is not None:
        ranked = stmt.with_only_columns(JobApplication.id, func.row_number().over(
            partition_by=JobApplication.current_status, order_by=(JobApplication.updated_at.desc(), JobApplication.id.desc())
        ).label("position")).subquery()
        stmt = stmt.join(ranked, ranked.c.id == JobApplication.id).where(ranked.c.position <= limit + 1)
    return stmt.order_by(JobApplication.updated_at.desc(), JobApplication.id.desc())


def actions_query(user_id):
    action = JobApplication.metadata_json["next_action"].as_string()
    return application_query(user_id).where(
        JobApplication.current_status.not_in(("offer", "rejected", "withdrawn")),
        action.is_not(None), action.not_in(("null", "")),
    ).order_by(JobApplication.updated_at.desc(), JobApplication.id.desc()).limit(5)
