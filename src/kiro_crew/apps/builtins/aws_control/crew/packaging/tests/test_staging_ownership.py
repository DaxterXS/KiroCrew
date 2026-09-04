"""The third and last recursive-delete site: ``<out>.staging``.

Three paths in ``build_bundle`` delete a directory recursively, and each was reported
separately over three review rounds because each carried a different subset of the same
rule. ``--out`` and ``<out>.previous`` now share one function; staging cannot use it,
because staging is filled in incrementally and its manifest is written near the end, so a
directory this build abandoned legitimately has no digest to verify.

What staging has instead is that this build CREATES it. So it leaves a marker beside it, and
a directory without one was made by someone else whatever it contains. Before that, the name
and shape rules were satisfied by an operator's own directory: ``skills`` is a name the build
writes, so ``<out>.staging/skills/notes.txt`` passed the top-level check and the recursive
delete removed notes.txt.

The marker sits BESIDE staging rather than inside it because ``bundle_digest(staging)`` is a
frozen contract value computed over everything in there -- a file inside would either change
that digest or ship inside the bundle.
"""

from __future__ import annotations

import pathlib

import pytest

from .test_producer import load_build, make_crew


def _crew(mod, tmp_path):
    src = make_crew(tmp_path / "home", skills={"faq": {"SKILL.md": "# FAQ\nhours"}})
    return mod.resolve_crew("frontdesk", src)


def _build(mod, crew, out):
    spec = mod.read_agent_spec(crew)
    return mod.build_bundle(crew, spec, mod.enumerate_all(crew, spec), None, out)


def _staging(out: pathlib.Path) -> pathlib.Path:
    return out.parent / (out.name + ".staging")


def _marker(out: pathlib.Path) -> pathlib.Path:
    return out.parent / (out.name + ".staging.owned")


def test_an_unmarked_staging_directory_is_refused(tmp_path):
    """Even when everything in it uses names the build writes."""
    mod = load_build()
    crew = _crew(mod, tmp_path)
    out = tmp_path / "bundle"
    theirs = _staging(out)
    (theirs / "skills").mkdir(parents=True)
    (theirs / "skills" / "notes.txt").write_text("my own notes\n", encoding="utf-8")

    with pytest.raises(mod.ExportRefused, match="did not create it"):
        _build(mod, crew, out)

    assert (theirs / "skills" / "notes.txt").read_text(encoding="utf-8") == "my own notes\n"


def test_an_unmarked_but_perfectly_bundle_shaped_staging_is_refused(tmp_path):
    """The old name+shape scan passed this: every name is one the build writes."""
    mod = load_build()
    crew = _crew(mod, tmp_path)
    out = tmp_path / "bundle"
    theirs = _staging(out)
    theirs.mkdir(parents=True)
    (theirs / "manifest.json").write_text('{"mine": true}\n', encoding="utf-8")
    (theirs / "agent.json").write_text("{}\n", encoding="utf-8")
    (theirs / "skills").mkdir()

    with pytest.raises(mod.ExportRefused, match="did not create it"):
        _build(mod, crew, out)

    assert (theirs / "manifest.json").read_text(encoding="utf-8") == '{"mine": true}\n'


def test_a_marked_staging_directory_is_cleaned_and_the_build_proceeds(tmp_path):
    """What a killed build leaves: the directory AND the marker."""
    mod = load_build()
    crew = _crew(mod, tmp_path)
    out = tmp_path / "bundle"
    abandoned = _staging(out)
    (abandoned / "skills").mkdir(parents=True)
    (abandoned / "agent.json").write_text("{}\n", encoding="utf-8")
    _marker(out).write_text("left by an earlier run\n", encoding="utf-8")

    _build(mod, crew, out)
    assert (out / "manifest.json").is_file()


def test_a_successful_build_leaves_no_marker(tmp_path):
    """A marker left behind is a licence for the next run to delete whatever is there."""
    mod = load_build()
    crew = _crew(mod, tmp_path)
    out = tmp_path / "bundle"
    _build(mod, crew, out)
    assert not _marker(out).exists()
    assert not _staging(out).exists()


def test_a_failed_build_leaves_no_marker(tmp_path):
    """Otherwise the failure hands the next run permission it should not have."""
    mod = load_build()
    crew = _crew(mod, tmp_path)
    out = tmp_path / "bundle"
    out.mkdir()
    (out / "quarterly-report.xlsx").write_bytes(b"not mine to delete")

    with pytest.raises(mod.ExportRefused):
        _build(mod, crew, out)

    assert not _marker(out).exists(), "the refusal left a marker behind"
    assert not _staging(out).exists()
    assert (out / "quarterly-report.xlsx").read_bytes() == b"not mine to delete"


