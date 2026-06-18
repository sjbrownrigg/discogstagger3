"""Tests for DiscogsSearch matching methods.

These tests cover the pure-computation methods that compare local file
metadata against Discogs release data.  No API calls are made — releases
and tracks are constructed from lightweight mock objects.
"""
import os
import unittest
from datetime import timedelta

parentdir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from discogstagger.discogs_search import DiscogsSearch


# ── Test helpers ──────────────────────────────────────────────────────────────

class _Track:
    """Minimal Discogs track mock."""
    def __init__(self, position, title, duration):
        self.position = position
        self.title = title
        self.duration = duration
        self.data = {'type_': 'track'}


class _Release:
    """Minimal Discogs release mock."""
    def __init__(self, rid, tracks, year=2020, fmt_name='CD', fmt_qty=1):
        self.id = rid
        self.year = year
        self.data = {
            'formats': [{'name': fmt_name}],
            'format_quantity': fmt_qty,
        }
        self._tracklist = [_Track(**t) for t in tracks]

    @property
    def tracklist(self):
        return self._tracklist


def _make_search(local_tracks, year=2020, tolerance=5.0, threshold=60.0):
    """Construct a DiscogsSearch with just enough state for matching methods."""
    s = DiscogsSearch.__new__(DiscogsSearch)
    s.search_params = {
        'tracks': local_tracks,
        'year': year,
        'media': None,
    }
    s.tracklength_tolerance = tolerance
    s.title_similarity_threshold = threshold
    s._release_cache = None
    s.candidates = {}
    s.no_duration_candidates = {}
    return s


def _local(duration, title=''):
    """Build a local track dict as getSearchParams() would produce."""
    return {'position': '1', 'duration': duration, 'title': title, 'artist': ''}


def _discogs(position, title, duration):
    """Keyword dict for _Track constructor."""
    return {'position': position, 'title': title, 'duration': duration}


# ── _compareTrackLengths ──────────────────────────────────────────────────────

class TestCompareTrackLengths(unittest.TestCase):

    def setUp(self):
        self.s = _make_search([_local('0:03:45')])

    def _imported(self, *durations):
        return [{'duration': d, 'title': '', 'position': str(i+1)}
                for i, d in enumerate(durations)]

    def test_identical_durations_score_zero(self):
        local = [_local('0:03:45')]
        imported = self._imported('3:45')
        s = _make_search(local)
        self.assertAlmostEqual(0.0, s._compareTrackLengths(local, imported))

    def test_two_second_difference(self):
        local = [_local('0:03:45')]
        imported = self._imported('3:47')
        s = _make_search(local)
        self.assertAlmostEqual(2.0, s._compareTrackLengths(local, imported))

    def test_average_over_multiple_tracks(self):
        # Track 1: 0s diff, Track 2: 10s diff → average 5s
        local = [_local('0:03:00'), _local('0:05:00')]
        imported = self._imported('3:00', '5:10')
        s = _make_search(local)
        self.assertAlmostEqual(5.0, s._compareTrackLengths(local, imported))

    def test_none_discogs_duration_skipped(self):
        # Only second track has duration; average is based on that one only
        local = [_local('0:03:00'), _local('0:05:00')]
        imported = [{'duration': None, 'title': '', 'position': '1'},
                    {'duration': '5:10', 'title': '', 'position': '2'}]
        s = _make_search(local)
        self.assertAlmostEqual(10.0, s._compareTrackLengths(local, imported))

    def test_empty_local_duration_skipped(self):
        local = [_local(''), _local('0:04:00')]
        imported = self._imported('3:00', '4:10')
        s = _make_search(local)
        # Only second pair compared; diff = 10s
        self.assertAlmostEqual(10.0, s._compareTrackLengths(local, imported))

    def test_no_valid_pairs_returns_inf(self):
        local = [_local('')]
        imported = [{'duration': None, 'title': '', 'position': '1'}]
        s = _make_search(local)
        import math
        self.assertTrue(math.isinf(s._compareTrackLengths(local, imported)))

    def test_over_60_minute_track_handled(self):
        # Discogs encodes >60min as "63:00" which _paddedHMS normalises
        local = [_local('1:03:00')]
        imported = self._imported('63:00')
        s = _make_search(local)
        self.assertAlmostEqual(0.0, s._compareTrackLengths(local, imported))


# ── _compareTitleSimilarity ───────────────────────────────────────────────────

