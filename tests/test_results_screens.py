import re, html as htmllib
from io import BytesIO
import pytest
from app.models import Score, Result, StudentTermReport, AuditLog
from app.services import operator_service as ops, dashboard_service
from tests.test_results_engine import school   # noqa: F401  (fixture)


def login(c, u="admin"):
    c.post("/login", data={"username": u, "password": "password123"})


def fields(w, csub, ca1, ca2, ca3, exam):
    return {f"c{w['comps'][(csub.id, n)].id}": str(v) for n, v in
            [("CA 1", ca1), ("CA 2", ca2), ("CA 3", ca3), ("Exam", exam)]}


def test_score_entry_screen_saves_per_student_and_returns_live_results(client, school):
    w = school; login(client)
    page = client.get(f"/admin/class-sessions/{w['cs1'].id}/scores?term_id={w['term'].id}")
    html = page.get_data(as_text=True)
    assert page.status_code == 200 and html.count('class="slide"') == 3 and "css/pages/score-entry.css" in html
    r = client.post(f"/admin/enrollments/{w['en1'].id}/scores",
                    data={"term_id": w["term"].id, **fields(w, w["m1"], 9, 8, 10, 60), "form_teacher_remark": "Good",
                          "principal_remark": "Promoted", "r_neatness": "2"},
                    headers={"X-Requested-With": "fetch"})
    j = r.get_json()
    assert r.status_code == 200 and j["ok"] and j["changed"] == 4
    assert j["rows"][str(w["m1"].id)] == {"total": "87", "grade": "A", "position": "1st"}
    rep = StudentTermReport.query.filter_by(enrollment_id=w["en1"].id).first()
    assert rep.form_teacher_remark == "Good" and rep.principal_remark == "Promoted"
    bad = client.post(f"/admin/enrollments/{w['en3'].id}/scores", data={"term_id": w["term"].id, **fields(w, w["m1"], 99, 1, 1, 1)},
                      headers={"X-Requested-With": "fetch"})
    assert bad.status_code == 400 and "between 0 and 10" in bad.get_json()["error"]
    assert Score.query.filter_by(student_id=w["s3"].id).count() == 0
    nojs = client.post(f"/admin/enrollments/{w['en3'].id}/scores", data={"term_id": w["term"].id, **fields(w, w["m1"], 5, 5, 5, 40),
                       "back": f"/admin/class-sessions/{w['cs1'].id}/scores?term_id={w['term'].id}"})
    assert nojs.status_code == 302 and nojs.headers["Location"].endswith(f"#slide-{w['en3'].id}")
    assert client.post(f"/admin/enrollments/{w['en3'].id}/scores", data={"term_id": w["term"].id, "back": "https://evil.example/"}).headers["Location"].startswith("/admin/")


def test_lock_from_the_class_page_blocks_the_entry_screen(client, school):
    w = school; login(client)
    client.post(f"/admin/enrollments/{w['en1'].id}/scores", data={"term_id": w["term"].id, **fields(w, w["m1"], 9, 8, 10, 60)})
    client.post(f"/admin/class-sessions/{w['cs1'].id}/lock", data={"term_id": w["term"].id, "lock": "1"})
    assert Result.query.filter_by(status="LOCKED").count() > 0
    r = client.post(f"/admin/enrollments/{w['en1'].id}/scores", data={"term_id": w["term"].id, **fields(w, w["m1"], 1, 1, 1, 1)},
                    headers={"X-Requested-With": "fetch"})
    assert r.status_code == 400 and "locked" in r.get_json()["error"]
    assert "This term is locked" in client.get(f"/admin/class-sessions/{w['cs1'].id}/scores?term_id={w['term'].id}").get_data(as_text=True)
    client.post(f"/admin/class-sessions/{w['cs1'].id}/lock", data={"term_id": w["term"].id, "lock": "0"})
    ok = client.post(f"/admin/enrollments/{w['en1'].id}/scores", data={"term_id": w["term"].id, **fields(w, w["m1"], 1, 1, 1, 1)},
                     headers={"X-Requested-With": "fetch"})
    assert ok.status_code == 200


