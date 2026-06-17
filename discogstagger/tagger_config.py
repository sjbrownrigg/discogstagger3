import os
import logging

from configparser import RawConfigParser

logger = logging.getLogger(__name__)

_HERE = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_YAML    = os.path.join(_HERE, "conf", "config_sample.yaml")
_DEFAULT_FORMATS = os.path.join(_HERE, "conf", "formats_sample.ini")


class TaggerConfig(RawConfigParser):
    """Configuration for discogstagger3.

    Loading order:

      1. conf/config_sample.yaml  — baseline defaults (required)
      2. conf/formats_sample.ini  — baseline format strings (required)
      3. User config file         — YAML or INI overrides (optional, via -c)
      4. Formats INI file  — path from common.formats_file in the user YAML
                             (required when the key is set)

    Both baseline files must exist; a missing file raises FileNotFoundError
    immediately rather than silently falling back to built-in defaults.
    """

    # Preserve option key case so character_exceptions like 'Ö', 'Ä', 'Ü'
    # are stored distinctly from their lowercase equivalents.
    optionxform = str

    def __init__(self, config_file=None):
        # allow_no_value=True: suppress_tags entries can be bare keys
        # without a trailing '=', e.g. just "genres" instead of "genres ="
        RawConfigParser.__init__(self, strict=False, allow_no_value=True)

        # 1: Baseline operational settings.
        #
        # When discogstagger3 is installed as a library (e.g. as a dependency
        # of massMusicTagger), the built-in conf/ directory may not be present
        # in site-packages.  In that case, if a config_file is provided, skip
        # the bundled baseline and use config_file as the primary source.  This
        # lets callers supply a complete config without requiring the bundled
        # conf/ to be present on disk.
        #
        # If neither the default nor a config_file exists, raise promptly.
        if os.path.exists(_DEFAULT_YAML):
            self._load_yaml(_DEFAULT_YAML)
            have_default = True
        elif config_file and _is_yaml(config_file) and os.path.exists(config_file):
            # Caller's YAML becomes the baseline; skip bundled default.
            logger.debug('Bundled conf/config.yaml not found; using %s as primary config',
                         config_file)
            have_default = False
        else:
            raise FileNotFoundError(
                f"Required config not found: {_DEFAULT_YAML!r}\n"
                f"  The discogstagger3 installation appears incomplete.\n"
                f"  Alternatively, pass a complete YAML config file as config_file."
            )

        # 2: Baseline format strings (only when bundled baseline was loaded).
        if have_default:
            if not os.path.exists(_DEFAULT_FORMATS):
                raise FileNotFoundError(
                    f"Required formats not found: {_DEFAULT_FORMATS!r}\n"
                    f"  The discogstagger3 installation appears incomplete."
                )
            self.read(_DEFAULT_FORMATS)

        # 3: User config
        if config_file:
            if _is_yaml(config_file):
                self._load_yaml(config_file)
                # 4: formats file — explicit path from common.formats_file
                formats_file = self._resolve_formats_file(config_file)
                if formats_file:
                    logger.debug('Loading formats file: %s', formats_file)
                    self.read(formats_file)
            else:
                self.read(config_file)

    # ------------------------------------------------------------------

    def _resolve_formats_file(self, yaml_path: str) -> str | None:
        """Return the formats INI path to load after the user YAML.

        Reads common.formats_file from the loaded config.  Returns None when
        the key is absent or empty.  Raises FileNotFoundError if the key is
        set but the file does not exist.
        """
        try:
            explicit = self.get('common', 'formats_file')
        except Exception:
            explicit = None
        if not explicit:
            return None
        if not os.path.exists(explicit):
            raise FileNotFoundError(
                f"formats_file not found: {explicit!r}\n"
                f"  Set in common.formats_file — check the path is "
                f"correct relative to your working directory."
            )
        return explicit

    # ------------------------------------------------------------------

    def _load_yaml(self, yaml_path: str):
        """Load a YAML config file and inject its values into the parser.

        Each top-level YAML key becomes a section name.  Dict values become
        key=value pairs in that section.  List values (e.g. suppress_tags)
        become bare keys (allow_no_value).  Scalar top-level values are
        ignored (they have no INI equivalent).
        """
        if not yaml_path or not os.path.exists(yaml_path):
            return
        try:
            import yaml
        except ImportError:
            logger.warning(
                'pyyaml is not installed — YAML config files cannot be loaded. '
                'Run: pip install pyyaml'
            )
            return
        try:
            with open(yaml_path, encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
        except Exception as e:
            logger.warning('Failed to load YAML config %s: %s', yaml_path, e)
            return

        for section, values in data.items():
            if not isinstance(values, (dict, list)):
                continue  # skip scalar top-level keys
            if not self.has_section(section):
                self.add_section(section)
            if isinstance(values, list):
                # suppress_tags: [genres, country, …]
                for item in values:
                    item_str = str(item).strip()
                    if item_str:
                        self.set(section, item_str, None)
            else:
                for key, val in values.items():
                    if val is None:
                        self.set(section, str(key), None)
                    else:
                        self.set(section, str(key), str(val))

    # ------------------------------------------------------------------

    @property
    def id_tag_name(self):
        source_name = self.get("source", "name")
        return self.get("source", source_name)

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
        """Character replacement map from [character_exceptions] section."""
        if "character_exceptions" not in self._sections:
            return {}
        exceptions = dict(self._sections["character_exceptions"])
        exceptions.pop("__name__", None)
        if "{space}" in exceptions:
            exceptions[" "] = exceptions.pop("{space}")
        return exceptions

    @property
    def configured_tags(self):
        """Tags explicitly set in the [tags] section."""
        if "tags" not in self._sections:
            return {}
        tags = dict(self._sections["tags"])
        tags.pop("__name__", None)
        return tags

    @property
    def suppressed_tags(self) -> set:
        """Set of MediaFile attribute names to suppress from file metadata.

        Keys listed under [suppress_tags] (bare keys, no value needed) are
        not written to file metadata during tagging.  The Discogs data for
        those fields is still available to format strings for naming.
        """
        if "suppress_tags" not in self._sections:
            return set()
        tags = dict(self._sections["suppress_tags"])
        tags.pop("__name__", None)
        return {k.strip().lower() for k in tags}


# -- Module helpers -----------------------------------------------------------

def _is_yaml(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in ('.yaml', '.yml')
