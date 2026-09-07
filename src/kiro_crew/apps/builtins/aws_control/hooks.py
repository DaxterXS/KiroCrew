"""Lifecycle hooks — the nightly backup loop.

One background task, started on enable, that wakes every half hour and claims a
snapshot backup when it is due (nightly toggle on AND >23 h since the last run —
see ``backup.due_for_nightly``). The backup itself runs as a Job SDK run of the
same kind and ``dedupe_key`` the HTTP route uses, so one account cannot pay for
two concurrent uploads and a nightly run is visible on the Backup row like any
other. Every AWS-reaching step keeps the same guards the HTTP path has: consent
fails closed (a silent skip plus a log line, never an unconfirmed charge), and
the drive is tag-discovered per run rather than trusted from memory.

The loop runs against the REGISTRY DEFAULT account only — the same account
the consent card confirms. Multi-account nightly schedules arrive with the
per-account grant store (spec §9).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from kiro_crew import aws_consent
from kiro_crew.apps import job_sdk
from kiro_crew.apps.builtins.aws_control.backend import accounts as accounts_mod
from kiro_crew.apps.builtins.aws_control.backend import backup as backup_mod
from kiro_crew.apps.builtins.aws_control.backend import storage as storage_mod
from kiro_crew.apps.job_sdk import get_sdk as get_job_sdk
from kiro_crew.deploy import profiles as deploy_profiles
from kiro_crew.sel import sel

logger = logging.getLogger(__name__)

_CHECK_INTERVAL_SECS = 30 * 60

#: How often the loop re-reads its own claimed run's record while it is in
#: flight. Short enough that the terminal audit lands near the event, long enough
#: that a multi-minute archive build costs a handful of reads.
_RUN_POLL_SECS = 15

_task: asyncio.Task[None] | None = None


def _audit(operation: str, resources: str, outcome: str, *, error: str = "") -> None:
    """SEL record for an UNATTENDED backup step.

    The HTTP handlers get their audit from the dashboard layer; this loop has no
    request, so without this the only unattended S3 mutation in the app would be
    the one operation with no trail. The Job SDK audits a run's own lifecycle
    (``jobs.job_start``, ``jobs.job_done``) but attributes every run to the app,
    so these records remain the only ones that name the NIGHTLY trigger — they
    carry the run id, which is what joins the two trails. Best-effort by the same
    rule the handlers use: an audit failure must never abort the backup.
    """
    try:
        sel().log_api_access(
            caller="aws-control-nightly",
            operation=f"aws_control.{operation}",
            outcome=outcome,
            source=backup_mod.APP_NAME,
            resources=resources[:200],
            error=error[:200],
        )
    except Exception:
        logger.debug("aws-control nightly SEL audit failed", exc_info=True)


async def _run_once() -> None:
    """One due-check, then hand the backup to a Job SDK run. Failures log.

    The backup itself is NOT performed here. It is claimed through
    ``sdk.start_async(kind, dedupe_key=account)`` — the same kind and the same key
    the HTTP route uses — because the SDK's ``(kind, dedupe_key)`` index is what
    stops one account paying for two concurrent uploads, and an index cannot see a
    caller that does not enter it. Claiming here also makes a nightly run visible
    on ``GET /backup/{account}``, whose ``jobs`` block is read from the SDK's own
    records: before this, the Backup row read idle while a nightly backup was in
    flight.

    What is still decided HERE, before the claim, is unchanged: which account the
    default profile points at, whether that account is due (``due_for_nightly`` --
    nightly toggle on AND >23 h since the last run), and whether S3 consent still
    holds. Those keep the loop from claiming a run it knows will refuse, and keep
    a nightly-disabled account from being asked to spend money. One check is NEW
    and the migration needs it: the run's worker cannot await, so it reads the
    account's profile from a snapshot only the async resolver builds, and nothing
    on this path warmed it.
    """
    resolved = await asyncio.to_thread(deploy_profiles.resolve_profile, "")
    if resolved is None:
        logger.info("aws-control nightly: no registered profile; skipping")
        return
    profile, region = resolved
    # Backup state is keyed per account, so the loop resolves which
    # account the default profile is actually pointing at right now.
    identity = await aws_consent.probe_identity(profile, region)
    if not identity.ok or not identity.account:
        logger.info("aws-control nightly: account unresolved; skipping")
        return
    account = identity.account
    if not await asyncio.to_thread(backup_mod.due_for_nightly, account):
        return
    # WARM THE SNAPSHOT BEFORE CONSENT IS CONFIRMED, deliberately, so that nothing
    # suspends between the confirmation and the calls it authorizes.
    #
    # The run's worker is a thread and cannot await, so it resolves its profile
    # through `accounts.resolve_account_profile_cached`, which serves the WARM
    # snapshot only and returns None past its 300 s TTL. Nothing else on this path
    # warms it -- neither `resolve_profile` nor `probe_identity` does -- and at
    # 03:00 there is no dashboard traffic to have warmed it either, so without this
    # await the worker would resolve None and every unattended run would be
    # recorded `failed` with no upload. `resolve_account_profile_cached` names this
    # pre-flight as the reason it may return None; the HTTP route does it too.
    #
    # ORDER, not the call, is what makes it safe. Awaiting it AFTER `refuse_and_log`
    # left a suspension point between consent being confirmed and `find_drive`
    # acting on it, so consent could be withdrawn while the probe sweep ran. Its own
    # AWS work is an STS `GetCallerIdentity` per profile plus local `aws configure
    # get` reads, the same class as the `probe_identity` above, which this loop
    # already performs before the consent check -- so moving it here adds no
    # pre-consent surface. It also fails the loop closed on an account with no
    # working connection, rather than claiming a run that can only refuse.
    if await accounts_mod.resolve_account_profile(account) is None:
        logger.info("aws-control nightly: no working connection for the account; skipping")
        return
    allowed = await aws_consent.refuse_and_log(
        aws_consent.SERVICE_S3, profile=profile, region=region
    )
    if not allowed:
        return  # refuse_and_log already logged + audited
    sdk = get_job_sdk(backup_mod.APP_NAME)
    if sdk is None:
        # Same gap `_register_job_runners` reports at startup, reached from the
        # other side: without the `jobs` permission there is no run to claim, and
        # doing the upload anyway would put back the untracked path this replaced.
        logger.warning(
            "aws-control nightly: no job runtime; skipping (is the 'jobs' permission declared?)"
        )
        return
    # A due account whose drive does not exist yet is a SILENT skip, as it was
    # before this loop claimed runs. The runner refuses a driveless account by
    # raising, which the SDK records as `failed`, and a failed run never reaches
    # `_record_run` -- so `due_for_nightly` stays True and the account would accrue
    # one more failed record every half hour, forever, for a state that is simply
    # not configured yet.
    #
    # Discovery runs under the profile CONSENT WAS CHECKED FOR just above, not under
    # whichever same-account profile the resolver picked. `find_drive` reaches AWS
    # (tag:GetResources), consent is keyed per (service, profile, region), and
    # `_pick_profile` may return a healthy non-default profile of the same account
    # -- so using its answer here would make an unconsented call in the course of
    # deciding whether to claim. The drive is still re-discovered inside the run,
    # under the run's own authorized profile: this check decides whether to claim at
    # all. It is the first call after consent, with no suspension point between.
    # Discovery is the first call after consent and it can FAIL, not just come back
    # empty: `find_drive` raises on an ordinary AWS error or an ambiguous match.
    # Before this loop claimed runs that raise was caught here and audited `failed`;
    # the migration moved the upload out and took the handler with it, so a
    # discovery failure reached `_loop`'s log-only catch and the one unattended S3
    # path in this app recorded nothing. The handler is back, in the shape it had.
    try:
        bucket = await asyncio.to_thread(storage_mod.find_drive, profile, region, account=account)
    except asyncio.CancelledError:
        _audit("backup_nightly", "backup/snapshots", "cancelled")
        raise
    except Exception as exc:
        _audit("backup_nightly", "backup/snapshots", "failed", error=str(exc))
        logger.warning("aws-control nightly: drive discovery failed", exc_info=True)
        return
    if not bucket:
        logger.info("aws-control nightly: no drive bucket yet; skipping")
        return
    await _claim_and_watch(sdk, backup_mod.KIND_SNAPSHOT, account)


async def _claim_and_watch(sdk: Any, kind: str, account: str) -> None:
    """Claim the run, then follow it to a terminal state.

    The claim is ``start_async``, so if a run of this kind and key is already in
    flight the SDK ADOPTS it and returns its id rather than beginning a second
    paid upload. The loop does NOT try to tell adoption from a fresh claim: only
    ``start``'s own critical section knows that atomically, and nothing here needs
    to know it -- either way the id names the run that is doing this account's
    backup, which is the run to follow and to report.

    Following it to terminal is what keeps the SEL trail this loop has always
    produced: the SDK records the run's own lifecycle but attributes every run to
    the app, so these records stay the only ones naming the nightly trigger, and a
    success with no record would leave the app's one unattended S3 mutation
    reported as invoked and never resolved. It also keeps the loop from re-entering
    while the backup is still uploading, which the direct call gave for free.
    """
    _audit("backup_nightly", "backup/snapshots", "invoked")
    try:
        run_id = await sdk.start_async(kind, dedupe_key=account)
    except asyncio.CancelledError:
        _audit("backup_nightly", "backup/snapshots", "cancelled")
        raise
    except Exception as exc:
        _audit("backup_nightly", "backup/snapshots", "failed", error=str(exc))
        logger.warning("aws-control nightly backup could not be claimed", exc_info=True)
        return
    logger.info("aws-control nightly backup is running as job %s", run_id)
    await _watch_run(sdk, run_id)


def _terminal_outcome(sdk: Any, run_id: str) -> tuple[str, str] | None:
    """Terminal ``(status, error)`` for the run, or None while it is still going.

    Reading the record and classifying it live together so ONE handler covers
    both: a job-store I/O error, an absent record and a record whose shape cannot
    be read are the same thing to the loop -- it cannot say how the run ended.
    Absence raises rather than returning a sentinel, because "no record" is a
    failure to report and a sentinel invites a caller to treat it as "not yet".
    """
    run = sdk.get(run_id)
    if run is None:
        raise RuntimeError("the run record could not be read")
    if not run.is_terminal:
        return None
    return run.status, run.error


async def _watch_run(sdk: Any, run_id: str) -> None:
    """Audit how the claimed run ended. One record, from the run's own status.

    Every exit from here writes a record. A read that raises used to propagate to
    ``_loop``'s log-only catch, which left a claimed nightly run audited ``invoked``
    and never resolved -- an audit that is present exactly when nothing went wrong.
    """
    while True:
        try:
            outcome = await asyncio.to_thread(_terminal_outcome, sdk, run_id)
        except asyncio.CancelledError:
            _audit("backup_nightly", f"run={run_id}", "cancelled")
            raise
        except Exception as exc:
            _audit("backup_nightly", f"run={run_id}", "failed", error=str(exc))
            logger.warning("aws-control nightly: run %s could not be read", run_id, exc_info=True)
            return
        if outcome is not None:
            status, error = outcome
            if status == job_sdk.DONE:
                _audit("backup_nightly", f"run={run_id}", "succeeded")
                logger.info("aws-control nightly backup finished: run %s", run_id)
            else:
                _audit("backup_nightly", f"run={run_id}", status, error=error)
                logger.warning("aws-control nightly backup ended %s: run %s", status, run_id)
            return
        try:
            await asyncio.sleep(_RUN_POLL_SECS)
        except asyncio.CancelledError:
            # Teardown cancels the loop task mid-backup. The worker thread is not
            # killable, so this records that the LOOP stopped watching, which is
            # the same thing the direct call recorded when it was cancelled.
            _audit("backup_nightly", f"run={run_id}", "cancelled")
            raise


async def _loop() -> None:
    while True:
        try:
            await _run_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("aws-control nightly loop error", exc_info=True)
        await asyncio.sleep(_CHECK_INTERVAL_SECS)


async def _register_job_runners(ctx: Any) -> None:
    """Bind the backup kinds to their runners, then resolve any dead run.

    Registration is the SDK's contract: a kind is bound to its callable ONCE, at
    app init, and ``start`` then names only the kind. That is what lets the
    browser and the reconciliation pass address a run without holding a Python
    callable. It happens before the nightly-task guard below because a re-enable
    builds a FRESH ``AppContext`` -- and therefore a fresh ``JobSDK`` with an
    empty runner table -- so skipping it on the "already running" path would
    leave an app whose kinds have no runners.

    ``cancellable`` is left at its default of False. Neither backup runner polls
    ``handle.cancelled``: the only stop signal they honour is the teardown event
    ``_STOP``, checked in ``_authorize_upload``, which is not a cancel checkpoint.
    The SDK cannot verify the assertion, so claiming True here would put a Cancel
    button in front of the owner that does nothing. The UI hides it instead.

    The reconcile call is deliberate and is NOT redundant with the gateway's.
    ``reconcile_all()`` runs once after the WHOLE enable loop, so on the startup
    path there is a window -- every app enabled after this one -- in which
    ``_jobs/active`` would serve a run left behind by a process that is gone. The
    backup UI adopts an in-flight record on mount, so that window is precisely
    when it would show a phantom "running" for work nothing can finish. Calling
    it here shortens the window to this app's own startup, and it is safe to run
    twice: a terminal record is skipped (``job_sdk.py:786``), so the later pass
    finds nothing left to do.
    """
    sdk = getattr(ctx, "job", None)
    if sdk is None:
        # Granted-but-absent is the app's to report, not to assume away: without
        # the `jobs` permission the context carries no SDK, and a backup start
        # would fail at the route with no explanation of why.
        logger.warning(
            "aws-control: no job runtime on the app context; "
            "backups cannot run (is the 'jobs' permission declared?)"
        )
        return
    for kind in backup_mod.JOB_KINDS:
        sdk.register(kind, backup_mod.make_job_runner(sdk, kind))
    try:
        interrupted = await asyncio.to_thread(sdk.reconcile)
    except Exception:  # noqa: BLE001 — a bad run store must not block enable
        logger.warning("aws-control: job reconciliation failed", exc_info=True)
        return
    if interrupted:
        logger.info("aws-control: resolved %d interrupted backup run(s)", interrupted)


async def on_startup(ctx: Any) -> None:
    """Register the backup runners, then start the nightly loop.

    Idempotent across enable/disable cycles.
    """
    global _task
    # Before the guard below: a re-enable brings a new JobSDK that has no runners.
    await _register_job_runners(ctx)
    if _task is not None and not _task.done():
        return
    # Re-enabling clears a stop left by a previous teardown, so an enable/disable
    # /enable cycle does not leave the worker permanently refusing to upload.
    backup_mod.clear_stop()
    _task = asyncio.get_running_loop().create_task(_loop())


async def on_shutdown(ctx: Any) -> None:  # noqa: ARG001 — kept for the hook ABI
    """Stop the loop, and stop a worker that has not begun uploading yet.

    ``_task.cancel()`` alone only unblocks the ``await``: the upload now runs on a
    Job SDK worker thread, and Python cannot kill a thread, so a snapshot already
    streaming to S3 runs to completion regardless of what the hook does. The stop
    EVENT closes the part that is closeable -- the worker
    re-checks authorization immediately before ``put_file``, and that check now
    also refuses once teardown has been signalled, so a backup still building its
    archive when the owner disables the app never starts its upload.

    The residual is one in-flight object: an ``aws s3 cp`` already mid-stream
    finishes, into the owner's own bucket, and the SEL record above says it did.
    Revoking that would mean tracking and terminating the CLI subprocess itself,
    which is the same containment work tracked in #5430.
    """
    global _task
    backup_mod.signal_stop()
    if _task is not None:
        _task.cancel()
        _task = None
