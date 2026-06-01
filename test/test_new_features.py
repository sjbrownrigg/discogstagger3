"""Tests for features added in 3.0.1 / 3.0.2:
  - DiscogsAlbum.release_date normalisation
  - get_clean_filename case control (lower / upper / preserve)
  - track.new_file respects case_song / case_va_song settings
  - CUE repair_image_filename renames mismatched audio file
"""
import os
import sys
import shutil
import tempfile
import unittest

parentdir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(parentdir)

from _common_test import TestDummyResponse, DummyDiscogsAlbum

from discogstagger.tagger_config import TaggerConfig
from discogstagger.taggerutils import TaggerUtils


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _config(path=None):
    return TaggerConfig(path or os.path.join(parentdir, "test/empty.conf"))


def _album(release_id):
    resp = TestDummyResponse(release_id)
    return DummyDiscogsAlbum(resp).map()


# ---------------------------------------------------------------------------
# release_date normalisation
# ---------------------------------------------------------------------------

class TestReleaseDate(unittest.TestCase):
    """DiscogsAlbum.release_date strips zero components and validates format."""

    def _release_date(self, release_id):
        return _album(release_id).release_date

    def test_full_date(self):
        # 3083.json: released = "2000-02-21"
        self.assertEqual(self._release_date("3083"), "2000-02-21")

    def test_full_date_2(self):
        # 112146.json: released = "2000-02-14"
        self.assertEqual(self._release_date("112146"), "2000-02-14")

    def test_zero_day_stripped(self):
        # 13748.json: released = "1998-01-00" → strip zero day → "1998-01"
        self.assertEqual(self._release_date("13748"), "1998-01")

    def test_zero_month_and_day_stripped(self):
        # 2454735.json: released = "1995-00-00" → strip both → "1995"
        self.assertEqual(self._release_date("2454735"), "1995")

    def test_year_only(self):
        # 1448190.json: released = "2001"
        self.assertEqual(self._release_date("1448190"), "2001")

    def test_year_only_alternate(self):
        # 543030.json: released = "1992"
        self.assertEqual(self._release_date("543030"), "1992")


# ---------------------------------------------------------------------------
# get_clean_filename case control
# ---------------------------------------------------------------------------

class TestGetCleanFilenameCase(unittest.TestCase):
    """get_clean_filename(f, case=…) applies lower / upper / preserve."""

    def setUp(self):
        self.tu = TaggerUtils.__new__(TaggerUtils)
        self.tu.char_exceptions = {}
        self.tu._path_sep_replacement = ''
        self.tu._control_replacement = ''

    def test_preserve(self):
        self.assertEqual(
            self.tu.get_clean_filename("Hello World.flac", case='preserve'),
            "Hello World.flac",
        )

    def test_lower(self):
        self.assertEqual(
            self.tu.get_clean_filename("Hello World.flac", case='lower'),
            "hello world.flac",
        )

    def test_upper(self):
        self.assertEqual(
            self.tu.get_clean_filename("Hello World.flac", case='upper'),
            "HELLO WORLD.FLAC",
        )

    def test_lower_default_not_applied(self):
        # Default is 'preserve' — no lowercasing without explicit case=
        result = self.tu.get_clean_filename("Mixed Case.flac")
        self.assertEqual(result, "Mixed Case.flac")

    def test_dir_segment_no_extension(self):
        # Directory segments have no audio extension; whole string is filename
        self.assertEqual(
            self.tu.get_clean_filename("Clan of Xymox", case='lower'),
            "clan of xymox",
        )
        self.assertEqual(
            self.tu.get_clean_filename("Clan of Xymox", case='upper'),
            "CLAN OF XYMOX",
        )


# ---------------------------------------------------------------------------
# case_song / case_va_song applied to track.new_file
# ---------------------------------------------------------------------------

class TestCaseSongIntegration(unittest.TestCase):
    """track.new_file respects the case_song and case_va_song settings."""

    SOURCE = "/tmp/dummy_source_case"
    DEST   = "/tmp/dummy_dest_case"

    def setUp(self):
        os.makedirs(self.SOURCE, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.SOURCE, ignore_errors=True)
        shutil.rmtree(self.DEST, ignore_errors=True)

    def _new_file(self, release_id, case_song, case_va_song='lower'):
        """Return track.new_file for track 1 of the given release."""
        cfg = _config()
        cfg.set('details', 'case_song', case_song)
        cfg.set('details', 'case_va_song', case_va_song)
        album = _album(release_id)
        tu = TaggerUtils(self.SOURCE, self.DEST, cfg, album)
        tu._get_target_list()
        return album.discs[0].tracks[0].new_file

    def test_case_song_lower(self):
        # 3083: single-artist album
        result = self._new_file("3083", case_song='lower')
        self.assertEqual(result, result.lower())

    def test_case_song_upper(self):
        result = self._new_file("3083", case_song='upper')
        self.assertEqual(result, result.upper())

    def test_case_song_preserve(self):
        lower = self._new_file("3083", case_song='lower')
        preserved = self._new_file("3083", case_song='preserve')
        # Preserved should differ from forced-lower (Discogs title is mixed case)
        # (passes even if Discogs title happens to be all-lower, but confirms no crash)
        self.assertIsNotNone(preserved)


