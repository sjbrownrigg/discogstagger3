# Running discogstagger3 in Docker

## OS-level dependencies

The Python package handles all tagging and metadata. Two features require
external binaries that must be installed in the container:

| Feature | Binary | Package (Debian/Ubuntu) | Required? |
|---|---|---|---|
| CUE sheet splitting | `shntool` | `shntool` | Only if processing CUE files |
| CUE — FLAC source decoding | `flac` | `flac` | Only if source image is FLAC |
| CUE — any other format (APE, WavPack, …) | `ffmpeg` | `ffmpeg` | Used automatically; no extra package |
| ReplayGain analysis | `ffmpeg` | `ffmpeg` | Only if `add_tags=True` in `[replaygain]` |

`ffmpeg` handles format conversion for both ReplayGain and CUE processing.
For multi-track CUE files whose source image is not FLAC or WAV (e.g. APE,
WavPack), the source is decoded to a temporary WAV by `ffmpeg` before being
passed to `shntool split`.  For single-track CUE files the source is
converted directly to FLAC by `ffmpeg`.  No format-specific OS packages
(such as `monkeys-audio` or `wavpack`) are required.

## Minimal Dockerfile

```dockerfile
FROM python:3.12-slim

# OS dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        shntool \
        flac \
        libpillowfight0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .

RUN pip install --no-cache-dir -e .

ENTRYPOINT ["discogstagger"]
```

## Configuration for Docker

Set your Discogs personal access token via an environment variable rather
than hard-coding it in a conf file:

```bash
docker run --rm \
    -e DISCOGS_USER_TOKEN=your_token_here \
    -v /path/to/music:/music \
    -v /path/to/conf:/app/conf/local.conf \
    -v /path/to/cache:/cache \
    discogstagger3 -c conf/local.conf -s /music
```

Set `directory=/cache` under `[cache]` in your conf file to persist the
release JSON and image cache between container runs. The cache layout is:

```
/cache/
    releases/<id>.json   — Discogs API response (avoids re-fetching)
    images/<hash>.jpg    — downloaded cover art
```

Or pass `user_token` directly in your conf file's `[discogs]` section.

## Notes

- The `.token` OAuth cache file is written to the working directory. Mount a
  persistent volume there if you use OAuth rather than a personal access token.
- Log output goes to both stdout (INFO) and `discogstagger.log` (DEBUG) in the
  working directory. Mount that directory to keep logs between runs.
- If you do not use CUE splitting, omit `shntool` and `flac` to keep the image smaller.
- If you do not use ReplayGain (`add_tags=False`), omit `ffmpeg` too.
