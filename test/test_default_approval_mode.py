"""The standing approval tier a NEW session starts on -- now a KEYSTONE leaf.

Issue #6812. The setting was moved OUT of ``config.json`` / ``AgentConfig`` and
into ``<config_dir>/default_approval_mode.json`` (module
``kiro_crew.default_approval_state``), because ``config.json`` is writable by an
auto-approved agent SHELL and the tier is a security ceiling, not a preference.
The properties pinned here, and why the first two keep this setting from becoming
a way to escape an admin ceiling:

1. the offerable set (``DEFAULT_APPROVAL_MODES``) is a subset of the tiers the
   ``approval_modes`` governance scope declares ``always_permitted``, so the
   setting cannot name a deniable mode;
2. an unrecognised value -- including ``yolo`` and ``trust`` -- clamps to the
   interactive floor on READ, so a hand-edited leaf cannot grant more than it is
   allowed to;
3. the per-mode state matches what ``api_chat_mode`` writes for the same tier, so
   a tier reached from the store does not mean something different from the same
   tier reached from the footer picker;
4. the default is ``normal`` and a fresh install has no leaf, so installing this
   change alters no behaviour;
5. the read path consults ONLY the keystone leaf -- there is no ``config.json``
   fallback -- and fails closed to ``normal`` when the leaf is absent.

Deliberately a new file rather than an addition to
``test_approval_modes_enforcement.py``: open PR #8868 (the #8848 push-on-install
refactor) is editing that file, and colliding with it buys nothing.
"""

import pytest

from kiro_crew import default_approval_state
from kiro_crew.default_approval_state import (
    DEFAULT_APPROVAL_MODE as _DEFAULT_APPROVAL_MODE,
)
from kiro_crew.default_approval_state import (
    DEFAULT_APPROVAL_MODES as _DEFAULT_APPROVAL_MODES,
)
from kiro_crew.default_approval_state import (
    normalize_mode as _normalize_default_approval_mode,
)


class TestTheOfferableSetCannotEscapeAnAdminCeiling:
    def test_the_offerable_tiers_are_exactly_the_non_deniable_ones(self) -> None:
        """The drift guard that makes "no clamp needed" true rather than asserted.

        ``approval_modes`` may never forbid the modes in ``always_permitted``, so a
        setting restricted to exactly those cannot select past a policy. If a tier
        ever BECOMES deniable it leaves that tuple and this test fails -- which is
        the point: the failure is what stops the offerable list silently retaining
        a mode an admin can now deny.
        """
        from kiro_crew.platform.governance import SCOPE_CATALOG

        # SUBSET, not equality. Every persistable tier must be one the scope may never
        # forbid, which is what makes "cannot select past an admin ceiling" true. It is
        # no longer EQUALITY because `trust` is excluded for a different and stricter
        # reason -- it writes the unattended auto-approve session policy, so it must not
        # be persistable even though policy may not forbid it. Equality here would force
        # `trust` back in the moment someone "fixed" the test.
        assert set(_DEFAULT_APPROVAL_MODES) <= set(SCOPE_CATALOG["approval_modes"].always_permitted)
        assert "trust" not in _DEFAULT_APPROVAL_MODES

    def test_yolo_is_not_offerable_anywhere(self) -> None:
        """``yolo`` is process-global with its own expiry, not a per-session tier.

        Asserted at both surfaces a persisted tier can now reach: the canonical
        persistable set, and the offerable list the owner Settings card renders
        (the keystone handler's ``_payload``). A value only has to leak through one
        of them to be selectable, and both derive from ``DEFAULT_APPROVAL_MODES``.
        """
        from kiro_crew.dashboard.handlers import default_approval_mode as _handler

        assert "yolo" not in _DEFAULT_APPROVAL_MODES
        assert "yolo" not in _handler._payload()["values"]
        assert _normalize_default_approval_mode("yolo") == _DEFAULT_APPROVAL_MODE

    def test_the_offered_set_and_the_write_validator_are_one_set(self) -> None:
        """The UI-offered tiers and the tiers the writer accepts are one set.

        Formerly three declarations (constant, config field metadata, Settings PUT
        validator) that could drift; the move collapsed them to a single source.
        What can still drift is the keystone handler's GET payload (what the
        Settings card renders) against ``DEFAULT_APPROVAL_MODES`` (what its PUT
        validator checks a write against), so a value offered but not accepted
        would be selectable in the UI and refused on write, or vice versa. This
        pins that the payload is exactly the canonical set rather than a hardcoded
        list that could rot.
        """
        from kiro_crew.dashboard.handlers import default_approval_mode as _handler

        assert _handler._payload()["values"] == list(_DEFAULT_APPROVAL_MODES)
        # The PUT validator checks membership in the same constant the payload
        # exposes, so the offered set and the accepted set cannot diverge.
        assert _handler.default_approval_state.DEFAULT_APPROVAL_MODES == _DEFAULT_APPROVAL_MODES


class TestAnUnreadableValueAsksForMoreApprovalsNotFewer:
    @pytest.mark.parametrize("raw", list(_DEFAULT_APPROVAL_MODES))
    def test_every_offerable_tier_survives_normalization(self, raw: str) -> None:
        assert _normalize_default_approval_mode(raw) == raw

    @pytest.mark.parametrize(
        "raw",
        [
            # `TRUST` is deliberately NOT here any more: it is no longer a
            # persistable tier, so its normalized form is the floor, not itself. It
            # is asserted in the rejected set below instead.
            "  TRUST_READS  ",
            "Trust_Reads",
            "NORMAL",
        ],
    )
    def test_case_and_surrounding_whitespace_are_tolerated(self, raw: str) -> None:
        assert _normalize_default_approval_mode(raw) == raw.strip().lower()

    @pytest.mark.parametrize(
        "raw",
        [
            "yolo",  # the one deniable mode: must never arrive this way
            "YOLO",
            "auto",  # agent.approval_mode's vocabulary, not this one
            "interactive",
            "reads",  # the i18n LABEL spelling, not the key
            "",
            "bogus",
            None,
            5,
            [],
            {"mode": "trust"},
        ],
    )
    def test_anything_else_falls_back_to_the_interactive_floor(self, raw: object) -> None:
        assert _normalize_default_approval_mode(raw) == "normal"
        assert _normalize_default_approval_mode(raw) == _DEFAULT_APPROVAL_MODE

    def test_reads_is_rejected_because_the_key_is_trust_reads(self) -> None:
        """Guards the exact mistake the issue body invites.

        The picker LABELS the middle tier "Reads" via
        ``components.approvalModePicker.reads_label``, but its key is
        ``trust_reads``. A config saying ``reads`` is a typo, not a tier, and must
        not silently become one.
        """
        assert _normalize_default_approval_mode("reads") == "normal"
        assert "reads" not in _DEFAULT_APPROVAL_MODES
        assert "trust_reads" in _DEFAULT_APPROVAL_MODES


