"""Tests for MusicBrainz and ISRC tag writing in TagHandler.

Verifies:
  - musicbrainz_releaseid is written when album.source == 'musicbrainz'
  - discogs_id is written when album.source == 'discogs' (regression)
  - Neither release ID is written when album.source == 'existing_tags'
  - isrc is written from track.isrc when present
  - musicbrainz_trackid is written from track.mbid when present
  - Custom MediaFile fields (musicbrainz_releaseid, musicbrainz_trackid, isrc)
    are registered and readable
"""
import os
import sys
import shutil
import tempfile
import unittest

parentdir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parentdir)

from _common_test import TestDummyResponse, DummyDiscogsAlbum
from discogstagger.tagger_config import TaggerConfig
from discogstagger.taggerutils import TaggerUtils, TagHandler
from discogstagger.mediafile_ext import MediaFile


def _config():
    return TaggerConfig(os.path.join(parentdir, 'test', 'empty.conf'))


def _discogs_album():
    resp = TestDummyResponse('3083')
    return DummyDiscogsAlbum(resp).map()


def _write_tag(album, track, tmpdir, source_override=None):
    """Tag a dummy FLAC file and return the MediaFile for inspection."""
    src = os.path.join(parentdir, 'test', 'files', 'test.flac')
    dest = os.path.join(tmpdir, 'test.flac')
    shutil.copy(src, dest)

    track.orig_file = 'test.flac'
    track.new_file  = 'test.flac'

    if source_override is not None:
        album.source = source_override

    cfg = _config()
    th = TagHandler(album, cfg)
    th.tag_single_track(tmpdir, track)

    return MediaFile(dest)


# ---------------------------------------------------------------------------
# Custom field registration
# ---------------------------------------------------------------------------

class TestCustomFieldsRegistered(unittest.TestCase):
    """The three new custom fields are registered on MediaFile.

    MediaField descriptors raise AttributeError on class-level access (they
    only resolve on instances), so we check MediaFile.__dict__ directly
    rather than using hasattr().
    """

    def test_musicbrainz_releaseid_registered(self):
        self.assertIn('musicbrainz_releaseid', MediaFile.__dict__)

    def test_musicbrainz_trackid_registered(self):
        self.assertIn('musicbrainz_trackid', MediaFile.__dict__)

    def test_isrc_registered(self):
        self.assertIn('isrc', MediaFile.__dict__)


# ---------------------------------------------------------------------------
# Release ID routing by source
# ---------------------------------------------------------------------------

class TestReleaseIdRouting(unittest.TestCase):
    """Release ID is written to the correct field based on album.source."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.album  = _discogs_album()
        self.track  = self.album.discs[0].tracks[0]

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_discogs_source_writes_discogs_id(self):
        mf = _write_tag(self.album, self.track, self.tmpdir, source_override='discogs')
        self.assertEqual(str(mf.discogs_id), str(self.album.id))
        # MB field should be empty for a Discogs release
        self.assertFalsy(mf.musicbrainz_releaseid)

    def test_musicbrainz_source_writes_musicbrainz_releaseid(self):
        fake_mbid = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
        self.album.id = fake_mbid
        mf = _write_tag(self.album, self.track, self.tmpdir,
                         source_override='musicbrainz')
        self.assertEqual(mf.musicbrainz_releaseid, fake_mbid)
        # Discogs field should be empty for a MB release
        self.assertFalsy(mf.discogs_id)

    def test_existing_tags_writes_no_release_id(self):
        mf = _write_tag(self.album, self.track, self.tmpdir,
                         source_override='existing_tags')
        self.assertFalsy(mf.discogs_id)
        self.assertFalsy(mf.musicbrainz_releaseid)

    def test_no_source_attr_defaults_to_discogs(self):
        """When album.source is not set, Discogs ID is written (backward compat)."""
        # Album uses __getattr__ returning None for unknown attrs; removing
        # the attribute from __dict__ restores that fallback behaviour.
        self.album.__dict__.pop('source', None)
        mf = _write_tag(self.album, self.track, self.tmpdir)
        self.assertEqual(str(mf.discogs_id), str(self.album.id))

    def assertFalsy(self, value):
        if value:
            self.fail(f'Expected falsy, got {value!r}')


# ---------------------------------------------------------------------------
# Track-level MB tags
# ---------------------------------------------------------------------------

class TestTrackMBTags(unittest.TestCase):
    """isrc and musicbrainz_trackid are written from track attributes."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.album  = _discogs_album()
        self.album.source = 'musicbrainz'
        self.track  = self.album.discs[0].tracks[0]

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _tag(self):
        return _write_tag(self.album, self.track, self.tmpdir)

    def test_isrc_written_when_present(self):
        self.track.isrc = 'GBAYE0400099'
        mf = self._tag()
        self.assertEqual(mf.isrc, 'GBAYE0400099')

    def test_isrc_not_written_when_absent(self):
        # Track.__getattr__ returns None for unknown attrs — no isrc on a
        # Discogs track, so nothing should be written.
        self.track.__dict__.pop('isrc', None)
        mf = self._tag()
        self.assertIsNone(mf.isrc)

    def test_musicbrainz_trackid_written_when_present(self):
        self.track.mbid = '11111111-2222-3333-4444-555555555555'
        mf = self._tag()
        self.assertEqual(mf.musicbrainz_trackid, '11111111-2222-3333-4444-555555555555')

    def test_musicbrainz_trackid_not_written_when_absent(self):
        self.track.__dict__.pop('mbid', None)
        mf = self._tag()
        self.assertIsNone(mf.musicbrainz_trackid)

    def test_both_tags_written_together(self):
        self.track.isrc = 'USRC17607839'
        self.track.mbid = 'deadbeef-dead-dead-dead-deaddeadbeef'
        mf = self._tag()
        self.assertEqual(mf.isrc, 'USRC17607839')
        self.assertEqual(mf.musicbrainz_trackid, 'deadbeef-dead-dead-dead-deaddeadbeef')

    def test_isrc_written_for_discogs_source_too(self):
        """ISRC is source-agnostic — written regardless of album.source."""
        self.album.source = 'discogs'
        self.track.isrc = 'GBAYE0400099'
        mf = self._tag()
        self.assertEqual(mf.isrc, 'GBAYE0400099')


if __name__ == '__main__':
    unittest.main()
