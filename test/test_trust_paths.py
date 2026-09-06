"""Path-scoped trust grants for file-write tools (GitHub #938).

The property under test throughout is DEFAULT-DENY. A grant here widens what a
write tool may do without asking again, so every case below is written as "does
this grant refuse the thing it must refuse", not "does it allow the happy path".
The four escapes that would each turn one directory into the whole filesystem
get their own test: ``..`` traversal, a symlink at the leaf, a symlinked
ancestor, and a sibling directory whose name merely starts with the granted one.
"""

from __future__ import annotations

import asyncio
import json
import os
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from kiro_crew.dashboard.state import DashboardState, _ChatSlot
from kiro_crew.history import ConversationLog
from kiro_crew.trust_paths import (
    _WRITE_ONLY_BUILTIN_TOOLS,
    WRITE_GRANT_DECISIONS,
    WRITE_TOOL_KIND,
    WriteGrant,
    derive_write_grant_offer,
    match_write_grant,
    write_tool_trust_key,
)

WRITE_TOOL = "fs_write"
KEY = write_tool_trust_key("", WRITE_TOOL)


def _offer(path: str, *, project: str = "", kind: str = WRITE_TOOL_KIND, tool: str = WRITE_TOOL):
    return derive_write_grant_offer(
        tool_kind=kind,
        raw_params={"path": path},
        tool_name=tool,
        mcp_server_name="",
        project=project,
    )


def _match(path: str, grants, *, kind: str = WRITE_TOOL_KIND, tool: str = WRITE_TOOL):
    return match_write_grant(
        tool_kind=kind,
        raw_params={"path": path},
        tool_name=tool,
        mcp_server_name="",
        grants=grants,
    )


# ── Tool identity ──


class TestWriteToolTrustKey:
    def test_requires_a_tool_name(self):
        # Without a canonical identity there is nothing to bind a grant to, so
        # no grant may be minted. Empty is the fail-closed answer.
        assert write_tool_trust_key("srv", "") == ""

    def test_builtin_tool_needs_no_server(self):
        # A built-in write tool legitimately has no MCP server name; that must
        # not disqualify it, since it is the common case for this feature.
        assert write_tool_trust_key("", "fs_write").startswith("fswrite-trust:v2:")

    def test_component_split_is_injective(self):
        # The plain mcp__server__tool spelling collides here; the encoded form
        # must not, or two different tools could share one path grant.
        assert write_tool_trust_key("github", "repo__delete") != write_tool_trust_key(
            "github__repo", "delete"
        )

    def test_case_distinct_tools_get_distinct_keys(self):
        # str.lower() folding here would merge two case-distinct MCP tools onto
        # ONE grant key, letting a tool the user never approved spend the other
        # one's write grant. Identity is therefore exact-case on purpose.
        assert write_tool_trust_key("", "FS_Write") != write_tool_trust_key("", "fs_write")
        assert write_tool_trust_key("Srv", "tool") != write_tool_trust_key("srv", "tool")


# ── What may be offered ──


