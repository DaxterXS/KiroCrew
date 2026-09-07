"""Offline, owner-directed removal of obsolete accepted memory snapshots."""

from __future__ import annotations

import hashlib
import os
import stat
from contextlib import closing, nullcontext
from datetime import datetime, timedelta
from pathlib import Path

from kiro_crew import (
    member_memory_backup,
    memory_backup,
    memory_schema,
    memory_stores,
    platform_compat,
)
from kiro_crew._sqlite_compat import sqlite3
from kiro_crew.config.loader import KiroCrewConfig

_CANDIDATES = """
SELECT id FROM memory_revisions
WHERE status = 'accepted'
  AND julianday(created_at) < julianday(:cutoff_utc)
  AND id NOT IN (
      SELECT MAX(id) FROM memory_revisions
      WHERE status = 'accepted' GROUP BY record_id
  )
"""
_MISMATCH = """
SELECT m.record_id FROM memory_record_meta AS m
LEFT JOIN memory_revisions AS r ON r.id = (
    SELECT MAX(a.id) FROM memory_revisions AS a
    WHERE a.record_id = m.record_id AND a.status = 'accepted'
)
WHERE r.id IS NULL OR r.revision <> m.revision
LIMIT 1
"""
_REVISION_COLUMNS = (
    "id",
    "record_id",
    "revision",
    "base_revision",
    "status",
    "operation",
    "source",
    "before_json",
    "after_json",
    "metadata_json",
    "created_at",
)


def _regular_database(path: Path) -> None:
    for suffix in ("", "-wal", "-shm"):
        candidate = path.with_name(path.name + suffix)
        try:
            info = candidate.lstat()
        except FileNotFoundError:
            if suffix:
                continue
            raise
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or candidate.resolve() != candidate:
            raise ValueError(
                "Memory database or SQLite sidecar is redirected or not a regular file"
            )


def _target(store: str, *, check_database: bool = True) -> tuple[Path, str]:
    cfg = KiroCrewConfig.load()
    if cfg.degraded_sections & {"*", "agents", "memory_stores"}:
        raise ValueError("Repair the unreadable memory configuration before compaction")
    memory_stores.require_memory_store(store, config=cfg, require_directory=False)
    path = memory_stores.resolve_store_path(store)
    # Resolve the administrative root, preserving supported symlinked home ancestors.
    path = path.parent.resolve() / path.name
    _regular_database(path)
    if check_database:
        memory_stores.require_memory_store(store, config=cfg)
    status = memory_backup.pending_restore_status(path)
    if status.get("pending") or status.get("restore_error") or status.get("activation_failed"):
        raise ValueError("Resolve the pending or failed memory restore before compaction")
    owner = ""
    if store != memory_stores.DEFAULT_MEMORY_STORE:
        owner = cfg.memory_stores[store].owner_member
        if owner:
            if memory_stores.member_memory_identity(store) != (owner, 2):
                raise ValueError("Private manifest does not match its configured owner")
        else:
            marker = path.parent / memory_stores.MEMBER_MEMORY_MANIFEST
            try:
                marker.lstat()
            except FileNotFoundError:
                pass
            else:
                raise ValueError("Legacy memory retains a private ownership manifest")
    return path, owner


def _validate_database(db: sqlite3.Connection, store: str, owner: str) -> None:
    if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
        raise ValueError("Memory database failed integrity checking")
    lineage = memory_schema.detect_lineage(db)
    versions = {row[0] for row in db.execute("SELECT version FROM schema_version")}
    expected = (
        {memory_schema.CREW_SCHEMA_VERSION} if lineage == memory_schema.LINEAGE_CREW else {1, 2, 3}
    )
    if (
        lineage not in (memory_schema.LINEAGE_V1, memory_schema.LINEAGE_CREW)
        or versions != expected
    ):
        raise ValueError("Compaction requires a supported, fully initialized memory schema")
    if owner:
        identity = dict(db.execute("SELECT key, value FROM memory_meta"))
        if (
            lineage != memory_schema.LINEAGE_CREW
            or identity.get(memory_schema.STORE_NAME_META_KEY) != store
            or identity.get(memory_schema.PRIVATE_MEMORY_VERSION_META_KEY) != "2"
            or identity.get(memory_schema.OWNER_MEMBER_META_KEY) != owner
        ):
            raise ValueError("Private database identity does not match its owner and store")
    else:
        memory_backup._require_v1_restore_database(db, store)
    columns = tuple(row[1] for row in db.execute("PRAGMA table_info(memory_revisions)"))
    if columns != _REVISION_COLUMNS or db.execute(
        "SELECT type FROM sqlite_schema WHERE name='memory_record_meta'"
    ).fetchone() != ("table",):
        raise ValueError("Compaction requires the supported memory revision tables")
    if db.execute(_MISMATCH).fetchone() is not None:
        raise ValueError("Current memory revision does not match its latest accepted snapshot")


