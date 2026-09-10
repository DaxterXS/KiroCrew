"""``sandbox`` is an OPERATOR opt-in, not an agent-reachable one.

A script cron runs under the ``cc`` sandbox, which hides the credential stores
from the child. ``"standard"`` widens that, so WHO may write the field is itself
the control: a prompt-injected agent under an auto-approving session must not be
able to widen the sandbox its own next script runs in. That is the rule the
vault-secret grant flow already enforces -- the agent may record a REQUEST, only
the operator mints the grant -- applied here as "the agent cannot ask at all".

Reachable from: the dashboard REST PATCH handler, and ``kirocrew cron update
--sandbox``. Not reachable from: MCP ``cron_add`` / ``cron_update``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from body_stream_helpers import attach_body

from kiro_crew.cron import CronService
from kiro_crew.dashboard.handlers import api_cron_update
from kiro_crew.validation import MCP_CRON_SCHEMAS, ValidationError, validate_tool_args


def _make_request(body: dict, job_id: str = "abc123") -> MagicMock:
    mock_state = MagicMock()
    mock_job = MagicMock()
    mock_job.id = job_id
    mock_state.crons.update_job_async = AsyncMock(return_value=mock_job)

    request = MagicMock()
    request.app = {"state": mock_state}
    request.match_info = {"job_id": job_id}
    attach_body(request, body)
    return request


class TestMcpToolsCannotSetIt:
    @pytest.mark.parametrize("tool", ["cron_add", "cron_update"])
    def test_the_tool_schema_declares_no_sandbox_field(self, tool: str) -> None:
        names = {spec.name for spec in MCP_CRON_SCHEMAS[tool].fields}
        assert "sandbox" not in names, (
            f"{tool} must not accept 'sandbox': an agent that can widen its own "
            "script's sandbox has defeated the cc default. Only the dashboard "
            "REST handler and `kirocrew cron update` may write it."
        )

    @pytest.mark.parametrize(
        "tool,args",
        [
            ("cron_add", {"name": "j", "every": 300, "sandbox": "standard"}),
            ("cron_update", {"job_id": "abc123", "sandbox": "standard"}),
        ],
    )
    def test_passing_it_anyway_is_refused(self, tool: str, args: dict) -> None:
        """The validator rejects unknown keys, so the omission above is enforced
        rather than merely documented -- a smuggled 'sandbox' is an error, not a
        value that lands somewhere by accident."""
        with pytest.raises(ValidationError):
            validate_tool_args(args, MCP_CRON_SCHEMAS[tool])

    @pytest.mark.parametrize("tool", ["cron_add", "cron_update"])
    def test_the_advertised_input_schema_has_no_sandbox_property(self, tool: str) -> None:
        """The model reads the advertised schema, not the validator. Advertising
        a field the validator refuses would make every use of it an error."""
        from kiro_crew.mcp_cron import _list_tools

        defn = next(t for t in _list_tools() if t["name"] == tool)
        assert "sandbox" not in defn["inputSchema"]["properties"]


class TestRestHandlerAcceptsIt:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("value", ["cc", "standard", ""])
    async def test_a_valid_value_reaches_the_store(self, value: str) -> None:
        request = _make_request({"sandbox": value})

        resp = await api_cron_update(request)

        assert resp.status == 200
        _, kwargs = request.app["state"].crons.update_job_async.call_args
        assert kwargs.get("sandbox") == value

    @pytest.mark.asyncio
    async def test_null_narrows_to_the_default(self) -> None:
        request = _make_request({"sandbox": None})

        resp = await api_cron_update(request)

        assert resp.status == 200
        _, kwargs = request.app["state"].crons.update_job_async.call_args
        assert kwargs.get("sandbox") == ""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad", ["off", "strict", "CC", 1, ["cc"]])
    async def test_an_invalid_value_is_refused_and_nothing_is_written(self, bad: object) -> None:
        """'strict' is refused too: that profile belongs to a secret-granted run
        and is chosen by the runner, never stored as an operator's pick."""
        request = _make_request({"sandbox": bad})

        resp = await api_cron_update(request)

        assert resp.status == 400
        request.app["state"].crons.update_job_async.assert_not_called()


