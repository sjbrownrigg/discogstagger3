# Docker configuration

This directory is mounted at `/config` inside the container.

Data files (committed to this repo — do not edit):
- `char_substitutions.yaml` — character replacement map
- `format_codes.yaml` — Discogs format code lookup table
- `logger_docker.conf` — logging configuration

You must also add your own config files before starting:

```bash
cp conf/config_sample.yaml          docker/config/config.yaml
cp discogstagger/conf/formats_sample.ini docker/config/formats.ini
```

Then edit `config.yaml` to set your paths and Discogs token.
See `conf/config_sample.yaml` for the full annotated reference.
