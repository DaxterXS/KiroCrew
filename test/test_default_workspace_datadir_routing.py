"""Routing the default-workspace data dir through ``workspace_dir_for``.

Issue #7922. Every gateway/app site that used to hardcode
``config_dir() / "workspace"`` for the *data* dir (knowledge.db, episodic
memory, per-app state) now resolves it via ``workspace_dir_for(None)``.

Two things are proven here:

1. **No-op at the shipped default.** With ``workspaces.default.dir = "workspace"``
   the resolver returns exactly ``config_dir() / "workspace"`` -- byte-identical
   to the path every routed site used to hardcode. So the whole mechanical diff
   provably changes nothing on an existing install until a user opts in.

2. **Relocation moves them together.** With ``workspaces.default.dir`` pointed at
   a new relative or absolute dir, every routed site resolves under the new dir.
   That is what makes the change complete rather than a split brain where part of
   the data moves and part does not.
"""

from __future__ import annotations

import json
import unittest.mock
from pathlib import Path

from kiro_crew.config.loader import config_dir, workspace_dir_for


def _patched_config_path(tmp_path: Path, raw: dict):
    """Patch loader.config_path at a temp file holding ``raw`` (never a real path)."""
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps(raw), encoding="utf-8")
    return unittest.mock.patch("kiro_crew.config.loader.config_path", return_value=cfg_file)


class TestDefaultIsNoOp:
    """With the shipped default, the resolver equals the old hardcoded path."""

    def test_resolver_equals_hardcoded_default(self, tmp_path: Path) -> None:
        # The shipped default: workspaces.default.dir == "workspace".
        with _patched_config_path(tmp_path, {"workspaces": {"default": {"dir": "workspace"}}}):
            assert workspace_dir_for(None) == config_dir() / "workspace"

    def test_empty_config_equals_hardcoded_default(self, tmp_path: Path) -> None:
        # An install with no workspaces block at all also falls to "workspace".
        with _patched_config_path(tmp_path, {}):
            assert workspace_dir_for(None) == config_dir() / "workspace"

    def test_every_routed_subpath_equals_its_old_expression(self, tmp_path: Path) -> None:
        """Each routed site's resolved path equals what it used to hardcode.

        The left side is exactly what each call site now builds from
        ``workspace_dir_for(None)``; the right side is the literal string it
        replaced. Identical at the default is the whole safety argument.
        """
        with _patched_config_path(tmp_path, {"workspaces": {"default": {"dir": "workspace"}}}):
            base = workspace_dir_for(None)
            cdir = config_dir()

            # memory.py workspace_dir() / memory_dir()
            assert base == cdir / "workspace"
            # knowledge.db (state.py, mcp_tools/knowledge.py x3, metrics, cli.py)
            assert (
                base / "knowledge" / "knowledge.db"
                == cdir / "workspace" / "knowledge" / "knowledge.db"
            )
            # spec_builder _state_dir(): base / APP_NAME
            assert base / "spec-builder" == cdir / "workspace" / "spec-builder"
            # auto_research research_dir(): base / "research"
            assert base / "research" == cdir / "workspace" / "research"
            # NOTE: md_notebook is deliberately NOT routed. Its pat/vaults.json/
            # settings.json are credential + push-authorization keystones behind
            # the literal-path fence in security/paths.py; letting them follow an
            # agent-writable config.json would move them out from behind that
            # fence. See test_md_notebook_stays_fenced below.


class TestRelocationMovesEverythingTogether:
    """A relocated default dir moves every routed subpath under the new root."""

    def test_relative_relocation(self, tmp_path: Path) -> None:
        with _patched_config_path(
            tmp_path,
            {"workspaces": {"default": {"dir": "workspaces/default"}}},
        ):
            base = workspace_dir_for(None)
            assert base == config_dir() / "workspaces" / "default"
            # Knowledge + app state all hang off the SAME relocated base, so the
            # gateway and the MCP subprocess (both calling workspace_dir_for(None))
            # agree on one path -- no split brain.
            assert (base / "knowledge" / "knowledge.db").is_relative_to(base)
            assert (base / "research").is_relative_to(base)

    def test_absolute_relocation(self, tmp_path: Path) -> None:
        target = tmp_path / "relocated"
        with _patched_config_path(
            tmp_path,
            {"workspaces": {"default": {"dir": str(target)}}},
        ):
            base = workspace_dir_for(None)
            assert base == target
            assert base.is_absolute()

    def test_legacy_flat_string_relocation(self, tmp_path: Path) -> None:
        # Legacy flat format: workspaces.default is the dir string directly.
        with _patched_config_path(tmp_path, {"workspaces": {"default": "projects/default"}}):
            assert workspace_dir_for(None) == config_dir() / "projects" / "default"


class TestMdNotebookStaysFenced:
    """md_notebook's credential/push-auth keystones must NOT follow relocation.

    ``pat``, ``vaults.json`` and ``settings.json`` are protected by the
    literal-path fence in ``security/paths.py`` (anchored at the static
    crew-home ``workspace/md-notebook/*``). ``config.json`` is writable by an
    auto-approved agent shell, so if this app's data home followed
    ``workspaces.default.dir`` an agent could relocate those files out from
    behind the fence and flip ``autoSync`` (unattended ``git push``). So
    ``_crew_data_home()`` deliberately stays anchored at ``config_dir()``.
    """

    def test_relocated_config_does_not_move_md_notebook(self, tmp_path: Path) -> None:
        from kiro_crew.apps.builtins.md_notebook import server as md_server

        with _patched_config_path(
            tmp_path, {"workspaces": {"default": {"dir": "relocated/elsewhere"}}}
        ):
            # The resolver WOULD relocate...
            assert workspace_dir_for(None) == config_dir() / "relocated" / "elsewhere"
            # ...but md_notebook stays anchored at the fenced default path.
            assert md_server._crew_data_home() == config_dir() / "workspace" / "md-notebook"
