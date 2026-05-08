import os
import logging

from configparser import RawConfigParser

logger = logging.getLogger(__name__)

# Directory containing this file — used to locate default.conf reliably
# regardless of the working directory when the script is invoked.
_HERE = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_CONF = os.path.join(_HERE, "..", "conf", "default.conf")


class TaggerConfig(RawConfigParser):
    """Provides the configuration mechanisms for the discogstagger."""

    # Preserve option key case so character_exceptions like 'Ö', 'Ä', 'Ü'
    # are stored distinctly from their lowercase equivalents.
    optionxform = str

    def __init__(self, config_file):
        # allow_no_value=True lets [suppress_tags] entries be written as bare
        # keys without a trailing '=', e.g. just "genres" instead of "genres ="
        RawConfigParser.__init__(self, strict=False, allow_no_value=True)
        self.read(_DEFAULT_CONF)
        self.read(config_file)

    @property
    def id_tag_name(self):
        source_name = self.get("source", "name")
        id_tag_name = self.get("source", source_name)
        return id_tag_name

    def get_without_quotation(self, section, name):
        config_value = self.get(section, name)
        return config_value.replace("\"", "")

    def get(self, section, name, **kw):
        config_value = RawConfigParser.get(self, section, name.lower(), raw=True)

        if config_value is None or config_value == "":
            config_value = None
        else:
            config_value = config_value.strip()

        return config_value

    def items(self, section, **kw):
        return RawConfigParser.items(self, section, raw=True)

    @property
    def character_exceptions(self):
        """Return character replacement map from the [character_exceptions] config section."""
        if "character_exceptions" not in self._sections:
            return {}

        exceptions = dict(self._sections["character_exceptions"])
        exceptions.pop("__name__", None)

        if "{space}" in exceptions:
            exceptions[" "] = exceptions.pop("{space}")

        return exceptions

    @property
    def configured_tags(self):
        """Return all tags explicitly set in the [tags] config section."""
        if "tags" not in self._sections:
            return {}

        tags = dict(self._sections["tags"])
        tags.pop("__name__", None)
        return tags

    @property
    def suppressed_tags(self) -> set:
        """Return the set of MediaFile attribute names to suppress from file metadata.

        Keys listed under [suppress_tags] in the config file are not written
        to file metadata during tagging.  The Discogs data for those fields is
        still available to format strings for directory/file naming.
        """
        if "suppress_tags" not in self._sections:
            return set()
        tags = dict(self._sections["suppress_tags"])
        tags.pop("__name__", None)
        return {k.strip().lower() for k in tags}