class TestOfferGating:
    def test_no_offer_for_a_non_write_kind(self, tmp_path):
        # A read tool must never be handed a write grant, and 'kind' is the only
        # signal that separates them.
        assert _offer(str(tmp_path / "f.txt"), kind="read") == {}

    def test_no_offer_without_a_tool_identity(self, tmp_path):
        assert _offer(str(tmp_path / "f.txt"), tool="") == {}

    def test_dir_tier_withheld_when_a_leaf_symlink_resolves_outside(self, tmp_path):
        # docs/README.md -> ../README.md: the write lands OUTSIDE docs/, so a
        # tier saying "writes in and under docs/" would not contain the write
        # it is consenting to. Same containment rule the ws tier applies.
        outside = tmp_path / "README.md"
        outside.write_text("x")
        docs = tmp_path / "docs"
        docs.mkdir()
        link = docs / "README.md"
        try:
            link.symlink_to(outside)
        except OSError:
            pytest.skip("symlinks unavailable")
        out = _offer(str(link))
        assert "write_dir_root" not in out
        # The file tier remains: it names the RESOLVED target, so it is honest.
        assert out.get("write_file_root") == os.path.realpath(str(outside))

    def test_forged_edit_kind_on_a_non_write_builtin_gets_no_offer(self, tmp_path):
        # The payload `kind` is backend-authored. A destructive builtin
        # (execute_bash) forging kind="edit" must not be handed a write-grant
        # offer: classification comes from the provenance-verified identity,
        # never from the kind — otherwise one user click on a card that says
        # "write" mints a durable grant a destructive tool later spends.
        assert _offer(str(tmp_path / "f.txt"), tool="execute_bash") == {}

    def test_forged_edit_kind_on_an_mcp_tool_gets_no_offer(self, tmp_path):
        # No provenance-verified signal says what an arbitrary MCP tool does
        # with a `path` argument, so MCP tools fail closed to the prompt.
        assert (
            derive_write_grant_offer(
                tool_kind=WRITE_TOOL_KIND,
                raw_params={"path": str(tmp_path / "f.txt")},
                tool_name="innocuous_writer",
                mcp_server_name="srv",
            )
            == {}
        )

    def test_a_multi_capability_write_builtin_gets_no_offer(self, tmp_path):
        # `code` writes files AND shells out (its governance scopes include
        # `commands`), so a grant whose label says only "write to this path"
        # must not auto-approve it. Only write-ONLY builtins qualify.
        assert _offer(str(tmp_path / "f.txt"), tool="code") == {}

    def test_write_only_allowlist_derives_from_the_governance_table(self):
        # The classification source of truth is BUILTIN_TOOL_SCOPES: exactly
        # the builtins whose scope tuple is ("filesystem.write",). Pin the
        # current membership so widening it is a reviewed data change.
        from kiro_crew.platform.governance import BUILTIN_TOOL_SCOPES

        expected = {
            name for name, scopes in BUILTIN_TOOL_SCOPES.items() if scopes == ("filesystem.write",)
        }
        assert _WRITE_ONLY_BUILTIN_TOOLS == expected
        assert "fs_write" in _WRITE_ONLY_BUILTIN_TOOLS
        assert "code" not in _WRITE_ONLY_BUILTIN_TOOLS
        assert "execute_bash" not in _WRITE_ONLY_BUILTIN_TOOLS

    def test_no_offer_for_a_relative_path(self, tmp_path, monkeypatch):
        # Resolving a relative path needs a cwd this layer does not know.
        # Guessing one is how a grant lands on a different tree entirely.
        monkeypatch.chdir(tmp_path)
        assert _offer("f.txt") == {}

    def test_no_offer_for_two_targets(self, tmp_path):
        # A batch write has no single "this directory". Picking one of the two
        # would grant a scope the label does not describe.
        out = derive_write_grant_offer(
            tool_kind=WRITE_TOOL_KIND,
            raw_params={"path": str(tmp_path / "a"), "file_path": str(tmp_path / "b")},
            tool_name=WRITE_TOOL,
            mcp_server_name="",
        )
        assert out == {}

    def test_no_offer_when_the_path_scan_truncated(self, tmp_path):
        # A truncated walk may have MISSED a second target, so it is
        # unverifiable rather than single-target. Same fail-closed reading the
        # governance plane gives it.
        params = {"ops": [{"path": str(tmp_path / f"f{i}")} for i in range(400)]}
        assert (
            derive_write_grant_offer(
                tool_kind=WRITE_TOOL_KIND,
                raw_params=params,
                tool_name=WRITE_TOOL,
                mcp_server_name="",
            )
            == {}
        )

    def test_no_offer_for_a_hard_linked_target(self, tmp_path):
        # realpath resolves symlinks but not hard links: a second name for the
        # same inode may live outside any granted root, so a grant minted for
        # the inside name could never be honoured safely. No tier is offered.
        outside = tmp_path / "outside.txt"
        outside.write_text("x")
        d = tmp_path / "granted"
        d.mkdir()
        alias = d / "alias.txt"
        os.link(str(outside), str(alias))
        assert _offer(str(alias)) == {}

    def test_no_offer_for_a_nul_byte_in_the_path(self, tmp_path):
        assert _offer(f"{tmp_path}/a\x00b") == {}

    def test_directory_tier_withheld_at_a_filesystem_root(self):
        # dirname("/hosts") is "/". Offering that as "this directory" would hand
        # out the whole filesystem behind a label that says otherwise.
        out = _offer(f"{os.sep}hosts")
        assert "write_file_root" in out
        assert "write_dir_root" not in out

    def test_workspace_tier_withheld_when_the_target_is_outside_it(self, tmp_path):
        project = tmp_path / "proj"
        project.mkdir()
        outside = tmp_path / "elsewhere"
        outside.mkdir()
        out = _offer(str(outside / "f.txt"), project=str(project))
        assert "write_dir_root" in out
        assert "write_ws_root" not in out

    def test_workspace_tier_offered_for_a_target_inside_it(self, tmp_path):
        project = tmp_path / "proj"
        (project / "src").mkdir(parents=True)
        out = _offer(str(project / "src" / "f.txt"), project=str(project))
        assert out["write_ws_root"] == os.path.realpath(str(project))

    def test_roots_are_realpaths_not_the_requested_spelling(self, tmp_path):
        real = tmp_path / "real"
        real.mkdir()
        link = tmp_path / "link"
        link.symlink_to(real, target_is_directory=True)
        out = _offer(str(link / "f.txt"))
        # Stored as the resolved location, so a later request that reaches the
        # same file by its real name matches and one that merely reuses the link
        # name cannot smuggle in a different target.
        assert out["write_dir_root"] == os.path.realpath(str(real))


