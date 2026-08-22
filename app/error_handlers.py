# app/error_handlers.py
import logging

from flask import render_template
from flask_wtf.csrf import CSRFError


def register_error_handlers(app):
    @app.errorhandler(500)
    def error_500(e):
        logging.error("500: %s", e, exc_info=True)
        return render_template("error/500.html"), 500

    @app.errorhandler(404)
    def error_404(e):
        logging.info("404: %s", e)
        return render_template("error/404.html"), 404

    @app.errorhandler(401)
    def error_401(e):
        logging.info("401: %s", e)
        return render_template("error/401.html"), 401

    @app.errorhandler(CSRFError)
    def error_csrf(e):
        # HTMX swaps the response body straight into the page, so keep this a
        # short plain-text message rather than a rendered page or a traceback.
        logging.warning("CSRF failure: %s", e.description)
        return (
            "Security token missing or expired. Please reload the page and try again.",
            400,
            {"Content-Type": "text/plain; charset=utf-8"},
        )
