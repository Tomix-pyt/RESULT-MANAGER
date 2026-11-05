import io
from html.parser import HTMLParser
import pytest
from app.extensions import db
from app.errors import ValidationError, DuplicateError, PermissionDenied
from app.models import (Student, StudentEnrollment, StudentSubject, ClassSession, StaffAssignment, Class,
                        Subject, AcademicSession, Setting, Score, Result)
from app.services import operator_service as ops, auth_service, settings_service


def login(c, u, p="password123"):
    return c.post("/login", data={"username": u, "password": p})


# ---------------- enrollment services ----------------
def test_student_cannot_be_in_two_classes_in_one_session(world):
    with pytest.raises(ValidationError, match="Transfer"):
        ops.enroll_student(world["op"], student_id=world["s1"].id, class_session_id=world["cs2"].id)


def test_bulk_enroll_reports_problems_per_student(world):
    s3 = ops.add_student(world["op"], admission_number="CSS/003", first_name="C", last_name="Cee")
    res = ops.bulk_enroll(world["op"], student_ids=[world["s1"].id, s3.id], class_session_id=world["cs1"].id)
    assert res["enrolled"] == 1 and len(res["problems"]) == 1       # s1 was already in


def test_roll_numbers_alphabetical(world):
    ops.assign_roll_numbers(world["op"], class_session_id=world["cs1"].id)
    rolls = {e.student.last_name: e.roll_number for e in StudentEnrollment.query.filter_by(class_session_id=world["cs1"].id)}
    assert rolls == {"Musa": 1, "Smith": 2}


def test_transfer_moves_student_and_rebuilds_subjects(world):
    en = world["en1"]
    ops.transfer_student(world["op"], enrollment_id=en.id, to_class_session_id=world["cs2"].id)
    db.session.refresh(en)
    assert en.class_session_id == world["cs2"].id
    assert [x.class_subject_id for x in en.subjects] == [world["m2"].id]          # JSS 2 only offers Maths
    with pytest.raises(ValidationError):                                           # new session -> must promote
        s2 = ops.create_academic_session(world["op"], name="2027/2028")
        c = ops.create_class_session(world["op"], class_id=1, academic_session_id=s2.id)
        ops.transfer_student(world["op"], enrollment_id=en.id, to_class_session_id=c.id)


def test_transfer_blocked_once_scores_exist(world):
    comp = ops.create_assessment_component(world["op"], class_subject_id=world["m1"].id, term_id=world["term"].id,
                                           name="CA 1", max_score=20, weight=20)
    db.session.add(Score(student_id=world["s1"].id, assessment_component_id=comp.id, score=10, entered_by=world["t1"].id))
    db.session.commit()
    with pytest.raises(ValidationError, match="scores"):
        ops.transfer_student(world["op"], enrollment_id=world["en1"].id, to_class_session_id=world["cs2"].id)


def test_promote_keeps_history_and_graduate(world):
    new = ops.create_academic_session(world["op"], name="2027/2028")
    cs_new = ops.create_class_session(world["op"], class_id=2, academic_session_id=new.id)
    res = ops.promote_students(world["op"], student_ids=[world["s1"].id], to_class_session_id=cs_new.id)
    assert res["enrolled"] == 1
    assert StudentEnrollment.query.filter_by(student_id=world["s1"].id).count() == 2      # old enrolment kept
    assert ops.graduate_students(world["op"], student_ids=[world["s2"].id]) == 1
    assert db.session.get(Student, world["s2"].id).status == "GRADUATED"


def test_csv_import_good_bad_and_enrol(world):
    csv_text = ("admission_number,first_name,last_name,gender,date_of_birth\n"
                "CSS/010,Ada,Obi,female,2012-05-01\n"
                "CSS/011,Bayo,Ade,male,03/04/2011\n"
                "CSS/010,Dup,Licate,,\n"
                ",NoNumber,X,,\n"
                "CSS/012,Bad,Date,,not-a-date\n")
    res = ops.import_students_csv(world["op"], text=csv_text, class_session_id=world["cs1"].id)
    assert res["created"] == 2 and res["enrolled"] == 2 and len(res["problems"]) == 3
    assert any("Line 4" in p for p in res["problems"])
    assert Student.query.filter_by(admission_number="CSS/010").one().gender == "Female"
    with pytest.raises(ValidationError, match="Missing column"):
        ops.import_students_csv(world["op"], text="name\nx\n")


def test_copy_class_setup_copies_subjects_and_teachers(world):
    new = ops.create_academic_session(world["op"], name="2027/2028")
    cs_new = ops.create_class_session(world["op"], class_id=1, academic_session_id=new.id)
    res = ops.copy_class_setup(world["op"], from_class_session_id=world["cs1"].id, to_class_session_id=cs_new.id)
    assert res == {"subjects": 2, "staff": 1}
    assert StaffAssignment.query.filter_by(academic_session_id=new.id).count() == 1


