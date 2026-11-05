"""Result compilation: totals, grades, highest/lowest, positions, term summaries, locking, annual."""
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from app.extensions import db
from app.errors import NotFoundError, ValidationError
from app.models import (ClassSession, StudentEnrollment, AssessmentComponent, Score, Result, GradingScale,
                        StudentTermReport, Term)
from app.services.authorization_service import require_operator, LOCKED_STATES
from app.services.audit_log import log_action
from app.services import traits_service

D = Decimal


def to_whole(x) -> int:
    """Marks are rounded to a whole number, .5 rounds up (so 89.5 -> 90)."""
    return int(D(x).quantize(D("1"), rounding=ROUND_HALF_UP))


def rank(values: list, value) -> int:
    """Standard competition ranking: two students tied for 3rd are both 3rd, the next is 5th."""
    return 1 + sum(1 for v in values if v > value)


def grading_scale_for(academic_session_id: int):
    scales = (GradingScale.query.filter_by(academic_session_id=academic_session_id)
              .order_by(GradingScale.id.desc()).all())
    if len(scales) > 1:
        raise ValidationError(
            "This academic session has more than one grading scale. Keep one scale for the session "
            "so every subject is graded consistently."
        )
    return scales[0] if scales else None


def grade_for(scale, total):
    if scale is None or total is None:
        return None, None
    for b in scale.boundaries:
        if b.min_score <= total <= b.max_score:
            return b.grade, b.remark
    return None, None


def slotted_components(class_subject_ids, term_id) -> dict:
    out = defaultdict(list)
    if class_subject_ids:
        q = AssessmentComponent.query.filter(AssessmentComponent.class_subject_id.in_(class_subject_ids),
                                             AssessmentComponent.term_id == term_id,
                                             AssessmentComponent.report_slot.isnot(None))
        for c in q.order_by(AssessmentComponent.report_slot):
            out[c.class_subject_id].append(c)
    return out


