// FRESHNESS contract: an install always applies the NEWEST build, never a
// download the feed has moved past.
//
// The field bug this file pins. Discovery downloads eagerly (auto-download is on
// by default) and then waits — for a click, or for the next natural quit. The
// only thing that noticed a newer release in that window was the 4-hourly poll,
// so an install that landed between two polls applied the stale stage: the app
// relaunched on an already-superseded build, the very next check found the newer
// one, and the whole ~350MB transfer ran again. Two downloads and two restarts
// to reach a version one download could have reached.
//
// The deferred-install-on-quit path was the worst case: "Later" arms a
// before-quit handler that consulted nothing but its own `updateReady` flag, so
// a quit hours after the download installed whatever had been staged back then.
//
// Both install entry points now re-consult the feed as their last step, and both
// must FAIL OPEN — a feed that cannot answer must never make already-downloaded
// bytes uninstallable.
const { test } = require("node:test");
const assert = require("node:assert");

const { initAutoUpdate } = require("../auto-update");

/** Let queued microtasks + the async install/quit bodies run to completion. */
async function flush(times = 8) {
  for (let i = 0; i < times; i += 1) {
    await new Promise((resolve) => setImmediate(resolve));
  }
}

function makeHarness({ appVersion = "1.0.0", autoDownload = true } = {}) {
  const calls = {
    quitAndInstall: [],
    notifications: [],
    states: [],
    checks: 0,
    downloads: 0,
    quits: 0,
    stops: 0,
    // onInstallFailed is the host's gateway recovery: it respawns the gateway
    // child, so it must never fire while a bundle swap is in progress.
    installFailures: 0,
  };
  const handlers = {};
  const quitHandlers = [];
  // What the NEXT checkForUpdates() does — the seam that lets a test say "the
  // feed has moved on" / "the release was retracted" / "the feed is down".
  let onCheck = null;

  const autoUpdater = {
    setFeedURL: () => {},
    checkForUpdates: async () => {
      calls.checks += 1;
      if (onCheck) await onCheck();
    },
    downloadUpdate: async () => { calls.downloads += 1; },
    quitAndInstall: (...a) => calls.quitAndInstall.push(a),
    on: (ev, fn) => { handlers[ev] = fn; },
  };

  const deps = {
    app: {
      isPackaged: true,
      getVersion: () => appVersion,
      once: (ev, fn) => { if (ev === "before-quit") quitHandlers.push(fn); },
      removeListener: (ev, fn) => {
        const i = quitHandlers.indexOf(fn);
        if (i >= 0) quitHandlers.splice(i, 1);
      },
      quit: () => { calls.quits += 1; },
      exit: () => {},
      relaunch: () => {},
    },
    autoUpdater,
    dialog: { showMessageBox: async () => ({ response: 1 }) },
    Notification: function (options) {
      calls.notifications.push(options);
      return { show: () => {} };
    },
    getFlavor: () => "stable",
    getAutoDownloadPreference: () => autoDownload,
    stopGateway: async () => { calls.stops += 1; },
    onInstallFailed: () => { calls.installFailures += 1; },
    osPlatform: "darwin",
    osArch: "arm64",
    feedBase: "https://cdn.example.dev/feed",
    onUpdateState: (payload) => calls.states.push(payload),
    nativeAutoUpdater: { once: () => {} },
    log: { info: () => {}, warn: () => {}, error: () => {} },
  };

  const emit = (ev, payload) => handlers[ev] && handlers[ev](payload);
  return {
    deps,
    calls,
    emit,
    /** The feed answers this on the next check. */
    feedServes: (version) => { onCheck = () => emit("update-available", { version }); },
    feedSaysUpToDate: () => { onCheck = () => emit("update-not-available", {}); },
    feedFails: (err) => { onCheck = () => { throw err; }; },
    feedSilent: () => { onCheck = null; },
    /**
     * A check that hangs until the test lands it — the seam for an ABANDONED
     * check, where the freshness gate's bounded wait expires but the request
     * itself is still running and reports back afterwards.
     */
    feedDeferred: () => {
      let settle = null;
      autoUpdater.checkForUpdates = () => {
        calls.checks += 1;
        return new Promise((resolve, reject) => { settle = { resolve, reject }; });
      };
      const land = (fn) => { fn(); settle.resolve(); };
      return {
        serves: (version) => land(() => emit("update-available", { version })),
        upToDate: () => land(() => emit("update-not-available", {})),
        fails: (err) => { emit("error", err); settle.reject(err); },
      };
    },
    /** Fire the before-quit handler armed by a deferred install. */
    fireQuit: () => {
      const prevented = { value: false };
      const handler = quitHandlers[quitHandlers.length - 1];
      assert.ok(handler, "no before-quit handler was armed");
      handler({ preventDefault: () => { prevented.value = true; } });
      return prevented;
    },
    armedQuitHandlers: () => quitHandlers.length,
  };
}

