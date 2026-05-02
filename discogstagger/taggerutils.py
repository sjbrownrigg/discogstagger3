# -*- coding: utf-8 -*-
import errno
import json
import os
import re
import logging
import shutil
from shutil import copy2, copystat, Error
from datetime import timedelta

from unicodedata import normalize

from mako.template import Template
from mako.lookup import TemplateLookup

from discogstagger.discogsalbum import DiscogsAlbum
from discogstagger.album import Album, Disc, Track
from discogstagger.stringformatting import StringFormatting

from discogstagger.mediafile_ext import MediaFile

logger = logging.getLogger(__name__)

# class TagOpener(FancyURLopener, object):
#
#     version = "discogstagger2"
#
#     def __init__(self, user_agent):
#         self.version = user_agent
#         FancyURLopener.__init__(self)
#

class TaggerError(Exception):
    """ A central exception for all errors happening during the tagging
    """
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)

class TagHandler(object):
    """ Uses the album (taggerutils) and tags all given files using the given
        tags (album)
    """

    def __init__(self, album, tagger_config):
        self.album = album
        self.config = tagger_config

        self.keep_tags = self.config.get("details", "keep_tags")
        self.user_agent = self.config.get("common", "user_agent")
        self.variousartists = self.config.get("details", "variousartists")

    def tag_album(self):
        """ tags all tracks in an album, the filenames are determined using
            the given properties on the tracks
        """
        for disc in self.album.discs:
            # if disc.target_dir != None:
            #     target_folder = os.path.join(self.album.target_dir, disc.target_dir)
            # else:
            #     target_folder = self.album.target_dir
            #
            for track in disc.tracks:
                path, file = os.path.split(track.full_path)
                self.tag_single_track(path, track)

    def tag_single_track(self, target_folder, track):
        # load metadata information
        logger.debug("target_folder: %s" % target_folder)

        metadata = MediaFile(os.path.join(target_folder, track.orig_file))

        # read already existing (and still wanted) properties
        keepTags = {}
        if self.keep_tags is not None:
            for name in self.keep_tags.split(","):
                logger.debug("name %s" % name)
                if getattr(metadata, name):
                    keepTags[name] = getattr(metadata, name)

        # remove current metadata
        metadata.delete()

        self.album.codec = metadata.type

        # set album metadata
        metadata.album = self.album.title
        metadata.composer = self.album.artist

        # set both singular and plural albumartist fields
        if 'Various' in self.album.artists and self.album.is_compilation == True:
            metadata.albumartist = self.variousartists
            metadata.albumartists = [self.variousartists]
        else:
            metadata.albumartist = self.album.artist
            metadata.albumartists = self.album.artists

# !TODO really, or should we generate this using a specific method?
        metadata.albumartist_sort = self.album.sort_artist

# !TODO should be joined
        metadata.label = self.album.labels[0]

        metadata.year = self.album.year
        metadata.country = self.album.country

        metadata.catalognum = self.album.catnumbers[0] if self.album.catnumbers else ''

        # store styles in the standard grouping tag (joined string)
        metadata.grouping = ', '.join(self.album.styles or [])

        # use genres to allow multiple genres in muliple fields
        metadata.genres = self.album.genres

        # this assumes, that there is a metadata-tag with the id_tag_name in the
        # metadata object
        setattr(metadata, self.config.id_tag_name, self.album.id)
        metadata.discogs_release_url = self.album.url

        metadata.disctitle = track.discsubtitle
        metadata.disc = track.discnumber
        metadata.disctotal = len(self.album.discs)
        metadata.media = self.album.media

        if self.album.is_compilation:
            metadata.comp = True

        if track.notes:
            metadata.comments = '\r\n'.join((track.notes, self.album.notes))
        else:
            metadata.comments = self.album.notes

        tags = self.config.configured_tags
        logger.debug("tags: %s" % tags)
        for name in tags:
            value = self.config.get("tags", name)
            if not value == None:
                setattr(metadata, name, value)

        # set track metadata
        metadata.title = track.title
        metadata.artist = track.artist   # primary artist string (used by most players)
        metadata.artists = track.artists  # full list for players that support multiple artists

# !TODO take care about sortartist ;-)
        metadata.artist_sort = track.sort_artist
        if track.real_tracknumber is not None:
            metadata.track = track.real_tracknumber
        else:
            metadata.track = track.tracknumber

        metadata.tracktotal = len(self.album.disc(track.discnumber).tracks)

        if not keepTags is None:
            for name in keepTags:
                setattr(metadata, name, keepTags[name])

        metadata.save()

