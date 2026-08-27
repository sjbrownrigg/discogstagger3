# -*- coding: utf-8 -*-
"""The roots discogstagger3 resolves paths against.

Three roots, deliberately separate, because conflating them is what made the
program only work when run from a source checkout:

``PACKAGE_ROOT``
    Bundled defaults that ship inside the wheel -- sample configs,
    ``format_codes.yaml``, ``char_substitutions.yaml``, the Mako templates.
    Immutable, resolved from ``__file__``, always present in an installed
    package.

``config_root(config_file)``
    The directory of the config file being loaded.  Paths *named by* a config
    file (``formats_file``, ``templates_dir``) resolve against it, so a config
    file and the files it references travel together.  This is what lets one
    config work unchanged on a laptop and in a container.

``state_root()``
    Mutable runtime data -- the OAuth ``.token``, the API cache.  Explicit via
    ``DISCOGSTAGGER_STATE_DIR``, otherwise the XDG state directory.  Never the
    working directory: a cache that lands wherever the user happened to be
    standing is not a cache, and in a container it forced the image to make
    ``/app`` writable purely to hold a token file.

The data root -- the music library itself -- is not listed here.  It is
supplied by the user as ``source_dir``/``dest_dir`` or ``-s``, and belongs to
the user rather than to the program.

Nothing in discogstagger3 should call ``os.getcwd()``.  The one remaining use
is the deprecated fallback in :func:`resolve_config_path`.
"""

import logging
import os

logger = logging.getLogger(__name__)

# ── Package root ─────────────────────────────────────────────────────────────

PACKAGE_ROOT = os.path.dirname(os.path.abspath(__file__))

BUNDLED_CONF = os.path.join(PACKAGE_ROOT, "conf")
BUNDLED_TEMPLATES = os.path.join(PACKAGE_ROOT, "templates")


# ── Config root ──────────────────────────────────────────────────────────────

def config_root(config_file):
    """Return the directory *config_file* lives in, or None when there isn't one.

    Used as the base for paths a config file names.
    """
    if not config_file:
        return None
    return os.path.dirname(os.path.abspath(config_file))


def resolve_config_path(value, base_dir, key_name="path"):
    """Resolve *value*, a path read from a config file, to an absolute path.

    Resolution order:

    1. ``~`` expansion, and absolute paths returned as-is.
    2. Relative to *base_dir* -- the directory of the config file naming it.
    3. Relative to the working directory, which is the historic behaviour.
       This still works but emits a deprecation warning naming both paths
       tried, so the fix is obvious from the log.

    Returns None when *value* is empty.  Returns the step-2 candidate when
    nothing exists, so callers raise a "not found" error naming the path the
    user is meant to create rather than the legacy one.
    """
    if not value:
        return None

    expanded = os.path.expanduser(value)

    if os.path.isabs(expanded):
        return expanded

    preferred = (os.path.join(base_dir, expanded)
                 if base_dir else os.path.abspath(expanded))
    if os.path.exists(preferred):
        return preferred

    legacy = os.path.abspath(expanded)
    if legacy != preferred and os.path.exists(legacy):
        logger.warning(
            "%s resolved relative to the working directory, which is "
            "deprecated: %s\n"
            "  Move it beside the config file (expected at %s), or make the "
            "value an absolute path. The working-directory fallback will be "
            "removed in a future release.",
            key_name, legacy, preferred)
        return legacy

    return preferred


# ── State root ───────────────────────────────────────────────────────────────

_LEGACY_STATE_FILENAMES = (".token",)


def state_root():
    """Return the directory for mutable runtime state, creating it if needed.

    ``DISCOGSTAGGER_STATE_DIR`` wins when set -- containers should point it at
    a mounted volume.  Otherwise ``$XDG_STATE_HOME/discogstagger``, falling
    back to ``~/.local/state/discogstagger``.
    """
    explicit = os.environ.get("DISCOGSTAGGER_STATE_DIR")
    if explicit:
        base = os.path.expanduser(explicit)
    else:
        xdg = os.environ.get("XDG_STATE_HOME") or os.path.join(
            os.path.expanduser("~"), ".local", "state")
        base = os.path.join(os.path.expanduser(xdg), "discogstagger")

    try:
        os.makedirs(base, exist_ok=True)
    except OSError as exc:
        logger.warning("Could not create state directory %s: %s", base, exc)
    return base


def state_path(filename):
    """Return the path to *filename* within the state root.

    When the file is absent there but a legacy copy exists in the working
    directory, the legacy path is returned so an existing OAuth token keeps
    working instead of silently forcing re-authentication.
    """
    current = os.path.join(state_root(), filename)
    if os.path.exists(current):
        return current

    if filename in _LEGACY_STATE_FILENAMES:
        legacy = os.path.join(os.getcwd(), filename)
        if os.path.exists(legacy):
            logger.warning(
                "Using %s from the working directory. This location is "
                "deprecated; move it to %s (or set DISCOGSTAGGER_STATE_DIR).",
                legacy, current)
            return legacy

    return current
