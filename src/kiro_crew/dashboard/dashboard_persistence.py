"""Dashboard slot and context-snapshot persistence coordination.

The dashboard facade continues to own every mutable field used here.  This
component deliberately retains no slot map, dirty flag, lock, or task reference:
each operation reads the current value from its owner so existing direct access,
test replacement, and shutdown ordering remain valid after delegation.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Any

AtomicWriter = Callable[..., None]
JsonCodecProvider = Callable[[], Any]
SlotSaver = Callable[..., Any]


def _current_shutdown_event() -> Any:
    """Resolve the process shutdown event when a flush loop actually starts."""
    from kiro_crew import shutdown_event

    return shutdown_event


def _current_slot_saver() -> SlotSaver:
    """Resolve the re-export patched by existing flush characterizations."""
    from kiro_crew.dashboard.chat import _save_slot_to_history

    return _save_slot_to_history


class DashboardPersistenceCoordinator:
    """Coordinate durable dashboard state while the facade owns its data."""

    def __init__(
        self,
        *,
        config_dir_provider: Callable[[], Path],
        atomic_write_provider: Callable[[], AtomicWriter],
        logger_provider: Callable[[], logging.Logger],
        json_codec_provider: JsonCodecProvider,
        wall_time_provider: Callable[[], float],
        slot_saver_provider: Callable[[], SlotSaver] = _current_slot_saver,
        shutdown_event_provider: Callable[[], Any] = _current_shutdown_event,
    ) -> None:
        self._config_dir_provider = config_dir_provider
        self._atomic_write_provider = atomic_write_provider
        self._logger_provider = logger_provider
        self._json_codec_provider = json_codec_provider
        self._wall_time_provider = wall_time_provider
        self._slot_saver_provider = slot_saver_provider
        self._shutdown_event_provider = shutdown_event_provider

    @staticmethod
    def _owner_method(
        owner: Any,
        name: str,
        fallback: Callable[..., Any],
    ) -> Callable[..., Any]:
        """Resolve an instance-replaceable facade method for this call."""
        try:
            return getattr(owner, name)
        except AttributeError:
            return partial(fallback, owner)

    def start_flush_loop(self, owner: Any) -> None:
        """Start the five-second dirty-state flush loop once."""
        if owner._flush_task is None:
            flush_loop = self._owner_method(owner, "_flush_loop", self._flush_loop)
            owner._flush_task = asyncio.ensure_future(flush_loop())

    async def _flush_loop(self, owner: Any) -> None:
        """Periodically save dirty slots so a crash loses at most one interval."""
        shutdown_event = self._shutdown_event_provider()
        while not shutdown_event.is_set():
            try:
                await asyncio.wait_for(shutdown_event.wait(), timeout=owner._FLUSH_INTERVAL)
                return
            except asyncio.TimeoutError:
                pass
            # Resolve after every timeout. Tests and callers replace this facade
            # seam while a long-lived loop is already running.
            flush_dirty = self._owner_method(owner, "_flush_dirty_slots", self._flush_dirty_slots)
            await asyncio.get_running_loop().run_in_executor(None, flush_dirty)

    def flush_slot_now(self, owner: Any, slot: Any) -> None:
        """Write one dirty slot and clear only the generation that was saved."""
        # Endpoint metadata is applied to the live slot before its guarded
        # history write.  Do not let this unpinned periodic writer make that
        # provisional value durable while the guarded writer is still waiting.
        if getattr(slot, "_metadata_persist_inflight", 0):
            return
        if not owner.conversation_log or not slot._dirty or not slot.messages:
            return
        save_slot_to_history = self._slot_saver_provider()

        # Keep the dirty bit true for the whole save. chat_fork treats it as
        # "unpersisted state exists", and the history writer's resumed-slot
        # guard also reads it during the write. A generation comparison avoids
        # erasing a new dirty mark set concurrently by the event loop.
        generation = slot._dirty_gen
        try:
            # ``expected_slot=slot`` closes the same await-gap the boundary paths
            # carry, one level up: this periodic writer captures ``slot`` in the
            # ``_flush_dirty_slots`` loop and then AWAITS the transcript lock, so
            # from the executor thread it holds a reference to the old object
            # while the event loop can already have swapped ``state._slots[key]``
            # for a same-name close-and-recreate. A slot left in
            # ``_pending_rewrite`` (rewind / regenerate, or a failed inline
            # rewrite) forces the destructive rewrite branch here, so without the
            # guard this flush would truncate the REPLACEMENT's transcript with no
            # archive. The guard refuses (writes nothing) when the live slot under
            # this key is no longer this object; for the overwhelmingly common
            # case where it is unchanged the check is a GIL-atomic dict read that
            # passes, so a normal flush is unaffected.
            persisted = save_slot_to_history(owner, slot, expected_slot=slot)
        except Exception:
            # A failed write remains owed to the next periodic pass.
            self._logger_provider().warning("Flush failed for slot %s", slot.key, exc_info=True)
        else:
            # Clear the dirty bit when the write either LANDED or is never worth
            # retrying again. The save returns ``False`` without writing on three
            # distinct refusals, and they split by whether this slot is still the
            # live ``state._slots`` entry -- i.e. whether the periodic loop, which
            # iterates ``state._slots.values()``, will hand this same object back:
            #
            #   * ``expected_slot`` mismatch (pre-lock or in-lock): the object was
            #     REPLACED, so it is no longer ``state._slots[key]`` and the loop
            #     never revisits it. Keeping ``_dirty`` set is harmless (nothing
            #     re-flushes it) and is what lets a close arm's RESTORED slot --
            #     which is the current entry again, so its own flush writes and
            #     clears via ``persisted`` -- be retried rather than dropped.
            #   * delete-won: the session was permanently deleted while the save
            #     awaited the lock. This fires for a slot that is STILL
            #     ``state._slots[key]`` (a cron-linked tab the delete's cleanup
            #     could not pop), so the loop WOULD hand it back every 5s forever.
            #     There is nothing left to persist -- the session is gone -- so the
            #     retry is doomed, not deferred: clear the bit.
            #
            # ``persisted or is_current`` captures both: clear on a written save,
            # and clear a refusal whose slot is still current (delete-won, doomed),
            # while a refusal whose slot was replaced keeps the bit (moot for the
            # dead object, load-bearing for the restored one). A single boolean
            # return had hidden that "retry me" vs "never again" distinction; the
            # ``is`` check on the live entry is what recovers it. GIL-atomic dict
            # read + pointer compare, safe from this executor thread. The
            # generation comparison still guards a new dirty mark set concurrently
            # by the event loop.
            is_current = owner._slots.get(slot.key) is slot
            if (persisted or is_current) and slot._dirty_gen == generation:
                slot._dirty = False

    def _flush_dirty_slots(self, owner: Any) -> None:
        """Persist dirty transcripts, open tabs, then context snapshots."""
        if not owner.conversation_log:
            return

        for slot in list(owner._slots.values()):
            flush_slot_now = self._owner_method(owner, "flush_slot_now", self.flush_slot_now)
            flush_slot_now(slot)

        # Preserve the original ordering. Open tabs are the authoritative set
        # used to prune context snapshots, and both disk writes stay off-loop.
        persist_open_slots = self._owner_method(
            owner, "_persist_open_slots", self._persist_open_slots
        )
        persist_open_slots()
        persist_context_snapshots = self._owner_method(
            owner,
            "_persist_context_snapshots",
            self._persist_context_snapshots,
        )
        persist_context_snapshots()

    def _persist_open_slots(self, owner: Any) -> None:
        """Atomically snapshot the current persistent open-slot keys."""
        if owner.restoring_open_slots:
            self._logger_provider().debug("open_slots snapshot skipped: restore in progress")
            return
        try:
            path = self._config_dir_provider() / "open_slots.json"
            # Incognito, temporary, and future non-persistent modes must never
            # be resurrected by a later gateway process.
            keys = [
                name
                for name, slot in list(owner._slots.items())
                if getattr(slot, "memory_mode", "persistent") == "persistent"
            ]
            # A transient read failure during restore must not let the next
            # live-slot snapshot erase the unread key permanently. The restore
            # guard above also protects iteration from its sole mutator.
            seen = set(keys)
            keys.extend(
                key
                for key in getattr(owner, "unrestored_slot_keys", frozenset())
                if key not in seen
            )
            payload = self._json_codec_provider().dumps(
                {"keys": keys, "ts": self._wall_time_provider()}
            )
            # The canonical writer uses a unique temporary file, which avoids
            # collisions between the periodic and shutdown flush threads.
            self._atomic_write_provider()(path, payload, mode=0o600)
        except Exception:
            self._logger_provider().debug("Failed to persist open_slots.json", exc_info=True)

    def broadcast_context_usage(
        self,
        owner: Any,
        slot_key: str,
        payload: dict,
    ) -> None:
        """Broadcast one context reading and record its durable snapshot."""
        owner.broadcast_ws("context_usage", payload)
        slot = owner.get_slot(slot_key)
        if slot is None:
            return

        # WebSocket broadcast is invisible to SSE-only consumers. Feed the
        # identical payload to the slot queue as a wire-only frame before any
        # persistence eligibility checks.
        try:
            encoded = self._json_codec_provider().dumps(payload)
            slot.push_wire_frame("context_usage", encoded)
        except (TypeError, ValueError):
            pass

        if getattr(slot, "memory_mode", "persistent") != "persistent":
            return
        pct = payload.get("pct")
        if not isinstance(pct, (int, float)) or isinstance(pct, bool):
            return
        snapshot: dict[str, Any] = {"pct": pct, "model": slot.model}
        window = payload.get("window_tokens") or 0
        if window:
            snapshot["window_tokens"] = window
            snapshot["used_tokens"] = payload.get("used_tokens", 0)
        with owner._context_snapshots_lock:
            if owner._context_snapshots.get(slot_key) == snapshot:
                return
            owner._context_snapshots[slot_key] = snapshot
            owner._context_snapshots_dirty = True

    def ensure_context_snapshots_loaded(self, owner: Any) -> None:
        """Merge earlier-process snapshots into memory without overwriting live data."""
        with owner._context_snapshots_lock:
            if owner._context_snapshots_loaded:
                return
        try:
            raw = self._json_codec_provider().loads(
                (self._config_dir_provider() / "context_snapshots.json").read_text()
            )
        except FileNotFoundError:
            raw = {}
        except Exception:
            self._logger_provider().debug(
                "context_snapshots.json unreadable; starting empty",
                exc_info=True,
            )
            raw = {}
        if not isinstance(raw, dict):
            raw = {}
        with owner._context_snapshots_lock:
            if owner._context_snapshots_loaded:
                return
            for key, value in raw.items():
                if isinstance(key, str) and isinstance(value, dict):
                    owner._context_snapshots.setdefault(key, value)
            # Publish the loaded flag only after the merge, under the same lock.
            owner._context_snapshots_loaded = True

    @staticmethod
    def context_snapshot_for(owner: Any, slot_key: str) -> dict | None:
        """Return a detached copy of a slot's recorded context reading."""
        with owner._context_snapshots_lock:
            snapshot = owner._context_snapshots.get(slot_key)
            return dict(snapshot) if isinstance(snapshot, dict) else None

    def _persist_context_snapshots(self, owner: Any) -> None:
        """Prune and atomically write the current context-snapshot map."""
        if owner.restoring_open_slots:
            self._logger_provider().debug("context snapshot flush skipped: restore in progress")
            return
        with owner._context_snapshots_lock:
            if not owner._context_snapshots_dirty:
                return

        # Disk is merged before pruning so a new reading cannot overwrite
        # still-live readings left by an earlier process.
        ensure_loaded = self._owner_method(
            owner,
            "ensure_context_snapshots_loaded",
            self.ensure_context_snapshots_loaded,
        )
        ensure_loaded()

        # Serialize complete flushes. The data lock intentionally excludes IO,
        # but the flush lock prevents an older stalled write from landing after
        # a newer one and rolling the file back.
        with owner._context_snapshots_flush_lock:
            try:
                with owner._context_snapshots_lock:
                    owner._context_snapshots_dirty = False
                    live_keys = set(owner._slots)
                    for key in [key for key in owner._context_snapshots if key not in live_keys]:
                        del owner._context_snapshots[key]
                    payload = self._json_codec_provider().dumps(owner._context_snapshots)
                self._atomic_write_provider()(
                    self._config_dir_provider() / "context_snapshots.json",
                    payload,
                    mode=0o600,
                )
            except Exception:
                self._logger_provider().debug(
                    "Failed to persist context_snapshots.json", exc_info=True
                )
                with owner._context_snapshots_lock:
                    owner._context_snapshots_dirty = True