// --------------------------------------------------------------------------
// Manual install (the About panel's "Install Update & Restart App")
// --------------------------------------------------------------------------

test("a SUPERSEDED stage is not installed — the newest build is fetched instead", async () => {
  const h = makeHarness();
  const u = initAutoUpdate(h.deps);
  h.emit("update-downloaded", { version: "1.1.0" });

  h.feedServes("1.2.0"); // published while the user sat on the ready card
  await u.install();

  assert.strictEqual(
    h.calls.quitAndInstall.length,
    0,
    "installed the stale 1.1.0 — this is the field bug: the app relaunches on a superseded build and re-downloads 1.2.0",
  );
  assert.strictEqual(h.calls.checks, 1, "the install must ask the feed whether the stage is still latest");
  assert.strictEqual(h.calls.downloads, 1, "the newest build must be pursued, not just refused");
  assert.strictEqual(h.calls.stops, 0, "nothing was installed, so the gateway must not have been stopped");
  const found = h.calls.states.filter((s) => s.state === "found").map((s) => s.version);
  assert.deepStrictEqual(found, ["1.2.0"], "the renderer must be told about the newer version");
});

test("a stage that is STILL the newest installs — the gate must not break the normal path", async () => {
  const h = makeHarness();
  const u = initAutoUpdate(h.deps);
  h.emit("update-downloaded", { version: "1.1.0" });

  h.feedServes("1.1.0"); // nothing new since the download
  await u.install();

  assert.strictEqual(h.calls.quitAndInstall.length, 1);
  assert.strictEqual(h.calls.stops, 1, "the gateway must still be stopped before the swap");
  assert.strictEqual(h.calls.downloads, 0, "an already-staged build must never be re-downloaded");
});

test("a RETRACTED stage is not installed", async () => {
  // The feed repointed to the running version: the same signal the poll's
  // retraction path handles, now reachable at install time too.
  const h = makeHarness();
  const u = initAutoUpdate(h.deps);
  h.emit("update-downloaded", { version: "1.1.0" });

  h.feedSaysUpToDate();
  await u.install();

  assert.strictEqual(h.calls.quitAndInstall.length, 0, "a withdrawn build must not install");
  assert.ok(
    h.calls.states.some((s) => s.state === "not-available"),
    "the renderer must be told the update went away",
  );
});

test("FAIL OPEN: an unreachable feed still installs the staged build", async () => {
  const h = makeHarness();
  const u = initAutoUpdate(h.deps);
  h.emit("update-downloaded", { version: "1.1.0" });

  h.feedFails(Object.assign(new Error("getaddrinfo ENOTFOUND"), { code: "ENOTFOUND" }));
  await u.install();

  assert.strictEqual(
    h.calls.quitAndInstall.length,
    1,
    "bytes the user already downloaded must not become uninstallable because the network went away",
  );
});

test("FAIL OPEN: a feed that answers nothing still installs the staged build", async () => {
  // electron-updater resolving checkForUpdates() without emitting either
  // verdict is the shape every other test harness in this directory uses, so
  // the gate must read it as "no evidence", not as "the stage is gone".
  const h = makeHarness();
  const u = initAutoUpdate(h.deps);
  h.emit("update-downloaded", { version: "1.1.0" });

  h.feedSilent();
  await u.install();

  assert.strictEqual(h.calls.quitAndInstall.length, 1);
});

test("FAIL OPEN: a feed that never answers does not leave the install button dead", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "setInterval"] });
  const h = makeHarness();
  h.deps.autoUpdater.checkForUpdates = () => new Promise(() => {}); // hangs forever
  const u = initAutoUpdate(h.deps);
  h.emit("update-downloaded", { version: "1.1.0" });

  const installPromise = u.install();
  await flush();
  assert.strictEqual(h.calls.quitAndInstall.length, 0, "the install must await the freshness answer first");
  t.mock.timers.tick(8 * 1000); // the bound elapses
  await installPromise;

  assert.strictEqual(
    h.calls.quitAndInstall.length,
    1,
    "a click must never wait on a socket forever — an unanswerable feed falls through to the staged build",
  );
});

