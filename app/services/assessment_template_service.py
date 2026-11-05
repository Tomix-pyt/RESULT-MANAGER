"""School-wide assessment structure shared by every subject, class and term.

AssessmentComponent remains a term/class-subject snapshot because scores and results
refer to those rows. This service projects the central template into those snapshots.
"""
import json
from app.extensions import db
from app.models import Setting, AssessmentComponent, ClassSubject, Term
from app.errors import ValidationError

KEY = "assessment_template"
DEFAULT_TEMPLATE = [
    {"name": "First CA", "max_score": 10, "weight": 10, "report_slot": 1},
    {"name": "Second CA", "max_score": 10, "weight": 10, "report_slot": 2},
    {"name": "Third CA", "max_score": 10, "weight": 10, "report_slot": 3},
    {"name": "Examination", "max_score": 70, "weight": 70, "report_slot": 4},
]


def get_template():
    row = db.session.get(Setting, KEY)
    if not row or not row.value:
        return DEFAULT_TEMPLATE
    try:
        return json.loads(row.value)
    except (TypeError, ValueError):
        return DEFAULT_TEMPLATE


def validate_template(items):
    if not items or len(items) > 4:
        raise ValidationError("Configure between one and four assessment components.")
    clean, names, slots = [], set(), set()
    for i, item in enumerate(items, 1):
        name = str(item.get("name", "")).strip()
        try:
            maximum, weight, slot = int(item["max_score"]), int(item["weight"]), int(item["report_slot"])
        except (KeyError, TypeError, ValueError):
            raise ValidationError("Every assessment needs a name, maximum mark, weight and report column.")
        if not name or name.casefold() in names:
            raise ValidationError("Assessment names must be present and unique.")
        if maximum <= 0 or weight <= 0 or slot not in (1, 2, 3, 4) or slot in slots:
            raise ValidationError("Maximum marks and weights must be positive, and report columns must be unique (1–4).")
        names.add(name.casefold()); slots.add(slot)
        clean.append({"name": name, "max_score": maximum, "weight": weight, "report_slot": slot, "position": i})
    if sum(x["weight"] for x in clean) != 100:
        raise ValidationError("Assessment weights must add up to exactly 100%.")
    return clean


def save_template(actor, items):
    from app.services.authorization_service import require_operator
    from app.services.audit_log import log_action
    require_operator(actor)
    clean = validate_template(items)
    row = db.session.get(Setting, KEY)
    payload = json.dumps(clean)
    if row is None:
        db.session.add(Setting(key=KEY, value=payload))
    else:
        row.value = payload
    db.session.flush()
    sync_all()
    log_action(actor.id, "UPDATE_ASSESSMENT_TEMPLATE", "Setting", None,
               "Updated the school-wide assessment structure")
    db.session.commit()
    return clean


def sync_for(class_subject_id, term_id):
    """Create/update unscored component snapshots. Never rewrite scored history."""
    template = get_template()
    if not template:
        return []
    csub = db.session.get(ClassSubject, class_subject_id)
    term = db.session.get(Term, term_id)
    if csub is None or term is None or csub.class_session.academic_session_id != term.academic_session_id:
        return []
    existing = AssessmentComponent.query.filter_by(class_subject_id=class_subject_id, term_id=term_id).all()
    # A term/subject with entered scores is a historical snapshot. Never add,
    # remove or rewrite its assessment structure when the school template changes.
    if any(c.scores for c in existing):
        return sorted(existing, key=lambda c: (c.position or 0, c.id))
    by_name = {c.name.casefold(): c for c in existing}
    by_slot = {c.report_slot: c for c in existing if c.report_slot is not None}
    claimed = set()
    for item in template:
        # Match by name first, then by printed slot so legacy "CA 1" rows are
        # reused rather than duplicated as "First CA" when central settings land.
        comp = by_slot.get(item["report_slot"]) or by_name.get(item["name"].casefold())
        if comp is not None and comp.id in claimed:
            comp = None
        if comp is None:
            db.session.add(AssessmentComponent(class_subject_id=class_subject_id, term_id=term_id,
                name=item["name"], max_score=item["max_score"], weight=item["weight"],
                position=item.get("position", item["report_slot"]), report_slot=item["report_slot"]))
        else:
            claimed.add(comp.id)
            comp.name = item["name"]
            comp.report_slot = item["report_slot"]
            comp.position = item.get("position", item["report_slot"])
            if not comp.scores:
                comp.max_score, comp.weight = item["max_score"], item["weight"]
    # Remove obsolete, unscored legacy rows; retain scored rows as historical data.
    desired_slots = {x["report_slot"] for x in template}
    for comp in existing:
        if comp.id not in claimed and comp.report_slot not in desired_slots and not comp.scores:
            db.session.delete(comp)
    db.session.flush()
    return AssessmentComponent.query.filter_by(class_subject_id=class_subject_id, term_id=term_id).order_by(AssessmentComponent.position).all()


def sync_all():
    for csub in ClassSubject.query.all():
        terms = Term.query.filter_by(academic_session_id=csub.class_session.academic_session_id).all()
        for term in terms:
            sync_for(csub.id, term.id)