def test_printing_preview_pdf_and_nothing_stored(client, school):
    w = school; login(client)
    client.post(f"/admin/enrollments/{w['en1'].id}/scores", data={"term_id": w["term"].id, **fields(w, w["m1"], 9, 8, 10, 60)})
    base = f"/admin/class-sessions/{w['cs1'].id}/results"
    one = client.get(f"{base}?term_id={w['term'].id}&kind=terminal&enrollment={w['en1'].id}").get_data(as_text=True)
    assert one.count('<section class="sheet') == 1 and "SMITH Jane" in one
    one = htmllib.unescape(one)
    for text in ["STUDENT'S TERMINAL CONTINUOUS ASSESSMENT PERFOMANCE BREAKDOWN", "AFFECTIVE DEVELOPMENT", "PSHYCHOMOTOR", "Highest in Class",
                 "Lowest in Class", "Total obtainable  Marks:", "Postion:", "Grading keys:", "TEACHER'S REMARKS", "Kwagh Joseph"]:
        assert text in one, text
    whole = client.get(f"{base}?term_id={w['term'].id}&kind=terminal").get_data(as_text=True)
    assert whole.count('<section class="sheet') == 3                              # whole class = one sheet per student
    annual = client.get(f"{base}?kind=annual").get_data(as_text=True)
    assert "ANNUAL CONTINUOUS ASSESSMENT" in annual and "1st Term" in annual
    pdf = client.get(f"{base}.pdf?term_id={w['term'].id}&kind=terminal")
    assert pdf.status_code == 200 and pdf.data[:5] == b"%PDF-" and pdf.mimetype == "application/pdf"
    from pypdf import PdfReader
    pages = PdfReader(BytesIO(pdf.data)).pages
    assert len(pages) == 3, "3 students must give exactly 3 A4 pages"
    assert round(float(pages[0].mediabox.width)) == 595 and round(float(pages[0].mediabox.height)) == 842      # A4
    import os, glob
    assert not glob.glob(os.path.join(client.application.instance_path, "**", "*.pdf"), recursive=True)   # nothing saved to disk
    assert AuditLog.query.filter_by(action="PRINT_RESULTS").count() == 1
    assert client.get(f"{base}?kind=bogus").status_code == 404


def test_one_student_is_exactly_one_page_even_with_many_subjects(client, school):
    """The template has 12 subject rows; a class with more must still fit one A4 page."""
    w = school; login(client)
    for i in range(6):                                                    # 2 + 6 = 8 subjects (blank rows pad to 12)
        s = ops.create_subject(w["op"], code=f"x{i}", name=f"Extra {i}")
        ops.add_subject_to_class(w["op"], class_session_id=w["cs1"].id, subject_id=s.id)
    pdf = client.get(f"/admin/class-sessions/{w['cs1'].id}/results.pdf?term_id={w['term'].id}&kind=terminal&enrollment={w['en1'].id}")
    from pypdf import PdfReader
    assert len(PdfReader(BytesIO(pdf.data)).pages) == 1
    for i in range(6, 11):                                                # 13 subjects: rows compress, still one page
        s = ops.create_subject(w["op"], code=f"x{i}", name=f"Extra {i}")
        ops.add_subject_to_class(w["op"], class_session_id=w["cs1"].id, subject_id=s.id)
    pdf = client.get(f"/admin/class-sessions/{w['cs1'].id}/results.pdf?term_id={w['term'].id}&kind=terminal&enrollment={w['en1'].id}")
    assert len(PdfReader(BytesIO(pdf.data)).pages) == 1


def test_printing_is_never_stale_after_a_correction(client, school):
    w = school; login(client)
    url = f"/admin/class-sessions/{w['cs1'].id}/results?term_id={w['term'].id}&kind=terminal&enrollment={w['en1'].id}"
    client.post(f"/admin/enrollments/{w['en1'].id}/scores", data={"term_id": w["term"].id, **fields(w, w["m1"], 9, 8, 10, 60)})
    assert ">87<" in client.get(url).get_data(as_text=True)
    client.post(f"/admin/enrollments/{w['en1'].id}/scores", data={"term_id": w["term"].id, **fields(w, w["m1"], 9, 8, 10, 40)})
    page = client.get(url).get_data(as_text=True)
    assert ">67<" in page and ">87<" not in page


