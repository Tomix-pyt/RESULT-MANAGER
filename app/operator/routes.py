from datetime import date, datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, g, abort
from sqlalchemy import or_
from app.auth.decorators import operator_required
from app.extensions import db
from app.errors import ValidationError, NotFoundError
from app.models import (User, AcademicSession, Term, Class, ClassSession, ClassSubject, Subject, Student,
                        StudentEnrollment, StaffAssignment, AssessmentComponent, GradingScale, GradeBoundary)
from app.services import operator_service as ops
from app.services.dashboard_service import operator_stats

bp = Blueprint("operator", __name__)

DEFAULT_SCALE = [(90, 100, "A+", "Outstanding"), (80, 89.99, "A", "Excellent"), (70, 79.99, "B", "Very Good"),
                 (60, 69.99, "C", "Good"), (50, 59.99, "D", "Pass"), (0, 49.99, "F", "Fail")]


# ---- small form helpers -------------------------------------------------
def _date(name):
    v = request.form.get(name, "").strip()
    if not v:
        return None
    try:
        return date.fromisoformat(v)
    except ValueError:
        raise ValidationError("Invalid date.")


def _int(name, label=None):
    try:
        return int(request.form.get(name, ""))
    except ValueError:
        raise ValidationError(f"{label or name} must be a whole number.")


def _num(name, label=None):
    try:
        return float(request.form.get(name, ""))
    except ValueError:
        raise ValidationError(f"{label or name} must be a number.")


def _get(model, id_):
    obj = db.session.get(model, id_)
    if obj is None:
        raise NotFoundError(f"{model.__name__} not found.")
    return obj


def _ok(msg, endpoint, **kw):
    flash(msg, "ok")
    return redirect(url_for(endpoint, **kw))


# ---- dashboard ----------------------------------------------------------
@bp.route("/")
@operator_required
def dashboard():
    return render_template("operator/dashboard.html", stats=operator_stats())


# ---- users --------------------------------------------------------------
@bp.route("/users", methods=["GET", "POST"])
@operator_required
def users():
    if request.method == "POST":
        f = request.form
        u = ops.create_user_account(g.user, username=f.get("username"), first_name=f.get("first_name"),
                                    last_name=f.get("last_name"), password=f.get("password"),
                                    role=f.get("role", "STAFF"), email=f.get("email"))
        return _ok(f"Account '{u.username}' created.", "operator.users")
    return render_template("operator/users.html", users=User.query.order_by(User.role, User.last_name).all())


@bp.post("/users/<int:user_id>/active")
@operator_required
def user_active(user_id):
    active = request.form.get("active") == "1"
    u = ops.set_user_active(g.user, user_id=user_id, active=active)
    return _ok(f"{u.username} {'activated' if active else 'deactivated'}.", "operator.users")


@bp.post("/users/<int:user_id>/password")
@operator_required
def user_password(user_id):
    u = ops.reset_user_password(g.user, user_id=user_id, new_password=request.form.get("password", ""))
    return _ok(f"Password reset for {u.username}.", "operator.users")


# ---- sessions & terms ---------------------------------------------------
@bp.route("/sessions")
@operator_required
def sessions():
    rows = AcademicSession.query.order_by(AcademicSession.name.desc()).all()
    return render_template("operator/sessions.html", sessions=rows)


@bp.post("/sessions")
@operator_required
def session_create():
    s = ops.create_academic_session(g.user, name=request.form.get("name", ""), start_date=_date("start_date"),
                                    end_date=_date("end_date"), make_current=bool(request.form.get("current")))
    return _ok(f"Session {s.name} created.", "operator.sessions")


@bp.post("/sessions/<int:sid>/current")
@operator_required
def session_current(sid):
    s = ops.set_current_session(g.user, session_id=sid)
    return _ok(f"{s.name} is now the current session.", "operator.sessions")


@bp.post("/sessions/<int:sid>/terms")
@operator_required
def term_create(sid):
    t = ops.create_term(g.user, academic_session_id=sid, name=request.form.get("name", ""),
                        start_date=_date("start_date"), end_date=_date("end_date"))
    return _ok(f"{t.name} added.", "operator.sessions")


@bp.post("/terms/<int:tid>/current")
@operator_required
def term_current(tid):
    t = ops.set_current_term(g.user, term_id=tid)
    return _ok(f"{t.name} {t.academic_session.name} is now current.", "operator.sessions")


