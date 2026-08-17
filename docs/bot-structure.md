# Bot structure

How the pieces fit together, and what the game engine calls when.

## Package layout

```
run.py                              game runner - not bundled logic, just the launcher
create_ladder_zip.py                build script
bot/
├── __init__.py                     re-exports the bot class
├── MyBot.py                        the bot class itself
├── unit_collections/               optional helper package
└── vrm/                            optional helper package
```

Everything your bot needs at runtime must live under `bot/`. That directory (plus `run.py` and the
bundled `sc2/` library) is what goes into the ladder zip — code outside it simply won't exist on
the ladder. See [ladder-packaging.md](ladder-packaging.md).

## The import chain

```
run.py
  └─ from bot import MyBot          # bot/__init__.py
       └─ from bot.MyBot import MyBot   # bot/MyBot.py
```

`run.py` reads `MyBot.NAME` and `MyBot.RACE` off the class to name the player and pick a default
race, then constructs an instance and hands it to python-sc2 wrapped in a `Bot(...)` player object.

If you rename the bot, all three of these have to agree: the module filename, the class name inside
it, and `BOT_MODULE` in `create_ladder_zip.py`.

## The lifecycle

python-sc2 calls these methods on your bot class. Only `on_step` is mandatory — the base class
raises `NotImplementedError` if you don't override it. All of them are `async`.

### Startup and shutdown

| Hook | When |
|---|---|
| `on_before_start()` | Once, after the first observation has been prepared but before `_prepare_first_step()`. See below for what that means in practice. |
| `on_start()` | Once, after `_prepare_first_step()`. Everything is available. Where you set `game_step` and do one-time setup. |
| `on_step(iteration)` | Every `game_step` frames, for the whole game. Everything else hangs off this. |
| `on_end(game_result)` | When the game ends. |

`on_before_start` is often described as "not all data is available", which is vaguer than it needs
to be. The first observation *has* already been prepared, so `self.state`, `self.units`,
`self.structures` and friends are populated. What is missing is everything
`_prepare_first_step()` computes:

- `self.game_info.player_start_location`
- `self.expansion_locations_list` / `expansion_locations_dict` (accessing these asserts)
- `self.game_info.map_ramps` and `self.game_info.vision_blockers`

Its documented use is realtime mode, where the few hundred milliseconds spent computing expansion
locations are real game time — so you split workers or queue your first worker in
`on_before_start`, then do everything else in `on_start`.

`on_end` is also called in two paths that aren't a normal finish: with `Result.Defeat` if your
`on_start` raises, and with `Result.Tie` if a `game_time_limit` was set and exceeded.

### Event hooks

These fire from `issue_events()`, which runs **immediately before `on_step` in the same
iteration** — so any event for this frame has already been delivered by the time `on_step` runs.
They are issued in a fixed order: unit deaths, then unit additions/damage/type changes, then
building events, then upgrades, then vision.

| Hook | Signature | Fires for |
|---|---|---|
| `on_unit_destroyed` | `(unit_tag: int)` | Your units and structures, and enemy ones — but only if the enemy unit was in vision when it died. A tag, not a `Unit`, because the unit is already gone. |
| `on_unit_created` | `(unit: Unit)` | **Your own non-structure units only.** Structures never trigger this; they go through the building hooks below. |
| `on_unit_took_damage` | `(unit: Unit, amount_damage_taken: float)` | Your own units **and** structures. Never enemies. Not called if the unit died this frame. |
| `on_unit_type_changed` | `(unit: Unit, previous_type: UnitTypeId)` | Your own units and structures. Larva → egg, tank sieging, a zerg unit burrowing, hatchery → lair, corruptor → broodlord cocoon, a Terran building lifting off or landing. Use `unit.type_id` for the new type. |
| `on_building_construction_started` | `(unit: Unit)` | Your structures, when one first appears with `build_progress < 1`. |
| `on_building_construction_complete` | `(unit: Unit)` | Your structures, when `build_progress` reaches 1. **Also fires for your starting townhall** at game start, since it appears already-complete. |
| `on_upgrade_complete` | `(upgrade: UpgradeId)` | Your own upgrades — computed as a diff against last frame's `self.state.upgrades`. |
| `on_enemy_unit_entered_vision` | `(unit: Unit)` | Enemy units **and enemy structures** newly visible this frame. |
| `on_enemy_unit_left_vision` | `(unit_tag: int)` | Enemy units and structures visible last frame but not this one. A tag, not a `Unit`. |

`on_unit_created` is guarded by a seen-tags set, so it fires **at most once per unit tag per
game**. A unit that leaves a transport, a bunker, or a refinery will not re-trigger it.

`MyBot.py` lists these commented out near the bottom; uncomment what you need.
`sc2/bot_ai.py` and `sc2/bot_ai_internal.py` in your installed `burnysc2` package are the
authoritative reference — the docstrings say what a hook is for, and `issue_events()` and the
`_issue_*` methods in `bot_ai_internal.py` show exactly when it fires.

## `game_step` and the frame rate

StarCraft II runs at **22.4 frames per second**. `self.client.game_step` sets how many frames pass
between `on_step()` calls:

| `game_step` | `on_step` calls/sec | Notes |
|---|---|---|
| 1 | 22.4 | Known to drop actions in some cases |
| 2 | 11.2 | Template default; common for competitive bots |
| 4 | 5.6 | python-sc2 default |
| 16 | 1.4 | Cheap, but slow to react |

Lower means more decisions per second and a higher achievable APM, at proportionally higher step time per
game. It's conventionally set in `on_start()`.

Note that `on_step`'s `iteration` argument counts `on_step` calls, not game frames. For anything
timing-related, use `self.time` (game seconds) or `self.state.game_loop` (game frames).

## Inside `on_step`

The template's `on_step` does three things before handing control to you:

```python
self.vrm.reset_to_actual()              # 1
self.fast_tag_cache.rebuild()           # 2
self.unit_collections_manager.cleanup_all()   # 3

# ---- YOUR BOT LOGIC GOES HERE ----
```

The order matters:

1. **`vrm.reset_to_actual()`** — snaps virtual resource balances back to the real ones and re-applies
   any reservations still outstanding from earlier frames. Must happen before anything checks
   affordability.
2. **`fast_tag_cache.rebuild()`** — rebuilds the tag → `Unit` lookup from this frame's observation.
   Must happen before anything resolves a stored tag.
3. **`unit_collections_manager.cleanup_all()`** — drops dead unit tags from every registered
   collection. Reads the current frame's state, so it comes after the rebuild.

Above those, `on_step` also updates two module-level globals that the log formatter reads, so every
log line is stamped with in-game time rather than wall-clock time.

If you delete a helper package, delete its line here too. See [utilities.md](utilities.md).

## Growing past one function

`on_step` is a hot path and a bad place for a whole bot. The mechanical options, in rough order of
how much structure they impose:

- **Methods on the bot class.** Fine for a handful of behaviors. Everything shares `self`.
- **Separate modules under `bot/`**, holding a reference to the bot instance and exposing something
  `on_step` calls each frame. This is the common shape once a bot outgrows one file.
- **Any architecture you like** — the template has no base classes to subclass and no registry to
  register with, so nothing here constrains the design.

Whatever you pick, the constraint is the same: it lives under `bot/`, and something in `on_step`
has to call it.
