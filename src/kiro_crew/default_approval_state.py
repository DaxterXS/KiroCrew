"""The KEYSTONE store for the approval tier a NEW chat session starts on.

State lives in ``<config_dir>/default_approval_mode.json`` -- **not** in
``config.json``. That is a security decision with a precedent in this repo: the
computer-use primary enable and the denied-command opt-out are both deliberately
kept off ``config.json`` BECAUSE they are security ceilings rather than
preferences, and ``security.py`` records the reasoning. A standing approval tier
is the same class of control: it decides whether a session's tools run without a
human approving each call, for every session minted afterwards.

The concrete reason it cannot live in ``config.json``: that file is write-caught
on the agent TOOL path but not on the SHELL path. ``security.py`` carries the
verification -- ``is_sensitive_bash_command("echo x > .../config.json")`` is
``None`` -- so any auto-approved agent shell can rewrite it. A tier stored there
would be self-grantable by the very party it exists to constrain, and no later
gate could tell that write apart from the operator's own choice.

The mechanics that make it un-flippable by the agent:

* the leaf is on ``security._CREW_SECRET_LEAVES``, so ``is_sensitive_path``
  refuses the agent's file tools AND the shell forms (``>``, ``tee``, ``cat``,
  extraction verbs) refuse it too. Protected on one path only is not protected.
* it is read+write protected rather than write-only: the stored tier tells an
  agent whether the sessions around it are already elevated, which is
  reconnaissance for choosing what to attempt.
* the dashboard PUT handler is the only writer and opens the path directly
  rather than through the gate, so the operator's Settings card still works.

Reads FAIL CLOSED to ``normal`` -- the interactive floor -- and never consult
``config.json`` on any path. A fallback there would silently reintroduce the
whole defect: the feature would keep working while being ungated, which is worse
than the feature being inert.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from kiro_crew.atomic_write import atomic_write
from kiro_crew.config import loader as config_loader

logger = logging.getLogger(__name__)

STATE_FILE_NAME = "default_approval_mode.json"
STATE_KEY_MODE = "mode"

#: The interactive floor. Every failure path resolves here.
DEFAULT_APPROVAL_MODE = "normal"

#: The PERSISTABLE tiers, which is deliberately NOT the per-chat vocabulary.
#: ``trust`` and ``yolo`` are excluded as a security boundary: ``trust`` is the
#: only tier that also writes the session ``approval_policy`` "auto" (unattended
#: tool auto-approve, which ``parent_trusted`` extends to spawned subagents), so
#: a stored ``trust`` would raise the floor for every future session. Both stay
#: available PER-CHAT from the footer picker -- narrowing what may be PERSISTED
#: must never narrow what is selectable at runtime.
#:
#: ``yolo`` is excluded for a second, structural reason: it is not "the tier a new
#: session starts in" at all. Selecting it arms the process-global SafetyOverride
#: with its own duration and expiry (``agent.yolo_duration``), which this setting
#: cannot express.
#:
#: The TWO that remain are a strict SUBSET of the modes the ``approval_modes``
#: governance scope declares ``always_permitted`` (``SCOPE_CATALOG`` in
#: ``kiro_crew/platform/governance.py``) -- the modes an admin policy may never
#: forbid. That is what makes this setting unable to escape a ceiling: it cannot
#: name the only deniable mode, so there is nothing for it to be clamped against.
#: A SUBSET rather than an exact match, because ``trust`` is excluded for the
#: stricter reason above. ``test/test_default_approval_mode.py`` pins that
#: correspondence, so if a tier ever becomes deniable the test fails rather than
#: this tuple silently widening.
DEFAULT_APPROVAL_MODES = (DEFAULT_APPROVAL_MODE, "trust_reads")

_STATE_FILE_MODE = 0o600


def default_approval_mode_path() -> Path:
    """Return the keystone leaf's path.

    Resolved through the loader MODULE ATTRIBUTE rather than a direct import so a
    test can retarget the whole store by patching one name.
    """
    return config_loader.default_approval_mode_path()


def load_state() -> dict:
    """Read the keystone state, failing soft to ``{}``.

    Absent, unreadable, malformed, or not-a-dict all yield ``{}``, which
    :func:`load_mode` resolves to the interactive floor.
    """
    try:
        raw = json.loads(default_approval_mode_path().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except Exception:
        logger.debug(
            "%s load failed; new sessions start on the interactive floor",
            STATE_FILE_NAME,
            exc_info=True,
        )
        return {}
    return raw if isinstance(raw, dict) else {}


def normalize_mode(value: object) -> str:
    """Coerce any stored value to a persistable tier, defaulting to the floor.

    Anything unrecognised -- a typo, a removed tier, the wrong type, ``trust``, or
    ``yolo`` -- becomes ``normal``. Note which direction the fallback runs: an
    unreadable or hostile value can only ever ask for MORE approval prompts,
    never fewer.
    """
    if isinstance(value, str):
        v = value.strip().lower()
        if v in DEFAULT_APPROVAL_MODES:
            return v
    return DEFAULT_APPROVAL_MODE


def load_mode(state: "dict | None" = None) -> str:
    """Return the stored tier, or ``normal`` when there is not a valid one.

    FAILS CLOSED and never reads ``config.json``: an absent leaf, a malformed
    leaf, a non-string value, and a value outside :data:`DEFAULT_APPROVAL_MODES`
    (including ``trust`` and ``yolo``, which are not persistable) all resolve to
    the interactive floor. Clamping on READ is what makes hand-editing the leaf
    useless as an escalation, so the guarantee does not rest on the writer alone.
    """
    data = load_state() if state is None else state
    if not isinstance(data, dict):
        return DEFAULT_APPROVAL_MODE
    return normalize_mode(data.get(STATE_KEY_MODE))


def save_mode(mode: str) -> None:
    """Write the tier atomically, owner-only. RAISES on failure.

    Only reads fail soft. A write that silently did nothing would leave the
    operator's Settings card showing a value the store does not hold.
    """
    if not isinstance(mode, str) or mode not in DEFAULT_APPROVAL_MODES:
        raise ValueError(f"{mode!r} is not a persistable approval tier")
    path = default_approval_mode_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(
        path,
        json.dumps({STATE_KEY_MODE: mode}, indent=2) + "\n",
        mode=_STATE_FILE_MODE,
    )
