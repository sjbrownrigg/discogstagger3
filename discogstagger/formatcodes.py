# -*- coding: utf-8 -*-
"""Discogs format code computation.

Translates the three format fields that Discogs provides — format name,
format descriptions, and disc count — into a compact, human-readable code
that can be used in directory/file naming format strings as ``%format_code%``.

Examples
--------
Vinyl  + ["Album"]                + 1  →  LP
Vinyl  + ["Single", "7\\""]      + 1  →  7″S
Vinyl  + ["Maxi-Single", "12\\""]+ 1  →  12″M
Vinyl  + ["Album"]                + 2  →  DLP
CD     + ["Album"]                + 1  →  CD
CD     + ["Single"]               + 1  →  CDS
CD     + ["Single","Limited Ed."] + 1  →  LCDS
CD     + ["Album","Limited Ed."]  + 2  →  DLCD
File   + ["Album", "FLAC"]        + 1  →  File

Architecture note
-----------------
This module is purely computational — no I/O except YAML loading via
``load_format_codes()``.  It has no dependency on Discogs, tagging or file
I/O, making it easy to reuse in a future service-agnostic tagger.
"""
import logging
import os

logger = logging.getLogger(__name__)

_HERE = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_YAML = os.path.join(_HERE, '..', 'conf', 'format_codes.yaml')


def load_format_codes(yaml_path: str | None = None) -> dict:
    """Load format code rules from a YAML file.

    Returns an empty dict (and logs a warning) if the file is missing or
    PyYAML is not installed — the caller falls back to the raw format name.
    """
    path = yaml_path or _DEFAULT_YAML
    try:
        import yaml
    except ImportError:
        logger.warning('pyyaml is not installed — format codes unavailable')
        return {}
    try:
        with open(path, encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}
        logger.debug('Loaded format codes from %s', path)
        return data
    except FileNotFoundError:
        logger.debug('Format codes file not found: %s', path)
        return {}
    except Exception as e:
        logger.warning('Failed to load format codes from %s: %s', path, e)
        return {}


def compute_format_code(format_name: str,
                        descriptions: list,
                        disctotal: int,
                        format_codes: dict) -> str:
    """Return a compact format code for a Discogs release.

    Parameters
    ----------
    format_name:
        The Discogs ``formats[0].name`` value, e.g. ``"Vinyl"``, ``"CD"``.
    descriptions:
        The raw (pre-mapping) ``formats[0].descriptions`` list from Discogs,
        e.g. ``["Album", "Limited Edition", "33 ⅓ RPM"]``.
    disctotal:
        Total number of records/discs in the release (``album.disctotal``).
    format_codes:
        Rules dict as returned by ``load_format_codes()``.  An empty dict
        causes the function to return ``format_name`` unchanged.

    Returns
    -------
    str
        The computed code, e.g. ``"LCDS"``, ``"12″M"``, ``"DLP"``.
        Falls back to ``format_name`` when no rules are available.
    """
    if not format_codes:
        return format_name or ''

    desc_set = set(descriptions or [])

    # ── Step 1: base code from format name ───────────────────────────────────
    base_formats = format_codes.get('base_formats', {})
    base = base_formats.get(format_name, format_name or '')

    # ── Step 2: vinyl size override ───────────────────────────────────────────
    if format_name == 'Vinyl':
        vinyl_sizes = format_codes.get('vinyl_sizes', {})
        for size_key, size_code in vinyl_sizes.items():
            if size_key in desc_set:
                base = size_code
                break   # first matching size wins

    # ── Step 3: suffix from descriptions ─────────────────────────────────────
    suffixes = format_codes.get('suffixes', {})
    suffix = ''
    for desc in (descriptions or []):
        if desc in suffixes:
            val = suffixes[desc]
            if val:          # empty string = "implied, suppress"
                suffix = val
            break            # first matching description wins

    code = base + suffix

    # ── Step 4: quantity prefix ───────────────────────────────────────────────
    # Applied before description prefixes so that the result reads naturally:
    # L (limited) + D (double) + CD = LDCD, not DLCD.
    qty = int(disctotal or 1)
    if qty > 1:
        aliases = format_codes.get('quantity_aliases', {})
        qty_fmt = format_codes.get('quantity_format', '{n}x')
        qty_str = str(aliases.get(qty, qty_fmt.replace('{n}', str(qty))))
        code = qty_str + code

    # ── Step 5: description prefixes ─────────────────────────────────────────
    # Applied last so they wrap the entire code including the quantity.
    # All matching prefixes are applied, in the order they appear in the YAML.
    prefixes = format_codes.get('prefixes', {})
    prefix = ''
    for prefix_desc, prefix_str in prefixes.items():
        if prefix_desc in desc_set:
            prefix += prefix_str

    return prefix + code