# ---------------- other CRUD ----------------
def test_edit_reactivate_delete_services(world):
    op = world["op"]
    ops.deactivate_class(op, class_id=1); ops.reactivate_class(op, class_id=1)
    assert db.session.get(Class, 1).is_active
    ops.deactivate_subject(op, subject_id=1); ops.reactivate_subject(op, subject_id=1)
    assert db.session.get(Subject, 1).is_active
    u = ops.update_user_account(op, user_id=world["t2"].id, first_name="Maria", email="Maria@X.com")
    assert u.first_name == "Maria" and u.email == "maria@x.com"
    with pytest.raises(ValidationError):
        ops.update_user_account(op, user_id=op.id, role="STAFF")                    # cannot demote yourself
    with pytest.raises(DuplicateError):
        ops.update_user_account(op, user_id=world["t1"].id, email="maria@x.com")
    empty = ops.create_academic_session(op, name="2030/2031")
    ops.delete_academic_session(op, session_id=empty.id)
    with pytest.raises(ValidationError):
        ops.delete_academic_session(op, session_id=world["ses"].id)                 # has classes
    sc = ops.create_grading_scale(op, name="Old", academic_session_id=world["ses"].id)
    ops.update_grading_scale(op, scale_id=sc.id, name="New")
    ops.delete_grading_scale(op, scale_id=sc.id)


def test_settings_roundtrip(world):
    settings_service.save_settings(world["op"], {"principal_name": "  Mrs Ade  ", "bogus": "x"})
    assert settings_service.get_settings()["principal_name"] == "Mrs Ade"
    assert db.session.get(Setting, "bogus") is None
    with pytest.raises(PermissionDenied):
        settings_service.save_settings(world["t1"], {"principal_name": "Hacker"})


# ---------------- web layer ----------------
class FormNesting(HTMLParser):
    def __init__(self):
        super().__init__(); self.depth = 0; self.bad = False
    def handle_starttag(self, tag, attrs):
        if tag == "form":
            self.depth += 1
            if self.depth > 1: self.bad = True
    def handle_endtag(self, tag):
        if tag == "form": self.depth -= 1


def test_no_page_has_nested_forms_and_every_page_renders(client, world):
    ops.set_student_status  # noqa
    login(client, "admin")
    urls = ["/admin/", "/admin/sessions", "/admin/classes", "/admin/class-sessions/1", "/admin/subjects",
            "/admin/students", "/admin/students/1", "/admin/grading", "/admin/class-subjects/1/assessments",
            "/admin/users", "/admin/enrollment", "/admin/enrollment?cs_id=1", "/admin/audit",
            "/admin/audit?action=ENROLL_STUDENT&q=student", "/admin/settings"]
    ops.create_grading_scale(world["op"], name="Std", academic_session_id=world["ses"].id)
    for u in urls:
        r = client.get(u)
        assert r.status_code == 200, u
        p = FormNesting(); p.feed(r.get_data(as_text=True))
        assert not p.bad, f"nested <form> on {u}"


def test_enrollment_screens_end_to_end(client, world):
    login(client, "admin")
    post = lambda url, **d: client.post(url, data=d, follow_redirects=True)
    s3 = ops.add_student(world["op"], admission_number="CSS/003", first_name="Cee", last_name="Zed")
    r = post("/admin/enrollment/1/bulk", student_ids=[str(s3.id)])
    assert "Enrolled 1" in r.get_data(as_text=True)
    r = post("/admin/enrollment/1/bulk")
    assert "Tick at least one" in r.get_data(as_text=True)
    post("/admin/enrollment/1/roll-numbers")
    assert StudentEnrollment.query.filter_by(class_session_id=1, roll_number=3).count() == 1
    r = post("/admin/enrollment/1/import", file=(io.BytesIO(b"admission_number,first_name,last_name\nCSS/050,Imp,Orted\n"), "s.csv"), enroll="on")
    assert "Imported 1" in r.get_data(as_text=True)
    en = StudentEnrollment.query.filter_by(class_session_id=1).first()
    post(f"/admin/enrollments/{en.id}/transfer", to_cs_id="2")
    assert db.session.get(StudentEnrollment, en.id).class_session_id == 2
    post("/admin/enrollment/1/graduate", student_ids=[str(s3.id)])
    assert db.session.get(Student, s3.id).status == "GRADUATED"


def test_crud_screens_and_staff_blocked(client, world):
    login(client, "admin")
    post = lambda url, **d: client.post(url, data=d, follow_redirects=True)
    assert "updated" in post("/admin/classes/1/edit", name="JSS 1 Gold", level="JSS 1", arm="G").get_data(as_text=True)
    assert "updated" in post("/admin/subjects/1/edit", code="MTH", name="Maths", description="").get_data(as_text=True)
    assert "updated" in post(f"/admin/users/{world['t2'].id}/edit", first_name="Mary", last_name="Roe", email="", role="STAFF").get_data(as_text=True)
    assert "settings saved" in post("/admin/settings", principal_name="Mrs Ade").get_data(as_text=True).lower()
    c2 = client.application.test_client(); login(c2, "teacher1")
    for url in ["/admin/enrollment", "/admin/audit", "/admin/settings"]:
        assert c2.get(url).status_code == 403
    for url in ["/admin/enrollment/1/bulk", "/admin/enrollments/1/transfer", "/admin/classes/1/edit",
                "/admin/sessions/1/delete", "/admin/settings", "/admin/users/1/edit"]:
        assert c2.post(url, data={}).status_code == 403