class TestInstallingThisChangesNothing:
    def test_the_default_is_the_behaviour_new_sessions_have_today(self) -> None:
        """No leaf, no change.

        A fresh install has no keystone file, so the read path resolves to the
        interactive floor and nothing about session creation differs from before
        this setting existed. ``load_mode({})`` exercises the resolve step with an
        empty store, without touching disk.
        """
        assert _DEFAULT_APPROVAL_MODE == "normal"
        assert default_approval_state.load_mode({}) == "normal"

    def test_an_absent_config_key_resolves_to_normal(self) -> None:
        assert _normalize_default_approval_mode(None) == "normal"


class TestThePerModeStateMatchesTheFooterPicker:
    """``_apply_default_approval_mode`` against ``api_chat_mode``'s own writes."""

    @staticmethod
    def _slot_and_state():
        from kiro_crew.dashboard.state import _ChatSlot

        class _Sessions:
            def __init__(self) -> None:
                self.policies: dict[str, str] = {}
                self.calls = 0

            def set_approval_policy(self, key: str, value: str) -> None:
                self.calls += 1
                self.policies[key] = value

        class _State:
            def __init__(self) -> None:
                self.sessions = _Sessions()

        return _ChatSlot("chat-6812"), _State()

    def test_normal_writes_nothing_because_a_fresh_slot_already_is_normal(self) -> None:
        from kiro_crew.dashboard.chat_handlers import _apply_default_approval_mode

        slot, state = self._slot_and_state()
        assert _apply_default_approval_mode(state, slot, "normal") is False
        assert slot._trust is False
        assert slot._trust_reads is False
        # No session policy write at all: touching it could only introduce a
        # difference from the untouched state that IS "normal".
        assert state.sessions.calls == 0

    def test_trust_reads_sets_only_the_read_flag_and_leaves_the_policy_empty(self) -> None:
        """``trust_reads`` must NOT grant subagent auto-approval.

        ``api_chat_mode`` writes ``""`` for this tier, and
        ``subagent_manager/admission.py``'s ``parent_trusted`` treats only
        ``"auto"`` as trusted (#8849). Writing ``"auto"`` here would silently make
        Reads stronger than the picker's Reads.
        """
        from kiro_crew.dashboard.chat_handlers import _apply_default_approval_mode
        from kiro_crew.dashboard.chat_utils import effective_session_key

        slot, state = self._slot_and_state()
        assert _apply_default_approval_mode(state, slot, "trust_reads") is True
        assert slot._trust_reads is True
        assert slot._trust is False
        assert state.sessions.policies == {effective_session_key(slot): ""}

    def test_trust_is_REFUSED_by_the_helper_and_writes_nothing(self) -> None:
        """`trust` is not persistable, and the granting branch is DELETED.

        Stronger than "unreachable": there is no code path in this helper that can
        write session policy "auto", so widening the persistable set later cannot
        revive the grant without also re-adding the branch -- which this test would
        then not catch, but the source assertion below would.
        """
        from kiro_crew.dashboard.chat_handlers import _apply_default_approval_mode

        slot, state = self._slot_and_state()
        assert _apply_default_approval_mode(state, slot, "trust") is False
        assert slot._trust is False
        assert slot._trust_reads is False
        assert state.sessions.calls == 0  # no policy write of any kind

    def test_the_helper_contains_no_auto_policy_write_at_all(self) -> None:
        """The structural half: absent, not merely unreachable.

        The conductor's distinction -- a guarded branch is correct only while nothing
        supplies `trust`, whereas a deleted branch cannot be revived by a config
        change. Asserted on the source so a re-added branch fails here.
        """
        import inspect

        from kiro_crew.dashboard import chat_handlers

        src = inspect.getsource(chat_handlers._apply_default_approval_mode)
        code = "\n".join(
            line for line in src.splitlines() if not line.lstrip().startswith(("#", "*"))
        )
        assert (
            '"auto"' not in code.split('"""')[-1]
        ), "an auto-approve policy write reappeared in the persistable-tier helper"

    @pytest.mark.parametrize("mode", ["yolo", "reads", "auto", "interactive", ""])
    def test_a_non_tier_reaching_the_helper_is_a_no_op(self, mode: str) -> None:
        """Defence in depth: the normalizer should stop these, and if it ever
        does not, the helper still grants nothing."""
        from kiro_crew.dashboard.chat_handlers import _apply_default_approval_mode

        slot, state = self._slot_and_state()
        assert _apply_default_approval_mode(state, slot, mode) is False
        assert slot._trust is False
        assert slot._trust_reads is False
        assert state.sessions.calls == 0


