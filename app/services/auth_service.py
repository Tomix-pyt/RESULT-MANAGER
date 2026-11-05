from werkzeug.security import check_password_hash, generate_password_hash
from sqlalchemy import func
from app.extensions import db
from app.models import User
from app.errors import ValidationError, DuplicateError

ROLES = ("OPERATOR", "STAFF")
MIN_PASSWORD_LENGTH = 8


def _validate_password(password: str) -> None:
    if not password or len(password) < MIN_PASSWORD_LENGTH:
        raise ValidationError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")


def create_user(*, username, first_name, last_name, password, role="STAFF", email=None) -> User:
    """Low-level user creation. Callers that act on behalf of a logged-in user
    should go through operator_service.create_user_account (which checks permissions)."""
    username = (username or "").strip()
    first_name = (first_name or "").strip()
    last_name = (last_name or "").strip()
    email = (email or "").strip().lower() or None

    if not (username and first_name and last_name):
        raise ValidationError("Username, first name and last name are required.")
    _validate_password(password)
    if role not in ROLES:
        raise ValidationError("Role must be OPERATOR or STAFF.")
    if User.query.filter(func.lower(User.username) == username.lower()).first():
        raise DuplicateError("That username is already taken.")
    if email and User.query.filter_by(email=email).first():
        raise DuplicateError("That email is already in use.")

    user = User(username=username, email=email, first_name=first_name, last_name=last_name,
                password_hash=generate_password_hash(password), role=role, is_active=True)
    db.session.add(user)
    db.session.commit()
    return user


def authenticate(username: str, password: str) -> User | None:
    user = User.query.filter(func.lower(User.username) == (username or "").strip().lower()).first()
    if user is None or not user.is_active:
        return None
    if not check_password_hash(user.password_hash, password or ""):
        return None
    return user
