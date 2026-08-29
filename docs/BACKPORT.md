# Fixes to bring back from massMusicTagger

massMusicTagger 3.x absorbed discogstagger3's tagging core and has since had a
long defect-hunting pass over it. Much of what that found is in code the two
projects still share, line for line, because it was copied rather than
rewritten.

This is the list, checked against this repository rather than assumed. Each
entry says what is wrong here, how it shows up, and what massMusicTagger did
about it. Nothing in this file changes discogstagger3 — it is a work list.

The through-line is worth naming, because it is the same fault every time:
**something fails and says nothing.** A path that does not resolve, a token
that is never checked, a value that is trusted. In each case the run completes
and looks successful, and the damage is only visible in the output.

---

## 1. Album metadata can execute code — `stringformatting.py`

**Confirmed reachable.** `$inarray` and `$flatten` both parse a list, both try
`json.loads` first, and both fall back to `eval()` on the value:

```python
# stringformatting.py:139 and :180
lst = eval(re.sub(r'\\', '', raw))
```

Both functions are meant to be pointed at metadata, which is the whole point
of them:

```
$if1($inarray('%album%','Box Set'),'B','')
```

So an album titled `__import__('sys').modules.setdefault('X',1) or []`
executes that code during tagging. Demonstrated against this repository,
through `_value_from_tag_format`'s real escaping — the `\x27` and U+E024
substitutions do not prevent it, because the value is unescaped again by the
time `$inarray` receives it.

Discogs titles are editable by anyone with an account, and the release being
tagged is chosen by matching against them.

**Fix:** `ast.literal_eval`. It reads the same literals — JSON arrays and
`['a','b']` alike — and cannot call anything. Roughly ten lines, no behaviour
change for any well-formed value.

This one is worth doing on its own, ahead of everything else here.

---

## 2. `eval()` evaluates the whole format string — `stringformatting.py:452`

```python
string = re.sub(r'\$', 'self.', string)
result = eval(string)
```