class TestOnlyAHumanDashboardCallerInheritsTheDefault:
    """The tier is a dashboard operator's preference, not an app-token capability.

    ``POST /api/chat/slots`` serves two principals: a human on the new-chat tab
    (``request["app"] == ""``) and an app token holding ``/api/chat`` (non-empty).
    An app's grant does not include "and start pre-trusted", so a ``trust`` default
    must not hand an app-created session the ``auto`` approval policy -- which
    ``parent_trusted`` would then extend to every subagent it spawns.

    Driven through the REAL handler rather than the helper: the helper is
    principal-blind by design, and what needs pinning is the call site's guard.
    A test of the helper alone would stay green with the guard deleted.
    """

    @staticmethod
    def _state(tmp_path):
        from unittest.mock import AsyncMock, MagicMock

        from chat_test_helpers import _make_ready_kiro_prerequisite

        from kiro_crew.dashboard.state import DashboardState
        from kiro_crew.history import ConversationLog

        sessions = MagicMock(count=0)
        sessions.remove = AsyncMock()
        sessions.recycle_background = AsyncMock()
        sessions.get_pid = MagicMock(return_value=None)
        state = DashboardState(
            sessions=sessions,
            crons=MagicMock(
                list_jobs=MagicMock(return_value=[]), status=MagicMock(return_value={})
            ),
            lessons=MagicMock(load_all=MagicMock(return_value=[])),
            start_time=0.0,
            conversation_log=ConversationLog(base_dir=tmp_path),
        )
        state.kiro_prerequisite_service = _make_ready_kiro_prerequisite()
        return state

    @staticmethod
    def _force_trust_default(tmp_path, monkeypatch):
        """Seed the KEYSTONE leaf with the strongest offerable tier.

        The tier no longer lives in ``config.json`` / ``AgentConfig`` -- it is a
        keystone leaf, and the read path (``default_approval_state.load_mode``)
        consults ONLY that leaf. So the way to arm these tests is to WRITE the leaf,
        not to stub a config object. The loader's ``default_approval_mode_path`` is
        retargeted into ``tmp_path`` first, so the write lands in the test's isolated
        store and never touches the real home.

        ``trust_reads`` on purpose: ``trust`` is no longer persistable, so
        ``trust_reads`` is the strongest tier this store can hold -- and the one
        whose leak to a non-owner or an app token would actually matter.
        """
        import types

        from kiro_crew.config import KiroCrewConfig

        leaf = tmp_path / "default_approval_mode.json"
        monkeypatch.setattr("kiro_crew.config.loader.default_approval_mode_path", lambda: leaf)
        default_approval_state.save_mode("trust_reads")
        assert default_approval_state.load_mode() == "trust_reads"
        # The handler still loads a real config for agent/workspace resolution
        # (``default_agent``, bindings). Give it a plain default config so that path
        # stays isolated and deterministic -- it no longer carries the tier.
        monkeypatch.setattr(
            "kiro_crew.dashboard.chat_handlers.KiroCrewConfig",
            types.SimpleNamespace(load=lambda: KiroCrewConfig()),
        )
        # The tier is owner-only to inherit as well as to persist, so the default
        # posture for these tests is OWNER -- otherwise every one of them would be
        # measuring the owner gate instead of the thing it names.
        monkeypatch.setattr(
            "kiro_crew.dashboard.handlers.source_providers.is_owner_dashboard_request",
            lambda _r: True,
        )

    @pytest.fixture(autouse=True)
    def _isolate_config_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr("kiro_crew.dashboard.state.config_dir", lambda: tmp_path)
        # The keystone leaf resolves through the LOADER's config_dir, not state's,
        # so retarget it explicitly into tmp_path: reads fail soft to the floor
        # when a test has not seeded a tier, and never touch the real home store.
        monkeypatch.setattr(
            "kiro_crew.config.loader.default_approval_mode_path",
            lambda: tmp_path / "default_approval_mode.json",
        )

    @pytest.mark.asyncio
    async def test_a_dashboard_user_gets_the_configured_tier(self, tmp_path, monkeypatch):
        """The control: without this passing, the denial below proves nothing."""
        from aiohttp import web
        from aiohttp.test_utils import TestClient, TestServer

        from kiro_crew.dashboard.chat import api_chat_slot_create

        self._force_trust_default(tmp_path, monkeypatch)
        state = self._state(tmp_path)

        async def as_dashboard_user(request: web.Request) -> web.Response:
            request["app"] = ""  # what the auth middleware sets for a dashboard user
            return await api_chat_slot_create(request)

        app = web.Application()
        app["state"] = state
        app.router.add_post("/api/chat/slots", as_dashboard_user)
        async with TestClient(TestServer(app)) as client:
            resp = await client.post("/api/chat/slots", json={"name": "human"})
            assert resp.status == 200, await resp.text()

        slot = next(iter(state._slots.values()))
        assert slot._trust_reads is True
        assert slot._trust is False

    @pytest.mark.asyncio
    async def test_an_app_token_does_not_inherit_the_configured_tier(self, tmp_path, monkeypatch):
        from aiohttp import web
        from aiohttp.test_utils import TestClient, TestServer

        from kiro_crew.dashboard.chat import api_chat_slot_create

        self._force_trust_default(tmp_path, monkeypatch)
        state = self._state(tmp_path)

        async def as_app_token(request: web.Request) -> web.Response:
            request["app"] = "some-app"
            return await api_chat_slot_create(request)

        app = web.Application()
        app["state"] = state
        app.router.add_post("/api/chat/slots", as_app_token)
        async with TestClient(TestServer(app)) as client:
            resp = await client.post("/api/chat/slots", json={"name": "app-made"})
            assert resp.status == 200, await resp.text()

        slot = next(iter(state._slots.values()))
        assert slot._trust is False, "an app token must not inherit a trust default"
        assert slot._trust_reads is False

    @pytest.mark.asyncio
    async def test_an_app_token_gets_no_auto_session_policy(self, tmp_path, monkeypatch):
        """The consequence that made this security-class rather than cosmetic.

        ``trust`` writes ``set_approval_policy(key, "auto")``, and
        ``subagent_manager/admission.py``'s ``parent_trusted`` reads that policy on a
        path independent of the SafetyOverride -- so the leak would auto-approve the
        app session's subagents too. Asserted on the sessions double directly,
        because the flags above and this write are separate effects.
        """
        from aiohttp import web
        from aiohttp.test_utils import TestClient, TestServer

        from kiro_crew.dashboard.chat import api_chat_slot_create

        self._force_trust_default(tmp_path, monkeypatch)
        state = self._state(tmp_path)

        async def as_app_token(request: web.Request) -> web.Response:
            request["app"] = "some-app"
            return await api_chat_slot_create(request)

        app = web.Application()
        app["state"] = state
        app.router.add_post("/api/chat/slots", as_app_token)
        async with TestClient(TestServer(app)) as client:
            assert (await client.post("/api/chat/slots", json={"name": "a"})).status == 200

        wrote_auto = [
            c for c in state.sessions.set_approval_policy.call_args_list if "auto" in repr(c)
        ]
        assert wrote_auto == [], f"app-created session was granted an auto policy: {wrote_auto}"


