import logging
import re
import os

import requests

from ext.mediafile import MediaFile

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
        self._user_token = None

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
        logger.info('Fetching release %s from Discogs' % release_id)
        return self.discogs_client.release(int(release_id))

    def fetch_image(self, image_dir, image_url):
        """Download a Discogs image. Requires authentication."""
        if not self.discogs_auth:
            logger.error('Not authenticated — cannot download image, skipping')
            return
        try:
            headers = {'User-Agent': self.user_agent}
            params = {'token': self._user_token} if self._user_token else {}
            response = requests.get(image_url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            with open(image_dir, 'wb') as fh:
                fh.write(response.content)
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

        json_file = open(json_file_path, "r")

        self.status_code = 200
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
        album.catnumbers = self.remove_duplicate_items([catno for name, catno in self.labels_and_numbers])
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
            logging.warning("no country set for relid %s" % self.release.id)
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
        """ return a single list of images for the given album """

        try:
            return [x["uri"] for x in self.release.data["images"]]
        except KeyError:
            pass

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
                if not last_artist == None:
                    logger.debug("name: %s" % x.name)
                    concatString = " "
                    if not join == None:
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

        files = self._getMusicFiles(source_dir)
        files.sort()
        subdirectories = self._fetchSubdirectories(source_dir, files)
        searchParams = self.search_params
        searchParams['sourcedir'] = source_dir

        trackcount = 0
        discnumber = 0
        searchParams['artists'] = []
        for i, file in enumerate(files):
            trackcount = trackcount + 1
            metadata = MediaFile(os.path.join(file))
            for a in metadata.artist:
                searchParams['artists'].append(a)
            searchParams['albumartist'] = ', '.join(set(metadata.albumartist))
            searchParams['album'] = metadata.album
            searchParams['album'] = re.sub(r'\[.*?\]', '', searchParams['album'])
            searchParams['year'] = metadata.year
            searchParams['date'] = metadata.date
            # print(file)
            # print(subdirectories)
            if metadata.disc is not None and int(metadata.disc) > 1:
                searchParams['disc'] = metadata.disc
            elif metadata.disc is None and len(set(subdirectories)) > 1:
                trackdisc = re.search(r'(?i)^(cd|disc)\s?(?P<discnumber>[0-9]{1,2})', subdirectories[i])
                searchParams['disc'] = int(trackdisc.group('discnumber'))
            # print(searchParams)
            if 'disc' in searchParams.keys() and searchParams['disc'] != discnumber:
                trackcount = 1
            if 'tracks' not in searchParams:
                searchParams['tracks'] = []
            tracknumber = str(searchParams['disc']) + '-' if 'disc' in searchParams.keys() else ''
            if metadata.track is not None:
                tracknumber += str(metadata.track)
            else:
                tracknumber += str(trackcount)

            # print(searchParams)
            trackInfo = {}
            if re.search(r'(?i)^[a-z]', str(metadata.track)):
                trackInfo['real_tracknumber'] = metadata.track
            trackInfo['position'] = tracknumber
            trackInfo['duration'] = str(timedelta(seconds = round(metadata.length, 0)))
            trackInfo['title'] = metadata.title
            trackInfo['artist'] = metadata.artist # useful for compilations
            searchParams['tracks'].append(trackInfo)
        searchParams['artists'] = list(dict.fromkeys(searchParams['artists']))
        searchParams['artist'] = ', '.join(searchParams['artists'])

        if len(searchParams['artists']) == 0 \
        and ('albumartist' not in searchParams or searchParams['albumartist'] == '') \
        and ('album' not in searchParams or searchParams['album'] == ''):
            logger.warninging('No metadata available in the audio files')
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

    def search_artist_title(self, type):
        searchParams = self.search_params
        candidates = self.candidates
        s = self.search_params['search']

        logger.info('Searching by artist and title ({}): {}'.format(type, s['artistRelease']))

        results = self.discogs_client.search(s['artistRelease'], type=type)

        # print(len(results))
        # print(dir(results))
        # print(results[0].id)

        for idx, result in enumerate(results):
            if len(candidates) > 0: # stop if we have already found some candidates
                continue

            if hasattr(result, '__class__') and 'Artist' in str(result.__class__):
                continue

            master = self.get_master_release(result)
            if hasattr(master, 'versions'):
                self._siftReleases(master.versions)
            else:
                if self._compareRelease(master) is not False:
                    candidates[master.id] = master


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
            if len(candidates) > 0: # stop if we have found some candidates
                continue

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
        logger.info('Searching Discogs for: artist="{}" album="{}"'.format(
            searchParams.get('artist', '?'), searchParams.get('album', '?')))

        self.candidates = {}
        candidates = self.candidates

        self.search_strings()
        self.search_switcher()

        if len(candidates) == 0:
            logger.warning('No matching release found on Discogs')
            return None

        if len(candidates) == 1:
            result = list(candidates.values())[0]
            logger.info('Found 1 candidate: {} — {}'.format(result.id, getattr(result, 'title', '?')))
            return result

        logger.info('Found {} candidates, selecting best match'.format(len(candidates)))
        # TODO: find a better way of sifting through multiple positive matches
        if len(candidates) > 1:
            qual = {}
            for id in candidates.keys():
                qual[id] = {}
                qual[id] = {
                    'format': candidates[id].data['formats'][0]['name'],
                    'quantity': candidates[id].data['format_quantity'],
                    'year': candidates[id].year
                    }

            ''' Prioritise year match and CD formats,
                QUESTION: How do we prioritrise vinyl or other formats?
            '''
            for k in qual.keys():
                if (searchParams['year'] == qual[k]['year']) and \
                (qual[k]['format'].lower() in ('lp', 'vinyl') and \
                (('media' in searchParams and searchParams['media'] == 'vinyl' ) or \
                'real_tracknumber' in searchParams['tracks'][0])):
                    return candidates[k]

            for k in qual.keys():
                if (searchParams['year'] == qual[k]['year']) and \
                (qual[k]['format'].lower() in ('lp', 'vinyl') and \
                (('media' in searchParams and searchParams['media'] == 'vinyl' ) or \
                'real_tracknumber' in searchParams['tracks'][0])):
                    return candidates[k]

            for k in qual.keys():
                if (qual[k]['format'].lower() in ('lp', 'vinyl') and \
                (('media' in searchParams and searchParams['media'] == 'vinyl' ) or \
                'real_tracknumber' in searchParams['tracks'][0])):
                    return candidates[k]

            for k in qual.keys():
                if 'disc' in searchParams.keys() and \
                searchParams['disc'] == qual[k]['quantity'] and \
                searchParams['year'] == qual[k]['year']:
                    return candidates[k]

            for k in qual.keys():
                if searchParams['year'] == qual[k]['year'] and \
                qual[k]['format'] in ('CD'):
                    return candidates[k]

            for k in qual.keys():
                if searchParams['year'] == qual[k]['year']:
                    return candidates[k]

            for k in qual.keys():
                if qual[k]['format'].lower() in ('cd'):
                    return candidates[k]

            # last resort, return the first one
            return list(candidates.values())[0]

        else:
            return None


    def _siftReleases(self, releases):
        """ Return candidates in a dict, keys are the quality match value.  Because
            we cannot have duplicate keys for those that match equally well, we will
            give the quality value a slight increase to keep them grouped together.
        """
        candidates = self.candidates
        temp = {}
        for release in releases:
            difference = self._compareRelease(release)
            if difference is not None and difference is not False:
                while difference in candidates.keys():
                    difference = difference + 0.001
                candidates[difference] = release

    def _compareRelease(self, release):
        ''' Compare the current track with a single release from Discogs.
            Current strategy is to compare track numbers and track lengths.
        '''
        searchParams = self.search_params
        trackInfo = self._getTrackInfo(release)
        if len(trackInfo) == 0:
            logger.info('Release rejected because there is no track duration information')
            return False
        elif len(searchParams['tracks']) == len(trackInfo):
            logger.info('Same number of tracks between source {} and release {}'.format(len(searchParams['tracks']), len(trackInfo)))
            difference = self._compareTrackLengths(searchParams['tracks'], trackInfo)
            if difference < self.tracklength_tolerance:
                logger.info('adding relid to the list of candidates: {}'.format(release.id))
                return difference
        else:
            logger.info('Number of tracks does not match between source {} and release {}'.format(len(searchParams['tracks']), len(trackInfo)))
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
        """ Compare original tracklist against discogs tracklist, by comparing
            the track lengths. Some releases have tracks in different order,
            so we need to filter those out.  Returns the highest time discrepancy.
        """
        tolerance = 0.0

        # try averaging the tracklength variation out by the number of tracks
        tracktotal = len(current)
        for i, track in enumerate(current):
            """ some tracks have alphanumerical identifiers,
                e.g. vinyl, cassettes
            """
            difference = self._compareTimeDifference(track['duration'], imported[i]['duration'])
            if difference.total_seconds() > tolerance:
                tolerance = tolerance + difference.total_seconds()

        logger.info('tracklength tolerance before averaging out by the number of tracks:  {}'.format(tolerance))
        tolerance = tolerance / tracktotal
        logging.debug('tracklength tolerance for release (change if there are any matching issues):  {}'.format(tolerance))
        logger.info('tracklength tolerance for release (change if there are any matching issues):  {}'.format(tolerance))
        return tolerance

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
                print(e)
        else:
            return timedelta(seconds = 999)


    def _getTrackInfo(self, version):
        """ Get the track values from the release, so that we can compare them
            to what we have got.  Remove extra info appearing with empty track
            number, e.g. Bonus tracks, or section titles.
        """
        trackinfo = []
        discogs_tracks = version.tracklist
        exclude = ("Video", "video", "DVD")

        for track in discogs_tracks:
            if track.data['type_'] in ('heading'):
                logger.debug('ignoring non-track info: {}'.format(getattr(track, 'title')))
                continue
            if track.position.startswith(exclude) or track.position.endswith(exclude):
                logger.debug('ignoring video track: {}'.format(getattr(track, 'title')))
                continue
            if track.duration == None or str(track.duration) == '':
                logger.debug('ignoring tracks without duration: {}'.format(getattr(track, 'title')))
                continue
            discogs_info = {}
            for key in ['position', 'duration', 'title']:
                discogs_info[key] = getattr(track, key)
            trackinfo.append(discogs_info)
        return trackinfo
