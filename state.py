"""Central mutable state for the bot.

Bug fix #4 — previously these lived as module-level globals (`last_deleted`,
`last_alerts`, `last_refuel_user`, `dashboard_message`), which is unsafe
under concurrent task/interaction execution. This class serialises access
with an asyncio.Lock and gives cogs a single object to share.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Dict, List, Optional, Tuple

import discord

from config import STATE_FILE_PATH

log = logging.getLogger(__name__)


class StateManager:
    """Thread/async-safe container for cross-cog runtime state."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()

        # Last generator that was deleted (used by UndoButton).
        self.last_deleted: Optional[str] = None

        # Last person who refuelled each generator (used in alert-resolved msg).
        self.last_refuel_user: Dict[str, str] = {}

        # Currently outstanding alerts, keyed by generator name.
        # Value: {"state": str, "message": discord.Message}
        self.last_alerts: Dict[str, dict] = {}

        # Registered dashboard messages, keyed by channel_id.
        # Each entry stores the discord.Message so it can be edited on refresh.
        self.dashboard_messages: Dict[int, discord.Message] = {}

    # -----------------------------------------------------------------
    # Locking helpers — use `async with state.lock():` in cogs.
    # -----------------------------------------------------------------
    def lock(self) -> asyncio.Lock:
        return self._lock

    # -----------------------------------------------------------------
    # Convenience mutators
    # -----------------------------------------------------------------
    async def set_last_deleted(self, name: Optional[str]) -> None:
        async with self._lock:
            self.last_deleted = name

    async def pop_last_deleted(self) -> Optional[str]:
        async with self._lock:
            name = self.last_deleted
            self.last_deleted = None
            return name

    async def set_refuel_user(self, gen_name: str, user: str) -> None:
        async with self._lock:
            self.last_refuel_user[gen_name] = user

    async def get_refuel_user(self, gen_name: str) -> str:
        async with self._lock:
            return self.last_refuel_user.get(gen_name, "Unknown")

    async def clear_alerts(self) -> None:
        async with self._lock:
            self.last_alerts.clear()

    async def register_dashboard(
        self, channel_id: int, message: discord.Message
    ) -> None:
        async with self._lock:
            self.dashboard_messages[channel_id] = message
        # Persist outside the lock — file I/O is sync but the writes are tiny.
        self._persist_dashboards()

    async def all_dashboards(self) -> Dict[int, discord.Message]:
        async with self._lock:
            return dict(self.dashboard_messages)

    # -----------------------------------------------------------------
    # Persistence (backlog #1) — survives restarts.
    # -----------------------------------------------------------------
    def _persist_dashboards(self) -> None:
        try:
            payload = {
                "dashboards": [
                    {"channel_id": ch_id, "message_id": msg.id}
                    for ch_id, msg in self.dashboard_messages.items()
                ]
            }
            STATE_FILE_PATH.write_text(json.dumps(payload), encoding="utf-8")
        except OSError as e:
            log.warning("Could not write state file %s: %s", STATE_FILE_PATH, e)

    @staticmethod
    def load_persisted() -> List[Tuple[int, int]]:
        """Return stored (channel_id, message_id) pairs. Empty on any failure."""
        try:
            raw = STATE_FILE_PATH.read_text(encoding="utf-8")
        except FileNotFoundError:
            return []
        except OSError as e:
            log.warning("Could not read state file %s: %s", STATE_FILE_PATH, e)
            return []

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            log.warning("State file is not valid JSON: %s", e)
            return []

        return [
            (int(entry["channel_id"]), int(entry["message_id"]))
            for entry in data.get("dashboards", [])
            if "channel_id" in entry and "message_id" in entry
        ]


# Module-level singleton.
state = StateManager()
