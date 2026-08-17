"""
Unit collection management system for persistent, tag-based unit tracking.

This module provides UnitCollection and UnitCollectionManager classes for safe
unit persistence in python-sc2 bots, preventing stale reference bugs.
"""

from bot.unit_collections.UnitCollection import UnitCollection, UnitCollectionManager
from bot.unit_collections.PassengerUnit import PassengerUnit
from bot.unit_collections.FastTagCache import FastTagCache

__all__ = [
    "UnitCollection",
    "UnitCollectionManager",
    "PassengerUnit",
    "FastTagCache",
]
