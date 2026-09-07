"""The nightly backup loop as a Job SDK run.

The loop used to call ``backup.run_snapshot_backup`` directly. Two consequences
followed, and both are pinned here:

* the SDK's ``(kind, dedupe_key)`` index cannot see a caller that never enters
  it, so a nightly run and a manual click could each pay for an upload of the
  same account;
* the Backup row reads its busy state from the account-scoped ``jobs`` block,
  which is built from SDK records, so a nightly run showed the row idle.

Two more cases cover what the migration itself could break. The run's worker is a
thread and cannot await, so it reads its profile from a snapshot only the async
resolver builds -- an unattended run would be recorded ``failed`` with no upload if
the loop did not warm it. And the gate must never attribute an upload to the
dashboard owner, now that a trigger nobody is watching reaches the same runner.

Every worker started here is driven to a terminal record before its test returns:
a Job SDK worker is a real thread, and one still running at teardown would write
its record into a directory pytest has already removed.
"""

from __future__ import annotations

import asyncio
import threading
import time
from contextlib import ExitStack
from types import SimpleNamespace
from unittest import mock
from unittest.mock import AsyncMock

import pytest

from kiro_crew import aws_consent
from kiro_crew.apps import job_sdk
from kiro_crew.apps.builtins.aws_control import hooks
from kiro_crew.apps.builtins.aws_control.backend import accounts as accounts_mod
from kiro_crew.apps.builtins.aws_control.backend import backup

ACCOUNT = "111122223333"
PROFILE = "prof"
REGION = "us-west-2"
BUCKET = "kirocrew-drive-abc"
KIND = backup.KIND_SNAPSHOT


def _drain(sdk: job_sdk.JobSDK, release: threading.Event, run_id: str) -> None:
    """Release a blocked worker and wait for its record to settle.

    A `JobStore.write` landing after pytest removed the test's directory would
    recreate it -- a side effect outside the test's own sandbox. Waiting for the
    terminal record is what makes that impossible, rather than merely unlikely.
    """
    release.set()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        run = sdk.get(run_id)
        if run is not None and run.is_terminal:
            return
        time.sleep(0.01)
    raise AssertionError(f"worker for run {run_id} never reached a terminal record")


def _nightly_preconditions(stack: ExitStack, sdk, *, warm_profile: bool = True) -> None:
    """Every pre-claim check passing, so a case exercises only the claim.

    ``warm_profile=False`` leaves the loop's own profile pre-flight REAL, for the
    case that is about that pre-flight.
    """
    stack.enter_context(
        mock.patch.object(hooks.deploy_profiles, "resolve_profile", return_value=(PROFILE, REGION))
    )
    stack.enter_context(
        mock.patch.object(
            hooks.aws_consent,
            "probe_identity",
            AsyncMock(return_value=aws_consent.Identity(ok=True, account=ACCOUNT)),
        )
    )
    stack.enter_context(mock.patch.object(hooks.backup_mod, "due_for_nightly", return_value=True))
    stack.enter_context(
        mock.patch.object(hooks.aws_consent, "refuse_and_log", AsyncMock(return_value=True))
    )
    if warm_profile:
        stack.enter_context(
            mock.patch.object(
                hooks.accounts_mod,
                "resolve_account_profile",
                AsyncMock(return_value=(PROFILE, REGION)),
            )
        )
    stack.enter_context(mock.patch.object(hooks, "get_job_sdk", return_value=sdk))
    stack.enter_context(mock.patch.object(hooks.storage_mod, "find_drive", return_value=BUCKET))
    # The watch poll is a real sleep; a test must not wait 15 s for a record that
    # is already terminal on the second read.
    stack.enter_context(mock.patch.object(hooks, "_RUN_POLL_SECS", 0.01))


