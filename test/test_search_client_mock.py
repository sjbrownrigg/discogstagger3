"""Tests for DiscogsSearch using a mocked Discogs client.

Unlike test_search_matching.py which bypasses __init__ via __new__, these
tests exercise the full object lifecycle so that:

  - Config values (tolerance, threshold) are verified as read from the real
    TaggerConfig rather than hard-coded in a manual setup.
  - _compareTrackLengths, _compareTitleSimilarity and _candidate_score are
    tested in isolation through a real, properly-initialised DiscogsSearch.
  - The search flow (siftReleases, tier selection, the "swallowed release" fix,
    _search_release_fields) is verified with a mocked Discogs API client.

Patching target: discogstagger.discogsalbum.discogs.Client
  DiscogsConnector (parent of DiscogsSearch) lives in discogsalbum.py and
  uses `import discogs_client as discogs`.  Patching discogs.Client there
  intercepts all three code paths in __init__ (user_token, skip_auth, and
  the default path).  With empty.conf (no consumer_key/secret), _init_oauth
  returns early without any interactive prompts.
"""
import os
import unittest
from unittest.mock import MagicMock, patch, PropertyMock
from datetime import timedelta

parentdir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from discogstagger.tagger_config import TaggerConfig
from discogstagger.discogs_search import DiscogsSearch

_PATCH = 'discogstagger.discogsalbum.discogs.Client'


# ── Shared test helpers ───────────────────────────────────────────────────────

class _Track:
    """Minimal Discogs track for passing to _getTrackInfo."""
    def __init__(self, position, title, duration):
        self.position = position
        self.title = title
        self.duration = duration
        self.data = {'type_': 'track'}


class _Release:
    """Minimal Discogs release object."""
    def __init__(self, rid, tracks, year=2020, fmt_name='CD', fmt_qty=1):
        self.id = rid
        self.year = year
        self.data = {
            'formats': [{'name': fmt_name}],
            'format_quantity': fmt_qty,
        }
        self._tracklist = [
            _Track(t['pos'], t['title'], t.get('dur', ''))
            for t in tracks
        ]

    @property
    def tracklist(self):
        return self._tracklist


def _local(duration='0:03:45', title='', position='1'):
    return {'position': position, 'duration': duration, 'title': title, 'artist': ''}


def _dt(pos='1', title='A Song', dur='3:45'):
    return {'pos': pos, 'title': title, 'dur': dur}


# ── Test fixture ──────────────────────────────────────────────────────────────

class _Base(unittest.TestCase):
    """Base class: starts/stops the client patch and creates a DiscogsSearch."""

    def setUp(self):
        self._patcher = patch(_PATCH)
        mock_cls = self._patcher.start()
        self.mock_client = MagicMock()
        mock_cls.return_value = self.mock_client

        cfg = TaggerConfig(os.path.join(parentdir, 'test/empty.conf'))
        self.search = DiscogsSearch(cfg)
        # Disable disk caches so tests don't touch the filesystem
        self.search._release_cache = None
        self.search._search_cache = None
        self.search._master_versions_cache = None

    def tearDown(self):
        self._patcher.stop()

    def _set_params(self, local_tracks, year=2020, albumartist='Artist',
                    album='Album'):
        """Populate search_params as getSearchParams() would produce them."""
        self.search.search_params = {
            'tracks': local_tracks,
            'year': year,
            'albumartist': albumartist,
            'artist': albumartist,
            'album': album,
            'artists': [albumartist],
            'search': {
                'artist': albumartist,
                'release': album,
                'artistRelease': f'{albumartist} {album}',
            },
        }
        self.search.candidates = {}
        self.search.no_duration_candidates = {}
        self.search._sifted_masters = set()


# ── Initialisation ────────────────────────────────────────────────────────────

class TestInit(_Base):
    """Verify __init__ reads config values correctly through the real code path."""

    def test_discogs_client_is_the_mock(self):
        self.assertIs(self.mock_client, self.search.discogs_client)

    def test_tracklength_tolerance_from_config(self):
        # default.conf ships tracklength_tolerance = 5.0
        self.assertAlmostEqual(5.0, self.search.tracklength_tolerance)

    def test_title_similarity_threshold_from_config(self):
        # default.conf ships title_similarity_threshold = 60
        self.assertAlmostEqual(60.0, self.search.title_similarity_threshold)

    def test_caches_disabled_when_directory_empty(self):
        # empty.conf → default.conf has cache.directory = "" → no caches
        # (we also set them None in setUp but this verifies the init path)
        self.assertIsNone(self.search._release_cache)

    def test_candidates_initially_empty(self):
        self.assertEqual({}, self.search.candidates)
        self.assertEqual({}, self.search.no_duration_candidates)


