# Plan: Granular case control for generated filenames

## Context

`use_lower_filenames` is a blunt single flag that lowercases every generated
path (directory names, disc folder names, track filenames, .nfo, .m3u).  A
GitHub issue requests per-format granularity; the user also wants to support
uppercase as well as lowercase.  The existing flag will be kept as a
deprecated alias so no existing configs break.

---

## Design

Six per-format config keys, each accepting `lower`, `upper`, or `preserve`:

```yaml
details:
  case_dir:     lower   # album directory path segments
  case_disc:    lower   # disc subfolder names (multi-disc releases)
  case_song:    lower   # single-artist track filenames
  case_va_song: lower   # various-artists track filenames
  case_nfo:     lower   # .nfo filename
  case_m3u:     lower   # .m3u filename

  # Deprecated — use the per-format keys above instead.
  # use_lower_filenames: true   # true → forces all six to 'lower'
  #                             # false → forces all six to 'preserve'
```

Defaults of `lower` preserve current behaviour (config.yaml currently has
`use_lower_filenames: true`).

---

## Structural fix required first

`_value_from_tag()` (line 868) currently calls `get_clean_filename()` at
line 876.  Every caller *also* calls `get_clean_filename()`, so case is
applied twice for dir segments, song names, m3u, and nfo.  The disc folder
is the exception — cleaned only once (inside `_value_from_tag`) with no
second call.

**Fix:** Remove the `get_clean_filename()` call from inside `_value_from_tag()`
(line 876).  Make `_value_from_tag()` a pure "evaluate format string"
function.  All callers already invoke `get_clean_filename()` on the result,
so behaviour is preserved after this removal — except for the disc folder
(`disc.target_dir`), which must get an explicit call added.

---

## Implementation steps

### 1. `conf/config.yaml`
- Add the six `case_*` keys under `[details]`, each defaulting to `lower`.
- Keep `use_lower_filenames` commented out with a deprecation note.

### 2. `discogstagger/taggerutils.py`

**`TaggerUtils.__init__`** (around line 645):
- Remove `self.use_lower = self.config.getboolean(...)`.
- Read each of the six keys with a `get()` fallback to `'lower'`:
  ```python
  self.case_dir     = self.config.get('details', 'case_dir')     or 'lower'
  self.case_disc    = self.config.get('details', 'case_disc')    or 'lower'
  self.case_song    = self.config.get('details', 'case_song')    or 'lower'
  self.case_va_song = self.config.get('details', 'case_va_song') or 'lower'
  self.case_nfo     = self.config.get('details', 'case_nfo')     or 'lower'
  self.case_m3u     = self.config.get('details', 'case_m3u')     or 'lower'
  ```
- Deprecated alias: if `use_lower_filenames` is present in config, log a
  deprecation warning and override all six to `lower` (true) or `preserve`
  (false).

**`_value_from_tag()`** (line 876):
- Remove the line `format = self.get_clean_filename(format)`.
- The method becomes a pure format-string evaluator.

**`get_clean_filename()`** (line 1178):
- Add a `case='preserve'` parameter.
- Replace the `if self.use_lower: cf = cf.lower()` block with:
  ```python
  if case == 'lower':
      cf = cf.lower()
  elif case == 'upper':
      cf = cf.upper()
  ```
- Remove `self.use_lower` from the method.

**Call sites — update each to pass the appropriate `case=` argument:**

| Call site | Line | New call |
|---|---|---|
| `dest_dir_name` — dir segments | ~1151 | `get_clean_filename(…, case=self.case_dir)` |
| `_set_target_discs_and_tracks` — disc folder | ~894–895 | add `get_clean_filename(target_dir, case=self.case_disc)` before assignment |
| `_set_target_discs_and_tracks` — song | ~906 | `get_clean_filename(newfile, case=self.case_song)` |
| `_set_target_discs_and_tracks` — va_song | ~900 | `get_clean_filename(newfile, case=self.case_va_song)` |
| `m3u_filename` | ~1168 | `get_clean_filename(m3u, case=self.case_m3u)` |
| `nfo_filename` | ~1175 | `get_clean_filename(nfo, case=self.case_nfo)` |

Note: song and va_song are currently produced by the same `_value_from_tag`
call (one or the other is chosen via `if … else`).  The case arg passed to
the single trailing `get_clean_filename` call at line 906 needs to reflect
which format was used.  Easiest fix: store a local `case_to_use` variable
before the if/else and set it to `self.case_song` or `self.case_va_song`
inside each branch, then pass it to the final `get_clean_filename`.

### 3. `conf/config_personal.yaml`
- Remove `use_lower_filenames: false`.
- Add the six keys with `preserve` values (since the user keeps original
  casing throughout).

### 4. `docs/tagging_reference.md` (Character substitution section)
- Update the documentation to mention the new per-format case keys and
  their allowed values.

---

## Backward compatibility

| Old config | New behaviour |
|---|---|
| `use_lower_filenames: true` | All six forced to `lower`; deprecation warning logged |
| `use_lower_filenames: false` | All six forced to `preserve`; deprecation warning logged |
| Key absent | Six per-format keys control case independently |

---

## Files to modify
- `conf/config.yaml`
- `conf/config_personal.yaml`
- `discogstagger/taggerutils.py`
- `docs/tagging_reference.md`

## Verification
- Run `pytest test/ -q` — all 181 tests should pass.
- Spot-check: tag a release with `case_dir: upper` and `case_song: lower`
  and verify directory names are uppercased while track filenames are
  lowercase.
- Verify deprecated alias: add `use_lower_filenames: false` to a test
  config and confirm deprecation warning appears and all six default to
  `preserve`.