class FileHandler(object):
    """ this class contains all file handling tasks for the tagger,
        it loops over the album and discs (see copy_files) to copy
        the files for each album. This could be done in the TagHandler
        class, but this would mean a too strong relationship between
        FileHandling and Tagging, which is not as nice for testing and
        for future extensability.
    """


    def __init__(self, album, tagger_config):
        self.config = tagger_config
        self.album = album
        self.cue_done_dir = self.config.get('cue', 'cue_done_dir')
        self.rg_process = self.config.getboolean('replaygain', 'add_tags')
        self.rg_application = self.config.get('replaygain', 'application')

    def mkdir_p(self, path):
        try:
            os.makedirs(path)
        except OSError as exc: # Python >2.5
            if exc.errno == errno.EEXIST and os.path.isdir(path):
                pass
            else: raise

    def create_done_file(self):
        # could be, that the directory does not exist anymore ;-)
        if os.path.exists(self.album.sourcedir):
            done_file = os.path.join(self.album.sourcedir, self.config.get("details", "done_file"))
            open(done_file, "w")

    def create_album_dir(self):
        if not os.path.exists(self.album.target_dir):
            self.mkdir_p(self.album.target_dir)

    def copy_files(self):
        """
            copy an album and all its files to the new location, rename those
            files if necessary
        """
        logger.debug("album sourcedir: %s" % self.album.sourcedir)
        logger.debug("album targetdir: %s" % self.album.target_dir)

        for disc in self.album.discs:
            logger.debug("disc.sourcedir: %s" % disc.sourcedir)
            logger.debug("disc.target_dir: %s" % disc.target_dir)

            if disc.sourcedir != None:
                source_folder = os.path.join(self.album.sourcedir, disc.sourcedir)
            else:
                source_folder = self.album.sourcedir

            if disc.target_dir != None:
                target_folder = os.path.join(self.album.target_dir, disc.target_dir)
            else:
                target_folder = self.album.target_dir

            copy_needed = False
            if not source_folder == target_folder:
                if not os.path.exists(target_folder):
                    self.mkdir_p(target_folder)
                copy_needed = True

            for track in disc.tracks:
                logger.debug("source_folder: %s" % source_folder)
                logger.debug("target_folder: %s" % target_folder)
                logger.debug("orig_file: %s" % track.orig_file)
                logger.debug("new_file: %s" % track.new_file)

                source_file = os.path.join(source_folder, track.orig_file)
                target_file = os.path.join(target_folder, track.new_file)

                if copy_needed and not os.path.exists(target_file):
                    if not os.path.exists(source_file):
                        logger.error("Source does not exists")
                        # throw error
                    logger.debug("copying files (%s/%s)", source_folder, track.orig_file)

                    shutil.copyfile(os.path.join(source_folder, track.orig_file),
                        os.path.join(target_folder, track.new_file))

    def remove_source_dir(self):
        """
            remove source directory, if configured as such (see config option
            details:keep_original)
        """
        keep_original = self.config.getboolean("details", "keep_original")
        source_dir = self.album.sourcedir

        logger.debug("keep_original: %s" % keep_original)
        logger.debug("going to remove directory....")
        if not keep_original:
            logger.warning("Deleting source directory '%s'" % source_dir)
            shutil.rmtree(source_dir)

    def copy_other_files(self):
        # copy "other files" on request
        copy_other_files = self.config.getboolean("details", "copy_other_files")

        if copy_other_files:
            logger.info("copying files from source directory")

            if not os.path.exists(self.album.target_dir):
                self.mkdir_p(self.album.target_dir)

            copy_files = self.album.copy_files

            if copy_files != None:

                extf = (self.cue_done_dir)
                copy_files[:] = [f for f in copy_files if f not in extf]

                for fname in copy_files:
                    if os.path.isdir(os.path.join(self.album.sourcedir, fname)):
                        copytree_multi(os.path.join(self.album.sourcedir, fname), os.path.join(self.album.target_dir, fname))
                    else:
                        shutil.copyfile(os.path.join(self.album.sourcedir, fname), os.path.join(self.album.target_dir, fname))

            for disc in self.album.discs:
                copy_files = disc.copy_files

                extf = (self.cue_done_dir)
                copy_files[:] = [f for f in copy_files if f not in extf]

                for fname in copy_files:
                    if not fname.endswith(".m3u"):
                        if disc.sourcedir != None:
                            source_path = os.path.join(self.album.sourcedir, disc.sourcedir)
                        else:
                            source_path = self.album.sourcedir

                        if disc.target_dir != None:
                            target_path = os.path.join(self.album.target_dir, disc.target_dir)
                        else:
                            target_path = self.album.target_dir

                        if not os.path.exists(target_path):
                            self.mkdir_p(target_path)

                        if os.path.isdir(os.path.join(source_path, fname)):
                            copytree_multi(os.path.join(source_path, fname), os.path.join(target_path, fname))
                        else:
                            shutil.copyfile(os.path.join(source_path, fname), os.path.join(target_path, fname))

    def get_images(self, conn_mgr):
        """
            Download and store any available images
            The images are all copied into the album directory, on multi-disc
            albums the first image (mostly folder.jpg) is copied into the
            disc directory also to make it available to mp3 players (e.g. deadbeef)

            we need http access here as well (see discogsalbum), and therefore the
            user-agent
        """
        if self.album.images:
            images = self.album.images

            logger.debug("images: %s" % images)

            image_format = self.config.get("file-formatting", "image")
            use_folder_jpg = self.config.getboolean("details", "use_folder_jpg")
            download_only_cover = self.config.getboolean("details", "download_only_cover")

            logger.debug("image-format: %s" % image_format)
            logger.debug("use_folder_jpg: %s" % use_folder_jpg)

            self.create_album_dir()

            no = 0
            for i, image_url in enumerate(images, 0):
                logger.debug("Downloading image '%s'" % image_url)
                try:
                    picture_name = ""
                    if i == 0 and use_folder_jpg:
                        picture_name = "folder.jpg"
                    else:
                        no = no + 1
                        picture_name = image_format + "-%.2d.jpg" % no

                    conn_mgr.fetch_image(os.path.join(self.album.target_dir, picture_name), image_url)

                    if i == 0 and download_only_cover:
                        break

                except Exception as e:
                    logger.error("Unable to download image '%s', skipping." % image_url)
                    print(e)

    def embed_coverart_album(self):
        """
            Embed cover art into all album files
        """
        embed_coverart = self.config.getboolean("details", "embed_coverart")
        image_format = self.config.get("file-formatting", "image")
        use_folder_jpg = self.config.getboolean("details", "use_folder_jpg")

        if use_folder_jpg:
            first_image_name = "folder.jpg"
        else:
            first_image_name = image_format + "-01.jpg"

        image_file = os.path.join(self.album.target_dir, first_image_name)

        logger.debug("Start to embed coverart (on request)...")

        if embed_coverart and os.path.exists(image_file):
            logger.debug("embed_coverart and image_file")
            with open(image_file, 'rb') as f:
                imgdata = f.read()

            header = imgdata[:4]
            if header[:2] == b'\xff\xd8':
                imgtype = 'jpeg'
            elif header == b'\x89PNG':
                imgtype = 'png'
            else:
                imgtype = None

            if imgtype in ("jpeg", "png"):
                    logger.info("Embedding album art...")
                    for disc in self.album.discs:
                        for track in disc.tracks:
                            self.embed_coverart_track(disc, track, imgdata)

    def embed_coverart_track(self, disc, track, imgdata):
        """
            Embed cover art into a single file
        """

        if disc.target_dir != None:
            track_dir = os.path.join(self.album.target_dir, disc.target_dir)
        else:
            track_dir = self.album.target_dir

        track_file = os.path.join(track_dir, track.new_file)
        metadata = MediaFile(track_file)
        try:
            metadata.art = imgdata
            metadata.save()
        except Exception as e:
            logger.error("Unable to embed image '%s': %s", track_file, e)

    def add_replay_gain_tags(self):
        """Add ReplayGain tags to all audio files in the album directory.

        Supported applications (configured via [replaygain] application=):
          r128gain  — pip-installable Python wrapper around ffmpeg (recommended)
          loudgain  — standalone C tool (OS dependency)
          metaflac  — part of the flac package; FLAC only (OS dependency)
        """
        if not self.rg_process:
            return

        import subprocess
        from pathlib import Path

        audio_extensions = {'.flac', '.ogg', '.mp3', '.ape'}
        album_path = Path(self.album.target_dir)

        # Collect all audio files recursively, grouped by extension
        files_by_ext: dict[str, list[str]] = {}
        for f in sorted(album_path.rglob('*')):
            if f.suffix.lower() in audio_extensions:
                files_by_ext.setdefault(f.suffix.lower(), []).append(str(f))

        if not files_by_ext:
            logger.warning('No audio files found for ReplayGain in %s', album_path)
            return

        lg_flags = {
            '.flac': ['-a', '-k', '-s', 'e'],
            '.mp3':  ['-I', '4', '-S', '-L', '-a', '-k', '-s', 'e'],
        }

        for ext, file_paths in files_by_ext.items():
            logger.info('Adding ReplayGain (%s) to %d %s file(s)',
                        self.rg_application, len(file_paths), ext)

            if self.rg_application == 'r128gain':
                cmd = ['r128gain', '-a'] + file_paths
            elif self.rg_application == 'loudgain':
                cmd = ['loudgain'] + lg_flags.get(ext, []) + file_paths
            elif self.rg_application == 'metaflac':
                cmd = ['metaflac', '--add-replay-gain'] + file_paths
            else:
                logger.error('Unknown ReplayGain application: %s', self.rg_application)
                return

            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error('ReplayGain failed (exit %d):\n%s',
                             result.returncode, result.stderr.strip())
            else:
                logger.debug('ReplayGain completed for %d file(s)', len(file_paths))


