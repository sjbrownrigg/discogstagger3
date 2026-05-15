import logging
import re
import os

from datetime import timedelta, datetime

from discogstagger.mediafile_ext import MediaFile
from discogstagger.album import Album, Disc, Track
from discogstagger.discogs_utils import strip_discogs_id_suffix

# Connector classes live in discogs_connector; re-exported here for backward compat.
from discogstagger.discogs_connector import (  # noqa: F401
    DiscogsConnector, LocalDiscogsConnector, DummyResponse,
)

logger = logging.getLogger(__name__)


class AlbumError(Exception):
    """Raised when album mapping or processing fails."""
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)


class DiscogsAlbum(object):
    """Wraps the Discogs API client, mapping release data to the Album/Track
    model used by the tagger."""

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
        album.release_date = self.release_date
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
    def release_date(self):
        """Return the full release date from the Discogs 'released' field.

        Normalises the various formats Discogs uses:
          2004-06-21  → '2004-06-21'
          2004-06-00  → '2004-06'   (zero day = month precision only)
          2004-00-00  → '2004'      (zero month = year precision only)
          2004        → '2004'
          0 / ''      → None        (unknown)
        """
        raw = str(self.release.data.get('released', '') or '').strip()
        if not raw or raw == '0':
            return None
        parts = raw.split('-')
        # Drop trailing zero components (day=00, month=00)
        while parts and parts[-1] in ('00', '0'):
            parts.pop()
        result = '-'.join(parts)
        # Must at least be a 4-digit year
        if not re.match(r'^\d{4}', result):
            return None
        return result

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

        logger.info("determined %d no of discs total", discno)
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
                logger.debug("x: %s", x)
                if last_artist:
                    last_artist = last_artist + " " + x
                else:
                    last_artist = x
            else:
                if last_artist is not None:
                    logger.debug("name: %s", x.name)
                    concatString = " "
                    if join is not None:
                        concatString = " " + join + " "

                    last_artist = last_artist + concatString + self.clean_name(x.name)
                    artists.append(last_artist)
                    last_artist = None
                else:
                    join = x.data['join']
                    last_artist = self.clean_name(x.name)

            logger.debug("last_artist: %s", last_artist)

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


        logger.error("Unable to match multi-disc track/position")
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
                logger.error("position is null, shouldn't be...")

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

            if discsubtitle:
                track.discsubtitle = discsubtitle[-1]
                # if disc.discnumber == len(discsubtitle):
                disc.discsubtitle = discsubtitle[-1]
                logger.debug("discsubtitle: {0}".format(disc.discsubtitle))

            track.sort_artist = sort_artist
            disc.tracks.append(track)
        disc_list.append(disc)
        return disc_list

    def remove_duplicate_items(self, duplicates_list):
        """Remove duplicates while preserving insertion order."""
        return list(dict.fromkeys(duplicates_list))

    def clean_duplicate_handling(self, clean_target):
        """Remove Discogs disambiguation suffix, e.g. 'Goldie (12)' → 'Goldie'."""
        return strip_discogs_id_suffix(clean_target)

    _THE_SUFFIX_RE = re.compile(r"(.*),\sThe$")

    def clean_name(self, clean_target):
        """Clean a Discogs artist or label name.

        Strips disambiguation suffixes ('Goldie (12)' → 'Goldie') and
        normalises 'Artist, The' → 'The Artist'.
        """
        clean_target = self.clean_duplicate_handling(clean_target)
        return self._THE_SUFFIX_RE.sub(r"The \g<1>", clean_target)

