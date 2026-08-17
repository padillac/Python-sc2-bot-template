# Ladder packaging

```bash
python create_ladder_zip.py
```

Produces `publish/<NAME>-<VERSION>.zip` — e.g. `publish/MyBot-0.1.0.zip` — ready to upload.

## What the script does

1. **Verify pins.** Every distribution in `DISTRIBUTIONS_TO_BUNDLE` is checked against its `==` pin
   in `requirements.txt`. Mismatch or missing pin aborts the build.
2. **Stage.** Copies `bot/` and `run.py` (plus anything in `EXTRA_INCLUDES`) into a temporary
   `.ladder_zip_staging/`.
3. **Bundle the SC2 library.** Copies `burnysc2`'s top-level packages — in practice `sc2/` — out of
   `site-packages` into the staging root.
4. **Patch the log level.** Rewrites the level in the staged copy of your bot module to
   `LADDER_LOG_LEVEL`.
5. **Zip**, skipping `__pycache__`, `.pyc`/`.pyo`/`.log` files, VCS and IDE directories, and
   anything in `EXCLUDED_DIRS`.
6. **Move** the archive into `publish/` and delete the staging directory.

Only the staged copy is ever modified. Your working tree is untouched.

## Why the SC2 library is bundled

The ladder's environment has its own python-sc2 install, which may be older or newer than yours.
Bundling `sc2/` at the zip root means the version that runs on the ladder is byte-identical to the
one you developed and tested against. Since it comes out of `site-packages` rather than a vendored
copy in the repo, it can't silently drift from your pin.

## Resulting layout

```
MyBot-0.1.0.zip
├── run.py
├── bot/
│   ├── MyBot.py
│   ├── __init__.py
│   └── ...
└── sc2/               <- the pinned burnysc2 library
```

Note that everything is at the **root** of the archive, not nested inside a folder. Ladders expect
the entry point to be at the top level after extraction.

## Configuration

At the top of `create_ladder_zip.py`:

| Setting | Purpose |
|---|---|
| `BOT_PACKAGE` | Directory holding your bot module (`"bot"`) |
| `BOT_MODULE` | Module filename without `.py`, and the class name inside it (`"MyBot"`) |
| `ENTRY_POINT` | Script the ladder invokes (`"run.py"`) |
| `EXTRA_INCLUDES` | Extra repo files/dirs to bundle — data files, configs, trained models |
| `DISTRIBUTIONS_TO_BUNDLE` | Pip distributions to copy from site-packages. Each needs an `==` pin in `requirements.txt`. |
| `LADDER_LOG_LEVEL` | Log level forced into the ladder build |
| `EXCLUDED_DIRS` | Directories never walked into. Add dev-only dirs here. |

If your bot grows a dependency the ladder environment doesn't provide, add it to `requirements.txt`
with an `==` pin **and** to `DISTRIBUTIONS_TO_BUNDLE`.

## Three couplings that will break the build

1. **`BOT_MODULE` must equal both the module filename and the class name inside it.** The script
   does `importlib.import_module(f"{BOT_PACKAGE}.{BOT_MODULE}")` then `getattr(module, BOT_MODULE)`.
   Rename the file without renaming the class and it fails at import.
2. **Your bot module must contain a literal `logger.add(sys.stdout, level="...")` line.** The log
   level patch is a regex over the source. If the line is gone or reformatted, the build raises
   rather than shipping an unpatched build.
3. **`NAME` and `VERSION` on the class determine the zip filename.** Forgetting to bump `VERSION`
   means overwriting the previous package.

## Pin enforcement

`requirements.txt` pins are checked in two places:

- **`create_ladder_zip.py`** at build time, before anything is staged — so a stale local install
  can't ship.
- **`run.py`** at startup, before any third-party import — so a bad install fails with a clear
  message instead of a confusing `ImportError` later.

`run.py`'s check is skipped when `requirements.txt` isn't found next to it, which is the case inside
the ladder zip (the file isn't bundled). That's intentional: the ladder manages its own environment.

To verify a build, list the archive:

```bash
python -c "import zipfile; print('\n'.join(zipfile.ZipFile('publish/MyBot-0.1.0.zip').namelist()))"
```

## AI Arena

Facts worth knowing before your first upload, from the
[AI Arena bot development wiki](https://aiarena.net/wiki/bot-development/getting-started/):

- **Maximum zip size is 50 MB.** The template's zip is small (the bundled `sc2/` library dominates),
  but trained models or replay data can push you over.
- **The entry point must be at the root of the zip**, not inside a folder. This script already does
  that.
- **Select bot type `python`** when creating the bot on the site, along with the correct race.
- **A `./data` directory persists between games**, and its contents can be downloaded from your
  bot's profile page. This is the supported route for anything you want to survive a match —
  opponent notes, tuning state, accumulated stats. If you use it, add `data` to `EXTRA_INCLUDES`.

The wiki is the authoritative source and changes over time; check it rather than trusting this list
if something doesn't match.