# ── What a grant refuses ──


class TestGrantMatching:
    def test_no_grants_never_matches(self, tmp_path):
        assert _match(str(tmp_path / "f.txt"), set()) is None

    def test_directory_grant_covers_a_sibling_file(self, tmp_path):
        d = tmp_path / "granted"
        d.mkdir()
        grant = WriteGrant(KEY, os.path.realpath(str(d)), True)
        assert _match(str(d / "new.txt"), {grant}) == grant

    def test_directory_grant_covers_a_nested_file(self, tmp_path):
        d = tmp_path / "granted"
        (d / "deep").mkdir(parents=True)
        grant = WriteGrant(KEY, os.path.realpath(str(d)), True)
        assert _match(str(d / "deep" / "new.txt"), {grant}) is grant

    def test_directory_grant_refuses_another_directory(self, tmp_path):
        # The headline default-deny property: dir A is not dir B.
        a = tmp_path / "a"
        b = tmp_path / "b"
        a.mkdir()
        b.mkdir()
        grant = WriteGrant(KEY, os.path.realpath(str(a)), True)
        assert _match(str(b / "f.txt"), {grant}) is None

    def test_directory_grant_refuses_dot_dot_traversal(self, tmp_path):
        a = tmp_path / "a"
        b = tmp_path / "b"
        a.mkdir()
        b.mkdir()
        grant = WriteGrant(KEY, os.path.realpath(str(a)), True)
        assert _match(f"{a}{os.sep}..{os.sep}b{os.sep}f.txt", {grant}) is None

    def test_directory_grant_refuses_a_symlink_escape_at_the_leaf(self, tmp_path):
        # granted/link -> outside/secret. The path LOOKS inside the grant; the
        # write lands outside it. Resolving the leaf is what catches this.
        granted = tmp_path / "granted"
        granted.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        secret = outside / "secret"
        secret.write_text("x")
        (granted / "link").symlink_to(secret)
        grant = WriteGrant(KEY, os.path.realpath(str(granted)), True)
        assert _match(str(granted / "link"), {grant}) is None

    def test_directory_grant_refuses_a_symlinked_ancestor_escape(self, tmp_path):
        # granted/sub -> outside. The leaf does not exist yet, so only resolving
        # the ANCESTOR shows the write leaving the grant.
        granted = tmp_path / "granted"
        granted.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        (granted / "sub").symlink_to(outside, target_is_directory=True)
        grant = WriteGrant(KEY, os.path.realpath(str(granted)), True)
        assert _match(str(granted / "sub" / "new.txt"), {grant}) is None

    def test_directory_grant_refuses_a_hard_link_escape(self, tmp_path):
        # A hard link inside the granted root aliases an inode whose OTHER name
        # lives outside it. realpath cannot see that, so containment alone
        # would match and an automatic write would corrupt the outside file.
        # The multi-link refusal closes this escape.
        outside = tmp_path / "outside.txt"
        outside.write_text("x")
        d = tmp_path / "granted"
        d.mkdir()
        alias = d / "alias.txt"
        os.link(str(outside), str(alias))
        grant = WriteGrant(KEY, os.path.realpath(str(d)), True)
        assert _match(str(alias), {grant}) is None

    def test_singly_linked_existing_file_still_matches(self, tmp_path):
        # The refusal is about multiplicity, not existence: a plain existing
        # file (one hard link) inside the root keeps matching, or every grant
        # would be a dead button for edits of existing files.
        d = tmp_path / "granted"
        d.mkdir()
        f = d / "plain.txt"
        f.write_text("x")
        grant = WriteGrant(KEY, os.path.realpath(str(d)), True)
        assert _match(str(f), {grant}) == grant

    def test_directory_grant_refuses_a_name_prefixed_sibling(self, tmp_path):
        # "/…/app" must not cover "/…/appdata" — the classic string-prefix bug.
        app = tmp_path / "app"
        appdata = tmp_path / "appdata"
        app.mkdir()
        appdata.mkdir()
        grant = WriteGrant(KEY, os.path.realpath(str(app)), True)
        assert _match(str(appdata / "f.txt"), {grant}) is None

    def test_file_grant_is_exact_and_not_its_neighbour(self, tmp_path):
        target = tmp_path / "one.txt"
        target.write_text("x")
        grant = WriteGrant(KEY, os.path.realpath(str(target)), False)
        assert _match(str(target), {grant}) is grant
        assert _match(str(tmp_path / "two.txt"), {grant}) is None

    def test_a_grant_belongs_to_one_TOOL(self, tmp_path):
        # A directory granted to fs_write must not be spendable by some other
        # tool that merely also takes a `path` argument — the reason the tool
        # identity is part of the grant and not decoration.
        d = tmp_path / "granted"
        d.mkdir()
        grant = WriteGrant(KEY, os.path.realpath(str(d)), True)
        assert _match(str(d / "f.txt"), {grant}, tool="some_other_tool") is None

    def test_a_grant_is_not_spendable_by_a_non_write_kind(self, tmp_path):
        d = tmp_path / "granted"
        d.mkdir()
        grant = WriteGrant(KEY, os.path.realpath(str(d)), True)
        assert _match(str(d / "f.txt"), {grant}, kind="read") is None

    def test_a_grant_is_not_spendable_under_a_forged_edit_kind(self, tmp_path):
        # Even a grant whose stored key SAYS execute_bash (however minted) must
        # not be spendable: the identity gate in _resolve refuses to classify a
        # non-write-only builtin as a write, whatever kind the payload claims.
        d = tmp_path / "granted"
        d.mkdir()
        forged_key = write_tool_trust_key("", "execute_bash")
        grant = WriteGrant(forged_key, os.path.realpath(str(d)), True)
        assert _match(str(d / "f.txt"), {grant}, tool="execute_bash") is None

    def test_a_grant_is_not_spendable_by_an_mcp_tool(self, tmp_path):
        d = tmp_path / "granted"
        d.mkdir()
        mcp_key = write_tool_trust_key("srv", "writer")
        grant = WriteGrant(mcp_key, os.path.realpath(str(d)), True)
        assert (
            match_write_grant(
                tool_kind=WRITE_TOOL_KIND,
                raw_params={"path": str(d / "f.txt")},
                tool_name="writer",
                mcp_server_name="srv",
                grants={grant},
            )
            is None
        )

    def test_a_grant_with_an_empty_root_matches_nothing(self, tmp_path):
        # Defence in depth: a malformed stored grant must not become a wildcard.
        assert _match(str(tmp_path / "f.txt"), {WriteGrant(KEY, "", True)}) is None

    @pytest.mark.skipif(
        os.path.normcase("/A") == os.path.normcase("/a"),
        reason="only meaningful where the filesystem is case-sensitive",
    )
    def test_case_is_not_folded(self, tmp_path):
        # The command tier matches with str.lower(); a path grant must not, or a
        # grant for /srv/Secret would authorize a write to /srv/secret.
        upper = tmp_path / "Granted"
        lower = tmp_path / "granted"
        upper.mkdir()
        lower.mkdir()
        grant = WriteGrant(KEY, os.path.realpath(str(upper)), True)
        assert _match(str(lower / "f.txt"), {grant}) is None

    def test_workspace_grant_covers_a_deep_subdirectory(self, tmp_path):
        project = tmp_path / "proj"
        (project / "a" / "b").mkdir(parents=True)
        grant = WriteGrant(KEY, os.path.realpath(str(project)), True)
        assert _match(str(project / "a" / "b" / "f.txt"), {grant}) is grant


