"""Baseline security response headers, applied to every response."""


def test_login_page_carries_security_headers(client):
    resp = client.get("/login")

    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert (
        resp.headers["Permissions-Policy"] == "camera=(), microphone=(), geolocation=()"
    )
    csp = resp.headers["Content-Security-Policy-Report-Only"]
    assert "default-src 'self'" in csp


def test_health_endpoint_carries_security_headers(client):
    resp = client.get("/health")

    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "Content-Security-Policy-Report-Only" in resp.headers


def test_image_proxy_nosniff_header_not_duplicated(client):
    """The image proxy already sets X-Content-Type-Options; the global
    after_request hook must not add a second, duplicate value."""
    from app.blueprints.public.routes import _image_proxy_response

    resp = _image_proxy_response(b"fake-bytes", "image/png")
    assert resp.headers.get_all("X-Content-Type-Options") == ["nosniff"]

    # Push it through the real app's after_request chain via a request context
    # to confirm the hook does not append a second value.
    with client.application.test_request_context("/image-proxy"):
        from flask import current_app

        processed = current_app.process_response(resp)
        assert processed.headers.get_all("X-Content-Type-Options") == ["nosniff"]
