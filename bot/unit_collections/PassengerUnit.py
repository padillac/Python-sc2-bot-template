"""
PassengerUnit - Extended Unit class for units inside transports/bunkers.

This class extends Unit to provide type safety by explicitly marking units as passengers,
which have different characteristics than regular units (position reflects transport position,
commands will fail, etc.).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sc2.unit import Unit

if TYPE_CHECKING:
    pass


class PassengerUnit(Unit):
    """
    Extended Unit class for units that are currently passengers in a transport.

    PassengerUnits are full Unit objects with all the same properties and methods,
    but with additional passenger-specific information and important behavioral notes:

    **Key Differences from Regular Units:**
    - **Position reflects transport position** - passenger.position returns the transport's position,
      not the actual position of the unit inside. This is intentional and matches game behavior.
    - **Commands will fail** - Issuing commands (move, attack, gather, etc.) to passengers will
      fail at the game API level since the unit is not directly controllable.
    - **Additional properties** - Has `is_passenger` property and `transport` reference

    **Safety:**
    By default, UnitCollection.get_units() excludes passengers (include_passengers=False).
    This prevents accidentally issuing commands to passengers in typical code flows.
    Only explicitly request passengers when you need to track units inside transports.

    Example::

        cache = game_state.fast_tag_cache
        unit_obj = cache.get_unit(worker_tag)

        if isinstance(unit_obj, PassengerUnit):
            print(f"Worker is inside {unit_obj.transport.type_id}")
            # Don't issue commands - they will fail
            # Position will be the transport's position
        else:
            # Regular unit - safe to command
            unit_obj.move(target)
    """

    def __init__(self, passenger_unit: Unit, transport_unit: Unit):
        """
        Initialize a PassengerUnit from an existing Unit object.

        Args:
            passenger_unit: The Unit object representing the passenger (from transport.passengers)
            transport_unit: The Unit object representing the transport carrying this passenger
        """
        # Call parent Unit constructor with all the passenger unit's data
        super().__init__(
            passenger_unit._proto,
            passenger_unit._bot_object,
            passenger_unit.distance_calculation_index,
            passenger_unit.base_build
        )
        self._transport = transport_unit

    @property
    def is_passenger(self) -> bool:
        """Always returns True for PassengerUnit instances."""
        return True

    @property
    def transport(self) -> Unit:
        """Returns the Unit object that is carrying this passenger."""
        return self._transport

    def __repr__(self) -> str:
        """String representation of the PassengerUnit."""
        return f"PassengerUnit(name={self.name!r}, tag={self.tag}, transport={self.transport.type_id})"
