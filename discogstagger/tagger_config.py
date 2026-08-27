import os
import logging

from configparser import RawConfigParser, NoSectionError, NoOptionError

from discogstagger import roots

logger = logging.getLogger(__name__)

_DEFAULT_YAML    = os.path.join(roots.BUNDLED_CONF, "config_sample.yaml")
_DEFAULT_FORMATS = os.path.join(roots.BUNDLED_CONF, "formats_sample.ini")


class TaggerConfig(RawConfigParser):
    """Configuration for discogstagger3.

    Each config file is expected to be complete — settings are never silently
    filled in from a baseline layer.  Callers should copy config_sample.yaml to
    config.yaml and edit that copy.

    Loading when a config_file is provided:
      1. config_file (YAML or INI) — loaded as the sole source.
      2. formats_file from common.formats_file (if set in the YAML).

    Loading when no config_file is provided (absolute fallback only):
      1. conf/config_sample.yaml  — bundled sample (required)
      2. conf/formats_sample.ini  — bundled format strings (required)
    """

    # Preserve option key case so character_exceptions like 'Ö', 'Ä', 'Ü'
    # are stored distinctly from their lowercase equivalents.
    optionxform = str

    def __init__(self, config_file=None):
        # allow_no_value=True: suppress_tags entries can be bare keys
        # without a trailing '=', e.g. just "genres" instead of "genres ="
        RawConfigParser.__init__(self, strict=False, allow_no_value=True)

        # Base for paths this config file names (formats_file, templates_dir).
        # None when running off the bundled sample, in which case such paths
        # fall back to the working directory as they always did.
        self.config_root = roots.config_root(config_file) if config_file else None

        if config_file and os.path.exists(config_file):
            if _is_yaml(config_file):
                # YAML config is expected to be complete — load it as the sole source.
                self._load_yaml(config_file)
                formats_file = self._resolve_formats_file(config_file)
                if formats_file:
                    logger.debug('Loading formats file: %s', formats_file)
                    self.read(formats_file)
            else:
                # INI config (e.g. legacy or test usage) — load the YAML baseline
                # first so the INI acts as a targeted override, not a complete config.
                if os.path.exists(_DEFAULT_YAML):
                    self._load_yaml(_DEFAULT_YAML)
                if os.path.exists(_DEFAULT_FORMATS):
                    self.read(_DEFAULT_FORMATS)
                self.read(config_file)
        else:
            # No user config provided — fall back to the bundled sample.
            if not os.path.exists(_DEFAULT_YAML):
                raise FileNotFoundError(
                    f"No config file provided and bundled sample not found: {_DEFAULT_YAML!r}\n"
                    f"  Pass a complete YAML config via -c <config.yaml>."
                )
            self._load_yaml(_DEFAULT_YAML)
            if not os.path.exists(_DEFAULT_FORMATS):
                raise FileNotFoundError(
                    f"Bundled formats not found: {_DEFAULT_FORMATS!r}\n"
                    f"  The discogstagger3 installation appears incomplete."
                )
            self.read(_DEFAULT_FORMATS)

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

        resolved = self.resolve_path(explicit, 'common.formats_file')
        if not os.path.exists(resolved):
            raise FileNotFoundError(
                f"formats_file not found: {resolved!r}\n"
                f"  Set in common.formats_file as {explicit!r}. Paths are "
                f"resolved relative to the config file's own directory, so "
                f"place the file beside the config or use an absolute path."
            )
        return resolved

    def resolve_path(self, value, key_name="path"):
        """Resolve a path read from this config file to an absolute path.

        Relative values resolve against the directory holding the config file,
        so a config and the files it names travel together. See
        discogstagger.roots for the full rationale.
        """
        return roots.resolve_config_path(value, self.config_root, key_name)

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
        try:
            config_value = RawConfigParser.get(self, section, name.lower(), raw=True)
        except (NoSectionError, NoOptionError):
            return None
        if config_value is None or config_value == "":
            return None
        return config_value.strip()

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


def extract_sample_section(section: str, sample_path: str | None = None) -> str:
    """Return the raw text block for a top-level YAML section from the sample config.

    Includes comment lines so callers can print useful context in error messages
    when a required setting is absent.  Returns empty string if the section is
    not found or the file cannot be read.
    """
    import re
    path = sample_path or _DEFAULT_YAML
    if not os.path.exists(path):
        return ''
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            lines = fh.readlines()
    except OSError:
        return ''
    section_re = re.compile(r'^' + re.escape(section) + r'\s*:')
    toplevel_re = re.compile(r'^[a-z_][a-z_0-9]*\s*:')
    collecting = False
    result: list[str] = []
    for line in lines:
        if not collecting:
            if section_re.match(line):
                collecting = True
                result.append(line)
        else:
            if toplevel_re.match(line) and not section_re.match(line):
                break
            result.append(line)
            if len(result) >= 60:
                result.append('  ...\n')
                break
    return ''.join(result).rstrip()