class TestARemoteBoundSessionKeepsThePeersTier:
    """A session bound to a remote crew is not re-tiered by the local default.

    For a remote-bound session the PEER enforces approvals. Applying the local
    default would set the flags the footer DISPLAYS while the peer decided what
    actually runs, so a peer at Normal could display Trust here (or the reverse) --
    a display that contradicts enforcement. Mirroring the peer's effective tier
    would need a defined path to read it and there is none, so the handler declines
    rather than guessing.

    Binding is owner-only and refuses app tokens, so this drives the handler as the
    owner -- the only principal that can reach the branch at all.
    """

    @pytest.fixture(autouse=True)
    def _isolate_config_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr("kiro_crew.dashboard.state.config_dir", lambda: tmp_path)
        # The keystone leaf resolves through the LOADER's config_dir, not state's,
        # so retarget it explicitly into tmp_path: reads fail soft to the floor
        # when a test has not seeded a tier, and never touch the real home store.
        monkeypatch.setattr(
            "kiro_crew.config.loader.default_approval_mode_path",
            lambda: tmp_path / "default_approval_mode.json",
        )

    @pytest.mark.asyncio
    async def test_a_remote_bound_create_does_not_inherit_the_local_default(
        self, tmp_path, monkeypatch
    ):
        from unittest.mock import AsyncMock, MagicMock

        from aiohttp import web
        from aiohttp.test_utils import TestClient, TestServer

        from kiro_crew.dashboard.chat import api_chat_slot_create

        TestOnlyAHumanDashboardCallerInheritsTheDefault._force_trust_default(tmp_path, monkeypatch)
        state = TestOnlyAHumanDashboardCallerInheritsTheDefault._state(tmp_path)

        # Owner, so the binding gates pass; the peer write itself is stubbed because
        # what is under test is the LOCAL tier decision, not the remote call.
        monkeypatch.setattr(
            "kiro_crew.dashboard.handlers.source_providers.is_owner_dashboard_request",
            lambda _r: True,
        )
        created = MagicMock(return_value=None)
        monkeypatch.setattr(
            "kiro_crew.dashboard.chat_handlers.create_peer_slot",
            AsyncMock(return_value={"slot": "peer-1"}),
            raising=False,
        )

        async def as_owner(request: web.Request) -> web.Response:
            request["app"] = ""
            return await api_chat_slot_create(request)

        app = web.Application()
        app["state"] = state
        app.router.add_post("/api/chat/slots", as_owner)
        async with TestClient(TestServer(app)) as client:
            resp = await client.post(
                "/api/chat/slots", json={"name": "remote", "instance_id": "peer-crew-1"}
            )
            # The create may legitimately fail for peer reasons in this harness; what
            # must hold either way is that no LOCAL trust flag was granted. Asserted
            # unconditionally rather than gated on a 200, so a harness-level peer
            # failure cannot make this vacuous.
            _ = resp.status

        for slot in state._slots.values():
            assert slot._trust is False, "a remote-bound session inherited the local trust default"
            assert slot._trust_reads is False
        assert created.call_count == 0  # the double above is unused; kept explicit


class TestPersistingTheDefaultIsOwnerOnly:
    """Raising the floor for every FUTURE session is an owner act.

    Persistence moved off the agent-writable ``config.json`` PATCH surface and onto
    the dedicated keystone writer ``PUT /api/security/default-approval-mode``
    (``api_default_approval_mode_save``), which owner-gates on its own -- an app
    token is refused, and an allow-listed non-owner dashboard identity (empty
    ``app`` claim, subject not the owner) is refused too. This is a STANDING
    auto-approve grant with no expiry, the same property that keeps
    ``agent.dangerously_skip_permissions`` out of the editable set entirely.
    """

    @staticmethod
    def _app():
        from aiohttp import web

        from kiro_crew.dashboard.handlers import api_kirocrew_config_patch

        app = web.Application()
        app.router.add_patch("/api/config/kirocrew", api_kirocrew_config_patch)
        return app

    @staticmethod
    def _keystone_app():
        from aiohttp import web

        from kiro_crew.dashboard.handlers import api_default_approval_mode_save

        app = web.Application()
        app.router.add_put("/api/security/default-approval-mode", api_default_approval_mode_save)
        return app

    @pytest.mark.asyncio
    async def test_a_non_owner_cannot_persist_the_default(self, monkeypatch):
        from aiohttp.test_utils import TestClient, TestServer

        # The keystone handler binds ``is_owner_dashboard_request`` at import, so the
        # gate is patched on the HANDLER module, not on source_providers.
        monkeypatch.setattr(
            "kiro_crew.dashboard.handlers.default_approval_mode.is_owner_dashboard_request",
            lambda _r: False,
        )
        async with TestClient(TestServer(self._keystone_app())) as client:
            resp = await client.put(
                "/api/security/default-approval-mode",
                json={"mode": "trust_reads"},
            )
        assert resp.status in (401, 403), f"non-owner write was not refused: {resp.status}"

    @pytest.mark.asyncio
    async def test_the_generic_config_patch_endpoint_stays_ungated(self, monkeypatch):
        """The control: the GENERIC config PATCH endpoint is not owner-gated.

        The tier's owner gate lives on the dedicated keystone handler, not on
        ``api_kirocrew_config_patch``. Without this, the refusal above could pass
        for the wrong reason -- a blanket owner gate on every editable key, which
        would be a regression, not a fix. An ordinary key (``agent.yolo_duration``)
        must answer anything BUT the owner refusal.
        """
        from aiohttp.test_utils import TestClient, TestServer

        monkeypatch.setattr(
            "kiro_crew.dashboard.handlers.source_providers.is_owner_dashboard_request",
            lambda _r: False,
        )
        async with TestClient(TestServer(self._app())) as client:
            resp = await client.patch(
                "/api/config/kirocrew",
                json={"path": "agent.yolo_duration", "value": "3600"},
            )
        # Whatever this ungated sibling answers, it must not be the owner refusal.
        assert resp.status not in (401, 403), "the owner gate leaked to an ungated key"

    def test_the_tier_is_no_longer_a_writable_config_key(self) -> None:
        """Cheap structural pin: the tier left the agent-writable config surface.

        Stronger than the old ``owner_only`` flag on the config key -- the key is
        GONE from ``_EDITABLE_CONFIG`` entirely, so it cannot be persisted through
        the generic (agent-writable) config PATCH path at all. Its store is a
        keystone leaf the agent's own file and shell tools are refused
        (``security._CREW_SECRET_LEAVES``), and the only writer is the owner-gated
        keystone handler. An unrelated key stays editable, as a control.
        """
        from kiro_crew import security
        from kiro_crew.dashboard.handlers import default_approval_mode as _handler
        from kiro_crew.dashboard.handlers.core import _EDITABLE_CONFIG

        assert "agent.default_approval_mode" not in _EDITABLE_CONFIG
        assert "agent.yolo_duration" in _EDITABLE_CONFIG
        assert "default_approval_mode.json" in security._CREW_SECRET_LEAVES
        assert callable(_handler.api_default_approval_mode_save)
        assert callable(_handler._reject_non_owner)


