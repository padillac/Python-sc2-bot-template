# CLAUDE.md

## What this repo is

A starter template for a StarCraft II bot built on [python-sc2](https://github.com/BurnySc2/python-sc2).
It contains a working game runner, a ladder packager, and a few runtime utilities — and no game
logic at all. `bot/MyBot.py` starts a game, wires up its helpers, and does nothing else.

The template takes no position on how a bot should be structured, that's up to the author implementing it.

## Layout

| Path | What it is |
|---|---|
| `run.py` | Game runner (local / human / ladder) and local-game config |
| `create_ladder_zip.py` | Builds the upload zip for a ladder |
| `bot/` | All bot code. **New code goes here** — this is the only directory bundled into the ladder zip |
| `bot/MyBot.py` | The bot class: entry point, logging setup, per-frame loop |
| `bot/unit_collections/`, `bot/vrm/` | Optional runtime helpers |
| `docs/` | How this repo works, mechanically |

## Entry point

`run.py` → `bot/__init__.py` → `bot.MyBot.MyBot`. The game engine calls `on_start()` once,
`on_step()` every frame, and `on_end()` at the end. `on_step()` is where all bot logic resides.

## Commands

```bash
python run.py                          # local game vs built-in AI
python run.py --map <Name>             # required if MAP_POOL in run.py is empty
python run.py --human                  # play against the bot yourself
python create_ladder_zip.py            # build publish/<NAME>-<VERSION>.zip
```

## Where to look things up

- `docs/` — this repo's mechanics: bot structure and the `BotAI` lifecycle, running games,
  the utilities, and ladder packaging. Read the relevant one before changing `run.py`,
  `create_ladder_zip.py`, or the per-frame setup in `on_step()`.
- `sc2/bot_ai.py` and `sc2/unit.py` in the installed `burnysc2` package — the real API surface, and more reliable than any summary of it.
- [python-sc2 framework](https://github.com/BurnySc2/python-sc2/) — official framework repository. You'll want to look here to understand how to use the BotAI API.