"""Entering and correcting scores (operator now; staff reuse this later with their own permission check)."""
from decimal import Decimal, InvalidOperation
from app.extensions import db
from app.errors import NotFoundError, ValidationError, PermissionDenied
from app.models import (StudentEnrollment, Term, AssessmentComponent, Score, ClassSubject, StudentTermReport, Result)
from app.report_labels import SCORE_COLUMNS
from app.services import authorization_service as authz, result_service, traits_service
from app.services.audit_log import log_action

D = Decimal


def entry_sheet(enrollment: StudentEnrollment, term: Term) -> list[dict]:
    """The grid for one student and one term: a row per subject they take, 4 cells (1'st CA ... Exams)."""
    csubs = sorted((ss.class_subject for ss in enrollment.subjects), key=lambda c: c.subject.name)
    comps = result_service.slotted_components([c.id for c in csubs], term.id)
    ids = [c.id for lst in comps.values() for c in lst]
    scores = {}
    if ids:
        for s in Score.query.filter(Score.student_id == enrollment.student_id, Score.assessment_component_id.in_(ids)):
            scores[s.assessment_component_id] = D(s.score)
    results = {r.class_subject_id: r for r in Result.query.filter(
        Result.student_id == enrollment.student_id, Result.term_id == term.id,
        Result.class_subject_id.in_([c.id for c in csubs] or [0]))}
    rows = []
    for csub in csubs:
        by_slot = {c.report_slot: c for c in comps.get(csub.id, [])}
        rows.append({
            "result": results.get(csub.id),
            "class_subject": csub, "name": csub.subject.name,
            "weight_total": sum(c.weight for c in comps.get(csub.id, [])),
            "locked": authz.subject_term_locked(csub.id, term.id),
            "configured": bool(by_slot),
            "cells": [{"slot": i, "label": SCORE_COLUMNS[i - 1], "component": by_slot.get(i),
                       "score": scores.get(by_slot[i].id) if i in by_slot else None} for i in range(1, 5)],
        })
    return rows


def save_student_scores(actor, *, enrollment_id: int, term_id: int, values: dict,
                        form_teacher_remark=None, principal_remark=None, ratings: dict | None = None) -> dict:
    """values: {component_id: "12.5" | ""}. Blank = not entered (an existing score is removed).
    All-or-nothing: if any cell is invalid nothing is saved."""
    authz.require_operator(actor)
    enr = db.session.get(StudentEnrollment, enrollment_id)
    term = db.session.get(Term, term_id)
    if enr is None or term is None:
        raise NotFoundError("Student enrollment or term not found.")
    cs = enr.class_session
    if term.academic_session_id != cs.academic_session_id:
        raise ValidationError("That term belongs to a different session than this class.")

    taken = {ss.class_subject_id for ss in enr.subjects}
    comps = {c.id: c for lst in result_service.slotted_components(list(taken), term_id).values() for c in lst}
    parsed, errors = {}, []
    for key, raw in values.items():
        try:
            cid = int(key)
        except (TypeError, ValueError):
            continue
        comp = comps.get(cid)
        if comp is None:
            errors.append("One of the boxes does not belong to this student's subjects.")
            continue
        raw = ("" if raw is None else str(raw)).strip().replace(",", ".")
        label = f"{comp.class_subject.subject.name} {comp.name}"
        if raw == "":
            parsed[cid] = None
            continue
        try:
            v = D(raw)
        except InvalidOperation:
            errors.append(f"{label}: '{raw}' is not a number.")
            continue
        if not v.is_finite() or v < 0 or v > comp.max_score:
            errors.append(f"{label}: must be between 0 and {comp.max_score}.")
            continue
        parsed[cid] = v.quantize(D("0.01"))
    if errors:
        raise ValidationError(" ".join(dict.fromkeys(errors)))

    existing = {s.assessment_component_id: s for s in
                Score.query.filter(Score.student_id == enr.student_id, Score.assessment_component_id.in_(list(comps) or [0]))}
    changes = {cid: v for cid, v in parsed.items()
               if (existing[cid].score if cid in existing else None) != v and not (cid not in existing and v is None)}
    for cid in changes:
        if authz.subject_term_locked(comps[cid].class_subject_id, term_id):
            raise PermissionDenied(f"{comps[cid].class_subject.subject.name} is locked for {term.name}. Unlock it first.")
    for cid, v in changes.items():
        if v is None:
            db.session.delete(existing[cid])
        elif cid in existing:
            existing[cid].score, existing[cid].entered_by = v, actor.id
        else:
            db.session.add(Score(student_id=enr.student_id, assessment_component_id=cid, score=v, entered_by=actor.id))
    db.session.flush()
    result_service.compile_class_term(cs.id, term_id)

    rep = StudentTermReport.query.filter_by(enrollment_id=enr.id, term_id=term_id).first()
    if rep is None and (form_teacher_remark or principal_remark):
        rep = StudentTermReport(enrollment_id=enr.id, term_id=term_id, class_size=len(cs.student_enrollments))
        db.session.add(rep)
    if rep is not None:
        if form_teacher_remark is not None:
            rep.form_teacher_remark = form_teacher_remark.strip() or None
        if principal_remark is not None:
            rep.principal_remark = principal_remark.strip() or None
    rated = traits_service.apply_manual(enr.id, term_id, ratings or {})
    if changes or rated:
        log_action(actor.id, "SAVE_SCORES", "StudentEnrollment", enr.id,
                   f"{len(changes)} score(s) and {rated} rating(s) saved for {enr.student.full_name} ({term.name})")
    db.session.commit()
    return {"changed": len(changes), "ratings": rated}
