#!/usr/bin/python3
# -*- coding: utf-8 -*-
import os
import errno
import logging
import logging.config
import sys

import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

import pprint
pp = pprint.PrettyPrinter(indent=4)

from optparse import OptionParser
# import pysplitcue

from discogstagger.fileutils import FileUtils
from discogstagger.tagger_config import TaggerConfig
from discogstagger.discogsalbum import DiscogsAlbum, DiscogsConnector, LocalDiscogsConnector, AlbumError, DiscogsSearch
from discogstagger.taggerutils import TaggerUtils, TagHandler, FileHandler, TaggerError

p = OptionParser(version="discogstagger3 3.0")
p.add_option("-r", "--releaseid", action="store", dest="releaseid",
             help="The release id of the target album")
p.add_option("-s", "--source", action="store", dest="sourcedir",
             help="The directory that you wish to tag")
p.add_option("-d", "--destination", action="store", dest="destdir",
             help="The (base) directory to copy the tagged files to")
p.add_option("-c", "--conf", action="store", dest="conffile",
             help="The discogstagger configuration file.")
p.add_option("--recursive", action="store_true", dest="recursive",
             help="Should albums be searched recursive in the source directory?")
p.add_option("-f", "--force", action="store_true", dest="forceUpdate",
             help="Should albums be updated even though the done token exists?")
p.add_option("-g", "--replay-gain", action="store_true", dest="replaygain",
             help="Should replaygain tags be added to the album? (metaflac needs to be installed)")
p.add_option("-w", "--watch", action="store_true", dest="watch",
             help="Watches for changes in the source directory (daemon mode)")

p.set_defaults(conffile="conf/default.conf")
p.set_defaults(recursive=False)
p.set_defaults(forceUpdate=False)
p.set_defaults(replaygain=False)

if len(sys.argv) == 1:
    p.print_help()
    sys.exit(1)

(options, args) = p.parse_args()

if not options.sourcedir or not os.path.exists(options.sourcedir):
    p.error("Please specify a valid source directory ('-s')")
else:
    options.sourcedir = os.path.abspath(options.sourcedir)

if options.destdir and os.path.exists(options.destdir):
    options.destdir = os.path.abspath(options.destdir)

tagger_config = TaggerConfig(options.conffile)
# options.replaygain = tagger_config.get("batch", "replaygain")
tagger_config.set('details', 'source_dir', options.sourcedir)
# initialize logging
logger_config_file = tagger_config.get("logging", "config_file")
logging.config.fileConfig(logger_config_file)

logger = logging.getLogger(__name__)

# read necessary config options for batch processing
id_file = tagger_config.get("batch", "id_file")
options.searchDiscogs = tagger_config.get('batch', 'searchDiscogs')
# options.parse_cue_files = tagger_config.get('cue', 'parse_cue_files')

file_utils = FileUtils(tagger_config, options)

def getSourceDirs():
    source_dirs = None
    if options.recursive:
        logger.debug("determine sourcedirs")
        source_dirs = file_utils.walk_dir_tree(options.sourcedir, id_file)
    elif options.searchDiscogs:
        logger.debug("looking for audio files")
        source_dirs = file_utils.get_audio_dirs(options.sourcedir)
    else:
        logger.debug("using sourcedir: %s" % options.sourcedir)
        source_dirs = [options.sourcedir]
    logger.info('Found {} audio source directories to process'.format(len(source_dirs)))
    return source_dirs


