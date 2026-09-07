"""Exercise the documented maintenance patch on a stopped, populated test home."""

from __future__ import annotations

import ast
import asyncio
import inspect
import json
import shutil
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiohttp.test_utils import TestClient, TestServer
from test_member_memory_creation_capability import _app, _environment

from kiro_crew import member_memory_auth as auth
from kiro_crew.acp.client import AcpClient
from kiro_crew.acp.runtime import AcpRuntime
from kiro_crew.agent_discovery import AgentInfo
from kiro_crew.config.loader import (
    KiroCrewAgentConfig,
    KiroCrewConfig,
    MemoryStoreConfig,
    config_dir,
)
from kiro_crew.context import session_store_for_turn
from kiro_crew.dashboard.handlers import agents as handlers
from kiro_crew.history import ConversationLog
from kiro_crew.history_consolidation import HistoryConsolidator
from kiro_crew.memory import MemoryStore
from kiro_crew.memory_stores import (
    UnknownMemoryStore,
    memory_store_dir_for,
    memory_stores_root,
    provision_member_memory,
    require_member_memory_store,
)
from kiro_crew.providers.acp import AcpProvider
from kiro_crew.session import SessionManager
from kiro_crew.subagent_persistence import create_agent_folder
from kiro_crew.vector_memory import VectorMemoryStore


def _file_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def _private_memory_mcp_failure(backend: str) -> str:
    """Maintenance withdrawal: admit no new private ACP execution."""
    return (
        "Private member execution and new private memory creation are paused "
        "by this maintenance build. Keep the existing memory assignments. "
        "Install a repaired build and restart the gateway to resume private members."
    )


def _documented_patch():
    path = Path(__file__).resolve().parents[1] / "docs/system-specs/modules/memory-skills-hooks.md"
    text = path.read_text(encoding="utf-8")
    section = text.split("### Emergency withdrawal of private execution\n", 1)[1]
    source = section.split("```python\n", 1)[1].split("```", 1)[0]
    documented = ast.parse(source, filename=str(path))
    tested = ast.parse(inspect.getsource(_private_memory_mcp_failure))
    # Compare the entire module, including the signature and any extra statements.
    # Documentation is data; only the statically defined test function is called.
    assert ast.dump(documented, include_attributes=False) == ast.dump(
        tested, include_attributes=False
    ), "documented withdrawal patch diverges from the tested replacement"
    return _private_memory_mcp_failure


@pytest.mark.parametrize("change", ["changed_return", "extra_statement"])
def test_documented_patch_refuses_changed_or_executable_instructions(change, monkeypatch, tmp_path):
    path = Path(__file__).resolve().parents[1] / "docs/system-specs/modules/memory-skills-hooks.md"
    original_read = Path.read_text
    text = original_read(path, encoding="utf-8")
    section = text.split("### Emergency withdrawal of private execution\n", 1)[1]
    source = section.split("```python\n", 1)[1].split("```", 1)[0]
    sentinel = tmp_path / "documentation-executed"
    if change == "changed_return":
        altered = source.replace("by this maintenance build", "by an untested replacement")
    else:
        altered = (
            source + f"\nfrom pathlib import Path\nPath({str(sentinel)!r}).write_text('ran')\n"
        )
    assert altered != source
    changed_document = text.replace(source, altered, 1)

    def read_document(target, *args, **kwargs):
        if target == path:
            return changed_document
        return original_read(target, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read_document)
    with pytest.raises(AssertionError, match="documented withdrawal patch diverges"):
        _documented_patch()
    assert not sentinel.exists()


@pytest.fixture
def populated_install(monkeypatch):
    # Only OS capability discovery is simulated. Identity, files, config,
    # admission decisions and the documented replacement remain real.
    cfg = _environment(monkeypatch, "linux", "kas", "auto", "namespace", False)
    cfg.agents["writer"] = KiroCrewAgentConfig(kiro_agent="kirocrew")
    cfg.agents["peer"] = KiroCrewAgentConfig(kiro_agent="kirocrew")
    writer = provision_member_memory(cfg, "writer")
    peer = provision_member_memory(cfg, "peer")
    cfg.memory_stores["legacy-team"] = MemoryStoreConfig(memory_version=1)
    cfg.agents["legacy-reader"] = KiroCrewAgentConfig(memory_store="legacy-team")
    cfg.save()
    memory_store_dir_for("legacy-team").mkdir()
    for name in ("default", "legacy-team", writer, peer):
        db = (
            config_dir() / "memory.db"
            if name == "default"
            else memory_store_dir_for(name) / "memory.db"
        )
        store = VectorMemoryStore(db_path=db, embedding_dim=2)
        store.init()
        try:
            assert store.set_semantic("project.owner", name, 1.0, "user_explicit") is None
            assert store.write_episodic(
                f"The {name} project keeps its existing records.", defer_embedding=True
            )
        finally:
            store.close()
    keys = (
        "dashboard:member-writer",
        "cron:withdrawal",
        "subagent:withdrawal",
        "taskrunner:withdrawal:runtime",
    )
    log = ConversationLog()
    log.update_metadata("dashboard:legacy", {"memory_store": "legacy-team"})
    create_agent_folder("withdrawal", memory_store=writer)
    for key in keys:
        auth.bind_private_session_store(key, writer)
        log.update_metadata(key, {"memory_store": writer})
        log.append(key, "user", "Retain the existing project decision.")
        log.append(key, "assistant", "The project decision is recorded.")
    assert auth.private_memory_store_for_session(keys[0]) == writer
    auth.require_private_memory_execution(session_key=keys[0])
    # Step 1 pauses allocations before stopping the old admission objects.
    cfg.memory.private_provisioning_enabled = False
    cfg.session.pool_size = 0
    cfg.save()
    return cfg, writer, peer, keys, log


