from datetime import date, datetime
from typing import Optional
from sqlalchemy.exc import IntegrityError
from app.extensions import db
from app.models import (
    StudentSubject,
    AcademicSession,
    Term,
    Class,
    ClassSession,
    Subject,
    ClassSubject,
    Student,
    StudentEnrollment,
    StaffAssignment,
    AssessmentComponent,
    GradingScale,
    GradeBoundary,
    User,
)
from app.errors import (
    DomainError,
    DuplicateError,
    ValidationError,
    NotFoundError,
)
from app.services.authorization_service import require_operator
from app.services import auth_service
from app.services.audit_log import log_action


# =====================================================================
# ACADEMIC SESSIONS
# =====================================================================

def create_academic_session(
    actor: User,
    *,
    name: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    make_current: bool = False,
) -> AcademicSession:
    require_operator(actor)

    if not name or not name.strip():
        raise ValidationError("Session name is required.")
    if AcademicSession.query.filter_by(name=name).first():
        raise DuplicateError(f"Session '{name}' already exists.")

    if make_current:
        AcademicSession.query.filter_by(is_current=True).update(
            {"is_current": False}
        )

    session = AcademicSession(
        name=name.strip(),
        start_date=start_date,
        end_date=end_date,
        is_current=make_current,          # ← FIX
    )
    db.session.add(session)
    db.session.flush()

    log_action(
        user_id=actor.id,
        action="CREATE_ACADEMIC_SESSION",
        entity_type="AcademicSession",
        entity_id=session.id,
        description=f"Created session {session.name}",
    )
    db.session.commit()
    return session


