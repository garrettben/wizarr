# app/middleware.py
from flask import current_app, redirect, request, url_for

from app.models import Settings

_DEFAULT_SECURITY_HEADERS = {
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


def require_onboarding():
    if (
        request.path.startswith("/setup")
        or request.path.startswith("/static")
        or request.path.startswith("/settings")
        or request.path.startswith("/api")
    ):
        return None

    # Skip onboarding check during testing
    if current_app.config.get("TESTING"):
        return None

    # Check if an admin user exists
    admin_setting = Settings.query.filter_by(key="admin_username").first()
    if not admin_setting or not admin_setting.value:
        return redirect(url_for("setup.onboarding"))
    return None
    # Allow access to the application even if no MediaServer has been configured yet.
    # Users can add servers later via the Settings page.


def register_security_headers(app):
    """Attach baseline security response headers to every response.

    Headers are only set when the response doesn't already carry them, so
    routes that already set their own value (e.g. the image proxy's
    ``X-Content-Type-Options``) are left untouched instead of duplicated.
    """

    @app.after_request
    def _apply_security_headers(response):
        for name, value in _DEFAULT_SECURITY_HEADERS.items():
            if name not in response.headers:
                response.headers[name] = value

        csp_report_only = current_app.config.get("CSP_REPORT_ONLY")
        if csp_report_only and "Content-Security-Policy-Report-Only" not in (
            response.headers
        ):
            response.headers["Content-Security-Policy-Report-Only"] = csp_report_only

        return response

    return app
