import os, sys
import logging

logging.basicConfig(level=10)
logger = logging.getLogger(__name__)

parentdir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(parentdir)

logger.debug("parentdir: %s" % parentdir)

from discogstagger.tagger_config import TaggerConfig

def test_default_values():

    config = TaggerConfig(os.path.join(parentdir, "test/empty.conf"))

    assert config.getboolean("details", "keep_original")
    assert config.get("details", "case_dir") == "lower"

    assert config.get("file-formatting", "image") == "image"

def test_set_values():

    config = TaggerConfig(os.path.join(parentdir, "test/test_values.conf"))

    assert not config.getboolean("details", "keep_original")

    assert config.get("file-formatting", "image") == "XXIMGXX"

    # not overwritten value should stay at the config.yaml default
    assert config.get("details", "case_dir") == "lower"

def test_id_tag_name():

    config = TaggerConfig(os.path.join(parentdir, "test/emtpy.conf"))

    assert config.id_tag_name == "discogs_id"

    config = TaggerConfig(os.path.join(parentdir, "test/files/discogs_id.txt"))

    assert config.get("source", "name") == "discogs"
    assert config.id_tag_name == "discogs_id"
    assert config.get("source", config.id_tag_name) == "4712"

    config = TaggerConfig(os.path.join(parentdir, "test/files/multiple_id.txt"))

    assert config.get("source", "name") == "amg"
    assert config.id_tag_name == "amg_id"
    assert config.get("source", config.id_tag_name) == "4711"

def test_get():

    config = TaggerConfig(os.path.join(parentdir, "test/emtpy.conf"))

# if the value is emtpy in the config file, it is returned as None
    assert config.get("tags", "encoder") == None

def test_overload_config():

    config = TaggerConfig(os.path.join(parentdir, "test/test_values.conf"))

    assert not config.getboolean("details", "keep_original")
    assert config.get("tags", "encoder") == None

    config.read(os.path.join(parentdir, "test/track_values.conf"))

    assert not config.getboolean("details", "keep_original")
    assert config.get("tags", "encoder") == "myself"

def test_get_character_exceptions():
    # default.conf no longer ships a [character_exceptions] section —
    # substitutions are now defined in conf/char_substitutions.yaml.
    config = TaggerConfig(os.path.join(parentdir, "test/test_values.conf"))
    assert len(config.character_exceptions) == 0

    # track_values.conf adds its own [character_exceptions] section with â=a
    config = TaggerConfig(os.path.join(parentdir, "test/track_values.conf"))
    logger.debug("config: %s" % config.character_exceptions)
    assert len(config.character_exceptions) == 1
    assert config.character_exceptions["â"] == "a"

def test_get_configured_tags():

    config = TaggerConfig(os.path.join(parentdir, "test/test_values.conf"))

    logger.debug("config.configured_tags %s" % config.configured_tags)
    assert len(config.configured_tags) == 3
    assert config.configured_tags["year"] == "1901"
    assert config.configured_tags["title"] == "Title"
    assert config.configured_tags["encoder"] == ""

def test_suppressed_tags_empty_by_default():
    """No [suppress_tags] section → empty set."""
    config = TaggerConfig(os.path.join(parentdir, "test/empty.conf"))
    assert config.suppressed_tags == set()

def test_suppressed_tags_from_config(tmp_path):
    """[suppress_tags] bare keys (no '=') become lowercase tag names in the set."""
    conf_path = tmp_path / "test_suppress.conf"
    conf_path.write_text(
        "[suppress_tags]\n"
        "genres\n"       # bare key — no '=' needed
        "country\n"
        "LABEL\n",       # keys are lowercased
        encoding="utf-8",
    )
    config = TaggerConfig(str(conf_path))
    assert config.suppressed_tags == {'genres', 'country', 'label'}

def test_suppressed_tags_with_equals_also_works(tmp_path):
    """key = value syntax is still accepted for compatibility."""
    conf_path = tmp_path / "sup_eq.conf"
    conf_path.write_text("[suppress_tags]\ngenres =\ncountry = yes\n", encoding="utf-8")
    config = TaggerConfig(str(conf_path))
    assert config.suppressed_tags == {'genres', 'country'}

def test_suppressed_tags_case_insensitive(tmp_path):
    conf_path = tmp_path / "sup.conf"
    conf_path.write_text("[suppress_tags]\nGrouping\n", encoding="utf-8")
    config = TaggerConfig(str(conf_path))
    assert 'grouping' in config.suppressed_tags