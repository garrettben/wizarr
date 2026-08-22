"""Sandboxed Jinja rendering for admin- and database-sourced template strings.

Wizard step markdown, wizard step titles and widget parameters are template
sources that reach the app from the database or from the wizard import route,
and the result is served to *anonymous* invitees.  Rendering them in the
application's own Jinja environment hands that source the full expression
language, so ``{{ ''.__class__.__mro__[1].__subclasses__() }}`` walks straight
out of the template and into the interpreter.

Everything here renders through :class:`jinja2.sandbox.SandboxedEnvironment`,
which keeps the templating features admins rely on while refusing unsafe
attribute access and unsafe callables.
"""

from __future__ import annotations

from flask import current_app, has_app_context
from jinja2.sandbox import SandboxedEnvironment

# Flask registers these in ``jinja_env.globals``.  They hand a template the
# application configuration (``config.SECRET_KEY``), the signed session cookie
# and the raw request, so they are never copied into the sandbox.
_UNSAFE_GLOBALS: frozenset[str] = frozenset({"config", "g", "request", "session"})

# Key under which the per-app environments are memoised on ``app.extensions``.
_ENV_CACHE_KEY = "wizarr_sandbox_envs"


def _build_env(autoescape: bool) -> SandboxedEnvironment:
    """Create a sandbox mirroring the app's Jinja setup, minus the unsafe bits."""
    source = current_app.jinja_env if has_app_context() else None

    # Mirroring the extensions keeps ``{% trans %}`` working in admin content.
    extensions = list(source.extensions) if source is not None else []
    env = SandboxedEnvironment(autoescape=autoescape, extensions=extensions)

    if source is not None:
        # Filters are presentation helpers (``human_date``, ``nl2br``, …) and
        # are safe to share.  Globals are shared except for the Flask internals
        # above; this is what keeps ``_``/``gettext`` available to steps.
        env.filters.update(source.filters)
        env.globals.update(
            {k: v for k, v in source.globals.items() if k not in _UNSAFE_GLOBALS}
        )
        env.policies.update(source.policies)
        env.newstyle_gettext = getattr(source, "newstyle_gettext", False)

    return env


def get_sandbox_env(autoescape: bool = True) -> SandboxedEnvironment:
    """Return the cached sandbox for *autoescape* (one per app, per mode)."""
    if not has_app_context():
        return _build_env(autoescape)

    cache = current_app.extensions.setdefault(_ENV_CACHE_KEY, {})
    env = cache.get(autoescape)
    if env is None:
        env = cache[autoescape] = _build_env(autoescape)
    return env


def render_sandboxed(source: str, *, autoescape: bool = True, **ctx) -> str:
    """Render *source* as a Jinja template inside the sandbox.

    Raises :class:`jinja2.exceptions.SecurityError` when the template attempts
    unsafe attribute access; callers decide whether to degrade or propagate.
    """
    return get_sandbox_env(autoescape).from_string(source).render(**ctx)
