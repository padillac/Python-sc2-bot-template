"""
UnitCollection - Safe unit persistence for python-sc2 bots.

Manages collections of units by storing tags internally while providing a clean
Unit-based interface. Prevents stale reference bugs by automatically handling
the tag-to-unit conversion.

Classes:
    UnitCollection: Manages a single collection of units
    UnitCollectionManager: Manages multiple collections with batch operations
"""

from __future__ import annotations # required to avoid circular import errors on older python interpreters, which are used on ladder

from typing import Set, List, Dict, Optional, Callable, Iterator, Iterable, Union, TYPE_CHECKING

from sc2.ids.unit_typeid import UnitTypeId
from sc2.unit import Unit
from sc2.units import Units


if TYPE_CHECKING:
    from bot.MyBot import MyBot

from bot.unit_collections.PassengerUnit import PassengerUnit


class UnitCollection:
    """
    A persistent collection of units that stores tags internally.

    Automatically handles conversion between Unit objects (which are recreated
    each frame) and unit tags (which persist safely). Provides a collection-like
    interface without the risk of stale references.

    UnitCollections are automatically cleaned up to remove dead units at the start of each frame by the UnitCollectionManager so they're guaranteed to never contain the tag of a dead unit
    * They may contain the tag of a unit that is currently inside a transport, in which case you must use the 'include_passengers' flag in the 'get_unit*' methods to acknowledge risks of using PassengerUnits
    * They may also contain the tag of a worker that is currently inside a gas building,
        in which case the 'Unit' object does not exist in the current frame.
        'get_units[by_tags]' methods will not include this Unit object in the returned Units collections this frame.
        'get_unit_by_tag' method will return None for this tag this frame.

    Example:
        >>> scouts = UnitCollection(self, "scouts")
        >>> scouts.add_unit(worker)
        >>> for scout in scouts.get_units():
        ...     scout.move(target)
    """

    def __init__(self, game_state: MyBot, name: str = ""):
        """
        Initialize an empty unit collection.

        Args:
            game_state: Reference to the MyBot instance
            name: Optional name for debugging/logging purposes
        """
        self._game_state = game_state
        self._tags: Set[int] = set()
        self.name = name

        # Register self with UnitCollectionManager for automatic cleanup
        self._game_state.unit_collections_manager.register_collection(self)

    def add_unit(self, unit: Unit) -> None:
        """
        Add a single unit to the collection.

        Args:
            unit: The Unit object to add
        """
        self._tags.add(unit.tag)

    def add_units(self, units: Units) -> None:
        """
        Add multiple units to the collection.

        Args:
            units: A Units collection or iterable of Unit objects
        """
        self._tags.update(unit.tag for unit in units)

    def add_tag(self, tag: int) -> None:
        """
        Add single unit tag to the collection.

        Args:
            tag: int - A Unit tag
        """
        self._tags.update({tag})

    def add_tags(self, tags: Iterable[int]) -> None:
        """
        Add multiple unit tags to the collection.

        Args:
            tags: Iterable[int] - An Iterable of Unit tags
        """
        self._tags.update(tags)

    def remove_unit(self, unit: Unit) -> None:
        """
        Remove a single unit from the collection.

        Args:
            unit: The Unit object to remove
        """
        self._tags.discard(unit.tag)

    def remove_tag(self, tag: int) -> None:
        """
        Remove a unit by its tag.

        Args:
            tag: The unit tag to remove
        """
        self._tags.discard(tag)

    def remove_units(self, units: Units) -> None:
        """
        Remove multiple units from the collection.

        Args:
            units: A Units collection or iterable of Unit objects
        """
        tags_to_remove = {unit.tag for unit in units}
        self._tags -= tags_to_remove

    def clear(self) -> None:
        """Remove all units from the collection."""
        self._tags.clear()

    def get_units(self, include_passengers: bool = False) -> Units:
        """
        Get a fresh Units object for all tags in this collection.

        Uses FastTagCache for efficient O(1) lookups.
        By default only returns visible, non-passenger units.

        Args:
            include_passengers: If True, include PassengerUnits in the result.
                               If False (default), only return visible units.

        Returns:
            A Units collection containing fresh Unit objects for stored tags
        """
        # Use FastTagCache to efficiently get all units for our tags
        return self._game_state.fast_tag_cache.get_units(self._tags, include_passengers=include_passengers)

    def get_unit_by_tag(self, tag: int, include_passengers: bool = False) -> Optional[Union[Unit, PassengerUnit]]:
        """
        Get a Unit or PassengerUnit object for the given tag if it's in this collection.

        Uses FastTagCache for O(1) lookup.

        Args:
            tag: The unit tag to search for
            include_passengers: If True, include PassengerUnits in the result.
                               If False (default), return None for passenger units.
                               Default is False to prevent accidentally issuing commands
                               to passengers in typical code flows.

        Returns:
            Unit object, PassengerUnit object, or None if:
            - Tag not in this collection
            - Tag is in collection but unit is dead
            - Tag is in collection but unit is inside gas building (invisible)
            - Tag is in collection but unit is a passenger and include_passengers is False
        """
        # First check if the tag exists in this collection (efficient O(1) check)
        if tag not in self._tags:
            return None

        # Tag is in collection, use FastTagCache for O(1) lookup
        return self._game_state.fast_tag_cache.get_unit(tag, include_passengers=include_passengers)

    def get_units_by_tags(self, tags: Iterable[int], include_passengers: bool = False) -> Units:
        """
        Get Unit objects for the given tags if they're present in this collection.

        Uses FastTagCache for O(1) lookups.
        By default only returns visible, non-passenger units.

        Args:
            tags: An iterable collection (list, set, etc.) of unit tags to search for
            include_passengers: If True, include PassengerUnits in the result.
                               If False (default), only return visible units.

        Returns:
            A Units collection containing Unit objects for tags that are in the collection
        """
        # Find intersection of requested tags and tags in this collection (efficient)
        tags_to_find = set(tags) & self._tags

        if not tags_to_find:
            return Units([], self._game_state)

        # Use FastTagCache for efficient O(1) lookups
        return self._game_state.fast_tag_cache.get_units(tags_to_find, include_passengers=include_passengers)

    def get_composition(self) -> Dict[UnitTypeId, int]:
        comp = {}
        for unit in self.get_units(include_passengers=True):
            if unit.type_id not in comp:
                comp[unit.type_id] = 1
            else:
                comp[unit.type_id] += 1
        return comp

    def cleanup_dead_units(self) -> int:
        """
        Remove only confirmed dead units from the collection.

        This method only removes tags that appear in game_state.state.dead_units,
        ensuring that units inside gas buildings or transports are not
        incorrectly removed.

        Returns:
            Number of dead units removed
        """
        dead_tags = self._game_state.state.dead_units
        old_size = len(self._tags)
        self._tags -= dead_tags
        return old_size - len(self._tags)

    def contains(self, unit: Unit) -> bool:
        """
        Check if a unit is in this collection.

        Args:
            unit: The Unit object to check

        Returns:
            True if the unit's tag is in the collection
        """
        return unit.tag in self._tags

    def contains_tag(self, tag: int) -> bool:
        """
        Check if a tag is in this collection.

        Args:
            tag: The unit tag to check

        Returns:
            True if the tag is in the collection
        """
        return tag in self._tags

    def __len__(self) -> int:
        """Return the number of unit tags stored."""
        return len(self._tags)

    def __bool__(self) -> bool:
        """Return True if the collection is not empty."""
        return bool(self._tags)

    def is_empty(self) -> bool:
        """Check if the collection is empty."""
        return len(self._tags) == 0

    def get_tags(self) -> Set[int]:
        """
        Get a copy of the stored tags.

        Returns:
            A set of unit tags
        """
        return self._tags.copy()

    def destroy(self):
        self.clear()
        self._game_state.unit_collections_manager.remove_collection(self)

    def __repr__(self) -> str:
        """String representation of the collection."""
        name_str = f" '{self.name}'" if self.name else ""
        return f"UnitCollection{name_str}(size={len(self._tags)})"


