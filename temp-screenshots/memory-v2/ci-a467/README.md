# CI browser evidence: a467

These are unchanged originals from [CI run 34446574480](https://github.com/kirodotdev/KiroCrew/actions/runs/34446574480), E2E job 102772791932, completed successfully on 2026-09-10 at 07:01:18 UTC.

Capture source: `a46796234356c217d5fd531f21e1ca7a1c026b86`. GitHub's test checkout was merge `8c8aeb3821766d7bdf0fbf705ab976b410767536`; both trees are `e5aa351b60a7d37156f8de6d4dba646bc1e8e828`. These captures show that source, not later repairs in the commit publishing this folder.

The folder contains all 35 memory PNGs, 10 WebMs and 10 scenario JSON receipts from artifact 10140337375, plus both gallery PNGs from artifact 10140337772. Every original file hash is listed in [evidence.json](evidence.json). The original ZIP SHA256 values are respectively `9f746b08cdcb56ac2ea39281d38ba1dfa853513855774e9008a6cc9d866659d4` and `1f287e5acbc9f716a3e3a2508ef86086958b440a6d68f5fc1da80331e9a4e355`.

All ten memory scenarios passed on attempt 1 with no retries. The outer E2E wrapper reports 18 passed, 2 warnings. All 37 original images were visually reviewed, and all ten videos were sampled at 1 fps into 83 frames; every sampled contact sheet was viewed. This is sampled video inspection, not uninterrupted playback. The recordings use a real dashboard and isolated gateway with synthetic data and a fake ACP provider. They do not demonstrate a deployed gateway restart or live provider fleet.

The screenshots cover member lifecycle, copy provenance, correction, recall, Profile, private isolation, V1/V2 bulk selection and concurrent-correction previews, proposal decisions, backup staging/cancellation, restored experiences, legacy opt-in, dirty-state guidance, and unavailable/mismatched identity. Gallery evidence is the English Design Critique detail page at desktop and mobile sizes, not a visual check of every app or locale.

Known capture limits:

- The legacy Members setup PNG was not uploaded: its old filename did not match the artifact glob. The source-only output-name repair is pending the next CI capture. This folder does not invent or substitute that missing PNG.
- `member-memory-recall-before.png` shows the search loading skeleton, not settled browse results. The separate recall-evidence image shows returned task context and its distinction from browse/edit results.
- Some desktop lists and empty-state copy continue below the viewport. Bulk-selection framing crops part of the upper identity header. Mobile previews retain visible action buttons; the next partial record is scroll continuation.
- Videos include initial navigation/loading frames. Mobile viewports occupy part of the original video canvas; blank recording padding is not evidence of application overflow. Sampling can miss subsecond transitions.
- The a467 full CI matrix was not green: Frontend Tests (3) and Coverage Merge reported the same generated settings-registry mismatch. Its subsequent source repair is not certified by these artifacts.

No local browser recapture, product execution, or modification of the original media was performed.
