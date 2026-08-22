"""Regression tests: the passkey second factor must not be skippable.

``POST /complete-2fa`` used to log the account in based solely on the
``pending_2fa_user_id`` session key, which is set as soon as the *password*
check succeeds.  Anyone who knew the password could therefore skip the
passkey assertion entirely.
"""

import os

import pytest

from app.extensions import db
from app.models import AdminAccount, WebAuthnCredential

PASSWORD = "correct-horse-battery-staple"


@pytest.fixture
def passkey_admin(app, session):
    """An AdminAccount that owns a passkey, so /login takes the 2FA branch."""
    with app.app_context():
        account = AdminAccount(username="passkey-admin")
        account.set_password(PASSWORD)
        db.session.add(account)
        db.session.flush()

        credential = WebAuthnCredential(
            admin_account_id=account.id,
            credential_id=os.urandom(16),
            public_key=os.urandom(32),
            sign_count=0,
            name="Test Key",
        )
        db.session.add(credential)
        db.session.commit()

        return {"id": account.id, "username": account.username}


def _login_with_password(client):
    return client.post(
        "/login",
        data={"username": "passkey-admin", "password": PASSWORD},
    )


def _is_logged_in(client) -> bool:
    """A ``@login_required`` route answers 200 only for an authenticated session."""
    response = client.get("/settings/connections/", headers={"HX-Request": "true"})
    return response.status_code == 200


def test_complete_2fa_without_verified_assertion_does_not_log_in(
    app, client, passkey_admin
):
    """Password alone must not be enough to finish the 2FA login."""
    response = _login_with_password(client)
    assert response.status_code == 200

    with client.session_transaction() as sess:
        assert sess.get("pending_2fa_user_id") == passkey_admin["id"]

    response = client.post("/complete-2fa")

    assert not _is_logged_in(client)

    with client.session_transaction() as sess:
        assert sess.get("pending_2fa_user_id") is None
        assert sess.get("webauthn_2fa_verified") is None


def test_complete_2fa_with_verified_assertion_logs_in(app, client, passkey_admin):
    """A verified passkey assertion completes the login and is consumed."""
    _login_with_password(client)

    with client.session_transaction() as sess:
        sess["webauthn_2fa_verified"] = passkey_admin["id"]

    response = client.post("/complete-2fa")
    assert response.status_code == 302

    assert _is_logged_in(client)

    with client.session_transaction() as sess:
        assert sess.get("webauthn_2fa_verified") is None
        assert sess.get("pending_2fa_user_id") is None

    client.get("/logout")


def test_complete_2fa_rejects_verified_flag_for_another_account(
    app, client, session, passkey_admin
):
    """The verified flag must match the account that passed the password check."""
    with app.app_context():
        other = AdminAccount(username="other-admin")
        other.set_password(PASSWORD)
        db.session.add(other)
        db.session.commit()
        other_id = other.id

    _login_with_password(client)

    with client.session_transaction() as sess:
        sess["webauthn_2fa_verified"] = other_id

    client.post("/complete-2fa")

    assert not _is_logged_in(client)