class TaggerUtils(object):
    """ Accepts a destination directory name and discogs release id.
        TaggerUtils returns a the corresponding metadata information, in which
        we can write to disk. The assumption here is that the destination
        direcory contains a single album in a support format (mp3 or flac).

        The class also provides a few methods that create supplimental files,
        relvant to a given album (m3u, nfo file and album art grabber.)"""

    # supported file types.
    FILE_TYPE = (".mp3", ".flac",)

    def __init__(self, sourcedir, destdir, tagger_config, album=None):
        self.config = tagger_config

        # ignore directory where old cue files are stashed
        self.cue_done_dir = self.config.get('cue', 'cue_done_dir')

# !TODO should we define those in here or in each method (where needed) or in a separate method
# doing the "mapping"?
        self.dir_format = self.config.get("file-formatting", "dir")
        self.song_format = self.config.get("file-formatting", "song")
        self.va_song_format = self.config.get("file-formatting", "va_song")
        self.images_format = self.config.get("file-formatting", "image")
        self.m3u_format = self.config.get("file-formatting", "m3u")
        self.nfo_format = self.config.get("file-formatting", "nfo")
        self.disc_folder_name = self.config.get("file-formatting", "discs")
        self.normalize = self.config.get("file-formatting", "normalize")
        self.use_lower = self.config.getboolean("details", "use_lower_filenames")
        self.join_artists = self.config.get("details", "join_artists")

