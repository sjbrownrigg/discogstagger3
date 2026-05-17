"""Regression tests for complex Discogs release structures.

Each test class captures a specific release that exposed a real-world
edge case in disc/track mapping.  Add a new class whenever a complicated
release is successfully handled so that future refactors can't break it.

Releases covered
----------------
5924594  Dead Or Alive – Sophisticated Boom Box MMXVI (2016, 20-disc box set)
         Demonstrates:
           • Pattern A: index entry whose sub_tracks are individually ripped
             files (8 continuous-mix songs on CD8, each with its own duration)
           • Pattern B: index entry that is a single file containing named
             sub-movements without individual durations (Mighty Mix Parts 1 & 2)
           • Disc-boundary heading classification by tracklist lookahead
             (rather than hard-coded label lists)
           • "Bonus Tracks" section labels correctly concatenated with their
             enclosing album heading (e.g. "Youthquake: Bonus Tracks" for CD4)
"""
import json
import os
import sys
import unittest

import discogs_client as discogs

parentdir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parentdir)

from _common_test import TestDummyResponse, DummyDiscogsAlbum
from discogstagger.discogs_utils import build_flat_tracklist

_RELEASE_DIR = os.path.join(os.path.dirname(__file__), 'release')


def _load_release(release_id: str):
    """Load a Discogs Release object from a test fixture JSON file."""
    fixture = json.load(open(os.path.join(_RELEASE_DIR, f'{release_id}.json'),
                             encoding='utf-8'))
    client = discogs.Client('test')
    return discogs.Release(client, fixture['resp']['release'])


