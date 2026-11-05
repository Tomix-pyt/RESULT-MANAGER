from app.models import (StudentEnrollment, Student, User, AcademicSession, Term, Result, StaffAssignment,
                        ClassSession, ClassSubject)


def unenrolled_students() -> int:
    """Active students who are in no class for the current session (or in no class at all if none is current)."""
    cur = AcademicSession.query.filter_by(is_current=True).first()
    q = Student.query.filter(Student.status == "ACTIVE")
    if cur:
        enrolled = StudentEnrollment.query.filter_by(academic_session_id=cur.id).with_entities(StudentEnrollment.student_id)
    else:
        enrolled = StudentEnrollment.query.with_entities(StudentEnrollment.student_id)
    return q.filter(~Student.id.in_(enrolled)).count()


def operator_stats() -> dict:
    count = lambda status: Result.query.filter_by(status=status).count()
    return {
        "students": Student.query.filter_by(status="ACTIVE").count(),
        "unenrolled": unenrolled_students(),
        "staff": User.query.filter_by(role="STAFF", is_active=True).count(),
        "current_session": AcademicSession.query.filter_by(is_current=True).first(),
        "current_term": Term.query.filter_by(is_current=True).first(),
        "pending": count("SUBMITTED"),
        "approved": count("APPROVED"),
        "locked": count("LOCKED"),
        "drafts": count("DRAFT"),
    }


def staff_assignments(user: User, academic_session_id: int | None = None):
    """The class/subject pairs this staff member is allowed to work on."""
    q = (StaffAssignment.query.filter_by(staff_id=user.id)
         .join(ClassSubject).join(ClassSession))
    if academic_session_id is None:
        cur = AcademicSession.query.filter_by(is_current=True).first()
        academic_session_id = cur.id if cur else None
    if academic_session_id is not None:
        q = q.filter(StaffAssignment.academic_session_id == academic_session_id)
    return q.all()