test("a second click during the freshness check does not dispatch a second install", async () => {
  // The gate awaits the network BEFORE `installing` is set, so `installing`
  // alone no longer guards re-entry.
  const h = makeHarness();
  const u = initAutoUpdate(h.deps);
  h.emit("update-downloaded", { version: "1.1.0" });

  h.feedServes("1.1.0");
  await Promise.all([u.install(), u.install()]);

  assert.strictEqual(h.calls.quitAndInstall.length, 1);
  assert.strictEqual(h.calls.checks, 1, "the second click must not start a second check either");
});

// --------------------------------------------------------------------------
// The consent click (auto-download off): don't spend the bytes on a stale card
// --------------------------------------------------------------------------

test("a click on a stale 'found' card downloads the NEWEST build, not the one on the card", async () => {
  // With auto-download off the card waits for a click that can come hours
  // later. Fetching what it says wastes the whole transfer: the pre-install gate
  // then refuses the stale stage and fetches the newer build anyway.
  const h = makeHarness({ autoDownload: false });
  const u = initAutoUpdate(h.deps);
  h.emit("update-available", { version: "1.1.0" }); // the card the user is looking at

  h.feedServes("1.2.0"); // published while it sat there
  await u.download();

  assert.strictEqual(h.calls.checks, 1, "a click must confirm the card before spending the bytes");
  assert.strictEqual(h.calls.downloads, 1, "the newest build must still be downloaded");
  const downloading = h.calls.states.filter((s) => s.state === "downloading").map((s) => s.version);
  assert.strictEqual(downloading.at(-1), "1.2.0", "downloaded the stale 1.1.0 — one wasted transfer");
});

test("a click moments after a check does not pay a second round trip", async () => {
  const h = makeHarness({ autoDownload: false });
  const u = initAutoUpdate(h.deps);

  h.feedServes("1.1.0");
  await u.check();
  await u.download();

  assert.strictEqual(h.calls.checks, 1, "the feed had just answered");
  assert.strictEqual(h.calls.downloads, 1);
});

test("a click whose re-check finds the release retracted downloads nothing", async () => {
  const h = makeHarness({ autoDownload: false });
  const u = initAutoUpdate(h.deps);
  h.emit("update-available", { version: "1.1.0" });

  h.feedSaysUpToDate();
  await u.download();

  assert.strictEqual(h.calls.downloads, 0, "a withdrawn build must not be fetched");
});

test("two fast clicks fetch once", async () => {
  const h = makeHarness({ autoDownload: false });
  const u = initAutoUpdate(h.deps);
  h.emit("update-available", { version: "1.1.0" });

  h.feedServes("1.1.0");
  await Promise.all([u.download(), u.download()]);

  assert.strictEqual(h.calls.downloads, 1);
  assert.strictEqual(h.calls.checks, 1, "the second click must not start a second check either");
});

test("the automatic download inside a check does not re-check", async () => {
  // The automatic caller runs from the update-available handler, i.e. INSIDE a
  // check: its discovery cannot be stale, and re-checking there would recurse.
  const h = makeHarness({ autoDownload: true });
  initAutoUpdate(h.deps);

  h.emit("update-available", { version: "1.1.0" });
  await flush();

  assert.strictEqual(h.calls.checks, 0);
  assert.strictEqual(h.calls.downloads, 1);
});

test("a stale click with auto-download ON still fetches exactly once", async () => {
  // The click's re-check surfaces the newer build, whose handler starts the
  // automatic download; the click must then stand down rather than fetch again.
  const h = makeHarness({ autoDownload: true });
  const u = initAutoUpdate(h.deps);
  h.emit("update-available", { version: "1.1.0" });
  await flush();
  assert.strictEqual(h.calls.downloads, 1, "the automatic download runs on discovery");
  h.emit("error", new Error("download failed")); // clears `downloading`, card stays

  h.feedServes("1.2.0");
  await u.download();

  assert.strictEqual(h.calls.downloads, 2, "exactly one further fetch, for the newest build");
});

// --------------------------------------------------------------------------
// Reuse of a check that just happened
// --------------------------------------------------------------------------

