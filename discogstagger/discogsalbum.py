import logging
import re
import os

import requests

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
        album._artist_display = self.album_artist_display(self.release.artists)

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
        """Return individual artist names for the albumartists multi-value tag."""
        artists = []
        for x in artist_data:
            if isinstance(x, str):
                continue
            try:
                artists.append(self.clean_name(x.name))
            except AttributeError:
                pass
        return artists

    def album_artist_display(self, artist_data):
        """Build the full display string for the albumartist tag and format vars.

        Uses the Discogs join field ('Feat.', '&', 'vs.', …) when present.
        Returns empty string when Discogs provides no join between multiple
        artists — the caller (TaggerUtils) then applies the configured
        join_artists separator or falls back to the first artist name alone.

        Debug-level logs show the raw name/join/anv from Discogs so join
        field problems can be diagnosed.
        """
        parts = []  # list of (clean_name, join_after)

        for x in artist_data:
            if isinstance(x, str):
                # Legacy inline-string format: [Artist, "Feat.", Artist]
                if parts:
                    name, _ = parts[-1]
                    parts[-1] = (name, x.strip())
                continue
            try:
                name = self.clean_name(x.name)
            except AttributeError:
                continue
            raw_join = x.data.get('join', '').strip()
            logger.debug("album-artist raw: name=%r join=%r anv=%r",
                         name, raw_join, x.data.get('anv', ''))
            parts.append((name, raw_join))

        if not parts:
            return ''
        if len(parts) == 1:
            return parts[0][0]

        # Combine only when at least one meaningful join is present between artists
        meaningful = any(j and j != ',' for _, j in parts[:-1])
        if not meaningful:
            logger.debug("album-artist: Discogs provides no join text — "
                         "TaggerUtils will apply join_artists or use first artist")
            return ''

        result = parts[0][0]
        for i in range(1, len(parts)):
            _, join_before = parts[i - 1]
            sep = f' {join_before} ' if join_before and join_before != ',' else ' '
            result = result + sep + parts[i][0]

        logger.debug("album-artist display: %r", result)
        return result

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

        if last_artist is not None:
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
                track = Track(i + 1, t.title.strip(), artists)
                # track._artist_display left None; track.artist uses first_of(artists)
                # which already embeds the join from self.artists()
            else:
                artists = album.artists
                sort_artist = album.sort_artist
                track = Track(i + 1, t.title.strip(), artists)
                # Inherit album's display string (Discogs join or override applied later)
                track._artist_display = album.artist

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

