"""Owner compaction preserves usable memory and refuses an unsafe offline snapshot."""

from __future__ import annotations

import argparse
import json
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace

import pytest

from kiro_crew import member_memory_auth, memory_backup
from kiro_crew import memory_record_metadata as metadata
from kiro_crew import memory_revision_compaction as compaction
from kiro_crew import memory_stores, platform_compat
from kiro_crew._sqlite_compat import sqlite3
from kiro_crew.config import loader
from kiro_crew.vector_memory import VectorMemoryStore

_CUTOFF = "2030-01-01T00:00:00+00:00"


def _rows(db):
    schema = tuple(
        tuple(row)
        for row in db.execute("SELECT type, name, tbl_name, sql FROM sqlite_schema ORDER BY name")
    )
    result = {"schema": schema}
    for kind, name, _, _ in schema:
        if kind in ("table", "view"):
            quoted = '"' + name.replace('"', '""') + '"'
            result[name] = tuple(
                sorted((tuple(row) for row in db.execute(f"SELECT * FROM {quoted}")), key=repr)
            )
    return result


def _read(path):
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
        assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        return _rows(db)


def _proposal(tier, value, *, status="conflict"):
    before = tier.get_semantic("user.work_email")
    assert before is not None
    proposal = metadata.propose_conflict(
        tier.db,
        kind="fact",
        record_id="user.work_email",
        before=before,
        after={**before, "value_json": json.dumps(value)},
        source="consolidation:dm",
    )
    # Forward-compatible proposal statuses must remain outside accepted-history removal.
    tier.db.execute("UPDATE memory_revisions SET status=? WHERE id=?", (status, proposal))
    tier.db.commit()
    return proposal


@pytest.fixture(params=["v1", "named-v1", "v2"])
def populated(request, tmp_path, monkeypatch):
    monkeypatch.setenv("KIROCREW_HOME", str(tmp_path))
    name = "default" if request.param == "v1" else "member-alice"
    private = request.param == "v2"
    directory = tmp_path if name == "default" else tmp_path / "memory_stores" / name
    directory.mkdir(parents=True, exist_ok=True)
    declaration = {"memory_version": 2, "owner_member": "alice"} if private else {}
    config = {"memory_stores": {"default": {}, name: declaration}, "agents": {}}
    if private:
        config["agents"] = {"alice": {"memory_store": name}}
        (directory / "member-memory.json").write_text(json.dumps(declaration), encoding="utf-8")
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    loader._invalidate_config_cache()
    monkeypatch.setattr(memory_stores, "_DECLARED_MEMO", None)
    # Establish an initialized install before recording its immutable identity.
    # The canonical loader can complete missing-agent/default migrations.
    loader.KiroCrewConfig.load()
    tier = VectorMemoryStore(db_path=directory / "memory.db", embedding_dim=2)
    try:
        tier.init()
        proposals = []
        for number in range(1, 7):
            assert (
                tier.set_semantic(
                    "user.work_email", f"address{number}@example.net", 1, "user_explicit"
                )
                is None
            )
            if number == 2:
                proposals.append(_proposal(tier, "stale-proposal@example.net"))
        proposals.append(_proposal(tier, "current-proposal@example.net"))
        proposals.append(_proposal(tier, "pending@example.net", status="pending"))
        proposals.append(_proposal(tier, "future@example.net", status="future_review"))
        for value in ("SQLite", "PostgreSQL"):
            assert tier.set_semantic("project.database", value, 1, "user_explicit") is None
        assert tier.set_semantic("project.obsolete", "Retired project", 1, "user_explicit") is None
        tier.delete_semantic("project.obsolete", "user_explicit")
        assert tier.write_episodic(
            "The owner approved the release after checking its backups.",
            source="user_explicit",
            embedding=[1.0, 0.0],
        )
        assert tier.write_lesson(
            "Verify the restored database before resuming work.",
            source="user_explicit",
            rule_emb=[0.0, 1.0],
        )
        tier.db.execute("UPDATE memory_revisions SET created_at='2020-01-01T00:00:00+00:00'")
        for revision, timestamp in (
            (2, "invalid timestamp"),
            (3, "2035-01-01T00:00:00+00:00"),
            (4, _CUTOFF),
        ):
            tier.db.execute(
                "UPDATE memory_revisions SET created_at=? WHERE record_id=? AND revision=? AND status='accepted'",
                (timestamp, "key:user.work_email", revision),
            )
        tier.db.commit()
        removed = set()
        for record_id, revision in (
            ("key:user.work_email", 1),
            ("key:user.work_email", 5),
            ("key:project.database", 1),
            ("key:project.obsolete", 1),
        ):
            row = tier.db.execute(
                "SELECT id FROM memory_revisions WHERE record_id=? AND revision=? AND status='accepted'",
                (record_id, revision),
            ).fetchone()
            assert row is not None
            removed.add(row[0])
        assert tier.db.execute("SELECT COUNT(*) FROM memory_events").fetchone()[0] > 0
        if private:
            member_memory_auth.bind_private_session_store("dashboard:maintenance-proof", name)
        identity = {config_path: config_path.read_bytes()}
        if private:
            manifest = directory / "member-memory.json"
            binding = member_memory_auth._session_binding_path("dashboard:maintenance-proof")
            identity.update({manifest: manifest.read_bytes(), binding: binding.read_bytes()})
        tier.close()
        yield SimpleNamespace(
            tier=tier,
            path=directory / "memory.db",
            name=name,
            private=private,
            removed=removed,
            proposals=proposals,
            identity=identity,
            root=tmp_path,
        )
    finally:
        tier.close()
        loader._invalidate_config_cache()


