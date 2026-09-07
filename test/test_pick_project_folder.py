"""Tests for the native project-folder picker.

Covers /api/pick-folder and /api/project-picker/config: the availability gate
(local + a platform we can drive a native chooser on), the argv the dialog
launches with (a fixed literal on both platforms -- no caller value is
interpolated), and that a returned path is handed back verbatim for the existing
downstream validation rather than being trusted here.
"""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from kiro_crew.dashboard.handlers import (
    api_pick_project_folder,
    api_project_picker_config,
)
from kiro_crew.dashboard.handlers.files import (
    _PROJECT_OSASCRIPT_PROGRAM,
    _PROJECT_POWERSHELL_PROGRAM,
    _project_folder_dialog_argv,
    _project_folder_picker_available,
    _run_project_folder_dialog,
)

FILES = "kiro_crew.dashboard.handlers.files"


def _make_app(local_only: bool) -> web.Application:
    app = web.Application()
    app["local_only"] = local_only
    app.router.add_post("/api/pick-folder", api_pick_project_folder)
    app.router.add_get("/api/project-picker/config", api_project_picker_config)
    return app


@pytest.fixture()
def mock_sel():
    with patch("kiro_crew.dashboard.handlers.sel") as m:
        m.return_value = MagicMock()
        yield m.return_value


def _req(local_only: bool) -> MagicMock:
    r = MagicMock()
    r.app = {"local_only": local_only}
    return r


class TestAvailabilityGate:
    def test_unavailable_when_not_local(self):
        with patch(f"{FILES}.sys") as s:
            s.platform = "darwin"
            assert _project_folder_picker_available(_req(local_only=False)) is False

    def test_available_on_local_macos_with_osascript(self):
        with (
            patch(f"{FILES}.sys") as s,
            patch(f"{FILES}.is_direct_local_request", return_value=True),
            patch(f"{FILES}.shutil.which", return_value="/usr/bin/osascript"),
        ):
            s.platform = "darwin"
            assert _project_folder_picker_available(_req(local_only=True)) is True

    def test_unavailable_when_proxied_remote(self):
        # local_only True but a reverse proxy delivers a remote user's request:
        # the direct-local check must still deny it.
        with (
            patch(f"{FILES}.sys") as s,
            patch(f"{FILES}.is_direct_local_request", return_value=False),
            patch(f"{FILES}.shutil.which", return_value="/usr/bin/osascript"),
        ):
            s.platform = "darwin"
            assert _project_folder_picker_available(_req(local_only=True)) is False

    def test_unavailable_on_macos_without_osascript(self):
        with (
            patch(f"{FILES}.sys") as s,
            patch(f"{FILES}.is_direct_local_request", return_value=True),
            patch(f"{FILES}.shutil.which", return_value=None),
        ):
            s.platform = "darwin"
            assert _project_folder_picker_available(_req(local_only=True)) is False

    def test_available_on_local_windows_with_powershell(self):
        with (
            patch(f"{FILES}.sys") as s,
            patch(f"{FILES}.is_direct_local_request", return_value=True),
            patch(f"{FILES}._windows_powershell", return_value="powershell.exe"),
        ):
            s.platform = "win32"
            assert _project_folder_picker_available(_req(local_only=True)) is True

    def test_unavailable_on_windows_without_powershell(self):
        with (
            patch(f"{FILES}.sys") as s,
            patch(f"{FILES}.is_direct_local_request", return_value=True),
            patch(f"{FILES}._windows_powershell", return_value=None),
        ):
            s.platform = "win32"
            assert _project_folder_picker_available(_req(local_only=True)) is False

    def test_unavailable_on_linux(self):
        """A plain browser / Linux gateway has no host chooser -- the picker is
        honestly absent and the typed-path route stays the way in."""
        with (
            patch(f"{FILES}.sys") as s,
            patch(f"{FILES}.is_direct_local_request", return_value=True),
        ):
            s.platform = "linux"
            assert _project_folder_picker_available(_req(local_only=True)) is False