@bp.post("/terms/<int:tid>/deadline")
@operator_required
def term_deadline(tid):
    raw = request.form.get("edit_deadline", "").strip()
    try:
        dl = datetime.fromisoformat(raw) if raw else None
    except ValueError:
        raise ValidationError("Invalid deadline.")
    ops.update_term(g.user, term_id=tid, edit_deadline=dl, clear_deadline=dl is None)
    return _ok("Edit deadline saved." if dl else "Edit deadline cleared.", "operator.sessions")


# ---- classes ------------------------------------------------------------
@bp.route("/classes", methods=["GET", "POST"])
@operator_required
def classes():
    if request.method == "POST":
        f = request.form
        c = ops.create_class(g.user, name=f.get("name", ""), level=f.get("level") or None, arm=f.get("arm") or None)
        return _ok(f"Class {c.name} created.", "operator.classes")
    cur = AcademicSession.query.filter_by(is_current=True).first()
    sessions_ = AcademicSession.query.order_by(AcademicSession.name.desc()).all()
    sel = request.args.get("session_id", type=int)
    session_ = db.session.get(AcademicSession, sel) if sel else cur
    rows = []
    for c in Class.query.order_by(Class.name).all():
        cs = ClassSession.query.filter_by(class_id=c.id, academic_session_id=session_.id).first() if session_ else None
        rows.append((c, cs))
    return render_template("operator/classes.html", rows=rows, session=session_, sessions=sessions_)


@bp.post("/classes/<int:cid>/deactivate")
@operator_required
def class_deactivate(cid):
    ops.deactivate_class(g.user, class_id=cid)
    return _ok("Class deactivated.", "operator.classes")


@bp.post("/classes/<int:cid>/open")
@operator_required
def class_open(cid):
    cs = ops.create_class_session(g.user, class_id=cid, academic_session_id=_int("session_id", "Session"))
    return _ok("Class opened for the session.", "operator.class_detail", cs_id=cs.id)


@bp.route("/class-sessions/<int:cs_id>")
@operator_required
def class_detail(cs_id):
    cs = _get(ClassSession, cs_id)
    enrolled = (StudentEnrollment.query.filter_by(class_session_id=cs_id).join(Student)
                .order_by(Student.last_name, Student.first_name).all())
    enrolled_ids = {e.student_id for e in enrolled}
    candidates = [s for s in Student.query.filter_by(status="ACTIVE").order_by(Student.last_name).all()
                  if s.id not in enrolled_ids]
    taken = {cs_.subject_id for cs_ in cs.class_subjects}
    from app.services import result_service
    from app.operator.results import _term_for
    term, terms = _term_for(cs, request.args.get("term_id", type=int))
    return render_template(
        "operator/class_detail.html", cs=cs, enrolled=[e for e in enrolled if e.student.status == "ACTIVE"],
        former=[e for e in enrolled if e.student.status != "ACTIVE"], enrolled_total=len(enrolled),
        term=term, terms=terms, summary=result_service.class_term_summary(cs_id, term.id) if term else None,
        candidates=candidates,
        subjects_free=[s for s in Subject.query.filter_by(is_active=True).order_by(Subject.name) if s.id not in taken],
        staff=User.query.filter_by(role="STAFF", is_active=True).order_by(User.last_name).all(),
        class_subjects=sorted(cs.class_subjects, key=lambda x: x.subject.name),
        copy_from=[o for o in ClassSession.query.join(Class).join(AcademicSession)
                   .order_by(AcademicSession.name.desc(), Class.name).all() if o.id != cs.id and o.class_subjects])


@bp.post("/class-sessions/<int:cs_id>/subjects")
@operator_required
def class_subject_add(cs_id):
    ops.add_subject_to_class(g.user, class_session_id=cs_id, subject_id=_int("subject_id", "Subject"))
    return _ok("Subject added to the class (and to every enrolled student).", "operator.class_detail", cs_id=cs_id)


@bp.post("/class-subjects/<int:csub_id>/remove")
@operator_required
def class_subject_remove(csub_id):
    cs_id = _get(ClassSubject, csub_id).class_session_id
    ops.remove_subject_from_class(g.user, class_subject_id=csub_id)
    return _ok("Subject removed from the class.", "operator.class_detail", cs_id=cs_id)


