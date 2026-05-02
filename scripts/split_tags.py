#!/usr/bin/env python3
"""Split multi-value FLAC tags that were stored with \\ as a separator.

Also normalises known genre name variants (e.g. Hip-Hop → Hip Hop).
"""
import argparse
import fnmatch
import logging
import os

from mutagen.flac import FLAC

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

GENRE_FIXES = {
    'Hip-Hop': 'Hip Hop',
    'Folk, World, & Country': 'Folk, World & Country',
}


def split_tag(values):
    """Split any values that contain \\\\ and return a flat list."""
    result = []
    for v in values:
        if '\\\\' in v:
            result.extend(v.split('\\\\'))
        else:
            result.append(v)
    return result


def find_files(basepath, pattern):
    base = os.path.expanduser(basepath)
    for root, dirs, files in os.walk(base):
        for filename in fnmatch.filter(files, pattern):
            yield os.path.join(root, filename)


p = argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter)
p.add_argument('-b', '--basedir', required=True,
               help='Base directory to search for FLAC files')
args = p.parse_args()

updated = []
for filename in find_files(args.basedir, '*.flac'):
    audio = FLAC(filename)
    dirty = False

    for tag in ('genre', 'artist', 'album artist', 'albumartist'):
        if tag not in audio:
            continue
        original = audio[tag]
        split = split_tag(original)
        if split != original:
            audio[tag.upper()] = split
            dirty = True

    # Normalise genre names
    if 'genre' in audio:
        fixed = [GENRE_FIXES.get(g, g) for g in audio['genre']]
        if fixed != audio['genre']:
            audio['GENRE'] = fixed
            dirty = True

    if dirty:
        audio.save()
        updated.append(filename)
        logger.debug('updated %s', filename)

logger.info('Updated %d file(s)', len(updated))
