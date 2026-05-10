# Daemon mode

Daemon mode (`-w`) watches a source directory and automatically tags any new
album that appears there.  It is designed to run continuously as a background
process — start it once, drop albums into your incoming folder, and they are
tagged and moved to your library without further intervention.

---

## Quick start

```bash
discogstagger -c conf/config_personal.yaml -w
```

If `common.source_dir` and `common.dest_dir` are set in your config you do not
need `-s` or `-d`.  Override them on the fly with the usual flags:

```bash
discogstagger -c conf/config_personal.yaml -w -s /mnt/incoming -d /mnt/library
```

The process runs until you press **Ctrl-C**.

---

## How it works

The watcher uses `watchdog`'s `PollingObserver`, which scans the source
directory at a fixed interval and detects new content by comparing directory
snapshots.  **Polling is used by default** — not inotify — so it works on any
mounted filesystem including CIFS/SMB and NFS.

When a change is detected:

1. A stability check runs: the watcher polls the directory's total size every
   60 seconds until it stops growing.  This avoids tagging a release while it
   is still being copied in.
2. `id.txt` files are scanned (or Discogs is searched automatically if
   `searchdiscogs: true`).
3. Matching source directories are tagged and written to the destination.

### Poll interval

The poll interval is set in your config under `common.watch_poll_interval`
(default: 30 seconds).  Shorter intervals give faster response; longer intervals
reduce filesystem load on slow or remote mounts.

```yaml
common:
  watch_poll_interval: 30   # seconds
```

---

## Network filesystems — CIFS/SMB and NFS

**inotify does not work on CIFS or NFS mounts.**  The Linux kernel's CIFS and
NFS drivers do not implement the inotify interface because filesystem change
events are not reliably propagated from a remote server to a local client.
Applications that rely on inotify (including `watchdog`'s default `Observer`)
will start without error but never receive any events.

discogstagger3 avoids this entirely by using `PollingObserver`.  No special
configuration is required on CIFS or NFS; increase `watch_poll_interval` if
you want to reduce the number of directory scans.

### Recommended CIFS mount options (WSL2 / Linux)

A minimal working `/etc/fstab` entry for a CIFS music share:

```
//server/music  /mnt/music  cifs  credentials=/etc/samba/creds,uid=1000,gid=1000,file_mode=0664,dir_mode=0775,vers=3.0  0  0
```

Key points:

| Option | Reason |
|---|---|
| `vers=3.0` | SMB 3.0 gives better performance and reliability than the SMB 1.0 default |
| `uid=` / `gid=` | Match your Linux user so discogstagger can read and write without `sudo` |
| `file_mode=0664` / `dir_mode=0775` | Ensure newly written files are group-readable |
| `credentials=` | Keep the password out of `/etc/fstab` |
| *(no `iocharset=utf8`)* | Omitting this lets the kernel substitute `?` for non-UTF-8 bytes; discogstagger handles those via `pathutils.resolve_path()` |

For WSL2 specifically, mount via `/etc/wsl.conf` or a startup script rather
than `/etc/fstab` if `fstab` entries are not being applied automatically.

### NFS

NFS 4.x mounts work the same way.  A typical entry:

```
server:/export/music  /mnt/music  nfs4  rsize=65536,wsize=65536,timeo=14,intr  0  0
```

No special handling is needed; polling works the same as for CIFS.

---

## Docker

### Approach

Run discogstagger3 as a long-lived container with your incoming and library
directories mounted as volumes.

### Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -e ".[oauth]"

# Default command — override with your own config path
CMD ["discogstagger", "-c", "/config/config_personal.yaml", "-w"]
```

### docker-compose.yml

```yaml
services:
  discogstagger:
    build: .
    restart: unless-stopped
    volumes:
      - /mnt/music/incoming:/incoming        # source
      - /mnt/music/library:/library          # destination
      - ./conf:/config                       # your personal config lives here
    environment:
      - TZ=Europe/London
```

In `/config/config_personal.yaml`:

```yaml
common:
  formats_file: /config/formats_personal.ini
  source_dir: /incoming
  dest_dir: /library
  watch_poll_interval: 30
```

Start and stop:

```bash
docker compose up -d        # start in background
docker compose logs -f      # follow logs
docker compose down         # stop
```

### Volume notes

- If the Docker host mounts the music share via CIFS or NFS, the container
  sees a normal bind-mounted directory and polling works without any extra
  configuration.
- For direct CIFS/NFS access inside the container, add the `privileged: true`
  flag and the `cifs-utils` / `nfs-common` packages to the image — but
  bind-mounting from the host is simpler.
- Discogs API credentials should be passed via environment variables or a
  secrets file mounted into `/config/`, not baked into the image.

---

## Troubleshooting

### No albums are being picked up

1. Check the log — run at `logging.level: 10` (DEBUG) to see poll events.
2. Verify the source directory path is correct inside the container / WSL2
   namespace, not the Windows or macOS path.
3. Ensure each album subdirectory contains an `id.txt` (or that
   `searchdiscogs: true` is set) — the daemon does not tag directories without
   a release identifier unless auto-search is enabled.

### Albums are tagged before the copy finishes

Increase `watch_poll_interval` or reduce network throughput so the
size-stability check has time to catch a still-growing directory.

### Permission errors on CIFS

Verify the `uid=` / `gid=` mount options match the user running discogstagger.
On WSL2 your Linux UID is typically 1000.

### `KeyError` or crash on startup

The most common cause is a missing or mis-spelled key in your personal config.
The error message names the key; check `conf/config.yaml` for the canonical
spelling.