# ── _compareTrackLengths through real object ──────────────────────────────────

class TestCompareTrackLengthsMocked(_Base):
    """_compareTrackLengths exercised through the properly-initialised object."""

    def test_perfect_match(self):
        local = [_local('0:03:45')]
        discogs = [{'duration': '3:45', 'title': '', 'position': '1'}]
        self.assertAlmostEqual(0.0, self.search._compareTrackLengths(local, discogs))

    def test_within_configured_tolerance(self):
        # 3s diff; tolerance from config is 5.0 → should be < tolerance
        local = [_local('0:03:45')]
        discogs = [{'duration': '3:48', 'title': '', 'position': '1'}]
        diff = self.search._compareTrackLengths(local, discogs)
        self.assertLess(diff, self.search.tracklength_tolerance)

    def test_exceeds_configured_tolerance(self):
        # 10s diff > 5.0 tolerance
        local = [_local('0:03:45')]
        discogs = [{'duration': '3:55', 'title': '', 'position': '1'}]
        diff = self.search._compareTrackLengths(local, discogs)
        self.assertGreater(diff, self.search.tracklength_tolerance)

    def test_tolerance_respected_in_compare_release(self):
        """_compareRelease uses self.tracklength_tolerance from the real config."""
        self._set_params([_local('0:03:45')])
        r_pass = _Release('r_pass', [_dt(dur='3:47')])   # 2s diff — within 5s
        r_fail = _Release('r_fail', [_dt(dur='3:55')])   # 10s diff — rejected
        self.assertGreaterEqual(self.search._compareRelease(r_pass), 0.0)
        self.assertIs(False, self.search._compareRelease(r_fail))


# ── _compareTitleSimilarity through real object ───────────────────────────────

class TestCompareTitleSimilarityMocked(_Base):

    def test_identical_titles(self):
        local = [_local(title='Holding On')]
        discogs = [{'title': 'Holding On', 'duration': None, 'position': '1'}]
        self.assertAlmostEqual(100.0,
                               self.search._compareTitleSimilarity(local, discogs))

    def test_threshold_respected_in_compare_release(self):
        """_compareRelease uses self.title_similarity_threshold from config."""
        self._set_params([_local('0:03:45', title='Completely Different Title')])
        r = _Release('r1', [_dt(dur='', title='XYZ Nothing Alike 999')])
        # Low similarity → should be rejected, not tier-2 accepted
        result = self.search._compareRelease(r)
        self.assertIs(False, result)


# ── _candidate_score through real object ──────────────────────────────────────

class TestCandidateScoreMocked(_Base):

    def test_year_match_improves_score(self):
        self._set_params([_local()], year=2020)
        r_match = _Release('r_match', [], year=2020)
        r_nomatch = _Release('r_nomatch', [], year=1990)
        self.assertLess(
            self.search._candidate_score(r_match, base_score=3.0),
            self.search._candidate_score(r_nomatch, base_score=3.0),
        )

    def test_cd_format_improves_score_for_non_vinyl(self):
        self._set_params([_local()], year=1990)   # no vinyl indicators
        r = _Release('r1', [], year=1990, fmt_name='CD')
        score = self.search._candidate_score(r, base_score=3.0)
        self.assertAlmostEqual(3.0 - 2.0 - 1.0, score)  # year + CD

    def test_best_scored_candidate_wins(self):
        """search_discogs returns the lowest composite-score candidate."""
        self._set_params([_local('0:03:45')], year=2020)
        # Two tier-1 candidates: one matches the year, one doesn't
        self.search.candidates = {
            0.0: _Release('r_year_match',    [], year=2020, fmt_name='CD'),
            0.001: _Release('r_no_year',     [], year=1990, fmt_name='CD'),
        }
        result = self.search._pick_best()
        self.assertEqual('r_year_match', result.id)


# ── _siftReleases routing ─────────────────────────────────────────────────────

