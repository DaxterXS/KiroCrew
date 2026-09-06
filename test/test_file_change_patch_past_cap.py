"""An edit past the per-file snapshot cap must still reach the UI.

The before/after snapshots are each cut from the START of the file, so an edit
beyond ``_MAX_SNAPSHOT`` leaves both sides byte-identical: a real change reads as
no change at all, and the budget was spent on a prefix that does not contain it.
The entry therefore carries a capped unified diff instead, which is small for a
small edit however large the file and whose hunk headers keep the true line
numbers.
"""

from __future__ import annotations

from kiro_crew.dashboard import chat_runner as cr


def _big(marker_line: str, *, lines: int = 400) -> str:
    """A body comfortably past the snapshot cap, with one distinctive line."""
    filler = "x" * 800
    body = [f"{filler}  # line {i}" for i in range(lines)]
    body[-1] = marker_line
    return "\n".join(body) + "\n"


def _big_both_sides(first_line: str, last_line: str, *, lines: int = 400) -> str:
    """A body past the cap, edited at BOTH ends.

    The first line falls inside the capped prefix and the last falls past it, so
    the capped pair DIFFERS while still omitting the later change. That pair looks
    faithful -- it shows a real hunk -- which is what makes the omission worse than
    an identical pair: nothing on screen suggests anything is missing.
    """
    filler = "x" * 800
    body = [f"{filler}  # line {i}" for i in range(lines)]
    body[0] = first_line
    body[-1] = last_line
    return "\n".join(body) + "\n"


class _Slot:
    """Minimal stand-in for the fields `_flush_file_changes` touches."""

    key = "slot-under-test"

    def __init__(self, changes):
        self._file_changes = changes
        self._dirty = False
        # One assistant message already present, so the flush attaches to it
        # rather than taking the synthetic-message path.
        self.messages = [{"role": "assistant", "content": "done", "meta": {}}]

    def append(self, *args, **kwargs):  # pragma: no cover - synthetic path
        raise AssertionError("an assistant message exists; nothing to synthesize")


def test_before_entry_carries_full_text_only_when_the_cap_bit(tmp_path):
    small = "one\ntwo\n"
    assert "before_full" not in cr._before_entry("/a.ts", small)

    big = _big("marker BEFORE")
    assert len(big) > cr._MAX_SNAPSHOT
    entry = cr._before_entry("/a.ts", big)
    # The capped prefix is what would be persisted; the full text rides along
    # transiently so a patch can be computed from it.
    assert entry["before_full"] == big
    assert len(entry["content"]) < len(big)


def test_edit_past_the_cap_is_carried_as_a_patch(tmp_path):
    before_full = _big("marker BEFORE")
    after_full = _big("marker AFTER")
    # Precondition: this is exactly the blind spot — the capped pair is equal.
    assert cr._truncate_snapshot(before_full) == cr._truncate_snapshot(after_full)

    p = tmp_path / "huge.tsx"
    p.write_text(after_full, encoding="utf-8")
    slot = _Slot([cr._before_entry(str(p), before_full)])
    cr._flush_file_changes(slot)

    changes = slot.messages[-1]["meta"]["file_changes"]
    assert len(changes) == 1
    row = changes[0]
    # The pair still reads as unchanged — that is the cap, not a bug to hide.
    assert row["before"] == row["after"]
    # ...and the patch is what tells the truth about the change.
    assert "marker AFTER" in row["patch"]
    assert "marker BEFORE" in row["patch"]
    assert row["patch"].startswith("---")
    # Transient key must never reach message meta.
    assert "before_full" not in row


def test_no_patch_when_the_capped_pair_can_express_the_change(tmp_path):
    p = tmp_path / "small.ts"
    p.write_text("one\ntwo\nthree\n", encoding="utf-8")
    slot = _Slot([cr._before_entry(str(p), "one\ntwo\n")])
    cr._flush_file_changes(slot)
    row = slot.messages[-1]["meta"]["file_changes"][0]
    assert "patch" not in row


def test_a_genuine_no_op_past_the_cap_gets_no_patch(tmp_path):
    """An idempotent write must stay a no-op, not acquire an empty patch."""
    body = _big("marker SAME")
    p = tmp_path / "huge.tsx"
    p.write_text(body, encoding="utf-8")
    slot = _Slot([cr._before_entry(str(p), body)])
    cr._flush_file_changes(slot)
    row = slot.messages[-1]["meta"]["file_changes"][0]
    assert "patch" not in row


def test_the_patch_is_credential_scrubbed(tmp_path):
    """The patch carries file content, so it obeys the same scrub as before/after
    — otherwise the oversized-file path is a way around that layer."""
    secret = "AKIAIOSFODNN7EXAMPLE"
    before_full = _big("marker BEFORE")
    after_full = _big(f"key = {secret}")
    p = tmp_path / "huge.tsx"
    p.write_text(after_full, encoding="utf-8")
    slot = _Slot([cr._before_entry(str(p), before_full)])
    cr._flush_file_changes(slot)
    row = slot.messages[-1]["meta"]["file_changes"][0]
    assert secret not in row["patch"]