test("a check that settled moments ago is reused — the click pays no second round trip", async () => {
  const h = makeHarness();
  const u = initAutoUpdate(h.deps);

  h.feedServes("1.1.0");
  await u.check();
  h.emit("update-downloaded", { version: "1.1.0" });
  await u.install();

  assert.strictEqual(h.calls.checks, 1, "the feed had just answered; asking again only delays the install");
  assert.strictEqual(h.calls.quitAndInstall.length, 1);
});

test("the reuse window cannot resurrect a stage the recent check already dropped", async () => {
  // Reuse says "the stage survived that check", so it must be unreachable when
  // the check discarded the stage -- the guard above it reads the live state.
  const h = makeHarness();
  const u = initAutoUpdate(h.deps);
  h.emit("update-downloaded", { version: "1.1.0" });

  h.feedServes("1.2.0");
  await u.check(); // supersede: the stage is dropped, the newer build pursued
  await u.install(); // clicked on a card the check has already replaced

  assert.strictEqual(h.calls.quitAndInstall.length, 0, "the superseded build must not install");
});

test("a stage last checked longer ago than the reuse window is re-verified", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "setInterval", "Date"] });
  const h = makeHarness();
  const u = initAutoUpdate(h.deps);
  h.feedSilent();
  t.mock.timers.tick(30 * 1000); // the launch check settles, stamping the clock
  await flush();
  h.emit("update-downloaded", { version: "1.1.0" });

  t.mock.timers.tick(61 * 1000); // that answer is no longer current enough
  h.feedServes("1.2.0");
  await u.install();

  assert.strictEqual(h.calls.checks, 2, "a stale stamp must not stand in for a check");
  assert.strictEqual(h.calls.quitAndInstall.length, 0, "the superseded stage must not install");
});

// --------------------------------------------------------------------------
// Deferred install on the natural quit (the "Later" path)
// --------------------------------------------------------------------------

test("install-on-quit refuses a stage the feed has moved past, and quits", async () => {
  const h = makeHarness();
  initAutoUpdate(h.deps);
  h.emit("update-downloaded", { version: "1.1.0" }); // arms before-quit

  h.feedServes("1.2.0");
  const prevented = h.fireQuit();
  await flush();

  assert.ok(prevented.value, "the handler must take the quit over to run its own teardown");
  assert.strictEqual(
    h.calls.quitAndInstall.length,
    0,
    "installed the stale build on quit — the exact path that then re-downloads the newer one on relaunch",
  );
  assert.strictEqual(h.calls.stops, 0, "the gateway must not be stopped for an install that will not happen");
  assert.strictEqual(h.calls.quits, 1, "the user asked to quit; honour it");
  assert.match(
    h.calls.notifications.at(-1).body,
    /withdrawn or superseded/i,
    "a promised update that did not land must be explained, or the old version at next launch reads as a failure",
  );
});

test("the quit-time refusal does not claim a newer version for a RETRACTED build", async () => {
  // Both refusals arrive through the same "superseded" answer -- a retraction
  // clears the stage too -- so copy that announces a newer release would be a
  // false statement of fact on this half, and the user would wait for an offer
  // that never comes.
  const h = makeHarness();
  initAutoUpdate(h.deps);
  h.emit("update-downloaded", { version: "1.1.0" });

  h.feedSaysUpToDate();
  h.fireQuit();
  await flush();

  assert.strictEqual(h.calls.quitAndInstall.length, 0, "a withdrawn build must not install");
  assert.strictEqual(h.calls.quits, 1);
  assert.doesNotMatch(h.calls.notifications.at(-1).body, /newer version has been published/i);
  assert.match(h.calls.notifications.at(-1).body, /withdrawn or superseded/i);
});

test("install-on-quit does not start a download it cannot finish", async () => {
  // Discovering 1.2.0 seconds before the process exits must not begin a ~350MB
  // fetch: the exit kills it, and the next launch re-finds and downloads it.
  const h = makeHarness();
  initAutoUpdate(h.deps);
  h.emit("update-downloaded", { version: "1.1.0" });

  h.feedServes("1.2.0");
  h.fireQuit();
  await flush();

  assert.strictEqual(h.calls.downloads, 0);
});

test("install-on-quit still installs when the stage is the newest", async () => {
  const h = makeHarness();
  initAutoUpdate(h.deps);
  h.emit("update-downloaded", { version: "1.1.0" });

  h.feedServes("1.1.0");
  h.fireQuit();
  await flush();

  assert.strictEqual(h.calls.quitAndInstall.length, 1);
  assert.strictEqual(h.calls.stops, 1, "the gateway must stop before the bundle swap");
  assert.strictEqual(h.calls.quits, 0, "quitAndInstall owns the exit on this path");
});

