# discogstagger3 — Docker deployment

Single-command deployment using Docker Compose.  The daemon watches an
incoming directory and automatically tags new albums as they arrive.

---

## Volume strategy — Linux vs WSL2

Docker's NFS volume plugin (`driver: local` with NFS options) is **not
supported on WSL2** — the Docker daemon's mount syscall is blocked by the
WSL2 kernel environment, giving `Operation not permitted` even with
`nfs-common` installed and the export reachable.

The solution is the same on both platforms: mount network shares in the host
OS first, then give Docker plain bind mounts.

### Linux (native Docker)

Mount the NAS shares and add them to `/etc/fstab`:

```bash
sudo mkdir -p /mnt/nas/music /mnt/nas/discogstagger-config

# Test mounts
sudo mount -t nfs4 192.168.1.240:/volume1/Music /mnt/nas/music
sudo mount -t nfs4 192.168.1.240:/volume1/shared/Docker/discogstagger/config \
    /mnt/nas/discogstagger-config

# Persist in /etc/fstab
echo "192.168.1.240:/volume1/Music /mnt/nas/music nfs4 rw,hard,intr,timeo=600,_netdev 0 0" \
    | sudo tee -a /etc/fstab
echo "192.168.1.240:/volume1/shared/Docker/discogstagger/config /mnt/nas/discogstagger-config nfs4 rw,hard,intr,timeo=600,_netdev 0 0" \
    | sudo tee -a /etc/fstab
```

### WSL2

NFSv4 also fails in WSL2 for the same reason (restricted mount syscall).
Use CIFS/SMB instead, which works reliably:

```bash
sudo mkdir -p /mnt/nas/music /mnt/nas/discogstagger-config

sudo mount -t cifs //192.168.1.240/music /mnt/nas/music \
    -o credentials=/etc/samba/creds,uid=$(id -u),gid=$(id -g)
sudo mount -t cifs //192.168.1.240/shared/Docker/discogstagger/config \
    /mnt/nas/discogstagger-config \
    -o credentials=/etc/samba/creds,uid=$(id -u),gid=$(id -g)
```

Add to `/etc/fstab` (WSL2 reads fstab on startup with `automount enabled = true`
in `/etc/wsl.conf`):

```
//192.168.1.240/music /mnt/nas/music cifs credentials=/etc/samba/creds,uid=1000,gid=1000,_netdev 0 0
//192.168.1.240/shared/Docker/discogstagger/config /mnt/nas/discogstagger-config cifs credentials=/etc/samba/creds,uid=1000,gid=1000,_netdev 0 0
```

Once the shares are mounted, set the paths in `docker/.env`:

```bash
# docker/.env
MUSIC_DIR=/mnt/nas/music
CONFIG_DIR=/mnt/nas/discogstagger-config
```

The `docker-compose.yml` uses `${MUSIC_DIR}` and `${CONFIG_DIR}` with sensible
local defaults if the `.env` file is absent.

---

## Prerequisites

- Docker Engine with Compose v2 (`docker compose`)
- Shares mounted on the host as described above (or locally accessible paths)
- Discogs personal access token from https://www.discogs.com/settings/developers
- The following directories on the NAS (create if they don't exist):

| NAS path | Purpose |
|---|---|
| `/volume1/Music/incoming/` | Drop new albums here for tagging |
| `/volume1/Music/sorted/` | Tagged albums are written here |
| `/volume1/shared/Docker/discogstagger/config/` | Configuration files |

---

## First-time setup

### 1. Populate the NAS config directory

Copy everything from `docker/config/` to the NAS config share:

```bash
cp docker/config/* /mnt/nas/discogstagger-config/
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

Edit `config_personal.yaml` on the NAS and replace `YOUR_USER_TOKEN`:

```yaml
discogs:
  user_token: your_actual_token_here
```

### 3. Launch

```bash
cd docker
docker compose up -d
```

Docker builds the image from source, then starts the daemon polling
`/music/incoming/` every 30 seconds.

---

## Daily use

### Follow logs

```bash
docker compose logs -f
```

### Tagging a new album

1. Place the album directory (with audio files and `id.txt`) in
   `/volume1/Music/incoming/` on the NAS.
2. The daemon detects it within 30 seconds and begins tagging.
3. The tagged album appears in `/volume1/Music/sorted/`.

Set `searchdiscogs: true` in `config_personal.yaml` to search Discogs
automatically when no `id.txt` is present.

### Stop / start / rebuild

```bash
docker compose stop
docker compose start
docker compose up -d --build   # rebuild after a code update
```

---

## Volume layout

| Path in container | Source |
|---|---|
| `/music` | `${MUSIC_DIR}` (bind mount from host) |
| `/config` | `${CONFIG_DIR}` (bind mount from host) |
| `/cache` | `cache` named volume (local, persists across restarts) |

---

## Adjusting configuration

Settings in `config_personal.yaml` take effect on the next tagging run —
no restart needed for most changes.  `logger_docker.conf` changes require:

```bash
docker compose restart
```

To increase log verbosity temporarily, set `level: 10` (DEBUG) in
`config_personal.yaml`.

---

## Troubleshooting

| Symptom | Check |
|---|---|
| Container exits immediately | `docker compose logs` — likely a missing config file or bad credentials |
| NFS mount fails with "Operation not permitted" | Use CIFS on WSL2; see Volume strategy above |
| Albums not picked up | Confirm `id.txt` exists, or enable `searchdiscogs: true` |
| `Source directory does not exist` | Check `source_dir` in `config_personal.yaml` uses the container path (`/music/incoming`), not a `~`-relative path |
| Permission errors on mounted share | Check `uid=`/`gid=` mount options match the user running Docker |
| `formats_file not found` | Check `formats_personal.ini` exists in the config share |
