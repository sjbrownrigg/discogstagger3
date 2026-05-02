# Running discogstagger3 in Docker

## OS-level dependencies

The Python package handles all tagging and metadata. Two features require
external binaries that must be installed in the container:

| Feature | Binary | Package (Debian/Ubuntu) | Required? |
|---|---|---|---|
| CUE sheet splitting | `shntool` | `shntool` | Only if processing CUE files |
| ReplayGain analysis | `ffmpeg` | `ffmpeg` | Only if `add_tags=True` in `[replaygain]` |

`ffmpeg` is used by `r128gain` (the default ReplayGain application). It
supports all audio formats and is widely available in base images.

`shntool` splits a single-file audio image into per-track FLAC files using
a CUE sheet. It is only invoked when `parse_cue_files=True` in `[cue]` and
a matching CUE/image pair is found in the source directory.

## Minimal Dockerfile

```dockerfile
FROM python:3.12-slim

# OS dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        shntool \
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
- If you do not use CUE splitting, omit `shntool` to keep the image smaller.
- If you do not use ReplayGain (`add_tags=False`), omit `ffmpeg` too.