class TestANonOwnerDashboardUserDoesNotInheritTheDefault:
    """Inheriting the tier is owner-only, not merely non-app.

    An allow-listed messaging identity holds a dashboard credential whose subject is
    not the owner and whose ``app`` claim is EMPTY, so the app-token guard alone
    admits it. Without a positive owner assertion such a caller would pick up the
    owner's standing auto-approve grant just by opening a chat.
    """

    @pytest.fixture(autouse=True)
    def _isolate_config_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr("kiro_crew.dashboard.state.config_dir", lambda: tmp_path)
        # The keystone leaf resolves through the LOADER's config_dir, not state's,
        # so retarget it explicitly into tmp_path: reads fail soft to the floor
        # when a test has not seeded a tier, and never touch the real home store.
        monkeypatch.setattr(
            "kiro_crew.config.loader.default_approval_mode_path",
            lambda: tmp_path / "default_approval_mode.json",
        )

    @pytest.mark.asyncio
    async def test_a_non_owner_keeps_the_interactive_floor(self, tmp_path, monkeypatch):
        from aiohttp import web
        from aiohttp.test_utils import TestClient, TestServer

        from kiro_crew.dashboard.chat import api_chat_slot_create

        TestOnlyAHumanDashboardCallerInheritsTheDefault._force_trust_default(tmp_path, monkeypatch)
        # Applied AFTER the helper, which sets the owner posture these tests default to.
        monkeypatch.setattr(
            "kiro_crew.dashboard.handlers.source_providers.is_owner_dashboard_request",
            lambda _r: False,
        )
        state = TestOnlyAHumanDashboardCallerInheritsTheDefault._state(tmp_path)

        async def as_non_owner(request: web.Request) -> web.Response:
            request["app"] = ""  # a dashboard credential, but not the owner's
            return await api_chat_slot_create(request)

        app = web.Application()
        app["state"] = state
        app.router.add_post("/api/chat/slots", as_non_owner)
        async with TestClient(TestServer(app)) as client:
            resp = await client.post("/api/chat/slots", json={"name": "guest"})
            assert resp.status == 200, await resp.text()

        slot = next(iter(state._slots.values()))
        assert slot._trust is False, "a non-owner inherited the owner's trust default"
        assert slot._trust_reads is False


class TestTheCreationVerdictCannotGoStale:
    """No ``await`` between the newness check and the slot allocation.

    ``is_new_slot`` is a snapshot of ``state._slots``. An await between that check
    and ``get_or_create_slot`` is a TOCTOU window: a concurrent create can insert the
    same key while this coroutine is suspended, after which the allocation returns
    the OTHER caller's slot while the stale verdict still says it is fresh -- and an
    owner-tier auto-approve grant lands on a session this request did not create.

    Reading the config for this feature introduced exactly such an await; it is now
    hoisted above the check. This pins the ORDERING rather than the hoist, so any
    future await added into that window fails here instead of silently reopening the
    race. Source-level on purpose: the property is about scheduling points, which a
    behavioural test cannot observe without racing the loop it is asserting about.
    """

    def test_no_await_between_the_newness_check_and_the_allocation(self) -> None:
        import inspect

        from kiro_crew.dashboard import chat_handlers

        src = inspect.getsource(chat_handlers.api_chat_slot_create).splitlines()
        check = next(i for i, line in enumerate(src) if "is_new_slot = not _requested_key" in line)
        alloc = next(
            i for i, line in enumerate(src) if i > check and "state.get_or_create_slot(" in line
        )
        offenders = [
            (i, line.strip())
            for i, line in enumerate(src)
            if check < i < alloc and ("await " in line or "async with " in line)
        ]
        assert offenders == [], (
            "an await between the is_new_slot check and get_or_create_slot reopens the "
            f"stale-verdict race: {offenders}"
        )

    def test_the_tier_is_refused_when_the_slot_is_app_owned(self) -> None:
        """Defence in depth, asserted on the object rather than on the boolean.

        Even with the window closed, the apply site checks the slot's own ``_app``
        tag, so a slot that belongs to an app can never be tiered regardless of what
        the newness verdict says.
        """
        import inspect

        from kiro_crew.dashboard import chat_handlers

        src = inspect.getsource(chat_handlers.api_chat_slot_create)
        assert "and not slot._app" in src, "the app-ownership check at the apply site is gone"


