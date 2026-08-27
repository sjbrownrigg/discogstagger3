# -*- coding: utf-8 -*-
"""discogstagger3 — console audio tagger using the Discogs API."""

from importlib.metadata import PackageNotFoundError, version as _version

try:
    __version__ = _version("discogstagger3")
except PackageNotFoundError:  # running from a source tree, not installed
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
