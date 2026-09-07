"""POST /api/chat/slots must not report a failure for a create that committed.

The symptom (#8745): ``api_chat_slot_create`` finishes its body, the slot is in
``state._slots`` and its metadata is persisted, and only THEN does
``suspend_slots_push.__exit__`` flush the owed slots push. On the coalescing
window's leading edge that flush broadcasts synchronously, so an exception in it
escaped the handler and aiohttp rendered a 500 -- for a create that happened. The
user retries and gets a second session.

The broadcast serializes EVERY slot, so the evidenced fault (a non-serializable
value in slot state) fails a healthy create because some OTHER slot is poisoned.
These pin the handler-visible half of the containment: success, the slot present,
and no second slot needed.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from chat_test_helpers import _make_state

from kiro_crew.dashboard import chat_handlers


@pytest.fixture
def dashboard_state(tmp_path: Any) -> Any:
    return _make_state(tmp_path)


async def _post_create(state: Any, payload: dict[str, Any]) -> tuple[int, str]:
    """POST a create and return (status, body text).

    The body is read INSIDE the client's context: the response object is dead
    once the test server closes, so a caller reading it afterwards gets
    ClientConnectionError rather than the payload.
    """
    app = web.Application()
    app["state"] = state
    app.router.add_post("/api/chat/slots", chat_handlers.api_chat_slot_create)
    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/chat/slots", json=payload)
        return resp.status, await resp.text()


def _break_the_broadcast(state: Any) -> None:
    """Make the slots BROADCAST fail while every other path stays healthy.

    Patched at ``_broadcast`` -- the fan-out the announcement ends in -- rather
    than at ``serialize_slots``: the handler's own response serializes the
    created slot through ``serialize_slot``, so poisoning the shared projection
    would break that too and the test would pass for the wrong reason. This
    isolates the announcement, which is the step under test. The exception type
    mirrors the evidenced fault (a non-serializable value in slot state).
    """

    def _boom(note: Any) -> None:
        raise TypeError("Object of type object is not JSON serializable")

    state._broadcast = _boom  # type: ignore[method-assign]


@pytest.mark.asyncio
async def test_create_succeeds_when_the_slots_broadcast_fails(
    dashboard_state: Any, caplog: pytest.LogCaptureFixture
) -> None:
    """A broadcast failure must not turn a committed create into a 500."""
    _break_the_broadcast(dashboard_state)

    with caplog.at_level(logging.ERROR, logger="kiro_crew.dashboard.state"):
        status, text = await _post_create(dashboard_state, {"name": "committed"})

    assert status < 300, (
        "the slot create committed, so a failure announcing it must not be "
        f"reported as a failed create; got {status}: {text}"
    )
    assert "committed" in dashboard_state._slots, "the create really did commit"
    assert dashboard_state._slots_broadcast_drops >= 1, "the drop must be counted"
    assert any(
        "slots broadcast dropped" in r.getMessage() for r in caplog.records
    ), "contained is not silent: the drop must be logged"


@pytest.mark.asyncio
async def test_create_response_still_describes_the_new_slot(dashboard_state: Any) -> None:
    """The caller gets the slot it created, not an empty acknowledgement.

    A 200 whose body did not describe the new slot would be its own defect: the
    dashboard renders the created session from this payload.
    """
    _break_the_broadcast(dashboard_state)

    status, text = await _post_create(dashboard_state, {"name": "described"})

    assert status < 300
    assert json.loads(text).get("key") == "described"


@pytest.mark.asyncio
async def test_healthy_create_is_unchanged(dashboard_state: Any) -> None:
    """Benign control: nothing is dropped and nothing is logged on the happy path."""
    status, text = await _post_create(dashboard_state, {"name": "healthy"})

    assert status < 300, text
    assert "healthy" in dashboard_state._slots
    assert dashboard_state._slots_broadcast_drops == 0
