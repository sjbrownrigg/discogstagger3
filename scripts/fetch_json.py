#!/usr/bin/python
# -*- coding: utf-8 -*-
import os
import logging
import logging.config
import sys
import json

from optparse import OptionParser

import discogs_client

parentdir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(parentdir)

from discogstagger.tagger_config import TaggerConfig

p = OptionParser(version="discogstagger 3.0 - json fetcher")
p.add_option("-r", "--releaseid", action="store", dest="releaseid",
             help="The release id of the album")
p.add_option("-d", "--destination", action="store", dest="destdir",
             help="The directory to copy the json file to")
p.add_option("-c", "--conf", action="store", dest="conffile",
             help="The discogstagger configuration file.")

p.set_defaults(conffile="../conf/default.conf")

if len(sys.argv) == 1:
    p.print_help()
    sys.exit(1)

(options, args) = p.parse_args()

if not options.releaseid:
    p.error("Please specify a valid releaseid ('-r')")

tagger_config = TaggerConfig(options.conffile)

# initialize logging
logger_config_file = tagger_config.get("logging", "config_file")
logging.config.fileConfig(logger_config_file)

logger = logging.getLogger(__name__)

user_agent = tagger_config.get("common", "user_agent")
client = discogs_client.Client(user_agent)

# allow authentication to be able to download images (use key and secret from config options)
consumer_key = tagger_config.get("discogs", "consumer_key")
consumer_secret = tagger_config.get("discogs", "consumer_secret")

# allow config override thru env variables
if os.environ.has_key("DISCOGS_CONSUMER_KEY"):
    consumer_key = os.environ.get('DISCOGS_CONSUMER_KEY')
if os.environ.has_key("DISCOGS_CONSUMER_SECRET"):
    consumer_secret = os.environ.get("DISCOGS_CONSUMER_SECRET")

if consumer_key and consumer_secret:
    logger.debug('authenticating at discogs using consumer key {0}'.format(consumer_key))

    client.set_consumer_key(consumer_key, consumer_secret)
else:
    logger.warn('cannot authenticate on discogs (no image download possible) - set consumer_key and consumer_secret')
    sys.exit(1)

client.set_consumer_key(consumer_key, consumer_secret)

secrets_available = False


cwd = os.getcwd()
token_file_name = '.token'
token_file = os.path.join(cwd, token_file_name)

access_token = None
access_secret = None

try:
  if os.path.join(token_file):
    with open(token_file, 'r') as tf:
      access_token, access_secret = tf.read().split(',')
    if access_token and access_secret:
      secrets_available = True
except IOError:
  pass

if not secrets_available:
  request_token, request_token_secret, authorize_url = client.get_authorize_url()

  print 'Visit this URL in your browser: ' + authorize_url
  pin = raw_input('Enter the PIN you got from the above url: ')

  access_token, access_secret = client.get_access_token(pin)

  with open(token_file, 'w') as fh:
    fh.write('{0},{1}'.format(access_token, access_secret))

else:
  client.set_token(unicode(access_token), unicode(access_secret))

url = "{0}/releases/{1}".format(client._base_url, options.releaseid)

release = client._get(url)

target_file = open("{0}.json".format(options.releaseid), "w")
target_file.write(json.dumps(release))
target_file.close()