def processSourceDirs(source_dirs, tagger_config):
    # initialize connection (could be a problem if using multiple sources...)
    discogs_connector = DiscogsConnector(tagger_config)
    local_discogs_connector = LocalDiscogsConnector(discogs_connector)
    # try to re-use search, may be useful if working with several releases by the same artist
    discogsSearch = DiscogsSearch(tagger_config)

    logger.info("start tagging")
    discs_with_errors = []

    converted_discs = 0

    for source_dir in source_dirs:
        releaseid = None
        release = None
        connector = None

        try:
            done_file = tagger_config.get("details", "done_file")
            done_file_path = os.path.join(source_dir, done_file)

            if os.path.exists(done_file_path) and not options.forceUpdate:
                logger.warn('Do not read {}, because {} exists and forceUpdate is false'.format(source_dir, done_file))
                continue

            # reread config to make sure, that the album specific options are reset for each
            # album
            tagger_config = TaggerConfig(options.conffile)

            if options.releaseid is not None:
                releaseid = options.releaseid
            else:
                releaseid = file_utils.read_id_file(source_dir, id_file, options)

            if not releaseid:
                searchParams = discogsSearch.getSearchParams(source_dir)
                # release = discogsSearch.search_discogs(searchParams)
                release = discogsSearch.search_discogs()
                # reuse the Discogs Release class, it saves re-fetching later
                if release is not None and type(release).__name__ in ('Release', 'Version'):
                    releaseid = release.id
                    connector = discogs_connector

            if not releaseid:
                logger.warn('No releaseid for {}'.format(source_dir))
                continue

            # if not releaseid:
            #     p.error("Please specify the discogs.com releaseid ('-r')")

            logger.info('Found release ID: {} for source dir: {}'.format(releaseid, source_dir))

            # read destination directory
            # !TODO if both are the same, we are not copying anything,
            # this should be "configurable"
            if not options.destdir:
                destdir = source_dir
            else:
                destdir = options.destdir
                logger.debug('destdir set to {}'.format(options.destdir))

            logger.info('Using destination directory: {}'.format(destdir))
            logger.debug("starting tagging...")


            if releaseid is not None and release is None:
                #! TODO this is dirty, refactor it to be able to reuse it for later enhancements
                if tagger_config.get("source", "name") == "local":
                    release = local_discogs_connector.fetch_release(releaseid, source_dir)
                    connector = local_discogs_connector
                else:
                    release = discogs_connector.fetch_release(releaseid)
                    connector = discogs_connector

            discogs_album = DiscogsAlbum(release)

            try:
                album = discogs_album.map()
            except AlbumError as ae:
                msg = "Error during mapping ({0}), {1}: {2}".format(releaseid, source_dir, ae)
                logger.error(msg)
                discs_with_errors.append(msg)
                continue

            logger.info('Tagging album "{} - {}"'.format(album.artist, album.title))

            tagHandler = TagHandler(album, tagger_config)

            taggerUtils = TaggerUtils(source_dir, destdir, tagger_config, album)

            fileHandler = FileHandler(album, tagger_config)

            try:
                taggerUtils._get_target_list()
            except TaggerError as te:
                msg = "Error during Tagging ({0}), {1}: {2}".format(releaseid, source_dir, te)
                logger.error(msg)
                discs_with_errors.append(msg)
                continue

            tagHandler.tag_album()
            taggerUtils.gather_addional_properties()
            # reset the target directory now that we have discogs metadata and
            #  filedata - otherwise this is declared too early in the process
            album.target_dir = taggerUtils.dest_dir_name

            fileHandler.copy_files()

            logger.debug("Tagging files")

            # Do replaygain analysis before copying other files, the directory
            #  contents are cleaner, less prone to mistakes
            if options.replaygain:
                logger.debug("Add ReplayGain tags (if requested)")
                fileHandler.add_replay_gain_tags()

            logger.debug("Copy other interesting files (on request)")
            fileHandler.copy_other_files()

            logger.debug("Downloading and storing images")
            fileHandler.get_images(connector)

            logger.debug("Embedding Albumart")
            fileHandler.embed_coverart_album()

        # !TODO make this more generic to use different templates and files,
        # furthermore adopt to reflect multi-disc-albums
            logger.debug("Generate m3u")
            taggerUtils.create_m3u(album.target_dir)

            logger.debug("Generate nfo")
            taggerUtils.create_nfo(album.target_dir)

            fileHandler.create_done_file()
        except Exception as ex:
            if releaseid:
                msg = "Error during tagging ({0}), {1}: {2}".format(releaseid, source_dir, ex)
            else:
                msg = "Error during tagging (no relid) {0}: {1}".format(source_dir, ex)
            logger.error(msg)
            discs_with_errors.append(msg)
            continue

        # !TODO - make this a check during the taggerutils run
        # ensure we were able to map the release appropriately.
        #if not release.tag_map:
        #    logger.error("Unable to match file list to discogs release '%s'" %
        #                  releaseid)
        #    sys.exit()
        converted_discs = converted_discs + 1
        logger.info("Converted %d/%d" % (converted_discs, len(source_dirs)))

    logger.info("Tagging complete.")
    logger.info("converted successful: %d" % converted_discs)
    logger.info("converted with Errors %d" % len(discs_with_errors))
    logger.info("releases touched: %s" % len(source_dirs))

    if discs_with_errors:
        logger.error("The following discs could not get converted.")
        for msg in discs_with_errors:
            logger.error(msg)

def process():
    source_dirs = getSourceDirs()
    if len(source_dirs) > 0:
        processSourceDirs(source_dirs, tagger_config)

class DirectoryWatcher():

    def __init__(self):
        self.total_size = -1

    def dir_size(self, root_dir):
        total_size = -1
        for (dirpath, dirs, files) in os.walk(root_dir):
            for filename in files:
                file_size = os.stat(os.path.join(dirpath, filename)).st_size
                total_size += file_size
        return total_size

    def watch(self, root_dir):
        while self.total_size != self.dir_size(root_dir):
            self.total_size = self.dir_size(root_dir)
            time.sleep(60)
        # return 'Finished function'


class MyHandler(FileSystemEventHandler):
    def on_modified(self, event):
        print(f'event type: {event.event_type}  path : {event.src_path}')
        waitfor = DirectoryWatcher()
        waitfor.watch(options.sourcedir)
        print('Finished')
        process()


if __name__ == "__main__":
    if options.watch == True:
        logger.info('Daemon mode')
        event_handler = MyHandler()
        observer = Observer()
        observer.schedule(event_handler, path=options.sourcedir, recursive=False)
        observer.start()

        try:
            time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()
    else:
        source_dirs = getSourceDirs()
        if len(source_dirs) > 0:
            processSourceDirs(source_dirs, tagger_config)
