"""Score entry, result sheets (preview + on-demand PDF), locking, form teacher, branding images."""
import os, re
from pathlib import Path
from flask import (Blueprint, render_template, request, redirect, url_for, flash, g, abort, jsonify,
                   send_file, Response, current_app)
from app.auth.decorators import operator_required, login_required
from app.extensions import db
from app.errors import ValidationError, NotFoundError, DomainError
from app.models import (ClassSession, StudentEnrollment, Term, Student, StudentTermReport, Result)
from app import report_labels
from app.report_labels import AFFECTIVE, PSYCHOMOTOR, SCORE_COLUMNS
from app.services import report_service, result_service, score_service, branding, traits_service
from app.services import operator_service as ops
from app.services.audit_log import log_action

bp = Blueprint("results", __name__)


def _get(model, id_):
    obj = db.session.get(model, id_)
    if obj is None:
        raise NotFoundError(f"{model.__name__} not found.")
    return obj


def _term_for(cs, term_id=None):
    terms = Term.query.filter_by(academic_session_id=cs.academic_session_id).order_by(Term.id).all()
    chosen = next((t for t in terms if t.id == term_id), None) or next((t for t in terms if t.is_current), None) \
        or (terms[0] if terms else None)
    return chosen, terms


# ------------------------------------------------------------------ branding images (logo, signature)
@bp.route("/branding/<name>")
@login_required
def branding_file(name):
    path = branding.path_for(name)
    if not path:
        abort(404)
    return send_file(path, mimetype="image/png", max_age=0)


@bp.post("/branding/<name>/upload")
@operator_required
def branding_upload(name):
    f = request.files.get("image")
    if name not in branding.NAMES or not f or not f.filename:
        raise ValidationError("Choose an image file first.")
    branding.save_upload(name, f)
    log_action(g.user.id, "CHANGE_BRANDING", "Setting", None, f"Replaced {name} image")
    db.session.commit()
    flash("Image updated.", "ok")
    return redirect(url_for("operator.settings"))


@bp.post("/branding/<name>/reset")
@operator_required
def branding_reset(name):
    branding.reset(name)
    log_action(g.user.id, "CHANGE_BRANDING", "Setting", None, f"Restored original {name} image")
    db.session.commit()
    flash("Original image restored.", "ok")
    return redirect(url_for("operator.settings"))


# ------------------------------------------------------------------ result sheets
def _sheet(cs_id, enrollment_id=None):
    cs = _get(ClassSession, cs_id)
    kind = request.args.get("kind", "terminal")
    if kind not in ("terminal", "annual"):
        abort(404)
    term, _ = _term_for(cs, request.args.get("term_id", type=int))
    ids = [enrollment_id] if enrollment_id else None
    if enrollment_id and _get(StudentEnrollment, enrollment_id).class_session_id != cs.id:
        abort(404)
    if kind == "terminal":
        if term is None:
            raise ValidationError("This session has no term yet.")
        cards = report_service.terminal_cards(cs.id, term.id, ids)
        what = f"{term.name} Terminal Result"
    else:
        cards = report_service.annual_cards(cs.id, ids)
        what = "Annual Result"
    if not cards:
        raise ValidationError("There are no students in this class to print.")
    who = cards[0]["student"]["name"] if enrollment_id else f"{cs.class_.name} (whole class)"
    title = f"{who} · {what} · {cs.academic_session.name}"
    return cs, term, kind, cards, title


def _file_uri(path):
    return Path(path).resolve().as_uri() if path else ""


@bp.route("/class-sessions/<int:cs_id>/results")
@operator_required
def sheet_preview(cs_id):
    enr = request.args.get("enrollment", type=int)
    cs, term, kind, cards, title = _sheet(cs_id, enr)
    args = {k: v for k, v in request.args.items()}
    return render_template("reports/report.html", cards=cards, title=title, labels=report_labels, pdf=False,
                           css_href=url_for("static", filename="css/pages/report.css"),
                           logo_src=url_for("results.branding_file", name="logo"),
                           signature_src=url_for("results.branding_file", name="signature"),
                           back_url=request.referrer or url_for("operator.class_detail", cs_id=cs_id),
                           pdf_url=url_for("results.sheet_pdf", cs_id=cs_id, **args))


@bp.route("/class-sessions/<int:cs_id>/results.pdf")
@operator_required
def sheet_pdf(cs_id):
    enr = request.args.get("enrollment", type=int)
    cs, term, kind, cards, title = _sheet(cs_id, enr)
    html = render_template("reports/report.html", cards=cards, title=title, labels=report_labels, pdf=True,
                           css_href=_file_uri(os.path.join(current_app.static_folder, "css", "pages", "report.css")),
                           logo_src=_file_uri(branding.path_for("logo")),
                           signature_src=_file_uri(branding.path_for("signature")),
                           back_url="", pdf_url="")
    try:
        data = report_service.render_pdf(html, base_url=current_app.root_path)
    except RuntimeError as exc:
        raise ValidationError(f"{exc} Use Print instead, then choose 'Save as PDF'.")
    log_action(g.user.id, "PRINT_RESULTS", "ClassSession", cs.id, f"{kind} PDF: {title}")
    db.session.commit()
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", title)[:90] + ".pdf"
    return Response(data, mimetype="application/pdf", headers={"Content-Disposition": f'inline; filename="{name}"'})


# ------------------------------------------------------------------ score entry (one student at a time)
def _wants_json():
    return request.headers.get("X-Requested-With") == "fetch"


