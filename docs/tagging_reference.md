# Tagging format string reference

Format strings use Foobar2000-style `%variable%` placeholders and `$function()`
calls. See the
[Foobar2000 Title Formatting Reference](http://wiki.hydrogenaud.io/index.php?title=Foobar2000:Title_Formatting_Reference)
for the general syntax.

---

## Contents

1. [Variables](#variables)
2. [Functions](#functions)
3. [Format codes — `%format_code%`](#format-codes)
4. [Edition qualifiers — `%edition%`](#edition-qualifiers)
5. [Character substitution](#character-substitution)
6. [Invalid character handling](#invalid-character-handling)
7. [Cover art policy](#cover-art-policy)
8. [Example format strings](#example-format-strings)
9. [Metadata field mapping](#metadata-field-mapping)

---

## Variables

### Album-level

| Variable | Description |
|---|---|
| `%album artist%` / `%albumartist%` | Album artist (consistent across the whole release) |
| `%album%` | Album title |
| `%year%` | Release year (four-digit integer) |
| `%releasedate%` | Full release date from Discogs — `YYYY-MM-DD`, `YYYY-MM`, or `YYYY` depending on precision available; falls back to `%year%` when Discogs has year only |
| `%catno%` | Catalogue number(s), joined with `, ` if there are multiple |
| `%totaldiscs%` | Total number of discs |
| `%trackcount%` | Total number of tracks across all discs |
| `%discnumber%` | Disc number |
| `%disctitle%` | Disc subtitle (e.g. `Live Bonus Disc`) |
| `%format%` | Discogs format name (e.g. `Vinyl`, `CD`, `File`) |
| `%format_description%` | Format descriptions as a JSON list after `[media_description]` mapping (e.g. `["Album", "ltd"]`) |
| `%format_code%` | Computed compact format code — see [Format codes](#format-codes) |
| `%edition%` | Edition qualifier for display in the album title, or empty string — see [Edition qualifiers](#edition-qualifiers) |
| `%mediatype%` | Source media type |

### Track-level

| Variable | Description |
|---|---|
| `%artist%` / `%track artist%` | Track artist |
| `%title%` | Track title |
| `%tracknumber%` | Zero-padded track number (e.g. `05`) |
| `%track number%` | Track number without zero-padding |
| `%fileext%` | File extension including dot (e.g. `.flac`) |

### Release-level quality (available after file scan)

| Variable | Description |
|---|---|
| `%quality%` | `lossless`, `vbr`, or a CBR bitrate in kbps (e.g. `320`). Computed from all tracks — VBR detected when bitrates vary by more than 5 kbps. |

### Per-track technical (available after file scan)

| Variable | Description |
|---|---|
| `%bitrate%` | Bitrate in kbps |
| `%bitdepth%` | Bit depth (e.g. `24`) |
| `%channels%` | `mono`, `stereo`, or `Nch` |
| `%codec%` | Codec name (`flac`, `mp3`, `aac`, …) |
| `%encoding%` | `lossless` or `lossy` |
| `%samplerate%` | Sample rate in Hz (e.g. `44100`) |
| `%length%` | Track length as `H:MM:SS` |
| `%length_ex%` | Track length with milliseconds |
| `%length_seconds%` | Track length in whole seconds |
| `%length_seconds_fp%` | Track length as a floating-point number |

---

## Functions

| Function | Arguments | Description |
|---|---|---|
| `$if1(cond, a, b)` | condition, then, else | Returns `a` when `cond` is truthy, else `b` |
| `$if2(x, fallback)` | value, fallback | Returns `x` if non-empty, else `fallback` — null-coalescing |
| `$if3(a, b, c, …)` | any number of values | Returns the first non-empty value |
| `$strcmp(s1, s2)` | two strings | `True` if strings are equal |
| `$stricmp(s1, s2)` | two strings | Case-insensitive equality |
| `$ifequal(n1, n2, a, b)` | two integers, two values | Returns `a` if `n1 == n2`, else `b` |
| `$ifgreater(n1, n2, a, b)` | two integers, two values | Returns `a` if `n1 > n2`, else `b` |
| `$inarray(list, item)` | JSON list string, item | `True` if `item` is in the list |
| `$lower(s)` | string | Lowercase |
| `$upper(s)` | string | Uppercase |
| `$num(n, places)` | number, width | Zero-pad number to `places` digits |
| `$substr(s, start, end)` | string, int, int | Substring — Python slice semantics |
| `$strchr(s, char)` | string, char | Position of first occurrence of `char` |

### String concatenation

Function arguments support `+` to combine literal text with function results:

```
$if1($inarray('["File","Web"]','%format%'),'%trackcount%x','')%format_code%
```

Produces `10xfile` for a 10-track digital release or `DCD` for a double CD.

---

## Format codes

`%format_code%` is computed from the Discogs format name, descriptions, and disc
count using the rules in `conf/format_codes.yaml`.  It compresses a release's
format into a short human-readable code suitable for directory names.

### How the code is built

Five steps are applied in order:

| Step | Rule | Example |
|---|---|---|
| 1 | Base code from format name | `Vinyl` → `LP`, `CD` → `CD` |
| 2 | Vinyl size overrides base | `Vinyl` + `12"` → `12″` |
| 3 | Type suffix from descriptions (first match) | `+ Single` → `S` (giving `CDS`, `7″S`) |
| 4 | Quantity prefix when disctotal > 1 | `2 discs` → `D` (giving `DCD`, `DLP`) |
| 5 | Modifier prefixes from descriptions (all applied) | `+ Limited Edition` → `L` (giving `LCDS`, `LDCD`) |

The inch mark `"` is replaced with the double prime `″` (U+2033) which is safe
in all common filesystem path names.

### Code table

| Release type | Discogs format + descriptions | `%format_code%` |
|---|---|---|
| CD album | `CD` + `Album` | `CD` |
| CD single | `CD` + `Single` | `CDS` |
| CD maxi-single | `CD` + `Maxi-Single` | `CDM` |
| CD EP | `CD` + `EP` | `CDEP` |
| Limited CD single | `CD` + `Single, Limited Edition` | `LCDS` |
| Numbered LP | `Vinyl` + `Album, Numbered` | `#LP` |
| Double CD | `CD` + `Album` (2 discs) | `DCD` |
| Limited double CD | `CD` + `Album, Limited Edition` (2 discs) | `LDCD` |
| LP | `Vinyl` + `Album` | `LP` |
| 7-inch single | `Vinyl` + `7", Single` | `7″S` |
| 12-inch maxi | `Vinyl` + `12", Maxi-Single` | `12″M` |
| 12-inch EP | `Vinyl` + `12", EP` | `12″EP` |
| Double LP | `Vinyl` + `Album` (2 discs) | `DLP` |
| Digital album | `File` + `Album` | `file` |
| Web/streaming | `Web` + `Album` | `web` |

### Customising format_codes.yaml

Edit `conf/format_codes.yaml` to:

- Add new base formats or rename existing codes
- Add vinyl size variants (e.g. `Acetate`)
- Add new suffixes (e.g. `Mini-Album: Mini`)
- Change the quantity alias from `D` to `2x`
- Add edition qualifiers to the `editions` list (see below)

Descriptions not listed in any section are silently ignored.

---

## Edition qualifiers

`%edition%` returns the first edition qualifier found in the release's format
descriptions, or an empty string.  Edition qualifiers are defined under the
`editions` key in `conf/format_codes.yaml`:

```yaml
editions:
  - Deluxe Edition       # also matches "Super Deluxe Edition"
  - Ultimate Edition
  - Collector's Edition
  - Expanded Edition
  - Anniversary Edition  # also matches "30th Anniversary Edition"
  - Special Edition
```

Matching is **case-insensitive substring**, so a pattern of `Anniversary Edition`
catches `30th Anniversary Edition`, `25th Anniversary Edition`, etc.  The *full
Discogs description string* is returned, not the pattern, so
`(30th Anniversary Edition)` appears in the name — not `(Anniversary Edition)`.

### Using `%edition%` in the dir format

```ini
dir=.../%album%$if1($strcmp('%edition%',''),'', ' \(%edition%\)')...
```

| Release | `%album%` + `%edition%` | Combined |
|---|---|---|
| Standard release | `Darkest Hour` + `` | `Darkest Hour` |
| Deluxe edition | `The Young Gods` + `Deluxe Edition` | `The Young Gods (Deluxe Edition)` |
| Anniversary | `Superstition` + `30th Anniversary Edition` | `Superstition (30th Anniversary Edition)` |

Edition qualifiers are intentionally kept out of `%format_code%` since they
describe the release as a product, not its physical format.

---

## Character substitution

Filename character substitution is controlled by a profile selected in your
config file.  Profiles are defined in `conf/char_substitutions.yaml`.

```ini
# In your .conf file [details] section:
char_profile = windows         # linux / macos / windows / your-own-profile
char_substitutions = conf/char_substitutions.yaml   # override path if needed
```

### Built-in profiles

| Profile | What it does |
|---|---|
| `linux` | No substitutions — preserves every character the filesystem allows. Only `/` and control characters are ever removed. |
| `macos` | Adds `:` → `-` (HFS+/APFS uses `:` as its internal path separator). |
| `windows` | Full set of NTFS-illegal characters: `:` `?` `*` `"` `<` `>` `\|` `\`. Safe for Samba/NAS shares accessed from Windows. |
| `unicode_to_ascii` | (Commented-out template) Transliterates Latin characters to ASCII — uncomment the entries you want. |

The `windows` profile makes sensible substitutions rather than just stripping:
`"` → `'`, `<`/`>` → `(`/`)`, `:` and `|` → `-`.

### Adding your own profile

Add a named block to `conf/char_substitutions.yaml`:

```yaml
profiles:
  my_profile:
    "'": ""          # strip apostrophes
    ",": ""          # strip commas
    "&": " and "     # ampersand → "and"
```

Then set `char_profile = my_profile` in your config.

### INI overrides

The `[character_exceptions]` section in your `.conf` file is applied **on top
of** the YAML profile, so you can add individual tweaks without editing the YAML:

```ini
[character_exceptions]
&=_and_
```

These replacements apply to filenames and directory names only — metadata tags
are never modified.

---

## Invalid character handling

Two config keys control what happens to characters that are genuinely invalid
on the filesystem (`/` and control characters `\x00–\x1f`, `\x7f`):

```ini
# In [details]:
path_sep_replacement = -    # replace / with hyphen instead of removing it
control_replacement  =      # remove control characters (default)
```

With `path_sep_replacement = -`, a track titled `Side A/Side B` becomes
`Side A-Side B` rather than `Side ASide B`.

---

## Cover art policy

The `image_policy` key controls whether the front cover is downloaded from
Discogs or kept from local files:

```ini
# In [details]:
image_policy = prefer_larger   # default
```

| Value | Behaviour |
|---|---|
| `always` | Always download and replace — original behaviour |
| `prefer_existing` | Skip download if any local cover image already exists |
| `prefer_larger` | Download only when the Discogs image is larger (in pixels) than the existing local cover; falls back to downloading when Discogs dimensions are unknown |

The comparison uses Discogs API metadata (width/height) for the remote side and
reads the local file dimensions using Pillow if installed, or minimal JPEG/PNG
header parsing otherwise.  This avoids unnecessary downloads when you have a
high-quality scan already in the directory.

---

## Example format strings

### Single-artist album

```ini
dir=%albumartist%/[%year%] %album%$if1($strcmp('%edition%',''),'', ' \(%edition%\)') [%format_code% $lower('%codec%')-%quality%-$substr('%samplerate%','','-3')$if1($strcmp('%channels%','stereo'),'s','%channels%')]
song=$num('%tracknumber%','2') %title%%fileext%
```

Produces:
```
Stray/[2012] Holding On [DCD flac-lossless-44s]/01 Holding On.flac
The Young Gods/[2012] The Young Gods (Deluxe Edition) [DCD flac-lossless-44s]/01 …
```

### Various artists with catalogue number

```ini
dir=$if1($strcmp('%albumartist%','Various'),'Various Artists','%albumartist%')/[%year%] %album%$if1($strcmp('%catno%',''),'', ' \(%catno%\)') [%format_code% …]
song=$num('%tracknumber%','2') $if1($strcmp('%artist%','%albumartist%'),'','%artist% - ')%title%%fileext%
```

### Full dir format with format code and quality

```ini
dir=$if1($strcmp('%albumartist%', 'Various'),'Various Artists','%albumartist%')/[%year%] %album%$if1($strcmp('%edition%',''),'', ' \(%edition%\)')$if1($strcmp('%catno%',''),'', ' \(%catno%\)') [$if1($inarray('["File","Web"]','%format%'),'%trackcount%x','')%format_code% $lower('%codec%')-%quality%$if1($strcmp('%quality%','lossless'),$ifequal(%bitdepth%,24,'-24',''),'')-$substr('%samplerate%','','-3')$if1($strcmp('%channels%','stereo'),'s','%channels%')]
```

Sample results:

| Release | Dir name |
|---|---|
| Clan of Xymox — Darkest Hour (CD) | `Clan of Xymox/[2004] Darkest Hour [CD flac-lossless-44s]` |
| Stray — Holding On (2×CD) | `Stray/[2012] Holding On [DCD flac-lossless-44s]` |
| The Young Gods — The Young Gods (Deluxe 2×CD) | `The Young Gods/[2012] The Young Gods (Deluxe Edition) [DCD flac-lossless-44s]` |
| Front 242 — Masterhit (digital FLAC) | `Front 242/[1992] Masterhit [11xfile flac-lossless-44s]` |
| Front 242 — Masterhit (limited CD single) | `Front 242/[1992] Masterhit [LCDS flac-lossless-44s]` |

### Digital releases — `%trackcount%x` prefix

For `File` and `Web` format releases, `%format_code%` gives `file`/`web`.
Prefix with `%trackcount%x` to show the number of tracks:

```
$if1($inarray('["File","Web"]','%format%'),'%trackcount%x','')%format_code%
```

Produces `10xfile` for a 10-track album, `web` for a single-track web release.

---

## Metadata field mapping

This section documents every metadata tag written by discogstagger3, its
source in the Discogs API, its data type, and whether the field is native to
the mediafile library or a custom extension added by this project.

It also lists Discogs API fields and MediaFile fields that are **not** currently
used, so the mapping can be extended to other metadata sources in the future.

### Data type notation

| Notation | Meaning |
|---|---|
| `string` | Single text value |
| `integer` | Whole number |
| `boolean` | `True` / `False` |
| `array[string]` | Multiple separate tag entries (e.g. two `GENRE=` Vorbis comments in FLAC) |
| `binary` | Raw bytes (cover art image) |

`array[string]` fields are stored as genuinely separate entries in container
formats that support it (FLAC/Vorbis, MP4 atoms, ASF).  In ID3v2 (MP3) they
are stored as a single null-separated value inside one frame.  How a player
*displays* multiple values (e.g. joined with `//`) is a player convention, not
part of the tag format.

### Native vs. custom

| Status | Meaning |
|---|---|
| **Native** | Defined in the `mediafile` library.  Portable across any tagger that uses mediafile. |
| **Custom** | Added by discogstagger3 via `MediaFile.add_field()` in `mediafile_ext.py`.  Other applications must know the underlying tag name to read them. |

---

### Tags written by discogstagger3

#### Album-level

| MediaFile attribute | Discogs API source | Description | Type | Status |
|---|---|---|---|---|
| `album` | `release.title` | Album title | string | Native |
| `albumartist` | `release.artists` — combined with Discogs join text (e.g. `Feat.`, `&`); falls back to `join_artists` config or first artist | Album artist as a single display string | string | Native |
| `albumartists` | `release.artists` — individual canonical names | Album artist names as separate entries for sorting and filtering | array[string] | Native |
| `albumartist_sort` | `release.artists[0].name` — first artist's raw name (disambiguation suffix stripped) | Sort key for the album artist | string | Native |
| `composer` | Same value as `albumartist` | Album artist written to the composer field — allows players that use composer for sorting to work correctly | string | Native |
| `year` | `release.year` | Release year (four-digit integer) | integer | Native |
| `label` | `release.labels[0].name` (first label, disambiguation suffix stripped) | Record label | string | Native |
| `catalognum` | `release.labels[].catno` — first non-empty, non-`none` catalogue number after deduplication | Primary catalogue number | string | Native |
| `country` | `release.country` | Country of release | string | Native |
| `genres` | `release.genres` | Genre(s) | array[string] | Native |
| `grouping` | `release.styles` — joined with `, ` | Discogs style tags stored in the grouping field | string | Native |
| `media` | `release.formats[].qty` + `name` + `descriptions` joined | Full media description string (e.g. `1 x CD Album`) | string | Native |
| `comments` | `release.notes` and/or `tracklist[n].notes` | Release-level and track-level notes | string | Native |
| `disc` | Parsed from tracklist position (e.g. `2-03` → disc `2`) | Disc number within the release | integer | Native |
| `disctotal` | Count of distinct disc numbers across the tracklist | Total number of discs | integer | Native |
| `disctitle` | Tracklist heading immediately preceding the tracks on a disc | Disc subtitle (e.g. `Live Bonus Disc`) | string | Native |
| `comp` | Set to `True` when `release.artists[0].name == "Various"` and release is flagged as compilation | Compilation flag | boolean | Native |
| `discogs_id` | `release.id` | Discogs numeric release ID | string | **Custom** |
| `discogs_release_url` | Constructed: `http://www.discogs.com/release/{id}` | Full Discogs release URL | string | **Custom** |

#### Track-level

| MediaFile attribute | Discogs API source | Description | Type | Status |
|---|---|---|---|---|
| `title` | `release.tracklist[n].title` | Track title | string | Native |
| `artist` | `release.tracklist[n].artists` — combined with join text; inherits album artist display for tracks without individual credits | Track artist as a single display string | string | Native |
| `artists` | `release.tracklist[n].artists` — individual canonical names; inherits album artists list for tracks without individual credits | Track artist names as separate entries | array[string] | Native |
| `artist_sort` | `release.tracklist[n].artists[0].name` (raw, disambiguation stripped); inherits album sort artist when no track-level credits | Sort key for the track artist | string | Native |
| `track` | Parsed from tracklist position; `real_tracknumber` used for sub-tracks | Track number | integer | Native |
| `tracktotal` | Count of tracks on the disc | Total tracks on this disc | integer | Native |

#### Source identity (kept from existing file, not fetched from Discogs)

| MediaFile attribute | Source | Description | Type | Status |
|---|---|---|---|---|
| `freedb_id` | Preserved from the source audio file (configured via `keep_tags: freedb_id`) | FreeDB / CDDB disc ID embedded by a ripper | string | **Custom** |

#### Added by the ReplayGain step (post-tagging, not from Discogs)

| MediaFile attribute | Source | Description | Type | Status |
|---|---|---|---|---|
| `r128_album_gain` | `r128gain` / `loudgain` | EBU R128 album loudness offset (stored as integer: gain in LU × 256) | integer | Native |
| `r128_track_gain` | `r128gain` / `loudgain` | EBU R128 track loudness offset | integer | Native |
| `rg_album_gain` | `metaflac` / `loudgain` | ReplayGain v1 album gain in dB | float | Native |
| `rg_album_peak` | `metaflac` / `loudgain` | ReplayGain v1 album peak amplitude | float | Native |
| `rg_track_gain` | `metaflac` / `loudgain` | ReplayGain v1 track gain in dB | float | Native |
| `rg_track_peak` | `metaflac` / `loudgain` | ReplayGain v1 track peak amplitude | float | Native |

#### User-configurable extras (from `[tags]` in config)

Any MediaFile attribute can be written to every file by adding it to the
`tags` section of your config.  The only shipped default is:

| MediaFile attribute | Config key | Description | Type | Status |
|---|---|---|---|---|
| `encoder` | `tags.encoder` | Encoding application string (empty by default) | string | Native |

---

### Underlying tag names by format

The same MediaFile attribute maps to different raw tag names depending on the
audio format.  The custom fields (`discogs_id`, `discogs_release_url`,
`freedb_id`, `amg_id`) use widely-adopted conventions for storing Discogs
metadata but are not part of any formal standard.

| MediaFile attribute | FLAC / Vorbis | MP3 / ID3v2 | MP4 / M4A | ASF / WMA |
|---|---|---|---|---|
| `album` | `ALBUM` | `TALB` | `©alb` | `WM/AlbumTitle` |
| `albumartist` | `ALBUMARTIST` | `TPE2` | `aART` | `WM/AlbumArtist` |
| `albumartists` | `ALBUMARTISTS` (multi) | `TXXX:Artists` | `----:com.apple.iTunes:ARTISTS` | `WM/AlbumArtists` |
| `albumartist_sort` | `ALBUMARTISTSORT` | `TSO2` | `soaa` | `WM/AlbumArtistSortOrder` |
| `artist` | `ARTIST` | `TPE1` | `©ART` | `Author` |
| `artists` | `ARTISTS` (multi) | `TXXX:Artists` | `----:com.apple.iTunes:ARTISTS` | `WM/Artists` |
| `artist_sort` | `ARTISTSORT` | `TSOP` | `soar` | `WM/ArtistSortOrder` |
| `composer` | `COMPOSER` | `TCOM` | `©wrt` | `WM/Composer` |
| `title` | `TITLE` | `TIT2` | `©nam` | `Title` |
| `year` | `DATE` | `TDRC` | `©day` | `WM/Year` |
| `label` | `LABEL` | `TPUB` | `----:com.apple.iTunes:LABEL` | `WM/Publisher` |
| `catalognum` | `CATALOGNUMBER` | `TXXX:CATALOGNUMBER` | `----:com.apple.iTunes:CATALOGNUMBER` | `WM/CatalogNo` |
| `country` | `RELEASECOUNTRY` | `TXXX:MusicBrainz Album Release Country` | `----:com.apple.iTunes:MusicBrainz Album Release Country` | `MusicBrainz/Album Release Country` |
| `genres` | `GENRE` (multi) | `TCON` | `©gen` | `WM/Genre` |
| `grouping` | `GROUPING` | `TIT1` | `©grp` | `WM/ContentGroupDescription` |
| `media` | `MEDIA` | `TMED` | `----:com.apple.iTunes:MEDIA` | `WM/Media` |
| `comments` | `COMMENT` | `COMM:eng` | `©cmt` | `WM/Description` |
| `disc` | `DISCNUMBER` | `TPOS` | `disk` | `WM/PartOfSet` |
| `disctotal` | `DISCTOTAL` | `TPOS` (as `n/total`) | `disk` (as `n/total`) | `WM/PartOfSet` |
| `disctitle` | `DISCSUBTITLE` | `TSST` | `----:com.apple.iTunes:DISCSUBTITLE` | `WM/SetSubTitle` |
| `track` | `TRACKNUMBER` | `TRCK` | `trkn` | `WM/TrackNumber` |
| `tracktotal` | `TRACKTOTAL` | `TRCK` (as `n/total`) | `trkn` (as `n/total`) | `WM/TrackNumber` |
| `comp` | `COMPILATION` | `TCMP` | `cpil` | `WM/IsCompilation` |
| `encoder` | `ENCODER` | `TENC` | `©too` | `WM/EncodedBy` |
| `r128_album_gain` | `R128_ALBUM_GAIN` | `TXXX:R128_ALBUM_GAIN` | `----:com.apple.iTunes:R128_ALBUM_GAIN` | `R128_ALBUM_GAIN` |
| `r128_track_gain` | `R128_TRACK_GAIN` | `TXXX:R128_TRACK_GAIN` | `----:com.apple.iTunes:R128_TRACK_GAIN` | `R128_TRACK_GAIN` |
| `rg_album_gain` | `REPLAYGAIN_ALBUM_GAIN` | `TXXX:REPLAYGAIN_ALBUM_GAIN` | `----:com.apple.iTunes:REPLAYGAIN_ALBUM_GAIN` | `REPLAYGAIN_ALBUM_GAIN` |
| `rg_track_gain` | `REPLAYGAIN_TRACK_GAIN` | `TXXX:REPLAYGAIN_TRACK_GAIN` | `----:com.apple.iTunes:REPLAYGAIN_TRACK_GAIN` | `REPLAYGAIN_TRACK_GAIN` |
| `discogs_id` | `DISCOGSID` | `TXXX:DiscogsReleaseId` | `----:com.apple.iTunes:DISCOGS_RELEASE_ID` | `DT/Release Id` |
| `discogs_release_url` | `URL_DISCOGS_RELEASE_SITE` | `TXXX:DISCOGS_RELEASE_URL` | `----:com.apple.iTunes:DISCOGS_RELEASE_URL` | `WM/DiscogsReleaseUrl` |
| `freedb_id` | `DISCID` | `TXXX:DiscId` | `----:com.apple.iTunes:DISCID` | `DT/discid` |
| `amg_id` | `AMGID` | `TXXX:AMGID` | `----:com.apple.iTunes:AMG_ID` | `DT/AmgId` |

---

### Unused Discogs API fields

These fields are available in every Discogs release response but are not
currently written to file metadata.  They are available to format strings for
naming purposes where noted.

| Discogs API field | API path | Notes |
|---|---|---|
| Release URL slug | `release.uri` | Decorative — the numeric ID (`discogs_id`) is more stable |
| Master release ID | `release.master_id` | Available internally as `album.master_id`; not written as a tag |
| Master release URL | `release.master_url` | Not used |
| Barcode(s) | `release.identifiers[].value` where `type == "Barcode"` | Not extracted or written |
| Matrix / runout | `release.identifiers[].value` where `type == "Matrix / Runout"` | Not extracted |
| Other identifiers | `release.identifiers[]` (ASIN, Rights Society, etc.) | Not extracted |
| Format text | `release.formats[].text` | Free-text description of the pressing; not written |
| Format quantity | `release.formats[].qty` | Partially used in `%format_code%`; not a standalone tag |
| Data quality | `release.data_quality` | Editorial quality flag; not written |
| Status | `release.status` | `Official`, `Promo`, etc.; not written |
| Community rating | `release.community.rating` | Not written |
| Community have/want | `release.community.have` / `want` | Not written |
| Date added | `release.date_added` | Not written |
| Date changed | `release.date_changed` | Not written |
| Track duration | `release.tracklist[n].duration` | Used internally for release matching; not written as a tag |
| Track position (raw) | `release.tracklist[n].position` | Parsed into `disc` and `track` numbers; raw string not written |
| ANV (artist name variation) | `release.artists[n].anv` | The name as printed on the release sleeve; currently `x.name` (canonical) is used instead |
| Artist role | `release.artists[n].role` | Not used |
| Artist tracks | `release.artists[n].tracks` | Partial credits; not used |
| Track artist ANV | `release.tracklist[n].artists[n].anv` | Track artist as printed; canonical name used instead |

---

### Unused MediaFile fields

These MediaFile attributes exist in the library but are not written by
discogstagger3.  Discogs does not provide the data for most of them; those
where Discogs data does exist are noted.

| MediaFile attribute | Type | Status | Why unused / notes |
|---|---|---|---|
| `date` | string (`YYYY-MM-DD`) | Native | Discogs provides year only; `year` (integer) is written instead |
| `original_date` | string | Native | Not in Discogs API |
| `original_year` | integer | Native | Not in Discogs API |
| `mb_albumid` | string | Native | MusicBrainz album ID; not in Discogs API |
| `mb_artistid` | string | Native | MusicBrainz artist ID; not in Discogs API |
| `mb_albumartistid` | string | Native | MusicBrainz album artist ID; not in Discogs API |
| `mb_trackid` | string | Native | MusicBrainz track ID; not in Discogs API |
| `mb_releasetrackid` | string | Native | MusicBrainz release track ID; not in Discogs API |
| `mb_releasegroupid` | string | Native | MusicBrainz release group ID; not in Discogs API |
| `mb_workid` | string | Native | MusicBrainz work ID; not in Discogs API |
| `mb_albumartistids` | array[string] | Native | MusicBrainz album artist IDs; not in Discogs API |
| `mb_artistids` | array[string] | Native | MusicBrainz artist IDs; not in Discogs API |
| `bpm` | integer | Native | Not in Discogs API |
| `isrc` | string | Native | Available in `release.tracklist[n].identifiers` for some releases; not extracted |
| `asin` | string | Native | Available in `release.identifiers` for some releases; not extracted |
| `barcode` | string | Native | Available in `release.identifiers`; not extracted |
| `script` | string | Native | `release.formats[].text` sometimes contains script info; not extracted |
| `language` | string | Native | Not in Discogs API |
| `languages` | array[string] | Native | Not in Discogs API |
| `initial_key` | string | Native | Not in Discogs API |
| `lyrics` | string | Native | Not in Discogs API |
| `synced_lyrics` | string | Native | Not in Discogs API |
| `albumdisambig` | string | Native | Not in Discogs API |
| `albumstatus` | string | Native | Discogs `release.status` (`Official`, `Promo`, etc.) exists but is not written |
| `albumtype` | string | Native | Not in Discogs API in this form |
| `albumtypes` | array[string] | Native | Not in Discogs API in this form |
| `subtitle` | string | Native | Not in Discogs API |
| `copyright` | string | Native | Not in Discogs API |
| `arranger` | string | Native | Not in Discogs API at release level |
| `arrangers` | array[string] | Native | Not in Discogs API at release level |
| `lyricist` | string | Native | Not in Discogs API at release level |
| `lyricists` | array[string] | Native | Not in Discogs API at release level |
| `remixers` | array[string] | Native | Remix credits are embedded in track titles on Discogs, not as a structured field |
| `composer_sort` | string | Native | Discogs does not provide a sort name for composer |
| `composers` | array[string] | Native | Discogs does not provide composer credits as a structured field |
| `artist_credit` | string | Native | Discogs `artists[n].anv` is the equivalent but is not currently used |
| `albumartist_credit` | string | Native | Discogs `artists[n].anv` is the equivalent but is not currently used |
| `catalognums` | array[string] | Native | Multiple catalogue numbers exist (`album.catnumbers`); only the first is written to `catalognum` |
| `url` | string | Native | Generic URL field; `discogs_release_url` is used instead (custom field with Discogs-specific tag names) |
| `images` | binary | Native | Cover art is embedded via a separate image-writing path, not via `metadata.images` |

---

## Links

- [Foobar2000 Title Formatting Reference](http://wiki.hydrogenaud.io/index.php?title=Foobar2000:Title_Formatting_Reference)
- [Tag Mapping — Hydrogen Audio](https://wiki.hydrogenaud.io/index.php?title=Tag_Mapping)
- [Discogs API — release formats](https://www.discogs.com/developers/#page:database,header:database-search)
- [`conf/format_codes.yaml`](../conf/format_codes.yaml) — format code rules
- [`conf/char_substitutions.yaml`](../conf/char_substitutions.yaml) — character substitution profiles
