"""
FastTagCache - O(1) lookup cache for unit tags to Unit objects.

Provides high-performance tag-to-unit lookups by maintaining a dictionary
that is rebuilt each frame. This eliminates the need for O(n) searches
through unit collections.
"""

from __future__ import annotations

from typing import Dict, Iterable, Optional, Union, TYPE_CHECKING

from sc2.unit import Unit
from sc2.units import Units

if TYPE_CHECKING:
    from bot.MyBot import MyBot

from bot.unit_collections.PassengerUnit import PassengerUnit


class FastTagCache:
    """
    Frame-by-frame O(1) lookup cache for unit tags.

    This cache maps unit tags to Unit or PassengerUnit objects, providing
    fast lookups without needing to search through unit collections.

    The cache is rebuilt at the start of each on_step() before any bot
    logic runs, ensuring it's always up-to-date.

    Example:
        >>> # In MyBot.__init__
        >>> self.fast_tag_cache = FastTagCache(self)
        >>>
        >>> # In MyBot.on_step
        >>> self.fast_tag_cache.rebuild()
        >>>
        >>> # In any code that needs to look up a unit
        >>> unit = self.fast_tag_cache.get_unit(worker_tag)
        >>> if unit is None:
        ...     # Unit is dead or inside gas building
        ... elif isinstance(unit, PassengerUnit):
        ...     # Unit is in transport - can't issue commands
        ... else:
        ...     # Regular unit - can issue commands
        ...     unit.move(target)
    """

    def __init__(self, game_state: 'MyBot'):
        """
        Initialize the FastTagCache.

        Args:
            game_state: Reference to the MyBot instance
        """
        self._game_state = game_state
        self._cache: Dict[int, Union[Unit, PassengerUnit]] = {}

    def rebuild(self) -> None:
        """
        Rebuild the cache from scratch for the current frame.

        This method should be called at the start of on_step(), before any
        bot logic or UnitCollection cleanup.

        Population order:
        1. All friendly units (workers, army, structures)
        2. All enemy units (visible and snapshots)
        3. All neutral units (resources, destructibles, etc.)
        4. All passengers from transports/bunkers (wrapped in PassengerUnit)

        Note: Units inside gas buildings are not visible to the API and won't
        be in the cache. Queries for their tags will return None.
        """
        # Clear the old cache
        self._cache.clear()

        ## Add all friendly units and structures
        # Gas buildings (REFINERY, ASSIMILATOR, EXTRACTOR) are in gas_buildings collection, not structures
        # All other buildings are in structures collection
        for unit in self._game_state.units:
            self._cache[unit.tag] = unit

        for structure in self._game_state.structures:
            self._cache[structure.tag] = structure

        for gb in self._game_state.gas_buildings:
            self._cache[gb.tag] = gb

        # Add all enemy units and structures
        for unit in self._game_state.enemy_units:
            self._cache[unit.tag] = unit

        for structure in self._game_state.enemy_structures:
            self._cache[structure.tag] = structure

        # Add all neutral units (mineral fields, geysers, destructibles, etc.)
        for unit in self._game_state.resources:
            self._cache[unit.tag] = unit

        # Add destructibles if they exist
        if hasattr(self._game_state, 'destructibles'):
            for unit in self._game_state.destructibles:
                self._cache[unit.tag] = unit

        # Add all passengers from transports/bunkers (wrapped in PassengerUnit)
        # Iterate through all units that can carry passengers
        for unit in self._game_state.all_units:
            if unit.passengers:
                for passenger in unit.passengers:
                    # Create PassengerUnit from the passenger Unit object
                    passenger_unit = PassengerUnit(passenger, unit)
                    self._cache[passenger.tag] = passenger_unit

    def get_unit(self, tag: int, include_passengers: bool = False) -> Optional[Union[Unit, PassengerUnit]]:
        """
        Get the Unit or PassengerUnit object for the given tag.

        Returns None if:
        - Tag is dead/invalid
        - Tag belongs to a unit inside a gas building (invisible to API)
        - Tag belongs to a passenger and include_passengers is False

        Args:
            tag: The unit tag to look up
            include_passengers: If True, include PassengerUnits in the result.
                               If False (default), return None for passenger units.
                               Default is False to prevent accidentally issuing commands
                               to passengers in typical code flows.

        Returns:
            Unit object, PassengerUnit object, or None
        """
        unit = self._cache.get(tag, None)
        if unit is not None:
            # Only return if it's not a passenger, or if we want passengers
            if not isinstance(unit, PassengerUnit) or include_passengers:
                return unit
        return None

    def get_units(self, tags: Iterable[int], include_passengers: bool = False) -> Units:
        """
        Efficiently get a Units object containing all units matching the given tags.

        This method provides O(n) performance where n is the number of tags to look up,
        as opposed to O(n*m) if you were to search through a Units collection for each tag.

        Units that are not found (dead, invalid, or inside gas buildings) are silently
        skipped and not included in the returned Units object.

        Args:
            tags: An iterable of unit tags to look up
            include_passengers: If True, include PassengerUnits in the result.
                               If False (default), only return visible units.
                               Default is False to prevent accidentally issuing commands
                               to passengers in typical code flows.

        Returns:
            Units object containing all found units (may be empty if no tags are found)

        Example:
            >>> # Get all units from a collection of tags
            >>> worker_tags = [123, 456, 789]
            >>> workers = game_state.fast_tag_cache.get_units(worker_tags)
            >>> for worker in workers:
            ...     worker.gather(mineral_field)
            >>>
            >>> # Get units including any that might be passengers
            >>> all_units = game_state.fast_tag_cache.get_units(unit_tags, include_passengers=True)
        """
        # Collect all found units, filtering out None values for tags that don't exist
        units = []
        for tag in tags:
            unit = self._cache.get(tag)
            if unit is not None:
                # Include if it's not a passenger, or if we want passengers
                if not isinstance(unit, PassengerUnit) or include_passengers:
                    units.append(unit)

        return Units(units, self._game_state)

    def __contains__(self, tag: int) -> bool:
        """
        Check if a tag exists in the cache.

        Args:
            tag: The unit tag to check

        Returns:
            True if tag is in cache, False otherwise
        """
        return tag in self._cache

    def __len__(self) -> int:
        """Return the number of tags in the cache."""
        return len(self._cache)

    def __repr__(self) -> str:
        """String representation of the cache."""
        return f"FastTagCache(size={len(self._cache)})"
