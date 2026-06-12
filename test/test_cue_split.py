"""Tests for _splitCueFile()'s stash-to-.cue step.

Covers the fix for shutil.Error: "Destination path '...' already exists"
when a previous run already stashed a CUE/image file of the same name
in the .cue done directory (e.g. a re-run after a failed/partial process).
"""
import os
import sys
import shutil
import tempfile
import unittest
import unittest.mock

parentdir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(parentdir)

from discogstagger.tagger_config import TaggerConfig
from discogstagger.fileutils import FileUtils
from discogstagger.cue import CUE


def _config():
    return TaggerConfig(os.path.join(parentdir, "test/empty.conf"))


CUE_TEMPLATE = '''PERFORMER "Test Artist"
TITLE "Test Album"
FILE "{image_name}" WAVE
  TRACK 01 AUDIO
    TITLE "Track One"
    INDEX 01 00:00:00
'''


class TestSplitCueFileStash(unittest.TestCase):
    """_splitCueFile() must not crash when .cue already contains a
    same-named file from a previous run — it should overwrite instead."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.image_name = 'Album.flac'
        self.cue_name = 'Album.cue'

        shutil.copy2(os.path.join(parentdir, 'test/files/test.flac'),
                      os.path.join(self.tmpdir, self.image_name))
        with open(os.path.join(self.tmpdir, self.cue_name), 'w', encoding='utf-8') as f:
            f.write(CUE_TEMPLATE.format(image_name=self.image_name))

        opts = unittest.mock.MagicMock()
        opts.forceUpdate = False
        self.fu = FileUtils(_config(), opts)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _make_cue(self):
        cue = CUE(os.path.join(self.tmpdir, self.cue_name))
        cue.output_format = '%n'
        return cue

    def test_overwrites_existing_stashed_files(self):
        done_dir = os.path.join(self.tmpdir, self.fu.cue_done_dir)
        os.makedirs(done_dir, exist_ok=True)
        # Simulate a previous run that already stashed files with the same names.
        with open(os.path.join(done_dir, self.cue_name), 'w') as f:
            f.write('stale cue')
        with open(os.path.join(done_dir, self.image_name), 'wb') as f:
            f.write(b'stale image')

        cue = self._make_cue()
        with unittest.mock.patch.object(self.fu, '_tagFiles'):
            result = self.fu._splitCueFile(cue)

        self.assertEqual(result, 0)
        # New files should have replaced the stale stashed ones.
        with open(os.path.join(done_dir, self.cue_name), encoding='utf-8') as f:
            self.assertIn('Album', f.read())
        self.assertGreater(
            os.path.getsize(os.path.join(done_dir, self.image_name)), len(b'stale image'))
        # Source files should have been moved out.
        self.assertFalse(os.path.exists(os.path.join(self.tmpdir, self.cue_name)))
        self.assertFalse(os.path.exists(os.path.join(self.tmpdir, self.image_name)))

    def test_no_existing_stash_still_works(self):
        cue = self._make_cue()
        with unittest.mock.patch.object(self.fu, '_tagFiles'):
            result = self.fu._splitCueFile(cue)

        self.assertEqual(result, 0)
        done_dir = os.path.join(self.tmpdir, self.fu.cue_done_dir)
        self.assertTrue(os.path.exists(os.path.join(done_dir, self.cue_name)))
        self.assertTrue(os.path.exists(os.path.join(done_dir, self.image_name)))


if __name__ == '__main__':
    unittest.main()
