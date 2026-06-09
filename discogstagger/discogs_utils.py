"""Shared constants and small utilities used across the discogstagger package."""
import re

# Discogs role strings that map to the 'composer' tag.
# Matched case-insensitively after stripping parenthetical notes.
COMPOSER_ROLES = frozenset({
    'composed by', 'music by', 'written-by', 'written by',
    'composer', 'music, words by', 'music and lyrics by', 'music & lyrics by',
    'music by, words by',
})

# Discogs role strings that map to the 'lyricist' tag.
LYRICIST_ROLES = frozenset({
    'lyrics by', 'words by', 'lyricist', 'text by',
})

_ROLE_SUFFIX_RE = re.compile(r'\s*[\[\(].*?[\]\)]\s*')

# Position prefixes that indicate a non-audio disc type (DVD, Blu-ray, VHS …).
# Used by build_flat_tracklist() and is_non_audio_position().
_NON_AUDIO_PREFIXES = frozenset({
    'dvd', 'bd', 'blu-ray', 'bluray', 'vhs', 'umd', 'video',
})


def is_non_audio_position(pos: str) -> bool:
    """Return True when a Discogs track position indicates a non-audio disc.

    Matches positions like 'DVD-1', 'DVD1-3', 'BD-3', 'VHS-2', 'Video-1'
    against a known set of non-audio medium prefixes.  Bare labels ('DVD')
    and disc-numbered variants ('DVD1', 'DVD2-5') are all matched.
    Unknown or empty positions return False so they are always included
    rather than silently dropped.
    """
    if not pos:
        return False
    p = pos.lower()
    for prefix in _NON_AUDIO_PREFIXES:
        if p == prefix:
            return True
        if not p.startswith(prefix):
            continue
        # prefix must be followed by a separator or disc digit, not another letter
        rest = p[len(prefix):]
        if rest and (rest[0] in '-_ ' or rest[0].isdigit()):
            return True
    return False

def natural_sort_key(s: str) -> list:
    """Sort key treating numeric substrings numerically rather than lexicographically.

    Ensures multi-disc directories like 'Disc 2' sort before 'Disc 10'.
    Use as the ``key`` argument to ``list.sort()`` or ``sorted()``.
    """
    return [int(part) if part.isdigit() else part.lower()
            for part in re.split(r'(\d+)', s)]


# All audio extensions recognised for directory discovery.
# A directory containing any of these triggers inclusion in the scan.
AUDIO_EXTENSIONS = ('.flac', '.mp3', '.ogg', '.ape', '.wav', '.wv', '.m4a')

# Subset of AUDIO_EXTENSIONS that can be tagged in place.
# Formats NOT in this set (currently .wav) must be converted to a taggable
# format first — writing tags to them is either unsupported or unreliable
# (e.g. WAV ID3 chunks are ignored by most media players).
TAGGABLE_EXTENSIONS = ('.flac', '.mp3', '.ogg', '.ape', '.wv', '.m4a')

# Artist name variants that indicate a Various-Artists compilation.
VARIOUS_ARTIST_NAMES = frozenset({'various', 'various artists', 'va'})

_DISCOGS_ID_SUFFIX_RE = re.compile(r'\s*\(\d+\)\s*$')


