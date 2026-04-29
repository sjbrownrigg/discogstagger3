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
    assert not config.getboolean("details", "use_style")
    assert config.getboolean("details", "use_lower_filenames")

    assert config.get("file-formatting", "image") == "image"

def test_set_values():

    config = TaggerConfig(os.path.join(parentdir, "test/test_values.conf"))

    assert not config.getboolean("details", "keep_original")
    assert config.getboolean("details", "use_style")

    assert config.get("file-formatting", "image") == "XXIMGXX"

    # not overwritten value should stay the same
    assert config.getboolean("details", "use_lower_filenames")

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

def test_get_without_quotation():

    config = TaggerConfig(os.path.join(parentdir, "test/emtpy.conf"))

# if the value in the config file contains quotation marks, remove those
    assert config.get_without_quotation("details", "join_genres_and_styles") == " & "

def test_get():

    config = TaggerConfig(os.path.join(parentdir, "test/emtpy.conf"))

# if the value is emtpy in the config file, it is returned as None
    assert config.get("tags", "encoder") == None

def test_overload_config():

    config = TaggerConfig(os.path.join(parentdir, "test/test_values.conf"))

    assert config.getboolean("details", "use_style")
    assert config.get("tags", "encoder") == None

    config.read(os.path.join(parentdir, "test/track_values.conf"))

    assert config.getboolean("details", "use_style")
    assert config.get("tags", "encoder") == "myself"

def test_get_character_exceptions():

    config = TaggerConfig(os.path.join(parentdir, "test/test_values.conf"))

    assert len(config.character_exceptions) == 10
    assert config.character_exceptions[" "] == "_"
    assert config.character_exceptions["ö"] == "oe"


    config = TaggerConfig(os.path.join(parentdir, "test/track_values.conf"))

    logger.debug("config: %s" % config.character_exceptions)

    assert len(config.character_exceptions) == 11
    assert config.character_exceptions["â"] == "a"

def test_get_configured_tags():

    config = TaggerConfig(os.path.join(parentdir, "test/test_values.conf"))

    logger.debug("config.configured_tags %s" % config.configured_tags)
    assert len(config.configured_tags) == 3
    assert config.configured_tags["year"] == "1901"
    assert config.configured_tags["title"] == "Title"
    assert config.configured_tags["encoder"] == ""