@bp.post("/class-subjects/<int:csub_id>/assign")
@operator_required
def staff_assign(csub_id):
    cs_id = _get(ClassSubject, csub_id).class_session_id
    ops.assign_staff(g.user, staff_id=_int("staff_id", "Staff"), class_subject_id=csub_id)
    return _ok("Teacher assigned.", "operator.class_detail", cs_id=cs_id)


@bp.post("/assignments/<int:aid>/remove")
@operator_required
def staff_unassign(aid):
    cs_id = _get(StaffAssignment, aid).class_subject.class_session_id
    ops.remove_staff_assignment(g.user, assignment_id=aid)
    return _ok("Assignment removed.", "operator.class_detail", cs_id=cs_id)


@bp.post("/class-sessions/<int:cs_id>/enroll")
@operator_required
def enroll(cs_id):
    ops.enroll_student(g.user, student_id=_int("student_id", "Student"), class_session_id=cs_id)
    return _ok("Student enrolled.", "operator.class_detail", cs_id=cs_id)


@bp.post("/enrollments/<int:eid>/remove")
@operator_required
def enrollment_remove(eid):
    cs_id = _get(StudentEnrollment, eid).class_session_id
    ops.remove_enrollment(g.user, enrollment_id=eid)
    return _ok("Enrollment removed.", "operator.class_detail", cs_id=cs_id)


# ---- subjects -----------------------------------------------------------
@bp.route("/subjects", methods=["GET", "POST"])
@operator_required
def subjects():
    if request.method == "POST":
        s = ops.create_subject(g.user, code=request.form.get("code", ""), name=request.form.get("name", ""),
                               description=request.form.get("description") or None)
        return _ok(f"Subject {s.name} created.", "operator.subjects")
    return render_template("operator/subjects.html", subjects=Subject.query.order_by(Subject.name).all())


@bp.post("/subjects/<int:sid>/deactivate")
@operator_required
def subject_deactivate(sid):
    ops.deactivate_subject(g.user, subject_id=sid)
    return _ok("Subject deactivated. Historical results are untouched.", "operator.subjects")


# ---- school-wide assessment template -----------------------------------
@bp.route("/assessment-settings", methods=["GET", "POST"])
@operator_required
def assessment_settings():
    from app.services.assessment_template_service import get_template, save_template
    from app.report_labels import SCORE_COLUMNS
    slot_names = {i + 1: label for i, label in enumerate(SCORE_COLUMNS)}
    if request.method == "POST":
        names = request.form.getlist("name")
        maxima = request.form.getlist("max_score")
        weights = request.form.getlist("weight")
        slots = request.form.getlist("report_slot")
        items = []
        for name, maximum, weight, slot in zip(names, maxima, weights, slots):
            if not (name or maximum or weight or slot):
                continue
            if not (name.strip() and maximum.strip() and weight.strip() and slot.strip()):
                raise ValidationError("Complete every assessment row you use.")
            items.append({"name": name, "max_score": maximum, "weight": weight, "report_slot": slot})
        save_template(g.user, items)
        return _ok("School-wide assessment structure saved and synchronized.", "operator.assessment_settings")
    return render_template("operator/assessment_settings.html", items=get_template(), slot_names=slot_names)


# ---- assessments (CA 1, CA 2, Exam ...) ---------------------------------
@bp.route("/class-subjects/<int:csub_id>/assessments")
@operator_required
def assessments(csub_id):
    csub = _get(ClassSubject, csub_id)
    terms = Term.query.filter_by(academic_session_id=csub.class_session.academic_session_id).order_by(Term.id).all()
    tid = request.args.get("term_id", type=int)
    term = next((t for t in terms if t.id == tid), None) or next((t for t in terms if t.is_current), None) \
        or (terms[0] if terms else None)
    if term:
        from app.services.assessment_template_service import sync_for
        sync_for(csub_id, term.id)
        db.session.commit()
    comps = (AssessmentComponent.query.filter_by(class_subject_id=csub_id, term_id=term.id)
             .order_by(AssessmentComponent.position, AssessmentComponent.id).all()) if term else []
    from app import report_labels
    slot_names = {i + 1: label for i, label in enumerate(report_labels.SCORE_COLUMNS)}
    return render_template("operator/assessments.html", csub=csub, terms=terms, term=term, comps=comps,
                           slot_names=slot_names, used_slots={c.report_slot for c in comps if c.report_slot},
                           unprinted=sum(1 for c in comps if not c.report_slot),
                           total_weight=sum(c.weight for c in comps), total_max=sum(c.max_score for c in comps))