def _apply(env, **overrides):
    arguments = dict(
        apply=True,
        expected_count=len(env.removed),
        stopped=True,
        backup=env.root / "compaction-copy.db",
    )
    arguments.update(overrides)
    return compaction.compact_revisions(env.name, _CUTOFF, **arguments)


def test_cli_preview_and_apply_preserve_backup_content_and_future_revisions(
    populated, monkeypatch, capsys
):
    from kiro_crew import cli_commands

    env = populated
    baseline = _read(env.path)
    args = argparse.Namespace(
        mem_action="compact-revisions",
        store=env.name,
        before=_CUTOFF,
        apply=False,
        expect_count=None,
        stopped=False,
        backup=None,
    )
    with monkeypatch.context() as patcher:

        def refuse_init(self):
            pytest.fail("Offline compaction must not initialize or reconcile a live store")

        patcher.setattr(VectorMemoryStore, "init", refuse_init)
        cli_commands._memory_cmd(args)
        assert json.loads(capsys.readouterr().out) == {
            "store": env.name,
            "before": _CUTOFF,
            "eligible": len(env.removed),
            "removed": 0,
        }
        assert _read(env.path) == baseline
        assert not (env.root / "compaction-copy.db").exists()
        args.apply = True
        args.expect_count = len(env.removed)
        args.stopped = True
        args.backup = env.root / "compaction-copy.db"
        cli_commands._memory_cmd(args)
        result = json.loads(capsys.readouterr().out)
        assert result["removed"] == result["eligible"] == len(env.removed)
        assert _read(Path(result["backup"])) == baseline
    expected = dict(baseline)
    expected["memory_revisions"] = tuple(
        row for row in baseline["memory_revisions"] if row[0] not in env.removed
    )
    assert _read(env.path) == expected
    assert all(path.read_bytes() == contents for path, contents in env.identity.items())
    retained_ids = {row[0] for row in expected["memory_revisions"]}
    assert retained_ids.issuperset(env.proposals)
    env.tier.init()
    assert _rows(env.tier.db) == expected
    current = metadata.get_record_metadata(env.tier.db, "key:user.work_email")
    assert current["revision"] == 6
    assert (
        json.loads(env.tier.get_semantic("user.work_email")["value_json"]) == "address6@example.net"
    )
    assert env.tier.set_semantic("user.work_email", "next@example.net", 1, "user_explicit") is None
    assert metadata.get_record_metadata(env.tier.db, "key:user.work_email")["revision"] == 7
    newest = env.tier.db.execute("SELECT MAX(id) FROM memory_revisions").fetchone()[0]
    assert newest > max(row[0] for row in baseline["memory_revisions"])


@pytest.mark.parametrize(
    "defect",
    ["count", "acknowledgement", "existing-backup", "schema", "counter", "pending-restore"],
)
def test_unsafe_apply_refuses_without_deleting_snapshots(populated, defect):
    env = populated
    overrides = {}
    if defect == "count":
        overrides["expected_count"] = len(env.removed) + 1
    elif defect == "acknowledgement":
        overrides["stopped"] = False
    elif defect == "existing-backup":
        (env.root / "compaction-copy.db").write_bytes(b"Existing owner backup")
    elif defect in ("schema", "counter"):
        with closing(sqlite3.connect(env.path)) as db:
            if defect == "schema":
                db.execute("INSERT INTO schema_version VALUES (9999, 'unknown')")
            else:
                db.execute(
                    "UPDATE memory_record_meta SET revision=revision+1 WHERE record_id='key:user.work_email'"
                )
            db.commit()
    else:
        out = memory_backup.backup_dir_for(env.path)
        out.mkdir(parents=True, exist_ok=True)
        filename = "pending-restore.json" if env.private else "pending-v1-restore.json"
        (out / filename).write_text("{", encoding="utf-8")
    baseline = _read(env.path)
    with pytest.raises(
        (ValueError, FileExistsError), match="count|stopped|exists|schema|revision|restore"
    ):
        _apply(env, **overrides)
    assert _read(env.path) == baseline
    if defect == "existing-backup":
        assert (env.root / "compaction-copy.db").read_bytes() == b"Existing owner backup"