class TestCompareTitleSimilarity(unittest.TestCase):

    def _local_t(self, title):
        return {'title': title, 'duration': '0:03:00', 'position': '1', 'artist': ''}

    def _discogs_t(self, title):
        return {'title': title, 'duration': '3:00', 'position': '1'}

    def test_identical_titles_score_100(self):
        s = _make_search([self._local_t('Hello World')])
        result = s._compareTitleSimilarity(
            [self._local_t('Hello World')],
            [self._discogs_t('Hello World')]
        )
        self.assertAlmostEqual(100.0, result)

    def test_word_order_does_not_penalise(self):
        # token_sort_ratio sorts words before comparing
        s = _make_search([])
        result = s._compareTitleSimilarity(
            [self._local_t('A Love Supreme Pt 1')],
            [self._discogs_t('Pt. 1 A Love Supreme')]
        )
        self.assertGreater(result, 80.0)

    def test_completely_different_titles_low_score(self):
        s = _make_search([])
        result = s._compareTitleSimilarity(
            [self._local_t('Something Completely Different')],
            [self._discogs_t('XYZ ABC 123')]
        )
        self.assertLess(result, 50.0)

    def test_average_over_multiple_tracks(self):
        local = [self._local_t('Track One'), self._local_t('Track Two')]
        discogs = [self._discogs_t('Track One'), self._discogs_t('Track Two')]
        s = _make_search(local)
        self.assertAlmostEqual(100.0, s._compareTitleSimilarity(local, discogs))

    def test_no_titles_returns_zero(self):
        local = [{'title': '', 'duration': '0:03:00', 'position': '1', 'artist': ''}]
        discogs = [{'title': '', 'duration': '3:00', 'position': '1'}]
        s = _make_search(local)
        self.assertAlmostEqual(0.0, s._compareTitleSimilarity(local, discogs))

    def test_one_side_empty_skipped(self):
        # Local has title, Discogs doesn't — that pair is skipped
        local = [self._local_t('Title'), self._local_t('Other')]
        discogs = [self._discogs_t(''), self._discogs_t('Other')]
        s = _make_search(local)
        result = s._compareTitleSimilarity(local, discogs)
        self.assertAlmostEqual(100.0, result)  # Only the second pair counted


# ── _candidate_score ──────────────────────────────────────────────────────────