@bp.post("/class-subjects/<int:csub_id>/assessments")
@operator_required
def assessment_create(csub_id):
    term_id = _int("term_id", "Term")
    ops.create_assessment_component(g.user, class_subject_id=csub_id, term_id=term_id,
                                    name=request.form.get("name", ""), max_score=_int("max_score", "Max score"),
                                    weight=_int("weight", "Weight"),
                                    report_slot=_int("report_slot", "Printed column") if request.form.get("report_slot") else None)
    return _ok("Assessment added.", "operator.assessments", csub_id=csub_id, term_id=term_id)


@bp.post("/assessments/<int:aid>/delete")
@operator_required
def assessment_delete(aid):
    comp = _get(AssessmentComponent, aid)
    csub_id, term_id = comp.class_subject_id, comp.term_id
    ops.delete_assessment_component(g.user, component_id=aid)
    return _ok("Assessment deleted.", "operator.assessments", csub_id=csub_id, term_id=term_id)


# ---- students -----------------------------------------------------------
def _search(query, q):
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Student.first_name.ilike(like), Student.last_name.ilike(like),
                                 Student.middle_name.ilike(like), Student.admission_number.ilike(like)))
    return query


@bp.route("/students")
@operator_required
def students():
    q = request.args.get("q", "").strip()
    rows = (_search(Student.query.filter(Student.status == "ACTIVE"), q)
            .order_by(Student.last_name, Student.first_name).limit(300).all())
    cur = AcademicSession.query.filter_by(is_current=True).first()
    classes = ({e.student_id: e.class_session.class_.name for e in
                StudentEnrollment.query.filter_by(academic_session_id=cur.id)} if cur else {})
    former_count = Student.query.filter(Student.status != "ACTIVE").count()
    return render_template("operator/students.html", students=rows, q=q, classes=classes, session=cur,
                           former_count=former_count)


@bp.route("/students/new", methods=["GET", "POST"])
@operator_required
def student_new():
    if request.method == "POST":
        f = request.form
        s = ops.add_student(g.user, admission_number=f.get("admission_number", ""), first_name=f.get("first_name", ""),
                            last_name=f.get("last_name", ""), middle_name=f.get("middle_name") or None,
                            gender=f.get("gender") or None, date_of_birth=_date("date_of_birth"))
        flash(f"{s.full_name} added. They are not enrolled in a class yet.", "ok")
        return redirect(url_for("operator.student_new" if f.get("again") else "operator.students"))
    return render_template("operator/student_new.html")


@bp.route("/students/former")
@operator_required
def former_students():
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "")
    query = Student.query.filter(Student.status != "ACTIVE")
    if status in ("GRADUATED", "WITHDRAWN", "TRANSFERRED", "INACTIVE"):
        query = query.filter(Student.status == status)
    rows = _search(query, q).order_by(Student.last_name, Student.first_name).limit(300).all()
    counts = dict(db.session.query(Student.status, db.func.count(Student.id))
                  .filter(Student.status != "ACTIVE").group_by(Student.status).all())
    return render_template("operator/former_students.html", students=rows, q=q, status=status, counts=counts)


@bp.route("/students/<int:sid>", methods=["GET", "POST"])
@operator_required
def student_detail(sid):
    st = _get(Student, sid)
    if request.method == "POST":
        f = request.form
        ops.update_student(g.user, student_id=sid, first_name=f.get("first_name"), last_name=f.get("last_name"),
                           middle_name=f.get("middle_name") or None, gender=f.get("gender") or None,
                           date_of_birth=_date("date_of_birth"))
        if f.get("status") and f["status"] != st.status:
            ops.set_student_status(g.user, student_id=sid, status=f["status"])
        return _ok("Student updated.", "operator.student_detail", sid=sid)
    enrollments = sorted(st.enrollments, key=lambda e: e.class_session.academic_session.name, reverse=True)
    terms = {e.id: Term.query.filter_by(academic_session_id=e.class_session.academic_session_id).order_by(Term.id).all()
             for e in enrollments}
    return render_template("operator/student_detail.html", st=st, enrollments=enrollments, terms=terms)