class TestOneUploadPerAccount:
    """A nightly claim and a manual run must not both do the paid work."""

    def test_a_nightly_claim_adopts_a_manual_run_in_flight(self, tmp_path):
        sdk = job_sdk.JobSDK(backup.APP_NAME, tmp_path)
        entered = threading.Event()
        release = threading.Event()
        ran: list[str] = []

        def _runner(handle) -> None:
            ran.append(handle.run_id)
            entered.set()
            release.wait(10)

        sdk.register(KIND, _runner)
        manual = sdk.start(KIND, dedupe_key=ACCOUNT)
        try:
            assert entered.wait(10), "the manual run's worker never started"

            with ExitStack() as stack:
                _nightly_preconditions(stack, sdk)
                # If the loop ever uploads inline again this is the call that
                # proves it: the registered runner above is a stub, so nothing
                # else in this test can reach the real snapshot backup.
                inline = stack.enter_context(
                    mock.patch.object(backup, "run_snapshot_backup", return_value={"key": "k"})
                )
                stack.enter_context(
                    mock.patch(
                        "kiro_crew.apps.builtins.aws_control.backend.storage.find_drive",
                        return_value=BUCKET,
                    )
                )
                stack.enter_context(mock.patch.object(hooks, "_audit"))
                # The watch is covered by the row-visibility case below. Here it
                # would block on the deliberately-stuck manual worker, so this
                # case is scoped to the claim, which is what it pins.
                stack.enter_context(mock.patch.object(hooks, "_watch_run", AsyncMock()))
                asyncio.run(hooks._run_once())
        finally:
            _drain(sdk, release, manual)

        inline.assert_not_called()
        assert ran == [manual], "a second worker ran for the same account"


class TestTheRowSeesANightlyRun:
    """The Backup row is honest about every run the SDK knows about."""

    def test_a_nightly_claim_leaves_an_account_scoped_run_record(self, tmp_path):
        sdk = job_sdk.JobSDK(backup.APP_NAME, tmp_path)
        done: list[str] = []
        sdk.register(KIND, lambda handle: done.append(handle.run_id))

        with ExitStack() as stack:
            _nightly_preconditions(stack, sdk)
            stack.enter_context(mock.patch.object(hooks, "_audit"))
            asyncio.run(hooks._run_once())

        mine = [r for r in sdk.list_recent(KIND, limit=20) if r.dedupe_key == ACCOUNT]
        assert len(mine) == 1, "the nightly run left no record for this account"
        assert mine[0].kind == KIND
        assert mine[0].is_terminal, "the loop returned before its own run settled"


class TestTheWorkerCanResolveItsProfile:
    """The migration moved the upload onto a thread that cannot await."""

    def test_the_loop_warms_the_snapshot_before_claiming(self, tmp_path):
        # `resolve_account_profile_cached` serves the WARM snapshot only and
        # returns None past its 300 s TTL, which the runner turns into "no working
        # connection". At 03:00 no dashboard traffic has warmed it, so without the
        # loop's own pre-flight every unattended run would be recorded failed with
        # no upload -- where the pre-PR loop used the probed profile and succeeded.
        sdk = job_sdk.JobSDK(backup.APP_NAME, tmp_path)
        sdk.register(KIND, backup.make_job_runner(sdk, KIND))
        snapshot = {
            "accounts": [
                {
                    "account": ACCOUNT,
                    "profiles": [
                        {
                            "name": PROFILE,
                            "region": REGION,
                            "identityOk": True,
                            "default": True,
                        }
                    ],
                }
            ]
        }

        with ExitStack() as stack:
            # The async resolver is left REAL here -- it is the call under test --
            # and only the probe sweep underneath `list_accounts` is faked, so the
            # snapshot the worker later reads is warmed by the real code path.
            _nightly_preconditions(stack, sdk, warm_profile=False)
            stack.enter_context(mock.patch.object(hooks, "_audit"))
            stack.enter_context(
                mock.patch.object(accounts_mod, "_build_snapshot", AsyncMock(return_value=snapshot))
            )
            stack.enter_context(mock.patch.object(backup, "_authorize_upload"))
            stack.enter_context(
                mock.patch(
                    "kiro_crew.apps.builtins.aws_control.backend.storage.find_drive",
                    return_value=BUCKET,
                )
            )
            work = stack.enter_context(mock.patch.object(backup, "run_snapshot_backup"))
            asyncio.run(hooks._run_once())

        assert work.called, "the unattended run never reached the upload"
        assert work.call_args.args[0] == ACCOUNT

    def test_an_account_with_no_working_connection_claims_nothing(self, tmp_path):
        # Fail closed: a run that can only refuse is worse than no run, because it
        # leaves a `failed` record the owner has to interpret.
        sdk = SimpleNamespace(start_async=AsyncMock(return_value="run-1"))
        with ExitStack() as stack:
            _nightly_preconditions(stack, sdk)
            stack.enter_context(
                mock.patch.object(
                    hooks.accounts_mod, "resolve_account_profile", AsyncMock(return_value=None)
                )
            )
            audit = stack.enter_context(mock.patch.object(hooks, "_audit"))
            asyncio.run(hooks._run_once())
        sdk.start_async.assert_not_called()
        audit.assert_not_called()


