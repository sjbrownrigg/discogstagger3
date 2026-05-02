#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fetch a Discogs release by ID and write the full JSON to disk.

Useful for pre-populating the cache before a batch run, or for inspecting
exactly what data Discogs returns for a given release without running a full
tagging operation.
"""
import argparse
import json
import logging
import os
import sys

import discogs_client

parentdir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parentdir)

from discogstagger.tagger_config import TaggerConfig

logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
logger = logging.getLogger(__name__)

p = argparse.ArgumentParser(description=__doc__,
                            formatter_class=argparse.RawDescriptionHelpFormatter)
p.add_argument('-r', '--releaseid', required=True, help='Discogs release ID')
p.add_argument('-d', '--destination',
               help='Directory to write <id>.json (default: current directory)')
p.add_argument('-c', '--conf', default='conf/default.conf',
               help='discogstagger configuration file')
args = p.parse_args()

cfg = TaggerConfig(args.conf)
user_token = os.environ.get('DISCOGS_USER_TOKEN') or cfg.get('discogs', 'user_token')
user_agent = cfg.get('common', 'user_agent')

if not user_token:
    p.error('No Discogs user token found. '
            'Set user_token in [discogs] or export DISCOGS_USER_TOKEN.')

client = discogs_client.Client(user_agent, user_token=user_token)
logger.info('Fetching release %s from Discogs...', args.releaseid)

release = client.release(int(args.releaseid))
_ = release.title  # trigger the full data fetch before serialising
data = release.data

destdir = os.path.expanduser(args.destination or '.')
out = os.path.join(destdir, '{}.json'.format(args.releaseid))
with open(out, 'w', encoding='utf-8') as fh:
    json.dump(data, fh, ensure_ascii=False, indent=2)

logger.info('Written to %s', out)