@bp.post("/enrollments/<int:eid>/subjects/<int:csub_id>/<action>")
@operator_required
def student_subject(eid, csub_id, action):
    if action not in ("add", "remove"):
        abort(404)
    enr = _get(StudentEnrollment, eid)
    fn = ops.add_student_subject if action == "add" else ops.remove_student_subject
    fn(g.user, enrollment_id=eid, class_subject_id=csub_id)
    return _ok("Subject list updated.", "operator.student_detail", sid=enr.student_id)


# ---- grading scales -----------------------------------------------------
@bp.route("/grading", methods=["GET", "POST"])
@operator_required
def grading():
    if request.method == "POST":
        sc = ops.create_grading_scale(g.user, name=request.form.get("name", ""), academic_session_id=_int("session_id", "Session"))
        if request.form.get("load_default"):
            for lo, hi, gr, rem in DEFAULT_SCALE:
                ops.add_grade_boundary(g.user, grading_scale_id=sc.id, min_score=lo, max_score=hi, grade=gr, remark=rem)
        return _ok("Grading scale created.", "operator.grading")
    return render_template("operator/grading.html", scales=GradingScale.query.order_by(GradingScale.id.desc()).all(),
                           sessions=AcademicSession.query.order_by(AcademicSession.name.desc()).all())


@bp.post("/grading/<int:scale_id>/boundaries")
@operator_required
def boundary_add(scale_id):
    ops.add_grade_boundary(g.user, grading_scale_id=scale_id, min_score=_num("min_score", "Min"), max_score=_num("max_score", "Max"),
                           grade=request.form.get("grade", ""), remark=request.form.get("remark") or None)
    return _ok("Boundary added.", "operator.grading")


@bp.post("/grading/boundaries/<int:bid>/delete")
@operator_required
def boundary_delete(bid):
    ops.delete_grade_boundary(g.user, boundary_id=bid)
    return _ok("Boundary deleted.", "operator.grading")


# =====================================================================
# EDIT / REACTIVATE / DELETE
# =====================================================================
@bp.post("/sessions/<int:sid>/edit")
@operator_required
def session_edit(sid):
    s = ops.update_academic_session(g.user, session_id=sid, name=request.form.get("name"),
                                    start_date=_date("start_date"), end_date=_date("end_date"))
    return _ok(f"Session {s.name} updated.", "operator.sessions")


@bp.post("/sessions/<int:sid>/delete")
@operator_required
def session_delete(sid):
    ops.delete_academic_session(g.user, session_id=sid)
    return _ok("Session deleted.", "operator.sessions")


@bp.post("/terms/<int:tid>/edit")
@operator_required
def term_edit(tid):
    t = ops.update_term(g.user, term_id=tid, name=request.form.get("name"),
                        start_date=_date("start_date"), end_date=_date("end_date"),
                        next_term_begins=_date("next_term_begins"))
    return _ok(f"{t.name} updated.", "operator.sessions")


@bp.post("/terms/<int:tid>/delete")
@operator_required
def term_delete(tid):
    ops.delete_term(g.user, term_id=tid)
    return _ok("Term deleted.", "operator.sessions")


@bp.post("/classes/<int:cid>/edit")
@operator_required
def class_edit(cid):
    c = ops.update_class(g.user, class_id=cid, name=request.form.get("name"),
                         level=request.form.get("level", ""), arm=request.form.get("arm", ""))
    return _ok(f"Class {c.name} updated.", "operator.classes")


@bp.post("/classes/<int:cid>/reactivate")
@operator_required
def class_reactivate(cid):
    ops.reactivate_class(g.user, class_id=cid)
    return _ok("Class reactivated.", "operator.classes")


@bp.post("/class-sessions/<int:cs_id>/delete")
@operator_required
def class_session_delete(cs_id):
    session_id = _get(ClassSession, cs_id).academic_session_id
    ops.delete_class_session(g.user, class_session_id=cs_id)
    return _ok("Class removed from this session.", "operator.classes", session_id=session_id)


@bp.post("/class-sessions/<int:cs_id>/copy")
@operator_required
def class_copy(cs_id):
    res = ops.copy_class_setup(g.user, from_class_session_id=_int("from_cs_id", "Class to copy from"), to_class_session_id=cs_id,
                               include_staff=bool(request.form.get("include_staff")))
    return _ok(f"Copied {res['subjects']} subject(s) and {res['staff']} teacher assignment(s).", "operator.class_detail", cs_id=cs_id)