def update_academic_session(
    actor: User,
    *,
    session_id: int,
    name: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> AcademicSession:
    require_operator(actor)

    session = db.session.get(AcademicSession, session_id)
    if session is None:
        raise NotFoundError("Academic session not found.")

    if name is not None:
        name = name.strip()
        if not name:
            raise ValidationError("Session name cannot be empty.")
        clash = AcademicSession.query.filter(
            AcademicSession.name == name,
            AcademicSession.id != session_id,
        ).first()
        if clash:
            raise DuplicateError(f"Session '{name}' already exists.")
        session.name = name

    if start_date is not None:
        session.start_date = start_date
    if end_date is not None:
        session.end_date = end_date

    log_action(
        user_id=actor.id,
        action="UPDATE_ACADEMIC_SESSION",
        entity_type="AcademicSession",
        entity_id=session.id,
        description=f"Updated session {session.name}",
    )
    db.session.commit()
    return session


def set_current_session(actor: User, *, session_id: int) -> AcademicSession:
    require_operator(actor)

    session = db.session.get(AcademicSession, session_id)
    if session is None:
        raise NotFoundError("Academic session not found.")

    AcademicSession.query.filter_by(is_current=True).update(
        {"is_current": False}
    )
    session.is_current = True

    log_action(
        user_id=actor.id,
        action="SET_CURRENT_SESSION",
        entity_type="AcademicSession",
        entity_id=session.id,
        description=f"Set {session.name} as current session",
    )
    db.session.commit()
    return session


# =====================================================================
# TERMS
# =====================================================================

def create_term(
    actor: User,
    *,
    academic_session_id: int,
    name: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> Term:
    require_operator(actor)

    session = db.session.get(AcademicSession, academic_session_id)
    if session is None:
        raise NotFoundError("Academic session not found.")

    if not name or not name.strip():
        raise ValidationError("Term name is required.")

    if Term.query.filter_by(
        academic_session_id=academic_session_id, name=name.strip()
    ).first():
        raise DuplicateError(
            f"Term '{name}' already exists in session {session.name}."
        )

    term = Term(
        academic_session_id=academic_session_id,
        name=name.strip(),
        start_date=start_date,
        end_date=end_date,
    )
    db.session.add(term)
    db.session.flush()

    log_action(
        user_id=actor.id,
        action="CREATE_TERM",
        entity_type="Term",
        entity_id=term.id,
        description=f"Created term {term.name} in {session.name}",
    )
    db.session.commit()
    return term


def update_term(
    actor: User,
    *,
    term_id: int,
    name: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    edit_deadline=None,
    clear_deadline: bool = False,
    next_term_begins: Optional[date] = None,
) -> Term:
    require_operator(actor)

    term = db.session.get(Term, term_id)
    if term is None:
        raise NotFoundError("Term not found.")

    if name is not None:
        name = name.strip()
        if not name:
            raise ValidationError("Term name cannot be empty.")
        clash = Term.query.filter(
            Term.academic_session_id == term.academic_session_id,
            Term.name == name,
            Term.id != term_id,
        ).first()
        if clash:
            raise DuplicateError(
                f"Term '{name}' already exists in this session."
            )
        term.name = name

    if start_date is not None:
        term.start_date = start_date
    if end_date is not None:
        term.end_date = end_date
    if next_term_begins is not None:
        term.next_term_begins = next_term_begins
    if clear_deadline:
        term.edit_deadline = None
    elif edit_deadline is not None:
        term.edit_deadline = edit_deadline

    log_action(
        user_id=actor.id,
        action="UPDATE_TERM",
        entity_type="Term",
        entity_id=term.id,
        description=f"Updated term {term.name}",
    )
    db.session.commit()
    return term


def delete_term(actor: User, *, term_id: int) -> None:
    require_operator(actor)

    term = db.session.get(Term, term_id)
    if term is None:
        raise NotFoundError("Term not found.")

    if term.results or term.assessment_components:
        raise ValidationError(
            "Cannot delete a term that has assessments or results. "
            "Delete or archive those first."
        )

    db.session.delete(term)
    log_action(
        user_id=actor.id,
        action="DELETE_TERM",
        entity_type="Term",
        entity_id=term_id,
        description=f"Deleted term {term.name}",
    )
    db.session.commit()


# =====================================================================
# CLASSES
# =====================================================================

def create_class(
    actor: User,
    *,
    name: str,
    level: Optional[str] = None,
    arm: Optional[str] = None,
) -> Class:
    require_operator(actor)

    if not name or not name.strip():
        raise ValidationError("Class name is required.")

    if Class.query.filter_by(name=name.strip()).first():
        raise DuplicateError(f"Class '{name}' already exists.")

    class_ = Class(
        name=name.strip(),
        level=level,
        arm=arm,
        is_active=True,
    )
    db.session.add(class_)
    db.session.flush()

    log_action(
        user_id=actor.id,
        action="CREATE_CLASS",
        entity_type="Class",
        entity_id=class_.id,
        description=f"Created class {class_.name}",
    )
    db.session.commit()
    return class_


def update_class(
    actor: User,
    *,
    class_id: int,
    name: Optional[str] = None,
    level: Optional[str] = None,
    arm: Optional[str] = None,
) -> Class:
    require_operator(actor)

    class_ = db.session.get(Class, class_id)
    if class_ is None:
        raise NotFoundError("Class not found.")

    if name is not None:
        name = name.strip()
        if not name:
            raise ValidationError("Class name cannot be empty.")
        clash = Class.query.filter(
            Class.name == name, Class.id != class_id
        ).first()
        if clash:
            raise DuplicateError(f"Class '{name}' already exists.")
        class_.name = name

    if level is not None:
        class_.level = level
    if arm is not None:
        class_.arm = arm

    log_action(
        user_id=actor.id,
        action="UPDATE_CLASS",
        entity_type="Class",
        entity_id=class_.id,
        description=f"Updated class {class_.name}",
    )
    db.session.commit()
    return class_


def deactivate_class(actor: User, *, class_id: int) -> Class:
    """Soft delete — spec prefers is_active=False over physical deletion."""
    require_operator(actor)

    class_ = db.session.get(Class, class_id)
    if class_ is None:
        raise NotFoundError("Class not found.")

    class_.is_active = False
    log_action(
        user_id=actor.id,
        action="DEACTIVATE_CLASS",
        entity_type="Class",
        entity_id=class_.id,
        description=f"Deactivated class {class_.name}",
    )
    db.session.commit()
    return class_


# =====================================================================
# CLASS SESSIONS  ("JSS 1 in 2026/2027")
# =====================================================================

def create_class_session(
    actor: User,
    *,
    class_id: int,
    academic_session_id: int,
) -> ClassSession:
    require_operator(actor)

    if db.session.get(Class, class_id) is None:
        raise NotFoundError("Class not found.")
    if db.session.get(AcademicSession, academic_session_id) is None:
        raise NotFoundError("Academic session not found.")

    if ClassSession.query.filter_by(
        class_id=class_id, academic_session_id=academic_session_id
    ).first():
        raise DuplicateError(
            "This class already exists in this academic session."
        )

    cs = ClassSession(
        class_id=class_id,
        academic_session_id=academic_session_id,
    )
    db.session.add(cs)
    db.session.flush()

    log_action(
        user_id=actor.id,
        action="CREATE_CLASS_SESSION",
        entity_type="ClassSession",
        entity_id=cs.id,
        description=f"Created class session {cs.class_.name} for {cs.academic_session.name}",
    )
    db.session.commit()
    return cs


def delete_class_session(actor: User, *, class_session_id: int) -> None:
    require_operator(actor)

    cs = db.session.get(ClassSession, class_session_id)
    if cs is None:
        raise NotFoundError("Class session not found.")

    if cs.student_enrollments or cs.class_subjects:
        raise ValidationError(
            "Cannot delete a class session that has enrollments or subjects. "
            "Remove those first."
        )

    db.session.delete(cs)
    log_action(
        user_id=actor.id,
        action="DELETE_CLASS_SESSION",
        entity_type="ClassSession",
        entity_id=class_session_id,
        description="Deleted class session",
    )
    db.session.commit()


# =====================================================================
# SUBJECTS
# =====================================================================

def create_subject(
    actor: User,
    *,
    code: str,
    name: str,
    description: Optional[str] = None,
) -> Subject:
    require_operator(actor)

    if not code or not code.strip():
        raise ValidationError("Subject code is required.")
    if not name or not name.strip():
        raise ValidationError("Subject name is required.")

    code = code.strip().upper()
    if Subject.query.filter_by(code=code).first():
        raise DuplicateError(f"Subject code '{code}' already exists.")

    subject = Subject(
        code=code,
        name=name.strip(),
        description=description,
        is_active=True,
    )
    db.session.add(subject)
    db.session.flush()

    log_action(
        user_id=actor.id,
        action="CREATE_SUBJECT",
        entity_type="Subject",
        entity_id=subject.id,
        description=f"Created subject {subject.code} - {subject.name}",
    )
    db.session.commit()
    return subject


def update_subject(
    actor: User,
    *,
    subject_id: int,
    code: Optional[str] = None,
    name: Optional[str] = None,
    description: Optional[str] = None,
) -> Subject:
    require_operator(actor)

    subject = db.session.get(Subject, subject_id)
    if subject is None:
        raise NotFoundError("Subject not found.")

    if code is not None:
        code = code.strip().upper()
        if not code:
            raise ValidationError("Subject code cannot be empty.")
        clash = Subject.query.filter(
            Subject.code == code, Subject.id != subject_id
        ).first()
        if clash:
            raise DuplicateError(f"Subject code '{code}' already exists.")
        subject.code = code

    if name is not None:
        name = name.strip()
        if not name:
            raise ValidationError("Subject name cannot be empty.")
        subject.name = name

    if description is not None:
        subject.description = description

    log_action(
        user_id=actor.id,
        action="UPDATE_SUBJECT",
        entity_type="Subject",
        entity_id=subject.id,
        description=f"Updated subject {subject.code}",
    )
    db.session.commit()
    return subject


def deactivate_subject(actor: User, *, subject_id: int) -> Subject:
    require_operator(actor)

    subject = db.session.get(Subject, subject_id)
    if subject is None:
        raise NotFoundError("Subject not found.")

    subject.is_active = False
    log_action(
        user_id=actor.id,
        action="DEACTIVATE_SUBJECT",
        entity_type="Subject",
        entity_id=subject.id,
        description=f"Deactivated subject {subject.code}",
    )
    db.session.commit()
    return subject


# =====================================================================
# CLASS SUBJECTS  ("Math for JSS 1 in 2026/2027")
# =====================================================================

def add_subject_to_class(
    actor: User,
    *,
    class_session_id: int,
    subject_id: int,
) -> ClassSubject:
    require_operator(actor)

    cs = db.session.get(ClassSession, class_session_id)
    if cs is None:
        raise NotFoundError("Class session not found.")

    subject = db.session.get(Subject, subject_id)
    if subject is None:
        raise NotFoundError("Subject not found.")

    if ClassSubject.query.filter_by(
        class_session_id=class_session_id, subject_id=subject_id
    ).first():
        raise DuplicateError(
            f"{subject.name} is already assigned to {cs.class_.name}."
        )

    cs_subj = ClassSubject(
        class_session_id=class_session_id,
        subject_id=subject_id,
    )
    db.session.add(cs_subj)
    db.session.flush()

    for enr in cs.student_enrollments:
        db.session.add(StudentSubject(enrollment_id=enr.id, class_subject_id=cs_subj.id))

    log_action(
        user_id=actor.id,
        action="ADD_CLASS_SUBJECT",
        entity_type="ClassSubject",
        entity_id=cs_subj.id,
        description=(
            f"Assigned {subject.name} to {cs.class_.name} "
            f"({cs.academic_session.name})"
        ),
    )
    db.session.commit()
    return cs_subj


def remove_subject_from_class(
    actor: User, *, class_subject_id: int
) -> None:
    require_operator(actor)

    cs_subj = db.session.get(ClassSubject, class_subject_id)
    if cs_subj is None:
        raise NotFoundError("Class subject not found.")

    if cs_subj.assessment_components or cs_subj.results:
        raise ValidationError(
            "Cannot remove a class subject that has assessments or results."
        )

    StudentSubject.query.filter_by(class_subject_id=class_subject_id).delete()
    db.session.delete(cs_subj)
    log_action(
        user_id=actor.id,
        action="REMOVE_CLASS_SUBJECT",
        entity_type="ClassSubject",
        entity_id=class_subject_id,
        description="Removed subject from class",
    )
    db.session.commit()


# =====================================================================
# STUDENTS
# =====================================================================

def add_student(
    actor: User,
    *,
    admission_number: str,
    first_name: str,
    last_name: str,
    middle_name: Optional[str] = None,
    gender: Optional[str] = None,
    date_of_birth: Optional[date] = None,
) -> Student:
    require_operator(actor)

    if not admission_number or not admission_number.strip():
        raise ValidationError("Admission number is required.")   # ← FIX
    if not (first_name or "").strip() or not (last_name or "").strip():
        raise ValidationError("First name and last name are required.")

    admission_number = admission_number.strip()
    if Student.query.filter_by(admission_number=admission_number).first():
        raise DuplicateError(
            f"Admission number '{admission_number}' already exists."
        )

    student = Student(
        admission_number=admission_number,
        first_name=first_name.strip(),
        last_name=last_name.strip(),
        middle_name=middle_name,
        gender=gender,
        date_of_birth=date_of_birth,
        status="ACTIVE",
    )
    db.session.add(student)
    db.session.flush()

    log_action(
        user_id=actor.id,
        action="ADD_STUDENT",
        entity_type="Student",
        entity_id=student.id,
        description=(
            f"Added student {student.first_name} {student.last_name} "
            f"({student.admission_number})"
        ),
    )
    db.session.commit()
    return student


def update_student(
    actor: User,
    *,
    student_id: int,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    middle_name: Optional[str] = None,
    gender: Optional[str] = None,
    date_of_birth: Optional[date] = None,
) -> Student:
    require_operator(actor)

    student = db.session.get(Student, student_id)
    if student is None:
        raise NotFoundError("Student not found.")

    if first_name is not None:
        if not first_name.strip():
            raise ValidationError("First name cannot be empty.")
        student.first_name = first_name.strip()
    if last_name is not None:
        if not last_name.strip():
            raise ValidationError("Last name cannot be empty.")
        student.last_name = last_name.strip()
    if middle_name is not None:
        student.middle_name = middle_name
    if gender is not None:
        student.gender = gender
    if date_of_birth is not None:
        student.date_of_birth = date_of_birth

    log_action(
        user_id=actor.id,
        action="UPDATE_STUDENT",
        entity_type="Student",
        entity_id=student.id,
        description=f"Updated student {student.admission_number}",
    )
    db.session.commit()
    return student


def set_student_status(
    actor: User, *, student_id: int, status: str
) -> Student:
    """Soft-delete via status. Allowed: ACTIVE, INACTIVE, GRADUATED,
    TRANSFERRED, WITHDRAWN."""
    require_operator(actor)

    allowed = {"ACTIVE", "INACTIVE", "GRADUATED", "TRANSFERRED", "WITHDRAWN"}
    if status not in allowed:
        raise ValidationError(
            f"status must be one of: {', '.join(sorted(allowed))}."
        )

    student = db.session.get(Student, student_id)
    if student is None:
        raise NotFoundError("Student not found.")

    student.status = status
    log_action(
        user_id=actor.id,
        action="UPDATE_STUDENT_STATUS",
        entity_type="Student",
        entity_id=student.id,
        description=f"Set status of {student.admission_number} to {status}",
    )
    db.session.commit()
    return student


# =====================================================================
# STUDENT ENROLLMENTS
# =====================================================================

def ClassSession_subjects(class_session_id: int) -> list[ClassSubject]:
    return ClassSubject.query.filter_by(class_session_id=class_session_id).all()


def _ensure_not_enrolled_in_session(student_id: int, target: ClassSession) -> None:
    """Friendly pre-check. The database constraint is the real guarantee; this gives a clear message."""
    existing = (StudentEnrollment.query.join(ClassSession)
                .filter(StudentEnrollment.student_id == student_id,
                        ClassSession.academic_session_id == target.academic_session_id).first())
    if existing is None:
        return
    if existing.class_session_id == target.id:
        raise DuplicateError("Student is already enrolled in this class session.")
    raise ValidationError(
        f"This student is already in {existing.class_session.class_.name} for {target.academic_session.name}. "
        "Use Transfer to move them."
    )


def _write_enrollment(commit: bool) -> None:
    """flush/commit, turning a database 'one class per session' violation into a clear message."""
    try:
        db.session.commit() if commit else db.session.flush()
    except IntegrityError:
        db.session.rollback()
        raise ValidationError("This student is already enrolled in a class for this session "
                              "(someone may have just enrolled them). Refresh the page and check.")


def enroll_student(
    actor: User,
    *,
    student_id: int,
    class_session_id: int,
    roll_number: Optional[int] = None,
) -> StudentEnrollment:
    require_operator(actor)

    if db.session.get(Student, student_id) is None:
        raise NotFoundError("Student not found.")
    if db.session.get(ClassSession, class_session_id) is None:
        raise NotFoundError("Class session not found.")

    target = db.session.get(ClassSession, class_session_id)
    _ensure_not_enrolled_in_session(student_id, target)

    enrollment = StudentEnrollment(
        student_id=student_id,
        class_session_id=class_session_id,
        roll_number=roll_number,
    )
    db.session.add(enrollment)
    _write_enrollment(commit=False)

    # Infer the student's subjects from the class; operator can adjust afterwards.
    for cs_subj in ClassSession_subjects(class_session_id):
        db.session.add(StudentSubject(enrollment_id=enrollment.id, class_subject_id=cs_subj.id))

    log_action(
        user_id=actor.id,
        action="ENROLL_STUDENT",
        entity_type="StudentEnrollment",
        entity_id=enrollment.id,
        description=f"Enrolled student {student_id} into class session {class_session_id}",
    )
    _write_enrollment(commit=True)
    return enrollment


def update_enrollment(
    actor: User,
    *,
    enrollment_id: int,
    roll_number: Optional[int] = None,
) -> StudentEnrollment:
    require_operator(actor)

    enrollment = db.session.get(StudentEnrollment, enrollment_id)
    if enrollment is None:
        raise NotFoundError("Enrollment not found.")

    if roll_number is not None:
        enrollment.roll_number = roll_number

    log_action(
        user_id=actor.id,
        action="UPDATE_ENROLLMENT",
        entity_type="StudentEnrollment",
        entity_id=enrollment.id,
        description=f"Updated enrollment {enrollment.id}",
    )
    db.session.commit()
    return enrollment


def remove_enrollment(actor: User, *, enrollment_id: int) -> None:
    require_operator(actor)

    enrollment = db.session.get(StudentEnrollment, enrollment_id)
    if enrollment is None:
        raise NotFoundError("Enrollment not found.")

    db.session.delete(enrollment)
    log_action(
        user_id=actor.id,
        action="REMOVE_ENROLLMENT",
        entity_type="StudentEnrollment",
        entity_id=enrollment_id,
        description="Removed enrollment",
    )
    db.session.commit()


# =====================================================================
# STAFF ASSIGNMENTS
# =====================================================================

def assign_staff(
    actor: User,
    *,
    staff_id: int,
    class_subject_id: int,
) -> StaffAssignment:
    require_operator(actor)

    staff = db.session.get(User, staff_id)
    if staff is None:
        raise NotFoundError("Staff user not found.")
    if staff.role != "STAFF":
        raise ValidationError("Only users with role STAFF may be assigned.")

    cs_subj = db.session.get(ClassSubject, class_subject_id)
    if cs_subj is None:
        raise NotFoundError("Class subject not found.")

    academic_session_id = cs_subj.class_session.academic_session_id

    if StaffAssignment.query.filter_by(
        staff_id=staff_id,
        class_subject_id=class_subject_id,
        academic_session_id=academic_session_id,
    ).first():
        raise DuplicateError(
            "This staff member is already assigned to that class subject."
        )

    assignment = StaffAssignment(
        staff_id=staff_id,
        class_subject_id=class_subject_id,
        academic_session_id=academic_session_id,
    )
    db.session.add(assignment)
    db.session.flush()

    log_action(
        user_id=actor.id,
        action="ASSIGN_STAFF",
        entity_type="StaffAssignment",
        entity_id=assignment.id,
        description=(
            f"Assigned {staff.username} to class subject {class_subject_id}"
        ),
    )
    db.session.commit()
    return assignment


def remove_staff_assignment(
    actor: User, *, assignment_id: int
) -> None:
    require_operator(actor)

    assignment = db.session.get(StaffAssignment, assignment_id)
    if assignment is None:
        raise NotFoundError("Staff assignment not found.")

    db.session.delete(assignment)
    log_action(
        user_id=actor.id,
        action="REMOVE_STAFF_ASSIGNMENT",
        entity_type="StaffAssignment",
        entity_id=assignment_id,
        description="Removed staff assignment",
    )
    db.session.commit()


# =====================================================================
# ASSESSMENT COMPONENTS
# =====================================================================

def create_assessment_component(
    actor: User,
    *,
    class_subject_id: int,
    term_id: int,
    name: str,
    code: Optional[str] = None,
    max_score: int,
    weight: int,
    position: Optional[int] = None,
    report_slot: Optional[int] = None,
) -> AssessmentComponent:
    require_operator(actor)

    cs_subj = db.session.get(ClassSubject, class_subject_id)
    if cs_subj is None:
        raise NotFoundError("Class subject not found.")

    term = db.session.get(Term, term_id)
    if term is None:
        raise NotFoundError("Term not found.")

    if term.academic_session_id != cs_subj.class_session.academic_session_id:
        raise ValidationError(
            "Term and class subject belong to different academic sessions."
        )

    if not name or not name.strip():
        raise ValidationError("Assessment name is required.")
    if max_score <= 0:
        raise ValidationError("max_score must be greater than zero.")
    if weight <= 0:
        raise ValidationError("weight must be greater than zero.")

    if AssessmentComponent.query.filter_by(
        class_subject_id=class_subject_id,
        term_id=term_id,
        name=name.strip(),
    ).first():
        raise DuplicateError(
            f"Assessment '{name}' already exists for this class subject in this term."
        )

    used = {c.report_slot for c in AssessmentComponent.query.filter_by(
        class_subject_id=class_subject_id, term_id=term_id) if c.report_slot}
    if report_slot is None:
        free = [i for i in (1, 2, 3, 4) if i not in used]
        if not free:
            raise ValidationError("A subject can have at most 4 assessments per term "
                                  "(1'st CA, 2'nd CA, 3'rd CA and Exams).")
        report_slot = free[0]
    elif report_slot not in (1, 2, 3, 4):
        raise ValidationError("Choose a printed column: 1'st CA, 2'nd CA, 3'rd CA or Exams.")
    elif report_slot in used:
        raise DuplicateError("Another assessment already fills that column for this subject and term.")

    comp = AssessmentComponent(
        class_subject_id=class_subject_id,
        term_id=term_id,
        name=name.strip(),
        max_score=max_score,
        weight=weight,
        position=position if position is not None else report_slot,
        report_slot=report_slot,
        code=code,
    )
    db.session.add(comp)
    db.session.flush()

    log_action(
        user_id=actor.id,
        action="CREATE_ASSESSMENT",
        entity_type="AssessmentComponent",
        entity_id=comp.id,
        description=f"Created assessment {comp.name} (max {max_score})",
    )
    db.session.commit()
    return comp


def update_assessment_component(
    actor: User,
    *,
    component_id: int,
    name: Optional[str] = None,
    code: Optional[str] = None,
    max_score: Optional[int] = None,
    weight: Optional[int] = None,
    position: Optional[int] = None,
    report_slot: Optional[int] = None,
) -> AssessmentComponent:
    require_operator(actor)

    comp = db.session.get(AssessmentComponent, component_id)
    if comp is None:
        raise NotFoundError("Assessment component not found.")

    if comp.scores:
        # Once scores exist, prevent changing max_score to a smaller value.
        if max_score is not None and max_score < comp.max_score:
            raise ValidationError(
                "Cannot reduce max_score after scores have been entered."
            )

    if report_slot is not None and report_slot != comp.report_slot:
        if report_slot not in (1, 2, 3, 4):
            raise ValidationError("Choose a printed column: 1'st CA, 2'nd CA, 3'rd CA or Exams.")
        if AssessmentComponent.query.filter(
                AssessmentComponent.class_subject_id == comp.class_subject_id,
                AssessmentComponent.term_id == comp.term_id,
                AssessmentComponent.report_slot == report_slot,
                AssessmentComponent.id != component_id).first():
            raise DuplicateError("Another assessment already fills that column for this subject and term.")
        comp.report_slot = report_slot

    if name is not None:
        name = name.strip()
        if not name:
            raise ValidationError("Assessment name cannot be empty.")
        clash = AssessmentComponent.query.filter(
            AssessmentComponent.class_subject_id == comp.class_subject_id,
            AssessmentComponent.term_id == comp.term_id,
            AssessmentComponent.name == name,
            AssessmentComponent.id != component_id,
        ).first()
        if clash:
            raise DuplicateError(f"Assessment '{name}' already exists here.")
        comp.name = name

    if code is not None:
        code = code.strip()
        if not code:
            raise ValidationError("Assessment code cannot be empty.")
        clash = AssessmentComponent.query.filter(
            AssessmentComponent.class_subject_id == comp.class_subject_id,
            AssessmentComponent.term_id == comp.term_id,
            AssessmentComponent.code == code,
            AssessmentComponent.id != component_id,
        ).first()
        if clash:
            raise DuplicateError(f"Assessment '{code}' already exists here.")
        comp.code = code

    if max_score is not None:
        if max_score <= 0:
            raise ValidationError("max_score must be greater than zero.")
        comp.max_score = max_score

    if weight is not None:
        if weight <= 0:
            raise ValidationError("weight must be greater than zero.")
        comp.weight = weight

    if position is not None:
        comp.position = position

    log_action(
        user_id=actor.id,
        action="UPDATE_ASSESSMENT",
        entity_type="AssessmentComponent",
        entity_id=comp.id,
        description=f"Updated assessment {comp.name}",
    )
    db.session.commit()
    return comp


def delete_assessment_component(
    actor: User, *, component_id: int
) -> None:
    require_operator(actor)

    comp = db.session.get(AssessmentComponent, component_id)
    if comp is None:
        raise NotFoundError("Assessment component not found.")

    if comp.scores:
        raise ValidationError(
            "Cannot delete an assessment that already has scores. "
            "Remove the scores first."
        )

    db.session.delete(comp)
    log_action(
        user_id=actor.id,
        action="DELETE_ASSESSMENT",
        entity_type="AssessmentComponent",
        entity_id=component_id,
        description=f"Deleted assessment {comp.name}",
    )
    db.session.commit()


# =====================================================================
# GRADING SCALES
# =====================================================================

def create_grading_scale(
    actor: User,
    *,
    name: str,
    academic_session_id: int,
) -> GradingScale:
    require_operator(actor)

    if db.session.get(AcademicSession, academic_session_id) is None:
        raise NotFoundError("Academic session not found.")

    existing_scale = GradingScale.query.filter_by(academic_session_id=academic_session_id).first()
    if existing_scale is not None:
        raise ValidationError(
            f"{existing_scale.academic_session.name} already has a grading scale. "
            "Edit the existing scale instead of creating another one."
        )

    if not name or not name.strip():
        raise ValidationError("Grading scale name is required.")

    scale = GradingScale(
        name=name.strip(),
        academic_session_id=academic_session_id,
    )
    db.session.add(scale)
    db.session.flush()

    log_action(
        user_id=actor.id,
        action="CREATE_GRADING_SCALE",
        entity_type="GradingScale",
        entity_id=scale.id,
        description=f"Created grading scale {scale.name}",
    )
    db.session.commit()
    return scale


def add_grade_boundary(
    actor: User,
    *,
    grading_scale_id: int,
    min_score: float,
    max_score: float,
    grade: str,
    remark: Optional[str] = None,
) -> GradeBoundary:
    require_operator(actor)

    scale = db.session.get(GradingScale, grading_scale_id)
    if scale is None:
        raise NotFoundError("Grading scale not found.")

    if min_score < 0 or max_score > 100:
        raise ValidationError("Scores must be between 0 and 100.")
    if min_score > max_score:
        raise ValidationError("min_score cannot be greater than max_score.")
    if not grade or not grade.strip():
        raise ValidationError("Grade is required.")

    # Prevent overlapping ranges
    overlap = GradeBoundary.query.filter(
        GradeBoundary.grading_scale_id == grading_scale_id,
        GradeBoundary.min_score <= max_score,
        GradeBoundary.max_score >= min_score,
    ).first()
    if overlap:
        raise DuplicateError(
            f"Range {min_score}-{max_score} overlaps existing "
            f"boundary {overlap.min_score}-{overlap.max_score}."
        )

    boundary = GradeBoundary(
        grading_scale_id=grading_scale_id,
        min_score=min_score,
        max_score=max_score,
        grade=grade.strip(),
        remark=remark,
    )
    db.session.add(boundary)
    db.session.flush()

    log_action(
        user_id=actor.id,
        action="ADD_GRADE_BOUNDARY",
        entity_type="GradeBoundary",
        entity_id=boundary.id,
        description=f"Added boundary {min_score}-{max_score} => {grade}",
    )
    db.session.commit()
    return boundary


def update_grade_boundary(
    actor: User,
    *,
    boundary_id: int,
    min_score: Optional[float] = None,
    max_score: Optional[float] = None,
    grade: Optional[str] = None,
    remark: Optional[str] = None,
) -> GradeBoundary:
    require_operator(actor)

    boundary = db.session.get(GradeBoundary, boundary_id)
    if boundary is None:
        raise NotFoundError("Grade boundary not found.")

    new_min = min_score if min_score is not None else boundary.min_score
    new_max = max_score if max_score is not None else boundary.max_score

    if new_min < 0 or new_max > 100:
        raise ValidationError("Scores must be between 0 and 100.")
    if new_min > new_max:
        raise ValidationError("min_score cannot be greater than max_score.")

    overlap = GradeBoundary.query.filter(
        GradeBoundary.grading_scale_id == boundary.grading_scale_id,
        GradeBoundary.id != boundary_id,
        GradeBoundary.min_score <= new_max,
        GradeBoundary.max_score >= new_min,
    ).first()
    if overlap:
        raise DuplicateError(
            f"Range {new_min}-{new_max} overlaps existing boundary."
        )

    boundary.min_score = new_min
    boundary.max_score = new_max
    if grade is not None:
        boundary.grade = grade.strip()
    if remark is not None:
        boundary.remark = remark

    log_action(
        user_id=actor.id,
        action="UPDATE_GRADE_BOUNDARY",
        entity_type="GradeBoundary",
        entity_id=boundary.id,
        description=f"Updated boundary {new_min}-{new_max}",
    )
    db.session.commit()
    return boundary


def delete_grade_boundary(actor: User, *, boundary_id: int) -> None:
    require_operator(actor)

    boundary = db.session.get(GradeBoundary, boundary_id)
    if boundary is None:
        raise NotFoundError("Grade boundary not found.")

    db.session.delete(boundary)
    log_action(
        user_id=actor.id,
        action="DELETE_GRADE_BOUNDARY",
        entity_type="GradeBoundary",
        entity_id=boundary_id,
        description="Deleted grade boundary",
    )
    db.session.commit()

# =====================================================================
# PER-STUDENT SUBJECTS  (operator adds/removes a subject for one student)
# =====================================================================

def add_student_subject(actor: User, *, enrollment_id: int, class_subject_id: int) -> StudentSubject:
    require_operator(actor)
    enr = db.session.get(StudentEnrollment, enrollment_id)
    cs_subj = db.session.get(ClassSubject, class_subject_id)
    if enr is None or cs_subj is None:
        raise NotFoundError("Enrollment or class subject not found.")
    if cs_subj.class_session_id != enr.class_session_id:
        raise ValidationError("That subject is not offered in this student's class.")
    if StudentSubject.query.filter_by(enrollment_id=enrollment_id, class_subject_id=class_subject_id).first():
        raise DuplicateError("The student already takes this subject.")
    row = StudentSubject(enrollment_id=enrollment_id, class_subject_id=class_subject_id)
    db.session.add(row)
    db.session.flush()
    log_action(actor.id, "ADD_STUDENT_SUBJECT", "StudentSubject", row.id,
               f"Added class subject {class_subject_id} to enrollment {enrollment_id}")
    db.session.commit()
    return row


def remove_student_subject(actor: User, *, enrollment_id: int, class_subject_id: int) -> None:
    require_operator(actor)
    row = StudentSubject.query.filter_by(enrollment_id=enrollment_id, class_subject_id=class_subject_id).first()
    if row is None:
        raise NotFoundError("The student does not take this subject.")
    enr = row.enrollment
    from app.models import Result, Score, AssessmentComponent
    has_result = Result.query.filter_by(student_id=enr.student_id, class_subject_id=class_subject_id).first()
    has_score = (Score.query.join(AssessmentComponent)
                 .filter(Score.student_id == enr.student_id,
                         AssessmentComponent.class_subject_id == class_subject_id).first())
    if has_result or has_score:
        raise ValidationError("Cannot remove a subject that already has scores or results for this student.")
    db.session.delete(row)
    log_action(actor.id, "REMOVE_STUDENT_SUBJECT", "StudentSubject", row.id,
               f"Removed class subject {class_subject_id} from enrollment {enrollment_id}")
    db.session.commit()


# =====================================================================
# CURRENT TERM
# =====================================================================

def set_current_term(actor: User, *, term_id: int) -> Term:
    require_operator(actor)
    term = db.session.get(Term, term_id)
    if term is None:
        raise NotFoundError("Term not found.")
    Term.query.filter_by(is_current=True).update({"is_current": False})
    term.is_current = True
    # keep the session pointer in step with the term
    AcademicSession.query.filter_by(is_current=True).update({"is_current": False})
    term.academic_session.is_current = True
    log_action(actor.id, "SET_CURRENT_TERM", "Term", term.id,
               f"Set {term.name} ({term.academic_session.name}) as current term")
    db.session.commit()
    return term


# =====================================================================
# USER ACCOUNTS
# =====================================================================

def create_user_account(actor: User, *, username, first_name, last_name, password,
                        role="STAFF", email=None) -> User:
    require_operator(actor)
    user = auth_service.create_user(username=username, first_name=first_name, last_name=last_name,
                                    password=password, role=role, email=email)
    log_action(actor.id, "CREATE_USER", "User", user.id, f"Created {role} account {user.username}")
    db.session.commit()
    return user


def set_user_active(actor: User, *, user_id: int, active: bool) -> User:
    require_operator(actor)
    user = db.session.get(User, user_id)
    if user is None:
        raise NotFoundError("User not found.")
    if user.id == actor.id and not active:
        raise ValidationError("You cannot deactivate your own account.")
    if (not active and user.role == "OPERATOR"
            and User.query.filter_by(role="OPERATOR", is_active=True).count() <= 1):
        raise ValidationError("There must always be at least one active operator.")
    user.is_active = active
    log_action(actor.id, "ACTIVATE_USER" if active else "DEACTIVATE_USER", "User", user.id,
               f"{'Activated' if active else 'Deactivated'} {user.username}")
    db.session.commit()
    return user


def reset_user_password(actor: User, *, user_id: int, new_password: str) -> User:
    require_operator(actor)
    from werkzeug.security import generate_password_hash
    auth_service._validate_password(new_password)
    user = db.session.get(User, user_id)
    if user is None:
        raise NotFoundError("User not found.")
    user.password_hash = generate_password_hash(new_password)
    log_action(actor.id, "RESET_PASSWORD", "User", user.id, f"Reset password for {user.username}")
    db.session.commit()
    return user


# =====================================================================
# MORE EDIT / REACTIVATE / DELETE
# =====================================================================

def reactivate_class(actor: User, *, class_id: int) -> Class:
    require_operator(actor)
    c = db.session.get(Class, class_id)
    if c is None:
        raise NotFoundError("Class not found.")
    c.is_active = True
    log_action(actor.id, "REACTIVATE_CLASS", "Class", c.id, f"Reactivated class {c.name}")
    db.session.commit()
    return c


def reactivate_subject(actor: User, *, subject_id: int) -> Subject:
    require_operator(actor)
    s_ = db.session.get(Subject, subject_id)
    if s_ is None:
        raise NotFoundError("Subject not found.")
    s_.is_active = True
    log_action(actor.id, "REACTIVATE_SUBJECT", "Subject", s_.id, f"Reactivated subject {s_.code}")
    db.session.commit()
    return s_


def delete_academic_session(actor: User, *, session_id: int) -> None:
    require_operator(actor)
    ses = db.session.get(AcademicSession, session_id)
    if ses is None:
        raise NotFoundError("Academic session not found.")
    if ses.class_sessions or ses.staff_assignments or ses.grading_scales:
        raise ValidationError("This session already has classes, assignments or grading scales. It cannot be deleted.")
    if any(t.results or t.assessment_components for t in ses.terms):
        raise ValidationError("This session has assessments or results. It cannot be deleted.")
    name = ses.name
    db.session.delete(ses)
    log_action(actor.id, "DELETE_ACADEMIC_SESSION", "AcademicSession", session_id, f"Deleted session {name}")
    db.session.commit()


def update_user_account(actor: User, *, user_id: int, first_name=None, last_name=None, email=None, role=None) -> User:
    require_operator(actor)
    user = db.session.get(User, user_id)
    if user is None:
        raise NotFoundError("User not found.")
    if first_name is not None:
        if not first_name.strip():
            raise ValidationError("First name cannot be empty.")
        user.first_name = first_name.strip()
    if last_name is not None:
        if not last_name.strip():
            raise ValidationError("Last name cannot be empty.")
        user.last_name = last_name.strip()
    if email is not None:
        email = email.strip().lower() or None
        if email and User.query.filter(User.email == email, User.id != user_id).first():
            raise DuplicateError("That email is already in use.")
        user.email = email
    if role is not None and role != user.role:
        if role not in ("OPERATOR", "STAFF"):
            raise ValidationError("Role must be OPERATOR or STAFF.")
        if user.id == actor.id:
            raise ValidationError("You cannot change your own role.")
        if role == "STAFF" and user.staff_assignments:
            pass  # staff keep assignments; operators ignore them
        user.role = role
    log_action(actor.id, "UPDATE_USER", "User", user.id, f"Updated account {user.username}")
    db.session.commit()
    return user


def update_grading_scale(actor: User, *, scale_id: int, name: str) -> GradingScale:
    require_operator(actor)
    sc = db.session.get(GradingScale, scale_id)
    if sc is None:
        raise NotFoundError("Grading scale not found.")
    if not name or not name.strip():
        raise ValidationError("Grading scale name is required.")
    sc.name = name.strip()
    log_action(actor.id, "UPDATE_GRADING_SCALE", "GradingScale", sc.id, f"Renamed scale to {sc.name}")
    db.session.commit()
    return sc


def delete_grading_scale(actor: User, *, scale_id: int) -> None:
    require_operator(actor)
    sc = db.session.get(GradingScale, scale_id)
    if sc is None:
        raise NotFoundError("Grading scale not found.")
    name = sc.name
    db.session.delete(sc)
    log_action(actor.id, "DELETE_GRADING_SCALE", "GradingScale", scale_id, f"Deleted scale {name}")
    db.session.commit()


def copy_class_setup(actor: User, *, from_class_session_id: int, to_class_session_id: int,
                     include_staff: bool = True) -> dict:
    """Copy subjects (and optionally teacher assignments) from one class session to another,
    e.g. from last year's JSS 1 to this year's JSS 1. Existing rows are left alone."""
    require_operator(actor)
    src = db.session.get(ClassSession, from_class_session_id)
    dst = db.session.get(ClassSession, to_class_session_id)
    if src is None or dst is None:
        raise NotFoundError("Class session not found.")
    if src.id == dst.id:
        raise ValidationError("Choose a different class to copy from.")
    subjects = staff = 0
    for old in list(src.class_subjects):
        new = ClassSubject.query.filter_by(class_session_id=dst.id, subject_id=old.subject_id).first()
        if new is None:
            if not old.subject.is_active:
                continue
            new = add_subject_to_class(actor, class_session_id=dst.id, subject_id=old.subject_id)
            subjects += 1
        if include_staff:
            for a in list(old.staff_assignments):
                if a.staff.is_active and a.staff.role == "STAFF":
                    try:
                        assign_staff(actor, staff_id=a.staff_id, class_subject_id=new.id)
                        staff += 1
                    except DuplicateError:
                        pass
    return {"subjects": subjects, "staff": staff}


# =====================================================================
# ENROLLMENT TOOLS
# =====================================================================

def bulk_enroll(actor: User, *, student_ids: list[int], class_session_id: int) -> dict:
    require_operator(actor)
    if db.session.get(ClassSession, class_session_id) is None:
        raise NotFoundError("Class session not found.")
    enrolled, problems = 0, []
    for sid in student_ids:
        try:
            enroll_student(actor, student_id=sid, class_session_id=class_session_id)
            enrolled += 1
        except (DuplicateError, ValidationError, NotFoundError) as e:
            st = db.session.get(Student, sid)
            problems.append(f"{st.full_name if st else sid}: {e}")
    return {"enrolled": enrolled, "problems": problems}


def assign_roll_numbers(actor: User, *, class_session_id: int) -> int:
    """Number the class 1..n alphabetically by surname."""
    require_operator(actor)
    rows = (StudentEnrollment.query.filter_by(class_session_id=class_session_id).join(Student)
            .order_by(Student.last_name, Student.first_name, Student.id).all())
    for i, enr in enumerate(rows, start=1):
        enr.roll_number = i
    log_action(actor.id, "ASSIGN_ROLL_NUMBERS", "ClassSession", class_session_id, f"Numbered {len(rows)} students")
    db.session.commit()
    return len(rows)


def transfer_student(actor: User, *, enrollment_id: int, to_class_session_id: int) -> StudentEnrollment:
    """Move a student to another class in the SAME academic session (e.g. JSS 1 A -> JSS 1 B)."""
    require_operator(actor)
    from app.models import Result, Score
    enr = db.session.get(StudentEnrollment, enrollment_id)
    target = db.session.get(ClassSession, to_class_session_id)
    if enr is None or target is None:
        raise NotFoundError("Enrollment or class not found.")
    if target.id == enr.class_session_id:
        raise ValidationError("The student is already in that class.")
    if target.academic_session_id != enr.class_session.academic_session_id:
        raise ValidationError("Transfers stay within one session. Use Promote to move a student to a new session.")
    old_ids = [cs.id for cs in enr.class_session.class_subjects]
    has_scores = (Score.query.join(Score.assessment_component)
                  .filter(Score.student_id == enr.student_id, AssessmentComponent.class_subject_id.in_(old_ids)).first()
                  if old_ids else None)
    has_results = Result.query.filter(Result.student_id == enr.student_id,
                                      Result.class_subject_id.in_(old_ids)).first() if old_ids else None
    if has_scores or has_results:
        raise ValidationError("This student already has scores or results in the current class, so they cannot be transferred.")
    old_name, new_name = enr.class_session.class_.name, target.class_.name
    for row in list(enr.subjects):
        db.session.delete(row)
    enr.class_session_id = target.id
    enr.roll_number = None
    db.session.flush()
    for cs_subj in target.class_subjects:
        db.session.add(StudentSubject(enrollment_id=enr.id, class_subject_id=cs_subj.id))
    log_action(actor.id, "TRANSFER_STUDENT", "StudentEnrollment", enr.id,
               f"Transferred student {enr.student_id} from {old_name} to {new_name}")
    db.session.commit()
    return enr


def promote_students(actor: User, *, student_ids: list[int], to_class_session_id: int) -> dict:
    """Enrol students into a class in a new session. Their old enrollments stay as history."""
    res = bulk_enroll(actor, student_ids=student_ids, class_session_id=to_class_session_id)
    log_action(actor.id, "PROMOTE_STUDENTS", "ClassSession", to_class_session_id, f"Promoted {res['enrolled']} students")
    db.session.commit()
    return res


def graduate_students(actor: User, *, student_ids: list[int]) -> int:
    require_operator(actor)
    n = 0
    for sid in student_ids:
        st = db.session.get(Student, sid)
        if st and st.status != "GRADUATED":
            st.status = "GRADUATED"
            log_action(actor.id, "UPDATE_STUDENT_STATUS", "Student", st.id, f"Set status of {st.admission_number} to GRADUATED")
            n += 1
    db.session.commit()
    return n


def _parse_dob(text: str):
    text = (text or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    raise ValidationError(f"Unrecognised date '{text}' (use YYYY-MM-DD or DD/MM/YYYY).")


def import_students_csv(actor: User, *, text: str, class_session_id: Optional[int] = None) -> dict:
    """Columns: admission_number, first_name, last_name, middle_name (opt), gender (opt), date_of_birth (opt)."""
    require_operator(actor)
    import csv, io
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        raise ValidationError("The file has no rows.")
    if len(rows) > 1000:
        raise ValidationError("Import at most 1000 students at a time.")
    fields = {(k or "").strip().lower() for k in rows[0].keys()}
    missing = {"admission_number", "first_name", "last_name"} - fields
    if missing:
        raise ValidationError("Missing column(s): " + ", ".join(sorted(missing)))
    created, enrolled, problems = 0, 0, []
    for n, raw in enumerate(rows, start=2):
        r = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
        try:
            st = add_student(actor, admission_number=r.get("admission_number", ""), first_name=r.get("first_name", ""),
                             last_name=r.get("last_name", ""), middle_name=r.get("middle_name") or None,
                             gender=(r.get("gender") or "").capitalize() or None,
                             date_of_birth=_parse_dob(r.get("date_of_birth", "")))
            created += 1
            if class_session_id:
                enroll_student(actor, student_id=st.id, class_session_id=class_session_id)
                enrolled += 1
        except DomainError as e:
            db.session.rollback()
            problems.append(f"Line {n} ({r.get('admission_number') or '?'}): {e}")
    return {"created": created, "enrolled": enrolled, "problems": problems}


def set_form_teacher(actor: User, *, class_session_id: int, staff_id: Optional[int]) -> ClassSession:
    """The form teacher's name is printed on that class's results."""
    require_operator(actor)
    cs = db.session.get(ClassSession, class_session_id)
    if cs is None:
        raise NotFoundError("Class not found.")
    if staff_id is not None:
        t = db.session.get(User, staff_id)
        if t is None or not t.is_active:
            raise NotFoundError("Teacher not found.")
    cs.form_teacher_id = staff_id
    log_action(actor.id, "SET_FORM_TEACHER", "ClassSession", cs.id,
               f"Form teacher of {cs.class_.name} set to {t.full_name if staff_id else 'nobody'}")
    db.session.commit()
    return cs
