from flask import Blueprint, render_template, g
from app.auth.decorators import staff_required
from app.services.dashboard_service import staff_assignments

bp = Blueprint("staff", __name__)


@bp.route("/")
@staff_required
def dashboard():
    return render_template("staff/dashboard.html", assignments=staff_assignments(g.user))


@bp.route("/subjects/<int:csub_id>", methods=["GET", "POST"])
@staff_required
def subject_scores(csub_id):
    from decimal import Decimal, InvalidOperation
    from flask import request, redirect, url_for, flash, jsonify
    from app.extensions import db
    from app.errors import ValidationError, PermissionDenied, NotFoundError
    from app.models import (ClassSubject, Term, StudentEnrollment, StudentSubject,
                            AssessmentComponent, Score, Result, StaffAssignment,
                            StudentTermReport)
    from app.services import authorization_service as authz, result_service, report_service
    from app.services.assessment_template_service import sync_for
    from app.services.audit_log import log_action

    csub = db.session.get(ClassSubject, csub_id)
    if csub is None:
        raise NotFoundError("Class subject not found.")
    authz.require_staff_assignment(g.user, csub_id)
    session_id = csub.class_session.academic_session_id
    if not StaffAssignment.query.filter_by(staff_id=g.user.id, class_subject_id=csub_id,
                                           academic_session_id=session_id).first():
        raise PermissionDenied("You are not assigned to this subject for this academic session.")

    terms = Term.query.filter_by(academic_session_id=session_id).order_by(Term.id).all()
    term_id = request.values.get("term_id", type=int)
    term = next((t for t in terms if t.id == term_id), None) or next(
        (t for t in terms if t.is_current), None) or (terms[0] if terms else None)
    if term is None:
        raise ValidationError("The class has no academic term yet.")

    sync_for(csub_id, term.id)
    db.session.commit()
    components = (AssessmentComponent.query.filter_by(class_subject_id=csub_id, term_id=term.id)
                  .order_by(AssessmentComponent.position, AssessmentComponent.id).all())
    enrollments = (StudentEnrollment.query.join(StudentSubject)
                   .filter(StudentEnrollment.class_session_id == csub.class_session_id,
                           StudentSubject.class_subject_id == csub_id)
                   .order_by(StudentEnrollment.roll_number, StudentEnrollment.id).all())
    locked = authz.subject_term_locked(csub_id, term.id)
    deadline_passed = authz.staff_deadline_passed(term)
    enrollment_ids = [e.id for e in enrollments]
    student_ids = [e.student_id for e in enrollments]

    if request.method == "POST":
        wants_json = request.headers.get("X-Requested-With") == "fetch"
        if locked:
            if wants_json:
                return jsonify(ok=False, error="This subject is locked for this term."), 403
            raise PermissionDenied("This subject is locked for this term.")
        if deadline_passed:
            if wants_json:
                return jsonify(ok=False, error="The score-entry deadline for this term has passed."), 403
            raise PermissionDenied("The score-entry deadline for this term has passed.")

        enrollment_id = request.form.get("enrollment_id", type=int)
        enr = next((e for e in enrollments if e.id == enrollment_id), None)
        if enr is None:
            if wants_json:
                return jsonify(ok=False, error="That student is not enrolled for this subject."), 403
            raise PermissionDenied("That student is not enrolled for this subject.")

        result = Result.query.filter_by(student_id=enr.student_id,
                                        class_subject_id=csub_id, term_id=term.id).first()
        if result and result.status not in authz.EDITABLE_BY_STAFF:
            message = "This result has already been submitted or approved. Ask the operator to reopen it."
            if wants_json:
                return jsonify(ok=False, error=message), 403
            raise PermissionDenied(message)

        comp_ids = [c.id for c in components]
        existing = {s.assessment_component_id: s for s in Score.query.filter(
            Score.assessment_component_id.in_(comp_ids or [0]),
            Score.student_id == enr.student_id).all()}
        errors, changed = [], 0
        for comp in components:
            raw = request.form.get(f"score_{enr.id}_{comp.id}", "").strip().replace(",", ".")
            old = existing.get(comp.id)
            if raw == "":
                if old:
                    db.session.delete(old)
                    changed += 1
                continue
            try:
                value = Decimal(raw)
            except InvalidOperation:
                errors.append(f"{comp.name} must be a number.")
                continue
            if not value.is_finite() or value < 0 or value > comp.max_score:
                errors.append(f"{comp.name} must be between 0 and {comp.max_score}.")
                continue
            value = value.quantize(Decimal("0.01"))
            if old:
                if old.score != value:
                    old.score, old.entered_by = value, g.user.id
                    changed += 1
            else:
                db.session.add(Score(student_id=enr.student_id,
                                     assessment_component_id=comp.id,
                                     score=value, entered_by=g.user.id))
                changed += 1

        if errors:
            db.session.rollback()
            message = " ".join(errors)
            if wants_json:
                return jsonify(ok=False, error=message), 400
            raise ValidationError(message)

        db.session.flush()
        result_service.compile_class_term(csub.class_session_id, term.id)
        log_action(g.user.id, "STAFF_SAVE_SCORES", "ClassSubject", csub_id,
                   f"Saved {changed} score change(s) for {enr.student.full_name}, {csub.subject.name}, {term.name}")
        db.session.commit()

        if wants_json:
            saved_result = Result.query.filter_by(student_id=enr.student_id,
                                                  class_subject_id=csub_id, term_id=term.id).first()
            report = StudentTermReport.query.filter_by(enrollment_id=enr.id, term_id=term.id).first()
            rows = {str(csub_id): {
                "total": report_service.fmt_mark(saved_result.total_score) if saved_result else "",
                "grade": saved_result.grade or "" if saved_result else "",
                "position": report_service.ordinal(saved_result.position) if saved_result else ""
            }}
            return jsonify(ok=True, changed=changed, rows=rows,
                           average=report_service.fmt_pct(report.average) if report else "",
                           position=report_service.ordinal(report.position) if report else "")

        index = enrollment_ids.index(enr.id)
        if request.form.get("advance") == "1":
            index = min(index + 1, len(enrollments) - 1)
        flash(f"Scores saved for {enr.student.full_name}.", "ok")
        return redirect(url_for("staff.subject_scores", csub_id=csub_id,
                                term_id=term.id, student=index))

    start_index = request.args.get("student", 0, type=int)
    start_index = max(0, min(start_index, max(len(enrollments) - 1, 0)))
    score_values = {(s.student_id, s.assessment_component_id): s.score for s in Score.query.filter(
        Score.assessment_component_id.in_([c.id for c in components] or [0]),
        Score.student_id.in_(student_ids or [0])).all()}
    results = {r.student_id: r for r in Result.query.filter_by(
        class_subject_id=csub_id, term_id=term.id).filter(Result.student_id.in_(student_ids or [0])).all()}
    reports = {r.enrollment_id: r for r in StudentTermReport.query.filter_by(term_id=term.id)
               .filter(StudentTermReport.enrollment_id.in_(enrollment_ids or [0])).all()}
    return render_template("staff/subject_scores.html", csub=csub, terms=terms, term=term,
                           components=components, enrollments=enrollments, score_values=score_values,
                           results=results, reports=reports, start_index=start_index,
                           locked=locked, deadline_passed=deadline_passed)
