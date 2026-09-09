# Memory V2 review evidence

This branch retains the original evidence files from PR #9553 without adding
them to the feature branch's main ancestry or checkout. It is not an application
release. An ordinary all-branch clone may still fetch these objects.

The inventory records the exact blobs copied from source commit `5102085b24a83ef01d4b7ebe6207100c86e48413`.
That is the evidence-publication input, not a claim that every capture or model
run tested that revision. Original per-file provenance identifies each actual
source, CI run, synthetic merge, outcome and limitation. Older screenshots remain
historical until replaced by a verified current walkthrough.

The archived handoff and two review-resolution documents are retained unchanged
as historical source records. Their relative links describe the original source
tree, not this evidence-only tree. Current operating contracts live in the feature
branch's owning specifications and concise handoff. The supplied Fable syntheses
did not include the full lane reports or unlisted nits.

`inventory.json` contains SHA-256 values for every retained original file.
Images, videos, model outputs and source archives are outside runtime packages.

## Latest retained CI evidence

CI run 34356560737 tested PR source db32a2c5720477f9bd2f565bdb7245571a1d7ce9
through synthetic merge fe37d515a82568863e4eb924e58a0250d14f972c.
The ci-db32a2c5 directory retains all 45 originals from artifact 10106828077:
25 PNGs, 10 attempt receipts and 10 WebM recordings. Seven of eight distinct
member-memory scenarios passed on their first attempt. Legacy initialization
failed on the same accessible tab-name lookup across three attempts before
initialization; its downstream checks did not execute. The whole browser suite
reported 264 passed and one failed. All 25 PNGs were visually inspected across
the authoring team; the recordings have not been watched end to end. Synthetic
gateway evidence does not demonstrate live-provider answers, Crew delegation,
or restore activation after restart.

The ci-db32a2c5-benchmark directory retains the three real-Qwen artifact files
from artifact 10106153627. The report bytes equal the earlier measurement;
the new provenance and log identify this repeat. Six core source files were
independently hash-checked against the exact PR source. These are same-corpus
V2 retrieval measurements, not held-out validation, V1/V2 A/B testing or measured
answer, performance or cost improvements. CI structural checks passed.

This evidence predates the next source repair batch. No passing current-head
claim is inferred from retaining these files. Historical entries are unchanged.
