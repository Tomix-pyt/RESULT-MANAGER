"""Builds the data for the result sheets (terminal and annual) and turns the HTML into a PDF on demand.
Nothing is stored: a PDF exists only for the moment it is sent to the browser."""
from datetime import date
from decimal import Decimal
from io import BytesIO
from collections import defaultdict
from app.extensions import db
from app.errors import NotFoundError, ValidationError
from app.models import (ClassSession, StudentEnrollment, Term, Score, Result, StudentTermReport, StudentTrait)
from app import report_labels as L
from app.services import result_service, settings_service, traits_service


# ------------------------------------------------------------------ formatting
def fmt_mark(v) -> str:
    if v is None:
        return ""
    v = Decimal(v)
    return str(int(v)) if v == v.to_integral() else format(v.normalize(), "f")


def ordinal(n) -> str:
    if n is None:
        return ""
    n = int(n)
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def fmt_date(d) -> str:
    if isinstance(d, date):
        return d.strftime("%d/%m/%Y")
    return d or ""


def fmt_pct(v) -> str:
    return "" if v is None else format(Decimal(v).quantize(Decimal("0.01")), "f").rstrip("0").rstrip(".")


# ------------------------------------------------------------------ shared pieces
def school_block() -> dict:
    st = settings_service.get_settings()
    pick = lambda k: (st.get(k) or "").strip() or L.SCHOOL_DEFAULTS.get(k, "")
    return {"name": pick("school_name"), "region": pick("school_region"), "address": pick("school_address"),
            "principal": pick("principal_name"), "next_term_text": st.get("next_term_begins") or ""}


def grading_key(scale) -> dict:
    if scale is None or not scale.boundaries:
        return {"fallback": L.GRADING_KEY_FALLBACK, "parts": []}
    parts = []
    for i, b in enumerate(sorted(scale.boundaries, key=lambda b: b.min_score, reverse=True)):
        rng = f"{fmt_mark(b.min_score)} and above" if i == 0 else f"{fmt_mark(b.min_score)}-{fmt_mark(b.max_score)}"
        parts.append({"grade": b.grade, "remark": b.remark or "", "range": rng})
    return {"fallback": None, "parts": parts}


def _traits_block(enrollment_id, term_id):
    t = traits_service.get_traits(enrollment_id, term_id)
    pick = lambda key: (t[key].rating if key in t else "")
    return ([(label, pick(k)) for k, label in L.AFFECTIVE], [(label, pick(k)) for k, label in L.PSYCHOMOTOR])


def _student_block(enr, term_label, vacation, next_term, session_name):
    st = enr.student
    return {"name": st.full_name, "sex": st.gender or "", "class": enr.class_session.class_.name,
            "term": term_label, "id": st.admission_number, "session": session_name,
            "vacation": vacation, "next_term": next_term}


def _ordered_enrollments(class_session_id, enrollment_ids=None):
    q = StudentEnrollment.query.filter_by(class_session_id=class_session_id)
    if enrollment_ids is not None:
        q = q.filter(StudentEnrollment.id.in_(list(enrollment_ids) or [0]))
    return sorted(q.all(), key=lambda e: (e.roll_number or 10**6, e.student.last_name.lower(), e.student.first_name.lower()))


def _finish(card, scale, kind, n_subjects):
    card["kind"] = kind
    card["n_rows"] = max(12, n_subjects)
    card["blank_rows"] = card["n_rows"] - n_subjects
    card["dense"] = max(0, min(n_subjects, 30)) if n_subjects > 12 else 0       # css class: dense-13 ... dense-30
    card["grading_key"] = grading_key(scale)
    card["rating_key"] = L.RATING_KEY
    return card


