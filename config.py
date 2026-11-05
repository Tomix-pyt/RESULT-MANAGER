import os
from dotenv import load_dotenv

load_dotenv()


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    # The project uses psycopg v3; SQLAlchemy needs the +psycopg driver tag.
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY")
    SQLALCHEMY_DATABASE_URI = _database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("FLASK_ENV") == "production"
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 8  # 8 hours
    SCHOOL_NAME = os.environ.get("SCHOOL_NAME", "Creativity Science Secondary School")


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "test"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
