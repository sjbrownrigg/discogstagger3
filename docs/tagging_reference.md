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

---

## Variables

### Album-level

| Variable | Description |
|---|---|
| `%album artist%` / `%albumartist%` | Album artist (consistent across the whole release) |
| `%album%` | Album title |
| `%year%` | Release year |
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

## Links

- [Foobar2000 Title Formatting Reference](http://wiki.hydrogenaud.io/index.php?title=Foobar2000:Title_Formatting_Reference)
- [Tag Mapping — Hydrogen Audio](https://wiki.hydrogenaud.io/index.php?title=Tag_Mapping)
- [Discogs API — release formats](https://www.discogs.com/developers/#page:database,header:database-search)
- [`conf/format_codes.yaml`](../conf/format_codes.yaml) — format code rules
- [`conf/char_substitutions.yaml`](../conf/char_substitutions.yaml) — character substitution profiles
