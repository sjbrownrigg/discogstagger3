"""Shared constants and small utilities used across the discogstagger package."""
import re

# Audio file extensions used for directory discovery and file scanning.
# This is the authoritative set — use it everywhere rather than inline tuples.
AUDIO_EXTENSIONS = ('.flac', '.mp3', '.ape', '.wav', '.wv')

# Artist name variants that indicate a Various-Artists compilation.
VARIOUS_ARTIST_NAMES = frozenset({'various', 'various artists', 'va'})

_DISCOGS_ID_SUFFIX_RE = re.compile(r'\s*\(\d+\)\s*$')


def strip_discogs_id_suffix(name: str) -> str:
    """Remove a Discogs disambiguation suffix from an artist or label name.

    Discogs appends a parenthesised integer to distinguish artists who share
    a name, e.g. 'Goldie (12)' or 'Various (1)'.  This strips that suffix so
    the bare name can be used for matching and display.
    """
    return _DISCOGS_ID_SUFFIX_RE.sub('', name).strip()