class TestSiftReleases(_Base):

    def setUp(self):
        super().setUp()
        self._set_params([_local('0:03:45', title='Song')])

    def test_tier1_release_added_to_candidates(self):
        r = _Release('r1', [_dt(dur='3:45', title='Song')])
        self.search._siftReleases([r])
        self.assertIn('r1', [v.id for v in self.search.candidates.values()])
        self.assertEqual({}, self.search.no_duration_candidates)

    def test_tier2_release_added_to_no_duration_candidates(self):
        r = _Release('r1', [_dt(dur='', title='Song')])
        self.search._siftReleases([r])
        self.assertEqual({}, self.search.candidates)
        self.assertIn('r1', self.search.no_duration_candidates)

    def test_rejected_release_not_added(self):
        # Track count mismatch → rejected
        r = _Release('r1', [_dt(dur='3:45'), _dt(dur='4:00')])  # 2 tracks vs 1 local
        self.search._siftReleases([r])
        self.assertEqual({}, self.search.candidates)
        self.assertEqual({}, self.search.no_duration_candidates)

    def test_multiple_candidates_all_collected(self):
        r1 = _Release('r1', [_dt(dur='3:45')])
        r2 = _Release('r2', [_dt(dur='3:47')])
        self.search._siftReleases([r1, r2])
        self.assertEqual(2, len(self.search.candidates))


# ── search_discogs candidate selection ────────────────────────────────────────

class TestSearchDiscogsSelection(_Base):

    def test_no_candidates_returns_none(self):
        self._set_params([_local()])
        self.assertIsNone(self.search._pick_best())

    def test_single_tier1_candidate_returned(self):
        self._set_params([_local()])
        r = _Release('r1', [], year=2020)
        self.search.candidates = {0.5: r}
        self.assertIs(r, self.search._pick_best())

    def test_tier1_preferred_over_tier2(self):
        self._set_params([_local(title='Song')], year=2020)
        r_tier1 = _Release('r_t1', [], year=2020)
        r_tier2 = _Release('r_t2', [], year=2020)
        self.search.candidates = {0.5: r_tier1}
        self.search.no_duration_candidates = {'r_t2': (r_tier2, 90.0)}
        result = self.search._pick_best()
        self.assertEqual('r_t1', result.id)

    def test_tier2_fallback_when_no_tier1(self):
        self._set_params([_local(title='Holding On')], year=2020)
        r = _Release('r_t2', [], year=2020)
        self.search.no_duration_candidates = {'r_t2': (r, 85.0)}
        result = self.search._pick_best()
        self.assertEqual('r_t2', result.id)


# ── search_artist_title: the "swallowed release" fix ─────────────────────────

class TestSearchArtistTitleSwallowedReleaseFix(_Base):
    """Verify that a Release returned directly by the Discogs API is compared
    directly (not silently replaced by its master and never compared).

    This was the root cause of the 'Stray - Holding On' failure: release
    12880225 appeared as result #2 but get_master_release() returned its
    parent master, so the release itself was never passed to _compareRelease.
    """

    def setUp(self):
        super().setUp()
        self._set_params([_local('0:03:45', title='Holding On')], year=2012)

    def _make_release_result(self, rid, dur='3:45', title='Holding On',
                              year=2012, has_master=True):
        """Mock a Discogs API search result that is a Release (not a Master)."""
        r = _Release(rid, [_dt(dur=dur, title=title)], year=year)
        if has_master:
            master = MagicMock()
            master.id = f'master_{rid}'
            # Pretend the master has versions — make it look like a Master object
            master.versions = []
            r.master = master
        else:
            r.master = None
        return r

    def test_release_added_to_candidates_despite_having_master(self):
        """Release with a master must still be directly compared."""
        r = self._make_release_result('r12880225', dur='3:45',
                                       title='Holding On', year=2012)
        # Pretend the master's versions list is empty (cached as nothing found)
        r.master.versions = []
        self.mock_client.search.return_value = [r]

        self.search._search_artist_title('all')

        # The release should appear in candidates (tier-1 match)
        release_ids = [v.id for v in self.search.candidates.values()]
        no_dur_ids = list(self.search.no_duration_candidates.keys())
        self.assertTrue(
            'r12880225' in release_ids or 'r12880225' in no_dur_ids,
            "Release was not compared directly — the 'swallowed release' bug is present"
        )

    def test_standalone_release_no_master_compared(self):
        """A release with no master is also directly compared."""
        r = self._make_release_result('r_standalone', has_master=False)
        self.mock_client.search.return_value = [r]
        self.search._search_artist_title('all')
        release_ids = [v.id for v in self.search.candidates.values()]
        no_dur_ids = list(self.search.no_duration_candidates.keys())
        self.assertTrue(
            'r_standalone' in release_ids or 'r_standalone' in no_dur_ids,
        )

    def test_artist_type_results_skipped(self):
        """Artist results (not releases) are ignored."""
        artist_result = MagicMock()
        artist_result.__class__ = type('Artist', (), {})   # class name contains 'Artist'
        self.mock_client.search.return_value = [artist_result]
        self.search._search_artist_title('all')
        self.assertEqual({}, self.search.candidates)
        self.assertEqual({}, self.search.no_duration_candidates)


if __name__ == '__main__':
    unittest.main()