class TestAnUnconfiguredAccountIsASilentSkip:
    """A due account with no drive yet must not accrue a record every wake."""

    def test_a_due_account_with_no_drive_claims_nothing(self, tmp_path):
        # The runner refuses a driveless account by raising, which the SDK records
        # as `failed`, and a failed run never reaches `_record_run` -- so
        # `due_for_nightly` stays True and one more failed record would land every
        # half hour, forever, for a state that is simply not configured yet. The
        # pre-PR loop skipped silently and so must this one.
        sdk = SimpleNamespace(start_async=AsyncMock(return_value="run-1"))
        with ExitStack() as stack:
            _nightly_preconditions(stack, sdk)
            stack.enter_context(mock.patch.object(hooks.storage_mod, "find_drive", return_value=""))
            audit = stack.enter_context(mock.patch.object(hooks, "_audit"))
            asyncio.run(hooks._run_once())
        sdk.start_async.assert_not_called()
        audit.assert_not_called()

    def test_the_drive_is_looked_up_with_the_consented_profile(self, tmp_path):
        # `find_drive` reaches AWS (tag:GetResources) and consent is keyed per
        # (service, profile, region). The loop checked S3 consent for the registry
        # default, so discovery must run under THAT profile: `_pick_profile` can
        # return a healthy non-default profile of the same account, and using its
        # answer here would make an unconsented call while deciding whether to
        # claim. The run re-discovers the drive under its own authorized profile.
        sdk = SimpleNamespace(start_async=AsyncMock(return_value="run-1"))
        with ExitStack() as stack:
            _nightly_preconditions(stack, sdk)
            stack.enter_context(
                mock.patch.object(
                    hooks.accounts_mod,
                    "resolve_account_profile",
                    AsyncMock(return_value=("other-profile", "eu-1")),
                )
            )
            find = stack.enter_context(
                mock.patch.object(hooks.storage_mod, "find_drive", return_value=BUCKET)
            )
            stack.enter_context(mock.patch.object(hooks, "_audit"))
            stack.enter_context(mock.patch.object(hooks, "_watch_run", AsyncMock()))
            asyncio.run(hooks._run_once())
        assert find.call_args.args[:2] == (PROFILE, REGION)
        assert "other-profile" not in find.call_args.args
        assert find.call_args.kwargs["account"] == ACCOUNT


