# -*- coding: utf-8 -*-
"""The schema is the source of truth; the sample is documentation of it.

conf/config_sample.yaml is no longer loaded at runtime, so nothing would
otherwise notice it drifting away from config_schema.DEFAULTS. These tests
notice.
"""

import os
import sys

import pytest
import yaml

parentdir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parentdir)

from discogstagger import config_schema, roots
from discogstagger.config_schema import ConfigError
from discogstagger.tagger_config import TaggerConfig


SAMPLE = os.path.join(roots.BUNDLED_CONF, "config_sample.yaml")


def _sample_pairs():
    """Flatten the sample the same way TaggerConfig._load_yaml does."""
    with open(SAMPLE, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    pairs = {}
    for section, values in data.items():
        if not isinstance(values, dict):
            continue  # suppress_tags is a list of bare keys, not settings
        for key, val in values.items():
            pairs[(section, key)] = "" if val is None else str(val)
    return pairs


# ── sample and schema agree ──────────────────────────────────────────────────

def test_sample_documents_every_schema_key():
    documented = set(_sample_pairs())
    known = set(config_schema.DEFAULTS) | set(config_schema.REQUIRED)
    undocumented = known - documented
    assert not undocumented, (
        "these keys exist in config_schema but not in config_sample.yaml: "
        f"{sorted(undocumented)}")


def test_schema_knows_every_sample_key():
    documented = set(_sample_pairs())
    known = set(config_schema.DEFAULTS) | set(config_schema.REQUIRED)
    unknown = documented - known
    assert not unknown, (
        "config_sample.yaml documents keys the schema does not know, so they "
        f"would be reported as typos: {sorted(unknown)}")


def test_sample_values_match_schema_defaults():
    sample = _sample_pairs()
    mismatched = {
        key: (sample[key], default)
        for key, default in config_schema.DEFAULTS.items()
        if key in sample and sample[key] != default
    }
    assert not mismatched, (
        "config_sample.yaml shows a different value than the schema applies "
        f"(key: sample vs schema): {mismatched}")


# ── a missing config is an error, not a fallback ─────────────────────────────

def test_nonexistent_config_path_raises():
    """The old behaviour silently loaded the bundled sample instead.

    test/emtpy.conf -- a real typo that lived in this suite -- passed for
    exactly that reason.
    """
    with pytest.raises(FileNotFoundError) as exc:
        TaggerConfig(os.path.join(parentdir, "test/definitely-not-here.conf"))
    assert "definitely-not-here.conf" in str(exc.value)


def test_no_config_at_all_raises():
    with pytest.raises(ConfigError) as exc:
        TaggerConfig(None)
    assert "-c" in str(exc.value)


# ── defaults come from the table ─────────────────────────────────────────────

def test_defaults_applied_to_an_empty_config():
    cfg = TaggerConfig(os.path.join(parentdir, "test/empty.conf"))
    assert cfg.get("details", "char_profile") == "linux"
    assert cfg.get("details", "done_file") == "dt.done"
    assert cfg.get("common", "user_agent")


def test_user_value_beats_the_default(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("details:\n  char_profile: windows\n", encoding="utf-8")
    cfg = TaggerConfig(str(cfg_file))
    assert cfg.get("details", "char_profile") == "windows"
    # untouched keys still take the schema default
    assert cfg.get("details", "done_file") == "dt.done"


def test_unknown_key_warns_but_does_not_fail(tmp_path, caplog):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("details:\n  char_profle: windows\n", encoding="utf-8")
    with caplog.at_level("WARNING"):
        TaggerConfig(str(cfg_file))
    assert "char_profle" in caplog.text
