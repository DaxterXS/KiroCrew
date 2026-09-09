"""Two authority-boundary properties of the builder.

``_tree_hash`` takes the content pin over the bytes that SHIP, so it must read each file
through the same authority the copy reads it through -- ``hooks.safe_read_file_bytes_nolink``,
which refuses a hard link (``st_nlink > 1``) the name checks cannot see. A ``read_bytes`` here
would pin the bytes of a hard-linked credential swapped in after the scan cleared the file.

The promotion renames staging onto ``out_dir`` relative to the parent pinned by descriptor,
not ``staging.rename(out_dir)``. A bare rename re-resolves both path strings, so a parent
component swapped for a link after ``--out`` was validated would land the promotion wherever
the link points; the descriptor-relative rename refuses a component swapped since.
"""

from __future__ import annotations

import os
import pathlib
import shutil

import pytest

from .test_producer import load_build, make_crew

_posix_only = pytest.mark.skipif(
    os.name != "posix",
    reason="the crew bundle builder is POSIX-only; guarded off on platforms without an "
    "atomic no-follow primitive (Windows). See the POSIX-only entry guard.",
)


# ---------------------------------------------------------------------------
# _tree_hash reads through the shared file-read guard, so a hard-linked file is
# refused at hashing rather than pinned through its second name.
# ---------------------------------------------------------------------------
@_posix_only
def test_tree_hash_refuses_a_hard_linked_file_and_names_it(tmp_path: pathlib.Path) -> None:
    """A skill member hard-linked to a file outside the skill is refused at hashing.

    The outside file's content is benign, so the refusal is the hard-link identity
    (``st_nlink > 1``) on the opened descriptor, not the credential scan. The refusal names
    the file so the pin cannot silently certify content the copy then refuses.
    """
    mod = load_build()
    src = make_crew(tmp_path / "home", skills={"leaky": {"SKILL.md": "# ok\n"}})
    skill_dir = src / "skills" / "leaky"
    outside = tmp_path / "outside_secret"
    outside.write_text("shared bytes that live outside the skill\n", encoding="utf-8")
    os.link(outside, skill_dir / "notes.md")
    assert (skill_dir / "notes.md").stat().st_nlink > 1, "test setup: member must be a hard link"

    with pytest.raises(mod.ExportRefused) as caught:
        mod._tree_hash(skill_dir)
    assert "notes.md" in str(caught.value), "the refusal must name the offending file"


@_posix_only
def test_tree_hash_hashes_an_ordinary_tree(tmp_path: pathlib.Path) -> None:
    """Non-vacuity: a tree of ordinary single-name regular files still hashes.

    The guard must not have become a blanket refusal -- a plain skill is read and pinned, so
    the hard-link refusal above is the hard link and not the read.
    """
    mod = load_build()
    src = make_crew(
        tmp_path / "home",
        skills={"faq": {"SKILL.md": "# faq\nhours 9 to 5\n", "extra.md": "no secrets\n"}},
    )
    digest = mod._tree_hash(src / "skills" / "faq")
    assert isinstance(digest, str) and len(digest) == 64, "an all-regular-file tree must hash"


@_posix_only
def test_MUTATION_a_by_name_read_pins_a_hard_linked_file_through(tmp_path: pathlib.Path) -> None:
    """Revert the guarded read to ``read_bytes`` and the hard-linked file is pinned, not refused.

    Reddens the fix: ``read_bytes`` never fstats for ``st_nlink``, so a hard link passes and
    the pin is taken over its bytes instead of refusing. The mutation anchor is the guarded
    read, unique to ``_tree_hash`` by its ``str(root)`` argument.
    """
    mod = load_build(
        mutate=(
            "safe_read_file_bytes_nolink(str(p), str(root), max_bytes=_MAX_PROMPT_BYTES)",
            "p.read_bytes()",
        )
    )
    src = make_crew(tmp_path / "home", skills={"leaky": {"SKILL.md": "# ok\n"}})
    skill_dir = src / "skills" / "leaky"
    outside = tmp_path / "outside_secret"
    outside.write_text("shared bytes that live outside the skill\n", encoding="utf-8")
    os.link(outside, skill_dir / "notes.md")

    digest = mod._tree_hash(skill_dir)
    assert isinstance(digest, str) and len(digest) == 64, (
        "mutated: a by-name read with no st_nlink check pins the hard-linked file instead of "
        "refusing it, proving the guard's fstat is what refuses it"
    )