#        self.first_image_name = "folder.jpg"
        self.copy_other_files = self.config.getboolean("details", "copy_other_files")
        self.char_exceptions = self.config.character_exceptions

        self.sourcedir = sourcedir
        self.destdir = destdir

        if not album == None:
            self.album = album
        else:
            raise RuntimeError('Cannot tag, no album given')

        self.map_format_description()

        self.album.sourcedir = sourcedir
        # the album is stored in a directory beneath the destination directory
        # and following the given dir_format
        self.album.target_dir = self.dest_dir_name

        logging.debug("album.target_dir: %s" % self.dest_dir_name)

        # add template functionality ;-)
        self.template_lookup = TemplateLookup(directories=["templates"])

    def map_format_description(self):
        """ Gets format desription, and maps to user defined variations,
            e.g. Limited Edition -> ltd
        """
        self.format_mapping = {}
        self.media_desc_formatting = self.config.items('media_description')

        # get the mapping from config and convert to dict (lowercase keys for matching)
        for i in self.media_desc_formatting:
            self.format_mapping[i[0].lower()] = i[1] if i[1] != '' else None

        for i, desc in enumerate(self.album.format_description):
            if desc.lower() in self.format_mapping.keys():
                if self.format_mapping[desc.lower()] is not None:
                    self.album.format_description[i] = self.format_mapping[desc.lower()]

    def _value_from_tag_format(self, format, discno=1, trackno=1, filetype=".mp3"):
        """ Fill in the used variables using the track information
            Transform all variables and use them in the given format string, make this
            slightly more flexible to be able to add variables easier

            Transfer this via a map.
        """

        property_map = {

            '%album artist%': self.join_artists.join(self.album.artists),
            '%albumartist%': self.join_artists.join(self.album.artists),
            '%album%': self.album.title,
            '%catno%': ', '.join(self.album.catnumbers),
            "%year%": self.album.year,
            '%artist%': self.album.disc(discno).track(trackno).artist,
            '%totaldiscs%': self.album.disctotal,
            '%discnumber%': discno,
            '%mediatype%': self.album.disc(discno).mediatype,
            '%disctitle%': self.album.disc(discno).discsubtitle,
            '%track artist%': self.album.disc(discno).track(trackno).artist,
            '%title%': self.album.disc(discno).track(trackno).title,
            '%tracknumber%': self.get_real_track_number(format, discno, trackno),
            '%track number%': trackno,
            '%format%': self.album.format,
            '%format_description%': json.dumps(self.album.format_description or []),
            '%fileext%': self.album.disc(discno).filetype,
            '%bitdepth%': self.album.disc(discno).track(trackno).bitdepth,
            '%bitrate%': self.album.disc(discno).track(trackno).bitrate,
            '%channels%': self.album.disc(discno).track(trackno).channels,
            '%codec%': self.album.disc(discno).track(trackno).codec,
            '%filesize%':'',
            '%filesize_natural%':'',
            '%length_samples%':'',
            '%encoding%': self.album.disc(discno).track(trackno).encoding,
            '%quality%': getattr(self.album, 'quality', '') or '',
            '%samplerate%': self.album.disc(discno).track(trackno).samplerate,
            '%channels%': self.album.disc(discno).track(trackno).channels,
            '%length_seconds_fp%': self.album.disc(discno).track(trackno).length_seconds_fp,
            '%length%': self.album.disc(discno).track(trackno).length,
            '%length_ex%': self.album.disc(discno).track(trackno).length_ex,
            '%length_seconds%': self.album.disc(discno).track(trackno).length_seconds,

            "%ALBTITLE%": self.album.title,
            "%ALBARTIST%": self.album.artist,
            "%YEAR%": self.album.year,
            "%CATNO%": self.album.catnumbers[0] if self.album.catnumbers else '',
            "%GENRE%": self.album.genre,
            "%STYLE%": self.album.style,
            "%ARTIST%": self.album.disc(discno).track(trackno).artist,
            "%TITLE%": self.album.disc(discno).track(trackno).title,
            "%DISCNO%": discno,
            "%TRACKNO%": "%.2d" % trackno,
            "%TYPE%": filetype,
            "%LABEL%": self.album.labels[0],
            "%CODEC%": self.album.codec,
        }

        for hashtag in property_map.keys():
            format = format.replace(hashtag, str(property_map[hashtag]))

        return format

    def get_real_track_number(self, format, discno=1, trackno=1):
        if self.album.disc(discno).track(trackno).real_tracknumber is not None:
            return self.album.disc(discno).track(trackno).real_tracknumber
        else:
            return "%.2d" % trackno

    def _value_from_tag(self, format, discno=1, trackno=1, filetype=".mp3"):
        """ Generates the filename tagging map
            avoid usage of file extension here already, could lead to problems
        """

        stringFormatting = StringFormatting()
        format = self._value_from_tag_format(format, discno, trackno, filetype)
        format = stringFormatting.parseString(format)
        format = self.get_clean_filename(format)

        logger.debug("output: %s" % format)

        return format

    def _set_target_discs_and_tracks(self, filetype):
        """
            set the target names of the disc and tracks in the discnumber
            based on the configuration settings and the name of the disc
            or track
            these can be calculated without knowing the source (well, the
            filetype seems to be a different calibre)
        """
        for disc in self.album.discs:
            if not self.album.has_multi_disc:
                disc.target_dir = None
            else:
                target_dir = self._value_from_tag(self.disc_folder_name, disc.discnumber)
                disc.target_dir = target_dir

            for track in disc.tracks:
                # special handling for Various Artists discs
                if self.album.artist == "Various":
                    newfile = self._value_from_tag(self.va_song_format, disc.discnumber,
                                               track.tracknumber, filetype)
                else:
                    newfile = self._value_from_tag(self.song_format, disc.discnumber,
                                               track.tracknumber, filetype)

                track.new_file = self.get_clean_filename(newfile)

    def gather_addional_properties(self):
        ''' Fetches additional technical information about the tracks
        '''
        for disc in self.album.discs:
            dn = disc.discnumber
            for track in disc.tracks:
                tn = track.tracknumber
                metadata = MediaFile(track.full_path)
                # for field in metadata.readable_fields():
                #     print('fieldname: {}: '.format(field)) #, getattr(metadata, field)

                self.album.disc(dn).track(tn).codec = metadata.type
                codec = metadata.type
                lossless = ('flac', 'alac', 'wma', 'ape', 'wav')
                encod = 'lossless' if codec.lower() in lossless else 'lossy'
                self.album.disc(dn).track(tn).encoding = encod
                self.album.disc(dn).track(tn).samplerate = metadata.samplerate
                self.album.disc(dn).track(tn).bitrate = metadata.bitrate
                self.album.disc(dn).track(tn).bitdepth = metadata.bitdepth
                chans = metadata.channels
                ch_opts = {1: 'mono', 2: 'stereo'}
                self.album.disc(dn).track(tn).channels = ch_opts[chans] if chans in ch_opts else '{}ch'.format(chans)
                self.album.disc(dn).track(tn).length_seconds_fp = metadata.length
                length_seconds_fp = metadata.length
                self.album.disc(dn).track(tn).length_seconds = int(length_seconds_fp)
                self.album.disc(dn).track(tn).length = str(timedelta(seconds = int(length_seconds_fp)))
                length_ex_str = str(timedelta(seconds = round(length_seconds_fp, 4)))
                self.album.disc(dn).track(tn).length_ex = length_ex_str[:-2]

        # After all per-track data is collected, compute release-level quality
        self.album.quality = self._assess_quality()

    def _assess_quality(self):
        """Compute a release-level quality string from per-track technical data.

        Returns one of:
          'lossless'        — every track uses a lossless codec
          '<kbps>'          — all lossy tracks share the same bitrate (CBR),
                              e.g. '320', '192'
          'vbr'             — lossy tracks with varying bitrates (VBR / ABR)
          ''                — no data available

        Intended for use as %quality% in format strings.  Combined with
        %bitdepth%, %samplerate% and %channels% it produces strings like:
          lossless-24-96s   (24-bit / 96 kHz / stereo lossless)
          lossless-44s      (16-bit / 44.1 kHz / stereo lossless)
          320-44s           (320 kbps CBR / 44.1 kHz / stereo)
          vbr-44s           (VBR / 44.1 kHz / stereo)
        """
        encodings = set()
        lossy_bitrates_kbps = []

        for disc in self.album.discs:
            for track in disc.tracks:
                enc = getattr(track, 'encoding', None)
                br  = getattr(track, 'bitrate',  None)
                if enc:
                    encodings.add(enc)
                if enc == 'lossy' and br:
                    lossy_bitrates_kbps.append(round(br / 1000))

        if not encodings:
            return ''

        # All tracks lossless (or no lossy data at all)
        if 'lossy' not in encodings:
            return 'lossless'

        # Mixed lossless + lossy is unusual but handle gracefully
        if not lossy_bitrates_kbps:
            return 'lossless'

        min_br = min(lossy_bitrates_kbps)
        max_br = max(lossy_bitrates_kbps)
        # Treat as CBR if all track bitrates agree within 5 kbps
        if max_br - min_br <= 5:
            return str(round(sum(lossy_bitrates_kbps) / len(lossy_bitrates_kbps)))

        return 'vbr'

    def _directory_has_audio_files(self, dir):
        codecs = ('.flac', '.ogg', '.mp3')
        files = next(os.walk(dir))[2]
        found = 0
        for f in files:
            if list(filter(f.endswith, codecs)) != []:
                found += 1
        return False if found == 0 else True

    def _directory_prune_unwanted(self, dir_list):
        """ Remove directories without audio files / in ignore list
        """
        extf = (self.cue_done_dir)
        dir_list[:] = [d for d in dir_list if d not in extf]
        # return dir_list

    def _audio_files_in_subdirs(self, dir_list):
        """ Are files in subdirectories rather than root dirs?
        """
        codecs = ('.flac', '.ogg', '.mp3')
        sourcedir = self.album.sourcedir
        for x in dir_list:
            if x.endswith(codecs):
                return False
            elif os.path.isdir(os.path.join(sourcedir, x)) and \
            self._directory_has_audio_files(os.path.join(sourcedir, x)):
                return True
        return False

    def _get_target_list(self):
        """
            fetches a list of files with the defined file_type
            in the self.sourcedir location as target_list, other
            files in the sourcedir are returned in the copy_files list.
        """
        copy_files = []
        target_list = []
        disc_source_dir = None

        sourcedir = self.album.sourcedir

        logger.debug("target_dir: %s" % self.album.target_dir)
        logger.debug("sourcedir: %s" % sourcedir)

        try:
            dir_list = os.listdir(sourcedir)
            dir_list.sort()
            self._directory_prune_unwanted(dir_list)
            filetype = ""
            self.album.copy_files = []

            if self.album.has_multi_disc or self._audio_files_in_subdirs(dir_list) is True:
                logger.debug("is multi disc album, looping discs")

                logger.debug("dir_list: %s" % dir_list)
                dirno = 0
                for y in dir_list:
                    logger.debug("is it a dir? %s" % y)
                    if os.path.isdir(os.path.join(sourcedir, y)):
                        if self._directory_has_audio_files(os.path.join(sourcedir, y)):
                            logger.debug("Setting disc(%s) sourcedir to: %s" % (dirno, y))
                            self.album.discs[dirno].sourcedir = y
                            dirno = dirno + 1
                    else:
                        logger.debug("Setting copy_files instead of sourcedir")
                        self.album.copy_files.append(y)
            else:
                logger.debug("Setting disc sourcedir to none")
                self.album.discs[0].sourcedir = None

            for disc in self.album.discs:
                # print('disc.sourcedir: {}'.format(disc.sourcedir))
                # try:
                #     disc_source_dir = os.path.join(self.album.sourcedir, disc.sourcedir) \
                #         if disc.sourcedir is not None else None
                # except AttributeError:
                #     logger.error("there seems to be a problem in the meta-data, check if there are sub-tracks")
                #     raise TaggerError("no disc sourcedir defined, does this release contain sub-tracks?")

                if hasattr(disc, 'sourcedir') and disc.sourcedir is not None:
                    disc_source_dir = os.path.join(self.album.sourcedir, disc.sourcedir)
                else:
                    disc_source_dir = self.album.sourcedir

                # if disc_source_dir == None:
                #     disc_source_dir = self.album.sourcedir

                logger.debug("discno: %d" % disc.discnumber)
                logger.debug("sourcedir: %s" % disc_source_dir)

                # strip unwanted files
                disc_list = os.listdir(disc_source_dir)
                disc_list.sort()

                disc.copy_files = [x for x in disc_list
                                if not x.lower().endswith(TaggerUtils.FILE_TYPE)]

                target_list = [os.path.join(disc_source_dir, x) for x in disc_list
                                 if x.lower().endswith(TaggerUtils.FILE_TYPE)]

                if len(target_list) > 0 and len(target_list) != len(disc.tracks):
                    logger.debug("target_list: %s" % target_list)
                    logger.error("not matching number of files....")
                    raise TaggerError("number of audio files ({}) does not match number of tracks ({}) for disc {}".format(
                        len(target_list), len(disc.tracks), disc.discnumber))

                for position, filename in enumerate(target_list):
                    logger.debug("track position: %d" % position)

                    track = disc.tracks[position]

                    logger.debug("mapping file %s --to--> %s - %s" % (filename,
                                 track.artists[0], track.title))

                    track.orig_file = os.path.basename(filename)
                    track.full_path = os.path.join(self.album.sourcedir, filename)
                    filetype = os.path.splitext(filename)[1]
                    disc.filetype = filetype

            self._set_target_discs_and_tracks(filetype)

        except (OSError) as e:
            if e.errno == errno.EEXIST:
                logger.error("No such directory '{}'".format(self.sourcedir))
                raise TaggerError("No such directory '{}'".format(self.sourcedir))
            else:
                raise TaggerError("General IO system error '{}'".format(errno[e]))

    @property
    def dest_dir_name(self):
        """ generates new album directory name """

        logger.debug("self.destdir: {}".format(self.destdir))

        # determine if an absolute base path was specified.
        path_name = os.path.normpath(self.destdir)

        logger.debug("path_name: {}".format(path_name))

        dest_dir = ""
        for ddir in self.dir_format.split("/"):
            d_dir = self.get_clean_filename(self._value_from_tag(ddir))
            if dest_dir == "":
                dest_dir = d_dir
            else:
                dest_dir = os.path.join(dest_dir, d_dir)

            logger.debug("d_dir: {}".format(dest_dir))

        dir_name = os.path.join(path_name, dest_dir)

        return dir_name

    @property
    def m3u_filename(self):
        """ generates the m3u file name """

        m3u = self._value_from_tag(self.m3u_format)
        return self.get_clean_filename(m3u)

    @property
    def nfo_filename(self):
        """ generates the nfo file name """

        nfo = self._value_from_tag(self.nfo_format)
        return self.get_clean_filename(nfo)


    def get_clean_filename(self, f):
        """ Removes unwanted characters from file names """

        filename, fileext = os.path.splitext(f)

        if not fileext in TaggerUtils.FILE_TYPE and not fileext in [".m3u", ".nfo"]:
            logger.debug("fileext: {}".format(fileext))
            filename = f
            fileext = ""

        a = str(filename)
        a = re.sub(r'\.$', '', a) # windows doesn't like folders ending with '.'
        a = re.sub(r'\$', 'S', a) # Replace $ with S

        for k, v in self.char_exceptions.items():
            a = a.replace(k, v)

        if self.normalize == True:
            a = normalize("NFKD", a)

        cf = re.compile(r"[^-\w.()\[\]\s#@&!]")  # commas, apostrophes excluded
        cf = cf.sub("", str(a))
        cf = re.sub(r'_+', '_', cf)  # collapse consecutive underscores (e.g. from "3. Word")


        # Don't force space/underscore replacement. If the user wants this it
        # can be done via config. The user may _want_ spaces.
        # cf = cf.replace(" ", "_")
        # cf = cf.replace("__", "_")
        # cf = cf.replace("_-_", "-")

        cf = "".join([cf, fileext])

        if self.use_lower:
            cf = cf.lower()

        return cf

    def create_file_from_template(self, template_name, file_name):
        file_template = self.template_lookup.get_template(template_name)
        return write_file(file_template.render(album=self.album),
            os.path.join(self.album.target_dir, file_name))

    def create_nfo(self, dest_dir):
        """ Writes the .nfo file to disk. """
        return self.create_file_from_template("info.txt", self.nfo_filename)

    def create_m3u(self, dest_dir):
        """ Generates the playlist for the given albm.
            Adhering to the following m3u format.

            ---
            #EXTM3U
            #EXTINF:233,Artist - Song
            directory\file_name.mp3.mp3
            #EXTINF:-1,My Cool Stream
            http://www.site.com:8000/listen.pls
            ---

            Taken from http://forums.winamp.com/showthread.php?s=&threadid=65772"""
        return self.create_file_from_template("m3u.txt", self.m3u_filename)


