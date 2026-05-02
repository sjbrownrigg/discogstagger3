#!/usr/bin/env python3
"""Report FLAC files where artist and albumartist counts differ (split releases)."""
import argparse
import fnmatch
import logging
import os

from mutagen.flac import FLAC

logging.basicConfig(filename='multi_discs.log', level=logging.DEBUG)
logger = logging.getLogger(__name__)


def find_files(basepath, pattern):
    base = os.path.expanduser(basepath)
    for root, dirs, files in os.walk(base):
        for filename in fnmatch.filter(files, pattern):
            yield os.path.join(root, filename)


p = argparse.ArgumentParser(description=__doc__)
p.add_argument('-b', '--basedir', required=True,
               help='Base directory to search for FLAC files')
args = p.parse_args()

for filename in find_files(args.basedir, '*.flac'):
    audio = FLAC(filename)
    artist_count = len(audio.get('artist', []))
    albumartist_count = len(audio.get('albumartist', []))

    if artist_count == 1 and albumartist_count > 1:
        logger.debug('multiple albumartists: %s', filename)
        print(filename)