# ── HTTP handler ──


def _make_state(tmp_path):
    sessions = MagicMock(count=0)
    sessions.get_pid = MagicMock(return_value=None)
    sessions.remove = AsyncMock()
    return DashboardState(
        sessions=sessions,
        crons=MagicMock(list_jobs=MagicMock(return_value=[]), status=MagicMock(return_value={})),
        lessons=MagicMock(load_all=MagicMock(return_value=[])),
        start_time=0.0,
        conversation_log=ConversationLog(base_dir=tmp_path),
    )


@web.middleware
async def _test_auth_middleware(request, handler):
    request.setdefault("app", "")
    request.setdefault("user", "local-app")
    return await handler(request)


def _make_app(state: DashboardState) -> web.Application:
    from kiro_crew.dashboard.chat import api_chat_slot_approve

    app = web.Application(middlewares=[_test_auth_middleware])
    app["state"] = state
    app.router.add_post("/api/chat/slots/{slot}/approve", api_chat_slot_approve)
    return app


def _armed_slot(state, request_id: str, offer: dict[str, str]):
    slot = _ChatSlot(key="slot-1")
    state._slots["slot-1"] = slot
    fut: asyncio.Future[str] = asyncio.get_running_loop().create_future()
    slot._approval_futures[request_id] = fut
    meta = {"request_id": request_id, **offer}
    slot.messages.append({"role": "permission", "content": "Editing", "cls": json.dumps(meta)})
    return slot, fut


