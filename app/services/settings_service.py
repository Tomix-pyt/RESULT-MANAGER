from app.extensions import db
from app.models import Setting
from app.services.authorization_service import require_operator
from app.services.audit_log import log_action

FIELDS = [
    ("school_name", "School name (top line of results)", "CREATIVITY SCIENCE AND TECHNICAL COLLEGE, WANNUNE"),
    ("school_region", "State / country line", "BENUE STATE, NIGERIA."),
    ("school_address", "Address", "Behind Timber shed Wannune, Tarka L.G.A, Benue state."),
    ("school_motto", "Motto", ""),
    ("principal_name", "Principal's name", "Kwagh Joseph"),
    ("principal_remark", "Default principal's remark", ""),
    ("next_term_begins", "Next term begins", ""),
    ("report_footer", "Report footer note", ""),
]


def get_settings() -> dict:
    stored = {s.key: s.value for s in Setting.query.all()}
    return {k: (stored.get(k) if stored.get(k) is not None else default) for k, _, default in FIELDS}


def save_settings(actor, values: dict) -> None:
    require_operator(actor)
    for key, _, _ in FIELDS:
        if key in values:
            row = db.session.get(Setting, key)
            val = (values[key] or "").strip()
            if row is None:
                db.session.add(Setting(key=key, value=val))
            else:
                row.value = val
    log_action(actor.id, "CHANGE_SETTINGS", "Setting", None, "Updated school settings")
    db.session.commit()