def test_concurrent_sqlite_writer_prevents_compaction(populated):
    env = populated
    baseline = _read(env.path)
    with closing(sqlite3.connect(env.path, timeout=0)) as writer:
        writer.execute("BEGIN IMMEDIATE")
        try:
            with pytest.raises((sqlite3.OperationalError, ValueError), match="locked|busy"):
                _apply(env)
        finally:
            writer.rollback()
    assert _read(env.path) == baseline


def test_changed_backup_snapshot_rolls_back_before_delete(populated, monkeypatch):
    env = populated
    baseline = _read(env.path)
    real_backup = compaction._backup

    def changed_copy(db, path):
        real_backup(db, path)
        with closing(sqlite3.connect(path)) as saved:
            saved.execute("UPDATE memory_record_meta SET category='changed copy'")
            saved.commit()

    monkeypatch.setattr(compaction, "_backup", changed_copy)
    with pytest.raises(ValueError, match="changed during backup"):
        _apply(env)
    assert _read(env.path) == baseline


def test_backup_permission_failure_precedes_content_and_deletion(populated, monkeypatch):
    env = populated
    baseline = _read(env.path)
    backup = env.root / "compaction-copy.db"
    real_restrict = platform_compat.restrict_to_owner
    seen = []

    def refuse_backup(candidate):
        if Path(candidate) == backup:
            seen.append(backup.read_bytes())
            raise OSError("Backup permissions could not be restricted")
        real_restrict(candidate)

    monkeypatch.setattr(platform_compat, "restrict_to_owner", refuse_backup)
    with pytest.raises(OSError, match="permissions"):
        _apply(env)
    assert seen == [b""]
    assert _read(env.path) == baseline
    assert backup.read_bytes() == b""
    assert all(path.read_bytes() == contents for path, contents in env.identity.items())
    backup.unlink()
    assert not backup.exists()


def test_verification_failure_rolls_back_trigger_side_effects(populated):
    env = populated
    with closing(sqlite3.connect(env.path)) as db:
        db.execute(
            "CREATE TRIGGER alter_counter AFTER DELETE ON memory_revisions BEGIN UPDATE memory_record_meta SET revision=revision+1; END"
        )
        db.commit()
    baseline = _read(env.path)
    with pytest.raises(ValueError, match="verification failed"):
        _apply(env)
    assert _read(env.path) == baseline
    assert _read(env.root / "compaction-copy.db") == baseline


@pytest.mark.parametrize("populated", ["v2"], indirect=True)
def test_private_owner_drift_and_live_store_handle_refuse(populated):
    env = populated
    baseline = _read(env.path)
    if platform_compat.IS_POSIX:
        env.tier.init()
        try:
            with pytest.raises(ValueError, match="still open"):
                _apply(env)
        finally:
            env.tier.close()
    with closing(sqlite3.connect(env.path)) as db:
        db.execute("UPDATE memory_meta SET value='bob' WHERE key='owner_member'")
        db.commit()
    damaged = _read(env.path)
    with pytest.raises(ValueError, match="identity"):
        _apply(env)
    assert _read(env.path) == damaged
    assert damaged["memory_revisions"] == baseline["memory_revisions"]


@pytest.mark.parametrize("cutoff", ["not-a-date", "2030-01-01", "2030-01-01T00:00:00+01:00"])
def test_cutoff_requires_explicit_utc(populated, cutoff):
    baseline = _read(populated.path)
    with pytest.raises(ValueError, match="UTC"):
        compaction.compact_revisions(populated.name, cutoff)
    assert _read(populated.path) == baseline


def test_missing_store_does_not_create_database(populated):
    path = populated.root / "memory_stores" / "misspelled"
    with pytest.raises(memory_stores.UnknownMemoryStore):
        compaction.compact_revisions("misspelled", _CUTOFF)
    assert not path.exists()


def test_missing_database_is_not_recreated(populated):
    env = populated
    env.path.unlink()
    with pytest.raises(FileNotFoundError):
        compaction.compact_revisions(env.name, _CUTOFF)
    assert not env.path.exists()
