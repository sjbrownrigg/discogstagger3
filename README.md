# discogstagger3

A console-based audio tagger that fetches release metadata from the
[Discogs](https://www.discogs.com) API and writes it to FLAC and MP3 files.

Based on the original work of
[jesseward](https://github.com/jesseward/discogstagger) and
[triplem](https://github.com/triplem/discogstagger).

---

> ## ⚠ Known issue: album metadata can execute code
>
> `$inarray` and `$flatten` fall back to `eval()` on their argument, and both
> are meant to be pointed at metadata — so an album title can run code during
> tagging. Discogs titles are editable by anyone with an account.
>
> Not yet fixed here. The fix is small (`ast.literal_eval`) and is described,
> with everything else worth bringing back from massMusicTagger, in
> [docs/BACKPORT.md](docs/BACKPORT.md).

> ## ⚠ Breaking changes in 4.0.0 — read before upgrading
>
> **`-c` / `--conf` is gone.** A configuration is `config.yaml`, `formats.ini`
> and `credentials/` resolving relative to each other — it moves as a unit, so
> the directory is what gets selected:
>
> ```bash
> DISCOGSTAGGER_CONFIG_DIR=/path/to/config discogstagger
> ```
>
> Found via `DISCOGSTAGGER_CONFIG_DIR`, else `$XDG_CONFIG_HOME/discogstagger`,
> else `~/.config/discogstagger`. Create one with `discogstagger --new-config`.
>
> **A missing configuration is an error, not a fallback.** A path that did not
> exist used to silently load the bundled sample, so a typo ran the tagger
> against settings nobody had seen. This tool renames and moves files; it now
> refuses rather than guessing.
>
> **`common.templates_dir` removed** — Mako templates always come from the
> package. **`common.formats_file` deprecated** — `formats.ini` is found beside
> `config.yaml` by name; the key still works and warns.
>
> Section names are unchanged: a 3.x `config.yaml` keeps working once the
> directory is where discogstagger3 looks for it.
>
> Full detail: [docs/HISTORY.md](docs/HISTORY.md).

---

> **Looking for MusicBrainz support or a mass tagger?**
> See [massMusicTagger](https://github.com/sjbrownrigg/massMusicTagger) —
> a multi-source mass tagger built on discogstagger3 that adds MusicBrainz
> (with cascading fallback), Cover Art Archive images, AcoustID fingerprinting,
> concurrent processing, and Docker deployment.

---

## What it does

- Fetches full album metadata from Discogs by release ID, or searches
  automatically using existing file tags
- Writes tags (artist, album, year, label, catalogue number, genre, country,
  ReplayGain, and more) to FLAC and MP3 files
- Downloads and optionally embeds cover art
- Generates `.m3u` playlist and `.nfo` info files per release
- Splits CUE sheet + single-file images into per-track FLAC files
- Adds ReplayGain tags via `r128gain` (requires `ffmpeg`)
- Watches a directory for new arrivals in daemon mode (`-w`)
- Caches all Discogs API responses on disk, avoiding repeated API calls on
  re-runs and making troubleshooting easier

## Why this version?

This fork was created to run as an automated cron job processing new releases
dropped into an incoming folder, without manual intervention.  Key additions
over the upstream:

- **Foobar2000-style format strings** — flexible `%variable%` and `$function()`
  syntax for filenames and directory names (see
  [docs/tagging_reference.md](docs/tagging_reference.md))
- **Automatic Discogs search** — searches by existing file metadata when no
  release ID is supplied
- **CUE file processing** — splits single-file audio images using `shntool`
- **Disk cache** — all API responses stored as human-readable JSON
- **r128gain** — pip-installable ReplayGain analysis via `ffmpeg`, replacing
  `metaflac`/`loudgain`

---

## Requirements

- Python 3.10+
- `ffmpeg` — required for ReplayGain (`r128gain` wraps it)
- `shntool` — required for CUE sheet splitting

See [DOCKER.md](DOCKER.md) for OS dependency details and a minimal Dockerfile.

## Installation

```bash
git clone https://github.com/sjbrownrigg/discogstagger3.git
cd discogstagger3
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Authentication

Generate a personal access token from your
[Discogs developer settings](https://www.discogs.com/settings/developers)
and add it to your config:

```ini
[discogs]
user_token = your_token_here
```

Or export it as an environment variable before running:

```bash
export DISCOGS_USER_TOKEN=your_token_here
```

---

## Quick start

Create a configuration (once):

```bash
discogstagger --new-config
```

That writes `config.yaml` and `formats.ini` into `~/.config/discogstagger`
(or `$DISCOGSTAGGER_CONFIG_DIR`) and tells you what to edit. It never
overwrites an existing file.

Tag a single album with a known Discogs release ID:

```bash
./discogstagger.py -s ~/Music/incoming/Artist/Album/ -r 12345678
```

Tag a whole incoming folder automatically (searches Discogs using existing
file tags):

```bash
./discogstagger.py -s ~/Music/incoming/
```

Copy tagged files to a separate destination:

```bash
./discogstagger.py -s ~/Music/incoming/ -d ~/Music/sorted/
```

## Command-line reference

```
usage: discogstagger [-h] [--version] [-r RELEASEID] [-s SOURCEDIR]
                     [-d DESTDIR] [--new-config [DIR]] [--force-new-config]
                     [--recursive] [-f] [-g] [-w]

Tag audio files with metadata from Discogs.

options:
  -h, --help            show this help message and exit
  --version             show program's version number and exit
  -r RELEASEID, --releaseid RELEASEID
                        Discogs release ID of the target album
  -s SOURCEDIR, --source SOURCEDIR
                        Directory containing the audio files to tag (overrides
                        common.source_dir in config)
  -d DESTDIR, --destination DESTDIR
                        Base directory to copy tagged files to (overrides
                        common.dest_dir in config)
  --new-config [DIR]    Write a fresh config.yaml and formats.ini into DIR and
                        exit. Defaults to the configuration directory, so
                        plain --new-config sets you up where the next run will
                        look. Existing files are never overwritten.
  --force-new-config    With --new-config, overwrite files that already exist.
                        This discards credentials and format strings.
  --recursive           Search source directory recursively for albums
  -f, --force           Re-tag albums even when the done marker already exists
  -g, --replay-gain     Add ReplayGain tags after tagging
  -w, --watch           Watch source directory for new albums (daemon mode)
```

See [docs/daemon_mode.md](docs/daemon_mode.md) for daemon mode setup including
CIFS/SMB, NFS, and Docker deployment instructions.

---

## Configuration

Configuration is a **directory**, not a single file. `config.yaml` is the entry
point, and every path inside it resolves against that file's own directory — so
a configuration and the files it references travel together, and the same
directory works unchanged on a laptop or mounted into a container.

```
config.yaml              your settings
formats.ini              your file and directory naming (optional)
```

That is the whole list — the configuration directory holds what *you* own and
nothing else. Neither file needs to reference the other: `formats.ini` is found
because it sits beside `config.yaml` under that name, and if it is absent the
bundled format strings are used.

Mako templates for `.nfo`/`.m3u` and the rule tables (`format_codes.yaml`,
`char_substitutions.yaml`) belong to discogstagger3 and ship inside the package.
They are not copied into your config directory, so they keep improving with each
upgrade rather than freezing at whatever version was installed the day you set
up. `details.format_codes` and `details.char_substitutions` remain as escape
hatches if you genuinely need to change one.

It is found in this order:

1. `$DISCOGSTAGGER_CONFIG_DIR`
2. `$XDG_CONFIG_HOME/discogstagger`, else `~/.config/discogstagger`

Create one with `discogstagger --new-config`. There is no `-c` switch: the
configuration is a directory, so it is selected by pointing
`DISCOGSTAGGER_CONFIG_DIR` at one.

```bash
DISCOGSTAGGER_CONFIG_DIR=~/configs/vinyl discogstagger
```

### Where defaults come from

Every setting and its default lives in one table, `discogstagger/config_schema.py`.
`conf/config_sample.yaml` is documentation of that table and is **never loaded at
runtime** — so a value you did not set can always be traced to one place.
Unknown keys are reported rather than ignored, and a config file that does not
exist is an error rather than a silent fall back to defaults.

### Key options

| Section | Key | Default | Description |
|---|---|---|---|
| `common` | `source_dir` | *(empty)* | Default source directory; overridden by `-s` |
| `common` | `dest_dir` | *(empty)* | Default destination directory; overridden by `-d` |
| `common` | `formats_file` | *(empty)* | Path to your format strings INI file |
| `common` | `watch_poll_interval` | `30` | Polling interval in seconds for daemon mode |
| `details` | `keep_original` | `true` | Keep source files after tagging |
| `details` | `embed_coverart` | `true` | Embed cover art into file metadata |
| `details` | `image_policy` | `prefer_larger` | Cover art download policy |
| `details` | `char_profile` | `linux` | Character substitution profile (`linux`, `macos`, `windows`) |
| `details` | `use_lower_filenames` | `true` | Lowercase filenames |
| `replaygain` | `add_tags` | `true` | Calculate and write ReplayGain tags |
| `replaygain` | `application` | `r128gain` | `r128gain`, `metaflac`, or `loudgain` |
| `cache` | `directory` | *(empty)* | Path for disk cache of API responses and images |

See `conf/config.yaml` for the full annotated reference.

### Filename and directory formatting

Filenames and directory names are built from Foobar2000-style format strings.
See [docs/tagging_reference.md](docs/tagging_reference.md) for all available
`%variables%` and `$functions()`.

### Batch processing with `id.txt`

Place an `id.txt` file in each album directory to provide the release ID
without using `-r`:

```ini
[source]
discogs_id = 12345678
```

Use `--recursive` to walk a whole tree of directories, each containing its
own `id.txt`.  Use `searchdiscogs=True` in `[batch]` to have the script
search Discogs automatically for directories that have no `id.txt`.

### Disk cache

```ini
[cache]
directory = ~/.cache/discogstagger3
```

With caching enabled, on the first run all Discogs API responses are written
to disk.  Subsequent runs for the same albums make zero API calls.  Release
data is stored as human-readable JSON under
`<cache_dir>/releases/<id>.json`, making it easy to inspect what the API
returned without making a live request.

---

## Running in Docker

[**docker-dt3**](https://github.com/sjbrownrigg/docker-dt3) is a ready-made
deployment: compose files, PUID/PGID handling, NAS mounts and WSL2 notes.

See [DOCKER.md](DOCKER.md) for what discogstagger3 itself needs from a
container — OS dependencies, the two environment variables, and a minimal
Dockerfile — if you would rather build your own.

---

## Development

```bash
pip install -e ".[dev]"
pytest
```

The test suite runs without network access — Discogs API responses are
replayed from JSON fixtures in `test/release/`.

---

## Utility scripts

The `scripts/` directory contains standalone helpers:

| Script | Description |
|---|---|
| `fetch_json.py` | Fetch a release by ID and save the JSON (for cache pre-population or inspection) |
| `add_folder.py` | Tag FLAC files with a `FOLDER` grouping tag |
| `clean_tags.py` | Remove legacy/duplicate tags and normalise DISCOGSID storage |
| `find_id_files.py` | List Discogs IDs from all `id.txt` files in a tree |
| `migrate_id_files.py` | Migrate old-style `id.txt` files to the current sectioned format |
| `split_tags.py` | Split multi-value tags stored with `\\` as a separator |
| `find_multiple_albumartists.py` | Report files where artist and albumartist counts differ |

---

## Project history

See [docs/HISTORY.md](docs/HISTORY.md) for the full changelog going back to
the original jesseward project.

---

## Credits

- Original project: [jesseward/discogstagger](https://github.com/jesseward/discogstagger)
- Python 3 port: [triplem/discogstagger](https://github.com/triplem/discogstagger)
- Discogs API client: [joalla/discogs_client](https://github.com/joalla/discogs_client)
- Audio tagging: [beets/mediafile](https://github.com/beetbox/mediafile)

## Useful links

- [Foobar2000 Title Formatting Reference](http://wiki.hydrogenaud.io/index.php?title=Foobar2000:Title_Formatting_Reference)
- [Tag Mapping — Hydrogen Audio](https://wiki.hydrogenaud.io/index.php?title=Tag_Mapping)
- [Discogs API documentation](https://www.discogs.com/developers/)