class TestApproveHandlerPathGrants:
    @pytest.mark.asyncio
    async def test_directory_grant_is_stored_and_the_call_resolves(self, tmp_path):
        state = _make_state(tmp_path)
        d = tmp_path / "granted"
        d.mkdir()
        offer = _offer(str(d / "f.txt"))
        slot, fut = _armed_slot(state, "req-1", offer)
        async with TestClient(TestServer(_make_app(state))) as client:
            resp = await client.post(
                "/api/chat/slots/slot-1/approve",
                json={
                    "action": "trust_path_dir",
                    "request_id": "req-1",
                    "pattern": offer["write_dir_root"],
                },
            )
            assert resp.status == 200
        assert slot._trusted_write_grants == {
            WriteGrant(offer["write_tool_key"], offer["write_dir_root"], True)
        }
        assert fut.result() == "approved"
        # And the grant does what its label promised, in both directions.
        assert _match(str(d / "other.txt"), slot._trusted_write_grants) is not None
        assert _match(str(tmp_path / "elsewhere.txt"), slot._trusted_write_grants) is None

    @pytest.mark.asyncio
    async def test_a_non_string_action_is_rejected_not_a_crash(self, tmp_path):
        # `action: []` / `{}` is unhashable: probing it against the
        # WRITE_GRANT_DECISIONS dict raised TypeError — an HTTP 500 with the
        # approval future left unresolved. It must resolve as an ordinary
        # reject, exactly as the pre-existing string-equality branches treated
        # a malformed action, and mint nothing.
        state = _make_state(tmp_path)
        d = tmp_path / "granted"
        d.mkdir()
        offer = _offer(str(d / "f.txt"))
        slot, fut = _armed_slot(state, "req-crash", offer)
        async with TestClient(TestServer(_make_app(state))) as client:
            resp = await client.post(
                "/api/chat/slots/slot-1/approve",
                json={
                    "action": [],
                    "request_id": "req-crash",
                    "pattern": offer["write_dir_root"],
                },
            )
            assert resp.status < 500
        assert slot._trusted_write_grants == set()
        assert fut.done() and fut.result() == "rejected"

    @pytest.mark.asyncio
    async def test_workspace_grant_is_stored_as_a_subtree(self, tmp_path):
        state = _make_state(tmp_path)
        project = tmp_path / "proj"
        (project / "src").mkdir(parents=True)
        offer = _offer(str(project / "src" / "f.txt"), project=str(project))
        slot, _ = _armed_slot(state, "req-2", offer)
        async with TestClient(TestServer(_make_app(state))) as client:
            resp = await client.post(
                "/api/chat/slots/slot-1/approve",
                json={
                    "action": "trust_path_ws",
                    "request_id": "req-2",
                    "pattern": offer["write_ws_root"],
                },
            )
            assert resp.status == 200
        (grant,) = slot._trusted_write_grants
        assert grant.root == offer["write_ws_root"]
        assert grant.subtree is True

    @pytest.mark.asyncio
    async def test_file_grant_is_stored_as_an_exact_root(self, tmp_path):
        state = _make_state(tmp_path)
        target = tmp_path / "one.txt"
        target.write_text("x")
        offer = _offer(str(target))
        slot, _ = _armed_slot(state, "req-3", offer)
        async with TestClient(TestServer(_make_app(state))) as client:
            resp = await client.post(
                "/api/chat/slots/slot-1/approve",
                json={
                    "action": "trust_path_file",
                    "request_id": "req-3",
                    "pattern": offer["write_file_root"],
                },
            )
            assert resp.status == 200
        (grant,) = slot._trusted_write_grants
        assert grant.subtree is False
        assert _match(str(tmp_path / "two.txt"), slot._trusted_write_grants) is None

    @pytest.mark.asyncio
    async def test_a_client_supplied_root_cannot_widen_the_grant(self, tmp_path):
        # The body `pattern` is consent PROOF, not authority. Sending a wider
        # root than the card displayed must be refused outright rather than
        # stored — this is the escalation the echo check exists to stop.
        state = _make_state(tmp_path)
        d = tmp_path / "granted"
        d.mkdir()
        offer = _offer(str(d / "f.txt"))
        slot, fut = _armed_slot(state, "req-4", offer)
        async with TestClient(TestServer(_make_app(state))) as client:
            resp = await client.post(
                "/api/chat/slots/slot-1/approve",
                json={
                    "action": "trust_path_dir",
                    "request_id": "req-4",
                    "pattern": str(tmp_path),
                },
            )
            assert resp.status == 400
            assert (await resp.json())["code"] == "path_superseded"
        assert slot._trusted_write_grants == set()
        assert not fut.done()

    @pytest.mark.asyncio
    async def test_a_card_with_no_write_scope_cannot_be_granted(self, tmp_path):
        state = _make_state(tmp_path)
        slot, fut = _armed_slot(state, "req-5", {})
        async with TestClient(TestServer(_make_app(state))) as client:
            resp = await client.post(
                "/api/chat/slots/slot-1/approve",
                json={"action": "trust_path_dir", "request_id": "req-5", "pattern": "/tmp"},
            )
            assert resp.status == 400
            assert (await resp.json())["code"] == "path_underivable"
        assert slot._trusted_write_grants == set()
        assert not fut.done()

    @pytest.mark.asyncio
    async def test_a_tier_the_card_withheld_cannot_be_granted(self, tmp_path):
        # The card offered file + dir but NOT workspace (target outside the
        # project). Clicking the withheld tier must fail closed, not fall back
        # to a neighbouring root.
        state = _make_state(tmp_path)
        project = tmp_path / "proj"
        project.mkdir()
        outside = tmp_path / "elsewhere"
        outside.mkdir()
        offer = _offer(str(outside / "f.txt"), project=str(project))
        slot, _ = _armed_slot(state, "req-6", offer)
        async with TestClient(TestServer(_make_app(state))) as client:
            resp = await client.post(
                "/api/chat/slots/slot-1/approve",
                json={
                    "action": "trust_path_ws",
                    "request_id": "req-6",
                    "pattern": str(project),
                },
            )
            assert resp.status == 400
            assert (await resp.json())["code"] == "path_underivable"
        assert slot._trusted_write_grants == set()

    @pytest.mark.asyncio
    async def test_a_missing_pattern_is_refused(self, tmp_path):
        state = _make_state(tmp_path)
        d = tmp_path / "granted"
        d.mkdir()
        offer = _offer(str(d / "f.txt"))
        slot, _ = _armed_slot(state, "req-7", offer)
        async with TestClient(TestServer(_make_app(state))) as client:
            resp = await client.post(
                "/api/chat/slots/slot-1/approve",
                json={"action": "trust_path_dir", "request_id": "req-7"},
            )
            assert resp.status == 400
            assert (await resp.json())["code"] == "path_required"
        assert slot._trusted_write_grants == set()

    @pytest.mark.asyncio
    async def test_a_state_level_approval_cannot_mint_a_path_grant(self, tmp_path):
        # A state-level future has no owning slot, so no canonical card and no
        # scoped store. Falling through to the boolean resolver would run the
        # write having skipped every scope check.
        state = _make_state(tmp_path)
        slot = _ChatSlot(key="slot-1")
        state._slots["slot-1"] = slot
        fut: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        state._approval_futures["req-8"] = fut
        async with TestClient(TestServer(_make_app(state))) as client:
            resp = await client.post(
                "/api/chat/slots/slot-1/approve",
                json={"action": "trust_path_dir", "request_id": "req-8", "pattern": "/tmp"},
            )
            assert resp.status == 400
            assert (await resp.json())["code"] == "approval_not_slot_owned"
        assert not fut.done()

    def test_every_path_decision_inherits_the_state_owner_guard(self):
        from kiro_crew.dashboard.chat_handlers import _DURABLE_TRUST_ACTIONS

        # A new tier added to the table must not be able to skip the guard.
        for decision in WRITE_GRANT_DECISIONS:
            assert decision in _DURABLE_TRUST_ACTIONS
