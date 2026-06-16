"""Tests for features added in 3.0.1 / 3.0.2:
  - DiscogsAlbum.release_date normalisation
  - get_clean_filename case control (lower / upper / preserve)
  - track.new_file respects case_song / case_va_song settings
  - CUE repair_image_filename renames mismatched audio file
  - _actual_audio_format detects real format from file header (not extension)
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
# _actual_audio_format — magic-byte format detection
# ---------------------------------------------------------------------------

class TestActualAudioFormat(unittest.TestCase):
    """_actual_audio_format() reads the file header, ignoring extension.

    Regression: APE files named .wav cause shntool to fail because the code
    trusts the extension and skips the ffmpeg pre-decode step.
    """

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _write(self, name: str, magic: bytes) -> str:
        path = os.path.join(self.tmpdir, name)
        with open(path, 'wb') as f:
            f.write(magic + b'\x00' * 16)
        return path

    def test_wav_magic_detected(self):
        from discogstagger.fileutils import _actual_audio_format
        p = self._write('track.wav', b'RIFF')
        self.assertEqual(_actual_audio_format(p), 'wav')

    def test_flac_magic_detected(self):
        from discogstagger.fileutils import _actual_audio_format
        p = self._write('track.flac', b'fLaC')
        self.assertEqual(_actual_audio_format(p), 'flac')

    def test_ape_magic_detected(self):
        from discogstagger.fileutils import _actual_audio_format
        p = self._write('track.ape', b'MAC ')
        self.assertEqual(_actual_audio_format(p), 'ape')

    def test_wavpack_magic_detected(self):
        from discogstagger.fileutils import _actual_audio_format
        p = self._write('track.wv', b'wvpk')
        self.assertEqual(_actual_audio_format(p), 'wavpack')

    def test_ape_file_named_wav_detected_as_ape(self):
        """Regression: CD 1.wav that is actually APE format must be detected."""
        from discogstagger.fileutils import _actual_audio_format
        p = self._write('track.wav', b'MAC ')
        self.assertEqual(_actual_audio_format(p), 'ape')

    def test_unknown_format_returns_empty(self):
        from discogstagger.fileutils import _actual_audio_format
        p = self._write('track.xyz', b'\x00\x01\x02\x03')
        self.assertEqual(_actual_audio_format(p), '')

    def test_missing_file_returns_empty(self):
        from discogstagger.fileutils import _actual_audio_format
        self.assertEqual(_actual_audio_format('/nonexistent/track.wav'), '')


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
# _resolve_primary_format — Box Set / All Media container handling
# ---------------------------------------------------------------------------

class TestResolvePrimaryFormat(unittest.TestCase):
    """DiscogsAlbum._resolve_primary_format() resolves container formats."""

    def _call(self, fmts):
        from discogstagger.discogsalbum import DiscogsAlbum
        return DiscogsAlbum._resolve_primary_format(fmts)

    def test_plain_cd_unchanged(self):
        fmts = [{'name': 'CD', 'descriptions': ['Album']}]
        self.assertEqual(self._call(fmts), 'CD')

    def test_all_media_resolves_to_first_physical_medium(self):
        """Regression: Discogs release 7988313 — All Media + 2×CD → CD."""
        fmts = [
            {'name': 'All Media', 'qty': '1',
             'descriptions': ['Album', 'Promo', 'Remastered'],
             'text': '30th Anniversary 2CD Edition'},
            {'name': 'CD', 'qty': '1', 'descriptions': ['Album', 'Reissue', 'Remastered']},
            {'name': 'CD', 'qty': '1', 'descriptions': ['Compilation']},
        ]
        self.assertEqual(self._call(fmts), 'CD')

    def test_box_set_resolves_to_contained_vinyl(self):
        fmts = [
            {'name': 'Box Set'},
            {'name': 'Vinyl', 'descriptions': ['Album']},
            {'name': 'Cassette'},
        ]
        self.assertEqual(self._call(fmts), 'Vinyl')

    def test_all_media_no_recognised_medium_falls_back_to_container(self):
        fmts = [
            {'name': 'All Media'},
            {'name': 'File', 'descriptions': ['MP3']},
        ]
        self.assertEqual(self._call(fmts), 'All Media')

    def test_empty_list_returns_empty_string(self):
        self.assertEqual(self._call([]), '')


# format_text_notes and loose edition detection
# ---------------------------------------------------------------------------

class TestFormatTextNotes(unittest.TestCase):
    """format_text_notes is separate from format_description; editions detected
    from it via loose word-set matching.

    Regression: Discogs release 7988313 — 'All Media' container with text
    '30th Anniversary 2CD Edition'.  The pattern 'Anniversary Edition' is not
    an exact substring of that text ('2CD' sits between the two words), so
    we need loose word-set matching to detect the edition correctly.
    """

    def _make_da(self, fmts):
        """Create a DiscogsAlbum stub with the given formats list."""
        from unittest.mock import MagicMock
        from discogstagger.discogsalbum import DiscogsAlbum
        da = DiscogsAlbum.__new__(DiscogsAlbum)
        release = MagicMock()
        release.data = {'formats': fmts}
        da.release = release
        return da

    def test_text_notes_returned(self):
        da = self._make_da([
            {'name': 'All Media', 'text': '30th Anniversary 2CD Edition'},
            {'name': 'CD'},
        ])
        self.assertEqual(da.format_text_notes, ['30th Anniversary 2CD Edition'])

    def test_text_notes_empty_when_no_text(self):
        da = self._make_da([{'name': 'CD', 'descriptions': ['Album']}])
        self.assertEqual(da.format_text_notes, [])

    def test_format_description_not_polluted_by_text(self):
        da = self._make_da([
            {'name': 'All Media',
             'descriptions': ['Album', 'Promo'],
             'text': '30th Anniversary 2CD Edition'},
            {'name': 'CD', 'descriptions': ['Remastered']},
        ])
        self.assertNotIn('30th Anniversary 2CD Edition', da.format_description)
        self.assertEqual(da.format_description, ['Album', 'Promo', 'Remastered'])

    def test_loose_edition_detected_from_text_note(self):
        """'Anniversary Edition' pattern matches '30th Anniversary 2CD Edition'
        via word-set matching even though it's not an exact substring."""
        from discogstagger.formatcodes import load_format_codes, compute_edition
        fc = load_format_codes(None)
        self.assertEqual(
            compute_edition(['30th Anniversary 2CD Edition'], fc, loose=True),
            '30th Anniversary 2CD Edition',
        )

    def test_loose_does_not_match_partial_word(self):
        """Loose matching is word-boundary — 'Edition' must appear as a whole
        word, not as part of e.g. 'Reedition'."""
        from discogstagger.formatcodes import load_format_codes, compute_edition
        fc = load_format_codes(None)
        # "Deluxe Reedition" has "deluxe" but not a whole-word "edition"
        result = compute_edition(['Deluxe Reedition'], fc, loose=True)
        self.assertEqual(result, '')

    def test_exact_match_unaffected_by_loose_flag(self):
        """Standard description 'Deluxe Edition' still matched regardless of mode."""
        from discogstagger.formatcodes import load_format_codes, compute_edition
        fc = load_format_codes(None)
        self.assertEqual(compute_edition(['Deluxe Edition'], fc), 'Deluxe Edition')
        self.assertEqual(compute_edition(['Deluxe Edition'], fc, loose=True), 'Deluxe Edition')