class TestNothingSuspendsBetweenConsentAndUse:
    """Consent is an approval control, so the gap after confirming it matters."""

    def test_the_snapshot_is_warmed_before_consent_is_confirmed(self, tmp_path):
        # The warming runs a probe sweep, which suspends. Awaiting it AFTER
        # `refuse_and_log` put that suspension between consent being confirmed and
        # `find_drive` acting on it, so consent could be withdrawn while the sweep
        # ran. Moving it above the check closes the window by subtraction rather
        # than by re-checking consent afterwards. Its own AWS work is an STS
        # identity probe plus local `aws configure get` reads -- the same class as
        # the `probe_identity` this loop already performs before the consent check
        # -- so nothing consent-gated moves ahead of consent.
        order: list[str] = []
        sdk = SimpleNamespace(start_async=AsyncMock(return_value="run-1"))

        async def _warm(account):
            order.append("warm")
            return (PROFILE, REGION)

        async def _consent(*a, **k):
            order.append("consent")
            return True

        def _find(*a, **k):
            order.append("find_drive")
            return BUCKET

        with ExitStack() as stack:
            _nightly_preconditions(stack, sdk, warm_profile=False)
            stack.enter_context(
                mock.patch.object(hooks.accounts_mod, "resolve_account_profile", _warm)
            )
            stack.enter_context(mock.patch.object(hooks.aws_consent, "refuse_and_log", _consent))
            stack.enter_context(mock.patch.object(hooks.storage_mod, "find_drive", _find))
            stack.enter_context(mock.patch.object(hooks, "_audit"))
            stack.enter_context(mock.patch.object(hooks, "_watch_run", AsyncMock()))
            asyncio.run(hooks._run_once())

        assert order == ["warm", "consent", "find_drive"]
        # And the confirmation is the LAST await before the call it authorizes:
        # anything inserted between them reopens the window.
        assert order.index("consent") + 1 == order.index("find_drive")


class TestNoPostConsentFailureIsSilent:
    """Once consent is confirmed, every exit writes a nightly record.

    An audit an error path can skip is present exactly when nothing went wrong,
    which is the opposite of the case it exists for. Before this loop claimed runs,
    a drive-discovery failure was caught in `_run_once` and audited `failed`; the
    migration moved the upload out and took the handler with it, so the raise
    reached `_loop`'s log-only catch. One case per raising exit.
    """

    def test_a_drive_discovery_failure_is_audited(self, tmp_path):
        # `find_drive` raises on an ordinary AWS error or an ambiguous match, so
        # this is a common path rather than an extreme one.
        sdk = SimpleNamespace(start_async=AsyncMock(return_value="run-1"))
        with ExitStack() as stack:
            _nightly_preconditions(stack, sdk)
            stack.enter_context(
                mock.patch.object(
                    hooks.storage_mod, "find_drive", side_effect=RuntimeError("tag:GetResources")
                )
            )
            audit = stack.enter_context(mock.patch.object(hooks, "_audit"))
            asyncio.run(hooks._run_once())
        outcomes = [c.args[2] for c in audit.call_args_list]
        assert outcomes == ["failed"]
        assert "tag:GetResources" in audit.call_args.kwargs["error"]
        sdk.start_async.assert_not_called()

    def test_a_cancel_during_discovery_is_audited_and_reraised(self, tmp_path):
        sdk = SimpleNamespace(start_async=AsyncMock(return_value="run-1"))
        with ExitStack() as stack:
            _nightly_preconditions(stack, sdk)
            stack.enter_context(
                mock.patch.object(
                    hooks.storage_mod, "find_drive", side_effect=asyncio.CancelledError()
                )
            )
            audit = stack.enter_context(mock.patch.object(hooks, "_audit"))
            with pytest.raises(asyncio.CancelledError):
                asyncio.run(hooks._run_once())
        assert [c.args[2] for c in audit.call_args_list] == ["cancelled"]

    def test_a_run_store_read_error_is_audited(self, tmp_path):
        # A claimed run whose record cannot be read left `invoked` with no
        # resolution -- the loop reported starting work and never reported its end.
        sdk = SimpleNamespace(
            start_async=AsyncMock(return_value="run-1"),
            get=mock.Mock(side_effect=OSError("job store unreadable")),
        )
        with ExitStack() as stack:
            _nightly_preconditions(stack, sdk)
            audit = stack.enter_context(mock.patch.object(hooks, "_audit"))
            asyncio.run(hooks._run_once())
        outcomes = [c.args[2] for c in audit.call_args_list]
        assert outcomes == ["invoked", "failed"]
        assert "job store unreadable" in audit.call_args.kwargs["error"]

    def test_an_absent_run_record_is_audited_as_failed(self, tmp_path):
        # Absence and an unreadable store are the same thing to the loop: it cannot
        # say how the run ended, so both take the one failure exit.
        sdk = SimpleNamespace(
            start_async=AsyncMock(return_value="run-1"), get=mock.Mock(return_value=None)
        )
        with ExitStack() as stack:
            _nightly_preconditions(stack, sdk)
            audit = stack.enter_context(mock.patch.object(hooks, "_audit"))
            asyncio.run(hooks._run_once())
        outcomes = [c.args[2] for c in audit.call_args_list]
        assert outcomes == ["invoked", "failed"]
        assert "could not be read" in audit.call_args.kwargs["error"]

    def test_a_malformed_run_record_is_audited_rather_than_raising(self, tmp_path):
        # The record's shape is read inside the same handler as the store read, so a
        # record missing `is_terminal` cannot escape unaudited either.
        sdk = SimpleNamespace(
            start_async=AsyncMock(return_value="run-1"),
            get=mock.Mock(return_value=SimpleNamespace()),
        )
        with ExitStack() as stack:
            _nightly_preconditions(stack, sdk)
            audit = stack.enter_context(mock.patch.object(hooks, "_audit"))
            asyncio.run(hooks._run_once())
        assert [c.args[2] for c in audit.call_args_list] == ["invoked", "failed"]