class TestCandidateScore(unittest.TestCase):

    def _release(self, year=2020, fmt_name='CD', fmt_qty=1):
        return _Release('r1', [], year=year, fmt_name=fmt_name, fmt_qty=fmt_qty)

    def test_base_score_returned_when_no_match(self):
        s = _make_search([], year=1999)
        r = self._release(year=2020, fmt_name='CD')
        # Year doesn't match, format doesn't match vinyl preference
        score = s._candidate_score(r, base_score=3.0)
        # CD with no vinyl preference gives -1.0 bonus
        self.assertAlmostEqual(3.0 - 1.0, score)

    def test_year_match_reduces_score(self):
        s = _make_search([], year=2020)
        r_match = self._release(year=2020, fmt_name='CD')
        r_nomatch = self._release(year=1990, fmt_name='CD')
        self.assertLess(
            s._candidate_score(r_match, base_score=3.0),
            s._candidate_score(r_nomatch, base_score=3.0)
        )

    def test_cd_bonus_for_non_vinyl_search(self):
        s = _make_search([], year=2020)  # no vinyl indicators
        r = self._release(year=1990, fmt_name='CD')
        score = s._candidate_score(r, base_score=3.0)
        self.assertAlmostEqual(3.0 - 1.0, score)  # -1.0 for CD

    def test_vinyl_bonus_for_vinyl_search(self):
        local = [{'position': 'A1', 'duration': '0:03:00', 'title': '',
                  'artist': '', 'real_tracknumber': 'A1'}]
        # Use mismatched year so the year bonus does not interfere
        s = _make_search(local, year=2020)
        r = self._release(year=1990, fmt_name='Vinyl')
        score = s._candidate_score(r, base_score=3.0)
        self.assertAlmostEqual(3.0 - 1.5, score)  # -1.5 for vinyl match only

    def test_broken_release_data_returns_base(self):
        # year=9999 ensures no year bonus fires; empty formats → no fmt bonus
        s = _make_search([], year=9999)
        r = _Release('r1', [], year=1900)
        r.data = {}   # missing 'formats' key — fmt_name = '', no bonus
        score = s._candidate_score(r, base_score=7.0)
        self.assertAlmostEqual(7.0, score)

    def test_descriptor_hint_match_reduces_score(self):
        s = _make_search([], year=9999)
        s.search_params['descriptor_hints'] = ['Remastered']
        r = _Release('r1', [], year=1900, fmt_name='CD')
        r.data['formats'] = [{'name': 'CD', 'descriptions': ['Album', 'Remastered']}]
        score_with = s._candidate_score(r, base_score=3.0)
        # CD bonus (-1.0) + descriptor match (-1.0)
        self.assertAlmostEqual(3.0 - 1.0 - 1.0, score_with)

    def test_descriptor_hint_no_match_no_bonus(self):
        s = _make_search([], year=9999)
        s.search_params['descriptor_hints'] = ['Remastered']
        r = _Release('r1', [], year=1900, fmt_name='CD')
        r.data['formats'] = [{'name': 'CD', 'descriptions': ['Album']}]
        score = s._candidate_score(r, base_score=3.0)
        # CD bonus only — no descriptor bonus
        self.assertAlmostEqual(3.0 - 1.0, score)

    def test_descriptor_hint_boosts_remastered_over_plain(self):
        """Remastered candidate ranks higher than plain when hint is set."""
        s = _make_search([], year=9999)
        s.search_params['descriptor_hints'] = ['Remastered']
        r_remaster = _Release('r1', [], year=1900, fmt_name='CD')
        r_remaster.data['formats'] = [{'name': 'CD', 'descriptions': ['Remastered']}]
        r_plain = _Release('r2', [], year=1900, fmt_name='CD')
        r_plain.data['formats'] = [{'name': 'CD', 'descriptions': ['Album']}]
        self.assertLess(
            s._candidate_score(r_remaster, base_score=3.0),
            s._candidate_score(r_plain, base_score=3.0),
        )

    def test_catalog_hint_match_decisively_reduces_score(self):
        """Regression: Depeche Mode 'In Your Room' maxi-singles — several
        regional reissues share identical track counts and near-identical
        durations, so duration/format/year bonuses alone pick an unrelated
        pressing. A catalog number folded into the embedded tag
        ('In Your Room (Maxi XLCDBong24)') is extracted as catalog_hint and
        must outweigh a closer raw duration match from a release with an
        unrelated catalog number."""
        s = _make_search([], year=9999)
        s.search_params['catalog_hint'] = 'xlcdbong24'

        r_match = _Release('r1', [], year=1900, fmt_name='CD')
        r_match.data['labels'] = [{'catno': 'XLCD BONG 24'}]

        r_other = _Release('r2', [], year=1900, fmt_name='CD')
        r_other.data['labels'] = [{'catno': '74321184092'}]

        # Even with a worse base score (further duration diff), the catalog
        # match must still win.
        self.assertLess(
            s._candidate_score(r_match, base_score=2.0),
            s._candidate_score(r_other, base_score=0.0),
        )

    def test_catalog_hint_no_match_no_bonus(self):
        s = _make_search([], year=9999)
        s.search_params['catalog_hint'] = 'xlcdbong24'
        r = _Release('r1', [], year=1900, fmt_name='CD')
        r.data['labels'] = [{'catno': 'UNRELATED123'}]
        score = s._candidate_score(r, base_score=3.0)
        self.assertAlmostEqual(3.0 - 1.0, score)  # CD bonus only

    def test_no_catalog_hint_no_effect(self):
        s = _make_search([], year=9999)
        r = _Release('r1', [], year=1900, fmt_name='CD')
        r.data['labels'] = [{'catno': 'XLCD BONG 24'}]
        score = s._candidate_score(r, base_score=3.0)
        self.assertAlmostEqual(3.0 - 1.0, score)  # CD bonus only, no catalog hint set

    def test_no_descriptor_hints_no_effect(self):
        """descriptor_hints absent → score unchanged vs. baseline."""
        s_with = _make_search([], year=9999)
        s_with.search_params['descriptor_hints'] = []
        s_without = _make_search([], year=9999)
        r = _Release('r1', [], year=1900, fmt_name='CD')
        r.data['formats'] = [{'name': 'CD', 'descriptions': ['Remastered']}]
        self.assertAlmostEqual(
            s_with._candidate_score(r, base_score=3.0),
            s_without._candidate_score(r, base_score=3.0),
        )


# ── strip_catalog_suffix ──────────────────────────────────────────────────────