class TestOnlyASlotTheUserCanSeeInheritsTheTier:
    """An app-worker slot is not a chat the user opened.

    Design Critique's ``dc-*`` worker is created by the OWNER's own page (same-origin,
    no app token), so it has an empty app tag and passes every principal gate. What it
    does not have is a user watching it: its ``design-critique`` mode keeps it off the
    chat sidebar. A standing auto-approve grant there runs tools unattended.
    """

    @pytest.fixture(autouse=True)
    def _isolate_config_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr("kiro_crew.dashboard.state.config_dir", lambda: tmp_path)
        # The keystone leaf resolves through the LOADER's config_dir, not state's,
        # so retarget it explicitly into tmp_path: reads fail soft to the floor
        # when a test has not seeded a tier, and never touch the real home store.
        monkeypatch.setattr(
            "kiro_crew.config.loader.default_approval_mode_path",
            lambda: tmp_path / "default_approval_mode.json",
        )

    @pytest.mark.asyncio
    async def test_an_app_worker_mode_does_not_inherit_the_tier(self, tmp_path, monkeypatch):
        from aiohttp import web
        from aiohttp.test_utils import TestClient, TestServer

        from kiro_crew.dashboard.chat import api_chat_slot_create

        TestOnlyAHumanDashboardCallerInheritsTheDefault._force_trust_default(tmp_path, monkeypatch)
        state = TestOnlyAHumanDashboardCallerInheritsTheDefault._state(tmp_path)

        async def as_owner(request: web.Request) -> web.Response:
            request["app"] = ""
            return await api_chat_slot_create(request)

        app = web.Application()
        app["state"] = state
        app.router.add_post("/api/chat/slots", as_owner)
        async with TestClient(TestServer(app)) as client:
            resp = await client.post(
                "/api/chat/slots",
                json={"name": "dc-1", "memory_mode": "temporary", "mode": "design-critique"},
            )
            assert resp.status == 200, await resp.text()

        slot = next(iter(state._slots.values()))
        assert slot._trust is False, "an off-sidebar app-worker slot inherited the tier"
        assert slot._trust_reads is False

    def test_the_allowlist_holds_only_sidebar_modes(self) -> None:
        """Pinned against the CREATABLE set so a new app-worker mode cannot default in."""
        from kiro_crew.dashboard.chat_handlers import (
            _CREATABLE_MODES,
            _TIER_INHERITING_MODES,
        )

        assert set(_TIER_INHERITING_MODES) < set(_CREATABLE_MODES)
        assert "design-critique" not in _TIER_INHERITING_MODES


class TestAGrantThatCannotBeAuditedIsRefused:
    """The audit is written BEFORE the grant, and a failed audit refuses it.

    An unattended auto-approve grant whose SEL entry is lost is exactly what an
    auditor cannot reconstruct, and the loss is permanent. Refusing leaves the session
    on the interactive floor, which is the fail-safe direction.
    """

    @pytest.fixture(autouse=True)
    def _isolate_config_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr("kiro_crew.dashboard.state.config_dir", lambda: tmp_path)
        # The keystone leaf resolves through the LOADER's config_dir, not state's,
        # so retarget it explicitly into tmp_path: reads fail soft to the floor
        # when a test has not seeded a tier, and never touch the real home store.
        monkeypatch.setattr(
            "kiro_crew.config.loader.default_approval_mode_path",
            lambda: tmp_path / "default_approval_mode.json",
        )

    @pytest.mark.asyncio
    async def test_an_unwritable_audit_refuses_the_tier(self, tmp_path, monkeypatch):
        from unittest.mock import MagicMock

        from aiohttp import web
        from aiohttp.test_utils import TestClient, TestServer

        from kiro_crew.dashboard.chat import api_chat_slot_create

        TestOnlyAHumanDashboardCallerInheritsTheDefault._force_trust_default(tmp_path, monkeypatch)
        state = TestOnlyAHumanDashboardCallerInheritsTheDefault._state(tmp_path)

        # SEL unwritable, the infra fault the finding names (e.g. disk full).
        broken = MagicMock()
        broken.log_api_access.side_effect = OSError("disk full")
        monkeypatch.setattr("kiro_crew.dashboard.chat_handlers.sel", lambda: broken)

        async def as_owner(request: web.Request) -> web.Response:
            request["app"] = ""
            return await api_chat_slot_create(request)

        app = web.Application()
        app["state"] = state
        app.router.add_post("/api/chat/slots", as_owner)
        async with TestClient(TestServer(app)) as client:
            resp = await client.post("/api/chat/slots", json={"name": "unaudited"})
            assert resp.status == 200, await resp.text()

        slot = next(iter(state._slots.values()))
        assert slot._trust is False, "a grant was made that could not be audited"
        assert slot._trust_reads is False
        assert broken.log_api_access.called, "the audit was not even attempted"


class TestAnUnpersistableTierIsRefusedByTheRealLoadPath:
    """``trust`` and ``yolo`` cannot be persisted, measured through the REAL read.

    The tier now lives in the KEYSTONE leaf, not ``config.json``, and
    ``default_approval_state.load_mode`` is what ``api_chat_slot_create`` calls to
    read it. This writes an actual ``default_approval_mode.json`` containing the
    value a hand-edit -- or an agent that reached the leaf -- would store, then
    reads it back through the real ``load_mode`` (file -> ``load_state`` ->
    ``normalize_mode``) and asserts the built-in default comes out instead.

    ``trust`` is the tier that matters: it is the only one whose apply path also
    writes the session ``approval_policy`` "auto" -- unattended tool auto-approve,
    inherited by spawned subagents. Clamping on READ removes the escalation
    mechanism rather than merely discouraging it: even a leaf written past the
    keystone writer's own validation is refused when read, so the guarantee does
    not rest on the writer alone.
    """

    @staticmethod
    def _load_leaf(tmp_path, monkeypatch, payload: dict) -> str:
        """Write a real keystone leaf and read it back through ``load_mode``."""
        import json as _json

        leaf = tmp_path / "default_approval_mode.json"
        leaf.write_text(_json.dumps(payload), encoding="utf-8")
        # Point the REAL resolver at this leaf. ``load_mode`` -> ``load_state`` reads
        # ``default_approval_mode_path()``, so this exercises read + clamp rather than
        # substituting a value.
        monkeypatch.setattr("kiro_crew.config.loader.default_approval_mode_path", lambda: leaf)
        return default_approval_state.load_mode()

    def test_a_persistable_tier_IS_honoured(self, tmp_path, monkeypatch) -> None:
        """The control. Without this, the refusals below could pass vacuously.

        If the reader were not reading this leaf at all, every assertion in this
        class would still see ``normal`` -- because ``normal`` is also the default.
        This proves the leaf reaches the reader, so the refusals mean something.
        """
        assert self._load_leaf(tmp_path, monkeypatch, {"mode": "trust_reads"}) == "trust_reads"

    @pytest.mark.parametrize("stored", ["trust", "yolo"])
    def test_an_unpersistable_tier_is_not_honoured(
        self, tmp_path, monkeypatch, stored: str
    ) -> None:
        got = self._load_leaf(tmp_path, monkeypatch, {"mode": stored})
        assert (
            got == _DEFAULT_APPROVAL_MODE == "normal"
        ), f"a stored {stored!r} was honoured; it must fall back to the built-in default"

    def test_case_and_whitespace_cannot_smuggle_trust_past_the_clamp(
        self, tmp_path, monkeypatch
    ) -> None:
        """The clamp lowercases and strips, so these must not become a bypass."""
        for raw in ("  TRUST  ", "Trust", "TRUST", "\ttrust\n"):
            assert (
                self._load_leaf(tmp_path, monkeypatch, {"mode": raw}) == "normal"
            ), f"{raw!r} was honoured"

    def test_trust_is_absent_from_every_persistable_declaration(self) -> None:
        """One assertion per surface, so a partial revert is caught."""
        from kiro_crew.dashboard.handlers import default_approval_mode as _handler

        assert "trust" not in _DEFAULT_APPROVAL_MODES
        assert "trust" not in _handler._payload()["values"]

    def test_the_per_chat_picker_still_offers_trust(self) -> None:
        """Only PERSISTING trust is refused; the footer picker is unchanged.

        Pinned so a later reader does not "tidy" the two sets into agreement --
        ``_SLOT_SCOPED_TRUST_MODES`` is the per-chat vocabulary and must keep
        ``trust``.
        """
        from kiro_crew.dashboard.chat_handlers import _SLOT_SCOPED_TRUST_MODES

        assert "trust" in _SLOT_SCOPED_TRUST_MODES
        assert "trust_reads" in _SLOT_SCOPED_TRUST_MODES


