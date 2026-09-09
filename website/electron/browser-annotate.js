"use strict";

// Annotate capture for the native Browser panel.
//
// A HUMAN action, not an agent op: the user clicks "Annotate" in the panel,
// gets a screenshot of the page they are looking at, and draws on it. So this
// deliberately does NOT go through the agent control plane (browser-control.js)
// or the CDP wire ops (browser-ops.js `screenshot`/`snapshot`):
//
//   • `webContents.capturePage()` needs no debugger attachment, so it cannot
//     compete with -- or require -- the single agent owner of the CDP session.
//     Browser Mode being OFF must not stop a user from annotating their own
//     page.
//   • The element outline is taken by running the SAME walker the agent's
//     `snapshot` op injects, in the same main world. Refs are minted once per
//     element (`el.__kcRef`) and reused, so the `eN` a mark is mapped to here
//     is the `eN` the agent will see on its next snapshot and can pass to
//     `click`. Only the walker's per-node `rect`/`selector` fields are consumed
//     here; the agent's outline text ignores them.
//
// Pure helpers are exported for unit tests; `captureForAnnotation` takes the
// WebContents through a small deps object so it is testable without Electron.

const { WALKER_SOURCE } = require("./browser-ops");

/** Upper bound on one capture step -- a hidden view can leave capturePage
 *  unsettled, and the click handler must not hang the panel. */
const CAPTURE_TIMEOUT_MS = 8000;

/** Page-side probe for the CSS viewport size and device pixel ratio. */
const VIEWPORT_SOURCE =
  "({ width: window.innerWidth, height: window.innerHeight, dpr: window.devicePixelRatio || 1 })";

function withTimeout(promise, ms, label) {
  return new Promise((resolve, reject) => {
    let settled = false;
    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      const err = new Error(`${label} timed out after ${ms}ms`);
      err.code = "capture_timeout";
      reject(err);
    }, ms);
    Promise.resolve(promise).then(
      (v) => { if (!settled) { settled = true; clearTimeout(timer); resolve(v); } },
      (e) => { if (!settled) { settled = true; clearTimeout(timer); reject(e); } },
    );
  });
}

/** A finite, non-negative number or `null`. */
function num(v) {
  return typeof v === "number" && Number.isFinite(v) && v >= 0 ? v : null;
}

/**
 * Reduce raw walker nodes to the annotation element list: interactive nodes
 * only (they carry a ref), with a well-formed rect. Structural lines
 * (headings) and anything the walker could not measure are dropped -- a mark
 * can only be mapped to something the agent can act on.
 */
function elementsFromNodes(nodes) {
  if (!Array.isArray(nodes)) return [];
  const out = [];
  for (const n of nodes) {
    if (!n || typeof n.ref !== "string" || !n.rect) continue;
    const x = num(n.rect.x);
    const y = num(n.rect.y);
    const width = num(n.rect.width);
    const height = num(n.rect.height);
    if (x === null || y === null || width === null || height === null) continue;
    if (width === 0 && height === 0) continue;
    out.push({
      ref: n.ref,
      role: typeof n.role === "string" && n.role ? n.role : "generic",
      name: typeof n.name === "string" ? n.name : "",
      selector: typeof n.selector === "string" ? n.selector : "",
      rect: { x, y, width, height },
    });
  }
  return out;
}

/**
 * Capture the page for annotation: a PNG of the viewport plus the interactive
 * elements with their CSS-px rects. Resolves `{ ok:false, code, error }` for
 * answered failures (no view, hidden view, walker error) and never throws for
 * those, so the renderer can show one message instead of an unhandled
 * rejection in the click handler.
 *
 * `deps`: `{ webContents }` -- an Electron WebContents (or a test double with
 * `capturePage()` and `executeJavaScript()`).
 */
async function captureForAnnotation(deps) {
  const wc = deps && deps.webContents;
  if (!wc || typeof wc.capturePage !== "function" || typeof wc.executeJavaScript !== "function") {
    return { ok: false, code: "no_view", error: "no native browser view to capture" };
  }
  if (typeof wc.isDestroyed === "function" && wc.isDestroyed()) {
    return { ok: false, code: "no_view", error: "the browser view is gone" };
  }
  try {
    const viewport = await withTimeout(wc.executeJavaScript(VIEWPORT_SOURCE, true), CAPTURE_TIMEOUT_MS, "viewport probe");
    const image = await withTimeout(wc.capturePage(), CAPTURE_TIMEOUT_MS, "capturePage");
    if (!image || typeof image.toPNG !== "function") {
      return { ok: false, code: "capture_failed", error: "capturePage returned no image" };
    }
    const size = typeof image.getSize === "function" ? image.getSize() : { width: 0, height: 0 };
    if (!size.width || !size.height) {
      // A hidden or not-yet-painted view yields an empty image; say so rather
      // than opening an editor on a blank canvas.
      return { ok: false, code: "capture_empty", error: "the page has not painted yet -- try again" };
    }
    const walked = await withTimeout(wc.executeJavaScript(WALKER_SOURCE, true), CAPTURE_TIMEOUT_MS, "element walk");
    const cssWidth = num(viewport && viewport.width) || size.width;
    const cssHeight = num(viewport && viewport.height) || size.height;
    return {
      ok: true,
      png: image.toPNG().toString("base64"),
      // Pixel size of the PNG; CSS size of the viewport it shows. The renderer
      // lays the image out at CSS size so element rects (CSS px) line up.
      width: size.width,
      height: size.height,
      cssWidth,
      cssHeight,
      dpr: num(viewport && viewport.dpr) || size.width / cssWidth,
      url: walked && typeof walked.url === "string" ? walked.url : "",
      title: walked && typeof walked.title === "string" ? walked.title : "",
      elements: elementsFromNodes(walked && walked.nodes),
      walkerError: walked && walked.error ? String(walked.error) : undefined,
    };
  } catch (e) {
    const code = e && e.code === "capture_timeout" ? "capture_timeout" : "capture_failed";
    return { ok: false, code, error: String((e && e.message) || e) };
  }
}

module.exports = {
  CAPTURE_TIMEOUT_MS,
  VIEWPORT_SOURCE,
  elementsFromNodes,
  captureForAnnotation,
};
