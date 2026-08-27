## Changelog

---

## Version 4.0.0 (2026-08-27)

Configuration is now a **directory** that discogstagger3 finds for itself,
holding only files the user owns. Defaults moved out of a sample file and into
code. Paths no longer resolve against the current working directory.

### Breaking changes

**`-c` / `--conf` is gone.** It named a single file, but a configuration is
`config.yaml` and `formats.ini` resolving relative to each other — it moves as a
unit, so the directory is what gets selected:

```bash
DISCOGSTAGGER_CONFIG_DIR=~/configs/vinyl discogstagger
```

The directory is found via `DISCOGSTAGGER_CONFIG_DIR`, else
`$XDG_CONFIG_HOME/discogstagger`, else `~/.config/discogstagger`.

**A missing config is an error.** Previously a config path that did not exist
fell back to loading the bundled sample, so a typo ran the tagger against
settings the user had never seen. Running with no configuration at all now
refuses rather than guessing — this tool renames and moves files.

**`common.templates_dir` removed.** Mako templates belong to discogstagger3 and
always come from the package.

**`common.formats_file` deprecated.** `formats.ini` is found beside
`config.yaml` by name. The key still works and warns.

### New

- **`--new-config [DIR]`** writes a fresh `config.yaml` and `formats.ini`,
  defaulting to the configuration directory. It never overwrites; use
  `--force-new-config` to override, which discards credentials and format
  strings.
- **`DISCOGSTAGGER_STATE_DIR`** sets where mutable runtime state goes — the
  OAuth `.token` and the API cache. Defaults to `$XDG_STATE_HOME/discogstagger`.
- **`--version`** now reports the installed version instead of a hardcoded
  string that had been stuck at `3.0`.

### The three roots

`discogstagger/roots.py` names the roots the program resolves against, which
were previously conflated and all defaulting to the working directory:

| Root | Holds | Resolved by |
|---|---|---|
| Package | Bundled defaults, templates, rule tables | `__file__` |
| Config | `config.yaml`, `formats.ini` | `DISCOGSTAGGER_CONFIG_DIR`, else XDG |
| State | OAuth `.token`, API cache | `DISCOGSTAGGER_STATE_DIR`, else XDG |

The music library itself is not a root — it is supplied by the user via
`source_dir`/`dest_dir` or `-s`/`-d`.

Paths a config file names resolve against **that config file's directory**, so a
configuration and its files travel together and one config works unchanged on a
laptop or mounted into a container. Resolution falls back to the working
directory with a deprecation warning naming both paths tried, so existing setups
keep working.

`os.getcwd()` no longer appears anywhere outside that one documented fallback.

### Defaults live in code

`conf/config_sample.yaml` used to be loaded as a silent baseline underneath the
user's own config, so a setting could take effect without appearing anywhere in
the file the user was reading.

Every key and its default now lives in one table,
`discogstagger/config_schema.py`. The sample is documentation of that table and
is never loaded at runtime; `test_config_schema.py` checks the two cannot drift
apart. Unknown keys are reported rather than ignored, so typos surface.

### What the config directory holds

Only what the user owns:

```
config.yaml    your settings
formats.ini    your file and directory naming (optional)
```

Mako templates and the rule tables (`format_codes.yaml`,
`char_substitutions.yaml`) ship inside the package and are not copied into a
config directory, so they keep improving with each upgrade instead of freezing
at whatever version was installed on setup day.
`details.format_codes` and `details.char_substitutions` remain as explicit
escape hatches.

### Fixes

- **`.nfo` and `.m3u` were never generated outside a source checkout.**
  `TemplateLookup(directories=["templates"])` was relative to the working
  directory, and `package-data` declared `templates/*` for a directory that did
  not exist — so the templates were not in the wheel at all. Templates moved
  into the package and now resolve via `__file__`.
- **The OAuth `.token` was written to the working directory.** It now goes to
  the state root. An existing `.token` in the working directory is still read,
  with a warning, so nobody is forced to re-authenticate.
- **`pip install` put `test`, `conf`, `docs`, `scripts` and `templates` on the
  import path.** `[tool.setuptools.packages.find]` defaults to
  `namespaces = true` in `pyproject.toml`, so unbounded discovery matched
  directories with no `__init__.py`. Now bounded to `discogstagger*`.
