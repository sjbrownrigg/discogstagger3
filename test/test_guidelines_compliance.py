"""Tests for Discogs submission-guidelines compliance improvements (3.0.3).

Covers:
  - Catno insertion-order preserved (no alphabetical sort)
  - ANV used in album_artists() / album_artist_display() / artists()
  - use_anv=False falls back to canonical name
  - Vinyl side-based position parsing (A1, B3, C2)
  - Dot-notation position parsing (1.1, 2.3)
  - Hyphenated position parsing still works
  - parse_extraartists() role-to-tag mapping
  - composer tag from track-level extraartists (Written-By with ANV)
  - Release status read from fixture
  - Barcode extracted from identifiers
  - disctotal extended media coverage
"""
import os
import sys
import unittest

parentdir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parentdir)

from _common_test import TestDummyResponse, DummyDiscogsAlbum
from discogstagger.discogsalbum import DiscogsAlbum
from discogstagger.discogs_utils import parse_extraartists


def _album(release_id, use_anv=True):
    resp = TestDummyResponse(release_id)
    dda = DummyDiscogsAlbum(resp)
    dda.use_anv = use_anv
    return dda.map()


# ---------------------------------------------------------------------------
# Catno insertion order
# ---------------------------------------------------------------------------

class TestCatnoOrder(unittest.TestCase):
    """album.catnumbers preserves Discogs insertion order (primary label first)."""

    def test_first_catno_is_primary(self):
        # Release 3083 has two labels: MOLECD023-2 (primary) then MOLE023-2.
        # Without sort, MOLECD023-2 must remain first.
        album = _album('3083')
        self.assertEqual(album.catnumbers[0], 'MOLECD023-2')

    def test_insertion_order_preserved(self):
        album = _album('3083')
        self.assertEqual(album.catnumbers, ['MOLECD023-2', 'MOLE023-2'])


# ---------------------------------------------------------------------------
# ANV — Artist Name Variation
# ---------------------------------------------------------------------------

class TestANV(unittest.TestCase):
    """DiscogsAlbum uses ANV when use_anv=True, canonical name when False."""

    def test_anv_used_when_enabled(self):
        # Release 112146: canonical='Artful Dodger', ANV='Artful Dodger, The'
        # ANV is normalised: "Artist, The" → "The Artist"
        album = _album('112146', use_anv=True)
        self.assertIn('The Artful Dodger', album.artists)

    def test_canonical_used_when_anv_disabled(self):
        album = _album('112146', use_anv=False)
        # clean_name('Artful Dodger') = 'Artful Dodger'
        self.assertIn('Artful Dodger', album.artists)
        self.assertNotIn('The Artful Dodger', album.artists)

    def test_anv_in_artist_display(self):
        # artist display string uses normalised ANV
        album = _album('112146', use_anv=True)
        self.assertIn('The Artful Dodger', album.artist)

    def test_anv_two_artists(self):
        # Release 2454735: Frank Zappa ANV='Zappa', joined with &
        album = _album('2454735', use_anv=True)
        self.assertIn('Zappa', album.artists)

    def test_canonical_fallback_when_anv_empty(self):
        # When ANV is empty, canonical name should be used regardless of use_anv
        album = _album('3083', use_anv=True)
        # Yonderboi has no ANV — clean_name('Yonderboi') = 'Yonderboi'
        self.assertIn('Yonderboi', album.artists)


# ---------------------------------------------------------------------------
# disc_and_track_no — vinyl and dot notation
# ---------------------------------------------------------------------------

class TestDiscAndTrackNo(unittest.TestCase):
    """disc_and_track_no() handles vinyl side positions and dot notation."""

    def setUp(self):
        resp = TestDummyResponse('3083')
        dda = DummyDiscogsAlbum(resp)
        self._dda = dda

    def _pos(self, position):
        return self._dda.disc_and_track_no(position)

    # Vinyl side-based
    def test_vinyl_a_side(self):
        r = self._pos('A1')
        self.assertEqual(r['discnumber'], 1)
        self.assertEqual(r['tracknumber'], '1')

    def test_vinyl_b_side(self):
        r = self._pos('B3')
        self.assertEqual(r['discnumber'], 2)
        self.assertEqual(r['tracknumber'], '3')

    def test_vinyl_c_side(self):
        r = self._pos('C2')
        self.assertEqual(r['discnumber'], 3)
        self.assertEqual(r['tracknumber'], '2')

    def test_vinyl_d_side(self):
        r = self._pos('D1')
        self.assertEqual(r['discnumber'], 4)
        self.assertEqual(r['tracknumber'], '1')

    def test_vinyl_lowercase(self):
        r = self._pos('a2')
        self.assertEqual(r['discnumber'], 1)
        self.assertEqual(r['tracknumber'], '2')

    # Dot notation
    def test_dot_notation_disc2(self):
        r = self._pos('2.3')
        self.assertEqual(r['discnumber'], '2')
        self.assertEqual(r['tracknumber'], '3')

    def test_dot_notation_disc1(self):
        r = self._pos('1.1')
        self.assertEqual(r['discnumber'], '1')
        self.assertEqual(r['tracknumber'], '1')

    # Hyphenated (regression: must still work)
    def test_cd_hyphen(self):
        r = self._pos('CD1-05')
        self.assertEqual(r['discnumber'], '1')
        self.assertEqual(r['tracknumber'], '05')

    def test_numeric_hyphen(self):
        r = self._pos('2-08')
        self.assertEqual(r['discnumber'], '2')
        self.assertEqual(r['tracknumber'], '08')

    # Bare number (single disc)
    def test_bare_number(self):
        r = self._pos('7')
        self.assertEqual(r['discnumber'], 1)
        self.assertEqual(r['tracknumber'], '7')