class TestAttribution:
    """One runner, two triggers, and no upload attributed to a person."""

    def test_the_gate_names_the_job_worker_not_the_owner(self):
        # The property the old owner/scheduler pair protected: an unattended
        # refusal is not recorded against the dashboard owner. The runner cannot
        # know which trigger it serves, so the gate names the actor it can observe
        # -- and names it itself, rather than taking it as an argument no caller
        # varies. Pinned here as the CALL SHAPE: nothing threads a caller through.
        sdk = SimpleNamespace(get=lambda run_id: SimpleNamespace(dedupe_key=ACCOUNT))
        runner = backup.make_job_runner(sdk, KIND)
        with (
            mock.patch.object(
                accounts_mod, "resolve_account_profile_cached", return_value=(PROFILE, REGION)
            ),
            mock.patch.object(backup, "_authorize_upload") as authorize,
            mock.patch(
                "kiro_crew.apps.builtins.aws_control.backend.storage.find_drive",
                return_value=BUCKET,
            ),
            mock.patch.object(backup, "run_snapshot_backup") as work,
        ):
            runner(SimpleNamespace(run_id="run-1"))
        assert authorize.call_args.args == (ACCOUNT, PROFILE, REGION)
        assert "caller" not in authorize.call_args.kwargs
        assert "caller" not in work.call_args.kwargs
        assert "dashboard-owner" not in backup.CALLER_JOB

    def test_the_nightly_record_is_what_names_the_scheduler(self):
        # WHO ASKED moved to the starter, which knows it without a race. If this
        # record stopped naming the scheduler, nothing in SEL would say a run was
        # unattended.
        with mock.patch.object(hooks, "sel") as sel_factory:
            hooks._audit("backup_nightly", "run=abc", "succeeded")
        kwargs = sel_factory.return_value.log_api_access.call_args.kwargs
        assert kwargs["caller"] == "aws-control-nightly"
        assert "abc" in kwargs["resources"]
        assert kwargs["caller"] != backup.CALLER_JOB


@pytest.fixture(autouse=True)
def _reset_account_cache():
    """The account snapshot is module state; no test may inherit a warm one."""
    accounts_mod.invalidate_cache()
    yield
    accounts_mod.invalidate_cache()
