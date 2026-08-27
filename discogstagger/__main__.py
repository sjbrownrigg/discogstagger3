# -*- coding: utf-8 -*-
import os
import logging
import logging.config
import sys
import time

from argparse import ArgumentParser
from watchdog.observers.polling import PollingObserver
from watchdog.events import FileSystemEventHandler

from discogstagger.fileutils import FileUtils
from discogstagger.tagger_config import (
    TaggerConfig, extract_sample_section, write_new_config)
from discogstagger import roots
from discogstagger.discogsalbum import DiscogsAlbum, AlbumError
from discogstagger.discogs_connector import DiscogsConnector, LocalDiscogsConnector
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


def _new_config(parser, options):
    """Scaffold a fresh configuration and print what to do next.

    Returns a process exit status: 0 when something was written, 1 when
    everything already existed and nothing was done.
    """
    try:
        written, skipped = write_new_config(
            options.new_config, force=options.force_new_config)
    except OSError as exc:
        parser.error(f"Could not write the new config: {exc}")

    dest = os.path.abspath(os.path.expanduser(options.new_config or '.'))

    for path in written:
        print(f"created  {path}")
    for path in skipped:
        print(f"exists   {path}  (left alone)")

    if not written:
        print(
            "\nNothing written -- every file already exists.\n"
            "  Use --force-new-config to overwrite them, but note that this\n"
            "  discards any credentials and format strings they contain.")
        return 1

    config_path = os.path.join(dest, 'config.yaml')
    print(f"""
Next:

  1. Edit {config_path}
     At minimum set common.source_dir, common.dest_dir, and your Discogs
     token under discogs.user_token.

  2. Run it:
       discogstagger

     That works when the config is in the default location. Elsewhere:
       DISCOGSTAGGER_CONFIG_DIR={dest} discogstagger

Paths inside the config resolve against the config file's own directory, so
'formats.ini' already points at the file written beside it. Move this whole
directory anywhere and it keeps working.

Rule tables and .nfo/.m3u templates were not copied -- leaving them unset uses
the bundled versions, which keep improving with each upgrade. To customise one,
copy it out and point the matching setting at your copy:

  {os.path.join(roots.BUNDLED_CONF, 'format_codes.yaml')}
     -> details.format_codes
  {os.path.join(roots.BUNDLED_CONF, 'char_substitutions.yaml')}
     -> details.char_substitutions
  {roots.BUNDLED_TEMPLATES}/
     -> common.templates_dir
""")
    return 0