# ---------------------------------------------------------------------------
# The promotion renames staging onto out_dir relative to a pinned parent
# descriptor, and refuses a parent swapped for a link after validation.
# ---------------------------------------------------------------------------
def _build_at(mod, home: pathlib.Path, out: pathlib.Path):
    crew = mod.resolve_crew("frontdesk", home)
    spec = mod.read_agent_spec(crew)
    cands = mod.enumerate_all(crew, spec)
    return mod.build_bundle(crew, spec, cands, None, out)


@_posix_only
def test_promotion_renames_staging_relative_to_a_pinned_parent_fd(
    tmp_path: pathlib.Path, monkeypatch
) -> None:
    """A clean build promotes via ``os.rename`` of the bare leaf names under a pinned fd.

    Non-vacuity for the pinned parent: the promotion of ``<name>.staging`` -> ``<name>``
    passes bare leaf names and ``src_dir_fd`` / ``dst_dir_fd``, which is only possible when
    the parent is opened as a descriptor first. A bare ``staging.rename(out_dir)`` would
    re-resolve full path strings instead and carries no descriptor.
    """
    mod = load_build()
    home = make_crew(tmp_path / "home")
    out = tmp_path / "work" / "bundle"

    calls: list[tuple] = []
    real_rename = os.rename

    def spy(src, dst, *, src_dir_fd=None, dst_dir_fd=None):
        calls.append((str(src), str(dst), src_dir_fd, dst_dir_fd))
        return real_rename(src, dst, src_dir_fd=src_dir_fd, dst_dir_fd=dst_dir_fd)

    monkeypatch.setattr(os, "rename", spy)
    _build_at(mod, home, out)
    assert (out / "agent.json").is_file(), "the clean build must land the bundle"

    promote = [
        c
        for c in calls
        if c[0] == "bundle.staging" and c[1] == "bundle" and c[2] is not None and c[3] is not None
    ]
    assert promote, "the promotion did not rename staging->out_dir relative to a pinned parent fd"


@_posix_only
def test_MUTATION_a_bare_rename_promotion_is_not_descriptor_relative(
    tmp_path: pathlib.Path, monkeypatch
) -> None:
    """Revert to ``staging.rename(out_dir)`` and no descriptor-relative promotion happens.

    ``Path.rename`` re-resolves the full path strings, so the bare-leaf, ``dir_fd``-anchored
    promotion the fix records never appears -- proving the pinned ``os.rename`` is what makes
    the promotion descriptor-relative.
    """
    mod = load_build(
        mutate=(
            "            os.rename(\n"
            "                staging.name,\n"
            "                out_dir.name,\n"
            "                src_dir_fd=promote_parent_fd,\n"
            "                dst_dir_fd=promote_parent_fd,\n"
            "            )",
            "            staging.rename(out_dir)",
        )
    )
    home = make_crew(tmp_path / "home")
    out = tmp_path / "work" / "bundle"

    calls: list[tuple] = []
    real_rename = os.rename

    def spy(src, dst, *, src_dir_fd=None, dst_dir_fd=None):
        calls.append((str(src), str(dst), src_dir_fd, dst_dir_fd))
        return real_rename(src, dst, src_dir_fd=src_dir_fd, dst_dir_fd=dst_dir_fd)

    monkeypatch.setattr(os, "rename", spy)
    _build_at(mod, home, out)
    assert (out / "agent.json").is_file(), "the mutated build still promotes (via Path.rename)"

    promote = [
        c
        for c in calls
        if c[0] == "bundle.staging" and c[1] == "bundle" and c[2] is not None and c[3] is not None
    ]
    assert not promote, (
        "mutated: a bare Path.rename promotion produced a descriptor-relative rename, which it "
        "cannot -- the pinned os.rename is what the fix adds"
    )