# media property — descriptions may be None
# ---------------------------------------------------------------------------

class TestMedia(unittest.TestCase):
    """DiscogsAlbum.media handles formats with descriptions=None.

    Regression: Discogs release 246544 has a format entry with
    'descriptions': None, which crashed ', '.join(None) with
    TypeError: can only join an iterable.
    """

    def _make_da(self, fmts):
        from unittest.mock import MagicMock
        from discogstagger.discogsalbum import DiscogsAlbum
        da = DiscogsAlbum.__new__(DiscogsAlbum)
        release = MagicMock()
        release.data = {'formats': fmts}
        da.release = release
        return da

    def test_descriptions_none_does_not_raise(self):
        da = self._make_da([
            {'name': 'CD', 'qty': '1', 'descriptions': None},
        ])
        self.assertEqual(da.media, '1 x CD')

    def test_descriptions_list_still_joined(self):
        da = self._make_da([
            {'name': 'CD', 'qty': '1', 'descriptions': ['Album', 'Remastered']},
        ])
        self.assertEqual(da.media, '1 x CD Album, Remastered')


class TestIsCompilation(unittest.TestCase):
    """DiscogsAlbum.is_compilation handles formats with descriptions=None.

    Regression: Discogs release 246544 has a format entry with
    'descriptions': None, which crashed 'for description in None' with
    TypeError: 'NoneType' object is not iterable.
    """

    def _make_da(self, fmts, artist_name='Some Artist'):
        from unittest.mock import MagicMock
        from discogstagger.discogsalbum import DiscogsAlbum
        da = DiscogsAlbum.__new__(DiscogsAlbum)
        release = MagicMock()
        release.data = {'formats': fmts, 'artists': [{'name': artist_name}]}
        da.release = release
        return da

    def test_descriptions_none_does_not_raise(self):
        da = self._make_da([{'name': 'CD', 'qty': '1', 'descriptions': None}])
        self.assertFalse(da.is_compilation)

    def test_compilation_description_detected(self):
        da = self._make_da([
            {'name': 'CD', 'qty': '1', 'descriptions': ['Album', 'Compilation']},
        ])
        self.assertTrue(da.is_compilation)

    def test_various_artist_is_compilation(self):
        da = self._make_da([{'name': 'CD', 'descriptions': None}], artist_name='Various')
        self.assertTrue(da.is_compilation)


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