- **`build/lib/build/lib/…` nesting.** Same cause: discovery matched
  `build/lib/discogstagger`, so each build copied the previous one back in a
  level deeper.
- **`test/emtpy.conf`** — a typo referenced by two tests, which passed only
  because a missing config silently loaded bundled defaults. Both fixed.

### Upgrading

```bash
discogstagger --new-config          # creates ~/.config/discogstagger
```

Then copy your settings across from your old config file. If you would rather
keep your existing directory, point `DISCOGSTAGGER_CONFIG_DIR` at it and remove
`common.formats_file` once `formats.ini` sits beside `config.yaml`.

---

## Version 3.1.0 (2026-05-21)

### Format code overhaul

`%format_code%` now encodes only **physical medium and quantity**.  Release-type
suffixes (S, M, EP) and edition prefixes (L, #) have been removed; they are
available via separate variables so they can be placed anywhere in a format
string independently of the format code.

| Before | After | Now via |
|---|---|---|
| `CDS` | `CD` | `%releasetype%` = `Single` |
| `LCDS` | `CD` | `%edition%` = `Limited Edition` |
| `7″S` | `7″` | `%releasetype%` = `Single` |
| `LDCD` | `DCD` | `%edition%` = `Limited Edition` |
| `file` | `DM` | — (Digital Media, unified across File/Web/Digital Media) |

#### New and updated format string variables

| Variable | Description |
|---|---|
| `%format_base%` | Physical medium without quantity prefix (`CD`, `LP`, `12″`, `DM`) |
| `%releasetype%` | MB-style primary release type inferred from Discogs format descriptions (`Album`, `Single`, `EP`, `Compilation`, `Live`, …) |
| `%digital%` | `'1'` for digital formats (File, Web, Digital Media), `''` for physical |
| `%disctotal%` | Total disc count — canonical name matching the `disctotal` MediaFile attribute; `%totaldiscs%` is now a deprecated alias |
| `%status%` | Release status: `Official`, `Promo`, `Bootleg`, `Pseudo-Release` |

#### Vinyl size rules

The `12"` format code is now conditional on release type:

- **12" album → `LP`** — a new `vinyl_sizes_conditional` section in
  `format_codes.yaml` applies `12″` only when a non-album type (`Single`,
  `Maxi-Single`, `EP`, `Mini-Album`) is present in the descriptions.
  A 12" LP album stays as `LP`.
- **7" and 10"** always show the size regardless of release type.

### Vinyl track position labels

- **Full position preserved** — `disc_and_track_no()` now returns the complete
  position string (`A1`, `B3`, …) as `real_tracknumber` so that `%tracknumber%`
  in format strings produces `A1 Title.flac` rather than `01 Title.flac`.
- **Sides paired onto physical records** — A+B = record 1, C+D = record 2.
  Previously each side was its own disc, doubling `disctotal` for a single LP.
- **Letter-only positions** (`A`, `B`) — single-track-per-side releases where
  the Discogs position is just a side letter now produce `A Title.flac`, not
  `0A Title.flac`.

### `$num()` — pass-through for non-numeric values

`$num(value, places)` no longer zero-pads values that start with a non-digit
character.  Vinyl positions (`A`, `A1`, `B3`) pass through unchanged; bare
track numbers are still zero-padded as before.

### New boolean format functions

Three composable boolean functions eliminate deeply-nested `$if1()` chains:

- **`$any(c1, c2, …)`** — `True` if at least one argument is truthy (boolean OR)
- **`$all(c1, c2, …)`** — `True` if every argument is truthy (boolean AND)
- **`$neg(cond)`** — inverts truthiness (boolean NOT)

All three return `True`/`False` and compose naturally inside `$if1()`:

```
; Show type suffix only for single/EP types — suppress for Album
$if1($neg($strcmp('%releasetype%','Album')),'%releasetype%','')

; Limited Edition AND Numbered — both must be present
$if1($all($inarray('%format_description%','Limited Edition'),
          $inarray('%format_description%','Numbered')),'L#','')

; Single OR Maxi-Single on a 7" or 12" vinyl — suppress suffix (size implies type)
$if1($all($any($strcmp('%format_base%','7″'),$strcmp('%format_base%','12″')),
          $strcmp('%releasetype%','Single')),'','S')
```

### Custom variables (`[custom-variables]`)

- New `[custom-variables]` section in the formats INI file.  Fragments are
  referenced as `%__varname__%` in any format string.
- **Nested references** — a custom variable may reference other custom
  variables (up to 5 expansion passes).
- **Critical quoting rule** documented — variables that expand to `$function()`
  calls must not be wrapped in single quotes when used as function arguments.

### New tags

| Tag | Description | Format |
|---|---|---|
| `barcode` | EAN / UPC barcode | Vorbis `BARCODE`, TXXX `BARCODE` |
| `discogs_release_status` | `Official`, `Promo`, `Bootleg`, … | Vorbis `DISCOGS_RELEASE_STATUS` |
| `releasetype` | MB-style primary release type | Vorbis `RELEASETYPE`, follows MusicBrainz Picard naming |
| `musicbrainz_releaseid` | MusicBrainz release UUID (populated via massMusicTagger) | `MUSICBRAINZ_ALBUMID` |
| `musicbrainz_releasegroupid` | Release-group UUID | `MUSICBRAINZ_RELEASEGROUPID` |
| `musicbrainz_trackid` | Recording UUID per track | `MUSICBRAINZ_TRACKID` |
| `isrc` | ISRC per track | `ISRC` |

### Bug fixes

- **`.done` marker copied to sorted output** — `copy_other_files()` was
  including the done marker when re-tagging with `--force`.  It is now
  excluded from the copy list.
- **`int('')` crash** — an empty year from the API was written to the `year`
  tag as an empty string, which `mediafile` then tried to convert to `int`.
  Year is now skipped when absent.
- **`labels[0]` IndexError** — accessing the first label when the labels list
  is empty now falls back to `''`.
- **Preliminary target directory** — technical properties (`%codec%`,
  `%quality%`, `%samplerate%`, etc.) guarded against `None` in the preliminary
  directory name computation, preventing `None--NNone` in paths.
- **`parseString()` TypeError** — boolean values returned by top-level
  `$any`/`$all`/`$neg` calls are now converted to strings before concatenation.

### License

GPL-3.0-or-later added to `pyproject.toml` and `LICENSE` file.

### Tests

- `test_guidelines_compliance.py`: updated for paired-side disc numbering
  (A+B=1, C+D=2) and full position labels (`'A1'` not `'1'`); added
  letter-only position cases (`A`, `B`).
- `test_formatcodes.py`: updated for `DM` digital code and `12"` album → `LP`
  rule; added `12"` single → `12″` test.
- `test_new_features.py`: new `TestNumFunction` suite covering `$num()`
  zero-padding and non-numeric pass-through.

---

## Version 3.0.3 (2026-05-17)

### Discogs submission-guidelines compliance

Fills the gaps identified in a review of how the tagger maps Discogs release
data against the official submission guidelines.

#### Artist Name Variation (ANV)

* Artist display now uses the ANV — the name as credited on the physical
  release sleeve — when present.  Falls back to the canonical Discogs name when
  no ANV is recorded.  The `"Artist, The"` → `"The Artist"` display
  normalisation is applied to ANVs just as it is to canonical names.

* New `details.use_anv` config key (default: `true`).  Set `false` to always
  use the canonical Discogs database name regardless of sleeve credits.

* Applies to all three name-resolution paths: album-level artists
  (`albumartist` / `albumartists` tags), track-level artists (`artist` /
  `artists` tags), and the combined multi-artist display string.

#### Vinyl and dot-notation track positions

* `disc_and_track_no()` now handles **vinyl side-based positions** (A1, B2,
  C3, …).  Each side letter maps to a disc slot: A=1, B=2, C=3, D=4, …,
  consistent with how `disctotal` counts physical records.

* **Dot-separated positions** (1.1, 2.3) used in classical and some box-set
  releases are now parsed: the number before the dot is the disc number, the
  number after is the track number.

* Hyphenated schemes (CD01-12, 1-02, CD-12, USB-Stick-n) continue to work
  as before.

#### Extra artist credits — composer tag

* Release-level and track-level `extraartists` are now read from the Discogs
  API.  Entries with roles matching "Composed By", "Written-By", "Music By",
  and related variants are mapped to the `composer` tag.  Track-level credits
  take priority over release-level credits.  The ANV of the extra artist is
  preferred when present.

* `composer` is no longer incorrectly set to the album artist.

* New shared utility `parse_extraartists()` in `discogs_utils.py` extracts
  composer and lyricist credits from any Discogs `extraartists` list.

#### Release identifiers — barcode

* `release.data['identifiers']` is now read.  The first entry of type
  `Barcode` is stored on `album.barcode` and written to a new `barcode` tag
  (Vorbis `BARCODE`, MP3 TXXX `BARCODE`, MP4 `BARCODE`, ASF `WM/Barcode`).

#### Release status

* `release.data['status']` (`Official`, `Promo`, `Bootleg`,
  `Pseudo-Release`) is stored on `album.status` and written to a new
  `discogs_release_status` tag.

#### Catalogue number order

* `album.catnumbers.sort()` removed.  `dict.fromkeys` already preserves
  Discogs insertion order, so the primary catalogue number (first listed) is
  now reliably written to the `catalognum` tag.

#### `disctotal` — extended media coverage

* `disctotal` now counts `SACD`, `Blu-ray`, `DVD-Audio`, `Cassette`,
  `Minidisc`, `DAT`, `DCC`, and `Laserdisc` in addition to the existing
  `CD`, `CDr`, `Vinyl`, and `LP`.

### Tests

* New `test/test_guidelines_compliance.py` — 38 tests covering all of the
  above: catno order, ANV (enabled and disabled), vinyl/dot position parsing,
  `parse_extraartists()` role mapping, barcode extraction, release status, and
  extended `disctotal` media types.

---

## Version 3.0.2 (2026-05-11)

### Docker deployment (`docker/`)

* New `docker/` directory containing a complete, self-contained deployment
  stack.  All Docker assets are kept separate from the project source to avoid
  polluting the development tree.

* `docker/Dockerfile` — production image based on `python:3.12-slim`.
  Installs `ffmpeg`, `shntool`, and `flac` OS dependencies, then installs the
  Python package from the repository in editable mode so the built-in
  `conf/` path resolution works correctly at runtime.

* `docker/docker-compose.yml` — single-command launch.  Bind mounts supply
  music and config from the host (NAS shares mounted in the host OS); a local
  named volume persists the Discogs API cache.  `MUSIC_DIR` and `CONFIG_DIR`
  environment variables allow the mount paths to be overridden via a
  `docker/.env` file without editing the compose file.

* `docker/config/` — ready-to-deploy configuration template.  Copy to the
  NAS config share and add Discogs credentials before first launch.  Uses
  absolute container paths (`/music`, `/config`, `/cache`) throughout.

* `docker/README.md` — step-by-step setup guide covering both native Linux
  and WSL2.  Documents the NFS Docker volume plugin limitation on WSL2
  (`Operation not permitted`) and the recommended workaround: mount NFS/CIFS
  shares in the host OS first and use bind mounts in Docker Compose.

* `pypillowfight` dependency removed from `pyproject.toml` — it was never
  used in the codebase.  Replaced with `Pillow>=10.0`, which is the imaging
  library actually used for cover art dimension comparison.

### Configuration

* `common.source_dir` and `common.dest_dir` — default source and destination
  directories configurable in YAML; `-s` and `-d` flags override when provided.
* `common.watch_poll_interval` — polling interval in seconds for daemon mode
  (default: 30).  Longer values reduce NFS/CIFS mount overhead.

### Daemon mode (`-w`)

* **Fixed:** replaced `watchdog.observers.Observer` (inotify-based, broken on
  CIFS/NFS) with `PollingObserver`.  Daemon mode now works on any mounted
  filesystem.
* **Fixed:** the main event loop exited immediately after one second.
* New `docs/daemon_mode.md` covering CIFS/NFS setup and Docker deployment.

---

## Version 3.0.1 (2026-05-10)

### Configuration

* `common.source_dir` — default source directory; overrides the `-s` flag
  when set.  Supports `~` expansion.  `-s` still overrides when provided.
* `common.dest_dir` — default destination directory; same override semantics
  as `source_dir` with `-d`.
* `common.watch_poll_interval` — polling interval in seconds for daemon mode
  (default: 30).

### Daemon mode (`-w`)

* **Fixed:** replaced `watchdog.observers.Observer` (uses inotify, which is
  not supported on CIFS or NFS mounts) with `PollingObserver`.  Daemon mode
  now works on any mounted filesystem including CIFS/SMB, NFS, and Docker
  bind mounts without any additional configuration.
* **Fixed:** the main event loop exited after one second due to a bare
  `time.sleep(1)` — replaced with `while True: time.sleep(1)`.
* Two leftover `print()` debug statements converted to `logger.debug()`.
* New `docs/daemon_mode.md` — covers CIFS/NFS mount options, Docker
  deployment (`Dockerfile` + `docker-compose.yml`), and troubleshooting.

### Multi-disc flat layout

* **Fixed:** multi-disc releases where all files are in a single directory
  (no per-disc subdirectories) now tag correctly.  Previously each disc
  scanned the root directory independently, found all N files every time, and
  raised a track count mismatch error.  The fix detects this flat layout,
  verifies the total file count equals the total Discogs track count, and
  distributes the sorted file list across discs in order.

* **Fixed:** `AttributeError: 'Disc' object has no attribute 'sourcedir'`
  during `copy_files()`.  `Disc.__init__` now declares `sourcedir`,
  `target_dir`, and `copy_files` with safe defaults; previously they were
  only set dynamically and any code path that read them before assignment
  raised `AttributeError`.

### CUE file processing

* **Fixed — single-track CUE:** `shntool split` raises "no split points
  given" when a CUE file contains exactly one track.  The fix detects this
  case and bypasses splitting: FLAC sources are copied directly; any other
  format (APE, WAV, etc.) is converted to FLAC via `ffmpeg`.

* **Fixed — non-FLAC/WAV multi-track CUE:** `shntool split` requires
  format-specific external decoders (`monkeys-audio`, `wavpack`) which are
  not available in standard Debian/Ubuntu repositories.  Non-FLAC/WAV sources
  are now decoded to a temporary WAV by `ffmpeg` (already a hard dependency)
  before being passed to `shntool`.  The temporary file is removed after
  splitting.  No additional OS packages are required for APE or WavPack
  sources.

* **Fixed — missing image file guard:** if the audio image referenced by a
  CUE FILE directive cannot be located, `_splitCueFile` now logs a clear
  error and returns rather than passing the string `'None'` as a file path
  (which previously produced a cryptic ffmpeg "No such file or directory"
  error).

* **Improved — `locate_image()` fallback matching:** when the exact filename
  from the CUE FILE directive does not exist on disk, three strategies are
  tried in order:
  1. Exact stem prefix match (handles stale extensions after format
     conversion).
  2. ASCII-only stem comparison — tolerates encoding mismatches between the
     CUE text and the filesystem, e.g. `ú` (Windows-1252, 0xFA) vs `ъ`
     (Windows-1251, 0xFA) on a CIFS mount where the same byte is interpreted
     under different code pages.
  3. Single-file fallback — if exactly one audio file exists in the directory
     it is used (the caller already verified CUE count equals audio file
     count).

* **New — `repair_image_filename()`:** when the audio image is found via a
  fallback strategy, the on-disk file is renamed to match the filename in the
  CUE FILE directive before splitting.  This restores consistency between the
  CUE sheet and the audio file so that subsequent runs resolve the path
  directly without needing any fallback.

---

## Version 3.0.0 (2026-05-10)

This release completes the modernisation of discogstagger for Python 3.10+ and
marks the end of the alpha period.  It is a breaking release: the configuration
format has changed (see Configuration below) and several deprecated options have
been removed.

### Configuration

* **Breaking:** The primary configuration file is now `conf/config.yaml` (YAML).
  The legacy `conf/default.conf` INI file is no longer loaded by the
  application; it is retained in the repository as reference only.

* **Breaking:** Format strings are kept in a companion INI file
  (`conf/formats.ini` by default).  A personal formats file must now be
  referenced explicitly via `common.formats_file` in the YAML config rather
  than being auto-discovered by filename convention.

* All operational settings are documented with annotations in `conf/config.yaml`
  (the canonical reference).  A personal config only needs to override values
  that differ from the defaults.

* `formats_file` paths are validated at startup; a missing file is reported
  immediately rather than silently falling back to built-in defaults.

* `-c` with no argument now uses only the built-in defaults (`config.yaml` +
  `formats.ini`); the previous default of `conf/default.conf` is removed.

* The `[suppress_tags]` YAML list allows individual Discogs metadata fields to
  be excluded from file tags while still being available to format strings for
  directory/file naming.  A startup warning is logged when a format string
  references a suppressed tag.

* `char_profile` / `char_substitutions` replaces the old `[character_exceptions]`
  INI section.  Profiles are defined in `conf/char_substitutions.yaml`; built-in
  profiles cover `linux`, `macos`, and `windows` (NTFS/Samba-safe).
  `path_sep_replacement` and `control_replacement` give explicit control over
  what embedded `/` and control characters are replaced with.

* **Removed:** `normalize` setting (Unicode NFKD filename decomposition).  The
  `char_profile` system covers the same use case more explicitly.

* **Removed:** `join_artists` / `join_genres_and_styles` as active config.  The
  Discogs join field (`Feat.`, `&`, `vs.`, etc.) is now used directly; see
  Artist handling below.

### Discogs search

* Completely rewritten in `discogs_search.py` as a standalone `DiscogsSearch`
  class with a four-tier search strategy:

  1. Structured fields (artist + title + year)
  2. Structured fields without year
  3. Artist browse (all releases for the artist)
  4. Free-text search (max 5 results)

* Two-tier candidate matching: tier-1 candidates are scored by average track
  length difference; tier-2 candidates (no Discogs duration data) are scored by
  fuzzy title similarity (`rapidfuzz` token sort ratio).  Both are configurable
  via `tracklength_tolerance` and `title_similarity_threshold`.

* Fixed broken accumulation in `_compareTrackLengths` that previously compared
  against a running sum instead of per-track differences.

* Fixed "swallowed release" bug where a direct release match was discarded in
  favour of a master lookup and never compared.

* Early canonical artist name resolution via two-phase lookup: space-insensitive
  exact match, then Discogs namevariations API.  Eliminates failed searches
  caused by artist name variants.

### Artist and tag handling

* Multi-artist credits (`Blutengel Feat. Solar Fake`, `Coldcut & Hexstatic`)
  are now preserved in full in the single-value `albumartist` and `artist` tags
  using the Discogs join field.

* The multi-value `albumartists` and `artists` tags always store individual
  artist names as separate array entries for filtering and sorting, regardless
  of how the single-value fields are displayed.

* Tracks without individual Discogs artist credits inherit the album's full
  display string (e.g. all tracks on a `Coldcut & Hexstatic` release use
  `Coldcut & Hexstatic` as the track artist, not just `Coldcut`).

* `join_artists` config option (empty by default) provides a separator fallback
  for the rare case where Discogs supplies no join text between multiple artists.

* Tags are now applied to the destination copy of the file, never to the
  original.  The copy step always runs before the tag step.

* `remove_duplicate_items` preserves Discogs insertion order (primary label is
  now reliably written to the `label` tag, not an arbitrary one).

### File naming — new format string variables

* `%format_code%` — compact release-format code computed from Discogs format +
  descriptions + disc count via a five-step pipeline defined in
  `conf/format_codes.yaml` (e.g. `CD`, `DCD`, `LCDS`, `7″S`).

* `%edition%` — edition qualifier extracted from Discogs format descriptions
  (e.g. `Deluxe Edition`, `30th Anniversary Edition`).  Matching is
  case-insensitive substring so `Anniversary Edition` catches any anniversary
  year.

* `%quality%` — release-level audio quality: `lossless`, `vbr`, or a CBR
  bitrate in kbps (e.g. `320`).  Computed from all tracks.

* `%trackcount%` — total number of tracks across all discs.

### File naming — new format string functions

* `$if2(x, fallback)` — null-coalescing: returns `x` if non-empty, else
  `fallback`.

* `$if3(a, b, c, …)` — returns the first non-empty value from any number of
  arguments.

### Cover art

* `image_policy` setting with three modes:
  - `always` — always download and replace (original behaviour)
  - `prefer_existing` — skip if any local cover image exists
  - `prefer_larger` — download only when the Discogs image has more pixels;
    uses Pillow or minimal JPEG/PNG header parsing for local comparison

### Filesystem robustness

* `pathutils.resolve_path()` handles WSL2/CIFS mounts where the kernel decodes
  non-UTF-8 bytes as `?`.  Falls back to `fnmatch` wildcard scanning when an
  exact path is not found.

### Custom metadata fields

* `discogs_id`, `discogs_release_url`, `amg_id`, and `freedb_id` are now
  registered via `MediaFile.add_field()` in `discogstagger/mediafile_ext.py`
  rather than being patched into the upstream library.

### Documentation

* New `docs/tagging_reference.md` covering all format string variables and
  functions, format codes, edition qualifiers, character substitution, cover art
  policy, and example format strings.

* New **Metadata field mapping** section documenting every tag written by the
  tagger: Discogs API source, description, data type, native/custom status, and
  the raw tag name in FLAC/Vorbis, MP3/ID3v2, MP4/M4A, and ASF/WMA.  Includes
  tables of unused Discogs fields and unused MediaFile fields for future
  reference.

### Tests

* Five new test modules: `test_formatcodes.py`, `test_charmap.py`,
  `test_pathutils.py`, `test_search_matching.py`, `test_search_client_mock.py`.

* 181 tests passing, 4 skipped.

### Bug fixes

* Fixed `⅓` (U+2153) crash in format string evaluation (`inarray` fallback
  eval path; fixed by switching to `json.loads`).

* Fixed `join_artists` KeyError when the key is absent from config.

* Fixed ReplayGain never running when `add_tags = true` but `-g` not passed on
  the command line.

* Fixed `errno[e]` in `OSError` handler (was `TypeError`; corrected to
  `e.strerror`).

* Fixed `print(results)` debug statement left in artist name resolution code.

* Fixed duplicate `%channels%` key in format string property map.

### Code quality

* **Python 2 removal:** `optparse` → `argparse`; `FancyURLopener`/`TagOpener`
  class removed; 42 logger calls converted from eager `%` operator to lazy
  `logger.xxx("msg %s", arg)` form; two bare `logging.error()` calls corrected
  to use the module-level logger.

* `clean_name()` regex precompiled as `_THE_SUFFIX_RE` class constant (was
  recreated and recompiled on every call).

* `_directory_has_audio_files()` simplified to `any(f.endswith(FILE_TYPE) …)`;
  duplicated `codecs` tuple removed.

* Dead code removed: commented `TagOpener` class, commented `disc_source_dir`
  fallback blocks, stale `!TODO` comment.

---

Version 3.0-alpha

* feature: add Discogs searching based on original metadata

* feature: add CUE file parsing, using the CUE libary from lolcut project: https://pypi.org/project/lolcut/

* feature: daemon mode, watches for changes to the source directory

* feature: add Foobar2000-style string formatting commands (basics)

* improvement: refactored replaygain, now works with loudgain or metaflac

* improvement: updated to python3

* improvement: updated metadata fields:
               * added MEDIA - original media information
               * updated ALBUMARTIST and ARTIST storage as lists, now able to save multiple artists e.g. on split discs
               * removed ALBUM ARTIST from MediaFile library, was causing duplication and not in the mapping on Hydrogen Audio (https://wiki.hydrogenaud.io/index.php?title=Tag_Mapping#cite_note-vorbis-field-names-13)
               * added CATNUMBERS_SORTED - available in tagging fields




Version 2.2.1

* improvement: Use field mapping used by Jaikoz (https://docs.google.com/spreadsheets/d/1afugW3R1FRDN-mwt5SQLY4R7aLAu3RqzjN3pR1497Ok/htmlview),
               this means specifially:
               * DISCOGSID is still used (which is an additional field only used by discogstagger2)
               * GROUPING used for Style grouping (using styles from Discogs)
               * FOLDER is still used (another additonal field only used by discogstagger2)
               * DISCNUMBER instead of the below mentioned DISC
               * TRACKNUMBER instead of the below mentioned TRACK
               * ENCODER instead of the below mentioned ENCODEDBY
               * URL_DISCOGS_RELEASE_SITE, the url to the discogs release
               * DISCID instead of the formerly used freedb_id
               * URL and URLTAGS are not used anymore

* improvement: provide script for tag update

* improvement: refactored replay gain

* improvement: version bump uses bumpversion

* improvement: remove unnecessary enumeration class

* improvement: use genres instead of genre to allow multiple genre fields, the same for GROUPING, ARTIST and ALBUMARTIST
               Note: this is just tested for FLAC files

Version 2.2.0

* improvement: be able to store and re-use tokens for the access to discogs (these are stored
               in the file .token in the current directory

* improvement: use latest version of the ext/mediafile (cloned from https://raw.githubusercontent.com/beetbox/mediafile/master/mediafile.py)

* improvement: cleanup storeage of Metadata of flacs, the following fields are used now:
               TRACK (TRACKNUMBER is not used anymore), TRACKTOTAL (TRACKC and TOTALTRACKS are not used anymore),
               DISC (DISCNUMBER is not used anymore), DISCTOTAL (DISCC and TOTALDISCS are not used anymore),
               COMMENT (DESCRIPTION is not used anymore), ALBUMARTIST (ALBUM ARTIST is not used anymore),
               LABEL (PUBLISHER is not used anymore), ENCODEDBY (ENCODER is not used anymore),
               DISCOGSID (was DiscogsId), DISCID (for freedb) added, FOLDER (for grouping purposes) added

Version 2.1.1

* improvement: This release contains some fixes for #14 and #16. Furthermore there is already a first draft for #7 included.

Version 2.0.1

* improvement: add new script to add folder tag to all selected files, so that the
               sorting of those files will be easier in BubbleUpnp, this new tag
               has to be added to minimserver to be sortable

Version 2.0.0

* improvement: remove group-config tag, as this could be easily added in the
               dir-format
* improvement: replace id.txt structure with usual config structure, to be able
               to overwrite config options in batch mode for each album/release

Version 1.2.0

* improvement: add several new tags (e.g. artist_sort, url) to the tracks
* improvement: add possibility to use '/' in dir-property, to allow subdirectory
               creation (e.g. %ARTIST%/%ALBUM%)
* feature: add possibility to name the first image folder.jpg, so that clients
           recognize this picture, even though it is not embedded (Issue #12)
* feature: add multi disc support (Issue #14), this does right now covers
           the handling of tags (discnumber, discstotal) and splitting folders
           for multiple discs based on a configuration parameter
* feature: copy files already existing in source directory (using config option
           copy_other_files)
* feature: add additional tags for all tracks in configuration (see section tags
           in discogs_tagger.conf - tagname: encoder) - right now not all tags
           are supported, to see a list of supported tags, please see
           discogstagger/ext/mediafile.py (Issue #11)
* feature: add possibility to adopt config options for each release via the id.txt
           file (Issue #17), this allows also to adopt certain tags via the
           config-option-prefix "tag:" (e.g. tag:artist will replace the artist
           of the current album with the given value)

Version 1.1.0

* improvement: use genre from discogs as the genre (configurable, so that you are still
               able to use style like in previous versions)
* improvement: provide the picture type "cover image" for flac as well
* improvement: add discogs_id as a tag to each file (as discogs_id for flac and mp3),
               some taggers (e.g. puddletag) need this information
* improvement: add some translations for german umlauts
* feature: add possiblity to provide a separate destination directory (-d)
* feature: add possiblity to provide the release id via a file in the source
           directory. The name of the file as well as the name of the used key
           is configurable, a default configuration is provided
* feature: add possibility to use lower case file and directory names via config option
* feature: add possibility to keep already existing tags in the file (e.g. freedb_id)

Version 1.0.1

* style clean-up

Version 1.0.0
* feature : options to embed cover art into metadata (issue #4)
* feature : now supports mp4/asf formats (in addition to mp3/flac) via
                the inclusion of the mediafile.py library. (not yet tested)
* improvement : clean up code base and installer
* improvement : remove comments from metadata (issue #6)

Version 0.8

* fix : bug in discogs_tagger.py . song_format initialized incorrectly.

Version 0.6

* fix : artist name is now accessed from the release class, and not the Artist
class (reported by cmaussan)
* improvement : Release names now support multiple artists in release names.
Multiple artist names are statically joined with an ampersand (&).

Version 0.5

* Included updated version of discogs_client.py (1.1.1)
* minimal style cleanup in discogs_tagger.py

Version 0.4

A couple minor bugfixes, and feature enhancements.
    - FIX : incorrect handling of directory names, when the basename was not in the
      immediate path.
    - Added a new filename tag. %LABEL% now allows the record label name in the filename
    - Improvement : using the unicodedata library to convert unicode values to their
      known ASCII counterpart. Reduction the CHAR_EXCEPTION dict, which will eventually
      move to the configuration file.

Version 0.3

Add a couple requests from dimitry_ghost and Dec via discogs.com
http://www.discogs.com/help/forums/topic/251892?page=1#msg2950783

    - Writes the master release id to the .nfo file if present.
    - Option to allow the original directory to be kept on FS (keep_original=True in
      config file)

Version 0.2
    - Documentation updates
    - Very basic logging and error handling added to discogs_tagger
    - Providing script to a wider audience.

Version 0.1

    - An initial, very basic working release. Minimal testing was performed.
