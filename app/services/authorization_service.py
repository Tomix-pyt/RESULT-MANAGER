"""All permission decisions live here. Routes call these; they never decide for themselves."""
from datetime import datetime
from app.models import User, StaffAssignment, ClassSubject, Score, Result
from app.errors import PermissionDenied

EDITABLE_BY_STAFF = {"DRAFT", "REJECTED", "REOPENED"}
NOT_EDITABLE_BY_OPERATOR = {"LOCKED", "PUBLISHED"}


def is_operator(user: User | None) -> bool:
    return bool(user and user.role == "OPERATOR" and user.is_active)


def require_operator(user: User | None) -> None:
    if not is_operator(user):
        raise PermissionDenied("Operator privileges are required to perform this action.")


def staff_has_class_subject(user: User, class_subject_id: int) -> bool:
    return StaffAssignment.query.filter_by(staff_id=user.id, class_subject_id=class_subject_id).first() is not None


def require_staff_assignment(user: User, class_subject_id: int) -> None:
    if is_operator(user):
        return
    if not (user and user.is_active and staff_has_class_subject(user, class_subject_id)):
        raise PermissionDenied("You are not assigned to this class/subject.")


LOCKED_STATES = ("LOCKED", "PUBLISHED")


def subject_term_locked(class_subject_id: int, term_id: int) -> bool:
    """A subject is locked for a term as soon as any of its results is LOCKED/PUBLISHED."""
    return Result.query.filter(Result.class_subject_id == class_subject_id, Result.term_id == term_id,
                               Result.status.in_(LOCKED_STATES)).first() is not None


def staff_deadline_passed(term) -> bool:
    return bool(term is not None and term.edit_deadline is not None and datetime.now() > term.edit_deadline)


def _result_for(score: Score) -> Result | None:
    comp = score.assessment_component
    return Result.query.filter_by(student_id=score.student_id, class_subject_id=comp.class_subject_id,
                                  term_id=comp.term_id).first()


def can_edit_score(user: User, score: Score) -> bool:
    result = _result_for(score)
    status = result.status if result else "DRAFT"
    if is_operator(user):
        return status not in NOT_EDITABLE_BY_OPERATOR
    if not (user and user.is_active):
        return False
    if not staff_has_class_subject(user, score.assessment_component.class_subject_id):
        return False
    if staff_deadline_passed(score.assessment_component.term):      # grace period over
        return False
    return status in EDITABLE_BY_STAFF


def require_can_edit_score(user: User, score: Score) -> None:
    if not can_edit_score(user, score):
        raise PermissionDenied("This score cannot be edited: you are not assigned to this subject, or the result is locked/submitted.")
