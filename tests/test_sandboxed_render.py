"""Tests for the shared sandboxed Jinja renderer.

Wizard step titles, wizard step markdown and widget parameters are template
sources that arrive from the database or from an admin import file and are
rendered for anonymous invitees.  They must never reach a full Jinja
environment, where ``{{ ''.__class__.__mro__ }}`` walks straight out of the
template into the interpreter.
"""

import pytest
from jinja2.exceptions import SecurityError

from app.jinja_filters import render_jinja
from app.services.sandbox import render_sandboxed

SANDBOX_ESCAPE = "{{ ''.__class__.__mro__[1].__subclasses__() }}"
# The widget text path treats "_(" as a translation call, so this variant
# stays a plain attribute walk.
WIDGET_ESCAPE = "{{ ''.__class__.__mro__[1] }}"


def test_render_sandboxed_evaluates_plain_expressions(app):
    with app.app_context():
        assert render_sandboxed("{{ 7*6 }}") == "42"


def test_render_sandboxed_blocks_class_traversal(app):
    with app.app_context(), pytest.raises(SecurityError):
        render_sandboxed(SANDBOX_ESCAPE)


def test_render_sandboxed_blocks_class_traversal_without_app_context():
    with pytest.raises(SecurityError):
        render_sandboxed(SANDBOX_ESCAPE)


def test_render_sandboxed_autoescapes_by_default(app):
    with app.app_context():
        assert (
            render_sandboxed("{{ value }}", value="<b>x</b>") == "&lt;b&gt;x&lt;/b&gt;"
        )


def test_render_sandboxed_can_disable_autoescape(app):
    with app.app_context():
        rendered = render_sandboxed("{{ value }}", autoescape=False, value="<b>x</b>")
        assert rendered == "<b>x</b>"


def test_render_sandboxed_does_not_expose_flask_config(app):
    """``config.SECRET_KEY`` is the classic SSTI payoff – keep it out."""
    with app.app_context():
        assert render_sandboxed("{{ config }}") == ""


def test_render_jinja_still_renders_gettext_titles(app):
    with app.app_context():
        assert str(render_jinja("{{ _('Hello') }}")) == "Hello"


def test_render_jinja_escapes_html_expressions(app):
    with app.app_context():
        rendered = str(render_jinja("{{ '<b>' }}"))
        assert rendered == "&lt;b&gt;"


def test_render_jinja_does_not_execute_sandbox_escape(app):
    """A wizard step title is DB-sourced; it must not reach the interpreter."""
    with app.app_context():
        rendered = str(render_jinja(SANDBOX_ESCAPE))
        assert "WizardPreset" not in rendered
        assert "type&#39;" not in rendered
        # The unrendered source is echoed back, escaped.
        assert "__subclasses__" in rendered


def test_widget_text_does_not_execute_sandbox_escape(app):
    """Widget parameters come from step content and are template sources too."""
    from app.services.wizard_widgets import ButtonWidget

    with app.app_context():
        html = ButtonWidget().render(
            "jellyfin", url="https://example.com", text=WIDGET_ESCAPE
        )
        # The widget escapes its text twice, so normalise before looking.
        assert "&lt;class" not in html.replace("&amp;", "&")
        assert "__class__" in html