def test_the_patch_is_capped(tmp_path):
    """A large change PAST the cap must not smuggle the file back in as a diff."""
    prefix = "\n".join("x" * 800 for _ in range(300)) + "\n"
    before_full = prefix + "\n".join(f"before line {i}" for i in range(20_000)) + "\n"
    after_full = prefix + "\n".join(f"after line {i}" for i in range(20_000)) + "\n"
    assert cr._truncate_snapshot(before_full) == cr._truncate_snapshot(after_full)
    p = tmp_path / "huge.tsx"
    p.write_text(after_full, encoding="utf-8")
    slot = _Slot([cr._before_entry(str(p), before_full)])
    cr._flush_file_changes(slot)
    row = slot.messages[-1]["meta"]["file_changes"][0]
    # The cap lives in chat_utils, which owns the ONE patch implementation: the
    # read path shrinks oversized pairs through it too, so a second copy in the
    # writer would let the two halves cap differently.
    from kiro_crew.dashboard import chat_utils as cu

    assert len(row["patch"]) <= cu._MAX_PATCH + 100
    assert "patch truncated" in row["patch"]


def test_a_change_on_both_sides_of_the_cap_is_still_carried(tmp_path):
    """The capped pair DIFFERING does not mean it is faithful.

    The original gate asked "are the capped prefixes identical", which is only the
    easy half of the problem. A file edited both inside and past the cap has
    differing prefixes, so that gate computed no patch -- and the wire then carried
    a pair showing the early hunk while silently dropping the later one. That is
    worse than an identical pair, because a reader sees a plausible diff and has no
    cue that anything is missing.

    The question that matters is whether the capped pair can represent EVERY
    change, which is false whenever either body was truncated at all.
    """
    before_full = _big_both_sides("head BEFORE", "tail BEFORE")
    after_full = _big_both_sides("head AFTER", "tail AFTER")
    # Precondition: the capped prefixes DIFFER (so the old gate stayed shut) while
    # still omitting the change at the tail.
    b_cap = cr._truncate_snapshot(before_full)
    a_cap = cr._truncate_snapshot(after_full)
    assert b_cap != a_cap, "prefix must differ, or this is the already-covered case"
    assert "tail AFTER" not in a_cap, "the tail edit must fall past the cap"

    p = tmp_path / "huge.tsx"
    p.write_text(after_full, encoding="utf-8")
    slot = _Slot([cr._before_entry(str(p), before_full)])
    cr._flush_file_changes(slot)
    row = slot.messages[-1]["meta"]["file_changes"][0]
    assert "patch" in row, "a truncated pair must carry a patch even when it differs"
    # Both ends of the change survive: the one the pair could show and the one it
    # could not.
    assert "head AFTER" in row["patch"]
    assert "tail AFTER" in row["patch"]


def test_the_snapshot_read_goes_through_the_symlink_safe_chokepoint(tmp_path, monkeypatch):
    """`validate_file_path` then `read_text` is a TOCTOU, and the sibling closes it.

    Between validating a path and reading it, an agent can swap the file for a
    symlink pointing outside the validated tree; a plain `read_text` follows it and
    the target's bytes land in message metadata. `hooks.safe_read_file` re-checks
    the RESOLVED target and opens with `O_NOFOLLOW`, which is why
    `_reconstruct_str_replace_before` already uses it.

    Asserted by routing rather than by winning a race: the chokepoint is replaced,
    and the reader must be the thing that notices. A reverting mutation back to
    `read_text` bypasses the replacement and the file is read anyway.
    """
    p = tmp_path / "a.ts"
    p.write_text("hello\n", encoding="utf-8")
    assert cr._safe_read_snapshot_raw(str(p)) == "hello\n"

    calls: list[str] = []

    def _refuse(path: str) -> str:
        calls.append(path)
        raise PermissionError("symlink target outside the validated path")

    monkeypatch.setattr(cr, "safe_read_file", _refuse)
    assert cr._safe_read_snapshot_raw(str(p)) is None
    assert calls == [str(p)], "the read must go through safe_read_file, not read_text"


def test_an_oversized_body_is_not_read_or_diffed(tmp_path):
    """This reader is the one snapshot path NOT capped by `_MAX_SNAPSHOT`.

    It exists to feed a full-body diff, so an agent can hand it a file of any size
    and both the read and difflib's pass over the result run on the turn coroutine.
    Bounded at the same ceiling the sibling reader uses, and re-checked after the
    read because `stat()` races a writer still growing the file.

    MUTATION NOTE: the two bounds MASK each other here. Removing the `stat()` gate
    alone leaves the post-read check to catch it, and removing the post-read check
    alone leaves the gate -- so neither mutation reddens this test on its own, and
    only removing BOTH does. That is the defence-in-depth the sibling reader also
    carries, and it is recorded rather than papered over: the case that separates
    them is a file that stats small and reads large (the sibling's comment names
    /dev/zero and FIFOs), which cannot be exercised here because reading a FIFO
    would block the test.
    """
    p = tmp_path / "huge.bin"
    p.write_text("y" * (cr._MAX_RECONSTRUCT_BYTES + 1_000), encoding="utf-8")
    assert cr._safe_read_snapshot_raw(str(p)) is None

    ok = tmp_path / "fine.ts"
    ok.write_text("z" * 1_000, encoding="utf-8")
    assert cr._safe_read_snapshot_raw(str(ok)) is not None