class TestStripCatalogSuffix(unittest.TestCase):
    """strip_catalog_suffix() removes a trailing catalog/format suffix from
    a search title without touching legitimate parenthetical titles.

    Regression: Depeche Mode "In Your Room" — both maxi-single pressings had
    the catalog number folded into the embedded album tag itself
    ('In Your Room (Maxi XLCDBong24)', 'In Your Room (Maxi LCDBong24)'),
    presumably by whatever tool originally tagged the files. Searching
    Discogs for that literal title returned zero results since Discogs
    release titles never include catalog numbers.
    """

    def _strip(self, title):
        from discogstagger.discogs_utils import strip_catalog_suffix
        return strip_catalog_suffix(title)

    def test_maxi_catalog_suffix_stripped(self):
        self.assertEqual(self._strip('In Your Room (Maxi XLCDBong24)'), 'In Your Room')

    def test_different_catalog_suffix_stripped(self):
        self.assertEqual(self._strip('In Your Room (Maxi LCDBong24)'), 'In Your Room')

    def test_bare_catalog_suffix_without_format_word(self):
        self.assertEqual(self._strip('Violator (STUMM64)'), 'Violator')

    def test_deluxe_edition_untouched(self):
        self.assertEqual(self._strip('Album (Deluxe Edition)'), 'Album (Deluxe Edition)')

    def test_year_remaster_untouched(self):
        self.assertEqual(self._strip('Album (2009 Remaster)'), 'Album (2009 Remaster)')

    def test_legitimate_parenthetical_title_untouched(self):
        self.assertEqual(self._strip('Use (Of Weapons)'), 'Use (Of Weapons)')

    def test_live_suffix_untouched(self):
        self.assertEqual(self._strip('Track (Live)'), 'Track (Live)')

    def test_no_parens_unchanged(self):
        self.assertEqual(self._strip('Sounds Of The Universe'), 'Sounds Of The Universe')

    def test_only_outermost_catalog_group_stripped(self):
        # '(Maxi)' alone has no digit, so it isn't catalog noise on its own —
        # only the trailing '(XLCDBong24)' group is removed.
        self.assertEqual(self._strip('Title (Maxi) (XLCDBong24)'), 'Title (Maxi)')

    def test_only_affects_trailing_group_not_mid_title(self):
        # A mixed-alnum token in a non-trailing position is left alone.
        self.assertEqual(
            self._strip('Album (XLCDBong24) (Deluxe Edition)'),
            'Album (XLCDBong24) (Deluxe Edition)',
        )


# ── extract_catalog_hint / normalize_catalog_number ──────────────────────────

class TestExtractCatalogHint(unittest.TestCase):
    """extract_catalog_hint() pulls a normalised catalog number out of the
    same trailing parenthetical group strip_catalog_suffix() removes, so it
    can disambiguate between Discogs releases with identical track counts
    and near-identical durations (common across regional/format reissues).
    """

    def _hint(self, title):
        from discogstagger.discogs_utils import extract_catalog_hint
        return extract_catalog_hint(title)

    def test_maxi_catalog_extracted_and_normalized(self):
        self.assertEqual(self._hint('In Your Room (Maxi XLCDBong24)'), 'xlcdbong24')

    def test_bare_catalog_extracted(self):
        self.assertEqual(self._hint('Violator (STUMM64)'), 'stumm64')

    def test_no_catalog_returns_none(self):
        self.assertIsNone(self._hint('Album (Deluxe Edition)'))

    def test_no_parens_returns_none(self):
        self.assertIsNone(self._hint('Sounds Of The Universe'))


class TestNormalizeCatalogNumber(unittest.TestCase):
    """normalize_catalog_number() makes spaced/hyphenated/cased catalog
    numbers comparable — e.g. Discogs's 'XLCD BONG 24' vs an embedded tag's
    'XLCDBong24' both become 'xlcdbong24'."""

    def _norm(self, s):
        from discogstagger.discogs_utils import normalize_catalog_number
        return normalize_catalog_number(s)

    def test_spaced_and_compact_forms_match(self):
        self.assertEqual(self._norm('XLCD BONG 24'), self._norm('XLCDBong24'))

    def test_hyphens_stripped(self):
        self.assertEqual(self._norm('STUMM-64'), self._norm('STUMM 64'))

    def test_empty_string(self):
        self.assertEqual(self._norm(''), '')

    def test_none_safe(self):
        self.assertEqual(self._norm(None), '')


# ── is_non_audio_position ────────────────────────────────────────────────────

class TestIsNonAudioPosition(unittest.TestCase):
    """is_non_audio_position() identifies non-audio disc position prefixes."""

    def _check(self, pos):
        from discogstagger.discogs_utils import is_non_audio_position
        return is_non_audio_position(pos)

    def test_dvd_dash(self):
        self.assertTrue(self._check('DVD-1'))

    def test_dvd_with_disc_number(self):
        """Positions like DVD1-3 (second DVD, track 3) are non-audio."""
        self.assertTrue(self._check('DVD1-3'))
        self.assertTrue(self._check('DVD2-12'))

    def test_bd_dash(self):
        self.assertTrue(self._check('BD-5'))

    def test_vhs(self):
        self.assertTrue(self._check('VHS-1'))

    def test_video(self):
        self.assertTrue(self._check('Video-1'))

    def test_bare_dvd_label(self):
        self.assertTrue(self._check('DVD'))

    def test_cd_is_audio(self):
        self.assertFalse(self._check('CD1-1'))

    def test_plain_number_is_audio(self):
        self.assertFalse(self._check('1-01'))

    def test_vinyl_side_is_audio(self):
        self.assertFalse(self._check('A1'))
        self.assertFalse(self._check('B2'))

    def test_empty_is_audio(self):
        self.assertFalse(self._check(''))

    def test_case_insensitive(self):
        self.assertTrue(self._check('dvd-1'))
        self.assertTrue(self._check('Dvd-1'))


# ── Two-pass non-audio track exclusion ────────────────────────────────────────