class TestTheGuardStackDoesNotArgueFromTrust:
    """No guard around this feature reasons from `trust` any more.

    `trust` is unpersistable as of this revision, so a gate testing membership in
    `_SLOT_SCOPED_TRUST_MODES` (the PER-CHAT vocabulary, which still contains `trust`)
    would argue from an invalidated premise: it admits a value this path cannot honour
    and would widen again if that tuple grew. Asserted as ABSENCE of the superseded
    reasoning, not merely presence of the new.
    """

    def test_the_create_gate_tests_the_persistable_set_not_the_per_chat_tuple(self) -> None:
        import inspect

        from kiro_crew.dashboard import chat_handlers

        src = inspect.getsource(chat_handlers.api_chat_slot_create)
        assert "_default_approval_mode in _DEFAULT_APPROVAL_MODES" in src
        # The superseded phrasing must be GONE from this handler.
        assert "_default_approval_mode in _SLOT_SCOPED_TRUST_MODES" not in src

    def test_the_per_chat_path_still_uses_its_own_tuple(self) -> None:
        """The control: the per-chat vocabulary is untouched and still offers trust."""
        from kiro_crew.dashboard.chat_handlers import _SLOT_SCOPED_TRUST_MODES

        assert "trust" in _SLOT_SCOPED_TRUST_MODES


class TestADeclinedDefaultIsNeverSilent:
    """A guard that declines the configured tier must say which guard and why.

    This feature exists to remove a per-chat click. A guard that puts that click back
    without a trace means the user pays it and cannot find out why -- the failure mode
    where a capability is present at every layer except the one that decides.
    """

    def test_every_guard_has_a_named_refusal_reason(self) -> None:
        import inspect

        from kiro_crew.dashboard import chat_handlers

        src = inspect.getsource(chat_handlers.api_chat_slot_create)
        for reason in ("not_a_new_session", "slot_owned_by_an_app"):
            assert reason in src, f"guard refusal {reason!r} is not attributable"
        assert "not applied to" in src, "the refusal is never logged"

    def test_no_unreachable_refusal_is_claimed(self) -> None:
        """The five refusals this branch CANNOT reach must not be named.

        `_default_approval_mode` is non-"normal" only when the read gate passed, so
        an app-token caller, a remote-bound create, a non-owner and an app-worker mode
        never resolved a tier and cannot be refused one here; the loader's clamp makes
        an unpersistable value unreachable too. Naming them would assert observability
        the code does not have -- the exact defect this test exists to prevent
        regressing. Asserted as ABSENCE, which is the only form that catches a
        well-meaning future edit re-adding a dead branch.
        """
        import inspect

        from kiro_crew.dashboard import chat_handlers

        # Comments STRIPPED: the explanation of why these are unreachable names them,
        # and asserting against raw source would match the prose rather than the logic
        # -- the shared-substring trap. Only executable lines are examined.
        src = "\n".join(
            line
            for line in inspect.getsource(chat_handlers.api_chat_slot_create).splitlines()
            if not line.lstrip().startswith("#")
        )
        for dead in (
            "app_token_caller",
            "session_bound_to_remote_crew",
            "caller_is_not_the_owner",
            "app_worker_mode",
            "tier_not_persistable",
        ):
            assert dead not in src, f"{dead!r} can never fire; claiming it is a false promise"

    def test_no_refusal_is_logged_when_nothing_was_configured(self) -> None:
        """`normal` is the default, so an unconfigured install logs nothing.

        Without this the log would fire on every session create on every install,
        which would make the signal worthless.
        """
        import inspect

        from kiro_crew.dashboard import chat_handlers

        src = inspect.getsource(chat_handlers.api_chat_slot_create)
        assert 'if _default_approval_mode != "normal":' in src


class TestAChannelBoundSlotDoesNotInheritTheTier:
    """A slot born with ``linked_session_key`` set must not get the stored tier.

    ``get_or_create_slot`` resolves a channel-shaped requested key and binds
    ``linked_session_key`` AT CREATION, so the helper's former justification -- "a new
    slot has no binding yet" -- was false. The gate tests the FIELD rather than a claim
    about creation time. A bound slot's effective session key is shared, and applying a
    tier there skips the sharing-propagation loop that keeps co-resolving slots from
    disagreeing.
    """

    @pytest.mark.asyncio
    async def test_a_slot_bound_to_a_channel_session_is_refused_the_tier(
        self, tmp_path, monkeypatch
    ):
        from aiohttp import web
        from aiohttp.test_utils import TestClient, TestServer

        from kiro_crew.dashboard.chat import api_chat_slot_create

        TestOnlyAHumanDashboardCallerInheritsTheDefault._force_trust_default(tmp_path, monkeypatch)
        state = TestOnlyAHumanDashboardCallerInheritsTheDefault._state(tmp_path)
        monkeypatch.setattr(
            "kiro_crew.dashboard.handlers.source_providers.is_owner_dashboard_request",
            lambda _r: True,
        )

        # Force the birth-time binding the docstring wrongly claimed cannot happen:
        # every slot this create mints comes back already bound to a channel session.
        real = state.get_or_create_slot

        def bound(*a, **k):
            out = real(*a, **k)
            slot = out[0] if isinstance(out, tuple) else out
            slot.linked_session_key = "channel:slack:C0FAKE"
            return out

        monkeypatch.setattr(state, "get_or_create_slot", bound, raising=False)

        async def as_owner(request):
            request["app"] = ""
            return await api_chat_slot_create(request)

        app = web.Application()
        app["state"] = state
        app.router.add_post("/api/chat/slots", as_owner)
        async with TestClient(TestServer(app)) as client:
            await client.post("/api/chat/slots", json={"name": "chan"})

        assert state._slots, "harness minted no slot, so this test would be vacuous"
        for slot in state._slots.values():
            assert slot.linked_session_key, "the harness failed to bind, test is vacuous"
            assert slot._trust_reads is False, (
                "a channel-bound slot inherited the stored tier; its effective session "
                "key is shared and the sharing-propagation loop was skipped"
            )
            assert slot._trust is False


