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
    known = (set(config_schema.DEFAULTS) | set(config_schema.REQUIRED)
             | set(config_schema.DEPRECATED))
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


# ── --new-config scaffolding ─────────────────────────────────────────────────

def test_new_config_writes_a_usable_pair(tmp_path):
    from discogstagger.tagger_config import write_new_config

    written, skipped = write_new_config(str(tmp_path))
    names = sorted(os.path.basename(p) for p in written)
    assert names == ["config.yaml", "formats.ini"]
    assert skipped == []

    # Nothing links the two files: formats.ini is found because it sits beside
    # config.yaml under the name the layout expects.
    cfg = TaggerConfig(str(tmp_path / "config.yaml"))
    assert cfg.resource("formats") == str(tmp_path / "formats.ini")
    assert cfg.get("file-formatting", "dir")
    assert cfg.get("common", "formats_file") is None, \
        "the generated config should not need the deprecated key"


def test_new_config_never_clobbers(tmp_path):
    from discogstagger.tagger_config import write_new_config

    write_new_config(str(tmp_path))
    (tmp_path / "config.yaml").write_text("# mine\n", encoding="utf-8")

    written, skipped = write_new_config(str(tmp_path))
    assert written == []
    assert len(skipped) == 2
    assert (tmp_path / "config.yaml").read_text(encoding="utf-8") == "# mine\n"


def test_new_config_force_overwrites(tmp_path):
    from discogstagger.tagger_config import write_new_config

    write_new_config(str(tmp_path))
    (tmp_path / "config.yaml").write_text("# mine\n", encoding="utf-8")

    written, skipped = write_new_config(str(tmp_path), force=True)
    assert len(written) == 2
    assert skipped == []
    assert "# mine" not in (tmp_path / "config.yaml").read_text(encoding="utf-8")


# ── config discovery ─────────────────────────────────────────────────────────

def test_config_dir_honours_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("DISCOGSTAGGER_CONFIG_DIR", str(tmp_path))
    assert roots.config_dir() == str(tmp_path)


def test_config_dir_falls_back_to_xdg(tmp_path, monkeypatch):
    monkeypatch.delenv("DISCOGSTAGGER_CONFIG_DIR", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert roots.config_dir() == os.path.join(str(tmp_path), "discogstagger")


def test_discover_config_finds_only_an_existing_file(tmp_path, monkeypatch):
    monkeypatch.setenv("DISCOGSTAGGER_CONFIG_DIR", str(tmp_path))
    assert roots.discover_config() is None

    from discogstagger.tagger_config import write_new_config
    write_new_config(str(tmp_path))
    assert roots.discover_config() == str(tmp_path / "config.yaml")


def test_formats_is_discovered_not_configured(tmp_path):
    """formats.ini beside config.yaml is picked up with nothing declared."""
    (tmp_path / "config.yaml").write_text("common: {}\n", encoding="utf-8")
    (tmp_path / "formats.ini").write_text(
        "[file-formatting]\ndir = %albumartist%\n", encoding="utf-8")

    cfg = TaggerConfig(str(tmp_path / "config.yaml"))
    assert cfg.get("file-formatting", "dir") == "%albumartist%"


def test_no_formats_file_falls_back_to_bundled(tmp_path):
    (tmp_path / "config.yaml").write_text("common: {}\n", encoding="utf-8")
    cfg = TaggerConfig(str(tmp_path / "config.yaml"))
    assert cfg.resource("formats") is None
    assert cfg.get("file-formatting", "dir"), "bundled format strings apply"


def test_legacy_formats_file_key_still_works_but_warns(tmp_path, caplog):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "custom.ini").write_text(
        "[file-formatting]\ndir = %album%\n", encoding="utf-8")
    (tmp_path / "config.yaml").write_text(
        "common:\n  formats_file: elsewhere/custom.ini\n", encoding="utf-8")

    with caplog.at_level("WARNING"):
        cfg = TaggerConfig(str(tmp_path / "config.yaml"))

    assert cfg.get("file-formatting", "dir") == "%album%"
    assert "deprecated" in caplog.text
    # and it must not also be reported as an unknown key
    assert "Unknown config key" not in caplog.text


# ── watch mode processes an existing backlog ─────────────────────────────────

def test_watch_mode_scans_before_watching():
    """Daemon mode must reconcile current state, not only react to changes.

    Starting against a populated incoming directory used to do nothing: the
    observer fires on modification only, so an existing backlog stayed
    invisible until something touched the directory. The container defaults
    to -w, so a fresh deployment silently tagged nothing.
    """
    import inspect
    from discogstagger import __main__ as dt3_main

    src = inspect.getsource(dt3_main.main)
    watch_at = src.index("if options.watch:")
    observer_at = src.index("observer.start()", watch_at)
    between = src[watch_at:observer_at]

    assert "get_source_dirs()" in between, (
        "watch mode must scan for existing work before starting the observer")
    assert "process_source_dirs(" in between, (
        "watch mode must process what the initial scan found")
