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


def compute_edition(descriptions: list, format_codes: dict) -> str:
    """Return the first edition qualifier found in descriptions, or ''.

    Edition qualifiers (e.g. ``'Deluxe Edition'``, ``'Anniversary Edition'``)
    are listed under the ``editions`` key in format_codes.yaml.  They are
    intended to be displayed alongside the album title:

        [2012] The Young Gods (Deluxe Edition) [DCD flac-lossless-44s]

    Matching is **case-insensitive substring** so that a pattern like
    ``'Anniversary Edition'`` matches the full Discogs description
    ``'30th Anniversary Edition'``, and the *full description string* is
    returned so that the specific wording appears in the directory name.

    The first description in the list that matches any pattern wins.
    """
    patterns = [p.lower() for p in format_codes.get('editions', [])]
    for desc in (descriptions or []):
        desc_lower = desc.lower()
        if any(pat in desc_lower for pat in patterns):
            return desc   # full Discogs string, not the pattern
    return ''


def compute_format_code(format_name: str,
                        descriptions: list,
                        disctotal: int,
                        format_codes: dict) -> str:
    """Return the physical format code for a release.

    Produces the physical medium abbreviation and multi-disc quantity prefix.
    Release type (Single, EP, Compilation) and edition qualifiers are NOT
    encoded here — use ``%releasetype%`` and ``%edition%`` in format strings
    to include those dimensions independently.

    Parameters
    ----------
    format_name:
        The format name, e.g. ``"Vinyl"``, ``"CD"``, ``"Digital Media"``.
    descriptions:
        Format descriptions list (used for vinyl size override only).
    disctotal:
        Total number of physical discs/records.
    format_codes:
        Rules dict as returned by ``load_format_codes()``.

    Returns
    -------
    str
        Examples: ``"CD"``, ``"LP"``, ``"7″"``, ``"DCD"``, ``"3xLP"``, ``"file"``.
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

    # ── Step 3: quantity prefix ───────────────────────────────────────────────
    # Multi-disc quantity is still a physical property worth encoding.
    # D (double), 3x, 4x, etc.
    code = base
    qty = int(disctotal or 1)
    if qty > 1:
        aliases = format_codes.get('quantity_aliases', {})
        qty_fmt = format_codes.get('quantity_format', '{n}x')
        qty_str = str(aliases.get(qty, qty_fmt.replace('{n}', str(qty))))
        code = qty_str + code

    return code


def compute_release_types(
    format_name: str,
    descriptions: list,
    is_compilation: bool,
    format_codes: dict,
) -> tuple:
    """Infer MusicBrainz-style release types from Discogs format data.

    Returns
    -------
    (primary_type, secondary_types)
        primary_type   — str, e.g. "Album", "Single", "EP"
        secondary_types — list[str], e.g. ["Compilation", "Live"]

    The mapping is driven by the ``release_type_map`` section of
    ``format_codes.yaml`` so users can extend it without code changes.

    Discogs mixes release-type information ("Single", "Compilation") with
    physical-edition information ("Limited Edition", "Gatefold") in the same
    descriptions list.  This function extracts only the type-relevant entries.
    """
    rtm = format_codes.get('release_type_map', {})
    primary_map = {k.lower(): v for k, v in rtm.get('primary', {}).items()}
    secondary_map = {k.lower(): v for k, v in rtm.get('secondary', {}).items()}
    fn_primary_map = {k.lower(): v for k, v in rtm.get('format_name_primary', {}).items()}

    # Default primary type
    primary = 'Album'

    # Check format name first (e.g. 7" vinyl → Single)
    if format_name.lower() in fn_primary_map:
        primary = fn_primary_map[format_name.lower()]
    else:
        # Check descriptions for primary type override
        for desc in (descriptions or []):
            if desc.lower() in primary_map:
                primary = primary_map[desc.lower()]
                break   # first match wins

    # Collect secondary types (all that match)
    secondary: list[str] = []
    seen: set[str] = set()
    for desc in (descriptions or []):
        mb_type = secondary_map.get(desc.lower())
        if mb_type and mb_type not in seen:
            secondary.append(mb_type)
            seen.add(mb_type)

    # is_compilation ensures "Compilation" appears even when not in descriptions
    if is_compilation and 'Compilation' not in seen:
        secondary.insert(0, 'Compilation')

    return primary, secondary
