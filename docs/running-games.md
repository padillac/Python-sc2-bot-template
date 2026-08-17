# Running games

`run.py` handles all three ways a bot gets run. You don't pick the mode explicitly — it's inferred:

| Condition | Mode |
|---|---|
| `--GamePort` is present | **Ladder** — connect to an already-running SC2 instance |
| `--human` is present | **Human vs bot** |
| otherwise | **Local test** vs the built-in AI (default) |

`--GamePort` is checked first, so a ladder invocation always wins.

## Local test game

The default. `run.py` launches StarCraft II itself and plays your bot against Blizzard's built-in AI.

```bash
python run.py
python run.py --map AcropolisAIE
python run.py --map AcropolisAIE --difficulty Medium --opponent-race Zerg
python run.py --difficulty CheatInsane --ai-build Rush
```

## Human vs bot

You play in the SC2 client against your own bot. Always runs in realtime, regardless of `--realtime`.

```bash
python run.py --human
python run.py --human --human-race Zerg --map AcropolisAIE
```

The human player is added first, which is required for the client to attach you to a player slot.

## Ladder game

The ladder starts SC2 itself and passes connection details on the command line; `run.py` joins the
existing game over a websocket instead of launching anything. You never type this by hand — it's
what the ladder does to your bot.

```bash
python run.py --GamePort 8765 --StartPort 8766 --LadderServer 127.0.0.1 --OpponentId <id>
```

`--StartPort` seeds five sequential ports used for the game's internal communication channels.

## Flags

### Game mode

| Flag | Default | Meaning |
|---|---|---|
| `--human` | off | Play against the bot yourself |

### Ladder

| Flag | Meaning |
|---|---|
| `--GamePort <int>` | Port of the running game to join. **Presence of this flag selects ladder mode.** |
| `--StartPort <int>` | Base port for communication channels |
| `--LadderServer <host>` | Ladder server address (default `127.0.0.1`) |
| `--OpponentId <str>` | Opponent identifier, logged at game end |
| `--Realtime` | Realtime mode |

### Local game

| Flag | Default | Values |
|---|---|---|
| `--opponent-race` | `Random` | `Terran`, `Protoss`, `Zerg`, `Random` |
| `--difficulty` | `VeryHard` | `VeryEasy`, `Easy`, `Medium`, `MediumHard`, `Hard`, `Harder`, `VeryHard`, `CheatVision`, `CheatMoney`, `CheatInsane` |
| `--ai-build` | `RandomBuild` | `RandomBuild`, `Rush`, `Timing`, `Power`, `Macro`, `Air` |

### Human game

| Flag | Default | Values |
|---|---|---|
| `--human-race` | `Terran` | `Terran`, `Protoss`, `Zerg`, `Random` |

### Common

| Flag | Default | Meaning |
|---|---|---|
| `--bot-race` | `MyBot.RACE` | Race your bot plays |
| `--map <name>` | from `MAP_POOL` | Map to play on |
| `--realtime` | off | See below |
| `--sc2-version <str>` | pinned AI Arena SC2 version | AI Arena/python-sc2 has pinned the latest stable SC2 build. Don't set this flag unless you really know what you're doing. |

Unknown arguments are warned about, not fatal — the ladder passes flags this runner doesn't use.

The defaults for `--opponent-race`, `--difficulty`, `--ai-build`, `--bot-race` and `--realtime` come
from constants in the CONFIG block near the top of `run.py`. Edit those if you want a different
baseline than typing flags every time.

## Realtime vs stepped

- **Stepped** (default, `realtime=False`) — the game waits for your bot to finish each step. Games
  run as fast as your CPU allows and your bot is never rushed. This is what you want for testing.
- **Realtime** (`--realtime`) — the game runs at wall-clock speed and does not wait. If a step takes
  too long, the game moves on without you. Required for human games, may cause issues for slow bots.

## Maps

Bots should only be run on the maps AI Arena publishes — download the current season's pack from
the [AI Arena maps page](https://aiarena.net/wiki/maps/). See the Maps section of the README for
the full setup.

SC2 looks for maps in its `Maps` directory (`C:\Program Files (x86)\StarCraft II\Maps` on Windows,
`~/StarCraftII/Maps` on Linux). Maps may be nested one directory deep. A map's *name* is its
filename without the `.SC2Map` extension.

Map selection for local and human games:

1. `--map <name>` if given.
2. Otherwise a random entry from `MAP_POOL` in `run.py`.
3. If `MAP_POOL` is empty and no `--map` was given, the runner exits with instructions rather than
   crashing:

   ```
   ERROR: No map specified and MAP_POOL is empty.
   ```

   Fix by passing `--map`, or by filling in `MAP_POOL`.

Ladder games never use either — the ladder supplies the map.

If you name a map that isn't installed, python-sc2 raises:

```
KeyError: Map 'Foo' was not found. Please put the map file in "/StarCraft II/Maps/".
```

Usually this means a typo, or the map file is nested more than one directory deep.

## Logs

Log lines are stamped with in-game time rather than wall-clock time:

```
04:32: 6082  | INFO     | bot.MyBot:on_step:118 - your message here
  │      │      │          │
  │      │      │          └─ module:function:line
  │      │      └─ log level
  │      └─ game loop (frame number)
  └─ game time mm:ss
```

That makes a log directly comparable against a replay's clock.

To change verbosity, edit the level in `bot/MyBot.py`:

```python
logger.add(sys.stdout, level="INFO", format=_game_time_formatter)
```

Levels, quietest to loudest: `CRITICAL`, `ERROR`, `WARNING`, `SUCCESS`, `INFO`, `DEBUG`, `TRACE`.

Logging is not free — `on_step` runs several times per second for an entire game, so a `DEBUG` line
in a per-unit loop can produce hundreds of thousands of lines and measurably slow you down. The
ladder build rewrites this level automatically; see [ladder-packaging.md](ladder-packaging.md).
