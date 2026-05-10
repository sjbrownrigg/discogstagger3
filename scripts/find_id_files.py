#!/usr/bin/env python3
"""Find all id.txt files under a directory and list their Discogs IDs."""
import argparse
import logging
import os
from configparser import ConfigParser

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def find_files(basepath, name):
    base = os.path.expanduser(basepath)
    for root, dirs, files in os.walk(base):
        if name in files:
            yield os.path.join(root, name)


p = argparse.ArgumentParser(description=__doc__)
p.add_argument('-b', '--basedir', required=True,
               help='Base directory to search for id.txt files')
p.add_argument('-o', '--output', default='local_ids.txt',
               help='Output file to write IDs to (default: local_ids.txt)')
args = p.parse_args()

parser = ConfigParser()
ids = []
for filename in find_files(args.basedir, 'id.txt'):
    parser.read(filename)
    try:
        discogs_id = parser.get('source', 'discogs_id')
        logger.debug('%s → %s', filename, discogs_id)
        ids.append(discogs_id)
    except Exception as e:
        logger.warning('Could not read ID from %s: %s', filename, e)

with open(args.output, 'w') as fh:
    fh.write('\n'.join(ids) + '\n')

logger.info('Found %d ID(s), written to %s', len(ids), args.output)