@_posix_only
def test_promotion_refuses_a_parent_swapped_after_validation(
    tmp_path: pathlib.Path, monkeypatch
) -> None:
    """A parent swapped for a link between validation and the rename is refused, not followed.

    The shared parent is swapped for a symlink to an attacker directory right before the
    promotion (at the report-path shape check, the last step before the rename). The parent
    was resolved once at validation, and the descriptor-relative promotion walks that value
    ``O_NOFOLLOW``, so the swapped component fails its own open and the build refuses. Nothing
    is promoted into the attacker directory.
    """
    mod = load_build()
    home = make_crew(tmp_path / "home")
    parent = tmp_path / "work"
    parent.mkdir()
    out = parent / "bundle"

    victim = tmp_path / "victim"
    victim.mkdir()
    # A decoy staging tree in the victim, so that if the promotion followed the swapped parent
    # (the bug) a bare rename would find a source and land ``victim/bundle``.
    (victim / "bundle.staging").mkdir()

    real_ire = mod._is_redirecting_entry
    state = {"swapped": False}

    def swap_before_promote(p):
        if str(p).endswith(".smc-bundle.json") and not state["swapped"]:
            state["swapped"] = True
            os.rename(parent, tmp_path / "real-work")
            parent.symlink_to(victim, target_is_directory=True)
        return real_ire(p)

    monkeypatch.setattr(mod, "_is_redirecting_entry", swap_before_promote)

    with pytest.raises(mod.ExportRefused):
        _build_at(mod, home, out)
    assert state["swapped"], "the swap never happened, so this proves nothing"
    assert not (victim / "bundle").exists(), "the promotion followed the swapped parent"


@_posix_only
def test_a_clean_parent_still_promotes(tmp_path: pathlib.Path) -> None:
    """Non-vacuity: an untouched parent promotes the bundle, so the refusal above is the swap."""
    mod = load_build()
    home = make_crew(tmp_path / "home")
    out = tmp_path / "work" / "bundle"
    report = _build_at(mod, home, out)
    assert (out / "agent.json").is_file()
    assert (out / "manifest.json").is_file()
    assert report.bundle_dir == out


# ---------------------------------------------------------------------------
# The disposal path pins its parent by descriptor, so a parent swapped BETWEEN
# two disposal mutation points is refused by the pin, not followed onto an
# external tree by a re-resolved recursive delete.
# ---------------------------------------------------------------------------
@_posix_only
def test_a_parent_swapped_between_two_disposal_points_refuses_by_the_pin(
    tmp_path: pathlib.Path, monkeypatch
) -> None:
    """Swap the shared parent between the leftover purge and the out_dir dispose; the pin refuses.

    A rebuild runs two disposal mutations in a row: it purges a leftover ``<out>.previous`` and
    then moves ``out_dir`` aside. The swap fires inside the FIRST one's ownership check, so its
    own held descriptor finishes safely; the SECOND opens a fresh pinned descriptor on the
    parent resolved at validation, and the swapped component fails its own ``O_NOFOLLOW`` open.
    The refusal is asserted BY THE DISPOSAL PIN'S OWN WORDING ("cannot dispose of"), not merely
    that something refused -- a downstream guard masking a late pin would use different words.
    Nothing is deleted inside the attacker directory.
    """
    mod = load_build()
    home = make_crew(tmp_path / "home")
    parent = tmp_path / "work"
    parent.mkdir()
    out = parent / "bundle"

    # A valid bundle at --out, and a build-owned leftover aside so the leftover purge runs.
    _build_at(mod, home, out)
    previous = parent / "bundle.previous"
    shutil.copytree(out, previous)

    victim = tmp_path / "victim"
    victim.mkdir()
    (victim / "sentinel.txt").write_text("operator data outside --out\n", encoding="utf-8")

    real_check = mod._refuse_unless_this_build_wrote_it
    state = {"swapped": False}

    def swapping_check(path, label, crew_name):
        real_check(path, label, crew_name)
        # After the leftover aside clears its ownership check, swap the shared parent for a
        # link to the attacker directory -- i.e. between the two disposal mutation points.
        if label == "the aside path" and not state["swapped"]:
            state["swapped"] = True
            os.rename(parent, tmp_path / "real-work")
            parent.symlink_to(victim, target_is_directory=True)

    monkeypatch.setattr(mod, "_refuse_unless_this_build_wrote_it", swapping_check)

    with pytest.raises(mod.ExportRefused) as caught:
        _build_at(mod, home, out)
    assert state["swapped"], "the swap never happened, so this proves nothing"
    assert "cannot dispose of" in str(caught.value), (
        "the refusal must come from the disposal pin's own message, not a downstream guard "
        f"that masks a pin landing too late: {caught.value}"
    )
    assert (victim / "sentinel.txt").read_text(encoding="utf-8") == (
        "operator data outside --out\n"
    ), "the disposal followed the swapped parent into the attacker directory"


