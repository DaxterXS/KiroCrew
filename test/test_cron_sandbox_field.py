"""The cron store's ``sandbox`` field: round-trip, grandfather, write boundaries.

An ungranted script cron used to run under the WIDE ``standard`` sandbox, which
leaves ``~/.aws/credentials``, ``~/.kube/config`` and ``~/.netrc`` readable by
the child. The only gate was a static text scan whose own docstring says static
analysis cannot be the fence. Scripts now default to ``cc`` (those stores
hidden, ``~/.aws/config`` and ``credential_process`` auth still working).

Two properties carry the whole design and are pinned here:

* **Absence of the key is the pre-upgrade signal.** A script record with no
  ``sandbox`` key at all ran ``standard`` before the upgrade and keeps it, so an
  upgrade changes no behaviour for a job that already existed. Every record
  written since serializes the field explicitly, so ``""`` can never be mistaken
  for "predates the field".
* **Only an operator may widen it.** The value is settable from the dashboard
  REST PATCH handler and ``kirocrew cron update --sandbox``; the MCP
  ``cron_add`` / ``cron_update`` tools do not carry it, so a prompt-injected
  agent under an auto-approving session cannot widen the sandbox its own next
  script runs in. That is the vault-secret grant rule applied to the sandbox.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from kiro_crew.cron import (
    _CRON_SANDBOX_MODES,
    CronJob,
    CronSchedule,
    CronService,
    _job_from_record,
    _validate_sandbox_mode,
)


def _record(**over: object) -> dict:
    """A minimally valid on-disk cron record. ``sandbox`` is absent by default."""
    rec: dict = {
        "id": "j1",
        "name": "legacy",
        "message": "args",
        "schedule": {"kind": "every", "every_secs": 60},
    }
    rec.update(over)
    return rec


def _write_store(tmp_path: Path, *records: dict) -> Path:
    path = tmp_path / "crons.json"
    path.write_text(json.dumps({"jobs": list(records)}, indent=2), encoding="utf-8")
    return path


class TestSandboxModeValidator:
    def test_accepts_the_three_spellings(self) -> None:
        for mode in _CRON_SANDBOX_MODES:
            assert _validate_sandbox_mode(mode) == mode

    @pytest.mark.parametrize("bad", ["off", "strict", "CC", "auto", None, 1, True, ["cc"]])
    def test_refuses_everything_else(self, bad: object) -> None:
        # "strict" is refused deliberately: it is the profile a SECRET-GRANTED
        # run takes, chosen by the runner from the grant, never a stored value an
        # operator picks.
        with pytest.raises(ValueError, match="Invalid sandbox"):
            _validate_sandbox_mode(bad)


class TestGrandfatherOnLoad:
    def test_legacy_script_record_loads_as_standard(self, tmp_path: Path) -> None:
        """No ``sandbox`` key + a script = a job that has always run wide."""
        _write_store(tmp_path, _record(script="x.py:run"))
        svc = CronService(base_dir=tmp_path)
        svc._load()
        assert svc.get_job("j1").sandbox == "standard"

    def test_legacy_script_record_marks_the_store_dirty(self, tmp_path: Path) -> None:
        """The in-memory job now says something the file does not."""
        _write_store(tmp_path, _record(script="x.py:run"))
        svc = CronService(base_dir=tmp_path)
        svc._load()
        assert svc._sandbox_grandfathered is True

    def test_the_next_save_makes_the_grandfathered_value_explicit(self, tmp_path: Path) -> None:
        """After one write the record no longer reads as pre-upgrade, so a later
        load resolves it from the stored value rather than the absence rule."""
        _write_store(tmp_path, _record(script="x.py:run"))
        svc = CronService(base_dir=tmp_path)
        svc._load()
        svc._save()
        stored = json.loads((tmp_path / "crons.json").read_text(encoding="utf-8"))["jobs"][0]
        assert stored["sandbox"] == "standard"
        assert svc._sandbox_grandfathered is False

        svc2 = CronService(base_dir=tmp_path)
        svc2._load()
        assert svc2.get_job("j1").sandbox == "standard"
        assert svc2._sandbox_grandfathered is False

    def test_legacy_command_record_stays_on_the_default(self, tmp_path: Path) -> None:
        """Command jobs already ran cc, so there is nothing to grandfather."""
        _write_store(tmp_path, _record(id="c1", command="echo hi"))
        svc = CronService(base_dir=tmp_path)
        svc._load()
        assert svc.get_job("c1").sandbox == ""
        assert svc._sandbox_grandfathered is False

    def test_legacy_agent_record_stays_on_the_default(self, tmp_path: Path) -> None:
        """An agent job spawns no script child; the field is inert for it."""
        _write_store(tmp_path, _record(id="a1"))
        svc = CronService(base_dir=tmp_path)
        svc._load()
        assert svc.get_job("a1").sandbox == ""
        assert svc._sandbox_grandfathered is False

    def test_an_explicit_empty_value_is_not_grandfathered(self, tmp_path: Path) -> None:
        """This is the case the two spellings exist for: a script job written
        AFTER the upgrade that the operator left on the default must stay cc."""
        _write_store(tmp_path, _record(script="x.py:run", sandbox=""))
        svc = CronService(base_dir=tmp_path)
        svc._load()
        assert svc.get_job("j1").sandbox == ""
        assert svc._sandbox_grandfathered is False

    def test_an_unrecognised_stored_value_resolves_to_the_safe_default(self) -> None:
        """The store is hand-editable. A junk value must narrow to cc, and must
        not drop the record — the loader's per-entry isolation would erase the
        job from disk on the next write."""
        job = _job_from_record(_record(script="x.py:run", sandbox="off"))
        assert job.sandbox == ""

    def test_a_load_that_grandfathers_nothing_clears_a_prior_mark(self, tmp_path: Path) -> None:
        """The flag describes the CURRENT load, not a high-water mark."""
        _write_store(tmp_path, _record(script="x.py:run"))
        svc = CronService(base_dir=tmp_path)
        svc._load()
        assert svc._sandbox_grandfathered is True
        _write_store(tmp_path, _record(script="x.py:run", sandbox="cc"))
        svc._load()
        assert svc._sandbox_grandfathered is False


class TestRoundTrip:
    def test_a_new_job_serializes_the_field_explicitly(self, tmp_path: Path) -> None:
        """Written even when "" — absence of the key is a load-bearing signal."""
        svc = CronService(base_dir=tmp_path)
        svc._load()
        svc.add_job(name="s", message="m", every_secs=60, script="x.py:run")
        stored = json.loads((tmp_path / "crons.json").read_text(encoding="utf-8"))["jobs"][0]
        assert "sandbox" in stored
        assert stored["sandbox"] == ""

    def test_an_explicit_value_round_trips(self, tmp_path: Path) -> None:
        svc = CronService(base_dir=tmp_path)
        svc._load()
        job = svc.add_job(
            name="s", message="m", every_secs=60, script="x.py:run", sandbox="standard"
        )
        svc2 = CronService(base_dir=tmp_path)
        svc2._load()
        assert svc2.get_job(job.id).sandbox == "standard"

    def test_add_job_refuses_an_invalid_value(self, tmp_path: Path) -> None:
        svc = CronService(base_dir=tmp_path)
        svc._load()
        with pytest.raises(ValueError, match="Invalid sandbox"):
            svc.add_job(name="s", message="m", every_secs=60, script="x.py:run", sandbox="off")

    def test_update_sets_and_persists_the_value(self, tmp_path: Path) -> None:
        svc = CronService(base_dir=tmp_path)
        svc._load()
        job = svc.add_job(name="s", message="m", every_secs=60, script="x.py:run")
        assert svc.update_job(job.id, sandbox="standard") is not None
        svc2 = CronService(base_dir=tmp_path)
        svc2._load()
        assert svc2.get_job(job.id).sandbox == "standard"

    def test_update_refuses_an_invalid_value_and_mutates_nothing(self, tmp_path: Path) -> None:
        """The check sits with the other pre-mutation gates, so a rejected
        update cannot strand an earlier field write on the in-memory job."""
        svc = CronService(base_dir=tmp_path)
        svc._load()
        job = svc.add_job(name="s", message="m", every_secs=60, script="x.py:run")
        with pytest.raises(ValueError, match="Invalid sandbox"):
            svc.update_job(job.id, name="renamed", sandbox="off")
        assert svc.get_job(job.id).name == "s"
        assert svc.get_job(job.id).sandbox == ""

    def test_update_can_narrow_a_widened_job_back(self, tmp_path: Path) -> None:
        svc = CronService(base_dir=tmp_path)
        svc._load()
        job = svc.add_job(
            name="s", message="m", every_secs=60, script="x.py:run", sandbox="standard"
        )
        svc.update_job(job.id, sandbox="cc")
        assert svc.get_job(job.id).sandbox == "cc"

    def test_the_field_defaults_to_the_narrow_profile(self) -> None:
        job = CronJob(
            id="j", name="n", message="m", schedule=CronSchedule(kind="every", every_secs=60)
        )
        assert job.sandbox == ""