class UnitCollectionManager:
    """
    Manages multiple UnitCollections with batch operations.

    Every UnitCollection registers itself with this manager on construction, so a
    single cleanup_all() call at the start of each frame keeps every collection
    free of dead unit tags.

    Example:
        >>> manager = UnitCollectionManager(self)
        >>> scouts = manager.create_collection("scouts")
        >>> army = manager.create_collection("army")
        >>> manager.cleanup_all()  # Cleanup all collections at once
    """

    def __init__(self, game_state: MyBot):
        """
        Initialize the manager with a game state reference.

        Args:
            game_state: Reference to the MyBot instance
        """
        self._game_state = game_state
        self._collections: List[UnitCollection] = []

    def create_collection(self, name: str = "") -> UnitCollection:
        """
        Create and register a new UnitCollection.

        Args:
            name: Optional name for the collection

        Returns:
            A new UnitCollection instance
        """
        collection = UnitCollection(self._game_state, name)
        self._collections.append(collection)
        return collection

    def register_collection(self, collection: UnitCollection) -> None:
        """
        Register an existing UnitCollection with this manager.

        Args:
            collection: The UnitCollection to register for management
        """
        if collection not in self._collections:
            self._collections.append(collection)

    def remove_collection(self, collection: UnitCollection) -> None:
        if collection in self._collections:
            self._collections.remove(collection)

    def cleanup_all(self) -> int:
        """
        Cleanup all registered collections at once.

        Returns:
            Total number of dead units removed across all collections
        """
        total_removed = 0
        for collection in self._collections:
            total_removed += collection.cleanup_dead_units()
        return total_removed

    def get_all_tags(self) -> Set[int]:
        """
        Get all unique tags across all collections.

        Returns:
            A set of all unit tags
        """
        all_tags = set()
        for collection in self._collections:
            all_tags.update(collection.get_tags())
        return all_tags

    def __len__(self) -> int:
        """Return the number of registered collections."""
        return len(self._collections)

    def __repr__(self) -> str:
        """String representation of the manager."""
        return f"UnitCollectionManager(collections={len(self._collections)})"
