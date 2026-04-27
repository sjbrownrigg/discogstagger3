import os
import logging
import functools

from configparser import RawConfigParser

logger = logging.getLogger(__name__)

# Directory containing this file — used to locate default.conf reliably
# regardless of the working directory when the script is invoked.
_HERE = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_CONF = os.path.join(_HERE, "..", "conf", "default.conf")


def memoized_property(func):
    """Simple memoizing property decorator using functools.cached_property style.

    Replaces the hand-rolled class-based version, which had a subtle mutation
    bug: it stored the cached value in obj.__dict__ but also mutated
    self._sections in place (via del exceptions["__name__"]), meaning the
    section data was corrupted after the first call. Using functools.lru_cache
    on a regular method, or just caching explicitly, avoids this entirely.
    """
    attr = "_cached_" + func.__name__

    @property
    @functools.wraps(func)
    def wrapper(self):
        if not hasattr(self, attr):
            object.__setattr__(self, attr, func(self))
        return getattr(self, attr)

    return wrapper


class TaggerConfig(RawConfigParser):
    """Provides the configuration mechanisms for the discogstagger."""

    def __init__(self, config_file):
        RawConfigParser.__init__(self, strict=False)
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
        config_value = RawConfigParser.get(self, section, name, raw=True)

        if config_value == "":
            config_value = None
        else:
            config_value = config_value.strip()

        return config_value

    def items(self, section, **kw):
        return RawConfigParser.items(self, section, raw=True)

    @memoized_property
    def get_character_exceptions(self):
        """Return character replacement map from the [character_exceptions] config section.

        Makes a copy of the section data to avoid mutating the live parser
        state, which was a bug in the original implementation.
        """
        if "character_exceptions" not in self._sections:
            return {}

        # Copy so we don't mutate the parser's internal state
        exceptions = dict(self._sections["character_exceptions"])

        exceptions.pop("__name__", None)

        # Expand placeholder key names to their actual characters
        KEY_MAP = {
            "{space}": " ",
        }
        for placeholder, actual in KEY_MAP.items():
            if placeholder in exceptions:
                exceptions[actual] = exceptions.pop(placeholder)

        return exceptions

    @memoized_property
    def get_configured_tags(self):
        """Return all tags explicitly set in the [tags] config section.

        These can be used to override certain metadata tags via a
        configuration file (e.g. id.txt).
        """
        if "tags" not in self._sections:
            return {}

        # Copy so we don't mutate the parser's internal state
        tags = dict(self._sections["tags"])
        tags.pop("__name__", None)

        return tags