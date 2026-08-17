"""
Virtual Resource Manager for frame-safe persistent resource reservation tracking.

Prevents race conditions when multiple actions check can_afford() in the same frame
by tracking virtual resource deductions before they're actually processed by the game.

Reservations are persistent across frames and must be explicitly released via
release_reservation(). Unreleased reservations auto-expire after 30 seconds (672 frames)
as a safety net.
"""

from __future__ import annotations
from typing import TYPE_CHECKING, Dict, Any, Optional, Set
from dataclasses import dataclass
from loguru import logger
from sc2.ids.unit_typeid import UnitTypeId

if TYPE_CHECKING:
    from bot.MyBot import MyBot


@dataclass
class Reservation:
    """
    Persistent resource reservation that spans multiple frames.

    Used to reserve resources for actions that may not execute spending
    commands in the same frame as the reservation.
    """
    id: int
    minerals: int
    vespene: int
    supply: int
    frame_created: int
    purpose: str  # Description of what this reservation is for (logging)


class VirtualResourceManager:
    """
    Tracks virtual resource balances with persistent reservations across frames.

    Reservations persist until explicitly released or timed out (30s). Each frame,
    reset_to_actual() resets to real game resources then re-applies all active
    reservations, so unreleased reservations continue blocking those resources.

    Usage:
        # Reserve resources and get a reservation ID:
        res_id = game_state.vrm.reserve(UnitTypeId.MARINE, purpose="train marine")
        if res_id is not None:
            structure.train(UnitTypeId.MARINE)
            game_state.vrm.release_reservation(res_id)  # mark for release next frame
    """

    def __init__(self, game_state: 'MyBot'):
        """Initialize the virtual resource manager."""
        self.game_state = game_state

        # Virtual balances (updated each frame)
        self.virtual_minerals: int = 0
        self.virtual_vespene: int = 0
        self.virtual_supply_left: int = 0

        # Persistent reservation tracking (spans multiple frames)
        self._next_reservation_id: int = 0
        self.active_reservations: Dict[int, Reservation] = {}
        self.reservations_to_release: Set[int] = set()  # IDs marked for release at next frame

        # Tracking for debugging
        self.reservations_this_frame: list[Dict[str, Any]] = []

    def reset_to_actual(self) -> None:
        """
        Reset virtual balances to match actual game state.

        Called at the start of each frame, before any bot logic runs.

        Processes:
        1. Release reservations marked for release via release_reservation()
        2. Auto-release timed-out reservations (30 seconds = 672 frames)
        3. Reset virtual balances to actual game state
        4. Re-apply remaining active reservations (reduces virtual balances)
        5. Log critical error if virtual resources go negative
        """
        current_frame = self.game_state.state.game_loop

        # Step 1: Process reservations marked for release
        for reservation_id in self.reservations_to_release:
            if reservation_id in self.active_reservations:
                reservation = self.active_reservations[reservation_id]
                logger.debug(
                    f"Released reservation {reservation_id}: "
                    f"M={reservation.minerals}, V={reservation.vespene}, S={reservation.supply} "
                    f"(purpose: {reservation.purpose})"
                )
                del self.active_reservations[reservation_id]
        self.reservations_to_release.clear()

        # Step 2: Auto-release timed-out reservations (30 seconds = 672 frames)
        TIMEOUT_FRAMES = 672
        timed_out_ids = [
            res_id for res_id, res in self.active_reservations.items()
            if current_frame - res.frame_created >= TIMEOUT_FRAMES
        ]

        for reservation_id in timed_out_ids:
            reservation = self.active_reservations[reservation_id]
            logger.warning(
                f"Auto-released timed-out reservation {reservation_id} "
                f"(age: {current_frame - reservation.frame_created} frames, "
                f"purpose: {reservation.purpose})"
            )
            del self.active_reservations[reservation_id]

        # Step 3: Reset virtual balances to actual game state
        self.virtual_minerals = self.game_state.minerals
        self.virtual_vespene = self.game_state.vespene
        self.virtual_supply_left = self.game_state.supply_left

        # Step 4: Re-apply remaining active reservations
        for reservation in self.active_reservations.values():
            self.virtual_minerals -= reservation.minerals
            self.virtual_vespene -= reservation.vespene
            self.virtual_supply_left -= reservation.supply

        # Step 5: Check for negative virtual resources (CRITICAL ERROR)
        if self.virtual_minerals < 0 or self.virtual_vespene < 0 or self.virtual_supply_left < 0:
            error_resources = []
            if self.virtual_minerals < 0:
                error_resources.append(f"Minerals: {self.virtual_minerals}")
            if self.virtual_vespene < 0:
                error_resources.append(f"Vespene: {self.virtual_vespene}")
            if self.virtual_supply_left < 0:
                error_resources.append(f"Supply: {self.virtual_supply_left}")

            # Build reservation summary for debugging
            reservation_summary = []
            for res_id, res in self.active_reservations.items():
                reservation_summary.append(
                    f"  ID {res_id}: M={res.minerals}, V={res.vespene}, S={res.supply}, "
                    f"age={current_frame - res.frame_created}f, purpose='{res.purpose}'"
                )

            logger.critical(
                f"VIRTUAL RESOURCES WENT NEGATIVE! "
                f"Actual: M={self.game_state.minerals}, V={self.game_state.vespene}, S={self.game_state.supply_left} | "
                f"Negative resources: {', '.join(error_resources)} | "
                f"Active reservations ({len(self.active_reservations)}):\n" +
                "\n".join(reservation_summary)
            )

        # Clear frame-only tracking
        self.reservations_this_frame.clear()

        logger.debug(
            f"VirtualResourceManager reset: "
            f"M={self.virtual_minerals}, "
            f"V={self.virtual_vespene}, "
            f"Supply={self.virtual_supply_left}, "
            f"Active reservations: {len(self.active_reservations)}"
        )

    def can_afford_safe(self, item: UnitTypeId, check_supply: bool = True) -> bool:
        """
        Check if we can afford an item using virtual balance.

        Args:
            item: Unit or structure type to check
            check_supply: Whether to check supply availability

        Returns:
            True if affordable with current virtual balance
        """
        cost = self.game_state.calculate_cost(item)

        # Check resources
        if self.virtual_minerals < cost.minerals:
            return False
        if self.virtual_vespene < cost.vespene:
            return False

        # Check supply if requested
        if check_supply:
            supply_cost = self.game_state.calculate_supply_cost(item)
            if supply_cost > 0 and self.virtual_supply_left < supply_cost:
                return False

        return True

    def can_afford_safe_explicit(self, minerals: int, vespene: int, supply: int = 0) -> bool:
        """
        Check if we can afford explicit resource amounts using virtual balance.

        Use this for items where calculate_cost() returns incorrect values
        (e.g., abilities whose cost lookup returns 0/0).

        Args:
            minerals: Mineral cost to check
            vespene: Vespene cost to check
            supply: Supply cost to check (default 0)

        Returns:
            True if affordable with current virtual balance
        """
        if self.virtual_minerals < minerals:
            return False
        if self.virtual_vespene < vespene:
            return False
        if supply > 0 and self.virtual_supply_left < supply:
            return False

        return True

    def reserve(self, item: UnitTypeId, quantity: int = 1, reserve_supply: bool = True, purpose: str = "unspecified") -> Optional[int]:
        """
        Reserve resources for an item, creating a persistent reservation.

        Args:
            item: Unit or structure type to reserve resources for
            quantity: Number of units to reserve for
            reserve_supply: Whether to reserve supply
            purpose: Description of what this reservation is for (for debugging)

        Returns:
            Reservation ID if successful, None if insufficient resources
        """
        cost = self.game_state.calculate_cost(item)
        supply_cost = self.game_state.calculate_supply_cost(item) if reserve_supply else 0

        total_minerals = cost.minerals * quantity
        total_vespene = cost.vespene * quantity
        total_supply = supply_cost * quantity

        # Check affordability
        if self.virtual_minerals < total_minerals:
            logger.warning(
                f"Cannot reserve {quantity}x {item.name}: "
                f"Need {total_minerals} minerals, have {self.virtual_minerals}"
            )
            return None

        if self.virtual_vespene < total_vespene:
            logger.warning(
                f"Cannot reserve {quantity}x {item.name}: "
                f"Need {total_vespene} vespene, have {self.virtual_vespene}"
            )
            return None

        if reserve_supply and self.virtual_supply_left < total_supply:
            # Even if reserve_supply is True, if an item costs NO supply, then virtual supply deficit doesn't matter
            if total_supply > 0:
                logger.warning(
                    f"Cannot reserve {quantity}x {item.name}: "
                    f"Need {total_supply} supply, have {self.virtual_supply_left}"
                )
                return None

        # Create persistent reservation
        reservation_id = self._next_reservation_id
        self._next_reservation_id += 1

        reservation = Reservation(
            id=reservation_id,
            minerals=total_minerals,
            vespene=total_vespene,
            supply=total_supply,
            frame_created=self.game_state.state.game_loop,
            purpose=purpose,
        )

        self.active_reservations[reservation_id] = reservation

        # Deduct from virtual balance
        self.virtual_minerals -= total_minerals
        self.virtual_vespene -= total_vespene
        if reserve_supply:
            self.virtual_supply_left -= total_supply

        # Track for frame-only debugging
        self.reservations_this_frame.append({
            'item': item.name,
            'quantity': quantity,
            'minerals': total_minerals,
            'vespene': total_vespene,
            'supply': total_supply,
            'reservation_id': reservation_id,
            'purpose': purpose,
        })

        logger.debug(
            f"Reserved {quantity}x {item.name} (ID={reservation_id}, purpose='{purpose}'): "
            f"-{total_minerals}M, -{total_vespene}V, -{total_supply}S | "
            f"Virtual balance: M={self.virtual_minerals}, "
            f"V={self.virtual_vespene}, S={self.virtual_supply_left}"
        )

        return reservation_id

    def reserve_explicit(self, minerals: int, vespene: int, supply: int, purpose: str = "unspecified") -> Optional[int]:
        """
        Reserve explicit amounts of resources, creating a persistent reservation.

        Use this for custom cost scenarios (e.g., retry builds with 0 cost).

        Args:
            minerals: Mineral cost to reserve
            vespene: Vespene cost to reserve
            supply: Supply to reserve
            purpose: Description of what this reservation is for (for debugging)

        Returns:
            Reservation ID if successful, None if insufficient resources
        """
        # Check affordability (only if cost is non-zero. Zero cost should pass even if the virtual_resource is negative)
        if self.virtual_minerals < minerals and minerals > 0:
            logger.warning(
                f"Cannot reserve explicit resources: "
                f"Need {minerals} minerals, have {self.virtual_minerals}"
            )
            return None

        if self.virtual_vespene < vespene and vespene > 0:
            logger.warning(
                f"Cannot reserve explicit resources: "
                f"Need {vespene} vespene, have {self.virtual_vespene}"
            )
            return None

        if self.virtual_supply_left < supply and supply > 0:
            logger.warning(
                f"Cannot reserve explicit resources: "
                f"Need {supply} supply, have {self.virtual_supply_left}"
            )
            return None

        # Create persistent reservation
        reservation_id = self._next_reservation_id
        self._next_reservation_id += 1

        reservation = Reservation(
            id=reservation_id,
            minerals=minerals,
            vespene=vespene,
            supply=supply,
            frame_created=self.game_state.state.game_loop,
            purpose=purpose,
        )

        self.active_reservations[reservation_id] = reservation

        # Deduct from virtual balance
        self.virtual_minerals -= minerals
        self.virtual_vespene -= vespene
        self.virtual_supply_left -= supply

        # Track for frame-only debugging
        self.reservations_this_frame.append({
            'item': 'EXPLICIT',
            'quantity': 1,
            'minerals': minerals,
            'vespene': vespene,
            'supply': supply,
            'reservation_id': reservation_id,
            'purpose': purpose,
        })

        logger.debug(
            f"Reserved explicit resources (ID={reservation_id}, purpose='{purpose}'): "
            f"-{minerals}M, -{vespene}V, -{supply}S | "
            f"Virtual balance: M={self.virtual_minerals}, "
            f"V={self.virtual_vespene}, S={self.virtual_supply_left}"
        )

        return reservation_id

    def release_reservation(self, reservation_id: int) -> None:
        """
        Mark a reservation for release at the start of the next frame.

        This delayed release prevents overspending bugs by ensuring the
        resource deduction persists until the next frame starts.

        Safe to call multiple times with the same ID (idempotent).

        Args:
            reservation_id: ID of the reservation to release
        """
        # Check if reservation exists
        if reservation_id not in self.active_reservations:
            # Already released or never existed - this is safe, just log debug
            logger.debug(f"Attempted to release non-existent reservation {reservation_id}")
            return

        # Mark for release at next frame
        self.reservations_to_release.add(reservation_id)

        reservation = self.active_reservations[reservation_id]
        logger.debug(
            f"Marked reservation {reservation_id} for release at next frame "
            f"(M={reservation.minerals}, V={reservation.vespene}, S={reservation.supply}, "
            f"purpose='{reservation.purpose}')"
        )

    def get_status(self) -> Dict[str, Any]:
        """Get current virtual resource status for debugging."""
        current_frame = self.game_state.state.game_loop
        return {
            'virtual_minerals': self.virtual_minerals,
            'virtual_vespene': self.virtual_vespene,
            'virtual_supply_left': self.virtual_supply_left,
            'actual_minerals': self.game_state.minerals,
            'actual_vespene': self.game_state.vespene,
            'actual_supply_left': self.game_state.supply_left,
            'active_reservations': {
                res_id: {
                    'minerals': res.minerals,
                    'vespene': res.vespene,
                    'supply': res.supply,
                    'age_frames': current_frame - res.frame_created,
                    'purpose': res.purpose,
                    'pending_release': res_id in self.reservations_to_release,
                }
                for res_id, res in self.active_reservations.items()
            },
            'reservations_this_frame': self.reservations_this_frame,
        }