test("FAIL OPEN on quit: a feed that never answers must not hold the app open", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "setInterval"] });
  const h = makeHarness();
  h.deps.autoUpdater.checkForUpdates = () => new Promise(() => {}); // hangs forever
  initAutoUpdate(h.deps);
  h.emit("update-downloaded", { version: "1.1.0" });

  h.fireQuit();
  await flush();
  assert.strictEqual(h.calls.quitAndInstall.length, 0, "the quit path must await the freshness answer first");
  t.mock.timers.tick(8 * 1000); // the bound elapses
  await flush();

  assert.strictEqual(
    h.calls.quitAndInstall.length,
    1,
    "the quit took over the exit; a hanging feed must not strand the app between quitting and installing",
  );
});

test("FAIL OPEN on quit: an unreachable feed still installs the staged build", async () => {
  const h = makeHarness();
  initAutoUpdate(h.deps);
  h.emit("update-downloaded", { version: "1.1.0" });

  h.feedFails(Object.assign(new Error("socket hang up"), { code: "ECONNRESET" }));
  h.fireQuit();
  await flush();

  assert.strictEqual(h.calls.quitAndInstall.length, 1);
});

// --------------------------------------------------------------------------
// The ABANDONED check: fail-open's own side effect
//
// The bound the gate puts on the feed ends the WAIT, not the request. Fail-open
// then sends that caller straight on to install, so the request's outcome can
// land AFTER the install is dispatched — the one thing the post-stopGateway
// abort exists to stop. Aborting cannot be the answer (aborting is what
// fail-open refuses to do), so the late outcome must be inert instead.
// --------------------------------------------------------------------------

test("an abandoned check FAILING after the dispatch must not fire the gateway recovery", async (t) => {
  // Recovery respawns the gateway child. Firing it here would put a live gateway
  // in the middle of the bundle swap — exactly what the strict stop-then-install
  // order exists to prevent — and tell the user the install failed while it runs.
  t.mock.timers.enable({ apis: ["setTimeout", "setInterval"] });
  const h = makeHarness();
  const feed = h.feedDeferred();
  const u = initAutoUpdate(h.deps);
  h.emit("update-downloaded", { version: "1.1.0" });

  const installPromise = u.install();
  await flush();
  t.mock.timers.tick(8 * 1000); // the WAIT ends; the request is still running
  await installPromise;
  assert.strictEqual(h.calls.quitAndInstall.length, 1, "fail-open must have installed the staged build");

  feed.fails(Object.assign(new Error("ETIMEDOUT"), { code: "ETIMEDOUT" }));
  await flush();
  // The suppression is DEFERRED by a macrotask (it has to ask whether the error
  // was the abandoned request's own — see the error handler), so drive the clock
  // or this test would pass because the decision never ran.
  t.mock.timers.tick(1);
  await flush();

  assert.strictEqual(h.calls.installFailures, 0, "the gateway must not be respawned during the swap");
  assert.ok(
    !h.calls.states.some((s) => s.state === "error"),
    "an install that is proceeding must not be reported as failed",
  );
  assert.strictEqual(h.calls.quitAndInstall.length, 1, "and no second dispatch");
});

test("a GENUINE install failure inside the abandoned window is still reported", async (t) => {
  // The twin of the test above, and the reason the suppression cannot be a bare
  // flag test. `error` is the one event both the check and the installer are
  // funnelled through, and the window is wide: the request was abandoned BECAUSE
  // it gave no answer in 8s, so a hung socket holds it open for the OS TCP
  // timeout while the install handoff it released takes about a second. Squirrel
  // rejecting the bundle in there must still reach the host — the gateway was
  // stopped on purpose and only onInstallFailed brings it back, or the app
  // survives with a dead dashboard and the renderer sits on the installing
  // overlay forever.
  t.mock.timers.enable({ apis: ["setTimeout", "setInterval"] });
  const h = makeHarness();
  h.feedDeferred(); // deliberately never landed: the request is still hanging
  const u = initAutoUpdate(h.deps);
  h.emit("update-downloaded", { version: "1.1.0" });

  const installPromise = u.install();
  await flush();
  t.mock.timers.tick(8 * 1000); // the WAIT ends; the request is still running
  await installPromise;
  assert.strictEqual(h.calls.quitAndInstall.length, 1, "fail-open must have installed the staged build");

  // Not the feed's error — the installer's, arriving while the abandoned request
  // is still outstanding.
  h.emit("error", Object.assign(new Error("Could not get code signature for running application"), { code: "ERR_UPDATER_INVALID_SIGNATURE" }));
  await flush();
  t.mock.timers.tick(1);
  await flush();

  assert.strictEqual(h.calls.installFailures, 1, "the deliberately-stopped gateway must be restored");
  const failure = h.calls.states.filter((s) => s.state === "error").at(-1);
  assert.ok(failure, "the renderer must be told the install failed, not left on the overlay");
  assert.strictEqual(failure.phase, "install", "and it must be attributed to the install, not the check");
});

