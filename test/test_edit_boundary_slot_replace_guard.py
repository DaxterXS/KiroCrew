"""expected_slot pin on the two edit-boundary endpoints (#8988).

Both edit context-boundary endpoints -- rewind and edit-resend -- dispatch the
destructive history rewrite to a worker thread and, on main, validate the slot's
OBJECT identity only AFTER the shielded write has landed. The save's only
pre-write routing guard is ``expected_history_key``, and a same-name
close-and-recreate keeps the SAME ``slot_history_key`` (the transcript key is
derived from routing, not from the object), so that guard waves the replacement
through. The truncating write then lands on the REPLACEMENT conversation's
transcript, and a rewrite has no archive for the overwritten rows
(``_archive_dropped_lines`` archives the OLD slot's dropped tail, not the
replacement's), so the loss is unrecoverable. The 503 that the post-save check
raises tells the client to retry the edit, not that another conversation lost
data.

The fix threads a new opt-in ``expected_slot`` guard through
``_save_slot_to_history`` (and ``save_slot_off_loop``), checked inside the same
pre-write snapshot stretch as ``expected_history_key`` / ``expected_disk_older_count``
and refusing the same way (``return False``, nothing written) when
``state._slots.get(slot.key)`` is no longer the object the caller authorized.

Each test drives the REAL save with a double that performs the close-and-recreate
(replaces ``state._slots[name]`` with a fresh object under the same name) and
then delegates to the real save, so the refusal comes from the production guard,
not a stub. RED before the fix: the save commits the truncation and the endpoint
returns success. GREEN after: the save refuses, the endpoint returns 503, and the
replacement's transcript on disk is intact.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from chat_test_helpers import _make_state

from kiro_crew.dashboard import chat_persistence
from kiro_crew.dashboard.chat_persistence import _save_slot_to_history as _real_save_to_history
from kiro_crew.dashboard.chat_persistence import save_slot_off_loop as _real_save_off_loop
from kiro_crew.dashboard.chat_regenerate import api_chat_slot_edit_resend
from kiro_crew.dashboard.chat_rewind import api_chat_slot_rewind
from kiro_crew.dashboard.chat_utils import slot_history_key


def _populate(state, key="src"):
    """A slot with four visible messages (u/a/u/a), drained to disk."""
    slot = state.get_or_create_slot(key)
    slot.append("user", "first question", "msg msg-u", ts="2026-05-21T16:00:00Z")
    slot.append("assistant", "first answer", "msg msg-a", ts="2026-05-21T16:00:01Z")
    slot.append("user", "second question", "msg msg-u", ts="2026-05-21T16:00:02Z")
    slot.append("assistant", "second answer", "msg msg-a", ts="2026-05-21T16:00:03Z")
    slot.drain()
    return slot


def _recreate_under_same_name(state, name):
    """Close-and-recreate: swap in a FRESH slot object under the same name.

    Returns the replacement, holding its own distinct conversation persisted to
    disk. The replacement keeps the same ``slot_history_key`` (routing-derived),
    so only the OBJECT identity distinguishes it from the original.
    """
    replacement = chat_persistence._ChatSlot(name)
    replacement.append("user", "REPLACEMENT keep me", "msg msg-r", ts="2026-05-21T17:00:00Z")
    replacement.append("assistant", "replacement reply", "msg msg-r2", ts="2026-05-21T17:00:01Z")
    replacement.drain()
    state._slots[name] = replacement
    # Land the replacement's rows on the shared transcript file, so a rewind
    # that overwrites it (the pre-fix behaviour) has real data to destroy.
    # Uses the synchronous save directly: the caller may already be on a worker
    # thread, where the loop-dispatching wrapper cannot run.
    _real_save_to_history(state, replacement, force=True)
    return replacement


@pytest.fixture(autouse=True)
def _no_backend(monkeypatch):
    """No real kiro-cli turn on either boundary path."""
    monkeypatch.setattr("kiro_crew.dashboard.chat_rewind._run_chat", AsyncMock(return_value=None))
    monkeypatch.setattr(
        "kiro_crew.dashboard.chat_regenerate._run_chat", AsyncMock(return_value=None)
    )


class TestRewindRefusesSlotReplace:
    """POST /api/chat/slots/{slot}/rewind."""

    @pytest.mark.asyncio
    async def test_same_name_recreate_refuses_and_leaves_transcript_intact(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr("kiro_crew.dashboard.state.config_dir", lambda: tmp_path)
        state = _make_state(tmp_path)
        slot = _populate(state, "src")
        state.sessions.discard_conversation = AsyncMock(return_value=True)
        state.sessions._session_map.get = MagicMock(return_value="")
        history_key = slot_history_key(slot)

        captured = {}

        def _replacing_save(st, target, *args, **kwargs):
            # A close-and-recreate lands under the same name before the write.
            _recreate_under_same_name(st, target.key)
            captured["expected_slot"] = kwargs.get("expected_slot")
            return _real_save_to_history(st, target, *args, **kwargs)

        monkeypatch.setattr(
            "kiro_crew.dashboard.chat_rewind._save_slot_to_history", _replacing_save
        )

        app = web.Application()
        app["state"] = state
        app.router.add_post("/api/chat/slots/{slot}/rewind", api_chat_slot_rewind)
        async with TestClient(TestServer(app)) as client:
            resp = await client.post(
                "/api/chat/slots/src/rewind",
                json={"at_message_index": 0, "content": "edited first question"},
            )
            status = resp.status
            body = await resp.json()

        # The save refused: the endpoint reports a retryable failure, never 200.
        assert status == 503
        assert body["code"] in {"rewind_save_failed", "rewind_slot_rebound"}
        # The guard was reached against the ORIGINAL slot object.
        assert captured["expected_slot"] is slot
        # The replacement's transcript on disk was NOT truncated: its own rows,
        # which a landed rewind would have overwritten, survive.
        persisted = state.conversation_log.read_messages(history_key)
        contents = [m["content"] for m in persisted]
        assert "REPLACEMENT keep me" in contents
        assert "edited first question" not in contents

    @pytest.mark.asyncio
    async def test_unchanged_slot_still_commits(self, tmp_path, monkeypatch):
        """The guard must not refuse the normal case: no replacement, the
        rewind commits as before."""
        monkeypatch.setattr("kiro_crew.dashboard.state.config_dir", lambda: tmp_path)
        state = _make_state(tmp_path)
        slot = _populate(state, "src")
        state.sessions.discard_conversation = AsyncMock(return_value=True)
        state.sessions._session_map.get = MagicMock(return_value="")

        app = web.Application()
        app["state"] = state
        app.router.add_post("/api/chat/slots/{slot}/rewind", api_chat_slot_rewind)
        async with TestClient(TestServer(app)) as client:
            resp = await client.post(
                "/api/chat/slots/src/rewind",
                json={"at_message_index": 0, "content": "edited first question"},
            )
            assert resp.status == 200
            assert (await resp.json())["ok"] is True
        assert [m["role"] for m in slot.messages] == ["user"]
        assert slot.messages[0]["content"] == "edited first question"
        if slot.task:
            slot.task.cancel()


class TestEditResendRefusesSlotReplace:
    """POST /api/chat/slots/{slot}/edit-resend."""

    @pytest.mark.asyncio
    async def test_same_name_recreate_refuses_and_leaves_transcript_intact(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr("kiro_crew.dashboard.state.config_dir", lambda: tmp_path)
        state = _make_state(tmp_path)
        slot = _populate(state, "s1")
        state.sessions.discard_conversation = AsyncMock(return_value=True)
        state.sessions.aflush = AsyncMock()
        state.sessions._session_map.get = MagicMock(return_value="")
        history_key = slot_history_key(slot)

        captured = {}

        async def _replacing_save(st, target, *args, **kwargs):
            _recreate_under_same_name(st, target.key)
            captured["expected_slot"] = kwargs.get("expected_slot")
            return await _real_save_off_loop(st, target, *args, **kwargs)

        monkeypatch.setattr(
            "kiro_crew.dashboard.chat_regenerate.save_slot_off_loop", _replacing_save
        )

        app = web.Application()
        app["state"] = state
        app.router.add_post("/api/chat/slots/{slot}/edit-resend", api_chat_slot_edit_resend)
        async with TestClient(TestServer(app)) as client:
            resp = await client.post(
                "/api/chat/slots/s1/edit-resend",
                json={"index": 0, "content": "edited first question"},
            )
            status = resp.status
            body = await resp.json()

        assert status == 503
        assert body["code"] in {
            "edit_resend_save_failed",
            "edit_resend_slot_rebound",
        }
        assert captured["expected_slot"] is slot
        persisted = state.conversation_log.read_messages(history_key)
        contents = [m["content"] for m in persisted]
        assert "REPLACEMENT keep me" in contents
        assert "edited first question" not in contents

    @pytest.mark.asyncio
    async def test_unchanged_slot_still_commits(self, tmp_path, monkeypatch):
        """No replacement: edit-resend commits the edited window as before."""
        monkeypatch.setattr("kiro_crew.dashboard.state.config_dir", lambda: tmp_path)
        state = _make_state(tmp_path)
        slot = _populate(state, "s1")
        state.sessions.discard_conversation = AsyncMock(return_value=True)
        state.sessions.aflush = AsyncMock()
        state.sessions._session_map.get = MagicMock(return_value="")

        app = web.Application()
        app["state"] = state
        app.router.add_post("/api/chat/slots/{slot}/edit-resend", api_chat_slot_edit_resend)
        async with TestClient(TestServer(app)) as client:
            resp = await client.post(
                "/api/chat/slots/s1/edit-resend",
                json={"index": 0, "content": "edited first question"},
            )
            assert resp.status == 200
            assert (await resp.json())["ok"] is True
        assert slot.messages[0]["content"] == "edited first question"
        if slot.task:
            slot.task.cancel()


class TestInLockRecheckClosesTheLockWaitWindow:
    """The object-identity guard is re-read INSIDE ``_locked``, not only at the
    pre-lock snapshot.

    The patient lock acquire is itself an await, so a same-name recreate can
    commit ahead of a stale save while it waits for the lock -- past the pre-lock
    check but before the write. The in-lock delete-won guard cannot catch it: a
    recreate that resumes the same transcript preserves ``created_at``. This
    drives ``_save_slot_to_history`` directly with the slot present at the
    pre-lock check and swapped from INSIDE the locked region (via a
    ``get_metadata_status`` side effect, which the save calls under the lock
    before the write), proving the in-lock recheck -- not the pre-lock early-out
    -- is what refuses.
    """

    def test_recheck_inside_lock_refuses_when_swap_lands_after_pre_lock_check(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr("kiro_crew.dashboard.state.config_dir", lambda: tmp_path)
        state = _make_state(tmp_path)
        slot = _populate(state, "src")
        history_key = slot_history_key(slot)

        real_status = state.conversation_log.get_metadata_status
        swapped = {"done": False}

        def _swap_inside_lock(key):
            # Runs INSIDE ``_locked(history_key)``, before the in-lock recheck
            # and the write. The slot was still ``slot`` at the pre-lock check,
            # so only the in-lock guard can catch this swap.
            if key == history_key and not swapped["done"]:
                swapped["done"] = True
                _recreate_under_same_name(state, "src")
            return real_status(key)

        monkeypatch.setattr(state.conversation_log, "get_metadata_status", _swap_inside_lock)

        saved = _real_save_to_history(
            state,
            slot,
            [{"role": "user", "content": "edited"}],
            expected_history_key=history_key,
            expected_slot=slot,
        )

        # The swap happened inside the lock; the in-lock recheck refused.
        assert swapped["done"] is True
        assert saved is False
        # The replacement's rows survive; the edited window never landed.
        persisted = state.conversation_log.read_messages(history_key)
        contents = [m["content"] for m in persisted]
        assert "REPLACEMENT keep me" in contents
        assert "edited" not in contents


class TestPeriodicFlushRefusesReplacedPendingRewriteSlot:
    """The periodic dirty-slot flush (`flush_slot_now`) now passes `expected_slot`
    too (#8988 GPT round).

    `_flush_dirty_slots` captures a slot, then the save AWAITS the transcript
    lock -- from that moment it holds the OLD object while `state._slots[key]`
    can already have moved to a same-name recreate. A slot left in
    `_pending_rewrite` (rewind / regenerate / a failed inline rewrite) forces the
    destructive rewrite branch, so without the guard this periodic writer would
    truncate the REPLACEMENT's transcript with no archive. This drives the REAL
    `flush_slot_now` on such a slot and swaps the replacement in from inside the
    locked region, proving the flush refuses and the replacement survives.
    """

    def test_flush_of_a_pending_rewrite_slot_refuses_when_replaced_mid_write(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr("kiro_crew.dashboard.state.config_dir", lambda: tmp_path)
        state = _make_state(tmp_path)
        slot = _populate(state, "src")
        history_key = slot_history_key(slot)
        # Leave the slot owing a truncating rewrite, exactly as a rewind does.
        del slot.messages[1:]
        slot._dirty = True
        slot._resumed_count = 0
        slot._pending_rewrite = True

        real_status = state.conversation_log.get_metadata_status
        swapped = {"done": False}

        def _swap_inside_lock(key):
            # Runs INSIDE _locked(history_key), before the in-lock recheck and
            # the write: the same-name recreate the flush's lock-await window
            # exposes.
            if key == history_key and not swapped["done"]:
                swapped["done"] = True
                _recreate_under_same_name(state, "src")
            return real_status(key)

        monkeypatch.setattr(state.conversation_log, "get_metadata_status", _swap_inside_lock)

        # The real periodic single-slot flush, on the ORIGINAL slot object.
        state.flush_slot_now(slot)

        assert swapped["done"] is True
        # The guard refused the write (nothing persisted for the stale object).
        # The replacement's transcript on disk is intact; the stale window never
        # truncated it -- which is the data-loss property this closes. (The old
        # object's own _dirty state is moot: it has been popped from state._slots
        # by the recreate, so no later flush ever visits it again.)
        persisted = [m["content"] for m in state.conversation_log.read_messages(history_key)]
        assert "REPLACEMENT keep me" in persisted
        assert "replacement reply" in persisted

    def test_refused_flush_keeps_dirty_set_so_a_restored_slot_is_retried(
        self, tmp_path, monkeypatch
    ):
        """A refused flush must NOT clear _dirty (the GPT round-2 bug).

        `flush_slot_now` clears _dirty on any non-exception return. The
        `expected_slot` guard makes the save return `False` (nothing written)
        when the live `_slots[key]` is not this object -- the shape a close arm
        leaves when it has popped the slot and its own save then fails, before it
        restores the slot for a later flush to persist. If the refused flush
        cleared _dirty, that later flush would skip the restored slot and its rows
        would die on restart. The fix clears _dirty only on a written save, so a
        refusal leaves _dirty set and the restored slot is retried.
        """
        monkeypatch.setattr("kiro_crew.dashboard.state.config_dir", lambda: tmp_path)
        state = _make_state(tmp_path)
        slot = _populate(state, "src")
        slot._dirty = True
        slot._pending_rewrite = True
        # The live entry under this name is a DIFFERENT object, so the save's
        # expected_slot guard refuses this flush (returns False, writes nothing).
        other = chat_persistence._ChatSlot("src")
        state._slots["src"] = other

        state.flush_slot_now(slot)

        # Refused -> nothing written -> _dirty MUST remain set so the retry stands.
        assert slot._dirty is True

    def test_written_flush_clears_dirty(self, tmp_path, monkeypatch):
        """The happy path is unchanged: a flush that writes clears _dirty."""
        monkeypatch.setattr("kiro_crew.dashboard.state.config_dir", lambda: tmp_path)
        state = _make_state(tmp_path)
        slot = _populate(state, "src")
        slot._dirty = True

        state.flush_slot_now(slot)

        # The slot is the live entry, the guard passes, the save writes, dirty clears.
        assert slot._dirty is False

    def test_delete_won_refusal_on_a_current_slot_clears_dirty(self, tmp_path, monkeypatch):
        """A delete-won refusal on a slot STILL in _slots must clear _dirty.

        The other half of the "retry me" vs "never again" split (GPT round-3).
        The delete-won guard returns False (nothing written) for a slot the
        cleanup could not pop, so it is still `state._slots[key]` and the periodic
        loop would hand it back every 5s forever. The session is gone -- nothing
        left to persist -- so the flush clears _dirty (the retry is doomed, not
        deferred) even though the save wrote nothing. This is the case
        `persisted or is_current` clears while the replaced-object case above
        keeps.
        """
        monkeypatch.setattr("kiro_crew.dashboard.state.config_dir", lambda: tmp_path)
        state = _make_state(tmp_path)
        slot = _populate(state, "src")
        slot._dirty = True

        # slot IS the live entry (never replaced), so is_current is True. Force
        # the underlying save to refuse WITHOUT writing, standing in for the
        # in-lock delete-won return: identity matches, but the write is declined.
        def _refuse(_owner, _slot, **_kw):
            return False

        from kiro_crew.dashboard.state import _persistence_for

        _persistence_for(state)._slot_saver_provider = lambda: _refuse

        state.flush_slot_now(slot)

        # is_current is True -> a doomed (delete-won) refusal clears _dirty rather
        # than retrying the gone session forever.
        assert state._slots.get("src") is slot
        assert slot._dirty is False
