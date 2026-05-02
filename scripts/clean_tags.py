#!/usr/bin/env python3
"""Remove legacy/duplicate FLAC tags and normalise DISCOGSID storage."""
import argparse
import fnmatch
import logging
import os
import subprocess

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

TAGS_TO_REMOVE = [
    'TRACK', 'TRACKC', 'TOTALTRACKS',
    'DISC', 'DISCC', 'TOTALDISCS',
    'ALBUM ARTIST', 'PUBLISHER', 'ENCODEDBY',
    'DESCRIPTION', 'URL', 'URLTAG',
]


def find_files(basepath, pattern):
    base = os.path.expanduser(basepath)
    for root, dirs, files in os.walk(base):
        for filename in fnmatch.filter(files, pattern):
            yield os.path.join(root, filename)


p = argparse.ArgumentParser(description=__doc__)
p.add_argument('-b', '--basedir', required=True,
               help='Base directory to search for FLAC files')
args = p.parse_args()

from mutagen.flac import FLAC

updated = []
for filename in find_files(args.basedir, '*.flac'):
    logger.debug('processing %s', filename)
    audio = FLAC(filename)

    cmd = ['metaflac', '--preserve-modtime']
    for tag in TAGS_TO_REMOVE:
        cmd.append('--remove-tag={}'.format(tag))

    if 'discogs_id' in audio:
        discogs_id = ''.join(str(e) for e in audio['discogs_id'])
        cmd += [
            '--remove-tag=discogs_id',
            '--set-tag=DISCOGSID={}'.format(discogs_id),
            '--set-tag=URL_DISCOGS_RELEASE_SITE=https://www.discogs.com/release/{}'.format(discogs_id),
        ]

    cmd.append(filename)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error('metaflac failed on %s: %s', filename, result.stderr.strip())
    else:
        updated.append(filename)

logger.info('Cleaned %d file(s)', len(updated))