class TestTheReadPathConsultsOnlyTheKeystoneLeaf:
    """The security argument of the move: the tier is read ONLY from the keystone
    leaf, never from the agent-writable ``config.json``, and an absent leaf fails
    closed to the interactive floor.

    ``config.json`` is writable by an auto-approved agent SHELL -- ``security.py``
    records that ``is_sensitive_bash_command("echo x > .../config.json")`` is
    ``None`` -- so a tier honoured from there would be self-grantable by the very
    party it exists to constrain. These two tests are what prove there is no such
    fallback, and that the read direction is fail-safe (more approvals, not fewer)
    when nothing is stored.
    """

    @pytest.fixture(autouse=True)
    def _isolate_config_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr("kiro_crew.dashboard.state.config_dir", lambda: tmp_path)
        monkeypatch.setattr(
            "kiro_crew.config.loader.default_approval_mode_path",
            lambda: tmp_path / "default_approval_mode.json",
        )

    @pytest.mark.asyncio
    async def test_a_config_json_grant_does_not_leak_through(self, tmp_path, monkeypatch):
        """A ``trust_reads`` grant in the AGENT-WRITABLE ``config.json`` stays OFF.

        The read path never consults ``config.json``, so even a real config load
        carrying the grant tiers nothing. This points the loader's ``config_path``
        at a ``config.json`` that DOES contain the grant, leaves the keystone leaf
        ABSENT, drives a fresh owner slot create, and asserts the slot gets no trust
        flags. If a ``config.json`` fallback were ever reintroduced, this slot would
        come back ``trust_reads`` -- which is exactly what the step-4 mutation
        proves this test catches.
        """
        import json as _json

        from aiohttp import web
        from aiohttp.test_utils import TestClient, TestServer

        from kiro_crew.config import loader as _loader
        from kiro_crew.dashboard.chat import api_chat_slot_create

        # The grant, written where an auto-approved agent shell could put it.
        cfg_file = tmp_path / "config.json"
        cfg_file.write_text(
            _json.dumps({"agent": {"default_approval_mode": "trust_reads"}}),
            encoding="utf-8",
        )
        # Make the REAL loader read that file, so this cannot pass merely because the
        # config was never loaded -- a reintroduced fallback would read it here.
        monkeypatch.setattr(_loader, "config_path", lambda: cfg_file)
        # Keystone leaf deliberately absent; owner posture so the read gate is open.
        assert not (tmp_path / "default_approval_mode.json").exists()
        monkeypatch.setattr(
            "kiro_crew.dashboard.handlers.source_providers.is_owner_dashboard_request",
            lambda _r: True,
        )
        state = TestOnlyAHumanDashboardCallerInheritsTheDefault._state(tmp_path)

        async def as_owner(request: web.Request) -> web.Response:
            request["app"] = ""
            return await api_chat_slot_create(request)

        app = web.Application()
        app["state"] = state
        app.router.add_post("/api/chat/slots", as_owner)
        async with TestClient(TestServer(app)) as client:
            resp = await client.post("/api/chat/slots", json={"name": "cfgjson"})
            assert resp.status == 200, await resp.text()

        slot = next(iter(state._slots.values()))
        assert slot._trust is False, (
            "a config.json grant leaked into a new session; the read path has a "
            "config.json fallback it must not have"
        )
        assert slot._trust_reads is False

    @pytest.mark.asyncio
    async def test_an_absent_leaf_fails_closed_and_grants_nothing(self, tmp_path, monkeypatch):
        """No keystone leaf -> ``load_mode()`` is ``normal`` and a new slot is untiered.

        The direct read and the end-to-end create are both asserted: ``load_mode``
        must resolve the floor with no leaf present, and a slot minted while the leaf
        is absent must carry no trust flags.
        """
        import types

        from aiohttp import web
        from aiohttp.test_utils import TestClient, TestServer

        from kiro_crew.config import KiroCrewConfig
        from kiro_crew.dashboard.chat import api_chat_slot_create

        # The read fails closed at the source.
        assert not (tmp_path / "default_approval_mode.json").exists()
        assert default_approval_state.load_mode() == "normal"

        monkeypatch.setattr(
            "kiro_crew.dashboard.handlers.source_providers.is_owner_dashboard_request",
            lambda _r: True,
        )
        # A plain default config for agent/workspace resolution, kept isolated.
        monkeypatch.setattr(
            "kiro_crew.dashboard.chat_handlers.KiroCrewConfig",
            types.SimpleNamespace(load=lambda: KiroCrewConfig()),
        )
        state = TestOnlyAHumanDashboardCallerInheritsTheDefault._state(tmp_path)

        async def as_owner(request: web.Request) -> web.Response:
            request["app"] = ""
            return await api_chat_slot_create(request)

        app = web.Application()
        app["state"] = state
        app.router.add_post("/api/chat/slots", as_owner)
        async with TestClient(TestServer(app)) as client:
            resp = await client.post("/api/chat/slots", json={"name": "noleaf"})
            assert resp.status == 200, await resp.text()

        slot = next(iter(state._slots.values()))
        assert slot._trust is False, "an absent keystone leaf granted a tier; it must fail closed"
        assert slot._trust_reads is False