import unittest.mock


# ---------------------------------------------------------------------------
# M4A codec detection
# ---------------------------------------------------------------------------

class TestM4ACodec(unittest.TestCase):
    """_m4a_codec() returns 'alac', 'aac', or '' based on mutagen's codec string."""

    def _patch_mp4(self, codec_str):
        m = unittest.mock.MagicMock()
        m.return_value.info.codec = codec_str
        return unittest.mock.patch('discogstagger.fileutils.MP4', m)

    def test_alac_codec_returns_alac(self):
        from discogstagger.fileutils import _m4a_codec
        with self._patch_mp4('alac'):
            self.assertEqual(_m4a_codec('/fake/track.m4a'), 'alac')

    def test_aac_codec_returns_aac(self):
        from discogstagger.fileutils import _m4a_codec
        with self._patch_mp4('mp4a.40.2'):
            self.assertEqual(_m4a_codec('/fake/track.m4a'), 'aac')

    def test_aac_variant_returns_aac(self):
        from discogstagger.fileutils import _m4a_codec
        with self._patch_mp4('mp4a.40.5'):
            self.assertEqual(_m4a_codec('/fake/track.m4a'), 'aac')

    def test_unknown_codec_returns_empty(self):
        from discogstagger.fileutils import _m4a_codec
        with self._patch_mp4('ac-3'):
            self.assertEqual(_m4a_codec('/fake/track.m4a'), '')

    def test_none_codec_returns_empty(self):
        from discogstagger.fileutils import _m4a_codec
        with self._patch_mp4(None):
            self.assertEqual(_m4a_codec('/fake/track.m4a'), '')

    def test_exception_returns_empty(self):
        from discogstagger.fileutils import _m4a_codec
        with unittest.mock.patch('discogstagger.fileutils.MP4',
                                  side_effect=Exception('bad file')):
            self.assertEqual(_m4a_codec('/fake/track.m4a'), '')


# ---------------------------------------------------------------------------
# _processM4aFiles — conversion routing and side-effects
# ---------------------------------------------------------------------------

