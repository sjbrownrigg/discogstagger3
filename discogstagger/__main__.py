# -*- coding: utf-8 -*-
import os
import logging
import logging.config
import sys
import time

from argparse import ArgumentParser
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from discogstagger.fileutils import FileUtils
from discogstagger.tagger_config import TaggerConfig
from discogstagger.discogsalbum import DiscogsAlbum, DiscogsConnector, LocalDiscogsConnector, AlbumError
from discogstagger.discogs_search import DiscogsSearch
from discogstagger.taggerutils import TaggerUtils, TagHandler, FileHandler, TaggerError


class DirectoryWatcher:

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


def main():
    p = ArgumentParser(
        description='Tag audio files with metadata from Discogs.',
        prog='discogstagger',
    )
    p.add_argument('--version', action='version', version='discogstagger3 3.0')
    p.add_argument('-r', '--releaseid', help='Discogs release ID of the target album')
    p.add_argument('-s', '--source', dest='sourcedir', required=True,
                   help='Directory containing the audio files to tag')
    p.add_argument('-d', '--destination', dest='destdir',
                   help='Base directory to copy tagged files to')
    p.add_argument('-c', '--conf', dest='conffile', default='conf/default.conf',
                   help='discogstagger configuration file')
    p.add_argument('--recursive', action='store_true',
                   help='Search source directory recursively for albums')
    p.add_argument('-f', '--force', dest='forceUpdate', action='store_true',
                   help='Re-tag albums even when the done marker already exists')
    p.add_argument('-g', '--replay-gain', dest='replaygain', action='store_true',
                   help='Add ReplayGain tags after tagging')
    p.add_argument('-w', '--watch', action='store_true',
                   help='Watch source directory for new albums (daemon mode)')

    options = p.parse_args()

    if not os.path.exists(options.sourcedir):
        p.error("Source directory does not exist: '{}'".format(options.sourcedir))
    options.sourcedir = os.path.abspath(options.sourcedir)

    if options.destdir and os.path.exists(options.destdir):
        options.destdir = os.path.abspath(options.destdir)

    tagger_config = TaggerConfig(options.conffile)
    tagger_config.set('details', 'source_dir', options.sourcedir)

    logger_config_file = tagger_config.get("logging", "config_file")
    logging.config.fileConfig(logger_config_file, disable_existing_loggers=False)

    # Filenames on Linux can contain bytes that aren't valid UTF-8 (e.g. latin-1
    # encoded names).  Python represents these as surrogate code points via
    # surrogateescape, but logging streams reject them when encoding to UTF-8.
    # Reconfigure every handler's stream to replace unencodable characters rather
    # than raising so that a badly-named file never silently aborts a tagging run.
    for _handler in logging.root.handlers:
        _stream = getattr(_handler, 'stream', None)
        if _stream is not None and hasattr(_stream, 'reconfigure'):
            try:
                _stream.reconfigure(errors='backslashreplace')
            except Exception:
                pass

    logger = logging.getLogger(__name__)

    id_file = tagger_config.get("batch", "id_file")
    options.searchDiscogs = tagger_config.get('batch', 'searchDiscogs')

    file_utils = FileUtils(tagger_config, options)

    def get_source_dirs():
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

    def process_source_dirs(source_dirs, cfg):
        discogs_connector = DiscogsConnector(cfg)
        local_discogs_connector = LocalDiscogsConnector(discogs_connector)
        discogs_search = DiscogsSearch(cfg)

        logger.info("start tagging")
        discs_with_errors = []
        converted_discs = 0

        for source_dir in source_dirs:
            releaseid = None
            release = None
            connector = None

            try:
                done_file = cfg.get("details", "done_file")
                done_file_path = os.path.join(source_dir, done_file)

                if os.path.exists(done_file_path) and not options.forceUpdate:
                    logger.warning('Do not read {}, because {} exists and forceUpdate is false'.format(source_dir, done_file))
                    continue

                cfg = TaggerConfig(options.conffile)

                if options.releaseid is not None:
                    releaseid = options.releaseid
                else:
                    releaseid = file_utils.read_id_file(source_dir, id_file, options)

                if not releaseid:
                    discogs_search.getSearchParams(source_dir)
                    release = discogs_search.search_discogs()
                    if release is not None and hasattr(release, "tracklist"):
                        releaseid = release.id
                        connector = discogs_connector

                if not releaseid:
                    logger.warning('No releaseid for {}'.format(source_dir))
                    continue

                logger.info('Found release ID: {} for source dir: {}'.format(releaseid, source_dir))

                if not options.destdir:
                    destdir = source_dir
                else:
                    destdir = options.destdir
                    logger.debug('destdir set to {}'.format(options.destdir))

                logger.info('Using destination directory: {}'.format(destdir))

                if releaseid is not None and release is None:
                    if cfg.get("source", "name") == "local":
                        release = local_discogs_connector.fetch_release(releaseid, source_dir)
                        connector = local_discogs_connector
                    else:
                        release = discogs_connector.fetch_release(releaseid)
                        connector = discogs_connector

                discogs_album = DiscogsAlbum(release)

                try:
                    album = discogs_album.map()
                    # Cache the fully-loaded release data now that map() has
                    # triggered all lazy fetches.  Works for both the search
                    # path (release came from search_discogs) and the known-ID
                    # path (release came from fetch_release).
                    discogs_connector.cache_release(release)
                except AlbumError as ae:
                    msg = "Error during mapping ({0}), {1}: {2}".format(releaseid, source_dir, ae)
                    logger.error(msg)
                    discs_with_errors.append(msg)
                    continue

                logger.info('Tagging album "{} - {}"'.format(album.artist, album.title))

                tag_handler = TagHandler(album, cfg)
                tagger_utils = TaggerUtils(source_dir, destdir, cfg, album)
                file_handler = FileHandler(album, cfg)

                try:
                    tagger_utils._get_target_list()
                except TaggerError as te:
                    msg = "Error during Tagging ({0}), {1}: {2}".format(releaseid, source_dir, te)
                    logger.error(msg)
                    discs_with_errors.append(msg)
                    continue

                # Gather quality metrics from source files before copy/move
                tagger_utils.gather_addional_properties()
                album.target_dir = tagger_utils.dest_dir_name

                # Copy (or move) untagged source files to destination first so
                # that the originals are never modified.  Tag the copies.
                file_handler.copy_files()
                tag_handler.tag_album()

                # -g/--replay-gain forces ReplayGain on even when add_tags=False
                # in the config; otherwise the config value controls it.
                if options.replaygain:
                    file_handler.rg_process = True
                file_handler.add_replay_gain_tags()

                file_handler.copy_other_files()
                file_handler.get_images(connector)
                file_handler.embed_coverart_album()
                tagger_utils.create_m3u(album.target_dir)
                tagger_utils.create_nfo(album.target_dir)
                file_handler.create_done_file()

            except Exception as ex:
                if releaseid:
                    msg = "Error during tagging ({0}), {1}: {2}".format(releaseid, source_dir, ex)
                else:
                    msg = "Error during tagging (no relid) {0}: {1}".format(source_dir, ex)
                logger.error(msg, exc_info=True)
                discs_with_errors.append(msg)
                continue

            converted_discs += 1
            logger.info("Converted %d/%d" % (converted_discs, len(source_dirs)))

        logger.info("Tagging complete.")
        logger.info("converted successful: %d" % converted_discs)
        logger.info("converted with Errors %d" % len(discs_with_errors))
        logger.info("releases touched: %s" % len(source_dirs))

        if discs_with_errors:
            logger.error("The following discs could not get converted.")
            for msg in discs_with_errors:
                logger.error(msg)

    class MyHandler(FileSystemEventHandler):
        def on_modified(self, event):
            print(f'event type: {event.event_type}  path : {event.src_path}')
            waitfor = DirectoryWatcher()
            waitfor.watch(options.sourcedir)
            print('Finished')
            source_dirs = get_source_dirs()
            if source_dirs:
                process_source_dirs(source_dirs, tagger_config)

    if options.watch:
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
        source_dirs = get_source_dirs()
        if source_dirs:
            process_source_dirs(source_dirs, tagger_config)


if __name__ == "__main__":
    main()