class TestSophisticatedBoomBoxMMXVI(unittest.TestCase):
    """Dead Or Alive – Sophisticated Boom Box MMXVI (release 5924594).

    20-disc box set (17 CDs + 2 DVDs) released 2016.  DVD tracks are
    excluded from album.discs so the tagger sees exactly 17 CD discs.
    """

    @classmethod
    def setUpClass(cls):
        resp = TestDummyResponse("5924594")
        cls.album = DummyDiscogsAlbum(resp).map()

    # ── Disc count and track counts ──────────────────────────────────────────

    def test_disc_count(self):
        self.assertEqual(len(self.album.discs), 17)

    def test_track_counts(self):
        expected = {1: 15, 2: 12, 3: 14, 4: 13, 5: 14,
                    6: 17, 7: 13, 8: 13, 9: 13, 10: 18,
                    11: 13, 12: 12, 13: 12, 14: 12, 15: 12,
                    16: 10, 17: 11}
        actual = {d.discnumber: len(d.tracks) for d in self.album.discs}
        self.assertEqual(actual, expected)

    # ── Disc-level subtitles (used for folder naming) ────────────────────────

    def test_disc_subtitles_plain(self):
        """Discs with their own boundary heading get that heading as subtitle."""
        cases = {
            1:  'Sophisticated Boom Boom',
            3:  'Youthquake',
            5:  'The Youthquake Tour – Live At Hammersmith Odeon, 6th July 1985',
            6:  'Mad, Bad And Dangerous To Know',
            8:  'Rip It Up',
            10: 'Nude',
            11: 'Remade Remodelled',
            12: 'Fan The Flame (Part 1)',
            13: 'Nukleopatra',
            15: 'Fragile',
            16: 'Unbreakable The Fragile Remixes',
        }
        disc_map = {d.discnumber: d for d in self.album.discs}
        for discno, expected in cases.items():
            with self.subTest(disc=discno):
                self.assertEqual(disc_map[discno].discsubtitle, expected)

    def test_disc_subtitles_bonus(self):
        """Bonus discs inherit 'Album: Bonus Tracks' by concatenation."""
        cases = {
            2:  'Sophisticated Boom Boom: Bonus Tracks',
            4:  'Youthquake: Bonus Tracks',
            7:  'Mad, Bad And Dangerous To Know: Bonus Tracks',
            9:  'Rip It Up: Bonus Tracks',
            14: 'Nukleopatra: Bonus Tracks',
        }
        disc_map = {d.discnumber: d for d in self.album.discs}
        for discno, expected in cases.items():
            with self.subTest(disc=discno):
                self.assertEqual(disc_map[discno].discsubtitle, expected)

    # ── Per-track disc subtitle (changes at section boundaries) ─────────────

    def test_cd1_track_subtitles_split_at_bonus(self):
        """CD1 tracks 1–10 are main album; 11–15 are bonus — subtitle changes."""
        d1 = next(d for d in self.album.discs if d.discnumber == 1)
        main_tracks   = [t for t in d1.tracks if t.tracknumber <= 10]
        bonus_tracks  = [t for t in d1.tracks if t.tracknumber >= 11]
        for t in main_tracks:
            self.assertEqual(t.discsubtitle, 'Sophisticated Boom Boom',
                             f'track {t.tracknumber}')
        for t in bonus_tracks:
            self.assertEqual(t.discsubtitle, 'Sophisticated Boom Boom: Bonus Tracks',
                             f'track {t.tracknumber}')

    # ── CD8: Pattern A + Pattern B + regular tracks ──────────────────────────

    def test_cd8_pattern_a_individual_titles(self):
        """CD8 tracks 1–8 are Pattern A: sub_tracks of 'Continuous Mix' with
        individual durations, expanded into separate files."""
        d8 = next(d for d in self.album.discs if d.discnumber == 8)
        expected_titles = [
            'Brand New Lover',
            'My Heart Goes Bang',
            'Something In My House',
            'Lover Come Back To Me',
            'You Spin Me Round (Like A Record)',
            "I'll Save You All My Kisses",
            'In Too Deep',
            'Hooked On Love',
        ]
        for i, title in enumerate(expected_titles):
            self.assertEqual(d8.tracks[i].title, title, f'track {i+1}')

    def test_cd8_pattern_b_mighty_mix_titles(self):
        """CD8 tracks 9–10 are Pattern B: single files containing named
        sub-movements; the track title is the parent index entry."""
        d8 = next(d for d in self.album.discs if d.discnumber == 8)
        self.assertEqual(d8.tracks[8].title, 'Mighty Mix (Part 1)')
        self.assertEqual(d8.tracks[9].title, 'Mighty Mix (Part 2)')

    def test_cd8_pattern_b_movements_in_notes(self):
        """Pattern B movements are stored in the track's notes."""
        d8 = next(d for d in self.album.discs if d.discnumber == 8)
        notes_p1 = getattr(d8.tracks[8], 'notes', '') or ''
        self.assertIn('Wish You Were Here', notes_p1)
        self.assertIn('What I Want', notes_p1)
        notes_p2 = getattr(d8.tracks[9], 'notes', '') or ''
        self.assertIn('Absolutely Nothing', notes_p2)

    def test_cd8_bonus_tracks(self):
        """CD8 tracks 11–13 are standard bonus tracks with Discogs positions."""
        d8 = next(d for d in self.album.discs if d.discnumber == 8)
        self.assertEqual(d8.tracks[10].title, 'Something In My House (Naughty XXX Mix)')
        self.assertEqual(d8.tracks[11].title, "Baby Don't Say Goodbye (The Powerful Club Twelve)")
        self.assertEqual(d8.tracks[12].title, 'Something In My House (Short Version)')

    # ── build_flat_tracklist() shared utility ────────────────────────────────

    def test_build_flat_tracklist_total_count(self):
        """build_flat_tracklist() expands Pattern A and collapses Pattern B so
        the count matches the number of physical files the tagger expects."""
        flat = build_flat_tracklist(_load_release('5924594').tracklist)
        # 17 CDs × their respective track counts (no DVD entries)
        expected_total = 15+12+14+13+14+17+13+13+13+18+13+12+12+12+12+10+11
        self.assertEqual(len(flat), expected_total)

    def test_build_flat_tracklist_pattern_a_expanded(self):
        """Pattern A: 'Continuous Mix' 8 sub_tracks appear as 8 separate entries."""
        flat = build_flat_tracklist(_load_release('5924594').tracklist)
        titles = [e['title'] for e in flat]
        # All 8 continuous-mix songs should be individually present
        self.assertIn('Brand New Lover', titles)
        self.assertIn('Hooked On Love',  titles)

    def test_build_flat_tracklist_pattern_b_collapsed(self):
        """Pattern B: 'Mighty Mix (Part 1)' appears as one entry with parent duration."""
        flat = build_flat_tracklist(_load_release('5924594').tracklist)
        mighty_entries = [e for e in flat if 'Mighty Mix' in (e['title'] or '')]
        self.assertEqual(len(mighty_entries), 2)
        self.assertEqual(mighty_entries[0]['duration'], '7:47')
        self.assertEqual(mighty_entries[1]['duration'], '8:17')

    def test_build_flat_tracklist_no_dvd_entries(self):
        """DVD tracks are excluded from the flat list."""
        release = _load_release('5924594')
        flat = build_flat_tracklist(release.tracklist)
        dvd_entries = [e for e in flat
                       if (e['position'] or '').upper().startswith('DVD')]
        self.assertEqual(dvd_entries, [])


if __name__ == '__main__':
    unittest.main()
