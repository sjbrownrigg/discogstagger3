"""Tests for discogstagger.pathutils — filesystem path resolution."""
import os
import tempfile
import unittest
from pathlib import Path
from unicodedata import normalize

from discogstagger.pathutils import resolve_path


class TestResolvePath(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _touch(self, name: str) -> str:
        """Create an empty file with the given name and return its full path."""
        p = os.path.join(self.tmpdir, name)
        Path(p).touch()
        return p

    # ── Fast path: file exists as given ──────────────────────────────────────

    def test_exact_match_returned_unchanged(self):
        path = self._touch('ordinary_file.flac')
        self.assertEqual(path, resolve_path(path))

    def test_unicode_filename_exact_match(self):
        # Curly apostrophe is valid on Linux — exact match always wins
        path = self._touch("I Can’t Let You Go.flac")
        self.assertEqual(path, resolve_path(path))

    # ── NFC / NFD normalisation ───────────────────────────────────────────────

    def test_nfc_normalisation(self):
        # File stored in NFD form (decomposed); query in NFC (composed)
        nfd_name = normalize('NFD', 'Ångström.flac')
        nfc_name = normalize('NFC', 'Ångström.flac')
        self._touch(nfd_name)
        query = os.path.join(self.tmpdir, nfc_name)
        resolved = resolve_path(query)
        self.assertTrue(os.path.exists(resolved),
                        f"resolved path does not exist: {resolved!r}")

    def test_nfd_normalisation(self):
        # File stored in NFC; query in NFD
        nfc_name = normalize('NFC', 'Café.flac')
        nfd_name = normalize('NFD', 'Café.flac')
        self._touch(nfc_name)
        query = os.path.join(self.tmpdir, nfd_name)
        resolved = resolve_path(query)
        self.assertTrue(os.path.exists(resolved))

    # ── Wildcard scan: '?' matches any single character ───────────────────────

    def test_question_mark_matches_non_ascii(self):
        # Simulate the WSL2/CIFS encoding bug: the file exists with a curly
        # apostrophe (U+2019) but the stored path has ASCII '?' in its place.
        real_name = "I Can’t Let You Go.flac"
        self._touch(real_name)
        bad_path = os.path.join(self.tmpdir, "I Can?t Let You Go.flac")
        resolved = resolve_path(bad_path)
        self.assertEqual(os.path.join(self.tmpdir, real_name), resolved)

    def test_question_mark_matches_any_single_char(self):
        self._touch("Die 3. Generation.flac")
        bad_path = os.path.join(self.tmpdir, "Die 3? Generation.flac")
        resolved = resolve_path(bad_path)
        self.assertEqual(os.path.join(self.tmpdir, "Die 3. Generation.flac"), resolved)

    def test_no_question_mark_skips_scan(self):
        # Path has no '?' so the scan should not run; return original even if
        # a similar file exists
        self._touch("something_else.flac")
        missing = os.path.join(self.tmpdir, "nonexistent.flac")
        self.assertEqual(missing, resolve_path(missing))

    def test_multiple_wildcards(self):
        # Multiple '?' characters — each matches one character
        self._touch("A1-B2.flac")
        bad_path = os.path.join(self.tmpdir, "??-??.flac")
        resolved = resolve_path(bad_path)
        self.assertEqual(os.path.join(self.tmpdir, "A1-B2.flac"), resolved)

    # ── No match ─────────────────────────────────────────────────────────────

    def test_no_match_returns_original(self):
        # File genuinely doesn't exist
        path = os.path.join(self.tmpdir, "ghost.flac")
        self.assertEqual(path, resolve_path(path))

    def test_no_match_with_question_mark_returns_original(self):
        # '?' present but no file matches the pattern
        path = os.path.join(self.tmpdir, "no?match.flac")
        self.assertEqual(path, resolve_path(path))

    def test_nonexistent_parent_returns_original(self):
        path = '/nonexistent/parent/dir/file.flac'
        self.assertEqual(path, resolve_path(path))

    # ── Ambiguous match ───────────────────────────────────────────────────────

    def test_ambiguous_returns_first_match(self):
        # Two files match the same '?' pattern; first alphabetically is used
        self._touch("A.flac")
        self._touch("B.flac")
        bad_path = os.path.join(self.tmpdir, "?.flac")
        resolved = resolve_path(bad_path)
        self.assertTrue(os.path.exists(resolved))
