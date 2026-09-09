# Browser annotation

Page: Kiro Crew — http://localhost:7895/settings
Viewport: 960×620 CSS px. The attached image `browser-annotation-2026-09-09T20-55-22.png` is this viewport with the user's marks drawn on it; coordinates below are CSS px in that image.

Each mark is mapped to the interactive element under it. `ref` values are the built-in Browser panel's element refs — the same `eN` the `browser` tool's `snapshot` returns — so they can be passed to `click` / `type` / `hover` directly (re-run `snapshot` first if the page has changed).

1. box → button "Overview" [ref=e21] · selector `#main-content > div > nav > button:nth-of-type(1)` · element at (248, 96) 175×36 — at (221, 71) 206×56 (coverage 0.86)
2. arrow → button "Artifacts" [ref=e10] · selector `nav > div:nth-of-type(1) > div:nth-of-type(5) > div` · element at (17, 173) 202×36 — tip at (89, 182)
3. text "this button" — at (444, 75) 113×25 — no interactive element under it