class TestTwoPassNonAudioExclusion(unittest.TestCase):
    """_compareRelease() falls back to audio-only matching when the full
    Discogs tracklist includes non-audio disc tracks the user doesn't have.

    Regression: Black Tie White Noise Limited Edition 2CD+DVD — local files
    are 24 audio tracks (CD1+CD2); Discogs release has 42 tracks (24 audio
    + 18 DVD).  Without two-pass logic the count mismatch causes rejection.
    """

    def _make_mixed_release(self, audio_specs, non_audio_specs,
                             non_audio_prefix='DVD'):
        """Release with audio tracks followed by non-audio (DVD etc.) tracks."""
        tracks = []
        for i, (dur, title) in enumerate(audio_specs, 1):
            tracks.append(_discogs(f'CD1-{i}', title, dur))
        for i, (dur, title) in enumerate(non_audio_specs, 1):
            tracks.append(_discogs(f'{non_audio_prefix}-{i}', title, dur))
        return _Release('r1', tracks)

    def test_audio_only_match_when_dvd_excluded(self):
        """Local=3 audio, Discogs=3 audio+2 DVD → audio-only pass matches."""
        s, _ = self._search_with_tracks('3:00', '4:00', '5:00')
        r = self._make_mixed_release(
            [('3:01', 'T1'), ('4:01', 'T2'), ('5:01', 'T3')],
            [('2:00', 'V1'), ('3:00', 'V2')],
        )
        result = s._compareRelease(r)
        self.assertIsNot(result, False)

    def test_full_match_when_user_has_all_content(self):
        """Local=5 tracks (3 audio+2 DVD), Discogs=3 audio+2 DVD → pass 1."""
        audio = [('3:00', 'T1'), ('4:00', 'T2'), ('5:00', 'T3')]
        dvd   = [('2:01', 'V1'), ('3:01', 'V2')]
        s, _ = self._search_with_tracks('3:00', '4:00', '5:00', '2:00', '3:00')
        r = self._make_mixed_release(audio, dvd)
        result = s._compareRelease(r)
        self.assertIsNot(result, False)

    def test_rejected_when_neither_count_matches(self):
        """Local=4, Discogs=3 audio+2 DVD (audio-only=3) → rejected."""
        s, _ = self._search_with_tracks('3:00', '4:00', '5:00', '6:00')
        r = self._make_mixed_release(
            [('3:01', 'T1'), ('4:01', 'T2'), ('5:01', 'T3')],
            [('2:00', 'V1'), ('3:00', 'V2')],
        )
        self.assertFalse(s._compareRelease(r))

    def test_bd_tracks_excluded(self):
        """Blu-ray positions also trigger the audio-only fallback."""
        s, _ = self._search_with_tracks('3:00', '4:00')
        r = self._make_mixed_release(
            [('3:01', 'T1'), ('4:01', 'T2')],
            [('90:00', 'Movie')],
            non_audio_prefix='BD',
        )
        result = s._compareRelease(r)
        self.assertIsNot(result, False)

    def _search_with_tracks(self, *durations):
        local = [_local(d) for d in durations]
        return _make_search(local, year=2020, tolerance=5.0), local


# ── _compareRelease (integration) ────────────────────────────────────────────