def compile_class_term(class_session_id: int, term_id: int) -> dict:
    """Recompute every student's subject totals, grades, class highest/lowest, positions, the overall
    average/position, and refresh suggested ratings. Locked subjects are left exactly as they were.
    Does not commit: it joins the caller's transaction."""
    cs = db.session.get(ClassSession, class_session_id)
    term = db.session.get(Term, term_id)
    if cs is None or term is None:
        raise NotFoundError("Class or term not found.")
    if term.academic_session_id != cs.academic_session_id:
        raise ValidationError("That term belongs to a different session.")

    enrollments = StudentEnrollment.query.filter_by(class_session_id=class_session_id).all()
    csub_ids = [x.id for x in cs.class_subjects]
    comps = slotted_components(csub_ids, term_id)
    comp_ids = [c.id for lst in comps.values() for c in lst]
    student_ids = [e.student_id for e in enrollments]

    scores = {}
    if comp_ids and student_ids:
        for s in Score.query.filter(Score.assessment_component_id.in_(comp_ids), Score.student_id.in_(student_ids)):
            scores[(s.student_id, s.assessment_component_id)] = D(s.score)

    existing = {}
    if csub_ids:
        for r in Result.query.filter(Result.term_id == term_id, Result.class_subject_id.in_(csub_ids)):
            existing[(r.student_id, r.class_subject_id)] = r
    locked = {csid for (_, csid), r in existing.items() if r.status in LOCKED_STATES}
    grading_scale = grading_scale_for(cs.academic_session_id)

    per_subject = defaultdict(list)                     # csid -> [(enrollment, result)]
    for enr in enrollments:
        for csid in {ss.class_subject_id for ss in enr.subjects}:
            if csid not in comps:
                continue
            r = existing.get((enr.student_id, csid))
            if csid in locked:
                if r is not None and r.total_score is not None:
                    per_subject[csid].append((enr, r))
                continue
            got = [(c, scores[(enr.student_id, c.id)]) for c in comps[csid] if (enr.student_id, c.id) in scores]
            if not got:
                if r is not None:
                    db.session.delete(r)
                continue
            # Every subject result is expressed out of 100. Central templates already
            # use weights totaling 100, but normalize older/custom snapshots too so
            # historical assessment structures cannot produce a subject total above
            # or below the 0-100 grading scale merely because their weights differ.
            weight_total = sum(c.weight for c in comps[csid])
            weighted_points = sum(v / c.max_score * c.weight for c, v in got)
            total = D(to_whole(weighted_points * D(100) / D(weight_total))) if weight_total else D(0)
            if r is None:
                r = Result(student_id=enr.student_id, class_subject_id=csid, term_id=term_id, status="DRAFT")
                db.session.add(r)
            r.total_score = total
            r.grade, r.remark = grade_for(grading_scale, total)
            per_subject[csid].append((enr, r))

    for csid, rows in per_subject.items():
        if csid in locked:
            continue
        # Subject positions are based on the students with an actual result for
        # that subject. A blank subject is not silently converted into a zero mark.
        totals = [r.total_score for _, r in rows]
        hi, lo = max(totals), min(totals)
        for _, r in rows:
            r.class_highest, r.class_lowest, r.position = hi, lo, rank(totals, r.total_score)

    # ---- overall figures per student
    # The class subject list defines the denominator, not the subset of subjects
    # for which this student happens to have a result. A subject with no recorded
    # result contributes zero obtained marks but still contributes 100 possible.
    summary = {}
    class_subject_count = len(csub_ids)
    obtainable = D(class_subject_count * 100) if class_subject_count else None
    for enr in enrollments:
        got = [(csid, r) for csid, rows in per_subject.items() for e, r in rows if e.id == enr.id]
        if not got or not class_subject_count:
            summary[enr.id] = None
            continue
        obtained = sum((r.total_score for _, r in got if r.total_score is not None), D(0))
        average = (D(obtained) / obtainable * 100).quantize(D("0.01"), rounding=ROUND_HALF_UP)
        summary[enr.id] = (D(obtained), obtainable, average)
    averages = [v[2] for v in summary.values() if v is not None and v[2] is not None]
    reports = {r.enrollment_id: r for r in StudentTermReport.query.filter_by(term_id=term_id)
               .filter(StudentTermReport.enrollment_id.in_([e.id for e in enrollments] or [0]))}
    for enr in enrollments:
        rep = reports.get(enr.id)
        s = summary[enr.id]
        if rep is None:
            if s is None:
                continue
            rep = StudentTermReport(enrollment_id=enr.id, term_id=term_id)
            db.session.add(rep)
        if s is None:
            rep.total_obtained = rep.total_obtainable = rep.average = rep.position = None
            rep.class_size = len(enrollments)
            continue
        rep.total_obtained, rep.total_obtainable, rep.average = s
        rep.position = rank(averages, s[2]) if s[2] is not None else None
        rep.class_size = len(enrollments)
        traits_service.refresh_auto(enr.id, term_id, s[2])
    db.session.flush()
    return {"students": len(enrollments), "subjects": len(per_subject)}


def class_term_summary(class_session_id: int, term_id: int) -> dict:
    """Numbers for the class page: how complete is score entry, what is locked."""
    cs = db.session.get(ClassSession, class_session_id)
    csub_ids = [x.id for x in cs.class_subjects]
    comps = slotted_components(csub_ids, term_id)
    results = Result.query.filter(Result.term_id == term_id, Result.class_subject_id.in_(csub_ids or [0])).all()
    locked_ids = {r.class_subject_id for r in results if r.status in LOCKED_STATES}
    return {"subjects_with_assessments": len(comps), "subjects_total": len(csub_ids),
            "results": len(results), "locked_subjects": len(locked_ids),
            "all_locked": bool(comps) and all(c in locked_ids for c in comps)}


