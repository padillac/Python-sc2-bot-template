"""
Virtual Resource Manager for frame-safe resource tracking.

This module provides the VirtualResourceManager class for preventing race conditions
when multiple actions check can_afford() in the same frame.
"""

from bot.vrm.VirtualResourceManager import VirtualResourceManager

__all__ = [
    "VirtualResourceManager",
]
