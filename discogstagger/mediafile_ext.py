"""
Extends mediafile.MediaFile with Discogs-specific tags and re-exports it as
the single import point for the rest of the codebase.

All custom fields are registered once at import time via MediaFile.add_field().
The guard against double-registration means this module is safe to import
from multiple places and in tests.
"""
from mediafile import (
    MediaFile,
    MediaField,
    MP3DescStorageStyle,
    MP4StorageStyle,
    StorageStyle,
    ASFStorageStyle,
)

__all__ = ['MediaFile']


def _add(name, descriptor):
    """Register a custom field only if it hasn't been added already."""
    if name not in MediaFile.__dict__:
        MediaFile.add_field(name, descriptor)


# ---------------------------------------------------------------------------
# Discogs release identity
# ---------------------------------------------------------------------------

_add('discogs_id', MediaField(
    MP3DescStorageStyle('DiscogsReleaseId'),
    MP4StorageStyle('----:com.apple.iTunes:DISCOGS_RELEASE_ID'),
    StorageStyle('DISCOGSID'),
    ASFStorageStyle('DT/Release Id'),
))

_add('discogs_release_url', MediaField(
    MP3DescStorageStyle('DISCOGS_RELEASE_URL'),
    MP4StorageStyle('----:com.apple.iTunes:DISCOGS_RELEASE_URL'),
    StorageStyle('URL_DISCOGS_RELEASE_SITE'),
    ASFStorageStyle('WM/DiscogsReleaseUrl'),
))

# ---------------------------------------------------------------------------
# Alternative source IDs (used when source.name != discogs in config)
# ---------------------------------------------------------------------------

_add('amg_id', MediaField(
    MP3DescStorageStyle('AMGID'),
    MP4StorageStyle('----:com.apple.iTunes:AMG_ID'),
    StorageStyle('AMGID'),
    ASFStorageStyle('DT/AmgId'),
))

# ---------------------------------------------------------------------------
# Legacy / compatibility fields
# ---------------------------------------------------------------------------

_add('freedb_id', MediaField(
    MP3DescStorageStyle('DiscId'),
    MP4StorageStyle('----:com.apple.iTunes:DISCID'),
    StorageStyle('DISCID'),
    ASFStorageStyle('DT/discid'),
))