Nesting works because Python's parser does it. The cost is that metadata is
spliced into Python source, so every character meaningful to Python must be
neutralised first — hence `'` becoming `\x27` and `$` becoming a private-use
codepoint. The backslash is not handled at all, so an album called `AC\`
closes the string literal it was interpolated into and raises `SyntaxError`:
that album cannot be tagged.

**Fix:** massMusicTagger replaced it with `naming/formatparser.py`, a
recursive-descent parser over the same dialect. Two contexts is the whole
grammar: text is literal with `$name(` and `%name%` embedded; an argument list
is an expression where terms concatenate. Values are resolved at evaluation
time from a mapping, so they are never parsed and never need escaping.

Verified byte-identical against 50 dialect cases covering all 25 functions and
70 renderings of a real `formats.ini`. Both corpora are in massMusicTagger's
`test/fixtures/` and port directly.

Larger than item 1 and not urgent once that is done — but it removes the whole
class, and it deletes the three escaping hacks with it.

---

## 3. A missing rule table switches the feature off — `formatcodes.py`

```python
except FileNotFoundError:
    logger.debug('Format codes file not found: %s', path)
    return {}
```

`config.yaml` shipped with `format_codes: conf/format_codes.yaml`, a path that
only resolves from a source checkout. In a container it resolves to nothing,
the rule table comes back empty, and every format abbreviation switches off:
a release on Digital Media is filed as **`Digital Media`** rather than `DM`.

Reported from a live discogstagger3 deployment; that is how this was found.

**Fix, in the order that matters:**

1. Fall back to the packaged table when a named file is missing, and warn.
   Naming a file that is not there is a mistake worth hearing about.
2. Find `format_codes.yaml` beside `config.yaml` by name, as `formats.ini`
   already is, and deprecate the path key. The table decides how a release is
   named, so it belongs where its owner can read it.
3. Merge a user table over the packaged one rather than replacing it —
   otherwise overriding a single abbreviation discards `vinyl_sizes` and the
   quantity rules with it, and later additions never reach anyone who has
   overridden a line.

The same shape appears in `char_substitutions` in massMusicTagger, where it
left `char_profile: windows` inert across a whole library. This repository
does not have that variant.

---

## 4. The Discogs token is never checked — `discogs_connector.py:61`

```python
logger.info('Authenticated via personal access token')
```

Logged because the string is non-empty. Discogs issues **one personal token
per account**, so generating one for a second application silently invalidates
the first — and with a warm disk cache an entire run completes while every
live call is being refused.

**Fix:** call `identity()` once at startup. A refused credential is fatal and
the message explains the one-token rule; a network failure is not fatal, since
an offline run against a warm cache is legitimate. Distinguish them by status
code — the client raises the same exception type for 401 and 503.

---

## 5. A missing release year becomes 1900 — `discogsalbum.py:261`

```python
return "1900"
```

A release with no year is filed under `[1900]`, which sorts wrongly and reads
as a real date.

**Fix:** return `None` and let the format string omit the bracket. Then take
the year from the release's **master** when it has one: 16.5% of releases in a
23,102-release sample carry no year, and 99.6% of those belong to a master
that does.

Read `master.year`, not `master.data['year']` — the client is lazy, and
`.data` on an unfetched object is an empty stub that yields `None` in silence.

---

## 6. `id.txt` leaks between directories — `fileutils.py:94`

```python
self.config.read(idfile)
```

Each album's `id.txt` is merged into the shared run configuration, so a value
set for one directory is still set for the next.

**Fix:** parse it with its own `RawConfigParser` and return `(source, id)`.
While there: read the ID as `<name>_id` directly rather than through the
`source.<name>` mapping in the main config, so a file can name a source
without anything being declared first.

---

## 7. Scanning converts — `fileutils.py`, `get_audio_dirs`

> *Returns a list of directories with audio track to be processed.
> Any CUE files encountered will be split automatically*

The function that lists directories also splits CUE sheets and transcodes
`.m4a`. discogstagger3 has no `--dry-run`, so the acute symptom massMusicTagger
had — a dry run rewriting the files it was reporting on — does not exist here.
The structural cost still does: a conversion failure removes the directory from
the results, so a broken CUE sheet surfaces as *"No audio source directories
found"* rather than as a conversion failure.

**Fix:** `scan()` returns the directories and a list of the work they need;
`prepare()` does that work and reports what succeeded. One broken album then
stops being able to take the batch with it.

Also worth taking: a single-file album with two cue sheets — `album.cue`
beside `album.flac.cue`, or `album FLAC.CUE` beside `album WAV.CUE` — is never
split, because the sheets outnumber the audio and the test for a single-file
rip is that the counts match. Group sheets by the album they name, ignoring any
trailing format word.

---

## Not applicable here

Checked and confirmed absent from this repository, so they need no work:

| From massMusicTagger | Why it does not apply |
|---|---|
| `glob.escape` on the credentials directory | discogstagger3 does not glob for credentials |
| `char_substitutions` falling back | not present in this variant |
| Case-insensitive local cover names | the typed-image path is massMusicTagger's |
| `--dry-run` rewriting the source | no `--dry-run` flag |
| The 97%-false-positive bad-match warning | not present |
| Cover Art Archive handling | Discogs-only here |

---

## The lesson, rather than the list

Every defect above was found by running the tool and looking at the output, or
by measuring a claim against real data — not by reading the code. Three
specific habits paid for themselves:

**Mocked filesystems hide filesystem bugs.** massMusicTagger's image tests used
a fake target directory and a connector that wrote nothing, asserting on what
it was *asked* to do. Rewriting them against a real directory surfaced three
defects immediately.

**Measure before believing a comment.** A warning documented as "a reliable
indicator that a wrong release was matched" fired on 371 of 379 albums. A note
claiming 48% of sub-track entries fell through a rule turned out to be 12%, and
the fix it proposed did not discriminate at all. Both were settled in minutes
by counting.

**Falling back beats switching off, and silence is the enemy.** Items 3, 4 and
5 are the same bug wearing different clothes: something is missing, the code
copes, and nobody is told. A warning naming what was expected and what was used
instead would have caught all three the first time anyone ran the tool.
