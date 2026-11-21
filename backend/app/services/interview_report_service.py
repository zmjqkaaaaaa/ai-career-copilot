from collections import defaultdict

from sqlalchemy import select

from app.models.interview import InterviewAnswer, InterviewQuestion, InterviewReport
from app.services.interview_evaluation_service import VERSION
from app.services.interview_training_service import make_tasks
from app.services.resumes import utc_now


def finish(db, session, reason):
    existing = db.scalar(select(InterviewReport).where(InterviewReport.session_id == session.id))
    if existing is not None:
        return existing
    session.state = "finished"
    session.finished_at = utc_now()
    session.finish_reason = reason
    session.revision += 1
    pairs = db.execute(select(InterviewQuestion, InterviewAnswer)
                       .join(InterviewAnswer, InterviewAnswer.question_id == InterviewQuestion.id)
                       .where(InterviewQuestion.session_id == session.id).order_by(InterviewQuestion.ordinal))
    turns, stages, dimensions = [], defaultdict(list), defaultdict(list)
    for question, answer in pairs:
        turn = {"question_id": question.id, "question": question.data["question"], "stage": question.stage,
                "knowledge_point": question.data["knowledge_point"], "answer": answer.text,
                "basis": question.data["basis"], "references": question.data["references"], **answer.data}
        turns.append(turn)
        stages[question.stage].append(turn)
        for row in answer.data["ratings"]:
            dimensions[(question.data["type"], row["key"], row["label"])].append(row["score"])

    def average(values):
        values = [item for item in values if item is not None]
        return round(sum(values) / len(values), 2) if values else None

    def summary(rows):
        coverage = average([row["coverage"] for row in rows])
        weighted = [(row["score"], row["coverage"]) for row in rows
                    if row["score"] is not None and row["coverage"] >= 50]
        total = sum(weight for _, weight in weighted)
        score = round(sum(value * weight for value, weight in weighted) / total, 2) if total and coverage >= 50 else None
        return {"score": score, "coverage": coverage, "answered": len(rows)}

    strengths = [{"question_id": row["question_id"], "knowledge_point": row["knowledge_point"], "feedback": row["strengths"]}
                 for row in turns if (row["score"] or 0) >= 80 and row["coverage"] >= 50 and row["strengths"]]
    weaknesses = [{"question_id": row["question_id"], "knowledge_point": row["knowledge_point"], "feedback": row["missing"],
                   "knowledge": row["corrected_idea"], "exercise": row["exercise"], "acceptance": row["acceptance"]}
                  for row in turns if row["score"] is None or row["score"] < 80 or row["coverage"] < 50]
    report = InterviewReport(session_id=session.id, data={
        **summary(turns), "mode": session.settings["mode"], "target": session.target, "finish_reason": reason,
        "duration_seconds": min(session.settings["minutes"] * 60, max(0, int(
            (session.finished_at - session.started_at).total_seconds()))) if session.started_at else 0,
        "dimensions": [{"type": kind, "key": key, "label": label, "score": average(values),
                        "evidence_count": sum(value is not None for value in values)}
                       for (kind, key, label), values in dimensions.items()],
        "stages": {key: summary(items) for key, items in stages.items()},
        "strengths": strengths, "weaknesses": weaknesses, "turns": turns,
        "sources": session.context["sources"], "rubric_version": VERSION,
        "contributions": [row["contribution_claim"] for row in turns if row.get("contribution_claim")],
        "practice_evidence": [row["text"] for row in session.context["refs"] if row["kind"] == "practice"],
        "unassessed_stages": [item["stage"] for item in session.context["schedule"] if item["stage"] not in stages],
    })
    db.add(report)
    db.flush()
    make_tasks(db, session, report, turns)
    return report