class TestCompareRelease(unittest.TestCase):

    def _search_with_tracks(self, *durations, titles=None, year=2020,
                             tolerance=5.0, threshold=60.0):
        titles = titles or [''] * len(durations)
        local = [_local(d, t) for d, t in zip(durations, titles)]
        return _make_search(local, year=year,
                            tolerance=tolerance, threshold=threshold), local

    def _release(self, *track_specs, rid='r1', year=2020):
        tracks = [_discogs(str(i+1), t, d)
                  for i, (d, t) in enumerate(track_specs)]
        return _Release(rid, tracks, year=year)

    def test_accepted_tier1_returns_float(self):
        s, _ = self._search_with_tracks('0:03:45')
        r = self._release(('3:45', 'Title'))
        result = s._compareRelease(r)
        self.assertIsInstance(result, float)
        self.assertGreaterEqual(result, 0.0)

    def test_accepted_within_tolerance(self):
        s, _ = self._search_with_tracks('0:03:45', tolerance=5.0)
        r = self._release(('3:47', 'Title'))   # 2s diff — within 5s
        result = s._compareRelease(r)
        self.assertGreaterEqual(result, 0.0)

    def test_rejected_exceeds_tolerance(self):
        s, _ = self._search_with_tracks('0:03:45', tolerance=2.0)
        r = self._release(('3:55', 'Title'))   # 10s diff — exceeds 2s
        self.assertIs(False, s._compareRelease(r))

    def test_rejected_track_count_mismatch(self):
        s, _ = self._search_with_tracks('0:03:45', '0:04:00')
        r = self._release(('3:45', 'Title'))   # only 1 track vs 2 local
        self.assertIs(False, s._compareRelease(r))

    def test_rejected_no_tracks_on_discogs(self):
        s, _ = self._search_with_tracks('0:03:45')
        r = _Release('r1', [])   # empty tracklist
        self.assertIs(False, s._compareRelease(r))

    def test_tier2_no_duration_high_similarity(self):
        titles = ['Track One']
        s, _ = self._search_with_tracks('0:03:45', titles=titles, threshold=60.0)
        r = self._release(('', 'Track One'))   # no duration but matching title
        result = s._compareRelease(r)
        # tier-2: negative float encoding -(similarity/100)
        self.assertIsInstance(result, float)
        self.assertLess(result, 0.0)
        self.assertGreater(abs(result) * 100, 60.0)  # similarity > threshold

    def test_tier2_rejected_low_similarity(self):
        s, _ = self._search_with_tracks('0:03:45',
                                         titles=['Something Completely Different'],
                                         threshold=60.0)
        r = self._release(('', 'XYZ ABC 123'))
        result = s._compareRelease(r)
        self.assertIs(False, result)

    def test_heading_tracks_excluded(self):
        s, _ = self._search_with_tracks('0:03:45')
        r = _Release('r1', [])
        heading = _Track('', 'Side A', '')
        heading.data = {'type_': 'heading'}
        audio = _Track('1', 'Song', '3:45')
        r._tracklist = [heading, audio]
        result = s._compareRelease(r)
        # Only 1 audio track (heading excluded) vs 1 local → should compare
        self.assertGreaterEqual(result, 0.0)


# ── _natural_sort_key + getSearchParams subdirectory disc detection ───────────

class TestNaturalSortKey(unittest.TestCase):
    """_natural_sort_key sorts numeric parts numerically (Disc 2 before Disc 10).

    Regression: a 10-disc box set (David Bowie – Outside / Earthling / …) was
    never matched because files.sort() placed Disc 10 between Disc 1 and Disc 2,
    so _compareTrackLengths compared the wrong tracks against Discogs positions.
    """

    def _sorted(self, paths):
        from discogstagger.discogs_utils import natural_sort_key
        return sorted(paths, key=natural_sort_key)

    def test_disc_2_before_disc_10(self):
        paths = [
            '/music/Disc 10 (Reality Bonus)/01.flac',
            '/music/Disc 2 (Bonus)/01.flac',
            '/music/Disc 1 (Main)/01.flac',
        ]
        result = self._sorted(paths)
        self.assertTrue(result[0].startswith('/music/Disc 1'))
        self.assertTrue(result[1].startswith('/music/Disc 2'))
        self.assertTrue(result[2].startswith('/music/Disc 10'))

    def test_cd_numbering(self):
        paths = ['/x/CD3/track.flac', '/x/CD10/track.flac', '/x/CD1/track.flac']
        result = self._sorted(paths)
        self.assertIn('CD1', result[0])
        self.assertIn('CD3', result[1])
        self.assertIn('CD10', result[2])

    def test_track_numbering_within_disc(self):
        paths = ['/d/Disc 1/09 - Track.flac', '/d/Disc 1/10 - Track.flac',
                 '/d/Disc 1/01 - Track.flac']
        result = self._sorted(paths)
        self.assertIn('01 - ', result[0])
        self.assertIn('09 - ', result[1])
        self.assertIn('10 - ', result[2])

    def test_plain_alpha_unchanged(self):
        paths = ['/x/Artist/c.flac', '/x/Artist/a.flac', '/x/Artist/b.flac']
        self.assertEqual(self._sorted(paths),
                         ['/x/Artist/a.flac', '/x/Artist/b.flac', '/x/Artist/c.flac'])


class TestSubdirDiscDetection(unittest.TestCase):
    """Disc detection from subdirectory names handles paths with leading /."""

    def _run_subdir_match(self, subdir_path):
        """Run the same regex logic as getSearchParams() after the lstrip fix."""
        import re
        subdir_name = subdir_path.lstrip('/\\')
        m = re.search(r'(?i)^(cd|disc)\s?(?P<n>[0-9]{1,2})', subdir_name)
        return int(m.group('n')) if m else None

    def test_disc_with_leading_slash(self):
        self.assertEqual(1, self._run_subdir_match('/Disc 1 (Excerpts From Outside)'))

    def test_disc_10_with_leading_slash(self):
        self.assertEqual(10, self._run_subdir_match('/Disc 10 (Reality Bonus)'))

    def test_cd_prefix(self):
        self.assertEqual(2, self._run_subdir_match('/CD2'))

    def test_disc_no_space(self):
        self.assertEqual(3, self._run_subdir_match('/Disc3'))

    def test_no_disc_subdir(self):
        self.assertIsNone(self._run_subdir_match('/Art'))

    def test_without_leading_slash(self):
        self.assertEqual(1, self._run_subdir_match('Disc 1 (Some Album)'))