def test_the_marker_never_ships_inside_the_bundle(tmp_path):
    """It sits beside staging so the frozen bundle digest is unchanged."""
    mod = load_build()
    crew = _crew(mod, tmp_path)
    out = tmp_path / "bundle"
    _build(mod, crew, out)
    names = {p.name for p in out.rglob("*")}
    assert not any("staging" in n for n in names), f"a staging artefact shipped: {names}"


def test_the_bundle_digest_still_covers_what_it_claims(tmp_path):
    """The manifest's recorded digest must still re-derive from the shipped bundle."""
    import json

    mod = load_build()
    crew = _crew(mod, tmp_path)
    out = tmp_path / "bundle"
    _build(mod, crew, out)
    recorded = json.loads((out / "manifest.json").read_text(encoding="utf-8"))["digest"]
    assert recorded == mod.bundle_digest(out)


# ---------------------------------------------------------------------------
# The marker is a PROOF, so a symlink must not be able to stand in for it.
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not hasattr(pathlib.Path, "symlink_to"), reason="no symlink support")
def test_a_symlinked_marker_does_not_pass_as_this_build_s_own(tmp_path):
    """``Path.is_file()`` follows symlinks, which would defeat the whole mechanism.

    The marker is the sole proof that lets ``build_bundle`` recursively delete the
    staging directory. A symlink at the marker path resolving to ANY regular file
    satisfies ``is_file()``, so before this guard a planted link bought two
    irreversible things at once: the ``rmtree`` of a staging directory this build did
    not create, and a ``write_text`` that followed the link onto its target.

    Both are asserted, not just the refusal: a refusal that still deleted or still
    clobbered would pass a test that only checked for the exception.
    """
    mod = load_build()
    crew = _crew(mod, tmp_path)
    out = tmp_path / "bundle"

    theirs = _staging(out)
    (theirs / "skills").mkdir(parents=True)
    (theirs / "skills" / "notes.txt").write_text("my own notes\n", encoding="utf-8")

    victim = tmp_path / "quarterly-report.csv"
    victim.write_text("month,revenue\n", encoding="utf-8")
    try:
        _marker(out).symlink_to(victim)
    except (OSError, NotImplementedError) as exc:  # pragma: no cover - Windows w/o privilege
        pytest.skip(f"cannot create a symlink here: {exc}")

    with pytest.raises(mod.ExportRefused, match="is a symlink"):
        _build(mod, crew, out)

    # The link is refused rather than followed: the staging directory this build did
    # not create is intact, and the file the link named is untouched.
    assert (theirs / "skills" / "notes.txt").read_text(encoding="utf-8") == "my own notes\n"
    assert victim.read_text(encoding="utf-8") == "month,revenue\n"


@pytest.mark.skipif(not hasattr(pathlib.Path, "symlink_to"), reason="no symlink support")
def test_a_symlink_planted_after_the_check_cannot_redirect_the_write(tmp_path):
    """The refusal above reads the path; this pins that the WRITE does not trust it.

    The marker lives in a directory the threat model treats as writable, so a link can
    appear between the ownership check and the write. ``O_NOFOLLOW`` is what makes the
    write refuse rather than follow, and the way to test that without racing a real
    build is to call the writer directly against a path that is already a link -- the
    state the race would produce.

    Skipped where the platform has no ``O_NOFOLLOW`` (Windows), because there the
    visible-symlink refusal is the whole guarantee and this assertion would be
    claiming one the code does not make.
    """
    import os

    if not hasattr(os, "O_NOFOLLOW"):
        pytest.skip("no O_NOFOLLOW on this platform; the read-time refusal is the guard")

    mod = load_build()
    victim = tmp_path / "quarterly-report.csv"
    victim.write_text("month,revenue\n", encoding="utf-8")
    link = tmp_path / "bundle.staging.owned"
    try:
        link.symlink_to(victim)
    except (OSError, NotImplementedError) as exc:  # pragma: no cover
        pytest.skip(f"cannot create a symlink here: {exc}")

    with pytest.raises(OSError):
        mod._write_marker_nofollow(link, "owned by this build\n")

    assert victim.read_text(encoding="utf-8") == "month,revenue\n"


def test_the_marker_writer_still_writes_an_ordinary_marker(tmp_path):
    """The no-follow open must not have broken the ordinary path it replaced."""
    mod = load_build()
    target = tmp_path / "bundle.staging.owned"
    mod._write_marker_nofollow(target, "owned by this build\n")
    assert target.read_text(encoding="utf-8") == "owned by this build\n"
    # Truncating, not appending: a second call must not stack two markers.
    mod._write_marker_nofollow(target, "owned again\n")
    assert target.read_text(encoding="utf-8") == "owned again\n"