@bp.post("/subjects/<int:sid>/edit")
@operator_required
def subject_edit(sid):
    s = ops.update_subject(g.user, subject_id=sid, code=request.form.get("code"), name=request.form.get("name"),
                           description=request.form.get("description", ""))
    return _ok(f"Subject {s.name} updated.", "operator.subjects")


@bp.post("/subjects/<int:sid>/reactivate")
@operator_required
def subject_reactivate(sid):
    ops.reactivate_subject(g.user, subject_id=sid)
    return _ok("Subject reactivated.", "operator.subjects")


@bp.post("/assessments/<int:aid>/edit")
@operator_required
def assessment_edit(aid):
    comp = _get(AssessmentComponent, aid)
    csub_id, term_id = comp.class_subject_id, comp.term_id
    ops.update_assessment_component(g.user, component_id=aid, name=request.form.get("name"),
                                    max_score=_int("max_score", "Max score"), weight=_int("weight", "Weight"),
                                    report_slot=_int("report_slot", "Printed column") if request.form.get("report_slot") else None)
    return _ok("Assessment updated.", "operator.assessments", csub_id=csub_id, term_id=term_id)


@bp.post("/grading/<int:scale_id>/rename")
@operator_required
def scale_rename(scale_id):
    ops.update_grading_scale(g.user, scale_id=scale_id, name=request.form.get("name", ""))
    return _ok("Scale renamed.", "operator.grading")


@bp.post("/grading/<int:scale_id>/delete")
@operator_required
def scale_delete(scale_id):
    ops.delete_grading_scale(g.user, scale_id=scale_id)
    return _ok("Scale deleted.", "operator.grading")


@bp.post("/grading/boundaries/<int:bid>/edit")
@operator_required
def boundary_edit(bid):
    ops.update_grade_boundary(g.user, boundary_id=bid, min_score=_num("min_score", "From"), max_score=_num("max_score", "To"),
                              grade=request.form.get("grade"), remark=request.form.get("remark", ""))
    return _ok("Boundary updated.", "operator.grading")


@bp.post("/users/<int:user_id>/edit")
@operator_required
def user_edit(user_id):
    f = request.form
    u = ops.update_user_account(g.user, user_id=user_id, first_name=f.get("first_name"), last_name=f.get("last_name"),
                                email=f.get("email", ""), role=f.get("role"))
    return _ok(f"{u.username} updated.", "operator.users")


# =====================================================================
# ENROLLMENT
# =====================================================================
@bp.route("/enrollment")
@operator_required
def enrollment():
    all_cs = (ClassSession.query.join(AcademicSession).join(Class)
              .order_by(AcademicSession.name.desc(), Class.name).all())
    cs_id = request.args.get("cs_id", type=int)
    cs = db.session.get(ClassSession, cs_id) if cs_id else None
    ctx = dict(all_cs=all_cs, cs=cs)
    if cs:
        enrolled = (StudentEnrollment.query.filter_by(class_session_id=cs.id).join(Student)
                    .filter(Student.status == "ACTIVE")
                    .order_by(StudentEnrollment.roll_number.is_(None), StudentEnrollment.roll_number,
                              Student.last_name, Student.first_name).all())
        in_session = {e.student_id for e in StudentEnrollment.query.join(ClassSession)
                      .filter(ClassSession.academic_session_id == cs.academic_session_id).all()}
        ctx.update(
            enrolled=enrolled,
            candidates=[s for s in Student.query.filter_by(status="ACTIVE").order_by(Student.last_name, Student.first_name).all()
                        if s.id not in in_session],
            same_session=[x for x in all_cs if x.academic_session_id == cs.academic_session_id and x.id != cs.id],
            other_session=[x for x in all_cs if x.academic_session_id != cs.academic_session_id],
        )
    return render_template("operator/enrollment.html", **ctx)


def _back(cs_id):
    return redirect(url_for("operator.enrollment", cs_id=cs_id))


