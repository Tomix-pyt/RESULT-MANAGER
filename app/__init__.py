import click
from flask import Flask, flash, redirect, request, url_for, render_template, g, session, send_from_directory, current_app

from markupsafe import Markup
from flask_wtf.csrf import generate_csrf
from config import Config
from app.extensions import db, migrate, csrf
from app.errors import DomainError, PermissionDenied, NotFoundError


def create_app(config_object=Config):
    app = Flask(__name__)
    app.config.from_object(config_object)

    if not app.config.get("SECRET_KEY"):
        raise RuntimeError("SECRET_KEY is not set. Copy .env.example to .env and fill it in.")
    if not app.config.get("SQLALCHEMY_DATABASE_URI"):
        raise RuntimeError("DATABASE_URL is not set. Copy .env.example to .env and fill it in.")

    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)

    from app import models  # noqa: F401  (registers tables with SQLAlchemy / Alembic)

    from app.auth.routes import bp as auth_bp
    from app.operator.routes import bp as operator_bp
    from app.staff.routes import bp as staff_bp
    app.register_blueprint(auth_bp)
    from app.operator.results import bp as results_bp
    app.register_blueprint(operator_bp, url_prefix="/admin")
    app.register_blueprint(results_bp, url_prefix="/admin")
    app.register_blueprint(staff_bp, url_prefix="/staff")

    from app.services import report_service as _rs
    app.jinja_env.filters["mark"] = _rs.fmt_mark
    app.jinja_env.filters["ordinal"] = _rs.ordinal
    app.jinja_env.filters["date_dmy"] = _rs.fmt_date

    @app.before_request
    def load_user():
        from app.models import User
        uid = session.get("user_id")
        g.user = db.session.get(User, uid) if uid else None
        if g.user is not None and not g.user.is_active:
            session.clear()
            g.user = None

    @app.context_processor
    def inject_globals():
        return {"current_user": g.get("user"), "school_name": current_app.config["SCHOOL_NAME"],
                "csrf_field": lambda: Markup(f'<input type="hidden" name="csrf_token" value="{generate_csrf()}">')}

    # ---- PWA files must be served from the site root so their scope covers the whole app
    @app.route("/sw.js")
    def service_worker():
        resp = send_from_directory(app.static_folder, "sw.js", mimetype="application/javascript")
        resp.headers["Service-Worker-Allowed"] = "/"
        resp.headers["Cache-Control"] = "no-cache"
        return resp

    @app.route("/manifest.webmanifest")
    def manifest():
        return send_from_directory(app.static_folder, "manifest.webmanifest", mimetype="application/manifest+json")

    @app.route("/offline")
    def offline():
        return render_template("offline.html")

    @app.route("/")
    def index():
        from app.auth.routes import home_for
        return redirect(home_for(g.user))

    # ---- Error handling: domain errors become friendly messages, never stack traces
    @app.errorhandler(PermissionDenied)
    def _denied(e):
        return render_template("errors/403.html", message=str(e)), 403

    @app.errorhandler(NotFoundError)
    def _missing(e):
        return render_template("errors/404.html", message=str(e)), 404

    @app.errorhandler(DomainError)
    def _domain(e):
        flash(str(e), "error")
        return redirect(request.referrer or url_for("index"))

    @app.errorhandler(403)
    def _403(e):
        return render_template("errors/403.html", message="You do not have access to this page."), 403

    @app.errorhandler(404)
    def _404(e):
        return render_template("errors/404.html", message="Page not found."), 404

    # ---- CLI
    @app.cli.command("create-operator")
    @click.option("--username", prompt=True)
    @click.option("--first-name", prompt=True)
    @click.option("--last-name", prompt=True)
    @click.password_option()
    def create_operator(username, first_name, last_name, password):
        """Create the first operator (admin) account."""
        from app.services.auth_service import create_user
        user = create_user(username=username, first_name=first_name, last_name=last_name,
                           password=password, role="OPERATOR")
        click.echo(f"Operator '{user.username}' created.")

    @app.cli.command("check-enrollments")
    def check_enrollments():
        """List students enrolled in more than one class in the same session."""
        from sqlalchemy import text
        agg = "string_agg(c.name, ', ' ORDER BY c.name)" if db.engine.dialect.name == "postgresql" \
            else "group_concat(c.name, ', ')"
        rows = db.session.execute(text(f"""
            SELECT st.admission_number, st.last_name, st.first_name, ses.name, {agg}
            FROM student_enrollments e
            JOIN class_sessions cs ON cs.id = e.class_session_id
            JOIN classes c ON c.id = cs.class_id
            JOIN academic_sessions ses ON ses.id = cs.academic_session_id
            JOIN students st ON st.id = e.student_id
            GROUP BY st.id, st.admission_number, st.last_name, st.first_name, ses.id, ses.name
            HAVING COUNT(*) > 1 ORDER BY ses.name, st.last_name""")).fetchall()
        if not rows:
            click.echo("OK: every student is in at most one class per session.")
        for adm, last, first, ses, classes in rows:
            click.echo(f"{adm}  {last} {first}  [{ses}]  -> {classes}")

    return app