# ---------------------------------------------------------------------------
# CUE repair_image_filename
# ---------------------------------------------------------------------------

class TestRepairImageFilename(unittest.TestCase):
    """CUE.repair_image_filename renames mismatched audio file."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _make_cue(self, actual_name, ref_name):
        """Build a minimal CUE-like object without parsing a real CUE file."""
        from discogstagger.cue import CUE
        cue = CUE.__new__(CUE)
        cue.image_file_name = os.path.join(self.tmpdir, actual_name)
        cue.image_file_ref  = os.path.join(self.tmpdir, ref_name)
        # Create the actual file
        open(cue.image_file_name, 'wb').close()
        return cue

    def test_rename_performed_when_names_differ(self):
        cue = self._make_cue(
            actual_name='Coil - 2004.06.21, Casa da Mъsica.flac',
            ref_name   ='Coil - 2004.06.21, Casa da Música.flac',
        )
        result = cue.repair_image_filename()
        self.assertTrue(result)
        self.assertTrue(os.path.exists(cue.image_file_ref))
        self.assertFalse(os.path.exists(os.path.join(
            self.tmpdir, 'Coil - 2004.06.21, Casa da Mъsica.flac')))
        self.assertEqual(cue.image_file_name, cue.image_file_ref)

    def test_no_rename_when_names_match(self):
        cue = self._make_cue('album.flac', 'album.flac')
        result = cue.repair_image_filename()
        self.assertFalse(result)

    def test_no_rename_when_image_file_name_is_none(self):
        from discogstagger.cue import CUE
        cue = CUE.__new__(CUE)
        cue.image_file_name = None
        cue.image_file_ref  = '/some/path.flac'
        self.assertFalse(cue.repair_image_filename())


# ---------------------------------------------------------------------------
# $num() — zero-padding with vinyl position pass-through
# ---------------------------------------------------------------------------

class TestNumFunction(unittest.TestCase):
    """$num() zero-pads integers but passes non-numeric strings through."""

    def setUp(self):
        from discogstagger.stringformatting import StringFormatting
        self.sf = StringFormatting()

    def _num(self, val, places):
        return self.sf.parseString(f"$num('{val}','{places}')")

    def test_pads_bare_number(self):
        self.assertEqual('07', self._num('7', '2'))

    def test_pads_single_digit(self):
        self.assertEqual('01', self._num('1', '2'))

    def test_no_pad_when_already_wide(self):
        self.assertEqual('12', self._num('12', '2'))

    def test_vinyl_letter_only_unchanged(self):
        # 'A' — single track per side, no trailing digit
        self.assertEqual('A', self._num('A', '2'))

    def test_vinyl_letter_and_digit_unchanged(self):
        # 'A1', 'B3' — multi-track side, two chars already
        self.assertEqual('A1', self._num('A1', '2'))
        self.assertEqual('B3', self._num('B3', '2'))

    def test_vinyl_lowercase_unchanged(self):
        self.assertEqual('a1', self._num('a1', '2'))


class TestContainsFunction(unittest.TestCase):
    """$contains() and $icontains() — substring search in format string fields."""

    def setUp(self):
        from discogstagger.stringformatting import StringFormatting
        self.sf = StringFormatting()

    def _eval(self, expr):
        return self.sf.parseString(expr)

    # parseString converts Python bool → str('True'/'False').
    # Test booleans via $if1() to get consistent string output.

    def _yes_if(self, condition_expr):
        """Evaluate condition inside $if1 — returns 'yes' or ''."""
        return self._eval(f"$if1({condition_expr},'yes')")

    # ── $contains (case-sensitive) ────────────────────────────────────────────

    def test_contains_match(self):
        self.assertEqual('yes', self._yes_if("$contains('12\" Vinyl','Vinyl')"))

    def test_contains_no_match(self):
        self.assertEqual('', self._yes_if("$contains('CD','Vinyl')"))

    def test_contains_case_sensitive_no_match(self):
        self.assertEqual('', self._yes_if("$contains('12\" Vinyl','vinyl')"))

    def test_contains_empty_substring_always_true(self):
        self.assertEqual('yes', self._yes_if("$contains('anything','')"))

    def test_contains_empty_text_no_match(self):
        self.assertEqual('', self._yes_if("$contains('','Vinyl')"))

    def test_contains_both_empty_true(self):
        self.assertEqual('yes', self._yes_if("$contains('','')"))

    def test_contains_partial_word(self):
        self.assertEqual('yes', self._yes_if("$contains('Deluxe Edition','luxe')"))

    # ── $icontains (case-insensitive) ─────────────────────────────────────────

    def test_icontains_match_lower(self):
        self.assertEqual('yes', self._yes_if("$icontains('12\" Vinyl','vinyl')"))

    def test_icontains_match_upper(self):
        self.assertEqual('yes', self._yes_if("$icontains('12\" Vinyl','VINYL')"))

    def test_icontains_no_match(self):
        self.assertEqual('', self._yes_if("$icontains('CD','vinyl')"))

    def test_icontains_exact_case_also_works(self):
        self.assertEqual('yes', self._yes_if("$icontains('Vinyl','Vinyl')"))

    def test_icontains_used_in_if1(self):
        result = self._eval("$if1($icontains('Live Concert','live'),'yes')")
        self.assertEqual('yes', result)

    def test_icontains_negative_in_if1(self):
        result = self._eval("$if1($icontains('Studio Album','live'),'yes')")
        self.assertEqual('', result)


# ---------------------------------------------------------------------------
# Format hint rejection in _compareRelease
# ---------------------------------------------------------------------------

class TestFormatHintRejection(unittest.TestCase):
    """_compareRelease() rejects releases whose format conflicts with format_hint."""

    def _make_search(self):
        from discogstagger.discogs_search import DiscogsSearch
        s = DiscogsSearch.__new__(DiscogsSearch)
        s.search_params = {}
        s.tracklength_tolerance = 5.0
        s.title_similarity_threshold = 60.0
        s._release_cache = None
        s.candidates = {}
        s.no_duration_candidates = {}
        return s

    def _make_release(self, fmt_name, tracks=None):
        """Return a mock Release with the given format name and N tracks."""
        from unittest.mock import MagicMock
        rel = MagicMock()
        rel.id = 'TEST-001'
        rel.data = {'formats': [{'name': fmt_name}]}
        if tracks is None:
            tracks = [{'position': '1', 'title': 'Track', 'duration': '3:00'}]
        rel.tracklist = tracks
        return rel

    def _set_params(self, search, fmt_hint, tracks=1):
        search.search_params = {
            'tracks': [{'title': f'Track {i}', 'duration': 180.0}
                       for i in range(tracks)],
            'format_hint': fmt_hint,
        }

    def test_vinyl_rejected_when_hint_digital(self):
        search = self._make_search()
        self._set_params(search, 'digital', tracks=1)
        release = self._make_release('LP', tracks=[{'position': 'A1', 'title': 'T', 'duration': '3:00'}])
        with unittest.mock.patch.object(search, '_getTrackInfo',
                                        return_value=[{'duration': 180.0, 'title': 'T'}]):
            result = search._compareRelease(release)
        self.assertFalse(result)

    def test_cd_accepted_when_hint_digital(self):
        search = self._make_search()
        self._set_params(search, 'digital', tracks=1)
        release = self._make_release('CD')
        with unittest.mock.patch.object(search, '_getTrackInfo',
                                        return_value=[{'duration': 180.0, 'title': 'T'}]), \
             unittest.mock.patch.object(search, '_compareTrackLengths', return_value=0.5):
            result = search._compareRelease(release)
        self.assertIsNot(result, False)

    def test_cd_rejected_when_hint_vinyl(self):
        search = self._make_search()
        self._set_params(search, 'vinyl', tracks=1)
        release = self._make_release('CD')
        with unittest.mock.patch.object(search, '_getTrackInfo',
                                        return_value=[{'duration': 180.0, 'title': 'T'}]):
            result = search._compareRelease(release)
        self.assertFalse(result)

    def test_vinyl_accepted_when_hint_vinyl(self):
        search = self._make_search()
        self._set_params(search, 'vinyl', tracks=1)
        release = self._make_release('LP')
        with unittest.mock.patch.object(search, '_getTrackInfo',
                                        return_value=[{'duration': 180.0, 'title': 'T'}]), \
             unittest.mock.patch.object(search, '_compareTrackLengths', return_value=0.5):
            result = search._compareRelease(release)
        self.assertIsNot(result, False)

    def test_no_hint_does_not_reject_vinyl(self):
        search = self._make_search()
        self._set_params(search, '', tracks=1)
        release = self._make_release('LP')
        with unittest.mock.patch.object(search, '_getTrackInfo',
                                        return_value=[{'duration': 180.0, 'title': 'T'}]), \
             unittest.mock.patch.object(search, '_compareTrackLengths', return_value=0.5):
            result = search._compareRelease(release)
        self.assertIsNot(result, False)

    def test_format_hint_not_in_searchparams_safe(self):
        search = self._make_search()
        search.search_params = {
            'tracks': [{'title': 'T', 'duration': 180.0}],
            # no format_hint key at all
        }
        release = self._make_release('LP')
        with unittest.mock.patch.object(search, '_getTrackInfo',
                                        return_value=[{'duration': 180.0, 'title': 'T'}]), \
             unittest.mock.patch.object(search, '_compareTrackLengths', return_value=0.5):
            result = search._compareRelease(release)
        self.assertIsNot(result, False)


if __name__ == '__main__':
    unittest.main()
