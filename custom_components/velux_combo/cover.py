"""Cover platform for the Velux Combo integration.

A Velux Combo cover pairs a roof window and its store (roller shutter).
Sequencing is enforced on every command:

- ``async_open_cover``: the store opens first, then the window opens. This
  prevents wind drafts and keeps rain off the window while it is opened.
- ``async_close_cover``: the window closes first, then the store closes, so
  the window is never left open while the store rolls down.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.components.cover import CoverDeviceClass, CoverEntity, CoverEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    SERVICE_CLOSE_COVER,
    SERVICE_OPEN_COVER,
    SERVICE_STOP_COVER,
    STATE_CLOSED,
    STATE_CLOSING,
    STATE_OPEN,
    STATE_OPENING,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from .const import CONF_STORE_ENTITY, CONF_WINDOW_ENTITY, DEFAULT_TIMEOUT

_LOGGER = logging.getLogger(__name__)

SUPPORTED_FEATURES = (
    CoverEntityFeature.OPEN
    | CoverEntityFeature.CLOSE
    | CoverEntityFeature.STOP
)

_MOVING_STATES = {STATE_OPENING, STATE_CLOSING}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Velux Combo covers from a config entry."""
    async_add_entities([SequenceCover(hass, entry)], update_before_add=True)


class SequenceCover(CoverEntity):
    """A cover that drives a window and its store in sequence."""

    _attr_device_class = CoverDeviceClass.WINDOW
    _attr_supported_features = SUPPORTED_FEATURES

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the cover."""
        self._window_entity: str = entry.data[CONF_WINDOW_ENTITY]
        self._store_entity: str = entry.data[CONF_STORE_ENTITY]

        self._attr_unique_id = entry.entry_id
        self._attr_name = entry.title

        self._lock = asyncio.Lock()
        self._task: asyncio.Task | None = None
        self._stop_requested = False

    async def async_added_to_hass(self) -> None:
        """Register listeners so state updates are reflected immediately."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_state_change_event(
                self.hass,
                [self._window_entity, self._store_entity],
                self._async_on_child_change,
            )
        )

    @callback
    def _async_on_child_change(self, _: Event) -> None:
        """Refresh this cover when one of the child entities changes."""
        self.async_schedule_update_ha_state(True)

    async def async_update(self) -> None:
        """Derive this cover's state from the window and the store."""
        window = self._get_child_state(self._window_entity)
        store = self._get_child_state(self._store_entity)

        moving = _MOVING_STATES & {window, store}

        if moving == {STATE_OPENING}:
            self._attr_is_opening = True
            self._attr_is_closing = False
        elif moving == {STATE_CLOSING}:
            self._attr_is_opening = False
            self._attr_is_closing = True
        elif window == STATE_OPEN and store == STATE_OPEN:
            self._attr_is_open = True
            self._attr_is_closed = False
            self._attr_is_opening = False
            self._attr_is_closing = False
        elif window == STATE_CLOSED and store == STATE_CLOSED:
            self._attr_is_open = False
            self._attr_is_closed = True
            self._attr_is_opening = False
            self._attr_is_closing = False
        else:
            # Mixed or unknown states: report as neither fully open nor closed.
            self._attr_is_open = False
            self._attr_is_closed = False
            self._attr_is_opening = False
            self._attr_is_closing = False

        self._attr_current_cover_position = self._average_position()

        available = []
        for entity_id in (self._window_entity, self._store_entity):
            state = self.hass.states.get(entity_id)
            available.append(
                state is not None and state.state != STATE_UNAVAILABLE
            )
        self._attr_available = any(available)

    def _get_child_state(self, entity_id: str) -> str:
        """Return the raw state of a child entity."""
        state = self.hass.states.get(entity_id)
        return state.state if state else STATE_UNKNOWN

    def _average_position(self) -> int | None:
        """Average the position of the two child covers, if both report one."""
        positions = []
        for entity_id in (self._window_entity, self._store_entity):
            state = self.hass.states.get(entity_id)
            if state is None:
                continue
            position = state.attributes.get("current_position")
            if isinstance(position, (int, float)):
                positions.append(position)
        if not positions:
            return None
        return round(sum(positions) / len(positions))

    async def async_open_cover(self, **_kwargs: Any) -> None:
        """Open the store, then the window."""
        await self._run_sequence(opening=True)

    async def async_close_cover(self, **_kwargs: Any) -> None:
        """Close the window, then the store."""
        await self._run_sequence(opening=False)

    async def async_stop_cover(self, **_kwargs: Any) -> None:
        """Stop any running child and cancel a pending sequence."""
        self._stop_requested = True

        if self._task is not None:
            self._task.cancel()
            await asyncio.sleep(0)

        for entity_id in (self._window_entity, self._store_entity):
            state = self.hass.states.get(entity_id)
            if state and state.state in _MOVING_STATES:
                await self.hass.services.async_call(
                    "cover",
                    SERVICE_STOP_COVER,
                    {"entity_id": entity_id},
                    blocking=True,
                )

    async def _run_sequence(self, *, opening: bool) -> None:
        """Queue a sequence if none is already running."""
        if self._task is not None:
            _LOGGER.debug(
                "A sequence is already running for %s, ignoring request", self.name
            )
            return

        self._stop_requested = False
        self._task = asyncio.create_task(self._execute_sequence(opening=opening))

    async def _execute_sequence(self, *, opening: bool) -> None:
        """Run the two moves in order, waiting for each to complete."""
        try:
            async with self._lock:
                if opening:
                    first, second = self._store_entity, self._window_entity
                else:
                    first, second = self._window_entity, self._store_entity

                await self._move_entity(first, opening=opening)
                if self._stop_requested:
                    return
                await self._move_entity(second, opening=opening)
        except asyncio.CancelledError:
            raise
        finally:
            self._task = None
            self.async_write_ha_state()

    async def _move_entity(self, entity_id: str, *, opening: bool) -> None:
        """Move one child and wait for it to reach its target state."""
        target_state = STATE_OPEN if opening else STATE_CLOSED

        state = self.hass.states.get(entity_id)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            _LOGGER.warning(
                "Cannot %s %s: current state is %s",
                "open" if opening else "close",
                entity_id,
                state.state if state else None,
            )
            return

        if self._already_at_target(state, opening):
            return

        arrived = asyncio.Event()

        @callback
        def _on_arrival(event: Event) -> None:
            new_state: State | None = event.data.get("new_state")
            if new_state is None:
                return
            if new_state.state == target_state or self._stop_requested:
                arrived.set()

        unsubscribe = async_track_state_change_event(
            self.hass, [entity_id], _on_arrival
        )

        try:
            service = SERVICE_OPEN_COVER if opening else SERVICE_CLOSE_COVER
            await self.hass.services.async_call(
                "cover",
                service,
                {"entity_id": entity_id},
                blocking=False,
            )
            try:
                await asyncio.wait_for(arrived.wait(), timeout=DEFAULT_TIMEOUT)
            except asyncio.TimeoutError:
                _LOGGER.warning(
                    "Timeout waiting for %s to reach %s after %s seconds",
                    entity_id,
                    target_state,
                    DEFAULT_TIMEOUT,
                )
        finally:
            unsubscribe()

        self.async_schedule_update_ha_state(True)

    @staticmethod
    def _already_at_target(state: State, opening: bool) -> bool:
        """Return True when the child is already at the target position."""
        target_state = STATE_OPEN if opening else STATE_CLOSED
        if state.state == target_state:
            return True

        position = state.attributes.get("current_position")
        if not isinstance(position, (int, float)):
            return False
        if opening and position >= 99:
            return True
        if not opening and position <= 1:
            return True
        return False