# ---------------------------------------------------------------------------
# parse_extraartists() utility
# ---------------------------------------------------------------------------

class TestParseExtraartists(unittest.TestCase):
    """parse_extraartists() maps Discogs role strings to composer/lyricist."""

    def _parse(self, entries):
        return parse_extraartists(entries)

    def test_composed_by(self):
        result = self._parse([{'name': 'John Williams', 'anv': '', 'role': 'Composed By'}])
        self.assertEqual(result['composers'], ['John Williams'])
        self.assertEqual(result['lyricists'], [])

    def test_written_by_hyphen(self):
        result = self._parse([{'name': 'Lennon', 'anv': '', 'role': 'Written-By'}])
        self.assertEqual(result['composers'], ['Lennon'])

    def test_written_by_spaces(self):
        result = self._parse([{'name': 'McCartney', 'anv': '', 'role': 'Written By'}])
        self.assertEqual(result['composers'], ['McCartney'])

    def test_lyrics_by(self):
        result = self._parse([{'name': 'Bernie Taupin', 'anv': '', 'role': 'Lyrics By'}])
        self.assertEqual(result['lyricists'], ['Bernie Taupin'])
        self.assertEqual(result['composers'], [])

    def test_anv_preferred_over_name(self):
        result = self._parse([{'name': 'Balázs Zságer', 'anv': 'Zságer', 'role': 'Written-By'}])
        self.assertEqual(result['composers'], ['Zságer'])

    def test_role_with_qualifier_stripped(self):
        result = self._parse([{'name': 'Someone', 'anv': '', 'role': 'Composed By [Tracks 1-3]'}])
        self.assertEqual(result['composers'], ['Someone'])

    def test_multiple_composers(self):
        entries = [
            {'name': 'A', 'anv': '', 'role': 'Composed By'},
            {'name': 'B', 'anv': '', 'role': 'Music By'},
        ]
        result = self._parse(entries)
        self.assertEqual(result['composers'], ['A', 'B'])

    def test_unrelated_role_ignored(self):
        result = self._parse([{'name': 'Dave', 'anv': '', 'role': 'Producer'}])
        self.assertEqual(result['composers'], [])
        self.assertEqual(result['lyricists'], [])

    def test_empty_list(self):
        result = self._parse([])
        self.assertEqual(result, {'composers': [], 'lyricists': []})

    def test_none_input(self):
        result = self._parse(None)
        self.assertEqual(result, {'composers': [], 'lyricists': []})

    def test_track_extraartists_from_fixture(self):
        # Release 3083, track 2 has Written-By credits with ANVs
        album = _album('3083')
        track2 = album.discs[0].tracks[1]
        eas = track2.extraartists or []
        result = parse_extraartists(eas)
        # Should find the ANV-named Written-By credits
        self.assertTrue(len(result['composers']) > 0)
        # ANV 'Zságer' should be preferred over canonical 'Balázs Zságer'
        self.assertIn('Zságer', result['composers'])


# ---------------------------------------------------------------------------
# Barcode and status from release identifiers / metadata
# ---------------------------------------------------------------------------

class TestReleaseIdentifiers(unittest.TestCase):
    """album.barcode and album.status are populated from the Discogs data."""

    def test_barcode_extracted(self):
        # Release 3083 has Barcode '4 017866 921482' as the first identifier
        album = _album('3083')
        self.assertIsNotNone(album.barcode)
        self.assertIn('4017866921482', album.barcode.replace(' ', ''))

    def test_status_extracted(self):
        album = _album('3083')
        self.assertIsNotNone(album.status)
        self.assertIsInstance(album.status, str)
        self.assertTrue(len(album.status) > 0)


# ---------------------------------------------------------------------------
# disctotal media type coverage
# ---------------------------------------------------------------------------

class TestDisctotalMedia(unittest.TestCase):
    """disctotal counts a broader set of physical media formats."""

    def _make_release_with_format(self, format_name, qty=1):
        """Return a minimal mock release object with one format."""
        import types
        release = types.SimpleNamespace()
        release.id = 0
        release.title = 'Test'
        release.data = {
            'artists':  [{'name': 'Various', 'anv': '', 'join': '', 'role': ''}],
            'formats':  [{'name': format_name, 'qty': str(qty)}],
            'labels':   [],
            'genres':   [],
            'identifiers': [],
            'extraartists': [],
            'tracklist': [],
        }
        release.tracklist = []
        da = DiscogsAlbum(release)
        return da

    def test_cd_counted(self):
        self.assertEqual(self._make_release_with_format('CD', 2).disctotal, 2)

    def test_sacd_counted(self):
        self.assertEqual(self._make_release_with_format('SACD', 1).disctotal, 1)

    def test_cassette_counted(self):
        self.assertEqual(self._make_release_with_format('Cassette', 3).disctotal, 3)

    def test_dat_counted(self):
        self.assertEqual(self._make_release_with_format('DAT', 1).disctotal, 1)

    def test_minidisc_counted(self):
        self.assertEqual(self._make_release_with_format('Minidisc', 1).disctotal, 1)

    def test_dvd_audio_counted(self):
        self.assertEqual(self._make_release_with_format('DVD-Audio', 1).disctotal, 1)

    def test_blu_ray_counted(self):
        self.assertEqual(self._make_release_with_format('Blu-ray', 1).disctotal, 1)

    def test_file_is_one_disc(self):
        self.assertEqual(self._make_release_with_format('File', 2).disctotal, 1)


if __name__ == '__main__':
    unittest.main()
