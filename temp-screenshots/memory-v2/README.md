# Memory V2 demo

The `ci-60fccbad-benchmark/` directory retains the three unmodified Qwen
measurement files from [CI run 34340819757](https://github.com/kirodotdev/KiroCrew/actions/runs/34340819757).
Its provenance records PR source `60fccbad521cad6df09a2f60075fa43f3ca02be4`
separately from merge checkout `17b40179e70547e3f8e298c8e7ca121602fcdb5e`.
The raw report SHA-256 is
`2727db85de0515c10b42166e8175eada0151e3dab232ac4a0373f32546ada611`;
the provenance SHA-256 is
`0ad8c32add329704de0e89c1cde7b6acef3bc3b501d3133bb3f0518e7c632114`.
This preserves the measurement when the hosted CI artifact expires. It is
in-sample retrieval evidence, not a V1 comparison or a passing whole-PR result.

The `ci-b02cd67c/` directory preserves the complete, unchanged media from the
successful offline browser job in [CI run 34333392423](https://github.com/kirodotdev/KiroCrew/actions/runs/34333392423).
All eight memory scenarios passed without retries. The PR source was
`b02cd67c08732b86e549973942a05e2638bf7976`; the CI merge checkout was
`bff23582600b7b444e75e9141207fc46c47b5558`. Its `provenance.json` records the
artifact identity and each original file's hash. The archive contains eight
WebM recordings, screenshots and the scenario receipts.

These captures show the real dashboard and an ephemeral gateway with synthetic
records, including copying, correction, separate stores, mobile bulk previews,
proposal review and staged restore cancellation. They do not demonstrate live
provider answers, Crew delegation or restore activation after restart. They
precede the follow-up recall hint, read-error handling and startup repairs.
The whole PR's CI was not green when this browser artifact was captured.

## Historical walkthrough

Captured from source revision `d7d05392f3e6be5bc4de0b6f5abd75d669db0633` on an
isolated Linux gateway. Mira and Theo are synthetic demo members. The screenshots
and video show the real application with test data.

That identifier is a retained local pre-squash object, not a promised public GitHub
commit URL. The committed media is the durable artifact. Later review fixes to
the toolbar, copy and recovery states are covered by newly authored CI captures;
these historical images and video do not attest those later changes.

The 54.36-second WebM records member identity, private memory, a correction preview,
the saved correction after reload, bounded recall, backup creation, a separate
empty member store and member conversation navigation. It does not show a live
model response or a Crew Mode delegation run.

Recall in this isolated demo uses keyword fallback with model downloads disabled.
The member header and drawer reflect the integrated React Query member interface.

Desktop captures are 1440 by 900 pixels. Mobile captures are 390 by 844 pixels.
Verification confirmed that the correction persists after reload, Theo's store
stays empty, raw retrieval context stays collapsed until requested, and cancelling
the mobile correction preview leaves the saved memory unchanged.

The video uses VP8 in a WebM container. The numbered PNG files cover eight desktop
views and four mobile views. These review artifacts are outside the packaged app.

The [historical benchmark evidence archive](memory-v2-d7d05392-evidence-20260908.zip)
preserves the original measured payload, publication records, run log and four
exact Git LF source files, with an internal inventory and hashes. SHA-256:
`1fc52ea63a189922ad68acd0196359434d0e2213678eee504e1d45e11e976b14`.
It does not contain a complete runtime or environment lock. The publication
metadata was added after measurement, and the historical results do not validate
later retrieval changes or a held-out evaluation set.
