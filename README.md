# Python-SC2 Starter Template

A clean, functional starting point for a StarCraft II bot written in Python with
[python-sc2](https://github.com/BurnySc2/python-sc2).

It gives you the infrastructure that is the same for every Python bot and annoying to get right the first time:

- **A game runner** (`run.py`) that already handles all three ways you'll run a bot — against the
  built-in AI, against yourself, and on a competitive ladder.
- **A ladder packager** (`create_ladder_zip.py`) that builds an upload-ready zip with the SC2
  library bundled at the exact version you developed against.
- **Version pinning that is actually enforced**, so "works on my machine, crashes on the ladder"
  stops being a category of bug.
- **A few runtime utilities** that solve real python-sc2 gotchas (see [docs/utilities.md](docs/utilities.md)).

**This is not a bot.** `bot/MyBot.py` starts a game, sets up its helpers, and does nothing else.
There are no build orders, no managers, no strategy, and no opinion about how you should structure
yours. That part is yours.

---

## Prerequisites

- **[Python](https://www.python.org/downloads/) 3.9 – 3.14** (required by the pinned `burnysc2`)
- **[Git](https://git-scm.com/downloads)**
- **[StarCraft II](https://battle.net/account/download/)** — the free version is fine

### Installing StarCraft II

- **Windows**: install through the Battle.net app.
- **Linux**: either the
  [Blizzard SC2 Linux package](https://github.com/Blizzard/s2client-proto#linux-packages),
  or Battle.net under WINE via [Lutris](https://lutris.net/games/battlenet/).

### Maps

**You need to install maps before your first game.** SC2 does not ship the maps that bots play on,
and this template deliberately does not guess which ones you have.

**Use the maps AI Arena provides, and nothing else.** Those are the maps the ladder actually runs,
and they are the only ones explicitly built for the SC2 version that bots use.

1. **Download the current season's map pack** from the
   [AI Arena maps page](https://aiarena.net/wiki/maps/). Maps are published there as one zip per
   season; take the most recent one. If you want to confirm which pool is live right now, check the
   active competition under [aiarena.net/competitions](https://aiarena.net/competitions/). The competition page will also include direct map download links.

2. **Extract the `.SC2Map` files into the `Maps` folder inside your StarCraft II install
   directory.** Create the folder if it doesn't exist. Maps may be nested one directory deep.

   | OS | Default location |
   |---|---|
   | Windows | `C:\Program Files (x86)\StarCraft II\Maps` |
   | Linux | `~/StarCraftII/Maps` |

3. **Tell the runner which maps you installed** — open `run.py` and fill in `MAP_POOL`:

   ```python
   MAP_POOL = ["AcropolisAIE", "PylonAIE"]
   ```

   A map name is its filename without the `.SC2Map` extension. You can skip this and pass
   `--map <name>` on every run instead; the runner will tell you if it has nothing to pick from.

When a new season starts, the pool may change — download the new pack and update `MAP_POOL`.

---

## Quick start

1. **Create your repository** — click **Use this template** at the top of this page, then clone it.

   ```bash
   git clone <your-repository-url>
   cd <repository-name>
   ```

2. **Set up a virtual environment**

   ```bash
   # Windows
   python -m venv venv
   .\venv\Scripts\activate

   # Linux/Mac
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

4. **Install maps and set `MAP_POOL`** — see [Maps](#maps) above.

5. **Run it**

   ```bash
   python run.py
   ```

   StarCraft II will launch and your bot will sit there doing nothing. That is the correct result —
   you now have a working harness to build on.

---

## Running games

```bash
# Local test game vs the built-in AI (default mode)
python run.py
python run.py --map AcropolisAIE --difficulty Medium

# Play against your own bot
python run.py --human
python run.py --human --human-race Zerg

# Ladder game — the ladder passes these; you never type them
python run.py --GamePort 8765 --StartPort 8766
```

Full flag reference and behavior: **[docs/running-games.md](docs/running-games.md)**

---

## Making it yours

Three things carry your bot's identity, and they're coupled. Change them together:

1. Rename `bot/MyBot.py` and the `MyBot` class inside it. **The filename and the class name must
   match** — the packager imports the class by module path.
2. Update the import in `bot/__init__.py`.
3. Set `NAME`, `RACE`, and `VERSION` on the class.
4. Set `BOT_MODULE` in `create_ladder_zip.py` to the new module name.

Then write your bot. `on_step()` in your bot class runs every frame and is where everything
starts — see [docs/bot-structure.md](docs/bot-structure.md).

Keep all your code under `bot/`. That directory is what gets bundled into the ladder zip; anything
outside it will not exist on the ladder.

---

## What's in the box

| Path | What it is |
|---|---|
| `run.py` | Game runner. Launches local, human, and ladder games. Contains the local-game config block. |
| `create_ladder_zip.py` | Builds `publish/<NAME>-<VERSION>.zip` for upload to a ladder. |
| `bot/MyBot.py` | Your bot class. Entry point, logging setup, per-frame loop. |
| `bot/unit_collections/` | Tag-based unit tracking that survives across frames. |
| `bot/vrm/` | Virtual resource manager — stops two systems spending the same minerals in one frame. |
| `requirements.txt` | Pinned dependencies. Enforced at startup and at build time. |
| `docs/` | How this repo works, mechanically. |
| `CLAUDE.md` | Orientation for AI coding agents working in this repo. |

The utilities are optional. If you don't want one, delete its package and the two lines in
`MyBot.py` that reference it.

---

## Competing with your bot

Build an upload-ready package:

```bash
python create_ladder_zip.py
```

This produces `publish/MyBot-0.1.0.zip`, with your `bot/` package, `run.py`, and the pinned `sc2/`
library all at the zip root — the layout ladders expect. Upload that file.

Details, and the AI Arena constraints worth knowing before your first upload:
**[docs/ladder-packaging.md](docs/ladder-packaging.md)**

---

## Upgrading the SC2 library (`burnysc2`)

`burnysc2` is pinned in `requirements.txt` so the dependency does not auto-update. The build script
bundles the pinned version's `sc2/` package from `site-packages` into the ladder zip, so the version
that runs on the arena matches the version you develop against locally.

To upgrade:

1. Pick a target version. Review the changelog at
   https://github.com/BurnySc2/python-sc2/releases and check the AI Arena base image
   (https://github.com/aiarena/aiarena-docker-base) for any tightened transitive-dep constraints.
2. Edit `requirements.txt`: change `burnysc2==<old>` to `burnysc2==<new>`.
3. Install the new version into your venv: `pip install -r requirements.txt`.
4. Smoke-test locally (`python run.py`), then build a ladder zip
   (`python create_ladder_zip.py`). The scripts will verify the bundled `sc2/` matches the new version.
5. Commit `requirements.txt`.

Both `run.py` and `create_ladder_zip.py` verify that the installed `burnysc2` version matches the
`==` pin and abort on mismatch, so a stale local install can't accidentally ship to the ladder.

---

## Links

- **[python-sc2](https://github.com/BurnySc2/python-sc2)** — the library this is built on
- **[python-sc2 API docs](https://burnysc2.github.io/python-sc2/)**
- **[python-sc2 examples](https://github.com/BurnySc2/python-sc2/tree/develop/examples)** — some examples of basic API usage.
- **[AI Arena](https://aiarena.net/)** — the main SC2 bot ladder, and its
  [bot development wiki](https://aiarena.net/wiki/bot-development/)
- **[SC2 AI Discord](https://aiarena.net/)** — linked from the AI Arena site; where bot authors actually hang out and the best place to ask for help.