class TestDialogArgv:
    def test_macos_argv_is_fixed_osascript_literal(self):
        with patch(f"{FILES}.sys") as s:
            s.platform = "darwin"
            argv = _project_folder_dialog_argv()
        assert argv == ["osascript", "-e", _PROJECT_OSASCRIPT_PROGRAM]
        # The program body carries no interpolation slot -- nothing injectable.
        assert "{" not in _PROJECT_OSASCRIPT_PROGRAM
        assert "%" not in _PROJECT_OSASCRIPT_PROGRAM

    def test_windows_argv_uses_noprofile_sta_and_fixed_program(self):
        with (
            patch(f"{FILES}.sys") as s,
            patch(f"{FILES}._windows_powershell", return_value="C:\\ps.exe"),
        ):
            s.platform = "win32"
            argv = _project_folder_dialog_argv()
        assert argv is not None
        assert argv[0] == "C:\\ps.exe"
        assert "-NoProfile" in argv and "-NonInteractive" in argv and "-STA" in argv
        assert argv[-1] == _PROJECT_POWERSHELL_PROGRAM
        # The `{...}` here is PowerShell block syntax, not a format slot -- what
        # matters is that no caller value is interpolated into the program text.
        assert "{}" not in _PROJECT_POWERSHELL_PROGRAM
        assert "%s" not in _PROJECT_POWERSHELL_PROGRAM

    def test_windows_argv_none_without_powershell(self):
        with patch(f"{FILES}.sys") as s, patch(f"{FILES}._windows_powershell", return_value=None):
            s.platform = "win32"
            assert _project_folder_dialog_argv() is None

    def test_linux_argv_none(self):
        with patch(f"{FILES}.sys") as s:
            s.platform = "linux"
            assert _project_folder_dialog_argv() is None


class TestRunDialog:
    def test_returns_stripped_path_on_success(self):
        proc = MagicMock(returncode=0, stdout="/Users/me/proj\n")
        with (
            patch(f"{FILES}._project_folder_dialog_argv", return_value=["x"]),
            patch(f"{FILES}.subprocess.run", return_value=proc),
        ):
            assert _run_project_folder_dialog() == "/Users/me/proj"

    def test_returns_none_on_cancel_nonzero(self):
        proc = MagicMock(returncode=1, stdout="")
        with (
            patch(f"{FILES}._project_folder_dialog_argv", return_value=["x"]),
            patch(f"{FILES}.subprocess.run", return_value=proc),
        ):
            assert _run_project_folder_dialog() is None

    def test_returns_none_on_empty_stdout_even_when_zero(self):
        proc = MagicMock(returncode=0, stdout="   \n")
        with (
            patch(f"{FILES}._project_folder_dialog_argv", return_value=["x"]),
            patch(f"{FILES}.subprocess.run", return_value=proc),
        ):
            assert _run_project_folder_dialog() is None

    def test_returns_none_when_no_argv(self):
        with patch(f"{FILES}._project_folder_dialog_argv", return_value=None):
            assert _run_project_folder_dialog() is None

    def test_returns_none_on_timeout(self):
        with (
            patch(f"{FILES}._project_folder_dialog_argv", return_value=["x"]),
            patch(
                f"{FILES}.subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd="x", timeout=1),
            ),
        ):
            assert _run_project_folder_dialog() is None


class TestPickFolderEndpoint:
    @pytest.mark.asyncio
    async def test_403_when_unavailable(self, mock_sel):
        with patch(f"{FILES}._project_folder_picker_available", return_value=False):
            async with TestClient(TestServer(_make_app(local_only=False))) as client:
                resp = await client.post("/api/pick-folder")
                assert resp.status == 403

    @pytest.mark.asyncio
    async def test_returns_selected_path(self, mock_sel):
        with (
            patch(f"{FILES}._project_folder_picker_available", return_value=True),
            patch(f"{FILES}._run_project_folder_dialog", return_value="/tmp/picked"),
        ):
            async with TestClient(TestServer(_make_app(local_only=True))) as client:
                resp = await client.post("/api/pick-folder")
                assert resp.status == 200
                assert (await resp.json())["path"] == "/tmp/picked"

    @pytest.mark.asyncio
    async def test_returns_null_path_on_cancel(self, mock_sel):
        with (
            patch(f"{FILES}._project_folder_picker_available", return_value=True),
            patch(f"{FILES}._run_project_folder_dialog", return_value=None),
        ):
            async with TestClient(TestServer(_make_app(local_only=True))) as client:
                resp = await client.post("/api/pick-folder")
                assert resp.status == 200
                assert (await resp.json())["path"] is None

    @pytest.mark.asyncio
    async def test_config_reports_availability(self, mock_sel):
        with patch(f"{FILES}._project_folder_picker_available", return_value=True):
            async with TestClient(TestServer(_make_app(local_only=True))) as client:
                resp = await client.get("/api/project-picker/config")
                assert resp.status == 200
                assert (await resp.json())["folder_picker"] is True

    @pytest.mark.asyncio
    async def test_config_reports_unavailable(self, mock_sel):
        with patch(f"{FILES}._project_folder_picker_available", return_value=False):
            async with TestClient(TestServer(_make_app(local_only=False))) as client:
                resp = await client.get("/api/project-picker/config")
                assert (await resp.json())["folder_picker"] is False