def main():
    p = ArgumentParser(
        description='Tag audio files with metadata from Discogs.',
        prog='discogstagger',
    )
    p.add_argument('--version', action='version', version='discogstagger3 3.0')
    p.add_argument('-r', '--releaseid', help='Discogs release ID of the target album')
    p.add_argument('-s', '--source', dest='sourcedir', default=None,
                   help='Directory containing the audio files to tag '
                        '(overrides common.source_dir in config)')
    p.add_argument('-d', '--destination', dest='destdir', default=None,
                   help='Base directory to copy tagged files to '
                        '(overrides common.dest_dir in config)')
    p.add_argument('--new-config', dest='new_config', nargs='?',
                   const=roots.config_dir(), metavar='DIR',
                   help='Write a fresh config.yaml and formats.ini into DIR '
                        'and exit. Defaults to the configuration directory, '
                        'so plain --new-config sets you up where the next run '
                        'will look. Existing files are never overwritten.')
    p.add_argument('--force-new-config', dest='force_new_config',
                   action='store_true',
                   help='With --new-config, overwrite files that already exist. '
                        'This discards credentials and format strings.')
    p.add_argument('--recursive', action='store_true',
                   help='Search source directory recursively for albums')
    p.add_argument('-f', '--force', dest='forceUpdate', action='store_true',
                   help='Re-tag albums even when the done marker already exists')
    p.add_argument('-g', '--replay-gain', dest='replaygain', action='store_true',
                   help='Add ReplayGain tags after tagging')
    p.add_argument('-w', '--watch', action='store_true',
                   help='Watch source directory for new albums (daemon mode)')

    options = p.parse_args()

    # Handled before anything else: the whole point is to work when there is no
    # usable configuration yet.
    if options.new_config is not None:
        return _new_config(p, options)

    options.conffile = roots.discover_config()
    if not options.conffile:
        p.error(
            f"No configuration found at "
            f"{os.path.join(roots.config_dir(), roots.CONFIG_FILENAME)}\n"
            f"  Create one:  discogstagger --new-config\n"
            f"  Or point at an existing configuration directory:\n"
            f"    DISCOGSTAGGER_CONFIG_DIR=/path/to/config discogstagger"
        )

    tagger_config = TaggerConfig(options.conffile)

    # Resolve source directory: -s overrides common.source_dir from config.
    sourcedir = options.sourcedir or tagger_config.get('common', 'source_dir')
    if not sourcedir:
        snippet = extract_sample_section('common')
        msg = (
            "No source directory specified — use -s or set common.source_dir in your config.\n"
            f"  See {options.conffile} (section 'common')."
        )
        if snippet:
            msg += "\n\n" + '\n'.join("  " + l.rstrip() for l in snippet.splitlines())
        p.error(msg)
    sourcedir = os.path.expanduser(sourcedir)
    if not os.path.exists(sourcedir):
        p.error("Source directory does not exist: '{}'".format(sourcedir))
    options.sourcedir = os.path.abspath(sourcedir)

    # Resolve destination directory: -d overrides common.dest_dir from config.
    destdir = options.destdir or tagger_config.get('common', 'dest_dir')
    if destdir:
        destdir = os.path.expanduser(destdir)
        options.destdir = os.path.abspath(destdir)
    else:
        options.destdir = None

    tagger_config.set('details', 'source_dir', options.sourcedir)

    _bundled_log_conf = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "conf", "logger_default.conf")
    logger_config_file = tagger_config.get("logging", "config_file") or _bundled_log_conf
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
    options.searchDiscogs = tagger_config.get('batch', 'searchdiscogs')

    file_utils = FileUtils(tagger_config, options)

    def get_source_dirs():
        if options.recursive:
            logger.debug("determine sourcedirs")
            source_dirs = file_utils.walk_dir_tree(options.sourcedir, id_file)
        elif options.searchDiscogs:
            # Combine id-file discovery with audio-dir discovery so that box
            # sets (where id.txt lives in a parent directory with audio files
            # in subdirectories) are processed as a whole rather than as
            # individual per-disc directories.
            #
            # Priority: directories with id.txt always win.  Audio directories
            # are included only when none of their ancestors has an id.txt.
            id_dirs = file_utils.walk_dir_tree(options.sourcedir, id_file)
            id_dir_set = set(id_dirs)
            audio_dirs = file_utils.get_audio_dirs(options.sourcedir)
            # Keep an audio dir only if no ancestor is already covered by id.txt
            orphan_audio = [
                d for d in audio_dirs
                if not any(
                    d == id_d or d.startswith(id_d + os.sep)
                    for id_d in id_dir_set
                )
            ]
            source_dirs = id_dirs + orphan_audio
            if id_dirs:
                logger.debug('%d id-file dir(s) found, %d additional audio-only dir(s)',
                             len(id_dirs), len(orphan_audio))
        else:
            logger.debug("using sourcedir: %s", options.sourcedir)
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
                    try:
                        release = discogs_search.search_discogs()
                        if release is not None:
                            # Accessing tracklist triggers a lazy API fetch —
                            # catch 404 in case the release was deleted since
                            # it appeared in search results.
                            _ = release.tracklist
                            releaseid = release.id
                            connector = discogs_connector
                    except Exception as search_ex:
                        logger.warning(
                            'Discogs search/fetch failed for %s (%s) — '
                            'skipping. Add an id.txt to tag manually.',
                            source_dir, search_ex
                        )
                        release = None

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

                _use_anv = cfg.getboolean('details', 'use_anv') if cfg.has_option('details', 'use_anv') else True
                discogs_album = DiscogsAlbum(release, use_anv=_use_anv)

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
            logger.info("Converted %d/%d", converted_discs, len(source_dirs))

        logger.info("Tagging complete.")
        logger.info("converted successful: %d", converted_discs)
        logger.info("converted with Errors %d", len(discs_with_errors))
        logger.info("releases touched: %d", len(source_dirs))

        if discs_with_errors:
            logger.error("The following discs could not get converted.")
            for msg in discs_with_errors:
                logger.error(msg)

    class MyHandler(FileSystemEventHandler):
        def on_modified(self, event):
            logger.debug("watch event: %s  path: %s", event.event_type, event.src_path)
            waitfor = DirectoryWatcher()
            waitfor.watch(options.sourcedir)
            logger.debug("source directory stable — starting tagging run")
            source_dirs = get_source_dirs()
            if source_dirs:
                process_source_dirs(source_dirs, tagger_config)

    if options.watch:
        poll_interval = int(tagger_config.get('common', 'watch_poll_interval') or 30)
        logger.info("Daemon mode — polling every %d s (PollingObserver, CIFS-safe)", poll_interval)
        event_handler = MyHandler()
        observer = PollingObserver(timeout=poll_interval)
        observer.schedule(event_handler, path=options.sourcedir, recursive=False)
        observer.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Daemon mode stopping.")
            observer.stop()
        observer.join()
    else:
        source_dirs = get_source_dirs()
        if source_dirs:
            process_source_dirs(source_dirs, tagger_config)


if __name__ == "__main__":
    main()
