import pytest
from app import create_app
from app.extensions import db
from config import TestConfig


@pytest.fixture()
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()          # tests only; real databases use `flask db upgrade`
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def world(app):
    """A small school: 1 operator, 2 staff, JSS 1 + JSS 2, Maths + English, 2 students."""
    from app.services import auth_service as a, operator_service as ops
    op = a.create_user(username="admin", first_name="Ada", last_name="Min", password="password123", role="OPERATOR")
    t1 = a.create_user(username="teacher1", first_name="John", last_name="Doe", password="password123")
    t2 = a.create_user(username="teacher2", first_name="Mary", last_name="Roe", password="password123")
    ses = ops.create_academic_session(op, name="2026/2027", make_current=True)
    term = ops.create_term(op, academic_session_id=ses.id, name="First Term")
    ops.set_current_term(op, term_id=term.id)
    jss1 = ops.create_class(op, name="JSS 1")
    jss2 = ops.create_class(op, name="JSS 2")
    cs1 = ops.create_class_session(op, class_id=jss1.id, academic_session_id=ses.id)
    cs2 = ops.create_class_session(op, class_id=jss2.id, academic_session_id=ses.id)
    maths = ops.create_subject(op, code="math", name="Mathematics")
    eng = ops.create_subject(op, code="eng", name="English")
    m1 = ops.add_subject_to_class(op, class_session_id=cs1.id, subject_id=maths.id)
    e1 = ops.add_subject_to_class(op, class_session_id=cs1.id, subject_id=eng.id)
    m2 = ops.add_subject_to_class(op, class_session_id=cs2.id, subject_id=maths.id)
    ops.assign_staff(op, staff_id=t1.id, class_subject_id=m1.id)
    s1 = ops.add_student(op, admission_number="CSS/001", first_name="Jane", last_name="Smith")
    s2 = ops.add_student(op, admission_number="CSS/002", first_name="Ali", last_name="Musa")
    en1 = ops.enroll_student(op, student_id=s1.id, class_session_id=cs1.id)
    ops.enroll_student(op, student_id=s2.id, class_session_id=cs1.id)
    return dict(op=op, t1=t1, t2=t2, ses=ses, term=term, cs1=cs1, cs2=cs2, m1=m1, e1=e1, m2=m2,
                maths=maths, eng=eng, s1=s1, s2=s2, en1=en1)