def write_file(filecontents, filename):
    """ writes a string of data to disk """

    if not os.path.exists(os.path.dirname(filename)):
        os.makedirs(os.path.dirname(filename))

    logger.debug("Writing file '%s' to disk" % filename)

    try:
        with open(filename, "w") as fh:
            fh.write(filecontents)
    except IOError:
        logger.error("Unable to write file '%s'" % filename)

    return True


def copytree_multi(src, dst, symlinks=False, ignore=None):
    names = os.listdir(src)
    if ignore is not None:
        ignored_names = ignore(src, names)
    else:
        ignored_names = set()

    # -------- E D I T --------
    # os.path.isdir(dst)
    if not os.path.isdir(dst):
        os.makedirs(dst)
    # -------- E D I T --------

    errors = []
    for name in names:
        if name in ignored_names:
            continue
        srcname = os.path.join(src, name)
        dstname = os.path.join(dst, name)
        try:
            if symlinks and os.path.islink(srcname):
                linkto = os.readlink(srcname)
                os.symlink(linkto, dstname)
            elif os.path.isdir(srcname):
                copytree_multi(srcname, dstname, symlinks, ignore)
            else:
                copy2(srcname, dstname)
        except (IOError, os.error) as why:
            errors.append((srcname, dstname, str(why)))
        except Error as err:
            errors.extend(err.args[0])
    try:
        copystat(src, dst)
    except OSError as why:
        errors.extend((src, dst, str(why)))
    if errors:
        raise Error(errors)
