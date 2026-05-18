# discogstagger3

A console-based audio tagger that fetches release metadata from the
[Discogs](https://www.discogs.com) API and writes it to FLAC and MP3 files.

Based on the original work of
[jesseward](https://github.com/jesseward/discogstagger) and
[triplem](https://github.com/triplem/discogstagger).

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

Tag a single album with a known Discogs release ID:

```bash
./discogstagger.py -c conf/my.conf -s ~/Music/incoming/Artist/Album/ -r 12345678
```

Tag a whole incoming folder automatically (searches Discogs using existing
file tags):

```bash
./discogstagger.py -c conf/my.conf -s ~/Music/incoming/
```

Copy tagged files to a separate destination:

```bash
./discogstagger.py -c conf/my.conf -s ~/Music/incoming/ -d ~/Music/sorted/
```

## Command-line reference

```
usage: discogstagger [-h] [--version] [-r RELEASEID] -s SOURCEDIR [-d DESTDIR]
                     [-c CONFFILE] [--recursive] [-f] [-g] [-w]

Tag audio files with metadata from Discogs.

options:
  -h, --help       show this help message and exit
  --version        show program version and exit
  -r RELEASEID     Discogs release ID of the target album
  -s SOURCEDIR     Directory containing the audio files to tag  (required)
  -d DESTDIR       Base directory to copy tagged files to
  -c CONFFILE      Configuration file (default: conf/default.conf)
  --recursive      Search source directory recursively for albums with id.txt
  -f, --force      Re-tag albums even when the done marker already exists
  -g, --replay-gain  Add ReplayGain tags after tagging
  -w, --watch      Watch source directory for new albums (daemon mode)
```

See [docs/daemon_mode.md](docs/daemon_mode.md) for daemon mode setup including
CIFS/SMB, NFS, and Docker deployment instructions.

---

## Configuration

Configuration is YAML.  `conf/config.yaml` is always loaded as the baseline;
your personal file (passed with `-c`) overrides only the values it specifies.
Format strings (file and directory naming patterns) live in a companion INI
file referenced via `common.formats_file`.

Copy `conf/config.yaml` to start your own config — it contains every option
with inline documentation.

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

See [DOCKER.md](DOCKER.md) for a minimal Dockerfile and notes on mounting
the cache and config as volumes.

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
