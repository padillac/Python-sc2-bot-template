"""
StarCraft II Bot Runner
Supports three game modes:
1. Ladder games (AI Arena, etc.)
2. Human vs Bot games
3. Local test games (Bot vs Computer AI)
"""

import argparse
import asyncio
import logging
import os
import random
import sys


def _verify_pinned_dependencies():
    """Abort early if installed distributions don't match `==` pins in requirements.txt.

    Silently skipped when requirements.txt is not found next to this script — that's the case
    on the AI Arena, which doesn't bundle requirements.txt in the ladder zip and manages
    dependencies via its base image. Runs before any third-party import so a bad install
    can't fail with a confusing ImportError further down.
    """
    import importlib.metadata
    import re

    requirements_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "requirements.txt")
    if not os.path.isfile(requirements_path):
        return

    pin_pattern = re.compile(r"^\s*([A-Za-z0-9_.\-]+)\s*==\s*([^\s;#]+)")
    pins = {}
    with open(requirements_path, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            match = pin_pattern.match(stripped)
            if match:
                pins[match.group(1).lower()] = match.group(2)

    problems = []
    for name, pinned_version in pins.items():
        try:
            installed = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            problems.append(f"  - {name}: pinned to {pinned_version}, NOT INSTALLED")
            continue
        if installed != pinned_version:
            problems.append(f"  - {name}: pinned to {pinned_version}, installed {installed}")

    if problems:
        print(
            "ERROR: Installed package versions do not match requirements.txt pins:",
            *problems,
            "",
            "Run: pip install -r requirements.txt",
            sep="\n",
            file=sys.stderr,
        )
        sys.exit(1)


_verify_pinned_dependencies()


import aiohttp

import sc2
import sc2.maps
from sc2.main import run_game
from sc2.data import Race, Difficulty, AIBuild
from sc2.client import Client
from sc2.player import Bot, Computer, Human
from sc2.protocol import ConnectionAlreadyClosedError

from bot import MyBot

# ========================================= CONFIG =========================================

# ===== BOT SETTINGS =====
# Your bot's name and race are defined on the bot class itself (bot/MyBot.py)
BOT_NAME = MyBot.NAME
BOT_RACE = MyBot.RACE  # Options: Terran, Protoss, Zerg, Random


# ===== GAME SETTINGS FOR LOCAL TEST MATCHES ONLY =====

# Maps to pick from at random for local test and human games.
#
# Ships EMPTY - you must install maps and list them here (or pass --map) before
# your first local game.
#
# Use the maps AI Arena publishes and nothing else - those are what the ladder
# runs, so they're the only ones your results mean anything on. Download the
# current season's pack from https://aiarena.net/wiki/maps/ and see the "Maps"
# section of the README.
#
# An entry is the map filename without its extension, e.g. "AcropolisAIE" for
# AcropolisAIE.SC2Map. Maps may be stored one directory deep inside the Maps folder.
#
# Default Maps directory:
#   Windows: C:\Program Files (x86)\StarCraft II\Maps
#   Linux:   ~/StarCraftII/Maps
#
# Not used for ladder games - the ladder supplies the map.
MAP_POOL = []

# ===== OPPONENT SETTINGS =====
# Computer opponent settings (for local games)
OPPONENT_RACE = "Random"  # Terran, Zerg, Protoss, Random
OPPONENT_DIFFICULTY = "VeryHard"  # VeryEasy, Easy, Medium, MediumHard, Hard, Harder, VeryHard, CheatVision, CheatMoney, CheatInsane
AI_BUILD = "RandomBuild"  # RandomBuild, Rush, Timing, Power, Macro, Air

# ===== GAME MODE =====
# Set to True to play in realtime (like a human), False for faster simulation
REALTIME = False

# ========================================= END CONFIG =========================================




# ============================================================================
# GAME RUNNERS - One function per game type
# ============================================================================

def run_ladder_game(args, bot):
    """
    Run a ladder match (AI Arena, Local Test Arena, etc.)
    Connects to an existing SC2 instance via WebSocket.
    """
    host = args.LadderServer if args.LadderServer else "127.0.0.1"
    host_port = args.GamePort
    lan_port = args.StartPort

    # Configure ports for ladder communication
    ports = [lan_port + p for p in range(1, 6)]
    portconfig = sc2.portconfig.Portconfig()
    portconfig.shared = ports[0]  # Not used
    portconfig.server = [ports[1], ports[2]]
    portconfig.players = [[ports[3], ports[4]]]

    print(f"Connecting to ladder server at {host}:{host_port}...")

    # Join ladder game
    g = _join_ladder_game(
        host=host,
        port=host_port,
        players=[bot],
        realtime=args.realtime,
        portconfig=portconfig
    )

    # Run the game
    result = asyncio.get_event_loop().run_until_complete(g)

    opponent_id = getattr(args, 'OpponentId', 'Unknown')
    print(f"Ladder game completed: {result} vs {opponent_id}")

    return result, opponent_id


def run_human_game(args, bot):
    """
    Run a human vs bot match.
    Human plays in the SC2 client, bot connects as AI opponent.
    """
    # Determine human race
    try:
        human_race = Race[args.human_race.capitalize()]
    except (KeyError, AttributeError):
        print(f"Invalid human race, defaulting to Terran")
        human_race = Race.Terran

    # Select map
    map_name = _select_map(args)
    map_obj = _get_map(map_name)

    print(f"Starting human vs bot game on {map_name}...")
    print(f"Human: {human_race.name}")
    print(f"Bot: {bot.race.name}")
    print(f"Realtime: Yes (required for human play)")

    # Run the game - Human MUST be first player
    run_game(
        map_obj,
        [
            Human(human_race),  # Human player (first)
            bot                 # Bot player (second)
        ],
        realtime=True,  # Human games MUST be realtime
        sc2_version=args.sc2_version if args.sc2_version else None
    )

    print("Human game completed!")


def run_local_game(args, bot):
    """
    Run a local test game (Bot vs Computer AI).
    Bot spawns SC2 and plays against built-in AI.
    """
    # Determine opponent race and difficulty
    try:
        opponent_race = Race[args.opponent_race.capitalize()]
    except KeyError:
        print(f"Invalid opponent race: {args.opponent_race}, using Terran")
        opponent_race = Race.Terran

    try:
        ai_build = AIBuild[args.ai_build]
    except KeyError:
        print(f"Invalid ai_build: {args.ai_build}, using AIBuild.RandomBuild")
        ai_build = AIBuild.RandomBuild

    try:
        difficulty = Difficulty[args.difficulty]
    except KeyError:
        print(f"Invalid difficulty: {args.difficulty}, using VeryHard")
        difficulty = Difficulty.VeryHard

    # Select map
    map_name = _select_map(args)
    map_obj = _get_map(map_name)

    print(f"Starting local test game on {map_name}...")
    print(f"Bot: {bot.race.name}")
    print(f"Opponent: {opponent_race.name} ({difficulty.name}) ({ai_build.name})")
    print(f"Realtime: {'Yes' if args.realtime else 'No'}")

    # Run the game
    run_game(
        map_obj,
        [bot, Computer(opponent_race, difficulty, ai_build=ai_build)],
        realtime=args.realtime,
        sc2_version=args.sc2_version if args.sc2_version else None
    )

    print("Local game completed!")


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

async def _join_ladder_game(host, port, players, realtime, portconfig,
                            save_replay_as=None, step_time_limit=None,
                            game_time_limit=None):
    """
    Connect to an existing ladder game via WebSocket.
    Based on: https://github.com/Dentosal/python-sc2/blob/master/examples/run_external.py
    """
    ws_url = f"ws://{host}:{port}/sc2api"
    ws_connection = await aiohttp.ClientSession().ws_connect(ws_url, timeout=120)
    client = Client(ws_connection)

    try:
        result = await sc2.main._play_game(
            players[0],
            client,
            realtime,
            portconfig,
            step_time_limit,
            game_time_limit
        )

        if save_replay_as:
            await client.save_replay(save_replay_as)

        return result

    except ConnectionAlreadyClosedError:
        logging.error("Connection was closed before the game ended")
        return None

    finally:
        await ws_connection.close()


def _select_map(args):
    """Pick the map for a local or human game: --map if given, otherwise a random MAP_POOL entry.

    Exits with an actionable message when neither is available, rather than letting
    random.choice() raise IndexError on an empty pool. Ladder games never call this —
    the ladder supplies the map.
    """
    if args.map:
        return args.map

    if not MAP_POOL:
        print(
            "ERROR: No map specified and MAP_POOL is empty.",
            "",
            "This template ships with no maps configured, because which maps you have",
            "depends on which season's map pack you installed.",
            "",
            "Bots should only be run on the maps AI Arena publishes. Download the current",
            "season's pack from https://aiarena.net/wiki/maps/ and extract it into the",
            "Maps folder inside your StarCraft II install directory.",
            "",
            "Then fix this in one of two ways:",
            "  1. Pass a map on the command line:   python run.py --map <MapName>",
            "  2. Add the maps you installed to MAP_POOL near the top of run.py",
            "",
            "A map name is its filename without the extension, e.g. \"AcropolisAIE\" for",
            "AcropolisAIE.SC2Map. See the \"Maps\" section of the README for details.",
            sep="\n",
            file=sys.stderr,
        )
        sys.exit(1)

    return random.choice(MAP_POOL)


def _get_map(map_name):
    """Load map from custom path or default SC2 maps."""
    return sc2.maps.get(map_name)


def load_bot(args):
    """Initialize and configure the bot instance."""
    # Create bot instance
    bot = MyBot()

    # Determine bot race
    try:
        bot_race = Race[args.bot_race.capitalize()]
    except KeyError:
        print(f"!! Invalid bot race: {args.bot_race}, using Terran")
        bot_race = Race.Terran

    # Return configured Bot player
    return Bot(bot_race, bot, BOT_NAME)


# ============================================================================
# ARGUMENT PARSING
# ============================================================================

def parse_arguments():
    """Parse command-line arguments for all game modes."""
    parser = argparse.ArgumentParser(
        description="StarCraft II Bot Runner - Supports ladder, human, and local test games",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Local test game:
    python run.py --map AcropolisAIE
    python run.py --map AcropolisAIE --difficulty Medium

  Human vs bot:
    python run.py --human --human-race Terran --map AcropolisAIE
    python run.py --human --map AcropolisAIE

  Ladder game (auto-detected):
    python run.py --GamePort 8765 --StartPort 8766 --LadderServer 127.0.0.1

Note: --map is required for local and human games until you populate MAP_POOL in run.py.
        """
    )

    # ========================================
    # Game Mode Selection
    # ========================================
    mode_group = parser.add_argument_group('Game Mode')
    mode_group.add_argument(
        '--human',
        action='store_true',
        help='Play against a human player (you) instead of computer AI'
    )

    # ========================================
    # Ladder-Specific Arguments
    # ========================================
    ladder_group = parser.add_argument_group('Ladder Game Options')
    ladder_group.add_argument(
        '--GamePort',
        type=int,
        help='Game port for ladder connection'
    )
    ladder_group.add_argument(
        '--StartPort',
        type=int,
        help='Starting port for ladder communication channels'
    )
    ladder_group.add_argument(
        '--LadderServer',
        type=str,
        help='Ladder server address (default: 127.0.0.1)'
    )
    ladder_group.add_argument(
        '--OpponentId',
        type=str,
        help='Opponent ID for ladder games'
    )
    ladder_group.add_argument(
        '--Realtime',
        action='store_true',
        help='Realtime mode',
        default=REALTIME
    )

    # ========================================
    # Human Game Options
    # ========================================
    human_group = parser.add_argument_group('Human Game Options')
    human_group.add_argument(
        '--human-race',
        type=str,
        default='Terran',
        choices=['Terran', 'Protoss', 'Zerg', 'Random'],
        help='Race for human player (default: Terran)'
    )

    # ========================================
    # Local Test Game Options
    # ========================================
    local_group = parser.add_argument_group('Local Test Game Options')
    local_group.add_argument(
        '--opponent-race',
        type=str,
        default=OPPONENT_RACE,
        choices=['Terran', 'Protoss', 'Zerg', 'Random'],
        help=f'Computer opponent race (default: {OPPONENT_RACE})'
    )
    local_group.add_argument(
        '--difficulty',
        type=str,
        default=OPPONENT_DIFFICULTY,
        choices=['VeryEasy', 'Easy', 'Medium', 'MediumHard', 'Hard',
                 'Harder', 'VeryHard', 'CheatVision', 'CheatMoney', 'CheatInsane'],
        help=f'Computer opponent difficulty (default: {OPPONENT_DIFFICULTY})'
    )
    local_group.add_argument(
        '--ai-build',
        type=str,
        default=AI_BUILD,
        choices=['RandomBuild', 'Rush', 'Timing', 'Power', 'Macro', 'Air'],
        help=f'Computer opponent build (default: {AI_BUILD})'
    )

    # ========================================
    # Common Options
    # ========================================
    common_group = parser.add_argument_group('Common Options')
    common_group.add_argument(
        '--bot-race',
        type=str,
        default=BOT_RACE,
        choices=['Terran', 'Protoss', 'Zerg', 'Random'],
        help=f'Bot race (default: {BOT_RACE})'
    )
    common_group.add_argument(
        '--map',
        type=str,
        help=(
            f'Map to play on. Currently configured in MAP_POOL: {", ".join(MAP_POOL)}'
            if MAP_POOL else
            'Map to play on. MAP_POOL is empty, so this is required for local and human games.'
        )
    )
    common_group.add_argument(
        '--realtime',
        action='store_true',
        default=REALTIME,
        help=f'Enable realtime mode (default: {REALTIME})'
    )
    common_group.add_argument(
        '--sc2-version',
        type=str,
        help='Specific SC2 game version to use'
    )

    # Parse arguments
    args, unknown_args = parser.parse_known_args()

    # Warn about unknown arguments
    for unknown_arg in unknown_args:
        print(f"Warning: Unknown argument: {unknown_arg}")

    # Set defaults for ladder compatibility
    if not hasattr(args, 'OpponentId') or not args.OpponentId:
        args.OpponentId = f"{args.opponent_race}_{args.difficulty}"

    return args


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def main():
    """Main entry point - determines game type and runs appropriate game."""
    # Parse arguments
    args = parse_arguments()

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s"
    )

    # Display header
    bot_name = BOT_NAME
    bot_race = args.bot_race
    print("=" * 50)
    print(f"  {bot_name} ({bot_race})")
    print("=" * 50)

    try:
        # Load bot
        bot = load_bot(args)

        # Determine game type and run appropriate game
        if args.GamePort is not None:
            # LADDER GAME (auto-detected by --GamePort presence)
            print("Mode: LADDER GAME")
            run_ladder_game(args, bot)

        elif args.human:
            # HUMAN vs BOT GAME
            print("Mode: HUMAN vs BOT")
            run_human_game(args, bot)

        else:
            # LOCAL TEST GAME (default)
            print("Mode: LOCAL TEST (vs Computer AI)")
            run_local_game(args, bot)

        return 0

    except KeyboardInterrupt:
        print("\n\nGame stopped by user")
        return 0

    except Exception as e:
        print(f"\n\nError: {e}")
        if __debug__:
            import traceback
            traceback.print_exc()
        return 1


# ============================================================================
# SCRIPT EXECUTION
# ============================================================================

if __name__ == "__main__":
    sys.exit(main())