def build_flat_tracklist(tracklist, skip_non_audio: bool = True) -> list:
    """Flatten a Discogs tracklist into one dict per physical file.

    Applies the same Pattern A / Pattern B logic used by DiscogsAlbum when
    building the disc/track model for tagging, so that search matching sees
    exactly the same track count and durations as the tagger expects.

    Pattern A — index entry whose sub_tracks each have an individual duration
        (e.g. a continuous-mix section whose songs were ripped separately).
        Expanded: each sub_track becomes its own entry.

    Pattern B — index entry with a parent duration whose sub_tracks lack
        individual durations (e.g. "Mighty Mix (Part 1)" covering four
        named movements in a single file).
        Collapsed: one entry using the parent title and duration.

    All other headings, bare structural labels and Video/DVD entries are
    skipped.

    Args:
        tracklist: iterable of track objects from python3-discogs-client.
                   Each item exposes .position, .title, .duration and a
                   .data dict containing 'type_' and 'sub_tracks'.

    Returns:
        List of dicts: {'position': str, 'title': str, 'duration': str|None}
    """
    result = []

    for t in tracklist:
        _type = (t.data.get('type_', 'track')
                 if hasattr(t, 'data') else getattr(t, 'type_', 'track'))
        pos   = (t.position or '') if hasattr(t, 'position') else ''
        dur   = (t.duration or '') if hasattr(t, 'duration') else ''
        title = (t.title   or '') if hasattr(t, 'title')    else ''
        subs  = (t.data.get('sub_tracks', [])
                 if hasattr(t, 'data') else [])
        real_subs = [s for s in subs if s.get('type_', '') == 'track']

        # ── Skip structural entries ───────────────────────────────────────
        if _type == 'heading':
            continue
        if skip_non_audio and is_non_audio_position(pos):
            continue

        # ── Pattern A: index container → expand sub_tracks ───────────────
        # Each sub_track is a separately ripped file (they have individual
        # durations).  Only applied when sub_track data is present (full
        # release).  When sub_tracks are absent (lightweight version from
        # master.versions), the entry falls through to single-entry fallback.
        if (_type == 'index' and real_subs and not dur
                and all(s.get('duration', '') for s in real_subs)):
            for sub in real_subs:
                sub_dur = sub.get('duration', '')
                result.append({
                    'position': sub.get('position', ''),
                    'title':    sub.get('title', ''),
                    'duration': sub_dur if sub_dur else None,
                })
            continue

        # ── Pattern B: index with parent duration → single file ───────────
        # The sub_tracks are movements within one file (no individual
        # durations).  Only applied when sub_track data is present.
        if (_type == 'index' and real_subs and dur
                and not any(s.get('duration', '') for s in real_subs)):
            result.append({
                'position': pos,
                'title':    title,
                'duration': dur,
            })
            continue

        # ── Normal track ──────────────────────────────────────────────────
        result.append({
            'position': pos,
            'title':    title,
            'duration': dur if dur else None,
        })

    return result


def strip_discogs_id_suffix(name: str) -> str:
    """Remove a Discogs disambiguation suffix from an artist or label name.

    Discogs appends a parenthesised integer to distinguish artists who share
    a name, e.g. 'Goldie (12)' or 'Various (1)'.  This strips that suffix so
    the bare name can be used for matching and display.
    """
    return _DISCOGS_ID_SUFFIX_RE.sub('', name).strip()


def parse_extraartists(extraartists_data: list) -> dict:
    """Extract role-grouped names from a Discogs extraartists list.

    Each item in extraartists_data is expected to be a dict with at least
    'name', 'anv', and 'role' keys (as returned by the Discogs API).

    Returns a dict:
        {
          'composers': [str, ...],   # 'Composed By', 'Written-By', etc.
          'lyricists': [str, ...],   # 'Lyrics By', 'Words By', etc.
        }

    The ANV (Artist Name Variation) is preferred over the canonical name when
    present.  Role strings are matched case-insensitively after stripping any
    parenthetical or bracketed qualifier (e.g. 'Composed By [Tracks 1-3]'
    → 'composed by').
    """
    result: dict = {'composers': [], 'lyricists': []}
    for ea in (extraartists_data or []):
        anv = (ea.get('anv') or '').strip()
        name = anv or (ea.get('name') or '').strip()
        if not name:
            continue
        role_raw = ea.get('role') or ''
        # Strip bracketed/parenthetical qualifiers: "Composed By [Tracks 1-3]" → "Composed By"
        role = _ROLE_SUFFIX_RE.sub('', role_raw).strip().rstrip(',').strip().lower()
        if role in COMPOSER_ROLES:
            result['composers'].append(name)
        elif role in LYRICIST_ROLES:
            result['lyricists'].append(name)
    return result
