const assert = require("node:assert");
const {
  VIEWPORT_SOURCE,
  elementsFromNodes,
  captureForAnnotation,
} = require("../browser-annotate");
const { WALKER_SOURCE, formatOutline } = require("../browser-ops");

// ── walker contract ──

test("walker: interactive nodes carry rect + selector; the agent outline ignores both", () => {
  // The Annotate flow reads `rect`/`selector` off the walker's nodes. They must
  // be emitted for interactive nodes only (headings stay ref-less lines), and
  // `formatOutline` must NOT surface them -- the agent's snapshot text is a
  // separate contract that this feature does not change.
  assert.ok(WALKER_SOURCE.includes("rect: rectOf(el)"), "interactive nodes emit rect");
  assert.ok(WALKER_SOURCE.includes("selector: selectorOf(el)"), "interactive nodes emit selector");
  assert.ok(WALKER_SOURCE.includes('out.push({ depth: depth, role: "heading", name: name });'), "headings stay bare");
  const line = formatOutline([
    { depth: 0, role: "button", name: "Save", ref: "e1", rect: { x: 1, y: 2, width: 3, height: 4 }, selector: "#save" },
  ]);
  assert.strictEqual(line, '- button "Save" [ref=e1]');
});

// ── elementsFromNodes ──

test("elementsFromNodes: keeps ref'd nodes with a measurable rect, drops the rest", () => {
  const out = elementsFromNodes([
    { depth: 0, role: "heading", name: "Title" },                                           // no ref
    { depth: 1, role: "button", name: "Save", ref: "e1", rect: { x: 10, y: 20, width: 30, height: 40 }, selector: "#save" },
    { depth: 1, role: "link", name: "Zero", ref: "e2", rect: { x: 0, y: 0, width: 0, height: 0 } },  // unmeasurable
    { depth: 1, role: "link", name: "NaN", ref: "e3", rect: { x: NaN, y: 0, width: 1, height: 1 } },
    { depth: 1, role: "", name: 7, ref: "e4", rect: { x: 1, y: 1, width: 1, height: 1 } },        // odd types
  ]);
  assert.deepStrictEqual(out, [
    { ref: "e1", role: "button", name: "Save", selector: "#save", rect: { x: 10, y: 20, width: 30, height: 40 } },
    { ref: "e4", role: "generic", name: "", selector: "", rect: { x: 1, y: 1, width: 1, height: 1 } },
  ]);
  assert.deepStrictEqual(elementsFromNodes(null), []);
  assert.deepStrictEqual(elementsFromNodes("nope"), []);
});

// ── captureForAnnotation ──

function fakeContents({ viewport, size, nodes, destroyed = false, captureHangs = false, walkerThrows = false } = {}) {
  const calls = [];
  return {
    calls,
    isDestroyed: () => destroyed,
    async executeJavaScript(src) {
      calls.push(["exec", src === VIEWPORT_SOURCE ? "viewport" : src === WALKER_SOURCE ? "walker" : "other"]);
      if (src === VIEWPORT_SOURCE) return viewport || { width: 1000, height: 700, dpr: 2 };
      if (src === WALKER_SOURCE) {
        if (walkerThrows) throw new Error("walker exploded");
        return { url: "https://example.test/p", title: "Example", nodes: nodes || [] };
      }
      throw new Error(`unexpected script: ${src}`);
    },
    capturePage() {
      calls.push(["capture"]);
      if (captureHangs) return new Promise(() => {});
      const s = size || { width: 2000, height: 1400 };
      return Promise.resolve({
        getSize: () => s,
        toPNG: () => Buffer.from("png-bytes"),
      });
    },
  };
}

test("captureForAnnotation: returns the PNG, both sizes, dpr, page meta and mapped elements", async () => {
  const wc = fakeContents({
    nodes: [{ depth: 0, role: "button", name: "Go", ref: "e1", rect: { x: 1, y: 2, width: 3, height: 4 }, selector: "#go" }],
  });
  const res = await captureForAnnotation({ webContents: wc });
  assert.strictEqual(res.ok, true);
  assert.strictEqual(res.png, Buffer.from("png-bytes").toString("base64"));
  assert.strictEqual(res.width, 2000);
  assert.strictEqual(res.height, 1400);
  assert.strictEqual(res.cssWidth, 1000);
  assert.strictEqual(res.cssHeight, 700);
  assert.strictEqual(res.dpr, 2);
  assert.strictEqual(res.url, "https://example.test/p");
  assert.strictEqual(res.title, "Example");
  assert.deepStrictEqual(res.elements, [
    { ref: "e1", role: "button", name: "Go", selector: "#go", rect: { x: 1, y: 2, width: 3, height: 4 } },
  ]);
  assert.strictEqual(res.walkerError, undefined);
  // The walk runs AFTER the capture so the rects describe the frame that was
  // captured, not a later layout.
  assert.deepStrictEqual(wc.calls.map((c) => c.join(":")), ["exec:viewport", "capture", "exec:walker"]);
});

test("captureForAnnotation: derives dpr from pixel/CSS ratio when the page reports none", async () => {
  const wc = fakeContents({ viewport: { width: 500, height: 400 }, size: { width: 1000, height: 800 } });
  const res = await captureForAnnotation({ webContents: wc });
  assert.strictEqual(res.ok, true);
  assert.strictEqual(res.dpr, 2);
});

test("captureForAnnotation: answers (never throws) when there is no view", async () => {
  assert.deepStrictEqual(await captureForAnnotation({}), {
    ok: false, code: "no_view", error: "no native browser view to capture",
  });
  assert.deepStrictEqual(await captureForAnnotation({ webContents: null }), {
    ok: false, code: "no_view", error: "no native browser view to capture",
  });
  const gone = await captureForAnnotation({ webContents: fakeContents({ destroyed: true }) });
  assert.strictEqual(gone.ok, false);
  assert.strictEqual(gone.code, "no_view");
});

test("captureForAnnotation: an empty (unpainted) frame is an answered failure", async () => {
  const res = await captureForAnnotation({ webContents: fakeContents({ size: { width: 0, height: 0 } }) });
  assert.strictEqual(res.ok, false);
  assert.strictEqual(res.code, "capture_empty");
});

test("captureForAnnotation: a walker exception fails the capture with its message", async () => {
  const res = await captureForAnnotation({ webContents: fakeContents({ walkerThrows: true }) });
  assert.strictEqual(res.ok, false);
  assert.strictEqual(res.code, "capture_failed");
  assert.match(res.error, /walker exploded/);
});
