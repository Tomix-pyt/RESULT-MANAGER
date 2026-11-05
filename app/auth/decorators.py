from functools import wraps
from flask import g, redirect, url_for
from app.errors import PermissionDenied


def login_required(view):
    @wraps(view)
    def wrapped(*a, **kw):
        if g.get("user") is None:
            return redirect(url_for("auth.login"))
        return view(*a, **kw)
    return wrapped


def role_required(role):
    def deco(view):
        @wraps(view)
        @login_required
        def wrapped(*a, **kw):
            if g.user.role != role:
                raise PermissionDenied("You do not have access to this area.")
            return view(*a, **kw)
        return wrapped
    return deco


operator_required = role_required("OPERATOR")
staff_required = role_required("STAFF")
