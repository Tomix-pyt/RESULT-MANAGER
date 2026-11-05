from flask import Blueprint, render_template, request, redirect, url_for, session, flash, g
from app.services.auth_service import authenticate
from app.services.audit_log import log_action
from app.extensions import db

bp = Blueprint("auth", __name__)


def home_for(user):
    if user is None:
        return url_for("auth.login")
    return url_for("operator.dashboard") if user.role == "OPERATOR" else url_for("staff.dashboard")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(home_for(g.user))
    if request.method == "POST":
        user = authenticate(request.form.get("username", ""), request.form.get("password", ""))
        if user is None:
            log_action(None, "LOGIN_FAILED", "User", None, f"Failed login for '{request.form.get('username','')[:80]}'")
            db.session.commit()
            flash("Incorrect username or password.", "error")
            return render_template("auth/login.html"), 401
        session.clear()               # new session on login (prevents session fixation)
        session["user_id"] = user.id
        session.permanent = True
        log_action(user.id, "LOGIN", "User", user.id, "Logged in")
        db.session.commit()
        return redirect(home_for(user))
    return render_template("auth/login.html")


@bp.route("/logout", methods=["POST"])
def logout():
    if g.user:
        log_action(g.user.id, "LOGOUT", "User", g.user.id, "Logged out")
        db.session.commit()
    session.clear()
    return redirect(url_for("auth.login"))
