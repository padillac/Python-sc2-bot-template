"""
Main bot class - the entry point the game runner instantiates and drives.

`run.py` imports this class, reads NAME/RACE/VERSION off it, and hands an instance
to python-sc2. From there the game engine calls on_start() once, on_step() every
frame, and on_end() when the game finishes.

Everything below is scaffolding. There is no game-playing logic here by design -
that part is yours to write.
"""

from __future__ import annotations

import sys

from loguru import logger

from sc2.bot_ai import BotAI
from sc2.data import Result

from bot.unit_collections import FastTagCache, UnitCollectionManager
from bot.vrm import VirtualResourceManager


# ============================================================================
# LOGGING SETUP
# ============================================================================

# Loguru is used throughout (it ships as a dependency of burnysc2).
# These globals are updated once per frame in on_step() so that every log line is
# stamped with in-game time instead of wall-clock time - which is what you actually
# want when reading a game log back against a replay.
_current_game_time = "00:00"
_current_game_loop = 0


def _game_time_formatter(record):
    """Custom formatter that includes game time and game loop instead of real time.

    Format: game_time: game_loop | log_level | package.module.class:function:line - log_message
    """
    # Build the location string (module path + function + line)
    location = f"{record['name']}:{record['function']}:{record['line']}"
    # Use <level></level> tags to apply loguru's default level coloring
    # Use <blue></blue> tags to color the location part blue
    return f"{_current_game_time}: {_current_game_loop} | <level>{record['level'].name:8}</level> | <blue>{location}</blue> - <level>{record['message']}</level>\n"


# Set the global logging level. A lower level gives more detail but has a real
# performance cost, since on_step runs many times per second.
# Levels: TRACE, DEBUG, INFO, SUCCESS, WARNING, ERROR, CRITICAL
#
# NOTE: create_ladder_zip.py rewrites the level in this exact line when building a
# ladder package. Keep the `logger.add(sys.stdout, level="...")` form intact.
logger.remove()
logger.add(sys.stdout, level="INFO", format=_game_time_formatter)


class MyBot(BotAI):
    """Main bot class. Rename this (and the file) to whatever your bot is called."""

    # Read by run.py (bot name shown in-game, default race) and by
    # create_ladder_zip.py (which names the zip "{NAME}-{VERSION}.zip").
    NAME = "MyBot"
    RACE = "Terran"  # Terran, Protoss, Zerg, Random
    VERSION = "0.1.0"

    # ========================================================================
    # INITIALIZATION, GAME START, GAME END
    # ========================================================================

    def __init__(self):
        super().__init__()

        # Helper systems. The attribute names below are the ones the helpers look
        # for on the bot instance, so keep them if you keep the helpers.
        # See docs/utilities.md for what each one does.
        self.vrm = VirtualResourceManager(self)
        self.fast_tag_cache = FastTagCache(self)
        self.unit_collections_manager = UnitCollectionManager(self)

        # Tags already sent this game, used by tag_send(tag_only_once=True)
        self.sent_tags: set = set()

    async def on_start(self):
        """Called once at game start, after the first observation is available."""
        # game_step controls how many game frames pass between on_step() calls.
        # The game runs at 22.4 frames/second, and the python-sc2 default is 4.
        #
        #   game_step = 2   ~11 calls/second  - common choice for competitive bots
        #   game_step = 16  ~1.4 calls/second - cheap, but slow to react
        #
        # Lower values mean more decisions per second and a higher APM ceiling, at
        # a proportionally higher CPU cost per game. game_step = 1 is possible but
        # is known to drop actions in some cases, so 2 is the safe floor.
        self.client.game_step = 2

    async def on_end(self, game_result: Result) -> None:
        """Called when the game ends."""
        pass

    # ========================================================================
    # MAIN GAME LOOP
    # ========================================================================

    async def on_step(self, iteration: int):
        """
        Main game loop - called every `game_step` frames.

        Keep this function short. Delegate real work to your own modules under bot/
        and call them from here.

        :param iteration: number of times on_step has been called this game
        """
        # Update the values the log formatter stamps onto every line this frame.
        global _current_game_time, _current_game_loop
        minutes = int(self.time // 60)
        seconds = int(self.time % 60)
        _current_game_time = f"{minutes:02d}:{seconds:02d}"
        _current_game_loop = self.state.game_loop

        # ---- PER-FRAME SETUP ----
        # These run before your logic, in this order, because each depends on the
        # one before it:
        #   1. Snap virtual resources back to the real balance and re-apply any
        #      reservations still held from previous frames.
        #   2. Rebuild the tag -> Unit cache from this frame's observation.
        #   3. Drop dead unit tags from every UnitCollection - this reads the cache,
        #      so it has to come after the rebuild.
        self.vrm.reset_to_actual()
        self.fast_tag_cache.rebuild()
        self.unit_collections_manager.cleanup_all()

        # ---- YOUR BOT LOGIC GOES HERE ----

        # ---- YOUR BOT LOGIC GOES HERE ----


    # ========================================================================
    # OTHER BotAI HOOKS
    # ========================================================================
    #
    # python-sc2 calls these automatically when the matching event occurs. None of
    # them are implemented here. Uncomment the ones you need.
    #
    # See sc2/bot_ai.py in your site-packages for the full list and exact behavior.
    #
    # The signatures below reference types you'll need to import:
    #   from sc2.unit import Unit
    #   from sc2.ids.unit_typeid import UnitTypeId
    #   from sc2.ids.upgrade_id import UpgradeId
    #
    # async def on_before_start(self) -> None: ...
    # async def on_unit_created(self, unit: Unit) -> None: ...
    # async def on_unit_destroyed(self, unit_tag: int) -> None: ...
    # async def on_unit_took_damage(self, unit: Unit, amount_damage_taken: float) -> None: ...
    # async def on_unit_type_changed(self, unit: Unit, previous_type: UnitTypeId) -> None: ...
    # async def on_building_construction_started(self, unit: Unit) -> None: ...
    # async def on_building_construction_complete(self, unit: Unit) -> None: ...
    # async def on_enemy_unit_entered_vision(self, unit: Unit) -> None: ...
    # async def on_enemy_unit_left_vision(self, unit_tag: int) -> None: ...
    # async def on_upgrade_complete(self, upgrade: UpgradeId) -> None: ...

    # ========================================================================
    # HELPER METHODS
    # ========================================================================

    async def tag_send(self, message: str, tag_only_once: bool = False, team_only: bool = False) -> bool:
        """
        Send a tag message to the game engine.

        Tags are chat messages prefixed with "Tag:". Ladder systems such as AI Arena
        scrape them out of the game and display them on the match page, which makes
        them a convenient way to mark that some branch of your code ran.

        Args:
            message: The tag string to send. "Tag:" prefix is added automatically if missing.
            tag_only_once: If True, checks self.sent_tags and skips sending if the
                bare tag has already been sent. Defaults to False.
            team_only: Whether to send the message to team only. Defaults to False.

        Returns:
            True if the message was sent, False if it was skipped (tag_only_once duplicate).
        """
        # Normalize the message and extract bare tag
        if message.startswith("Tag:"):
            bare_tag = message[len("Tag:"):]
            full_message = message
        else:
            bare_tag = message
            full_message = f"Tag:{message}"

        # If tag_only_once, check the global sent_tags set
        if tag_only_once:
            if bare_tag in self.sent_tags:
                logger.debug(f"Tag already sent, skipping: '{bare_tag}'")
                return False
            self.sent_tags.add(bare_tag)

        await self.chat_send(full_message, team_only=team_only)
        logger.info(f"Sent tag message: '{full_message}'")
        return True