# ------------------------------------------------------------------ terminal
def terminal_cards(class_session_id: int, term_id: int, enrollment_ids=None) -> list[dict]:
    cs = db.session.get(ClassSession, class_session_id)
    term = db.session.get(Term, term_id)
    if cs is None or term is None:
        raise NotFoundError("Class or term not found.")
    if term.academic_session_id != cs.academic_session_id:
        raise ValidationError("That term belongs to a different session.")
    result_service.compile_class_term(class_session_id, term_id)      # a print is never stale
    db.session.commit()

    school = school_block()
    scale = result_service.grading_scale_for(cs.academic_session_id)
    enrollments = _ordered_enrollments(class_session_id, enrollment_ids)
    csubs = {x.id: x for x in cs.class_subjects}
    comps = result_service.slotted_components(list(csubs), term_id)
    comp_ids = [c.id for lst in comps.values() for c in lst]
    scores = {(s.student_id, s.assessment_component_id): s.score for s in
              Score.query.filter(Score.assessment_component_id.in_(comp_ids or [0]))}
    results = {(r.student_id, r.class_subject_id): r for r in
               Result.query.filter(Result.term_id == term_id, Result.class_subject_id.in_(list(csubs) or [0]))}
    reports = {r.enrollment_id: r for r in StudentTermReport.query.filter_by(term_id=term_id)}
    next_term = fmt_date(term.next_term_begins) or school["next_term_text"]
    teacher = cs.form_teacher.full_name if cs.form_teacher else ""

    cards = []
    for enr in enrollments:
        rows = []
        for csub in sorted((ss.class_subject for ss in enr.subjects), key=lambda c: c.subject.name):
            by_slot = {c.report_slot: c for c in comps.get(csub.id, [])}
            r = results.get((enr.student_id, csub.id))
            rows.append({
                "name": csub.subject.name,
                "scores": [fmt_mark(scores.get((enr.student_id, by_slot[i].id))) if i in by_slot else "" for i in (1, 2, 3, 4)],
                "total": fmt_mark(r.total_score) if r else "", "highest": fmt_mark(r.class_highest) if r else "",
                "lowest": fmt_mark(r.class_lowest) if r else "", "position": ordinal(r.position) if r else "",
                "grade": (r.grade or "") if r else "", "remark": (r.remark or "") if r else ""})
        rep = reports.get(enr.id)
        aff, psy = _traits_block(enr.id, term_id)
        card = {
            "school": school, "student": _student_block(enr, term.name, fmt_date(term.end_date), next_term, cs.academic_session.name),
            "columns": L.SCORE_COLUMNS + L.RESULT_COLUMNS, "rows": rows,
            "obtainable": fmt_mark(rep.total_obtainable) if rep else "", "obtained": fmt_mark(rep.total_obtained) if rep else "",
            "class_size": rep.class_size if rep and rep.class_size else len(cs.student_enrollments),
            "average": fmt_pct(rep.average) if rep else "", "position": ordinal(rep.position) if rep else "",
            "affective": aff, "psychomotor": psy,
            "form_remark": (rep.form_teacher_remark or "") if rep else "", "form_teacher": teacher,
            "principal_remark": (rep.principal_remark or "") if rep else "", "principal": school["principal"],
            "date": fmt_date(term.end_date), "enrollment_id": enr.id}
        cards.append(_finish(card, scale, "terminal", len(rows)))
    return cards


# ------------------------------------------------------------------ annual
def annual_cards(class_session_id: int, enrollment_ids=None) -> list[dict]:
    cs = db.session.get(ClassSession, class_session_id)
    if cs is None:
        raise NotFoundError("Class not found.")
    data = result_service.annual_class(class_session_id)
    terms = Term.query.filter_by(academic_session_id=cs.academic_session_id).order_by(Term.id).limit(3).all()
    school = school_block()
    scale = result_service.grading_scale_for(cs.academic_session_id)
    last = terms[-1] if terms else None
    next_term = (fmt_date(last.next_term_begins) if last else "") or school["next_term_text"]
    teacher = cs.form_teacher.full_name if cs.form_teacher else ""
    reports = defaultdict(dict)
    for r in StudentTermReport.query.filter(StudentTermReport.term_id.in_([t.id for t in terms] or [0])):
        reports[r.enrollment_id][r.term_id] = r

    cards = []
    for enr in _ordered_enrollments(class_session_id, enrollment_ids):
        d = data[enr.id]
        rows = []
        for csub in sorted((ss.class_subject for ss in enr.subjects), key=lambda c: c.subject.name):
            s = d["subjects"].get(csub.id)
            per = s["per_term"] if s else {}
            term_vals = [fmt_mark(per.get(t.id)) for t in terms] + [""] * (3 - len(terms))
            grade, remark = result_service.grade_for(scale, s["average"]) if s else (None, None)
            rows.append({
                "name": csub.subject.name, "scores": term_vals,
                "total": fmt_mark(sum(per.values())) if per else "", "average": fmt_mark(s["average"]) if s else "",
                "highest": fmt_mark(s["highest"]) if s else "", "lowest": fmt_mark(s["lowest"]) if s else "",
                "position": ordinal(s["position"]) if s else "", "grade": grade or "", "remark": remark or ""})
        # ratings and remarks come from the latest term that has a report for this student
        latest = next((reports[enr.id][t.id] for t in reversed(terms) if t.id in reports[enr.id]), None)
        latest_term_id = next((t.id for t in reversed(terms) if t.id in reports[enr.id]), None)
        aff, psy = _traits_block(enr.id, latest_term_id) if latest_term_id else _traits_block(enr.id, 0)
        card = {
            "school": school,
            "student": _student_block(enr, "Annual", fmt_date(last.end_date) if last else "", next_term, cs.academic_session.name),
            "columns": L.ANNUAL_COLUMNS, "rows": rows,
            "obtainable": fmt_mark(d["obtainable"]) if d["subjects"] else "", "obtained": fmt_mark(d["obtained"]) if d["subjects"] else "",
            "class_size": d["class_size"], "average": fmt_pct(d["average"]), "position": ordinal(d["position"]),
            "affective": aff, "psychomotor": psy,
            "form_remark": (latest.form_teacher_remark or "") if latest else "", "form_teacher": teacher,
            "principal_remark": (latest.principal_remark or "") if latest else "", "principal": school["principal"],
            "date": fmt_date(last.end_date) if last else "", "enrollment_id": enr.id}
        cards.append(_finish(card, scale, "annual", len(rows)))
    return cards


# ------------------------------------------------------------------ PDF (on demand, in memory, never stored)
def render_pdf(html: str, base_url: str) -> bytes:
    try:
        from weasyprint import HTML
    except Exception as exc:                                    # pragma: no cover
        raise RuntimeError("PDF engine (WeasyPrint) is not installed or its system libraries are missing.") from exc
    buf = BytesIO()
    HTML(string=html, base_url=base_url).write_pdf(buf)
    return buf.getvalue()