@_posix_only
def test_MUTATION_bypassing_the_disposal_pin_lands_the_delete_on_a_swapped_parent(
    tmp_path: pathlib.Path, monkeypatch
) -> None:
    """Bypass the O_NOFOLLOW pin and a parent swap lands the recursive delete on the wrong tree.

    The pin is replaced by a plain open-by-name that follows symlinks (the pre-fix shape). With
    the parent swapped for a link to a victim directory after the resolve, the private-aside
    mkdir/rename/sweep all run inside the victim, and the recursive delete removes the victim's
    tree -- proving the descriptor pin is load-bearing. The ownership verifier is a no-op here
    so the pin is the only guard under test.
    """
    mod = load_build()
    parent = tmp_path / "work"
    parent.mkdir()
    target = parent / "bundle.previous"
    target.mkdir()
    (target / "keep.txt").write_text("real\n", encoding="utf-8")
    resolved_parent = parent.resolve()  # captured BEFORE the swap, as validation would

    victim = tmp_path / "victim"
    victim.mkdir()
    decoy = victim / "bundle.previous"
    decoy.mkdir()
    (decoy / "sentinel.txt").write_text("victim data\n", encoding="utf-8")

    def _unpinned_open(dir_path, *, already_resolved=False):
        # The pre-fix shape: open by NAME, following any link at a parent component.
        return os.open(str(dir_path), os.O_RDONLY | os.O_DIRECTORY)

    monkeypatch.setattr(mod, "_open_dir_nofollow_pinned", _unpinned_open)

    os.rename(parent, tmp_path / "real-work")
    parent.symlink_to(victim, target_is_directory=True)

    mod._purge_via_private_aside(target, lambda moved: None, resolved_parent=resolved_parent)

    assert not (decoy / "sentinel.txt").exists(), (
        "with the pin bypassed the open followed the swapped parent to the victim and the "
        "recursive delete removed its tree -- proving the O_NOFOLLOW pin is what keeps the "
        "delete inside --out"
    )


