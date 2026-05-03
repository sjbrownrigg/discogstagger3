# Tagging format string reference

Format strings use Foobar2000-style `%variable%` placeholders and `$function()`
calls. See the
[Foobar2000 Title Formatting Reference](http://wiki.hydrogenaud.io/index.php?title=Foobar2000:Title_Formatting_Reference)
for the general syntax.

---

## Available variables

### Album-level

| Variable | Description |
|---|---|
| `%album artist%` / `%albumartist%` | Album artist (consistent across the whole release) |
| `%album%` | Album title |
| `%year%` | Release year |
| `%catno%` | Catalogue number(s), joined with `, ` if there are multiple |
| `%totaldiscs%` | Total number of discs |
| `%trackcount%` | Total number of tracks across all discs (from Discogs data) |
| `%discnumber%` | Disc number |
| `%disctitle%` | Disc subtitle (e.g. "Live Bonus Disc") |
| `%format%` | Release format (e.g. `CD`, `Vinyl`, `File`) |
| `%format_description%` | Format descriptions as a JSON list (e.g. `["Album", "Limited Edition"]`) |
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
| `%quality%` | Release-level quality assessment: `lossless`, `vbr`, or a CBR bitrate in kbps (e.g. `320`, `192`). Computed by examining all tracks — VBR is detected when bitrates vary by more than 5 kbps across tracks. |

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

## Available functions

| Function | Arguments | Description |
|---|---|---|
| `$if1(cond, a, b)` | condition, then, else | Returns `a` when `cond` is truthy, else `b` |
| `$if2(x, fallback)` | value, fallback | Returns `x` if `x` is non-empty, else `fallback` — null-coalescing; `x` serves as both condition and value |
| `$if3(a, b, c, …)` | any number of values | Returns the first non-empty value from the list |
| `$strcmp(s1, s2)` | two strings | Returns `True` if strings are equal |
| `$stricmp(s1, s2)` | two strings | Case-insensitive string comparison |
| `$ifequal(n1, n2, a, b)` | two integers, two values | Returns `a` if `n1 == n2`, else `b` |
| `$ifgreater(n1, n2, a, b)` | two integers, two values | Returns `a` if `n1 > n2`, else `b` |
| `$inarray(list, item)` | JSON list string, item | Returns `True` if `item` is in the list |
| `$lower(s)` | string | Lowercase |
| `$upper(s)` | string | Uppercase |
| `$num(n, places)` | number, width | Zero-pad number to `places` digits |
| `$substr(s, start, end)` | string, int, int | Substring — Python slice semantics |
| `$strchr(s, char)` | string, char | Position of first occurrence of `char` |

### String concatenation in function arguments

Function arguments support Python string concatenation with `+`, which lets
you combine literal text with function results inside a single branch:

```
$if1($inarray('["File","Web"]','%format%'),'%trackcount%x'+$lower('%format%'),'%format%')
```

Produces `10xfile` for a digital release and `CD` (unchanged) for a CD.

---

## Character exceptions

Special characters are replaced during filename generation via `[character_exceptions]`
in the config file:

```ini
[character_exceptions]
&=_and_
ö=oe
.=_
# Uncomment to replace spaces with underscores:
#{space}=_
```

These replacements apply to filenames and directory names only — metadata
tags are not affected.

---

## Example format strings

Single-artist album:
```
dir=%albumartist%/[%year%] %album%
song=$num('%tracknumber%','2') %title%%fileext%
```

Various artists with conditional catalogue number:
```
dir=$if1($strcmp('%albumartist%','Various'),'Various Artists','%albumartist%')/[%year%] %album%$if1($strcmp('%catno%',''),'', ' (%catno%)')
song=$num('%tracknumber%','2') $if1($strcmp('%artist%','%albumartist%'),'','%artist% - ')%title%%fileext%
```

With codec and quality info in the directory name:
```
dir=%albumartist%/[%year%] %album% [$lower('%codec%') $ifequal(%bitdepth%,24,'24bit ','')$substr('%samplerate%','','-3')$if1($strcmp('%channels%','stereo'),'s','%channels%')]
```

---

## Links

- [Foobar2000 Title Formatting Reference](http://wiki.hydrogenaud.io/index.php?title=Foobar2000:Title_Formatting_Reference)
- [Tag Mapping — Hydrogen Audio](https://wiki.hydrogenaud.io/index.php?title=Tag_Mapping)
- [Discogs release format info](https://www.discogs.com/developers/)
