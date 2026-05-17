"""Shared constants and small utilities used across the discogstagger package."""
import re

# Positions whose prefix indicates a non-audio disc type to skip.
_MEDIA_EXCLUDE = ('Video', 'video', 'DVD')

# Audio file extensions used for directory discovery and file scanning.
# This is the authoritative set — use it everywhere rather than inline tuples.
AUDIO_EXTENSIONS = ('.flac', '.mp3', '.ape', '.wav', '.wv')

# Artist name variants that indicate a Various-Artists compilation.
VARIOUS_ARTIST_NAMES = frozenset({'various', 'various artists', 'va'})

_DISCOGS_ID_SUFFIX_RE = re.compile(r'\s*\(\d+\)\s*$')


def build_flat_tracklist(tracklist) -> list:
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
        if pos and (pos.startswith(_MEDIA_EXCLUDE) or pos.endswith(_MEDIA_EXCLUDE)):
            continue           # Video / DVD track

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