class TestCliAcceptsIt:
    def test_cron_update_sandbox_reaches_the_store(self, tmp_path: Path) -> None:
        svc = CronService(base_dir=tmp_path)
        svc._load()
        job = svc.add_job(name="s", message="m", every_secs=60, script="x.py:run")
        assert job.sandbox == ""

        from kiro_crew.cli_commands import _cron

        args = argparse.Namespace(cron_action="update", job_id=job.id, sandbox="standard")
        with patch("kiro_crew.cli_commands.config_dir", return_value=tmp_path):
            _cron(args)

        reloaded = CronService(base_dir=tmp_path)
        reloaded._load()
        assert reloaded.get_job(job.id).sandbox == "standard"

    def test_cron_update_without_the_flag_leaves_it_alone(self, tmp_path: Path) -> None:
        """An update that does not mention the sandbox must not reset a job an
        operator widened -- so the CLI default is None, not ""."""
        svc = CronService(base_dir=tmp_path)
        svc._load()
        job = svc.add_job(
            name="s", message="m", every_secs=60, script="x.py:run", sandbox="standard"
        )

        from kiro_crew.cli_commands import _cron

        args = argparse.Namespace(cron_action="update", job_id=job.id, name="renamed", sandbox=None)
        with patch("kiro_crew.cli_commands.config_dir", return_value=tmp_path):
            _cron(args)

        reloaded = CronService(base_dir=tmp_path)
        reloaded._load()
        assert reloaded.get_job(job.id).sandbox == "standard"
        assert reloaded.get_job(job.id).name == "renamed"


class TestImportStampsTheDefault:
    """An import is not an upgrade.

    The loader reads a MISSING key on a script record as "written before the cc
    default" and grandfathers it to the wide profile -- right for this host's own
    pre-upgrade store, wrong for a record arriving from somewhere else, which
    would get the wide sandbox with nobody having asked for it.
    """

    @staticmethod
    def _store(tmp_path: Path, *records: dict) -> Path:
        path = tmp_path / "crons.json"
        path.write_text(json.dumps({"jobs": list(records)}), encoding="utf-8")
        return path

    @staticmethod
    def _record(**over: object) -> dict:
        rec: dict = {
            "id": "j1",
            "name": "imported",
            "message": "args",
            "schedule": {"kind": "every", "every_secs": 60},
        }
        rec.update(over)
        return rec

    def test_an_imported_script_record_gets_the_explicit_default(self, tmp_path: Path) -> None:
        from kiro_crew.portability import _sanitize_imported_crons

        path = self._store(tmp_path, self._record(script="x.py:run"))
        _sanitize_imported_crons(path)

        stored = json.loads(path.read_text(encoding="utf-8"))["jobs"][0]
        assert stored["sandbox"] == ""

        svc = CronService(base_dir=tmp_path)
        svc._load()
        assert svc.get_job("j1").sandbox == ""
        assert svc._sandbox_grandfathered is False

    def test_an_imported_script_record_keeps_an_explicit_value(self, tmp_path: Path) -> None:
        """The stamp fills an ABSENT key; it never overrides a real setting."""
        from kiro_crew.portability import _sanitize_imported_crons

        path = self._store(tmp_path, self._record(script="x.py:run", sandbox="standard"))
        _sanitize_imported_crons(path)

        stored = json.loads(path.read_text(encoding="utf-8"))["jobs"][0]
        assert stored["sandbox"] == "standard"

    def test_a_non_script_import_is_not_stamped(self, tmp_path: Path) -> None:
        """Nothing reads the field for an agent job, so there is nothing to fill."""
        from kiro_crew.portability import _sanitize_imported_crons

        path = self._store(tmp_path, self._record())
        _sanitize_imported_crons(path)

        stored = json.loads(path.read_text(encoding="utf-8"))["jobs"][0]
        assert "sandbox" not in stored