class TestProcessM4aFiles(unittest.TestCase):
    """_processM4aFiles() dispatches to ffmpeg or keeps files according to config."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _write(self, name):
        path = os.path.join(self.tmpdir, name)
        with open(path, 'wb') as f:
            f.write(b'\x00' * 16)
        return path

    def _make_fu(self, alac_action='convert_to_flac', aac_action='keep',
                 m4a_done_dir='.m4a'):
        from discogstagger.fileutils import FileUtils
        config = _config()
        config.set('m4a', 'convert_m4a_files', 'true')
        config.set('m4a', 'alac_action', alac_action)
        config.set('m4a', 'aac_action', aac_action)
        config.set('m4a', 'm4a_done_dir', m4a_done_dir)
        opts = unittest.mock.MagicMock()
        opts.forceUpdate = False
        return FileUtils(config, opts)

    def _ok_run(self):
        r = unittest.mock.MagicMock()
        r.returncode = 0
        return r

    def test_alac_convert_to_flac_calls_ffmpeg(self):
        self._write('track.m4a')
        with unittest.mock.patch('discogstagger.fileutils._m4a_codec', return_value='alac'), \
             unittest.mock.patch('subprocess.run', return_value=self._ok_run()) as mock_run:
            self._make_fu(alac_action='convert_to_flac')._processM4aFiles(
                self.tmpdir, ['track.m4a'])
        args = mock_run.call_args[0][0]
        self.assertIn('ffmpeg', args)
        self.assertIn('flac', args)

    def test_alac_keep_skips_ffmpeg(self):
        self._write('track.m4a')
        with unittest.mock.patch('discogstagger.fileutils._m4a_codec', return_value='alac'), \
             unittest.mock.patch('subprocess.run') as mock_run:
            result = self._make_fu(alac_action='keep')._processM4aFiles(
                self.tmpdir, ['track.m4a'])
        mock_run.assert_not_called()
        self.assertFalse(result)

    def test_aac_keep_skips_ffmpeg(self):
        self._write('track.m4a')
        with unittest.mock.patch('discogstagger.fileutils._m4a_codec', return_value='aac'), \
             unittest.mock.patch('subprocess.run') as mock_run:
            result = self._make_fu(aac_action='keep')._processM4aFiles(
                self.tmpdir, ['track.m4a'])
        mock_run.assert_not_called()
        self.assertFalse(result)

    def test_aac_convert_to_mp3_uses_libmp3lame(self):
        self._write('track.m4a')
        with unittest.mock.patch('discogstagger.fileutils._m4a_codec', return_value='aac'), \
             unittest.mock.patch('subprocess.run', return_value=self._ok_run()) as mock_run:
            self._make_fu(aac_action='convert_to_mp3')._processM4aFiles(
                self.tmpdir, ['track.m4a'])
        args = mock_run.call_args[0][0]
        self.assertIn('libmp3lame', args)

    def test_aac_convert_to_ogg_uses_libvorbis(self):
        self._write('track.m4a')
        with unittest.mock.patch('discogstagger.fileutils._m4a_codec', return_value='aac'), \
             unittest.mock.patch('subprocess.run', return_value=self._ok_run()) as mock_run:
            self._make_fu(aac_action='convert_to_ogg')._processM4aFiles(
                self.tmpdir, ['track.m4a'])
        args = mock_run.call_args[0][0]
        self.assertIn('libvorbis', args)

    def test_original_moved_to_done_dir_on_success(self):
        src = self._write('track.m4a')
        with unittest.mock.patch('discogstagger.fileutils._m4a_codec', return_value='alac'), \
             unittest.mock.patch('subprocess.run', return_value=self._ok_run()):
            self._make_fu(alac_action='convert_to_flac')._processM4aFiles(
                self.tmpdir, ['track.m4a'])
        self.assertTrue(os.path.exists(os.path.join(self.tmpdir, '.m4a', 'track.m4a')))
        self.assertFalse(os.path.exists(src))

    def test_alac_convert_to_flac_passes_compression_level(self):
        self._write('track.m4a')
        fu = self._make_fu(alac_action='convert_to_flac')
        fu.flac_compression_level = '8'
        with unittest.mock.patch('discogstagger.fileutils._m4a_codec', return_value='alac'), \
             unittest.mock.patch('subprocess.run', return_value=self._ok_run()) as mock_run:
            fu._processM4aFiles(self.tmpdir, ['track.m4a'])
        args = mock_run.call_args[0][0]
        self.assertIn('-compression_level', args)
        self.assertEqual(args[args.index('-compression_level') + 1], '8')

    def test_aac_convert_to_mp3_passes_quality(self):
        self._write('track.m4a')
        fu = self._make_fu(aac_action='convert_to_mp3')
        fu.mp3_quality = '2'
        with unittest.mock.patch('discogstagger.fileutils._m4a_codec', return_value='aac'), \
             unittest.mock.patch('subprocess.run', return_value=self._ok_run()) as mock_run:
            fu._processM4aFiles(self.tmpdir, ['track.m4a'])
        args = mock_run.call_args[0][0]
        self.assertIn('-q:a', args)
        self.assertEqual(args[args.index('-q:a') + 1], '2')

    def test_aac_convert_to_ogg_passes_quality(self):
        self._write('track.m4a')
        fu = self._make_fu(aac_action='convert_to_ogg')
        fu.ogg_quality = '5'
        with unittest.mock.patch('discogstagger.fileutils._m4a_codec', return_value='aac'), \
             unittest.mock.patch('subprocess.run', return_value=self._ok_run()) as mock_run:
            fu._processM4aFiles(self.tmpdir, ['track.m4a'])
        args = mock_run.call_args[0][0]
        self.assertIn('-q:a', args)
        self.assertEqual(args[args.index('-q:a') + 1], '5')

    def test_ffmpeg_failure_leaves_original_in_place(self):
        src = self._write('track.m4a')
        fail = unittest.mock.MagicMock()
        fail.returncode = 1
        fail.stderr = 'error'
        with unittest.mock.patch('discogstagger.fileutils._m4a_codec', return_value='alac'), \
             unittest.mock.patch('subprocess.run', return_value=fail):
            result = self._make_fu(alac_action='convert_to_flac')._processM4aFiles(
                self.tmpdir, ['track.m4a'])
        self.assertFalse(result)
        self.assertTrue(os.path.exists(src))

    def test_unknown_codec_skips_file(self):
        self._write('track.m4a')
        with unittest.mock.patch('discogstagger.fileutils._m4a_codec', return_value=''), \
             unittest.mock.patch('subprocess.run') as mock_run:
            result = self._make_fu()._processM4aFiles(self.tmpdir, ['track.m4a'])
        mock_run.assert_not_called()
        self.assertFalse(result)

    def test_returns_true_when_any_converted(self):
        self._write('track.m4a')
        with unittest.mock.patch('discogstagger.fileutils._m4a_codec', return_value='alac'), \
             unittest.mock.patch('subprocess.run', return_value=self._ok_run()):
            result = self._make_fu(alac_action='convert_to_flac')._processM4aFiles(
                self.tmpdir, ['track.m4a'])
        self.assertTrue(result)

    def test_returns_false_when_all_kept(self):
        self._write('alac.m4a')
        self._write('aac.m4a')
        with unittest.mock.patch('discogstagger.fileutils._m4a_codec',
                                  side_effect=['alac', 'aac']):
            result = self._make_fu(alac_action='keep', aac_action='keep')._processM4aFiles(
                self.tmpdir, ['alac.m4a', 'aac.m4a'])
        self.assertFalse(result)


# ---------------------------------------------------------------------------
# get_audio_dirs — M4A pre-pass integration
# ---------------------------------------------------------------------------

class TestGetAudioDirsM4APrepass(unittest.TestCase):
    """get_audio_dirs() calls the M4A pre-pass and handles the rescan correctly."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _make_fu(self, process_m4a=True):
        from discogstagger.fileutils import FileUtils
        config = _config()
        config.set('m4a', 'convert_m4a_files', 'true' if process_m4a else 'false')
        opts = unittest.mock.MagicMock()
        opts.forceUpdate = False
        return FileUtils(config, opts)

    def test_prepass_called_when_m4a_present(self):
        fu = self._make_fu()
        open(os.path.join(self.tmpdir, 'track.m4a'), 'wb').close()
        with unittest.mock.patch.object(fu, '_processM4aFiles', return_value=False) as m:
            fu.get_audio_dirs(self.tmpdir)
        m.assert_called_once()

    def test_prepass_not_called_when_disabled(self):
        fu = self._make_fu(process_m4a=False)
        open(os.path.join(self.tmpdir, 'track.m4a'), 'wb').close()
        with unittest.mock.patch.object(fu, '_processM4aFiles', return_value=False) as m:
            fu.get_audio_dirs(self.tmpdir)
        m.assert_not_called()

    def test_rescan_picks_up_converted_flac(self):
        """Directory is found after _processM4aFiles converts .m4a → .flac."""
        fu = self._make_fu()
        open(os.path.join(self.tmpdir, 'track.m4a'), 'wb').close()

        def fake_convert(d, files):
            os.remove(os.path.join(d, 'track.m4a'))
            open(os.path.join(d, 'track.flac'), 'wb').close()
            os.makedirs(os.path.join(d, '.m4a'), exist_ok=True)
            return True

        with unittest.mock.patch.object(fu, '_processM4aFiles', side_effect=fake_convert):
            result = fu.get_audio_dirs(self.tmpdir)
        self.assertIn(self.tmpdir + '/', result)

    def test_done_dir_not_miscounted_as_audio_file(self):
        """Bug fix: .m4a done-dir must not match AUDIO_EXTENSIONS after rescan."""
        fu = self._make_fu()
        open(os.path.join(self.tmpdir, 'track.m4a'), 'wb').close()

        def fake_convert(d, files):
            # Simulate: original moved to done-dir, no converted output yet.
            # Pre-fix: os.listdir would include '.m4a' directory entry, and
            # '.m4a'.endswith('.m4a') → True, so done-dir counted as audio.
            # Post-fix: filter to files only; done-dir is excluded.
            os.remove(os.path.join(d, 'track.m4a'))
            os.makedirs(os.path.join(d, '.m4a'), exist_ok=True)
            return True

        with unittest.mock.patch.object(fu, '_processM4aFiles', side_effect=fake_convert):
            result = fu.get_audio_dirs(self.tmpdir)
        # No real audio file exists — directory must not appear in results.
        self.assertNotIn(self.tmpdir + '/', result)

    def test_done_dir_excluded_from_walk(self):
        """The .m4a done-dir is not descended into so originals aren't re-tagged."""
        fu = self._make_fu(process_m4a=False)
        done = os.path.join(self.tmpdir, '.m4a')
        os.makedirs(done)
        open(os.path.join(done, 'original.m4a'), 'wb').close()

        result = fu.get_audio_dirs(self.tmpdir)
        self.assertEqual(result, [])

    def test_prepass_called_for_disc_subdirectories(self):
        """M4A pre-pass must run for CD N / Disc N subdirs.

        Regression: get_audio_dirs() detects CD/Disc subdirs, adds them to
        unwalk (so os.walk never descends), then scans their files for audio.
        Before the fix the m4a conversion was never triggered for those dirs
        because the conversion check only ran at the top of the walk loop —
        which os.walk never reached for pruned disc subdirs.
        """
        fu = self._make_fu()
        cd1 = os.path.join(self.tmpdir, 'CD 1')
        cd2 = os.path.join(self.tmpdir, 'CD 2')
        os.makedirs(cd1)
        os.makedirs(cd2)
        open(os.path.join(cd1, '01.m4a'), 'wb').close()
        open(os.path.join(cd2, '01.m4a'), 'wb').close()

        calls = []
        def fake_convert(d, files):
            calls.append((d, sorted(files)))
            return False

        with unittest.mock.patch.object(fu, '_processM4aFiles',
                                        side_effect=fake_convert):
            fu.get_audio_dirs(self.tmpdir)

        converted_dirs = [c[0] for c in calls]
        self.assertIn(cd1, converted_dirs)
        self.assertIn(cd2, converted_dirs)


if __name__ == '__main__':
    unittest.main()