def _snapshot(db: sqlite3.Connection, cutoff: str | None = None) -> dict[str, str]:
    """Stream logical rows, including views and counters, without retaining database contents."""
    schema = list(db.execute("SELECT type, name, tbl_name, sql FROM sqlite_schema ORDER BY name"))
    result = {"schema": hashlib.sha256(repr(schema).encode("utf-8")).hexdigest()}
    for kind, name, _, _ in schema:
        if kind not in ("table", "view"):
            continue
        quoted = '"' + name.replace('"', '""') + '"'
        description = db.execute(f"SELECT * FROM {quoted} LIMIT 0").description
        assert description is not None
        columns = len(description)
        where = ""
        parameters: dict[str, str] = {}
        if name == "memory_revisions" and cutoff is not None:
            where = f" WHERE id NOT IN ({_CANDIDATES})"
            parameters = {"cutoff_utc": cutoff}
        order = ",".join(str(index) for index in range(1, columns + 1))
        digest = hashlib.sha256()
        for row in db.execute(f"SELECT * FROM {quoted}{where} ORDER BY {order}", parameters):
            encoded = repr(tuple(row)).encode("utf-8")
            digest.update(str(len(encoded)).encode("ascii") + b":" + encoded)
        result[name] = digest.hexdigest()
    return result


def _backup(db: sqlite3.Connection, path: Path) -> None:
    # Claim an unused file and restrict it before copying any private content.
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        platform_compat.restrict_to_owner(path)
    finally:
        os.close(fd)
    with closing(sqlite3.connect(path.as_uri() + "?mode=rw", uri=True)) as destination:

        def refuse_busy(status: int, remaining: int, total: int) -> None:
            if status in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
                raise ValueError("Memory is still busy; stop all users before compaction")

        db.backup(destination, progress=refuse_busy, sleep=0)
        if destination.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("Compaction backup failed integrity checking")
    with path.open("r+b") as handle:
        os.fsync(handle.fileno())


def compact_revisions(
    store: str,
    before: str,
    *,
    apply: bool = False,
    expected_count: int | None = None,
    stopped: bool = False,
    backup: Path | None = None,
) -> dict:
    """Preview by default; apply only to a stopped store with a verified new backup.

    This owner CLI does not discover remote readers or stop services. The explicit
    acknowledgement covers those operational steps; SQLite locks and the private
    lifetime lock also refuse locally conflicting database users.
    """
    try:
        stamp = datetime.fromisoformat(before.replace("Z", "+00:00"))
    except (ValueError, AttributeError) as exc:
        raise ValueError("--before must be an explicit ISO timestamp in UTC") from exc
    if stamp.tzinfo is None or stamp.utcoffset() != timedelta(0):
        raise ValueError("--before must be an explicit ISO timestamp in UTC")
    cutoff = stamp.isoformat()
    if apply and (
        not stopped or type(expected_count) is not int or expected_count < 0 or backup is None
    ):
        raise ValueError("Apply requires --stopped, --expect-count N and --backup NEW_FILE")
    if not apply and (stopped or expected_count is not None or backup is not None):
        raise ValueError("Use --apply with --stopped, --expect-count and --backup")
    path, owner = _target(store)
    original_file = path.stat()
    admission = (
        member_memory_backup._restore_store_admission(path) if apply and owner else nullcontext()
    )
    with admission:
        mode = "rw" if apply else "ro"
        with closing(sqlite3.connect(path.as_uri() + f"?mode={mode}", uri=True, timeout=0)) as db:
            if apply:
                db.execute("PRAGMA locking_mode=EXCLUSIVE")
            else:
                db.execute("PRAGMA query_only=ON")
                db.execute("BEGIN")
            _validate_database(db, store, owner)
            parameters = {"cutoff_utc": cutoff}
            count = db.execute(f"SELECT COUNT(*) FROM ({_CANDIDATES})", parameters).fetchone()[0]
            result = {"store": store, "before": cutoff, "eligible": count, "removed": 0}
            if not apply:
                return result
            if count != expected_count:
                raise ValueError("Eligible revision count changed; preview again before applying")
            assert backup is not None
            backup_path = backup.absolute().parent.resolve() / backup.name
            if backup_path.resolve() != backup_path or backup_path == path:
                raise ValueError("Backup must be a new, unredirected file")
            _backup(db, backup_path)
            with closing(sqlite3.connect(backup_path.as_uri() + "?mode=ro", uri=True)) as saved:
                baseline = _snapshot(saved)
                retained = _snapshot(saved, cutoff)
            # Recheck external authority without another SQLite connection while
            # this connection owns exclusive locking mode. Database identity is
            # verified below on the connection already held.
            if _target(store, check_database=False) != (path, owner):
                raise ValueError("Memory identity changed during backup; preview again")
            # Backup must finish before a write transaction: backing up a connection
            # inside BEGIN EXCLUSIVE can wait indefinitely for that same transaction.
            db.execute("BEGIN EXCLUSIVE")
            try:
                _regular_database(path)
                current_file = path.stat()
                if (current_file.st_dev, current_file.st_ino) != (
                    original_file.st_dev,
                    original_file.st_ino,
                ) or _snapshot(db) != baseline:
                    raise ValueError("Memory changed during backup; preview again before applying")
                _validate_database(db, store, owner)
                removed = db.execute(
                    f"DELETE FROM memory_revisions WHERE id IN ({_CANDIDATES})", parameters
                ).rowcount
                if removed != count or _snapshot(db) != retained:
                    raise ValueError(
                        "Compaction verification failed; all deletions were rolled back"
                    )
                if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                    raise ValueError(
                        "Compaction integrity check failed; deletions were rolled back"
                    )
                db.commit()
            except BaseException:
                db.rollback()
                raise
            return {**result, "removed": removed, "backup": str(backup_path)}
