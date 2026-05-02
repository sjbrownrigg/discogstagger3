#!/usr/bin/env python3
"""Migrate old-style id.txt files (bare discogs_id=X) to the sectioned format.

Old format:
    discogs_id=12345

New format:
    [source]
    discogs_id=12345
"""
import argparse
import logging
import os
import shutil

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

MARKER = '#migrated by migrate_id_files'


def find_id_files(basepath):
    base = os.path.expanduser(basepath)
    for root, dirs, files in os.walk(base):
        if 'id.txt' in files:
            yield os.path.join(root, 'id.txt')


def migrate(path):
    with open(path, 'r') as fh:
        content = fh.read()

    if MARKER in content:
        logger.debug('already migrated: %s', path)
        return False

    if 'discogs_id=' not in content:
        logger.debug('no discogs_id found in %s', path)
        return False

    backup = path + '.orig'
    shutil.copyfile(path, backup)
    logger.debug('backed up to %s', backup)

    new_content = content.replace(
        'discogs_id=',
        '{}\n[source]\ndiscogs_id='.format(MARKER),
        1,
    )
    with open(path, 'w') as fh:
        fh.write(new_content)

    logger.info('migrated %s', path)
    return True


p = argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter)
p.add_argument('-b', '--basedir', required=True,
               help='Base directory to search for id.txt files')
args = p.parse_args()

migrated = sum(migrate(f) for f in find_id_files(args.basedir))
logger.info('Migrated %d file(s)', migrated)