@bp.post("/enrollment/<int:cs_id>/bulk")
@operator_required
def enrollment_bulk(cs_id):
    ids = [int(x) for x in request.form.getlist("student_ids") if x.isdigit()]
    if not ids:
        raise ValidationError("Tick at least one student.")
    res = ops.bulk_enroll(g.user, student_ids=ids, class_session_id=cs_id)
    flash(f"Enrolled {res['enrolled']} student(s).", "ok")
    for p in res["problems"][:10]:
        flash(p, "error")
    return _back(cs_id)


@bp.post("/enrollment/<int:cs_id>/import")
@operator_required
def enrollment_import(cs_id):
    up = request.files.get("file")
    text = up.read(1_000_000).decode("utf-8-sig", errors="replace") if up and up.filename else request.form.get("text", "")
    res = ops.import_students_csv(g.user, text=text, class_session_id=cs_id if request.form.get("enroll") else None)
    flash(f"Imported {res['created']} new student(s); enrolled {res['enrolled']}.", "ok")
    for p in res["problems"][:15]:
        flash(p, "error")
    if len(res["problems"]) > 15:
        flash(f"…and {len(res['problems']) - 15} more problems.", "error")
    return _back(cs_id)


@bp.post("/enrollment/<int:cs_id>/roll-numbers")
@operator_required
def enrollment_rolls(cs_id):
    n = ops.assign_roll_numbers(g.user, class_session_id=cs_id)
    return _ok(f"Numbered {n} students alphabetically.", "operator.enrollment", cs_id=cs_id)


@bp.post("/enrollments/<int:eid>/roll")
@operator_required
def enrollment_roll(eid):
    enr = _get(StudentEnrollment, eid)
    ops.update_enrollment(g.user, enrollment_id=eid, roll_number=_int("roll_number", "Roll number"))
    return _back(enr.class_session_id)


@bp.post("/enrollments/<int:eid>/transfer")
@operator_required
def enrollment_transfer(eid):
    enr = _get(StudentEnrollment, eid)
    old = enr.class_session_id
    ops.transfer_student(g.user, enrollment_id=eid, to_class_session_id=_int("to_cs_id", "Class"))
    return _ok("Student transferred.", "operator.enrollment", cs_id=old)


@bp.post("/enrollment/<int:cs_id>/promote")
@operator_required
def enrollment_promote(cs_id):
    ids = [int(x) for x in request.form.getlist("student_ids") if x.isdigit()]
    if not ids:
        raise ValidationError("Tick at least one student.")
    res = ops.promote_students(g.user, student_ids=ids, to_class_session_id=_int("to_cs_id", "Destination class"))
    flash(f"Promoted {res['enrolled']} student(s). Their history in this class is kept.", "ok")
    for p in res["problems"][:10]:
        flash(p, "error")
    return _back(cs_id)


@bp.post("/enrollment/<int:cs_id>/graduate")
@operator_required
def enrollment_graduate(cs_id):
    ids = [int(x) for x in request.form.getlist("student_ids") if x.isdigit()]
    if not ids:
        raise ValidationError("Tick at least one student.")
    n = ops.graduate_students(g.user, student_ids=ids)
    return _ok(f"Marked {n} student(s) as graduated.", "operator.enrollment", cs_id=cs_id)


# =====================================================================
# AUDIT LOG & SETTINGS
# =====================================================================
@bp.route("/audit")
@operator_required
def audit():
    from app.models import AuditLog
    q = AuditLog.query
    action = request.args.get("action", "").strip()
    who = request.args.get("user_id", type=int)
    text = request.args.get("q", "").strip()
    if action:
        q = q.filter(AuditLog.action == action)
    if who:
        q = q.filter(AuditLog.user_id == who)
    if text:
        q = q.filter(AuditLog.description.ilike(f"%{text}%"))
    page = q.order_by(AuditLog.id.desc()).paginate(page=request.args.get("page", 1, type=int), per_page=50, error_out=False)
    actions = [a for (a,) in db.session.query(AuditLog.action).distinct().order_by(AuditLog.action)]
    return render_template("operator/audit.html", page=page, actions=actions, action=action, who=who, q=text,
                           users=User.query.order_by(User.username).all())


@bp.route("/settings", methods=["GET", "POST"])
@operator_required
def settings():
    from app.services import settings_service as st
    if request.method == "POST":
        st.save_settings(g.user, request.form)
        return _ok("Settings saved.", "operator.settings")
    return render_template("operator/settings.html", fields=st.FIELDS, values=st.get_settings())
