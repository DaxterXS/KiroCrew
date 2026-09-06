"""Dashboard read/write for the standing approval tier (a KEYSTONE leaf).

The tier lives in ``default_approval_mode.json``, not ``config.json``, because it
is a security ceiling rather than a preference -- see
``kiro_crew.default_approval_state`` for the full reasoning and
``security._CREW_SECRET_LEAVES`` for the enforcement.

This handler is the ONLY writer. It opens the path directly (via
``default_approval_state.save_mode`` -> ``atomic_write``) rather than going
through the agent tool gate, which is exactly what lets the operator's Settings
card write a file the agent's own file and bash tools are refused.
"""

from __future__ import annotations

import logging

from aiohttp import web

from kiro_crew import default_approval_state
from kiro_crew.dashboard.handlers._shared import _owner_denial_response
from kiro_crew.dashboard.handlers.source_providers import is_owner_dashboard_request

logger = logging.getLogger(__name__)

_ROUTE = "/api/security/default-approval-mode"


def _payload() -> dict:
    """The stored tier plus the offerable set, resolved through the clamp.

    ``mode`` is what a NEW session would actually start on right now, so the card
    renders server truth rather than the raw file contents: a hand-edited
    ``trust`` reads back as ``normal`` here for the same reason it is refused at
    apply time.
    """
    state = default_approval_state.load_state()
    mode = default_approval_state.load_mode(state)
    payload = {
        "mode": mode,
        "values": list(default_approval_state.DEFAULT_APPROVAL_MODES),
    }
    # The RAW stored value, present only when the clamp changed it. Without this the
    # card cannot tell "nothing is stored" from "something unpersistable is stored and
    # was ignored", because `mode` is clamped before it leaves the server -- the cue
    # that depends on it would be a branch that can never fire. The owner CAN reach
    # this state: the leaf is un-writable by the AGENT, not by the person who owns it,
    # so a hand-edited `trust` is exactly the case the cue exists for.
    raw = state.get(default_approval_state.STATE_KEY_MODE)
    if isinstance(raw, str) and raw.strip() and raw != mode:
        payload["stored"] = raw
    return payload


def _reject_non_owner(request: web.Request) -> "web.Response | None":
    """Refuse an app token AND a non-owner dashboard identity.

    Two checks rather than the one the ``computer_use.json`` sibling applies, and
    the difference is deliberate. ``request["user"]`` is truthy for an app token
    too, so the cookie check alone does not separate them -- that is the sibling's
    reason for the app-token guard and it holds here. But an allow-listed
    messaging identity carries a dashboard credential whose subject is not the
    owner and whose ``app`` claim is EMPTY, so the app-token guard alone would
    admit it. This write is a STANDING grant that applies to every session minted
    afterwards, so being authenticated is not enough to raise the floor.
    """
    if request.get("app"):
        return web.json_response(
            {"error": "app tokens cannot change the default approval mode", "code": "owner_only"},
            status=403,
        )
    if not is_owner_dashboard_request(request):
        return _owner_denial_response(request, "the default approval mode is owner-only")
    return None


async def api_default_approval_mode_get(request: web.Request) -> web.Response:
    """GET the standing tier. Owner-only: the value is reconnaissance.

    Knowing the stored tier tells a caller whether the sessions around it are
    already elevated, which is why the leaf is read-protected as well as
    write-protected. The read is gated the same way the write is.
    """
    denied = _reject_non_owner(request)
    if denied is not None:
        return denied
    return web.json_response(_payload())


async def api_default_approval_mode_save(request: web.Request) -> web.Response:
    """PUT the standing tier.

    Returns the refreshed GET payload so the card re-renders from server truth
    rather than from its own optimistic guess -- and so a value that the clamp
    rejects is visibly not what got stored.
    """
    denied = _reject_non_owner(request)
    if denied is not None:
        return denied
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid JSON body", "code": "bad_request"}, status=400)
    if not isinstance(body, dict):
        return web.json_response(
            {"error": "body must be an object", "code": "bad_request"}, status=400
        )
    mode = body.get("mode")
    # Validated against the PERSISTABLE set, so `trust` and `yolo` are refused
    # explicitly here rather than being silently clamped on the way in. The reader
    # clamps too; a caller that asks for a tier this store may not hold is told so.
    if not isinstance(mode, str) or mode not in default_approval_state.DEFAULT_APPROVAL_MODES:
        return web.json_response(
            {
                "error": f"mode must be one of {list(default_approval_state.DEFAULT_APPROVAL_MODES)}",
                "code": "bad_request",
            },
            status=400,
        )
    try:
        default_approval_state.save_mode(mode)
    except Exception as exc:
        logger.warning("writing the default-approval-mode keystone failed", exc_info=True)
        return web.json_response(
            {"error": f"failed to write the setting: {exc}", "code": "config_write_failed"},
            status=500,
        )
    return web.json_response(_payload())