# ---------------------------------------------------------------------------
# The transaction's recursive deletes are a CLOSED set, each bound to a pinned
# descriptor. Enumeration, not discovery: a name-based recursive delete of a
# tree derived from --out (staging / previous / the private aside) re-resolves
# its target and can be steered outside --out by a swap. Every such delete goes
# through _dispose_via_private_aside / _purge_via_private_aside / _rmtree_pinned,
# which reach the target relative to a held O_NOFOLLOW parent descriptor. This
# test fails if a NEW bare shutil.rmtree of an --out-derived tree is added.
# ---------------------------------------------------------------------------
def test_every_out_derived_recursive_delete_goes_through_the_pin() -> None:
    """No bare ``shutil.rmtree`` of staging / previous / the aside survives in ``build.py``.

    The pinned disposal helpers ARE allowed to call ``shutil`` internally is not the point:
    the rule is that a recursive delete of an --out-derived tree is reached through a held
    descriptor. Two bare forms are permitted and named explicitly: ``ignore_errors=True``
    cleanup of a staging tree THIS build itself created moments earlier in the same frame
    (there is no pre-existing tree to swap for, and the delete is best-effort teardown of the
    build's own scratch), and the delete inside ``_rmtree_pinned`` itself, which is the
    descriptor-relative primitive. Any OTHER bare ``shutil.rmtree`` is a re-derived target and
    fails here, so the closed set cannot silently grow.
    """
    import ast

    build_py = pathlib.Path(__file__).resolve().parents[1] / "build.py"
    tree = ast.parse(build_py.read_text(encoding="utf-8"), str(build_py))

    def _in_rmtree_pinned(node: ast.AST) -> bool:
        for fn in ast.walk(tree):
            if (
                isinstance(fn, ast.FunctionDef)
                and fn.name == "_rmtree_pinned"
                and any(n is node for n in ast.walk(fn))
            ):
                return True
        return False

    offenders: list[int] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr != "rmtree":
            continue
        if _in_rmtree_pinned(node):
            continue  # the descriptor-relative primitive itself
        ignore_errors = any(
            kw.arg == "ignore_errors"
            and isinstance(kw.value, ast.Constant)
            and kw.value.value is True
            for kw in node.keywords
        )
        if ignore_errors:
            continue  # best-effort teardown of THIS build's own freshly-created staging
        offenders.append(node.lineno)

    assert not offenders, (
        "these bare shutil.rmtree calls delete an --out-derived tree by a re-resolved name, "
        f"which a swap can steer outside --out (lines {offenders}); route each through the "
        "pinned aside (_purge_via_private_aside / _dispose_via_private_aside) so the target is "
        "reached relative to a held O_NOFOLLOW descriptor"
    )


def test_the_pin_rule_is_scanning_the_real_disposal_helpers() -> None:
    """Non-vacuity: the pinned helpers exist and the primitive is named as expected.

    A rule that scanned an empty set, or that named a helper absent from the module, would pass
    while the swap window it guards reopened. Assert the three names the rule relies on are
    real functions in the module.
    """
    import ast

    build_py = pathlib.Path(__file__).resolve().parents[1] / "build.py"
    tree = ast.parse(build_py.read_text(encoding="utf-8"), str(build_py))
    defined = {fn.name for fn in ast.walk(tree) if isinstance(fn, ast.FunctionDef)}
    for name in ("_rmtree_pinned", "_dispose_via_private_aside", "_purge_via_private_aside"):
        assert name in defined, f"{name} is the pin the closed-set rule relies on; it is gone"


@_posix_only
def test_a_preexisting_staging_swapped_before_cleanup_is_not_deleted(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The staging cleanup is the third mutation point; a swap between check and delete refuses.

    A pre-existing staging tree clears the ownership check BY NAME, then the cleanup deletes it.
    With the pin bypassed, a parent swapped for a link between the two steps steers the delete
    onto an external tree. The pinned aside opens the parent ``O_NOFOLLOW`` and reaches staging
    relative to that held descriptor, so the swapped parent fails its own no-follow open and the
    external tree is NOT deleted.
    """
    mod = load_build()
    parent = tmp_path / "work"
    parent.mkdir()
    staging = parent / "b.staging"
    staging.mkdir()
    resolved_parent = parent.resolve()

    victim = tmp_path / "victim"
    victim.mkdir()
    decoy = victim / "b.staging"
    decoy.mkdir()
    (decoy / "sentinel.txt").write_text("victim data\n", encoding="utf-8")

    def _unpinned_open(dir_path, *, already_resolved=False):
        return os.open(str(dir_path), os.O_RDONLY | os.O_DIRECTORY)

    monkeypatch.setattr(mod, "_open_dir_nofollow_pinned", _unpinned_open)
    os.rename(parent, tmp_path / "real-work")
    parent.symlink_to(victim, target_is_directory=True)

    mod._purge_via_private_aside(staging, lambda moved: None, resolved_parent=resolved_parent)

    assert not (decoy / "sentinel.txt").exists(), (
        "with the pin bypassed the staging cleanup opened the swapped parent (the victim) by "
        "name, moved the victim's own b.staging into the aside and swept it -- the delete "
        "landed OUTSIDE --out. This is the same defect as the previous-bundle and aside "
        "disposals, proving the staging delete must reach its target through the held "
        "O_NOFOLLOW parent descriptor, which refuses the swapped parent"
    )