def test_graduated_students_leave_the_active_lists_but_keep_their_results(client, school):
    w = school; login(client)
    client.post(f"/admin/enrollments/{w['en1'].id}/scores", data={"term_id": w["term"].id, **fields(w, w["m1"], 9, 8, 10, 60)})
    ops.set_student_status(w["op"], student_id=w["s1"].id, status="GRADUATED")
    cls = client.get(f"/admin/class-sessions/{w['cs1'].id}").get_data(as_text=True)
    assert "Left the school (1)" in cls
    assert "Jane" not in client.get("/admin/students").get_data(as_text=True)
    assert "SMITH Jane" in client.get("/admin/students/former").get_data(as_text=True)
    assert "SMITH Jane" in client.get("/admin/students/former?status=GRADUATED").get_data(as_text=True)
    assert client.get(f"/admin/class-sessions/{w['cs1'].id}/scores?term_id={w['term'].id}").get_data(as_text=True).count('class="slide"') == 2
    assert "Jane" not in "".join(re.findall(r'<option value="\d+"[^>]*>[^<]*</option>',
                                            client.get(f"/admin/enrollment?cs_id={w['cs1'].id}").get_data(as_text=True)))
    assert client.get(f"/admin/enrollments/{w['en1'].id}/scores?term_id={w['term'].id}").status_code == 200
    sheet = client.get(f"/admin/class-sessions/{w['cs1'].id}/results?term_id={w['term'].id}&kind=terminal&enrollment={w['en1'].id}")
    assert sheet.status_code == 200 and ">87<" in sheet.get_data(as_text=True)
    detail = client.get(f"/admin/students/{w['s1'].id}").get_data(as_text=True)
    assert "Terminal result" in detail and "Annual result" in detail and 'details class="edit details-btn"' in detail


def test_add_student_page_and_dashboard_kpi(client, world):
    login(client)
    assert dashboard_service.operator_stats()["unenrolled"] == 0
    assert 'href="/admin/students/new"' in client.get("/admin/students").get_data(as_text=True)
    assert "Add a student</h2>" not in client.get("/admin/students").get_data(as_text=True)
    r = client.post("/admin/students/new", data={"admission_number": "CSS/050", "first_name": "New", "last_name": "Kid"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/admin/students")            # does NOT open the student
    assert dashboard_service.operator_stats()["unenrolled"] == 1
    assert "Added, not enrolled" in client.get("/admin/").get_data(as_text=True)
    again = client.post("/admin/students/new", data={"admission_number": "CSS/051", "first_name": "N", "last_name": "K", "again": "1"})
    assert again.headers["Location"].endswith("/admin/students/new")
    assert "Not enrolled" in client.get("/admin/students").get_data(as_text=True)


def test_assessment_screen_shows_printed_columns(client, school):
    login(client)
    html = client.get(f"/admin/class-subjects/{school['m1'].id}/assessments").get_data(as_text=True)
    assert "1'st CA" in html and "Exams" in html and "Printed as" in html


def test_settings_branding_and_staff_lockout(client, school):
    w = school; login(client)
    assert client.get("/admin/branding/logo").mimetype == "image/png"
    assert client.get("/admin/branding/../../etc/passwd").status_code == 404
    assert "School logo" in client.get("/admin/settings").get_data(as_text=True)
    client.post("/logout"); login(client, "teacher1")
    for url in [f"/admin/class-sessions/{w['cs1'].id}/results", f"/admin/class-sessions/{w['cs1'].id}/results.pdf",
                f"/admin/class-sessions/{w['cs1'].id}/scores", f"/admin/enrollments/{w['en1'].id}/scores",
                "/admin/students/new", "/admin/students/former"]:
        assert client.get(url).status_code == 403, url
    for url in [f"/admin/enrollments/{w['en1'].id}/scores", f"/admin/class-sessions/{w['cs1'].id}/lock",
                f"/admin/class-sessions/{w['cs1'].id}/form-teacher", "/admin/branding/logo/upload"]:
        assert client.post(url, data={}).status_code == 403, url
