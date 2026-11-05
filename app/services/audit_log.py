from flask import has_request_context, request
from app.extensions import db
from app.models import AuditLog


def log_action(user_id, action, entity_type=None, entity_id=None, description=None, ip_address=None):
    """Record an auditable action. Does NOT commit: it joins the caller's
    transaction so the log entry and the change succeed or fail together."""
    if ip_address is None and has_request_context():
        ip_address = request.remote_addr
    entry = AuditLog(user_id=user_id, action=action, entity_type=entity_type,
                     entity_id=entity_id, description=description, ip_address=ip_address)
    db.session.add(entry)
    return entry