# --------------------------------------------------------------------------------- locking
def set_lock(actor, *, class_session_id: int, term_id: int, lock: bool, class_subject_id: int | None = None) -> int:
    """Lock (nobody can edit scores) or unlock (REOPENED, editable again) a whole class's term, or one subject."""
    require_operator(actor)
    cs = db.session.get(ClassSession, class_session_id)
    if cs is None:
        raise NotFoundError("Class not found.")
    compile_class_term(class_session_id, term_id)
    targets = [x for x in cs.class_subjects if class_subject_id in (None, x.id)]
    if class_subject_id is not None and not targets:
        raise NotFoundError("Subject is not in this class.")
    comps = slotted_components([x.id for x in targets], term_id)
    changed = 0
    for csub in targets:
        if csub.id not in comps:
            continue
        rows = {r.student_id: r for r in Result.query.filter_by(class_subject_id=csub.id, term_id=term_id)}
        if lock:
            for enr in cs.student_enrollments:
                if csub.id in {ss.class_subject_id for ss in enr.subjects} and enr.student_id not in rows:
                    r = Result(student_id=enr.student_id, class_subject_id=csub.id, term_id=term_id, status="DRAFT")
                    db.session.add(r)
                    rows[enr.student_id] = r
            for r in rows.values():
                if r.status not in LOCKED_STATES:
                    r.status = "LOCKED"
                    changed += 1
        else:
            for r in rows.values():
                if r.status == "LOCKED":
                    r.status = "REOPENED"
                    changed += 1
    db.session.flush()
    if not lock:
        compile_class_term(class_session_id, term_id)     # drops the empty placeholder rows
    scope = "all subjects" if class_subject_id is None else f"class subject {class_subject_id}"
    log_action(actor.id, "LOCK_RESULTS" if lock else "UNLOCK_RESULTS", "ClassSession", class_session_id,
               f"{'Locked' if lock else 'Unlocked'} {scope} for term {term_id} ({changed} results)")
    db.session.commit()
    return changed


# --------------------------------------------------------------------------------- annual
def annual_class(class_session_id: int) -> dict:
    """Annual figures for every student of a class, computed on demand (nothing stored).
    Subject annual mark = average of the terms that have a total, rounded to a whole number.
    Returns {enrollment_id: {"subjects": {csid: {...}}, "obtained", "obtainable", "average", "position", "class_size"}}"""
    cs = db.session.get(ClassSession, class_session_id)
    if cs is None:
        raise NotFoundError("Class not found.")
    terms = Term.query.filter_by(academic_session_id=cs.academic_session_id).order_by(Term.id).limit(3).all()
    term_ids = [t.id for t in terms]
    csub_ids = [x.id for x in cs.class_subjects]
    enrollments = StudentEnrollment.query.filter_by(class_session_id=class_session_id).all()
    by_student = {e.student_id: e for e in enrollments}

    totals = defaultdict(dict)                          # (student_id, csid) -> {term_id: total}
    if csub_ids and term_ids:
        for r in Result.query.filter(Result.class_subject_id.in_(csub_ids), Result.term_id.in_(term_ids),
                                     Result.total_score.isnot(None), Result.student_id.in_(list(by_student) or [0])):
            totals[(r.student_id, r.class_subject_id)][r.term_id] = r.total_score
    out = {e.id: {"subjects": {}, "terms": terms} for e in enrollments}
    for (sid, csid), per_term in totals.items():
        e = by_student[sid]
        avg = D(to_whole(sum(per_term.values()) / len(per_term)))
        out[e.id]["subjects"][csid] = {"per_term": per_term, "average": avg, "obtainable": D(100)}

    # Subject positions compare students with an annual result recorded in that subject.
    by_subject = defaultdict(list)
    for d in out.values():
        for csid, sdata in d["subjects"].items():
            by_subject[csid].append(sdata["average"])
    for d in out.values():
        for csid, sdata in d["subjects"].items():
            vals = by_subject[csid]
            sdata["highest"], sdata["lowest"], sdata["position"] = max(vals), min(vals), rank(vals, sdata["average"])

    # Annual overall totals use one 100-mark annual average per class subject.
    # Subjects with no annual result contribute zero obtained but remain possible.
    annual_obtainable = D(len(csub_ids) * 100) if csub_ids else D(0)
    for d in out.values():
        d["obtained"] = sum((s["average"] for s in d["subjects"].values()), D(0))
        d["obtainable"] = annual_obtainable
        d["average"] = (
            (d["obtained"] / annual_obtainable * 100).quantize(D("0.01"), rounding=ROUND_HALF_UP)
            if annual_obtainable and d["subjects"] else None
        )
        d["class_size"] = len(enrollments)
    avgs = [d["average"] for d in out.values() if d["average"] is not None]
    for d in out.values():
        d["position"] = rank(avgs, d["average"]) if d["average"] is not None else None
    return out
