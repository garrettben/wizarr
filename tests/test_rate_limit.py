"""Regression tests: the rate limiter must actually run.

``limiter`` was constructed with ``enabled=False`` and no config ever set
``RATELIMIT_ENABLED``, so Flask-Limiter kept that default and every
``@limiter.limit(...)`` decorator in the app was a no-op — ``POST /login``
could be brute-forced without limit.
"""

import contextlib
import os
import tempfile

import pytest
from flask_migrate import upgrade

from app import create_app
from app.config import BaseConfig
from tests.conftest import TestConfig


class RateLimitedConfig(TestConfig):
    """Same as the test config, but with the limiter switched on."""

    RATELIMIT_ENABLED = True
    _temp_db_path = os.path.join(tempfile.gettempdir(), "wizarr_ratelimit_test.db")
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{_temp_db_path}"


def _remove_db_files():
    for ext in ("", "-wal", "-shm"):
        with contextlib.suppress(OSError):
            os.unlink(RateLimitedConfig._temp_db_path + ext)


@pytest.fixture
def rate_limited_client(app):
    """A client for an app with RATELIMIT_ENABLED=True.

    The autouse ``reset_rate_limiter`` fixture switches the shared Limiter
    instance back off once the test is done.
    """
    _remove_db_files()

    limited_app = create_app(RateLimitedConfig)  # type: ignore[arg-type]
    with limited_app.app_context():
        upgrade()

    yield limited_app.test_client()

    _remove_db_files()


def _post_bad_login(client):
    return client.post("/login", data={"username": "nobody", "password": "wrong"})


def test_rate_limiting_is_enabled_by_default():
    """Deployments must get limits without opting in; only tests opt out."""
    assert BaseConfig.RATELIMIT_ENABLED is True
    assert TestConfig.RATELIMIT_ENABLED is False


def test_login_is_rate_limited_when_enabled(rate_limited_client):
    """The 11th login attempt in a minute is refused (limit is 10 per minute)."""
    statuses = [_post_bad_login(rate_limited_client).status_code for _ in range(11)]

    assert statuses[:10] == [200] * 10
    assert statuses[10] == 429


def test_login_is_not_rate_limited_in_tests(client):
    """The default test config keeps limits off so the suite can hammer /login."""
    statuses = [_post_bad_login(client).status_code for _ in range(11)]

    assert 429 not in statuses


def test_proxy_fix_uses_forwarded_client_ip(rate_limited_client):
    """Limits key off X-Forwarded-For, not the reverse proxy's own address."""
    for _ in range(10):
        rate_limited_client.post(
            "/login",
            data={"username": "nobody", "password": "wrong"},
            headers={"X-Forwarded-For": "203.0.113.7"},
        )

    blocked = rate_limited_client.post(
        "/login",
        data={"username": "nobody", "password": "wrong"},
        headers={"X-Forwarded-For": "203.0.113.7"},
    )
    other_client = rate_limited_client.post(
        "/login",
        data={"username": "nobody", "password": "wrong"},
        headers={"X-Forwarded-For": "203.0.113.8"},
    )

    assert blocked.status_code == 429
    assert other_client.status_code == 200
