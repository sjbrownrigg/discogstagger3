"""Tests for discogstagger.formatcodes."""
import os
import unittest

parentdir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from discogstagger.formatcodes import load_format_codes, compute_format_code, compute_edition


class TestFormatCodes(unittest.TestCase):

    def setUp(self):
        self.fc = load_format_codes()   # uses the default conf/format_codes.yaml

    # ── base format names ─────────────────────────────────────────────────────

    def test_cd_album(self):
        self.assertEqual('CD', compute_format_code('CD', ['Album'], 1, self.fc))

    def test_vinyl_album(self):
        self.assertEqual('LP', compute_format_code('Vinyl', ['Album'], 1, self.fc))

    def test_cassette(self):
        self.assertEqual('MC', compute_format_code('Cassette', ['Album'], 1, self.fc))

    def test_file(self):
        self.assertEqual('DM', compute_format_code('File', ['Album'], 1, self.fc))

    def test_unknown_format_falls_back_to_name(self):
        self.assertEqual('8-Track', compute_format_code('8-Track', [], 1, self.fc))

    # ── vinyl sizes ───────────────────────────────────────────────────────────

    def test_vinyl_7inch(self):
        # Album suffix suppressed → bare size code
        self.assertEqual('7″', compute_format_code('Vinyl', ['7"', 'Album'], 1, self.fc))

    def test_vinyl_12inch_album_stays_lp(self):
        # 12" vinyl Album → LP (size adds no info for albums; use LP)
        self.assertEqual('LP', compute_format_code('Vinyl', ['12"', 'Album'], 1, self.fc))

    def test_vinyl_12inch_single_shows_size(self):
        # 12" vinyl Single → 12″ (size distinguishes from 7" single)
        self.assertEqual('12″', compute_format_code('Vinyl', ['12"', 'Single'], 1, self.fc))

    def test_vinyl_10inch(self):
        self.assertEqual('10″', compute_format_code('Vinyl', ['10"', 'Album'], 1, self.fc))

    def test_vinyl_no_size_is_lp(self):
        # No size description → falls back to LP
        self.assertEqual('LP', compute_format_code('Vinyl', ['Album', '33 ⅓ RPM'], 1, self.fc))

    # ── type descriptions no longer affect the code ───────────────────────────
    # Release type (Single, EP, Maxi-Single, etc.) is now carried by
    # album.release_type / %releasetype% — not encoded in the format code.

    def test_cd_single_type_not_encoded(self):
        self.assertEqual('CD', compute_format_code('CD', ['Single'], 1, self.fc))

    def test_cd_maxi_single_type_not_encoded(self):
        self.assertEqual('CD', compute_format_code('CD', ['Maxi-Single'], 1, self.fc))

    def test_cd_ep_type_not_encoded(self):
        self.assertEqual('CD', compute_format_code('CD', ['EP'], 1, self.fc))

    def test_7inch_single_type_not_encoded(self):
        # Size override still applies; type suffix removed
        self.assertEqual('7″', compute_format_code('Vinyl', ['7"', 'Single'], 1, self.fc))

    def test_12inch_maxi_type_not_encoded(self):
        self.assertEqual('12″', compute_format_code('Vinyl', ['12"', 'Maxi-Single'], 1, self.fc))

    def test_12inch_ep_type_not_encoded(self):
        self.assertEqual('12″', compute_format_code('Vinyl', ['12"', 'EP'], 1, self.fc))

    def test_album_description_no_suffix(self):
        self.assertEqual('CD', compute_format_code('CD', ['Album'], 1, self.fc))
        self.assertEqual('LP', compute_format_code('Vinyl', ['Album'], 1, self.fc))

    # ── edition/modifier descriptions no longer affect the code ───────────────
    # Edition qualifiers (Limited Edition, Numbered) are now carried by
    # %edition% — not encoded as prefixes in the format code.

    def test_limited_edition_not_encoded(self):
        self.assertEqual('CD', compute_format_code('CD', ['Single', 'Limited Edition'], 1, self.fc))
        self.assertEqual('LP', compute_format_code('Vinyl', ['Album', 'Limited Edition'], 1, self.fc))

    def test_numbered_not_encoded(self):
        self.assertEqual('CD', compute_format_code('CD', ['Album', 'Numbered'], 1, self.fc))

    def test_limited_and_numbered_not_encoded(self):
        self.assertEqual('CD', compute_format_code('CD', ['Album', 'Limited Edition', 'Numbered'], 1, self.fc))

    # ── quantity ──────────────────────────────────────────────────────────────
    # Multi-disc quantity is still a physical property encoded in format_code.

    def test_double_lp(self):
        self.assertEqual('DLP', compute_format_code('Vinyl', ['Album'], 2, self.fc))

    def test_double_cd(self):
        self.assertEqual('DCD', compute_format_code('CD', ['Album'], 2, self.fc))

    def test_triple_cd(self):
        self.assertEqual('3xCD', compute_format_code('CD', ['Album'], 3, self.fc))

    def test_limited_double_cd_only_quantity_prefix(self):
        # Limited Edition no longer adds L prefix — only quantity D remains
        self.assertEqual('DCD', compute_format_code('CD', ['Album', 'Limited Edition'], 2, self.fc))

    # ── ignored descriptions don't affect the code ────────────────────────────

    def test_vinyl_speed_ignored(self):
        self.assertEqual('LP', compute_format_code('Vinyl', ['Album', '33 ⅓ RPM'], 1, self.fc))
        self.assertEqual('7″', compute_format_code('Vinyl', ['7"', 'Single', '45 RPM'], 1, self.fc))

    def test_compilation_ignored(self):
        self.assertEqual('LP', compute_format_code('Vinyl', ['Album', 'Compilation'], 1, self.fc))

    def test_remastered_ignored(self):
        self.assertEqual('CD', compute_format_code('CD', ['Album', 'Remastered'], 1, self.fc))

    # ── edge cases ────────────────────────────────────────────────────────────

    def test_empty_descriptions(self):
        self.assertEqual('CD', compute_format_code('CD', [], 1, self.fc))

    def test_no_format_codes(self):
        # Empty rules → returns format_name unchanged
        self.assertEqual('Vinyl', compute_format_code('Vinyl', ['Album'], 1, {}))

    def test_disctotal_one_no_prefix(self):
        self.assertEqual('LP', compute_format_code('Vinyl', ['Album'], 1, self.fc))

    def test_file_with_flac_description(self):
        # FLAC description is ignored — code is DM (Digital Media)
        self.assertEqual('DM', compute_format_code('File', ['Album', 'FLAC', '320 kbps'], 1, self.fc))


