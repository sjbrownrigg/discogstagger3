# discogstagger3 — Docker deployment

Single-command deployment using Docker Compose.  The image is built directly
from GitHub master, music lives on an NFS share, and the daemon watches for
new albums automatically.

---

## Prerequisites

- Docker Engine with Compose v2 (`docker compose` — not the older `docker-compose`)
- NFS client support on the Docker host (`nfs-common` on Debian/Ubuntu)
- Discogs personal access token from https://www.discogs.com/settings/developers
- The following directories on the NAS (create them if they don't exist):

| NAS path | Purpose |
|---|---|
| `/volume1/Music/incoming/` | Drop new albums here for tagging |
| `/volume1/Music/sorted/` | Tagged albums are written here |
| `/volume1/shared/Docker/discogstagger/config/` | Configuration files (see below) |

---

## First-time setup

### 1. Populate the NAS config directory

Copy everything from `docker/config/` in this repository to
`/volume1/shared/Docker/discogstagger/config/` on the NAS:

```bash
# From the project root — adjust the destination to match your NAS mount
cp docker/config/* /mnt/nas/shared/Docker/discogstagger/config/
```

The config directory must contain:

| File | Description |
|---|---|
| `config_personal.yaml` | Main configuration (paths, settings, credentials) |
| `formats_personal.ini` | Directory and filename format strings |
| `format_codes.yaml` | Format code rules (LP, CD, CDS, …) |
| `char_substitutions.yaml` | Character substitution profiles |
| `logger_docker.conf` | Logging configuration (stdout for `docker logs`) |

### 2. Add your Discogs credentials

Edit `/volume1/shared/Docker/discogstagger/config/config_personal.yaml` on the
NAS and replace `YOUR_USER_TOKEN` with your personal access token:

```yaml
discogs:
  user_token: your_actual_token_here
```

### 3. Launch

```bash
docker compose -f docker/docker-compose.yml up -d
```

Docker will:
1. Pull the source code from GitHub master
2. Build the image (this takes a few minutes on first run)
3. Mount the NFS volumes
4. Start the daemon, which polls `/music/incoming/` every 30 seconds

---

## Daily use

### Follow logs

```bash
docker compose -f docker/docker-compose.yml logs -f
```

### Tagging a new album

1. Place the album directory (containing audio files and `id.txt`) in
   `/volume1/Music/incoming/` on the NAS.
2. The daemon detects it within 30 seconds and begins tagging.
3. The tagged album appears in `/volume1/Music/sorted/`.

If the release ID is not known, set `searchdiscogs: true` in
`config_personal.yaml` and the tagger will search Discogs automatically using
the existing file metadata.

### Stop / start

```bash
docker compose -f docker/docker-compose.yml stop
docker compose -f docker/docker-compose.yml start
```

### Rebuild after a code update on GitHub

```bash
docker compose -f docker/docker-compose.yml up -d --build
```

This pulls the latest master, rebuilds the image, and restarts the container.
The NFS volumes and cache are untouched.

---

## Volume layout

| Docker volume | NFS path | Container path |
|---|---|---|
| `music` | `:/volume1/Music` | `/music` |
| `config` | `:/volume1/shared/Docker/discogstagger/config` | `/config` |
| `cache` | *(local named volume)* | `/cache` |

The `cache` volume persists the Discogs API response cache across container
restarts, avoiding unnecessary re-fetches.

---

## Adjusting configuration

All settings are in `/config/config_personal.yaml` on the NAS.  The container
reads it on every tagging run so most changes take effect without a restart.
Changes to `logger_docker.conf` require a container restart:

```bash
docker compose -f docker/docker-compose.yml restart
```

To increase log verbosity temporarily, set `level: 10` (DEBUG) in
`config_personal.yaml` — no restart needed.

---

## Troubleshooting

| Symptom | Check |
|---|---|
| Container exits immediately | `docker compose logs` — likely a missing or invalid config file |
| NFS volume fails to mount | Verify NFS export is reachable: `showmount -e 192.168.1.240` |
| Albums not picked up | Confirm `id.txt` exists in the album directory, or enable `searchdiscogs: true` |
| Permission errors on NFS | Ensure the Docker host's UID matches the NFS export permissions |
| `formats_file not found` | Check `/config/formats_personal.ini` exists on the NAS config share |
