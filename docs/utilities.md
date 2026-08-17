# Utilities

Two optional helper modules ship with the template. Both solve problems that are easy to hit and
hard to diagnose in python-sc2. Neither contains any game logic.

They are reached by fixed attribute names on the bot instance, set up in `MyBot.__init__`:

| Attribute | Class |
|---|---|
| `self.vrm` | `VirtualResourceManager` |
| `self.fast_tag_cache` | `FastTagCache` |
| `self.unit_collections_manager` | `UnitCollectionManager` |

The helpers look each other up through these names — `UnitCollection` reaches
`game_state.unit_collections_manager` and `game_state.fast_tag_cache` directly. If you rename an
attribute, the helpers break. See [Removing a utility](#removing-a-utility) if you'd rather not
have them.

---

## The problem they exist for

**`Unit` objects are rebuilt from scratch every frame.** A `Unit` you got last frame is a snapshot:
its position, health, and orders are all stale, and nothing warns you. Worse, the unit may be dead,
in which case you're holding an object describing something that no longer exists.

```python
# Broken - self.scout is stale the moment the frame ends
self.scout = self.workers.random

# Correct - a tag is a stable identifier
self.scout_tag = self.workers.random.tag
```

Tags are stable for the life of the unit. The rule is: **store tags, resolve to `Unit` objects each
frame.** Doing that naively means scanning unit collections, which is O(n) per lookup. These
utilities make it O(1) and handle the awkward edge cases.

---

## `bot/unit_collections/`

### `FastTagCache`

A dict from unit tag to `Unit`, rebuilt once per frame from the current observation. Covers your
units and structures, gas buildings, enemy units and structures, neutral resources and
destructibles, and units riding inside transports.

```python
unit = self.fast_tag_cache.get_unit(tag)          # Unit or None
units = self.fast_tag_cache.get_units(tag_list)   # Units collection, missing tags skipped
tag in self.fast_tag_cache                        # membership test
len(self.fast_tag_cache)                          # number of cached tags
```

`get_unit()` returns `None` when the tag is dead, invalid, or belongs to a worker currently inside a
gas building — the API does not report those, so for that frame the unit genuinely does not exist.
`get_units()` silently skips them.

`rebuild()` must be called once per frame before anything resolves a tag. `MyBot.on_step` does this.

### `UnitCollection`

A persistent set of units that stores tags internally and hands back fresh `Unit` objects on demand.

```python
scouts = UnitCollection(self, "scouts")

scouts.add_unit(worker)
scouts.add_units(some_units)
scouts.add_tag(tag)
scouts.remove_unit(worker)

for scout in scouts.get_units():      # fresh Units, this frame
    scout.move(target)

scouts.get_unit_by_tag(tag)           # Unit or None, only if in this collection
scouts.get_units_by_tags(tags)        # intersection of tags and this collection
scouts.get_composition()              # {UnitTypeId: count}
scouts.get_tags()                     # copy of the raw tag set

len(scouts), bool(scouts), scouts.is_empty()
scouts.contains(unit), scouts.contains_tag(tag)
scouts.clear()
scouts.destroy()                      # clear and unregister from the manager
```

A collection registers itself with `unit_collections_manager` on construction, so it's cleaned up
automatically — you never have to prune dead units yourself.

Dead-unit removal is driven by `state.dead_units`, not by absence from the observation. That
distinction matters: a worker inside a gas building or a marine inside a bunker is *invisible*, not
dead, and must not be dropped from the collection.

### `UnitCollectionManager`

Owns every `UnitCollection` and cleans them in one pass.

```python
army = self.unit_collections_manager.create_collection("army")
self.unit_collections_manager.cleanup_all()     # called once per frame in on_step
self.unit_collections_manager.get_all_tags()
```

### `PassengerUnit`

A `Unit` subclass marking a unit currently riding inside a transport or bunker. Two things are true
of passengers and surprising if you don't know:

- **Position is the transport's position**, not the passenger's own.
- **Commands silently fail** — the unit isn't directly controllable.

Because of that, the lookup methods **exclude passengers by default**. Pass
`include_passengers=True` when you specifically want to track units inside transports:

```python
riders = transport_group.get_units(include_passengers=True)
for u in riders:
    if isinstance(u, PassengerUnit):
        print(f"inside {u.transport.type_id}")
```

The default is the safe one: you can't accidentally issue orders to a unit that can't receive them.

---

## `bot/vrm/` — `VirtualResourceManager`

### The problem

Two parts of your bot check affordability in the same frame. Both see 200 minerals. Both spend.
Because the game only reconciles resources between frames, `can_afford()` returns `True` for both,
and one of the two commands is quietly dropped.

The VRM keeps a *virtual* balance alongside the real one. Reserving deducts from the virtual
balance immediately, so the second caller sees the money already gone.

### Usage

```python
res_id = self.vrm.reserve(UnitTypeId.MARINE, purpose="train marine")
if res_id is not None:
    barracks.train(UnitTypeId.MARINE)
    self.vrm.release_reservation(res_id)
```

```python
# affordability, against the virtual balance
self.vrm.can_afford_safe(UnitTypeId.MARINE)
self.vrm.can_afford_safe_explicit(minerals=100, vespene=0, supply=2)

# reservations
self.vrm.reserve(item, quantity=1, reserve_supply=True, purpose="...")   # -> id or None
self.vrm.reserve_explicit(minerals, vespene, supply, purpose="...")      # -> id or None
self.vrm.release_reservation(res_id)

# current virtual balances
self.vrm.virtual_minerals, self.vrm.virtual_vespene, self.vrm.virtual_supply_left

self.vrm.get_status()   # full dump incl. every active reservation, for debugging
```

`reserve()` returns `None` if the virtual balance can't cover the cost — that's your "can't afford"
signal, so you rarely need a separate `can_afford_safe()` call.

`reserve_explicit()` exists for items whose cost lookup is wrong or returns zero.

### Reservation lifetime

Reservations **persist across frames** and are not released automatically when the command
succeeds. You must call `release_reservation(id)`, which takes effect at the start of the next frame
— the delay is deliberate, so the deduction survives the rest of the current frame.

An unreleased reservation blocks its resources indefinitely, so a missing release is a real leak. As
a safety net, reservations auto-expire after **672 frames (30 seconds)** with a `WARNING` in the
log. If you see those warnings, something isn't releasing.

`reset_to_actual()` runs once per frame in `on_step`: it processes pending releases, expires stale
reservations, resets balances to the real values, then re-applies everything still outstanding. If
a virtual balance goes negative it logs a `CRITICAL` with a dump of every active reservation.

The VRM only uses stock `BotAI` members — `minerals`, `vespene`, `supply_left`, `state.game_loop`,
`calculate_cost()`, `calculate_supply_cost()` — so it works with any bot class.

---

## Removing a utility

Nothing else depends on these. To drop one:

1. Delete its package directory (`bot/vrm/` or `bot/unit_collections/`).
2. Delete its import, its constructor call in `MyBot.__init__`, and its line in the per-frame setup
   block in `MyBot.on_step`.

`unit_collections` is a single unit: `UnitCollection` depends on `FastTagCache` and
`UnitCollectionManager`, and `FastTagCache` depends on `PassengerUnit`. Remove them together.
`vrm` is independent of both.
