import logging
import re
import os

import requests
from rapidfuzz import fuzz

from discogstagger.cache import ReleaseCache, ImageCache, MasterVersionsCache, SearchCache
from discogstagger.mediafile_ext import MediaFile

from datetime import timedelta, datetime

import discogs_client as discogs

import json

from discogstagger.album import Album, Disc, Track

logger = logging.getLogger(__name__)

class AlbumError(Exception):
    """ A central exception for all errors happening during the album handling
    """
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)

class DiscogsConnector(object):
    """Connects to the Discogs API.

    Authentication priority:
      1. user_token in config / DISCOGS_USER_TOKEN env var (personal access token — simplest)
      2. consumer_key + consumer_secret (OAuth 1.0a PIN flow — stores token in .token file)
      3. No auth — metadata only, image downloads unavailable

    Rate limiting is handled automatically by the discogs_client library (backoff_enabled=True).
    """

    def __init__(self, tagger_config):
        self.config = tagger_config
        self.user_agent = self.config.get("common", "user_agent")
        self.discogs_auth = False
        self.release_cache = {}
        self.tracklength_tolerance = self.config.getfloat("batch", "tracklength_tolerance")
        self.title_similarity_threshold = self.config.getfloat("batch", "title_similarity_threshold")
        self._user_token = None
        self._release_cache = None
        self._image_cache = None
        self._master_versions_cache = None
        self._search_cache = None

        cache_dir = self.config.get("cache", "directory")
        if cache_dir:
            cache_dir = os.path.expanduser(cache_dir)
            self._release_cache = ReleaseCache(cache_dir)
            self._image_cache = ImageCache(cache_dir)
            self._master_versions_cache = MasterVersionsCache(cache_dir)
            self._search_cache = SearchCache(cache_dir)
            logger.info('Disk cache enabled at %s', cache_dir)

        user_token = os.environ.get('DISCOGS_USER_TOKEN') or self.config.get("discogs", "user_token")
        skip_auth = self.config.get("discogs", "skip_auth")

        if user_token:
            self.discogs_client = discogs.Client(self.user_agent, user_token=user_token)
            self._user_token = user_token
            self.discogs_auth = True
            logger.info('Authenticated via personal access token')
        elif skip_auth != "True":
            self.discogs_client = discogs.Client(self.user_agent)
            self._init_oauth()
        else:
            self.discogs_client = discogs.Client(self.user_agent)
            logger.warning('Authentication disabled — image downloads will not work')

    def _init_oauth(self):
        """Set up OAuth 1.0a using consumer key/secret from config or environment."""
        consumer_key = os.environ.get('DISCOGS_CONSUMER_KEY') or self.config.get("discogs", "consumer_key")
        consumer_secret = os.environ.get('DISCOGS_CONSUMER_SECRET') or self.config.get("discogs", "consumer_secret")

        if not (consumer_key and consumer_secret):
            logger.warning('No auth configured (no user_token, no consumer key/secret) — image downloads will not work')
            return

        self.discogs_client.set_consumer_key(consumer_key, consumer_secret)

        access_token, access_secret = self.read_token()
        if access_token and access_secret:
            self.discogs_client.set_token(access_token, access_secret)
            self.discogs_auth = True
            logger.info('Authenticated via cached OAuth token ({})'.format(self.construct_token_file()))
        else:
            self._run_oauth_pin_flow()

    def _run_oauth_pin_flow(self):
        """Interactive OAuth PIN flow — prompts user to visit a URL and enter a PIN."""
        try:
            request_token, request_token_secret, authorize_url = self.discogs_client.get_authorize_url()
            print('Visit this URL in your browser: ' + authorize_url)
            pin = input('Enter the PIN from the above URL: ').strip()
            access_token, access_secret = self.discogs_client.get_access_token(pin)
            token_file = self.construct_token_file()
            with open(token_file, 'w') as fh:
                fh.write('{},{}'.format(access_token, access_secret))
            self.discogs_auth = True
            logger.info('OAuth successful — token saved to {}'.format(token_file))
        except Exception as e:
            logger.error('OAuth flow failed: {}'.format(e))

    def read_token(self):
        """Read a cached OAuth token from the .token file."""
        token_file = self.construct_token_file()
        try:
            with open(token_file, 'r') as tf:
                parts = tf.read().split(',')
                if len(parts) == 2:
                    return parts[0].strip(), parts[1].strip()
        except (IOError, OSError):
            pass
        return None, None

    def construct_token_file(self):
        return os.path.join(os.getcwd(), '.token')

    def fetch_release(self, release_id):
        rid = int(release_id)
        if self._release_cache:
            cached = self._release_cache.get(rid)
            if cached is not None:
                logger.info('Release %s loaded from cache', rid)
                # Construct with full cached data; fetch(key) finds every key
                # in data dict so no API call is made.
                return discogs.Release(self.discogs_client, cached)
        logger.info('Fetching release %s from Discogs' % rid)
        return self.discogs_client.release(rid)

    def cache_release(self, release) -> None:
        """Write a fully-loaded release to the disk cache.

        Call this *after* DiscogsAlbum.map() so all fields are present in
        release.data (they are loaded lazily on first field access).
        """
        if self._release_cache and release is not None:
            self._release_cache.put(release.id, release.data)

    def fetch_image(self, image_dir, image_url):
        """Download a Discogs image, using the disk cache when available."""
        if not self.discogs_auth:
            logger.error('Not authenticated — cannot download image, skipping')
            return
        try:
            if self._image_cache:
                data = self._image_cache.get(image_url)
                if data is not None:
                    logger.info('Image loaded from cache: %s', image_url)
                    with open(image_dir, 'wb') as fh:
                        fh.write(data)
                    return

            headers = {'User-Agent': self.user_agent}
            params = {'token': self._user_token} if self._user_token else {}
            response = requests.get(image_url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            data = response.content
            with open(image_dir, 'wb') as fh:
                fh.write(data)
            if self._image_cache:
                self._image_cache.put(image_url, data)
        except Exception as e:
            logger.error("Unable to download image '%s': %s" % (image_url, e))

class DummyResponse(object):
    """
        The dummy response used to create a discogs.release from a local json file
    """
    def __init__(self, release_id, json_path):
        self.releaseid = release_id

        json_file_name = "%s.json" % self.releaseid
        json_file_path = os.path.join(json_path, json_file_name)

        self.status_code = 200
        with open(json_file_path, 'r', encoding='utf-8') as json_file:
            self.content = json_file.read()

class LocalDiscogsConnector(object):
    """ use local json, do not fetch json from discogs, instead use the one in the source_directory
        We will need to use the Original DiscogsConnector to allow the usage of the authentication
        for fetching images.
    """

    def __init__(self, delegate_discogs_connector):
        self.delegate = delegate_discogs_connector

    def fetch_release(self, release_id, source_dir):
        """ fetches the metadata for the given release_id from a local file
        """
        dummy_response = DummyResponse(release_id, source_dir)

        # we need a dummy client here ;-(
        client = discogs.Client('Dummy Client - just for testing')

        self.content = self.convert(json.loads(dummy_response.content))

        logger.debug('content: %s' % self.content)

        release = discogs.Release(client, self.content)

        return release

    def authenticate(self):
        self.delegate.authenticate()

    def fetch_image(self, image_dir, image_url):
        self.delegate.fetch_image(image_dir, image_url)

    def updateRateLimits(self, request):
        self.delegate.updateRateLimits(request)

    def convert(self, input):
        """ This is an exact copy of a method in _common_test, please refactor
        """
        if isinstance(input, dict):
            return {self.convert(key): self.convert(value) for key, value in input.items()}
        elif isinstance(input, list):
            return [self.convert(element) for element in input]
        # elif isinstance(input, unicode):
        #     return input.encode('utf-8')
        else:
            return input


class DiscogsAlbum(object):
    """ Wraps the discogs-client-api script, abstracting the minimal set of
        artist data required to tag an album/release

        >>> from discogstagger.discogsalbum import DiscogsAlbum
        >>> release = DiscogsAlbum(40522) # fetch discogs release id 40522
        >>> print "%s - %s (%s / %s)" % (release.artist, release.title, release.catno,
        >>> release.label)

        Blunted Dummies - House For All (12DEF006 / Definitive Recordings)

        >>> for song in release.tracks: print "[ %.2d ] %s - %s" % (song.position,
        >>> song.artist, song.title)

        [ 01 ] Blunted Dummies - House For All (Original Mix)
        [ 02 ] Blunted Dummies - House For All (House 4 All Robots Mix)
        [ 03 ] Blunted Dummies - House For All (Eddie Richard's Mix)
        [ 04 ] Blunted Dummies - House For All (J. Acquaviva's Mix)
        [ 05 ] Blunted Dummies - House For All (Ruby Fruit Jungle Mix) """

    def __init__(self, release):
        self.release = release

    def map(self):
        """ map the retrieved information to the tagger specific objects """

        album = Album(self.release.id, self.release.title.strip(), self.album_artists(self.release.artists))

        album.sort_artist = self.sort_artist(self.release.artists)
        album.url = self.url
        # Discogs returns "none" (lowercase) when no catalog number exists
        album.catnumbers = self.remove_duplicate_items([
            catno for name, catno in self.labels_and_numbers
            if catno and catno.lower() != 'none'
        ])
        album.catnumbers.sort()
        album.labels = self.remove_duplicate_items([name for name, catno in self.labels_and_numbers])
        album.images = self.images
        album.year = self.year
        album.format = self.release.data["formats"][0]["name"]
        album.format_description = self.format_description
        album.genres = self.release.data["genres"]
        album.media = self.media


        try:
            album.styles = self.release.data["styles"]
        except KeyError:
            album.styles = [""]

        if "country" in self.release.data:
            album.country = self.release.data["country"]
        else:
            logger.warning("no country set for relid %s", self.release.id)
            album.country = ""

        if "notes" in self.release.data:
            album.notes = self.release.data["notes"]

        album.disctotal = self.disctotal
        album.is_compilation = self.is_compilation

        album.master_id = self.master_id

        album.discs = self.discs_and_tracks(album)

        return album

    @property
    def media(self):
        ''' the recording media the track came from.
            eg, CD, Cassette, Radio Broadcast, LP, CD Single
        '''
        fields = ['qty', 'name', 'descriptions', 'text']
        source = []

        for format in self.release.data["formats"]:
            f = ''
            for field in fields:
                if field in format:
                    if field == 'descriptions':
                        f += ' ' + ', '.join(format['descriptions'])
                    elif field == 'qty':
                        f += '{} x '.format(format['qty'])
                    elif field == 'name':
                        f += format['name']
                    else:
                        f += ', {}'.format(format[field])
            source.append(f)

        return '; '.join(source)



    @property
    def format_description(self):
        descriptions = []

        for format in self.release.data["formats"]:
            if 'descriptions' in format:
                descriptions.extend(format['descriptions'])

        return descriptions


    @property
    def url(self):
        """ returns the discogs url of this release """

        return "http://www.discogs.com/release/{}".format(self.release.id)

    @property
    def labels_and_numbers(self):
        """ Returns all available catalog numbers"""
        for label in self.release.data["labels"]:
            yield self.clean_duplicate_handling(label["name"]), label["catno"]

    @property
    def images(self):
        """Return image metadata for the release.

        Each entry is a dict with at least 'uri' and 'type' keys.
        Discogs only distinguishes 'primary' (front cover) and 'secondary'
        (all other images — back, media, booklet, etc. are not differentiated).
        """
        try:
            return [
                {
                    'uri':    x['uri'],
                    'type':   x.get('type', 'secondary'),
                    'width':  x.get('width'),
                    'height': x.get('height'),
                }
                for x in self.release.data['images']
            ]
        except KeyError:
            return []

    @property
    def year(self):
        """ returns the album release year obtained from API 2.0 """

        good_year = re.compile(r"\d\d\d\d")
        try:
            return good_year.match(str(self.release.data["year"])).group(0)
        except IndexError:
            return "1900"
        except AttributeError:
            return "1900"

    @property
    def disctotal(self):
        """ Obtain the number of discs for the given release. """

        discno = 0

        # allows tagging of digital releases.
        # sample format <format name="File" qty="2" text="320 kbps">
        # assumes all releases of name=File is 1 disc.
        if self.release.data["formats"][0]["name"] == "File":
            discno = 1
        else:
            for format in self.release.data["formats"]:
                if format['name'] in ['CD', 'CDr', 'Vinyl', 'LP']:
                    discno += int(format['qty'])

        logger.info("determined %d no of discs total" % discno)
        return discno

    @property
    def master_id(self):
        """ returns the master release id """

        try:
            return self.release.data["master_id"]
        except KeyError:
            return None

    def _gen_artist(self, artist_data):
        """ yields a list of artists name properties """
        for x in artist_data:
            # bugfix to avoid the following scenario, or ensure we're yielding
            # an artist object.
            # AttributeError: 'unicode' object has no attribute 'name'
            # [<Artist "A.D.N.Y*">, u'Presents', <Artist "Leiva">]
            try:
                yield x.name
            except AttributeError:
                pass

    def album_artists(self, artist_data):
        """ obtain the artists (normalized using clean_name).
            the handling of the 'join' stuff is not implemented in discogs_client ;-(
        """
        artists = []

        last_artist = None
        for x in artist_data:
            logger.debug("album-x: %s" % x.name)
            artists.append(self.clean_name(x.name))

        return artists

    def artists(self, artist_data):
        """ obtain the artists (normalized using clean_name). this is specific for tracks, since tracks are handled
            differently from the album artists.
            here the "join" is taken into account as well....

        """
        artists = []
        last_artist = None
        join = None

        for x in artist_data:
#            logger.debug("x: %s" % vars(x))
#            logger.debug("join: %s" % x.data['join'])

            if isinstance(x, str):
                logger.debug("x: %s" % x)
                if last_artist:
                    last_artist = last_artist + " " + x
                else:
                    last_artist = x
            else:
                if last_artist is not None:
                    logger.debug("name: %s" % x.name)
                    concatString = " "
                    if join is not None:
                        concatString = " " + join + " "

                    last_artist = last_artist + concatString + self.clean_name(x.name)
                    artists.append(last_artist)
                    last_artist = None
                else:
                    join = x.data['join']
                    last_artist = self.clean_name(x.name)

            logger.debug("last_artist: %s" % last_artist)

        artists.append(last_artist)

        return artists

    def sort_artist(self, artist_data):
        """ Obtain a clean sort artist """
        return self.clean_duplicate_handling(artist_data[0].name)

    def disc_and_track_no(self, position):
        """ obtain the disc and tracknumber from given position
            problem right now, discogs uses - and/or . as a separator, furthermore discogs uses
            A1 for vinyl based releases, we should implement this as well.

            Further complications. Hidden tracks can have a . separator where the rest
            of the release doesn't, e.g. 1, 2, 3, 4, 5, 6, 7, 8, 9.1, 9.2, 9.3
            If we treat these as
        """
        # if position.find("-") > -1 or position.find(".") > -1:
        if position.find("-") > -1:
            # some variance in how discogs releases spanning multiple discs
            # or formats are kept, add regexs here as failures are encountered
            NUMBERING_SCHEMES = (
                r"^CD(?P<discnumber>\d+)-(?P<tracknumber>\d+)$", # CD01-12
                r"^(?P<discnumber>\d+)-(?P<tracknumber>\d+)$",   # 1-02
                r"^(?P<discnumber>CD)-(?P<tracknumber>\d+)$", # CD-12
                r"^(?P<discnumber>USB-Stick)-(?P<tracknumber>\d+)$",   # USB-Stick-1-12
                # r"^(?P<discnumber>\d+).(?P<tracknumber>\d+)$",   # 1.05
            )

            for scheme in NUMBERING_SCHEMES:
                re_match = re.search(scheme, position)

                if re_match:
                    return {'tracknumber': re_match.group("tracknumber"),
                            'discnumber': re_match.group("discnumber")}
        else:
            return {'tracknumber': position,
                    'discnumber': 1}


        logging.error("Unable to match multi-disc track/position")
        return False

    @property
    def is_compilation(self):
        if self.release.data["artists"][0]["name"] == "Various":
            return True

        for format in self.release.data["formats"]:
            if "descriptions" in format:
                for description in format["descriptions"]:
                    if description == "Compilation":
                        return True

        return False

    def discs_and_tracks(self, album):
        """ provides the tracklist of the given release id
        """
        disc_list = []
        track_list = []
        discsubtitle = []
        disccount= 1
        disc = Disc(1)
        running_num = 0

        for i, t in enumerate(x for x in self.release.tracklist):

            if t.position is None:
                logging.error("position is null, shouldn't be...")

            exclude = ("Video", "video", "DVD")
            if t.position.startswith(exclude) or t.position.endswith(exclude):
                continue

            # on multiple discs there do appears a subtitle as the first "track"
            # on the cd in discogs, this seems to be wrong, but we would like to
            # handle it anyway.
            # Headings could also be a chapter title.
            if (t.title and not t.position and not t.duration) or \
            (hasattr(t, 'type_') and t.type_ == 'heading') or \
            ('type_' in t.data and t.data['type_'] == 'heading'):
                discsubtitle.append(t.title.strip())
                continue

            running_num = running_num + 1
            if t.artists:
                artists = self.artists(t.artists)
                sort_artist = self.sort_artist(t.artists)
            else:
                artists = album.artists
                sort_artist = album.sort_artist

            track = Track(i + 1, t.title.strip(), artists)

            if 'sub_tracks' in t.data:
                comments = []
                for subtrack in t.data['sub_tracks']:
                    if subtrack['type_'] == 'track':
                        comment = subtrack['position'].strip() + '. ' + subtrack['title'].strip()
                        if 'duration' in subtrack and subtrack['duration'] != '':
                            comment += ' (' + subtrack['duration'].strip() + ')'
                        comments.append(comment)
                setattr(track, 'notes', '\r\n'.join(comments))

            track.position = i

            pos = self.disc_and_track_no(t.position)
            # box sets can have a mixture of CDs and other media, e.g. USB-Stick
            # with, or without numbering.  Where numerical disc number follows the
            # disc number, but we may have to add ourselves.  Store the media type
            # so that we can use that later.
            try:
                # track.discnumber = int(pos["discnumber"])
                if re.match(r'^\d+$', str(pos["discnumber"])):
                    track.discnumber = int(pos["discnumber"])
                elif disc.mediatype != pos["discnumber"]:
                    # if this is the first thing encountered don't increase disc count
                    track.discnumber = disccount if len(disc_list) == 0 else disccount + 1
                    track.mediatype = pos["discnumber"]
                else:
                    track.discnumber = disccount
                    track.mediatype = disc.mediatype
            except ValueError as ve:
                msg = "cannot convert {0} to a valid track-/discnumber".format(t.position)
                logger.error(msg)
                raise AlbumError(msg)

            if track.discnumber != disc.discnumber:
                disc_list.append(disc)
                disc = Disc(track.discnumber)
                running_num = 1
                disccount += 1
                if track.mediatype is not None:
                    disc.mediatype = track.mediatype
            # Store the actual track number. Used for non-standard numbering
            track.real_tracknumber = pos["tracknumber"] if pos["tracknumber"] != '' else str(running_num)
            # Tracknumber is a running number
            track.tracknumber = running_num

            if len(discsubtitle) > 0:
                track.discsubtitle = discsubtitle[-1]
                # if disc.discnumber == len(discsubtitle):
                disc.discsubtitle = discsubtitle[-1]
                logger.debug("discsubtitle: {0}".format(disc.discsubtitle))

            track.sort_artist = sort_artist
            disc.tracks.append(track)
        disc_list.append(disc)
        return disc_list

    def remove_duplicate_items(self, duplicates_list):
        """ remove duplicates from an n item list """
        return list(set(duplicates_list))

    def clean_duplicate_handling(self, clean_target):
        """ remove discogs duplicate handling eg : John (1) """
        return re.sub(r"\s\(\d+\)", "", clean_target)

    def clean_name(self, clean_target):
        """ Cleans up the format of the artist or label name provided by
            Discogs.
            Examples:
                'Goldie (12)' becomes 'Goldie'
                  or
                'Aphex Twin, The' becomes 'The Aphex Twin'
            Accepts a string to clean, returns a cleansed version """

        groups = {
            (r"(.*),\sThe$", r"The \g<1>"),
        }

        clean_target = self.clean_duplicate_handling(clean_target)

        for regex in groups:
            clean_target = re.sub(regex[0], regex[1], clean_target)

        return clean_target

class DiscogsSearch(DiscogsConnector):
    """ Search for a release based on the existing
        metadata of the files in the source directory
    """
    def __init__(self, tagger_config):
        DiscogsConnector.__init__(self, tagger_config)
        self.cue_done_dir = '.cue'
        self.candidates = {}
        self.no_duration_candidates = {}
        self.search_params = {}

    def _fetchSubdirectories(self, source_dir, filepaths):
        """ Receives an array of files (with full pathname), if the paths
            are not all the same, will return the subdirectories that differ,
            relative to the source_dir
        """
        paths = list()
        for filepath in filepaths:
            path, file = os.path.split(filepath)
            paths.append(path)
        if len(set(paths)) > 1:
            subdirs = [dir.replace(source_dir, '') for dir in paths]
            subdirs.sort()
            return subdirs
        else:
            return []

    def getSearchParams(self, source_dir):
        """ get search parameters from exiting tags to find release on discogs.
            Minimum tags = artist, album title, disc, tracknumber and date is also helpful.
            If track numbers are not present they are guessed by their index.
        """
        logger.info('Retrieving original metadata for search purposes')
        # reset candidates & searchParams
        self.search_params = {}
        self.candidates = {}
        self.no_duration_candidates = {}

        files = self._getMusicFiles(source_dir)
        files.sort()
        subdirectories = self._fetchSubdirectories(source_dir, files)
        searchParams = self.search_params
        searchParams['sourcedir'] = source_dir

        trackcount = 0
        discnumber = 0
        searchParams['artists'] = []
        searchParams['tracks'] = []
        for i, file in enumerate(files):
            trackcount = trackcount + 1
            metadata = MediaFile(file)

            for a in (metadata.artists or []):
                if a:
                    searchParams['artists'].append(a)
            searchParams['albumartist'] = metadata.albumartist or ''
            searchParams['album'] = re.sub(r'\[.*?\]', '', metadata.album or '')
            searchParams['year'] = metadata.year
            searchParams['date'] = metadata.date

            disc = metadata.disc
            if disc is not None and int(disc) > 1:
                searchParams['disc'] = disc
            elif disc is None and len(set(subdirectories)) > 1 and i < len(subdirectories):
                trackdisc = re.search(r'(?i)^(cd|disc)\s?(?P<discnumber>[0-9]{1,2})', subdirectories[i])
                if trackdisc:
                    searchParams['disc'] = int(trackdisc.group('discnumber'))

            if 'disc' in searchParams and searchParams['disc'] != discnumber:
                trackcount = 1

            tracknumber = str(searchParams['disc']) + '-' if 'disc' in searchParams else ''
            tracknumber += str(metadata.track) if metadata.track is not None else str(trackcount)

            trackInfo = {}
            if re.search(r'(?i)^[a-z]', str(metadata.track or '')):
                trackInfo['real_tracknumber'] = metadata.track
            trackInfo['position'] = tracknumber
            trackInfo['duration'] = str(timedelta(seconds=round(metadata.length or 0, 0)))
            trackInfo['title'] = metadata.title or ''
            trackInfo['artist'] = metadata.artist or ''
            searchParams['tracks'].append(trackInfo)

        searchParams['artists'] = [a for a in dict.fromkeys(searchParams['artists']) if a]
        searchParams['artist'] = ', '.join(searchParams['artists'])

        if len(searchParams['artists']) == 0 \
        and ('albumartist' not in searchParams or searchParams['albumartist'] == '') \
        and ('album' not in searchParams or searchParams['album'] == ''):
            logger.warning('No metadata available in the audio files')
            self.metadataFromFileNaming(source_dir, files)
            searchParams = None
            return None

    def metadataFromFileNaming(self, source_dir, files):
        """ Fall back method to retrieve release information from directories
            and filenames
        """
        logger.info('Fetching metadata from file & directory naming')
        searchParams = self.search_params
        base_dir = self.config.get('details', 'source_dir')
        if re.search(r'(?i)(vinyl)', source_dir):
            searchParams['media'] = 'vinyl'
        release_dir = re.sub(base_dir, '', source_dir)
        year = re.search(r'(\d{4})', release_dir)
        if year is not None:
            searchParams['year'] = year.group(0)
            release_dir = re.sub(year.group(0), '', release_dir)
        dirs = release_dir.split(os.sep)
        dirs = [self.u2s(d) for d in dirs if d != '' and d.lower() not in ('albums', 'singles')]
        if len(dirs) == 3:
            dirs.pop(1) # assume first artist, last release
        if len(dirs) == 2: # assume artist / album
            # is artist name repeated in the release directory name?
            dirs[1] = re.sub(dirs[0].lower(), '', dirs[1].lower())
        elif len(dirs) == 1:
            # is artist / release in the same directory name?
            dirs = re.split(r'\s*[-]\s*', dirs[0])
        if len(dirs) == 2:
            searchParams['artist'] = dirs[0].strip()
            searchParams['album'] = dirs[1].strip()
        else:
            searchParams['album'] = dirs[0]
        for idx, track in enumerate(searchParams['tracks']):
            filename = os.path.basename(files[idx])
            name, ext = os.path.splitext(self.u2s(filename))
            namesplit = name.split(' ', 1)
            track['real_tracknumber'] = namesplit[0]
            rest = namesplit[1].split(' - ')
            if len(rest) > 1:
                track['artist'] = rest[0]
                searchParams['artists'].append(rest[0])
                track['title'] = rest[1]
            else: # assume only title
                track['title'] = rest[0]
                track['artist'] = searchParams['artist'] # overkill?
        searchParams['artists'] = list(dict.fromkeys(searchParams['artists']))
        if searchParams['artist'] == '':
            searchParams['artist'] = ' '.join(searchParams['artists'])
            searchParams['albumartist'] = searchParams['artists'][0]

    def u2s(self, string):
        return re.sub(r'[_]',' ' , string)

    def _getMusicFiles(self, source_dir):
        """ Get album data
        """
        extf = (self.cue_done_dir)
        found = []
        for dirpath, dirs, files in os.walk(source_dir):
            dirs[:] = [d for d in dirs if d not in extf]
            for file in files:
                if file.endswith(('.flac', '.mp3')):
                    found.append(os.path.join(dirpath, file))
        return found

    def normalize(self, string):
        ''' Remove stopwords and other problem words from search strings
        '''
        if not string:
            return ''
        stop_words = ['lp', 'ep', 'bonus', 'tracks', 'mcd', 'cd', 'cdm', 'cds', 'none',
        'vs.', 'vs', 'inch', 'various', 'artists', 'boxset', 'limited', 'edition', 'the']
        string = re.sub(r'[,"\-_\\]', ' ', string)
        string = re.sub(r'[\[\]()|:;]', '', string)
        string = re.sub(r'\s\d{1}\s', ' ', string)
        tokens = list(dict.fromkeys(string.split(' ')))
        return ' '.join([w for w in tokens if not w.lower() in stop_words])

    def get_master_release(self, release):
        if hasattr(release, 'master') and release.master is not None:
            return release.master
        else:
            return release

    def _release_obj_from_cache(self, release_id):
        """Return a lazy Release pre-populated with cached data (if available)."""
        release = self.discogs_client.release(release_id)
        if self._release_cache:
            cached = self._release_cache.get(release_id)
            if cached:
                release.data.update(cached)
        return release

    def _sift_master_versions(self, master):
        """Sift a master's versions, using the master-versions cache."""
        cached_ids = (self._master_versions_cache.get(master.id)
                      if self._master_versions_cache else None)

        if cached_ids is not None:
            logger.info('Master %s: %d version(s) from cache', master.id, len(cached_ids))
            versions = [self._release_obj_from_cache(vid) for vid in cached_ids]
        else:
            versions = list(master.versions)  # single paginated API call
            version_ids = [v.id for v in versions]
            if self._master_versions_cache and version_ids:
                self._master_versions_cache.put(master.id, version_ids)
            logger.info('Master %s: %d version(s) fetched from API', master.id, len(versions))

        self._siftReleases(versions)

    def _replay_search_results(self, cached_results):
        """Process previously cached search results without hitting the search API."""
        for item in cached_results:
            if len(self.candidates) > 0:
                break
            rid = item['id']
            if item.get('is_master'):
                master = self.discogs_client.master(rid)
                self._sift_master_versions(master)
            else:
                release = self._release_obj_from_cache(rid)
                diff = self._compareRelease(release)
                if diff is False:
                    continue
                elif diff < 0:
                    self.no_duration_candidates[release.id] = (release, abs(diff) * 100)
                else:
                    while diff in self.candidates:
                        diff += 0.001
                    self.candidates[diff] = release

    def search_artist_title(self, type):
        s = self.search_params['search']
        query = s['artistRelease']

        # Check search cache first
        cached = self._search_cache.get(query, type) if self._search_cache else None
        if cached is not None:
            logger.info('Search cache hit: "%s" (%s)', query, type)
            self._replay_search_results(cached)
            return

        logger.info('Searching by artist and title ({}): {}'.format(type, query))
        results = self.discogs_client.search(query, type=type)

        collected = []
        for idx, result in enumerate(results):
            if len(self.candidates) > 0:
                break
            if hasattr(result, '__class__') and 'Artist' in str(result.__class__):
                continue

            master = self.get_master_release(result)
            is_master = hasattr(master, 'versions')
            collected.append({'id': master.id, 'is_master': is_master})

            if is_master:
                self._sift_master_versions(master)
            else:
                diff = self._compareRelease(master)
                if diff is False:
                    pass
                elif diff < 0:
                    self.no_duration_candidates[master.id] = (master, abs(diff) * 100)
                else:
                    while diff in self.candidates:
                        diff += 0.001
                    self.candidates[diff] = master

        if self._search_cache and collected:
            self._search_cache.put(query, type, collected)


    def search_artist(self):
        searchParams = self.search_params
        candidates = self.candidates

        artist = self.search_params['search']['artist']
        album = searchParams['album']

        logger.info('Searching by artist: {}'.format(artist))

        releases = None
        results = self.discogs_client.search(artist, type='artist')

        if results.count == 0:
            return None

        for result in results:
            if len(candidates) > 0: # stop as soon as we have candidates
                break

            found = []
            a = artist.lower()
            # workaround for many artists with the same name, e.g. Deimos (3)
            n = re.sub(r'\s+\(\d+\)$', '', result.name.lower()).strip()
            if a == n:
                releases = result.releases

            if releases is None:
                continue

            for i, release in enumerate(releases):
                if len(candidates) > 0 or i > 25: # give up after 25 iterations
                    return
                r = release.title.lower()
                s = searchParams['album'].lower()

                if s == r or r in s or s in r: # sometimes titles include extra info, e.g. EP
                    if hasattr(release, 'versions'):
                        self._siftReleases(release.versions)
                    else:
                        self._siftReleases([release])

    def search_album_title(self):
        searchParams = self.search_params
        candidates = self.candidates

        release = self.search_params['search']['release']
        logger.info('Searching by title: {}'.format(release))

        results = self.discogs_client.search(release, type='release')
        for i, result in enumerate(results):
            if len(candidates) == 0 or i > 25: # give up after 25 iterations
                master = self.get_master_release(result)
                if hasattr(master, 'versions'):
                    self._siftReleases(master.versions)
                else:
                    self._siftReleases([master])

    def search_switcher(self, types=None, count=0):
        """ Takes the search parameters and cycles through the various search
            strategies until we have some matching candidates.
        """
        if types is None:
            # types = ['all', 'master', 'artist', 'title']
            types = ['all', 'master']
        if len(types) > 0:
            type = types.pop(0)
            count = count + 1
            switcher = {
                'master': lambda: self.search_artist_title(type),
                'all': lambda: self.search_artist_title(type),
                'artist': lambda: self.search_artist(),
                'title': lambda: self.search_album_title(),
            }
            func = switcher.get(type, lambda: 'Invalid')
            try:
                func()
            except Exception as e:
                logger.warning('Search error ({}): {}'.format(type, e))
            if len(self.candidates) == 0:
                self.search_switcher(types, count)
            else:
                return
        else:
            return (len(self.candidates))

    def search_strings(self):
        """ Compile the search strings to be used from searchParams
        """
        searchParams = self.search_params
        searchParams['search'] = {}
        s = searchParams['search']
        va = ('various', 'various artists', 'va')
        if searchParams['albumartist'] is not None and searchParams['albumartist'].lower() in va:
            if len(searchParams['artists']) > 1:
                s['artist'] = ' '.join(searchParams['artists'][0:1]) # take the first couple of artists from the compilation
            elif len(searchParams['artists']) == 1:
                s['artist'] = searchParams['artist']
        elif searchParams['albumartist'] is not None and searchParams['albumartist'] != '':
            s['artist'] = searchParams['albumartist']
        elif searchParams['artist'] is not None and searchParams['artist'] != '':
            s['artist'] = searchParams['artist']

        s['artist'] = self.normalize(s['artist'])
        s['release'] = self.normalize(searchParams['album'])
        if s['artist'] in va:
            s['title'] = searchParams['tracks'][0]['title']
            s['artistRelease'] = self.normalize(' '.join((s['title'], s['release'])))
        else:
            s['artistRelease'] = self.normalize(' '.join((s['artist'], s['release'])))

    def search_discogs(self):
        """Search Discogs for a matching release using the gathered metadata."""
        searchParams = self.search_params
        logger.info('Searching Discogs for: artist="%s" album="%s"',
                    searchParams.get('artist', '?'), searchParams.get('album', '?'))

        self.candidates = {}
        self.no_duration_candidates = {}

        self.search_strings()
        self.search_switcher()

        candidates = self.candidates

        if not candidates and not self.no_duration_candidates:
            logger.warning('No matching release found on Discogs')
            return None

        # Tier-2 fallback: no release had Discogs duration data, rank by title similarity
        if not candidates:
            logger.info('No duration-matched candidates; falling back to %d no-duration candidate(s)',
                        len(self.no_duration_candidates))
            return self._select_by_metadata(self.no_duration_candidates)

        if len(candidates) == 1:
            result = list(candidates.values())[0]
            logger.info('Found 1 tier-1 candidate: [%s] — %s',
                        result.id, getattr(result, 'title', '?'))
            return result

        # Multiple tier-1 candidates: rank by composite score (track diff + metadata)
        logger.info('Found %d tier-1 candidates, selecting best match', len(candidates))
        scored = [
            (self._candidate_score(release, base_score=diff), release)
            for diff, release in candidates.items()
        ]
        scored.sort(key=lambda x: x[0])
        best_score, best = scored[0]
        logger.info('Selected [%s] composite score %.2f', best.id, best_score)
        return best


    def _siftReleases(self, releases):
        """Evaluate each release and file it into tier-1 or tier-2 candidates.

        Tier-1 (self.candidates): track count + length match; keyed by avg diff.
        Tier-2 (self.no_duration_candidates): count match, no Discogs duration data.
        """
        for release in releases:
            difference = self._compareRelease(release)
            if difference is False:
                continue
            elif difference < 0:
                # tier-2: negative encodes -(similarity/100)
                self.no_duration_candidates[release.id] = (release, abs(difference) * 100)
            else:
                while difference in self.candidates:
                    difference += 0.001
                self.candidates[difference] = release

    def _candidate_score(self, release, base_score=50.0):
        """Composite score for ranking candidates (lower is better).

        base_score is the avg track-length diff for tier-1 candidates, or a
        large sentinel (50.0) for tier-2 candidates that have no duration data.
        Year match, format match, and disc-count match each subtract a small
        bonus so that equally-close releases can be ranked by metadata.
        """
        score = float(base_score)
        searchParams = self.search_params
        try:
            data = release.data
            fmt_name = data.get('formats', [{}])[0].get('name', '').lower()
            qty = int(data.get('format_quantity', 1))
            year = release.year
        except Exception:
            return score

        local_year = searchParams.get('year')
        if local_year and str(year) == str(local_year):
            score -= 2.0

        is_vinyl = fmt_name in ('lp', 'vinyl', '12"', '7"', '10"')
        local_vinyl = (
            searchParams.get('media') == 'vinyl' or
            any('real_tracknumber' in t for t in searchParams.get('tracks', []))
        )
        if is_vinyl and local_vinyl:
            score -= 1.5
        elif fmt_name == 'cd' and not local_vinyl:
            score -= 1.0

        local_disc = searchParams.get('disc')
        if local_disc and qty == int(local_disc):
            score -= 0.5

        return score

    def _select_by_metadata(self, no_duration_candidates):
        """Pick the best tier-2 release: primary rank by title similarity, secondary by metadata.

        no_duration_candidates is the dict {release_id: (release, similarity_pct)}.
        """
        scored = []
        for release, similarity in no_duration_candidates.values():
            # Negate similarity so that higher similarity sorts first; use metadata
            # bonus (lower is better) as the tiebreaker.
            metadata_bonus = self._candidate_score(release, base_score=0.0)
            scored.append((-similarity, metadata_bonus, release))
        scored.sort(key=lambda x: (x[0], x[1]))
        best_similarity, _, best = scored[0]
        logger.info('Tier-2 selection: [%s] title similarity %.0f%%', best.id, -best_similarity)
        return best

    def _compareTitleSimilarity(self, local_tracks, discogs_tracks):
        """Average fuzzy title similarity (0–100) across tracks that have titles on both sides.

        Uses token_sort_ratio so word-order differences ("A Love Supreme Pt 1" vs
        "Pt. 1 A Love Supreme") don't penalise the score.  Returns 0.0 when neither
        side has any titles to compare.
        """
        total = 0.0
        count = 0
        for local, discogs_track in zip(local_tracks, discogs_tracks):
            lt = (local.get('title') or '').strip()
            dt = (discogs_track.get('title') or '').strip()
            if lt and dt:
                total += fuzz.token_sort_ratio(lt, dt)
                count += 1
        return total / count if count > 0 else 0.0

    def _compareRelease(self, release):
        """Compare local files against a single Discogs release.

        Return convention (lower is always better for the caller):
          float >= 0  — tier-1: avg track-length diff in seconds
          float < 0   — tier-2: -(similarity/100), i.e. abs()*100 = title similarity %
          False       — rejected
        """
        searchParams = self.search_params
        trackInfo = self._getTrackInfo(release)
        rid = release.id

        if len(trackInfo) == 0:
            logger.info('  [%s] rejected — no track info on Discogs', rid)
            return False

        local_count = len(searchParams['tracks'])
        if local_count != len(trackInfo):
            logger.info('  [%s] rejected — local has %d tracks, Discogs has %d',
                        rid, local_count, len(trackInfo))
            return False

        has_duration = any(t['duration'] is not None for t in trackInfo)
        if not has_duration:
            similarity = self._compareTitleSimilarity(searchParams['tracks'], trackInfo)
            if similarity > 0 and similarity < self.title_similarity_threshold:
                logger.info('  [%s] rejected — title similarity %.0f%% below threshold %.0f%%',
                            rid, similarity, self.title_similarity_threshold)
                return False
            logger.info('  [%s] tier-2 candidate — track count %d, title similarity %.0f%%',
                        rid, local_count, similarity)
            return -(similarity / 100.0)

        difference = self._compareTrackLengths(searchParams['tracks'], trackInfo)
        if difference < self.tracklength_tolerance:
            logger.info('  [%s] accepted — avg track length diff %.1fs', rid, difference)
            return difference

        logger.info('  [%s] rejected — avg track length diff %.1fs exceeds tolerance %s',
                    rid, difference, self.tracklength_tolerance)
        return False


    def _paddedHMS(self, string):
        ''' Returns a time string formatted "hh:mm:ss" cmpatible with
            strptime. If a Discogs track is over 60 minutes it is formatted
            as 63:00, we need to recalculate this as hh:mm:ss.
        '''
        dur = 0
        a = [int(s) for s in string.split(':')]
        while len(a) < 3:
            a.insert(0, 0)
        # recalculate: discogs tracks over 60 mins (i.e 61+ minutes)
        dur = (a[0] * 3600) + (a[1] * 60) + a[2]
        t = str(timedelta(seconds = dur))
        b = [int(s) for s in t.split(':')]
        while len(b) < 3:
            b.insert(0, 0)
        c = ['{:0>2}'.format(d) for d in b]
        return ':'.join(c)

    def _compareTrackLengths(self, current, imported):
        """Compare local tracklist against Discogs tracklist by track length.

        Only considers tracks where Discogs has duration data.  Returns the
        average absolute difference in seconds across those tracks, or inf
        when no comparable tracks exist.
        """
        total = 0.0
        count = 0
        for i, track in enumerate(current):
            if imported[i]['duration'] is None:
                continue
            difference = self._compareTimeDifference(track['duration'], imported[i]['duration'])
            total += difference.total_seconds()
            count += 1

        if count == 0:
            return float('inf')

        avg = total / count
        logger.info('avg track length diff: {:.1f}s over {} track(s)'.format(avg, count))
        return avg

    def _compareTimeDifference(self, current, imported):
        """ Compare the tracklengths between the gathered audio data and the
            Discogs tracklengths. Expect variation.  If no tracklengths return
            999
        """
        if current is not None and current != '' and imported is not None and imported != '':
            try:
                a = self._paddedHMS(current)
                b = self._paddedHMS(imported)
                timea = datetime.strptime(a, '%H:%M:%S')
                timeb = datetime.strptime(b, '%H:%M:%S')
                return timea - timeb if timea > timeb else timeb - timea
            except Exception as e:
                logger.debug('Track length comparison failed: %s', e)
                return timedelta(seconds=999)
        else:
            return timedelta(seconds=999)


    def _getTrackInfo(self, version):
        """Get track values from a release for length/count comparison.

        Pre-populates the release from the disk cache when available so no
        API call is made.  Saves to cache afterwards so subsequent runs are
        free.
        """
        # Pre-populate data from cache — if tracklist is already present,
        # version.tracklist returns it without making an API call.
        if self._release_cache:
            cached = self._release_cache.get(version.id)
            if cached is not None:
                version.data.update(cached)

        trackinfo = []
        discogs_tracks = version.tracklist   # may trigger API fetch if not cached
        exclude = ("Video", "video", "DVD")

        for track in discogs_tracks:
            if track.data['type_'] in ('heading'):
                logger.debug('ignoring non-track info: {}'.format(getattr(track, 'title')))
                continue
            if track.position.startswith(exclude) or track.position.endswith(exclude):
                logger.debug('ignoring video track: {}'.format(getattr(track, 'title')))
                continue
            discogs_info = {}
            for key in ['position', 'title']:
                discogs_info[key] = getattr(track, key)
            dur = track.duration
            discogs_info['duration'] = dur if (dur is not None and str(dur) != '') else None
            trackinfo.append(discogs_info)

        # Save fully-loaded release data so subsequent runs skip the API call
        if self._release_cache:
            self._release_cache.put(version.id, version.data)

        return trackinfo
