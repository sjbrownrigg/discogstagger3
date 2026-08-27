# Running discogstagger3 in Docker

For a ready-made deployment — compose files, PUID/PGID handling, `/config`
seeding and NAS mounts — see **[docker-dt3](https://github.com/sjbrownrigg/docker-dt3)**.
This page covers what the *tool* needs from a container, which is what you want
if you are building your own image.

## OS-level dependencies

The Python package handles all tagging and metadata. Some features require
external binaries:

| Feature | Binary | Package (Debian/Ubuntu) | Required? |
|---|---|---|---|
| CUE sheet splitting | `shntool` | `shntool` | Only if processing CUE files |
| CUE — FLAC source decoding | `flac` | `flac` | Only if source image is FLAC |
| CUE — any other format (APE, WavPack, …) | `ffmpeg` | `ffmpeg` | Used automatically; no extra package |
| ReplayGain analysis | `ffmpeg` | `ffmpeg` | Only if `replaygain.add_tags` is true |

`ffmpeg` handles format conversion for both ReplayGain and CUE processing. For
multi-track CUE files whose source image is not FLAC or WAV (e.g. APE,
WavPack), the source is decoded to a temporary WAV by `ffmpeg` before being
passed to `shntool split`. For single-track CUE files the source is converted
directly to FLAC by `ffmpeg`. No format-specific OS packages (such as
`monkeys-audio` or `wavpack`) are required.

Omit `shntool` and `flac` if you do not split CUE files, and `ffmpeg` too if you
do not use ReplayGain.

## Minimal Dockerfile

```dockerfile
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg shntool flac \
    && rm -rf /var/lib/apt/lists/*

COPY . /src/dt3
RUN pip install --no-cache-dir /src/dt3

# Configuration is a directory, not a file — there is no -c switch.
ENV DISCOGSTAGGER_CONFIG_DIR=/config
# Mutable runtime state: the OAuth token, the API cache and the log file.
ENV DISCOGSTAGGER_STATE_DIR=/cache

ENTRYPOINT ["discogstagger"]
```

Those two environment variables are the whole of the container-specific setup.
Without `DISCOGSTAGGER_STATE_DIR` the token, cache and log default under `HOME`,
which in a container is often not writable.

## Configuration

Mount a **directory** at `/config` containing:

```
config.yaml    your settings
formats.ini    your file and directory naming (optional)
```

Nothing in `config.yaml` needs to name `formats.ini` — it is found because it
sits beside it. No path inside the config should mention `/config`, which is
what lets the same directory work unchanged on a laptop.

Create one with:

```bash
docker run --rm -v /path/to/config:/config discogstagger3 --new-config
```

Running with no configuration refuses rather than falling back to defaults —
tagging renames and moves files.

## Credentials

Pass the token in the environment rather than writing it into a file that could
be committed or copied into an image layer:

```bash
docker run --rm \
    -e DISCOGS_USER_TOKEN=your_token_here \
    -v /path/to/config:/config \
    -v /path/to/incoming:/incoming \
    -v /path/to/sorted:/sorted \
    -v dt3-cache:/cache \
    discogstagger3 -s /incoming
```

`DISCOGS_USER_TOKEN` overrides `discogs.user_token` in the config.

## Mounts

Mount `incoming` and `sorted` as separate roots rather than the library root, so
the container cannot see the rest of the collection. **Both must be writable**:
discogstagger3 writes its done marker into the source directory and the tagged
copy into the destination.

`/cache` holds everything mutable, provided `DISCOGSTAGGER_STATE_DIR` points at
it:

```
/cache/
    .token               OAuth token cache
    discogstagger.log    debug log (INFO also goes to stdout)
    <cache.directory>/   Discogs release JSON and cover art, if configured
```

Set `cache.directory` to a path under `/cache` to persist API responses between
runs — they are rate limited, so this is worth doing.
