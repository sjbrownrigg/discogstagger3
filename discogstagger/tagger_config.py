import os
import logging

from configparser import RawConfigParser

logger = logging.getLogger(__name__)

# Paths relative to this file's directory
_HERE = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_CONF    = os.path.join(_HERE, "..", "conf", "default.conf")
_DEFAULT_YAML    = os.path.join(_HERE, "..", "conf", "config.yaml")
_DEFAULT_FORMATS = os.path.join(_HERE, "..", "conf", "formats.ini")


class TaggerConfig(RawConfigParser):
    """Configuration for discogstagger3.

    Accepts both YAML (.yaml / .yml) and legacy INI (.conf / .ini) config
    files.  The loading order is:

      1. conf/config.yaml    — YAML defaults  (operational settings)
      2. conf/formats.ini    — INI defaults   (file naming format strings)
      3. conf/default.conf   — legacy INI fallback (for backward compat)
      4. User config file    — YAML or INI overrides
      5. Formats INI file    — path from common.formats_file in the user
                               YAML; falls back to auto-named companion
                               (<basename>_formats.ini) for backward compat

    All existing callers use TaggerConfig.get(section, key) which works
    identically regardless of whether values came from YAML or INI.
    """

    # Preserve option key case so character_exceptions like 'Ö', 'Ä', 'Ü'
    # are stored distinctly from their lowercase equivalents.
    optionxform = str

    def __init__(self, config_file):
        # allow_no_value=True: suppress_tags entries can be bare keys
        # without a trailing '=', e.g. just "genres" instead of "genres ="
        RawConfigParser.__init__(self, strict=False, allow_no_value=True)

        # 1 + 2: YAML defaults then format strings defaults
        self._load_yaml(_DEFAULT_YAML)
        self.read(_DEFAULT_FORMATS)

        # 3: Legacy INI fallback — values already in YAML take precedence
        #    because RawConfigParser.read() only sets keys not yet present
        #    … except it doesn't work that way; later reads overwrite.
        #    We load default.conf BEFORE the YAML so YAML wins.
        # Re-load order: default.conf first, then YAML overrides, then formats
        # Re-start to get the correct precedence:
        RawConfigParser.__init__(self, strict=False, allow_no_value=True)
        self.read(_DEFAULT_CONF)       # 3: legacy INI (lowest precedence)
        self._load_yaml(_DEFAULT_YAML) # 1: YAML defaults (overrides INI)
        self.read(_DEFAULT_FORMATS)    # 2: format strings (additive)

        # 4: User config
        if config_file:
            if _is_yaml(config_file):
                self._load_yaml(config_file)
                # 5: formats file — explicit path from common.formats_file,
                #    or auto-named companion for backward compatibility
                formats_file = self._resolve_formats_file(config_file)
                if formats_file:
                    logger.debug('Loading formats file: %s', formats_file)
                    self.read(formats_file)
            else:
                self.read(config_file)

    # ------------------------------------------------------------------

    def _resolve_formats_file(self, yaml_path: str) -> str | None:
        """Return the formats INI path to load after the user YAML.

        If common.formats_file is set and the file is missing, raises
        FileNotFoundError — a missing explicit reference is always an error.

        Falls back to the auto-named companion (<basename>_formats.ini) for
        backward compatibility with configs that predate this key; the
        companion is optional and silently skipped when absent.
        """
        try:
            explicit = self.get('common', 'formats_file')
        except Exception:
            explicit = None
        if explicit:
            if not os.path.exists(explicit):
                raise FileNotFoundError(
                    f"formats_file not found: {explicit!r}\n"
                    f"  Set in common.formats_file — check the path is "
                    f"correct relative to your working directory."
                )
            return explicit
        companion = _companion_formats(yaml_path)
        return companion if os.path.exists(companion) else None

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


def _companion_formats(yaml_path: str) -> str:
    """Return the expected companion formats INI path for a YAML config file.

    myconfig.yaml  →  myconfig_formats.ini
    """
    base = os.path.splitext(yaml_path)[0]
    return base + '_formats.ini'
