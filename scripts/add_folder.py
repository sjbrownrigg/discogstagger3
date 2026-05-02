#!/usr/bin/env python3
"""Add a FOLDER tag to FLAC files, grouping them by albumartist or album."""
import argparse
import fnmatch
import logging
import os

from mutagen.flac import FLAC

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def find_files(basepath, pattern):
    base = os.path.expanduser(basepath)
    for root, dirs, files in os.walk(base):
        for filename in fnmatch.filter(files, pattern):
            yield os.path.join(root, filename)


p = argparse.ArgumentParser(description=__doc__)
p.add_argument('-b', '--basedir', required=True,
               help='Base directory to search for FLAC files')
p.add_argument('-f', '--force', dest='forceUpdate', action='store_true',
               help='Overwrite existing FOLDER tags')
args = p.parse_args()

updated = []
for filename in find_files(args.basedir, '*.flac'):
    audio = FLAC(filename)

    if 'folder' in audio:
        if args.forceUpdate:
            logger.debug('removing existing FOLDER tag from %s', filename)
            del audio['folder']
        else:
            continue

    folder = ''
    if 'albumartist' in audio:
        folder = audio['album'][0] if audio['albumartist'][0] == 'Various' else audio['albumartist'][0]

    if 'album' in audio:
        album = audio['album'][0]
        for prefix, tag in (('DJ Kicks', 'DJ Kicks'),
                            ('DJ-Kicks', 'DJ Kicks'),
                            ('Another LateNight', 'Another LateNight'),
                            ('LateNight', 'Another LateNight')):
            if album.startswith(prefix):
                folder = tag
                break

    logger.debug('setting FOLDER=%s on %s', folder, filename)
    audio['FOLDER'] = folder
    audio.save()
    updated.append(filename)

logger.info('Updated %d file(s)', len(updated))
