import pytest
from sqlalchemy.exc import IntegrityError
from app.extensions import db
from app.errors import PermissionDenied, ValidationError, DuplicateError
from app.models import Score, AssessmentComponent, Result, StudentSubject
from app.services import authorization_service as authz, operator_service as ops, auth_service


# ---------- authorization (spec: "Teacher A" example) ----------
def test_staff_only_reaches_assigned_class_subject(world):
    t1, m1, e1, m2 = world["t1"], world["m1"], world["e1"], world["m2"]
    authz.require_staff_assignment(t1, m1.id)                  # JSS 1 Maths -> allowed
    with pytest.raises(PermissionDenied):
        authz.require_staff_assignment(t1, m2.id)              # JSS 2 Maths -> rejected
    with pytest.raises(PermissionDenied):
        authz.require_staff_assignment(t1, e1.id)              # JSS 1 English -> rejected


def test_unassigned_staff_rejected_operator_allowed(world):
    with pytest.raises(PermissionDenied):
        authz.require_staff_assignment(world["t2"], world["m1"].id)
    authz.require_staff_assignment(world["op"], world["m1"].id)


def test_staff_cannot_use_operator_services(world):
    with pytest.raises(PermissionDenied):
        ops.create_subject(world["t1"], code="x", name="X")
    with pytest.raises(PermissionDenied):
        ops.create_user_account(world["t1"], username="u", first_name="a", last_name="b", password="password123")


def _score(w, status=None):
    comp = ops.create_assessment_component(w["op"], class_subject_id=w["m1"].id, term_id=w["term"].id,
                                           name="CA 1", max_score=20, weight=20)
    sc = Score(student_id=w["s1"].id, assessment_component_id=comp.id, score=15, entered_by=w["t1"].id)
    db.session.add(sc)
    if status:
        db.session.add(Result(student_id=w["s1"].id, class_subject_id=w["m1"].id, term_id=w["term"].id, status=status))
    db.session.commit()
    return sc


@pytest.mark.parametrize("status,staff_ok,op_ok", [
    (None, True, True), ("DRAFT", True, True), ("SUBMITTED", False, True), ("APPROVED", False, True),
    ("LOCKED", False, False), ("PUBLISHED", False, False), ("REOPENED", True, True)])
def test_score_edit_rules_by_result_status(world, status, staff_ok, op_ok):
    sc = _score(world, status)
    assert authz.can_edit_score(world["t1"], sc) is staff_ok
    assert authz.can_edit_score(world["op"], sc) is op_ok
    assert authz.can_edit_score(world["t2"], sc) is False      # unassigned staff never


# ---------- per-student subjects ----------
def test_enrollment_infers_subjects_and_operator_can_adjust(world):
    en = world["en1"]
    assert {s.class_subject_id for s in en.subjects} == {world["m1"].id, world["e1"].id}
    ops.remove_student_subject(world["op"], enrollment_id=en.id, class_subject_id=world["e1"].id)
    assert StudentSubject.query.filter_by(enrollment_id=en.id).count() == 1
    ops.add_student_subject(world["op"], enrollment_id=en.id, class_subject_id=world["e1"].id)
    assert StudentSubject.query.filter_by(enrollment_id=en.id).count() == 2
    with pytest.raises(ValidationError):                         # subject from another class
        ops.add_student_subject(world["op"], enrollment_id=en.id, class_subject_id=world["m2"].id)


def test_new_class_subject_reaches_students_already_enrolled(world):
    bio = ops.create_subject(world["op"], code="bio", name="Biology")
    cs = ops.add_subject_to_class(world["op"], class_session_id=world["cs1"].id, subject_id=bio.id)
    assert StudentSubject.query.filter_by(class_subject_id=cs.id).count() == 2


def test_cannot_drop_subject_that_has_scores(world):
    _score(world)
    with pytest.raises(ValidationError):
        ops.remove_student_subject(world["op"], enrollment_id=world["en1"].id, class_subject_id=world["m1"].id)


# ---------- data integrity ----------
def test_duplicates_rejected(world):
    with pytest.raises(DuplicateError):
        ops.add_student(world["op"], admission_number="CSS/001", first_name="X", last_name="Y")
    with pytest.raises(DuplicateError):
        ops.create_class_session(world["op"], class_id=1, academic_session_id=world["ses"].id)
    with pytest.raises(DuplicateError):
        auth_service.create_user(username="TEACHER1", first_name="a", last_name="b", password="password123")


def test_negative_score_blocked_by_database(world):
    comp = ops.create_assessment_component(world["op"], class_subject_id=world["m1"].id,
                                           term_id=world["term"].id, name="CA 1", max_score=20, weight=20)
    db.session.add(Score(student_id=world["s1"].id, assessment_component_id=comp.id, score=-1, entered_by=world["t1"].id))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_grade_boundaries_cannot_overlap(world):
    sc = ops.create_grading_scale(world["op"], name="Std", academic_session_id=world["ses"].id)
    ops.add_grade_boundary(world["op"], grading_scale_id=sc.id, min_score=70, max_score=100, grade="A")
    with pytest.raises(DuplicateError):
        ops.add_grade_boundary(world["op"], grading_scale_id=sc.id, min_score=60, max_score=75, grade="B")
    with pytest.raises(ValidationError, match="already has a grading scale"):
        ops.create_grading_scale(world["op"], name="Another scale", academic_session_id=world["ses"].id)


def test_passwords_are_hashed_and_short_ones_rejected(world):
    assert world["t1"].password_hash != "password123"
    with pytest.raises(ValidationError):
        auth_service.create_user(username="z", first_name="a", last_name="b", password="short")


def test_only_one_current_session_and_term(world):
    s2 = ops.create_academic_session(world["op"], name="2027/2028", make_current=True)
    from app.models import AcademicSession
    assert [s.name for s in AcademicSession.query.filter_by(is_current=True)] == ["2027/2028"]


# ---------- web layer ----------
def login(client, u, p="password123"):
    return client.post("/login", data={"username": u, "password": p})


def test_login_flow_and_role_separation(client, world):
    assert client.get("/admin/").status_code == 302                      # anonymous -> login
    assert login(client, "teacher1", "wrong").status_code == 401
    r = login(client, "teacher1")
    assert r.headers["Location"].endswith("/staff/")
    assert client.get("/staff/").status_code == 200
    assert client.get("/admin/").status_code == 403                      # staff blocked from admin pages
    assert client.get("/admin/users").status_code == 403
    r = client.post("/admin/users", data={"username": "hax", "first_name": "a", "last_name": "b", "password": "password123"})
    assert r.status_code == 403                                          # ...and from admin actions


def test_operator_can_manage_users_and_disabled_user_is_locked_out(client, world):
    login(client, "admin")
    assert client.get("/admin/").status_code == 200
    r = client.post("/admin/users", data={"username": "newbie", "first_name": "N", "last_name": "B",
                                           "password": "password123", "role": "STAFF"})
    assert r.status_code == 302
    client.post(f"/admin/users/{world['t1'].id}/active", data={"active": "0"})
    other = client.application.test_client()
    assert login(other, "teacher1").status_code == 401


def test_logged_in_session_dies_when_user_deactivated(client, world):
    login(client, "teacher1")
    ops.set_user_active(world["op"], user_id=world["t1"].id, active=False)
    assert client.get("/staff/").status_code == 302


def test_pwa_files_served_from_root(client):
    assert client.get("/manifest.webmanifest").status_code == 200
    r = client.get("/sw.js")
    assert r.status_code == 200 and r.headers["Service-Worker-Allowed"] == "/"
    assert client.get("/offline").status_code == 200