# ── compute_edition ───────────────────────────────────────────────────────────

class TestComputeEdition(unittest.TestCase):

    def setUp(self):
        self.fc = load_format_codes()

    # exact matches ────────────────────────────────────────────────────────────

    def test_deluxe_edition_found(self):
        self.assertEqual('Deluxe Edition',
                         compute_edition(['Album', 'Deluxe Edition'], self.fc))

    def test_anniversary_edition_found(self):
        self.assertEqual('Anniversary Edition',
                         compute_edition(['Anniversary Edition'], self.fc))

    def test_special_edition_found(self):
        self.assertEqual('Special Edition',
                         compute_edition(['Album', 'Special Edition'], self.fc))

    # case-insensitive matching ────────────────────────────────────────────────

    def test_uppercase_description_matched(self):
        # Discogs data is not always consistently cased
        result = compute_edition(['DELUXE EDITION'], self.fc)
        self.assertEqual('DELUXE EDITION', result)

    def test_mixed_case_matched(self):
        result = compute_edition(['deluxe edition'], self.fc)
        self.assertEqual('deluxe edition', result)

    # substring matching ───────────────────────────────────────────────────────

    def test_numbered_anniversary_matched(self):
        # "Anniversary Edition" pattern matches "30th Anniversary Edition"
        result = compute_edition(['30th Anniversary Edition'], self.fc)
        self.assertEqual('30th Anniversary Edition', result)

    def test_super_deluxe_matched_by_deluxe_pattern(self):
        # "Deluxe Edition" pattern is a substring of "Super Deluxe Edition"
        result = compute_edition(['Super Deluxe Edition'], self.fc)
        self.assertEqual('Super Deluxe Edition', result)

    def test_full_description_returned_not_pattern(self):
        # The exact Discogs string is returned so it displays correctly
        result = compute_edition(['40th Anniversary Edition'], self.fc)
        self.assertEqual('40th Anniversary Edition', result)

    # the Young Gods case ──────────────────────────────────────────────────────

    def test_young_gods_combined_descriptions(self):
        # release 4103383: combined descriptions from three format entries
        descs = ['Album', 'Reissue', 'Remastered', 'Album', 'Deluxe Edition']
        self.assertEqual('Deluxe Edition', compute_edition(descs, self.fc))

    # no match ────────────────────────────────────────────────────────────────

    def test_no_edition_in_descriptions(self):
        self.assertEqual('', compute_edition(['Album', 'Remastered'], self.fc))

    def test_empty_descriptions(self):
        self.assertEqual('', compute_edition([], self.fc))

    def test_none_descriptions(self):
        self.assertEqual('', compute_edition(None, self.fc))

    def test_no_format_codes(self):
        self.assertEqual('', compute_edition(['Deluxe Edition'], {}))

    # first match wins ─────────────────────────────────────────────────────────

    def test_first_matching_description_wins(self):
        # Both match; first in descriptions list returned
        result = compute_edition(['Deluxe Edition', 'Special Edition'], self.fc)
        self.assertEqual('Deluxe Edition', result)


if __name__ == '__main__':
    unittest.main()
