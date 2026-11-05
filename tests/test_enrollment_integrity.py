"""One class per student per session, enforced by the DATABASE, not just by Python checks."""
import pytest
from sqlalchemy.exc import IntegrityError
from app.extensions import db
from app.errors import ValidationError
from app.models import StudentEnrollment
from app.services import operator_service as ops


def test_database_itself_rejects_second_class_in_same_session(world):
    """Bypasses every service check: raw ORM rows, as a race or a bug would."""
    s3 = ops.add_student(world["op"], admission_number="CSS/777", first_name="Race", last_name="Condition")
    db.session.add(StudentEnrollment(student_id=s3.id, class_session_id=world["cs1"].id))
    db.session.add(StudentEnrollment(student_id=s3.id, class_session_id=world["cs2"].id))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_session_column_is_filled_automatically_and_stays_correct(world):
    en = world["en1"]
    assert en.academic_session_id == world["cs1"].academic_session_id
    ops.transfer_student(world["op"], enrollment_id=en.id, to_class_session_id=world["cs2"].id)
    db.session.refresh(en)
    assert en.class_session_id == world["cs2"].id
    assert en.academic_session_id == world["cs2"].academic_session_id


def test_race_between_check_and_insert_gives_friendly_error_not_crash(world, monkeypatch):
    """If two requests slip past the Python check at the same moment, the second must get a
    clear message and the session must stay usable."""
    monkeypatch.setattr(ops, "_ensure_not_enrolled_in_session", lambda *a, **k: None)
    with pytest.raises(ValidationError, match="already enrolled"):
        ops.enroll_student(world["op"], student_id=world["s1"].id, class_session_id=world["cs2"].id)
    assert StudentEnrollment.query.filter_by(student_id=world["s1"].id).count() == 1
    ops.add_student(world["op"], admission_number="CSS/888", first_name="Still", last_name="Works")  # session healthy


def test_same_student_can_be_enrolled_in_a_different_session(world):
    ses2 = ops.create_academic_session(world["op"], name="2027/2028")
    cs_next = ops.create_class_session(world["op"], class_id=1, academic_session_id=ses2.id)
    ops.enroll_student(world["op"], student_id=world["s1"].id, class_session_id=cs_next.id)   # promotion case
    assert StudentEnrollment.query.filter_by(student_id=world["s1"].id).count() == 2


def test_bulk_and_csv_report_instead_of_double_enrolling(world):
    r = ops.bulk_enroll(world["op"], student_ids=[world["s1"].id], class_session_id=world["cs2"].id)
    assert r["enrolled"] == 0 and "already in" in r["problems"][0]
    r = ops.import_students_csv(world["op"], text="admission_number,first_name,last_name\nCSS/001,Jane,Smith\n",
                                class_session_id=world["cs2"].id)
    assert r["enrolled"] == 0
    assert StudentEnrollment.query.filter_by(student_id=world["s1"].id).count() == 1
