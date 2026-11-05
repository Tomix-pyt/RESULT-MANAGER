import re
from app.models import (Student, StudentSubject, StaffAssignment, AssessmentComponent, GradeBoundary,
                        Term, ClassSession, AuditLog)
from app.services import auth_service


def login(c, u, p="password123"):
    return c.post("/login", data={"username": u, "password": p})


def test_full_school_setup_through_the_screens(client, app):
    auth_service.create_user(username="admin", first_name="A", last_name="D", password="password123", role="OPERATOR")
    auth_service.create_user(username="t1", first_name="John", last_name="Doe", password="password123")
    login(client, "admin")
    post = lambda url, **d: client.post(url, data=d, follow_redirects=True)

    post("/admin/sessions", name="2026/2027", current="on")
    post("/admin/sessions/1/terms", name="First Term")
    post("/admin/terms/1/current")
    post("/admin/terms/1/deadline", edit_deadline="2026-12-01T17:00")
    assert Term.query.get(1).edit_deadline.day == 1 and Term.query.get(1).is_current

    post("/admin/classes", name="JSS 1 A", level="JSS 1", arm="A")
    post("/admin/classes/1/open", session_id="1")
    assert ClassSession.query.count() == 1

    post("/admin/subjects", code="math", name="Mathematics")
    post("/admin/class-sessions/1/subjects", subject_id="1")
    post("/admin/class-subjects/1/assign", staff_id="2")
    assert StaffAssignment.query.count() == 1

    post("/admin/students/new", admission_number="CSS/001", first_name="Jane", last_name="Smith")
    post("/admin/class-sessions/1/enroll", student_id="1")
    assert StudentSubject.query.count() == 1                                  # inferred from the class

    post("/admin/class-subjects/1/assessments", term_id="1", name="CA 1", max_score="20", weight="20")
    post("/admin/class-subjects/1/assessments", term_id="1", name="Exam", max_score="80", weight="80")
    assert AssessmentComponent.query.count() == 2
    page = client.get("/admin/class-subjects/1/assessments").get_data(as_text=True)
    assert "not 100" not in page                                              # weights total 100

    post("/admin/enrollments/1/subjects/1/remove")                            # drop Maths for this student
    assert StudentSubject.query.count() == 0
    post("/admin/enrollments/1/subjects/1/add")
    assert StudentSubject.query.count() == 1

    post("/admin/grading", name="Std", session_id="1", load_default="on")
    assert GradeBoundary.query.count() == 6

    for url in ["/admin/", "/admin/sessions", "/admin/classes", "/admin/class-sessions/1", "/admin/subjects",
                "/admin/students", "/admin/students/new", "/admin/students/former", "/admin/students?q=jane", "/admin/students/1", "/admin/grading",
                "/admin/class-subjects/1/assessments", "/admin/users"]:
        assert client.get(url).status_code == 200, url
    assert "Jane" in client.get("/admin/students?q=smith").get_data(as_text=True)
    assert AuditLog.query.filter_by(action="ENROLL_STUDENT").count() == 1


def test_friendly_errors_not_crashes(client, app):
    auth_service.create_user(username="admin", first_name="A", last_name="D", password="password123", role="OPERATOR")
    login(client, "admin")
    r = client.post("/admin/subjects", data={"code": "", "name": ""}, follow_redirects=True)
    assert r.status_code == 200 and "required" in r.get_data(as_text=True)
    r = client.post("/admin/sessions", data={"name": "X", "start_date": "not-a-date"}, follow_redirects=True)
    assert "Invalid date" in r.get_data(as_text=True)
    assert client.get("/admin/students/999").status_code == 404
    assert client.get("/admin/class-sessions/999").status_code == 404


def test_staff_locked_out_of_every_admin_page(client, world):
    login(client, "teacher1")
    for url in ["/admin/", "/admin/sessions", "/admin/classes", "/admin/subjects", "/admin/students",
                "/admin/students/1", "/admin/grading", "/admin/class-sessions/1",
                "/admin/class-subjects/1/assessments", "/admin/users"]:
        assert client.get(url).status_code == 403, url
    for url in ["/admin/sessions", "/admin/subjects", "/admin/students/new", "/admin/class-sessions/1/enroll",
                "/admin/class-subjects/1/assign", "/admin/enrollments/1/subjects/1/remove",
                "/admin/grading", "/admin/assessments/1/delete"]:
        assert client.post(url, data={}).status_code == 403, url