test("an abandoned check finding a NEWER build after the dispatch changes nothing", async (t) => {
  // Two hazards in one event: dropping the stage would invalidate a dispatch that
  // has already passed every guard, and the automatic download would spend ~350MB
  // as the process exits. The next launch finds this version and offers it then.
  t.mock.timers.enable({ apis: ["setTimeout", "setInterval"] });
  const h = makeHarness({ autoDownload: true });
  const feed = h.feedDeferred();
  const u = initAutoUpdate(h.deps);
  h.emit("update-downloaded", { version: "1.1.0" });

  const installPromise = u.install();
  await flush();
  t.mock.timers.tick(8 * 1000);
  await installPromise;
  assert.strictEqual(h.calls.quitAndInstall.length, 1);

  feed.serves("1.2.0");
  await flush();

  assert.strictEqual(h.calls.downloads, 0, "no fetch may start while the bundle is being swapped");
  assert.ok(!h.calls.states.some((s) => s.state === "found"), "and no card may replace the running install");
});

test("an abandoned check reporting UP TO DATE after the dispatch does not pull the stage", async (t) => {
  // update-not-available clears `updateReady` and the staged version — the
  // retraction path. Landing that mid-swap would strip the bytes from an install
  // already under way.
  t.mock.timers.enable({ apis: ["setTimeout", "setInterval"] });
  const h = makeHarness();
  const feed = h.feedDeferred();
  const u = initAutoUpdate(h.deps);
  h.emit("update-downloaded", { version: "1.1.0" });

  const installPromise = u.install();
  await flush();
  t.mock.timers.tick(8 * 1000);
  await installPromise;

  feed.upToDate();
  await flush();

  assert.ok(
    !h.calls.states.some((s) => s.state === "not-available"),
    "the renderer must not be told the update went away while it is installing",
  );
  assert.strictEqual(h.calls.quitAndInstall.length, 1);
});

test("FAIL OPEN on quit: an abandoned check's late discovery does not fetch as the app exits", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "setInterval"] });
  const h = makeHarness({ autoDownload: true });
  const feed = h.feedDeferred();
  initAutoUpdate(h.deps);
  h.emit("update-downloaded", { version: "1.1.0" });

  h.fireQuit();
  await flush();
  t.mock.timers.tick(8 * 1000);
  await flush();
  assert.strictEqual(h.calls.quitAndInstall.length, 1, "the quit took over the exit; it must still install");

  feed.serves("1.2.0");
  await flush();

  assert.strictEqual(h.calls.downloads, 0);
  assert.strictEqual(h.calls.quits, 0, "quitAndInstall owns the exit on this path");
});

test("a check that is GENUINELY in flight still aborts the install after the gateway stops", async () => {
  // The relaxation above is scoped to the abandoned case. An ordinary concurrent
  // check has made no fail-open promise, and its outcome can still invalidate the
  // stage or be misread as an install failure, so the dispatch must still be the
  // serialization point — abort, restore the gateway, and say so.
  const h = makeHarness();
  const feed = h.feedDeferred();
  const u = initAutoUpdate(h.deps);
  h.emit("update-downloaded", { version: "1.1.0" });

  const checkPromise = u.check(); // hangs, holding `checking`
  await flush();
  await u.install();

  assert.strictEqual(h.calls.quitAndInstall.length, 0, "the install must not race a live check");
  assert.strictEqual(h.calls.stops, 1, "the gateway was stopped for a dispatch that then aborted…");
  assert.strictEqual(h.calls.installFailures, 1, "…so the host must be told to bring it back");
  const failure = h.calls.states.filter((s) => s.state === "error").at(-1);
  assert.strictEqual(failure.phase, "install");
  assert.strictEqual(failure.code, "check-in-flight");

  feed.upToDate(); // let the check land so nothing is left pending
  await checkPromise;
});
