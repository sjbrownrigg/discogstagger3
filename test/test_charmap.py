"""Tests for discogstagger.charmap — character substitution utilities."""
import os
import tempfile
import unittest

parentdir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from discogstagger.charmap import apply_substitutions, strip_invalid, load_substitutions, build_map


# ── apply_substitutions ───────────────────────────────────────────────────────

class TestApplySubstitutions(unittest.TestCase):

    def test_no_substitutions(self):
        self.assertEqual('hello', apply_substitutions('hello', {}))

    def test_single_substitution(self):
        self.assertEqual('hXllo', apply_substitutions('hello', {'e': 'X'}))

    def test_empty_value_removes_char(self):
        self.assertEqual('hllo', apply_substitutions('hello', {'e': ''}))

    def test_multi_char_key(self):
        self.assertEqual('hXXo', apply_substitutions('hello', {'ell': 'XX'}))

    def test_substitutions_applied_in_order(self):
        # 'a' → 'b', then 'b' → 'c': the second rule sees the result of the first
        result = apply_substitutions('a', {'a': 'b', 'b': 'c'})
        self.assertEqual('c', result)

    def test_unicode_key(self):
        self.assertEqual('oe', apply_substitutions('ö', {'ö': 'oe'}))

    def test_unicode_value(self):
        self.assertEqual('12″', apply_substitutions('12"', {'"': '″'}))

    def test_multiple_occurrences(self):
        self.assertEqual('_nd_', apply_substitutions('&nd&', {'&': '_'}))

    def test_empty_string(self):
        self.assertEqual('', apply_substitutions('', {'a': 'b'}))

    def test_no_match(self):
        self.assertEqual('xyz', apply_substitutions('xyz', {'a': 'b'}))


# ── strip_invalid ─────────────────────────────────────────────────────────────

class TestStripInvalid(unittest.TestCase):

    def test_slash_removed_by_default(self):
        self.assertEqual('ab', strip_invalid('a/b'))

    def test_slash_replaced(self):
        self.assertEqual('a-b', strip_invalid('a/b', path_sep_replacement='-'))

    def test_null_byte_removed(self):
        self.assertEqual('ab', strip_invalid('a\x00b'))

    def test_control_chars_removed(self):
        self.assertEqual('ab', strip_invalid('a\x1fb'))
        self.assertEqual('ab', strip_invalid('a\x7fb'))

    def test_control_chars_replaced(self):
        self.assertEqual('a_b', strip_invalid('a\x00b', control_replacement='_'))

    def test_ascii_printable_preserved(self):
        text = "Hello, World! It's 3:45 (fine)."
        self.assertEqual(text, strip_invalid(text))

    def test_unicode_preserved(self):
        self.assertEqual('⅓ ⅔ ñ é', strip_invalid('⅓ ⅔ ñ é'))

    def test_empty_string(self):
        self.assertEqual('', strip_invalid(''))


# ── load_substitutions ────────────────────────────────────────────────────────

class TestLoadSubstitutions(unittest.TestCase):

    def test_linux_profile_is_empty(self):
        subs = load_substitutions(None, 'linux')
        self.assertEqual({}, subs)

    def test_windows_profile_has_colon(self):
        subs = load_substitutions(None, 'windows')
        self.assertIn(':', subs)
        self.assertEqual('-', subs[':'])

    def test_windows_profile_has_question_mark(self):
        subs = load_substitutions(None, 'windows')
        self.assertIn('?', subs)

    def test_missing_profile_returns_empty(self):
        subs = load_substitutions(None, 'nonexistent_profile_xyz')
        self.assertEqual({}, subs)

    def test_missing_file_returns_empty(self):
        subs = load_substitutions('/nonexistent/path/file.yaml', 'linux')
        self.assertEqual({}, subs)

    def test_custom_yaml_file(self):
        yaml_content = "profiles:\n  test_profile:\n    \"a\": \"b\"\n    \"c\": \"\"\n"
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml',
                                         delete=False, encoding='utf-8') as f:
            f.write(yaml_content)
            path = f.name
        try:
            subs = load_substitutions(path, 'test_profile')
            self.assertEqual({'a': 'b', 'c': ''}, subs)
        finally:
            os.unlink(path)


# ── build_map ─────────────────────────────────────────────────────────────────

class TestBuildMap(unittest.TestCase):

    def _make_config(self, profile='linux', ini_exceptions=None):
        """Minimal config stub — avoids loading real TaggerConfig."""
        class _Cfg:
            def get(self, section, option):
                if section == 'details' and option == 'char_profile':
                    return profile
                if section == 'details' and option == 'char_substitutions':
                    return None
                raise Exception('option not found')

            @property
            def character_exceptions(self):
                return ini_exceptions or {}

        return _Cfg()

    def test_linux_profile_no_subs(self):
        cfg = self._make_config('linux')
        result = build_map(cfg)
        self.assertEqual({}, result)

    def test_windows_profile_loaded(self):
        cfg = self._make_config('windows')
        result = build_map(cfg)
        self.assertIn(':', result)

    def test_ini_exceptions_override_yaml(self):
        # windows profile maps ':' → '-'; INI overrides it to '='
        cfg = self._make_config('windows', ini_exceptions={':': '='})
        result = build_map(cfg)
        self.assertEqual('=', result[':'])

    def test_ini_exceptions_additive(self):
        cfg = self._make_config('linux', ini_exceptions={'ö': 'oe'})
        result = build_map(cfg)
        self.assertEqual('oe', result['ö'])

    def test_missing_config_options_fallback_to_linux(self):
        class _BrokenCfg:
            def get(self, *a, **kw):
                raise Exception('not found')
            character_exceptions = {}

        result = build_map(_BrokenCfg())
        self.assertEqual({}, result)   # linux profile = no subs
