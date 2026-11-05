"""Affective-development and psychomotor ratings (1-5).

AUTO ratings are suggested from the student's term average and stored, so a reprint never changes them.
They are deterministic (same student + term + trait always gives the same value), vary by at most
one step either way so a report does not look robotic, and are recomputed when scores change.
MANUAL ratings (typed by a person) are never overwritten."""
import hashlib
from app.extensions import db
from app.models import StudentTrait
from app.report_labels import TRAIT_KEYS

BANDS = [(75, 5), (65, 4), (50, 3), (40, 2)]   # average >= x  ->  rating (below 40 -> 1)


def base_rating(average) -> int:
    for floor, rating in BANDS:
        if average >= floor:
            return rating
    return 1


def _variation(enrollment_id: int, term_id: int, key: str) -> int:
    h = int(hashlib.sha256(f"{enrollment_id}:{term_id}:{key}".encode()).hexdigest(), 16) % 10
    return -1 if h < 2 else (1 if h >= 8 else 0)


def suggested(enrollment_id: int, term_id: int, key: str, average) -> int:
    return max(1, min(5, base_rating(average) + _variation(enrollment_id, term_id, key)))


def get_traits(enrollment_id: int, term_id: int) -> dict:
    rows = StudentTrait.query.filter_by(enrollment_id=enrollment_id, term_id=term_id).all()
    return {r.trait_key: r for r in rows}


def refresh_auto(enrollment_id: int, term_id: int, average) -> None:
    """Create/refresh AUTO ratings from the average. MANUAL rows are left alone. No-op without an average."""
    if average is None:
        return
    existing = get_traits(enrollment_id, term_id)
    for key in TRAIT_KEYS:
        row = existing.get(key)
        if row is not None and row.source == "MANUAL":
            continue
        value = suggested(enrollment_id, term_id, key, average)
        if row is None:
            db.session.add(StudentTrait(enrollment_id=enrollment_id, term_id=term_id,
                                        trait_key=key, rating=value, source="AUTO"))
        else:
            row.rating = value


def apply_manual(enrollment_id: int, term_id: int, ratings: dict) -> int:
    """ratings: {trait_key: '1'..'5' or ''}. A value only becomes MANUAL if the person actually changed it."""
    existing = get_traits(enrollment_id, term_id)
    changed = 0
    for key, raw in ratings.items():
        if key not in TRAIT_KEYS or str(raw).strip() == "":
            continue
        value = int(raw)
        if not 1 <= value <= 5:
            continue
        row = existing.get(key)
        if row is None:
            db.session.add(StudentTrait(enrollment_id=enrollment_id, term_id=term_id,
                                        trait_key=key, rating=value, source="MANUAL"))
            changed += 1
        elif row.rating != value or row.source == "MANUAL":
            if row.rating != value:
                changed += 1
            row.rating, row.source = value, "MANUAL"
    return changed