@pytest.mark.asyncio
async def test_documented_withdrawal_preserves_populated_install_and_v1(
    populated_install, monkeypatch, tmp_path
):
    cfg, writer, peer, keys, log = populated_install
    factory = cfg.create_provider_factory()
    old_provider = factory(keys[0], cwd=str(tmp_path))
    try:
        await asyncio.wait_for(old_provider.prepare_private_memory(), timeout=5)
        assert old_provider._private_memory and old_provider._private_memory_prepared
    finally:
        # This fixture has no model processes. Close its actual old provider object
        # before taking an offline archive or applying the maintenance build.
        await asyncio.wait_for(old_provider.shutdown(), timeout=5)
    del old_provider
    home = await asyncio.to_thread(config_dir)
    archive = tmp_path / "offline-home"
    await asyncio.to_thread(shutil.copytree, home, archive)
    assert await asyncio.to_thread(_file_bytes, archive) == await asyncio.to_thread(
        _file_bytes, home
    )
    root = await asyncio.to_thread(memory_stores_root)
    inventory_before = await asyncio.to_thread(lambda: sorted(path.name for path in root.iterdir()))
    private_before = await asyncio.to_thread(
        lambda: [
            (memory_store_dir_for(name), _file_bytes(memory_store_dir_for(name)))
            for name in (writer, peer)
        ]
    )
    bindings_before = await asyncio.to_thread(_file_bytes, home / "member-memory-bindings")
    config_before = await asyncio.to_thread((home / "config.json").read_bytes)
    patch_function = await asyncio.to_thread(_documented_patch)
    launch = AsyncMock(side_effect=AssertionError("private provider reached process startup"))

    async def process_boundary(provider):
        await launch(provider)

    monkeypatch.setattr(AcpProvider, "_start_kiro_runtime", process_boundary)
    monkeypatch.setattr(AcpClient, "ensure_ready", process_boundary)
    app = _app(monkeypatch)
    manager = SessionManager(cfg, provider_factory=factory)
    await asyncio.to_thread(
        manager._session_map.set, keys[0], "saved-native-session", provider="kas"
    )
    builder = SimpleNamespace(conversation_log=log, ensure_store=AsyncMock(return_value=None))
    try:
        with pytest.MonkeyPatch.context() as maintenance:
            maintenance.setattr(auth, "_private_memory_mcp_failure", patch_function)
            async with TestClient(TestServer(app)) as client:
                # The documented allocation pause is respected at the actual HTTP front door.
                response = await client.post(
                    "/api/agents", json={"name": "new-member", "kiro_agent": "kirocrew"}
                )
                assert response.status == 409
                assert (await response.json())["code"] == "member_memory_unavailable"
                assert await asyncio.to_thread((home / "config.json").read_bytes) == config_before
                # The maintenance patch must also refuse if allocation is re-enabled.
                cfg.memory.private_provisioning_enabled = True
                await asyncio.to_thread(cfg.save)
                checkpoint = await asyncio.to_thread((home / "config.json").read_bytes)
                discovered = AgentInfo(
                    name="new-member",
                    filename="new-member.json",
                    description="",
                    model="auto",
                    source="package",
                )
                maintenance.setattr(handlers, "list_agents", lambda: [discovered])
                for method, path, body in (
                    ("post", "/api/agents", {"name": "new-member", "kiro_agent": "kirocrew"}),
                    ("post", "/api/agents/sync", None),
                    ("put", "/api/agents/reviewer", {"provision_memory": True}),
                ):
                    response = await client.request(method, path, json=body)
                    result = await response.json()
                    assert response.status == 409, result
                    assert result["code"] == "member_memory_unavailable"
                    assert "by this maintenance build" in result["error"]
                    assert await asyncio.to_thread((home / "config.json").read_bytes) == checkpoint
                cfg.memory.private_provisioning_enabled = False
                await asyncio.to_thread(cfg.save)
                # The fixture's two owner saves stamp the config; admissions must
                # preserve the exact bytes after these deliberate setting changes.
                protected_config = await asyncio.to_thread((home / "config.json").read_bytes)

            # Real protected identities and persisted transcript/run state feed the
            # common direct-chat, schedule, child and task admission seams.
            for key in keys:
                with pytest.raises(UnknownMemoryStore, match="by this maintenance build"):
                    await asyncio.wait_for(session_store_for_turn(builder, key), timeout=5)
                with pytest.raises(UnknownMemoryStore, match="by this maintenance build"):
                    await asyncio.wait_for(
                        manager.get_or_create(
                            key, agent="kirocrew", model="auto", cwd=str(tmp_path)
                        ),
                        timeout=5,
                    )
                assert key not in manager._sessions
            assert (
                await asyncio.to_thread(manager._session_map.get, keys[0]) == "saved-native-session"
            )
            builder.ensure_store.assert_not_awaited()
            launch.assert_not_awaited()

            # Direct constructors cannot bypass manager/context preparation.
            for constructor in (AcpClient, AcpRuntime):
                with pytest.raises(UnknownMemoryStore, match="by this maintenance build"):
                    constructor(work_dir=tmp_path, acp_backend="kas", private_memory=True)
            consolidator = HistoryConsolidator(log, MemoryStore(), migrated=True)
            llm = AsyncMock()
            maintenance.setattr(consolidator, "_call_llm", llm)
            with pytest.raises(UnknownMemoryStore, match="by this maintenance build"):
                await asyncio.wait_for(
                    consolidator._consolidate(keys[0], include_history=False), timeout=5
                )
            llm.assert_not_awaited()

            # Both V1 scopes still resolve and reach the existing provider boundary.
            for key, expected_store in (
                ("dashboard:global", ""),
                ("dashboard:legacy", "legacy-team"),
            ):
                assert await session_store_for_turn(builder, key) == expected_store
                v1 = factory(key, cwd=str(tmp_path))
                try:
                    with pytest.raises(AssertionError, match="reached process startup"):
                        await asyncio.wait_for(v1.start(), timeout=5)
                    assert not v1._private_memory
                    launch.assert_awaited_with(v1)
                finally:
                    await asyncio.wait_for(v1.shutdown(), timeout=5)
            assert launch.await_count == 2
            builder.ensure_store.assert_awaited_once_with("legacy-team")

            def use_v1_memory():
                for name in ("default", "legacy-team"):
                    db = (
                        home / "memory.db"
                        if name == "default"
                        else memory_store_dir_for(name) / "memory.db"
                    )
                    store = VectorMemoryStore(db_path=db, embedding_dim=2)
                    store.init()
                    try:
                        assert store.algorithm_version == "v1"
                        assert json.loads(store.get_semantic("project.owner")["value_json"]) == name
                        assert (
                            store.set_semantic(
                                "project.maintenance", "V1 remains writable", 1.0, "user_explicit"
                            )
                            is None
                        )
                        assert (
                            json.loads(store.get_semantic("project.maintenance")["value_json"])
                            == "V1 remains writable"
                        )
                    finally:
                        store.close()

            await asyncio.to_thread(use_v1_memory)
            for private_root, before in private_before:
                assert await asyncio.to_thread(_file_bytes, private_root) == before
            assert (
                await asyncio.to_thread(lambda: sorted(path.name for path in root.iterdir()))
                == inventory_before
            )
            assert (
                await asyncio.to_thread(_file_bytes, home / "member-memory-bindings")
                == bindings_before
            )
            assert await asyncio.to_thread((home / "config.json").read_bytes) == protected_config
    finally:
        await asyncio.wait_for(manager.close_all(), timeout=5)

    # The repaired-build phase restores the real admission helper and uses the
    # existing assignments. It does not provision a replacement or adopt V1.
    loaded = await asyncio.to_thread(KiroCrewConfig.load)
    for member, store in (("writer", writer), ("peer", peer)):
        assert await asyncio.to_thread(require_member_memory_store, loaded, member) == store
    assert await asyncio.to_thread(require_member_memory_store, loaded, "reviewer") == "default"
    assert (
        await asyncio.to_thread(require_member_memory_store, loaded, "legacy-reader")
        == "legacy-team"
    )
    await asyncio.to_thread(auth.require_private_memory_execution, session_key=keys[0])
    recovered = loaded.create_provider_factory()(keys[0], cwd=str(tmp_path))
    try:
        await asyncio.wait_for(recovered.prepare_private_memory(), timeout=5)
        assert recovered._private_memory and recovered._private_memory_prepared
        assert await asyncio.to_thread(auth.read_private_session_store, keys[0]) == writer
    finally:
        await asyncio.wait_for(recovered.shutdown(), timeout=5)
    for private_root, before in private_before:
        assert await asyncio.to_thread(_file_bytes, private_root) == before
    assert (
        await asyncio.to_thread(lambda: sorted(path.name for path in root.iterdir()))
        == inventory_before
    )
    assert await asyncio.to_thread(_file_bytes, home / "member-memory-bindings") == bindings_before