# ── merge_indexed_subtracks + Pass 3 ─────────────────────────────────────────

from discogstagger.discogs_utils import combine_subtrack_titles, merge_indexed_subtracks


class TestCombineSubtrackTitles(unittest.TestCase):
    """combine_subtrack_titles() joining and length-overflow fallback."""

    def test_joins_with_slash(self):
        title, extra = combine_subtrack_titles(['Corrupt', '(silence)', 'Untitled'])
        self.assertEqual(title, 'Corrupt / (silence) / Untitled')
        self.assertIsNone(extra)

    def test_single_title_unchanged(self):
        title, extra = combine_subtrack_titles(['Solo'])
        self.assertEqual(title, 'Solo')
        self.assertIsNone(extra)

    def test_empty_titles_skipped(self):
        title, extra = combine_subtrack_titles(['Corrupt', '', None, 'Untitled'])
        self.assertEqual(title, 'Corrupt / Untitled')
        self.assertIsNone(extra)

    def test_all_empty_returns_empty_string(self):
        title, extra = combine_subtrack_titles(['', None, ''])
        self.assertEqual(title, '')
        self.assertIsNone(extra)

    def test_overflow_falls_back_to_first_title_plus_extra(self):
        titles = ['A Very Long First Movement Title Indeed',
                  'An Equally Long Second Movement Title',
                  'And A Third One Just As Verbose Again']
        title, extra = combine_subtrack_titles(titles, max_length=50)
        self.assertEqual(title, titles[0])
        self.assertEqual(extra, ' / '.join(titles[1:]))

    def test_exactly_at_max_length_not_overflowed(self):
        # 'AB / CD' is 7 chars
        title, extra = combine_subtrack_titles(['AB', 'CD'], max_length=7)
        self.assertEqual(title, 'AB / CD')
        self.assertIsNone(extra)

    def test_one_over_max_length_overflows(self):
        title, extra = combine_subtrack_titles(['AB', 'CDE'], max_length=7)
        self.assertEqual(title, 'AB')
        self.assertEqual(extra, 'CDE')


class TestMergeIndexedSubtracks(unittest.TestCase):
    """Unit tests for merge_indexed_subtracks() in discogs_utils."""

    def test_simple_three_way_merge(self):
        """13a + 13b + 13c → single entry with parent position and summed duration."""
        flat = [
            {'position': '13a', 'title': 'Part A', 'duration': '4:00'},
            {'position': '13b', 'title': 'Part B', 'duration': '3:30'},
            {'position': '13c', 'title': 'Part C', 'duration': '2:30'},
        ]
        merged = merge_indexed_subtracks(flat)
        self.assertIsNotNone(merged)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]['position'], '13')
        self.assertEqual(merged[0]['duration'], '10:00')
        self.assertEqual(merged[0]['title'], 'Part A / Part B / Part C')

    def test_mixed_normal_and_subtrack(self):
        """Only the lettered group is collapsed; adjacent normal tracks are kept."""
        flat = [
            {'position': '1',  'title': 'Normal',  'duration': '3:00'},
            {'position': '2a', 'title': 'Pt A',    'duration': '2:00'},
            {'position': '2b', 'title': 'Pt B',    'duration': '1:30'},
            {'position': '3',  'title': 'Normal 2','duration': '4:00'},
        ]
        merged = merge_indexed_subtracks(flat)
        self.assertIsNotNone(merged)
        self.assertEqual(len(merged), 3)
        self.assertEqual(merged[1]['position'], '2')
        self.assertEqual(merged[1]['duration'], '3:30')

    def test_no_merge_when_no_groups(self):
        """Returns None when no lettered sub-track patterns exist."""
        flat = [
            {'position': '1', 'title': 'T1', 'duration': '3:00'},
            {'position': '2', 'title': 'T2', 'duration': '4:00'},
        ]
        self.assertIsNone(merge_indexed_subtracks(flat))

    def test_no_merge_for_solo_lettered_position(self):
        """A single '13a' with no sibling is not a group — returns None."""
        flat = [{'position': '13a', 'title': 'Solo', 'duration': '4:00'}]
        self.assertIsNone(merge_indexed_subtracks(flat))

    def test_duration_none_when_sub_missing(self):
        """Merged duration is None when any sub-track lacks a duration."""
        flat = [
            {'position': '2a', 'title': 'Pt A', 'duration': '3:00'},
            {'position': '2b', 'title': 'Pt B', 'duration': None},
        ]
        merged = merge_indexed_subtracks(flat)
        self.assertIsNotNone(merged)
        self.assertIsNone(merged[0]['duration'])

    def test_vinyl_positions_not_merged(self):
        """A1, A2 (uppercase-letter prefix) do not match — not merged."""
        flat = [
            {'position': 'A1', 'title': 'Side A T1', 'duration': '3:00'},
            {'position': 'A2', 'title': 'Side A T2', 'duration': '4:00'},
        ]
        self.assertIsNone(merge_indexed_subtracks(flat))

    def test_vinyl_subtracks_merged(self):
        """A1a + A1b (vinyl sub-movements) are merged to A1."""
        flat = [
            {'position': 'A1a', 'title': 'Mvt 1', 'duration': '2:00'},
            {'position': 'A1b', 'title': 'Mvt 2', 'duration': '3:00'},
        ]
        merged = merge_indexed_subtracks(flat)
        self.assertIsNotNone(merged)
        self.assertEqual(merged[0]['position'], 'A1')
        self.assertEqual(merged[0]['duration'], '5:00')

    def test_duration_over_one_hour(self):
        """Duration sum crossing one hour is formatted as h:mm:ss."""
        flat = [
            {'position': '1a', 'title': 'P1', 'duration': '40:00'},
            {'position': '1b', 'title': 'P2', 'duration': '25:00'},
        ]
        merged = merge_indexed_subtracks(flat)
        self.assertEqual(merged[0]['duration'], '1:05:00')

    def test_two_separate_groups(self):
        """Two independent sub-track groups are each merged independently."""
        flat = [
            {'position': '1a', 'title': 'A1', 'duration': '2:00'},
            {'position': '1b', 'title': 'A2', 'duration': '3:00'},
            {'position': '2a', 'title': 'B1', 'duration': '4:00'},
            {'position': '2b', 'title': 'B2', 'duration': '1:00'},
        ]
        merged = merge_indexed_subtracks(flat)
        self.assertIsNotNone(merged)
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0]['position'], '1')
        self.assertEqual(merged[0]['duration'], '5:00')
        self.assertEqual(merged[1]['position'], '2')
        self.assertEqual(merged[1]['duration'], '5:00')