def _slide(enr, term):
    rep = StudentTermReport.query.filter_by(enrollment_id=enr.id, term_id=term.id).first()
    return {"enr": enr, "sheet": score_service.entry_sheet(enr, term), "report": rep,
            "traits": traits_service.get_traits(enr.id, term.id)}


def _safe_back(default):
    back = request.values.get("back", "")
    return back if back.startswith("/admin/") else default


@bp.route("/class-sessions/<int:cs_id>/scores")
@operator_required
def class_scores(cs_id):
    cs = _get(ClassSession, cs_id)
    term, terms = _term_for(cs, request.args.get("term_id", type=int))
    if term is None:
        raise ValidationError("Create a term for this session first.")
    from app.services.assessment_template_service import sync_for
    for csub in cs.class_subjects:
        sync_for(csub.id, term.id)
    db.session.commit()
    enrollments = (StudentEnrollment.query.filter_by(class_session_id=cs_id).join(Student)
                   .filter(Student.status == "ACTIVE")
                   .order_by(StudentEnrollment.roll_number.is_(None), StudentEnrollment.roll_number,
                             Student.last_name, Student.first_name).all())
    slides = [_slide(e, term) for e in enrollments]
    start = request.args.get("start", type=int)
    start_index = next((i for i, s in enumerate(slides) if s["enr"].id == start), 0)
    return render_template("operator/score_entry.html", cs=cs, term=term, terms=terms, slides=slides, start_index=start_index,
                           mode="class", back=url_for("operator.class_detail", cs_id=cs_id, term_id=term.id),
                           summary=result_service.class_term_summary(cs_id, term.id),
                           affective=AFFECTIVE, psychomotor=PSYCHOMOTOR, slot_labels=SCORE_COLUMNS,
                           here=url_for("results.class_scores", cs_id=cs_id, term_id=term.id))


@bp.route("/enrollments/<int:eid>/scores")
@operator_required
def student_scores(eid):
    """Same screen for one student, any status and any past class: used to correct old results."""
    enr = _get(StudentEnrollment, eid)
    cs = enr.class_session
    term, terms = _term_for(cs, request.args.get("term_id", type=int))
    if term is None:
        raise ValidationError("This session has no term yet.")
    from app.services.assessment_template_service import sync_for
    for student_subject in enr.subjects:
        sync_for(student_subject.class_subject_id, term.id)
    db.session.commit()
    return render_template("operator/score_entry.html", cs=cs, term=term, terms=terms, slides=[_slide(enr, term)],
                           start_index=0, mode="student",
                           back=url_for("operator.student_detail", sid=enr.student_id),
                           summary=result_service.class_term_summary(cs.id, term.id),
                           affective=AFFECTIVE, psychomotor=PSYCHOMOTOR, slot_labels=SCORE_COLUMNS,
                           here=url_for("results.student_scores", eid=eid, term_id=term.id))


@bp.post("/enrollments/<int:eid>/scores")
@operator_required
def save_scores(eid):
    enr = _get(StudentEnrollment, eid)
    f = request.form
    term_id = f.get("term_id", type=int)
    values = {k[1:]: v for k, v in f.items() if k.startswith("c") and k[1:].isdigit()}
    ratings = {k[2:]: v for k, v in f.items() if k.startswith("r_")}
    try:
        res = score_service.save_student_scores(
            g.user, enrollment_id=eid, term_id=term_id, values=values, ratings=ratings,
            form_teacher_remark=f.get("form_teacher_remark"), principal_remark=f.get("principal_remark"))
    except DomainError as exc:
        db.session.rollback()
        if _wants_json():
            return jsonify(ok=False, error=str(exc)), 400
        raise
    if _wants_json():
        rows = {r.class_subject_id: {"total": report_service.fmt_mark(r.total_score), "grade": r.grade or "",
                                     "position": report_service.ordinal(r.position)}
                for r in Result.query.filter_by(student_id=enr.student_id, term_id=term_id)}
        rep = StudentTermReport.query.filter_by(enrollment_id=eid, term_id=term_id).first()
        return jsonify(ok=True, changed=res["changed"], rows=rows,
                       average=report_service.fmt_pct(rep.average) if rep else "",
                       position=report_service.ordinal(rep.position) if rep else "")
    flash(f"Saved {enr.student.full_name}.", "ok")
    return redirect(_safe_back(url_for("results.student_scores", eid=eid, term_id=term_id)) + f"#slide-{eid}")


# ------------------------------------------------------------------ lock / unlock, form teacher
@bp.post("/class-sessions/<int:cs_id>/lock")
@operator_required
def lock_results(cs_id):
    lock = request.form.get("lock") == "1"
    csub = request.form.get("class_subject_id", type=int)
    term_id = request.form.get("term_id", type=int)
    n = result_service.set_lock(g.user, class_session_id=cs_id, term_id=term_id, lock=lock, class_subject_id=csub)
    flash(f"{'Locked' if lock else 'Unlocked'} ({n} result{'s' if n != 1 else ''}). "
          + ("Nobody can change these scores until you unlock them." if lock else "Scores can be edited again."), "ok")
    return redirect(url_for("operator.class_detail", cs_id=cs_id, term_id=term_id))


@bp.post("/class-sessions/<int:cs_id>/form-teacher")
@operator_required
def form_teacher(cs_id):
    raw = request.form.get("staff_id", "")
    ops.set_form_teacher(g.user, class_session_id=cs_id, staff_id=int(raw) if raw.isdigit() else None)
    flash("Form teacher saved.", "ok")
    return redirect(url_for("operator.class_detail", cs_id=cs_id, term_id=request.form.get("term_id", type=int)))
