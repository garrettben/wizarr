"""Session and remember-me cookie flags.

Dev runs on plain http, so SECURE is only forced on ProductionConfig; the
other flags (HttpOnly / SameSite / lifetime) apply everywhere via
BaseConfig.
"""

import os
import tempfile
from datetime import timedelta

from app import create_app
from app.config import BaseConfig, ProductionConfig
from app.extensions import db
from app.models import AdminAccount


class ProductionTestConfig(ProductionConfig):
    TESTING = True
    WTF_CSRF_ENABLED = False
    _temp_db_path = os.path.join(
        tempfile.gettempdir(), "wizarr_test_production_cookie.db"
    )
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{_temp_db_path}"


def test_production_config_forces_secure_cookies():
    app = create_app(ProductionTestConfig)

    assert app.config["SESSION_COOKIE_SECURE"] is True
    assert app.config["REMEMBER_COOKIE_SECURE"] is True


def test_base_config_sets_cookie_hardening_defaults():
    assert BaseConfig.SESSION_COOKIE_HTTPONLY is True
    assert BaseConfig.SESSION_COOKIE_SAMESITE == "Lax"
    assert BaseConfig.REMEMBER_COOKIE_HTTPONLY is True
    assert BaseConfig.REMEMBER_COOKIE_SAMESITE == "Lax"
    assert timedelta(days=7) == BaseConfig.PERMANENT_SESSION_LIFETIME


def test_session_cookie_carries_httponly_and_samesite(client, app):
    with app.app_context():
        acc = AdminAccount(username="cookie-carol")
        acc.set_password("Password1")
        db.session.add(acc)
        db.session.commit()

    resp = client.post(
        "/login", data={"username": "cookie-carol", "password": "Password1"}
    )
    assert resp.status_code in {302, 303}

    set_cookie_headers = resp.headers.get_all("Set-Cookie")
    session_cookie = next(h for h in set_cookie_headers if h.startswith("session="))
    assert "HttpOnly" in session_cookie
    assert "SameSite=Lax" in session_cookie