class TestPass3SubtrackMergeInCompareRelease(unittest.TestCase):
    """_compareRelease() Pass 3: sub-track merge fallback."""

    def _search_1file(self, duration, tolerance=10.0):
        """Search with a single local file of the given duration."""
        return _make_search([_local(duration)], tolerance=tolerance)

    def test_accepted_after_merge(self):
        """13a+13b+13c Discogs entries collapse to 1; matches 1 local file."""
        s = self._search_1file('10:00')
        r = _Release('r1', [
            _discogs('13a', 'Part A', '4:00'),
            _discogs('13b', 'Part B', '3:30'),
            _discogs('13c', 'Part C', '2:30'),
        ])
        result = s._compareRelease(r)
        self.assertIsNot(result, False)
        self.assertGreaterEqual(result, 0.0)

    def test_merge_duration_within_tolerance(self):
        """Merged duration (10:00) vs local (10:05) is within 10s tolerance."""
        s = self._search_1file('10:05', tolerance=10.0)
        r = _Release('r1', [
            _discogs('1a', 'Pt A', '4:00'),
            _discogs('1b', 'Pt B', '3:30'),
            _discogs('1c', 'Pt C', '2:30'),
        ])
        result = s._compareRelease(r)
        self.assertIsNot(result, False)

    def test_merge_duration_exceeds_tolerance(self):
        """Merged duration matches count but not duration — rejected on tolerance."""
        s = self._search_1file('10:00', tolerance=5.0)
        r = _Release('r1', [
            _discogs('1a', 'Pt A', '4:00'),
            _discogs('1b', 'Pt B', '5:00'),  # total 9:00 vs local 10:00 = 60s diff
        ])
        self.assertIs(False, s._compareRelease(r))

    def test_rejected_when_merged_count_still_mismatches(self):
        """Merge helps count but result still != local count → rejected."""
        s = _make_search([_local('10:00'), _local('5:00')], tolerance=10.0)  # 2 files
        r = _Release('r1', [
            _discogs('1a', 'Pt A', '4:00'),
            _discogs('1b', 'Pt B', '6:00'),  # merged to 1; local has 2 → mismatch
        ])
        self.assertIs(False, s._compareRelease(r))

    def test_pass1_still_works_when_separate_files_match(self):
        """13a, 13b, 13c files each present locally — no merge needed (Pass 1)."""
        local = [_local('4:00'), _local('3:30'), _local('2:30')]
        s = _make_search(local, tolerance=5.0)
        r = _Release('r1', [
            _discogs('13a', 'Part A', '4:01'),
            _discogs('13b', 'Part B', '3:31'),
            _discogs('13c', 'Part C', '2:31'),
        ])
        result = s._compareRelease(r)
        self.assertIsNot(result, False)


if __name__ == '__main__':
    unittest.main()
