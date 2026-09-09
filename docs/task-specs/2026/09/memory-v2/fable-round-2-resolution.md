# Memory V2: second adversarial review

The owner supplied the second Fable synthesis against PR #9553 revision
`201eb6e1b7b36ba93c3ee1f3fa8fa0ed09326070`. This page records that supplied review
and the follow-up work. The thirteen per-lane files and their unlisted nits were
not supplied. Source changes require fresh CI results before they count as
executed evidence.

The review confirms that the earlier Global V1 namespace refusal, restore boot
failure, temporary-home protection and missing kernel coverage were repaired.
It withdraws the proposed `/proc/$PPID/root` bypass: the Linux capability check
against the target process's user namespace denies the access. The real canary
passed in CI. Capability dropping and seccomp are not the reason for that denial.

| ID | Reported concern | Follow-up |
| --- | --- | --- |
| N1 | Continue and steer trust a supplied parent | Authenticate the caller and compare the target run's protected store before continuation, steering or any run read. |
| N2 | Run lists and results reveal other members | Filter member lists and bulk cleanup; fence status, retry, release, stop and delete. Owner coordination remains available. |
| N3 | Chat history is scoped only by workspace | Apply protected memory ownership to search, list and direct reads, including `all_workspaces`. A bounded per-request index maps protected canonical session keys to transcript filenames, then revalidates each selected binding and live owner. Ambiguous aliases or unreadable committed bindings refuse. A private claim needs a process binding or signed proof. Owner aggregate APIs and unbound session creation cannot replace this boundary. |
| N4 | Direct schedule creation omits creator | Private callers use the existing scoped cron-tool dispatcher. Owner aggregate cron endpoints refuse private callers before parsing or mutation. Trigger text controls automatic Crew matching; it does not disable explicit owner scheduling or a member scheduling its own work. |
| N5 | Transcript agent labels become authority after restart | Restored labels cannot create a private assignment. Existing protected bindings or an explicit owner assignment authorize member execution. |
| N6 | A malformed store key disables Global startup | Isolate validation failure to the individual declaration and continue healthy store preparation. |
| N7 | i18n preflight prevents browser evidence | Translate the store label, fix layout and semantic boundaries, and retain scanner coverage within controls. Browser CI subsequently passed at b02cd67c and 60fccbad; later UI repairs still require their own captures. |
| N8 | Local owner bootstrap cannot attribute a process | Keep the owner check closed when identity is unknown. Log the denial and identify the gateway-host CLI login route. Cross-host, WSL and container arrangements may need that route instead of automatic local minting. |
| N9 | FAISS recall grows with lifetime tombstones | Use a fixed native search window, indexed hit eligibility and one batch of explicit columns. Avoid lifetime-tombstone overfetch, per-hit BLOB reads and duplicate Python cosine. Candidate starvation falls back to SQLite. Fresh performance claims require measurement. |
| N10 | Unicode transport is overcounted | Match each actual serialization stage and normalize the MCP text before calculating both character and byte budgets. HTTP and the MCP envelope have different encoding costs; the shipped MCP outer frame does escape Unicode. Do not infer unused headroom from the HTTP form alone. |
| N11 | Paged vector repair repeatedly rebuilds the full index | Append repaired rows to the resident native index after the SQLite commit. A repair page no longer rebuilds and writes the full index. Restart and incompatible-generation rebuild rules remain explicit. |
| N12 | Hardlink validation only occurs at spawn | The existing scan proves only the starting filesystem view. It is not a continuing guarantee against another host process publishing an alias later. Runtime and host-authority assumptions need separate treatment. |
| N13 | Custom-path models leave a new store vectorless | Preserve supported custom embedding configurations while refusing comparisons across incompatible embedding spaces. |
| N14 | Gateway advertises readiness before memory preparation | Load cron state while disarmed and bind the recovery dashboard. Publish one tracked preparation task immediately before READY without yielding to it, then wait at the central dashboard agent-turn admission seam before identity, provider or metadata work. Cron, heartbeat, automatic memory work and channel transports arm only after preparation. Individual failed stores stay fenced; background vector migration follows. |
| N15 | Private consolidation leaves permanent runtime sessions | Retire the generated UUID runtime and resumable mapping before deleting its transcript, archive segments, lock and protected binding. Failed retirement preserves authority; user conversation retention is unchanged. |
| N16 | Missing record on a supplied key is treated as coordinator authority | Authenticate transport identity before interpreting the claimed key; compare the process-bound store at the spawn boundary. |
| N17 | A config edit can re-adopt an archived store | Publish a complete protected retirement marker outside the replaceable store directory before locked member deletion. Raw config rebind and old backup restoration cannot erase it. Failed saves roll back only while the same owner still actively binds that generation. Same-name recreation allocates a fresh store. |
| N18 | New scope refusals lack audit records | Add security-event attribution to the shared caller/scope refusal and run boundary. Preserve the existing explicit `memory_unavailable` response for refused delegation. |
| N19 | Restore renames a store while another writer owns it | Coordinate restore admission with live V2 vector and Markdown users through a lifetime lock outside the replaceable directory. POSIX activation requires exclusive admission; Windows keeps native open-handle replacement refusal. A one-time SQLite lock probe is insufficient. |
| N20 | Legacy cron labels and shared Hook names cross identities | Restored cron labels cannot create private authority. Private Hook names include their store identity so a member cannot reserve a Global Hook name. |
| N21 | Oversized benchmark row never receives its expected ID | Normalize the identity lookup exactly as ingestion does and require one updated row. Retain the original false artifact and add selected-ID and per-predicate diagnostics. A fresh CI run must establish the corrected result. Completed context, isolated retention, deletion and transport checks now fail CI when false; model availability and ranking scores remain separate observations. |
| N22 | Change ledger and reports omit shared effects | Document named-store file-tool restrictions, Crew routing and startup/owner bootstrap limits. Correct the native-thread default to four and remove the stale browser-count sentence. Historical measurements remain labelled with their own source revision. |

The deterministic CI failures on the reviewed revision were formatting-baseline
graduations, the cron error-code baseline and the i18n preflight. Linux and Windows
backend group 2 failed on the same baseline. Coverage was blocked by those backend
failures, rather than a measured coverage percentage. These facts do not imply
that later lint steps or browser scenarios ran successfully.

The CI Qwen artifacts, source identities, historical oversized failure and later
passing structural results are recorded in the [algorithm report](algorithm-effectiveness-report.md).
It is an in-sample V2 measurement, not a V1 comparison or a production-quality
claim. The separate executive documents explain the staged V1/V2 product vision.

Own-session keepalive, managed tool policy and directive callbacks remain available after exact caller verification. The aggregate controls are a separate authority surface. Positive callback tests accompany foreign-session refusal tests.

The hardlink check validates the starting sandbox view. A privileged host writer can later publish a hardlink or a copy into shared project data; private members cannot acquire the hidden source through their own sandbox. The static memory seam script catches supported literal call shapes and is a review aid, not a complete reflection analyzer or the isolation boundary.

Related: [first review resolution](adversarial-review-resolution.md).

Delegated proofs used by long-running tools bind a live process incarnation, session, store and OS isolation identity. Each use revalidates those fields, and tools/list forwards its own request proof to policy lookup. The earlier short-lived proof format retains its expiry check for compatibility. This changes the internal authorization format, not the V1/V2 memory versions.

At `60fccbad`, all CI jobs completed. The browser suite, frontend test shards,
Linux namespace canary and macOS gateway checks passed. The remaining backend
test failures came from one new startup test leaking its active barrier, an
outdated unsigned-hook assertion and an acquisition-order source assertion.
The repair cleans up the owning test and preserves the production refusal.
Frontend lint required eight translated labels; backend lint required import
ordering. Coverage aggregation was blocked by upstream tests, not a measured
percentage. Fresh CI must validate these repairs.

The later code reviews identified interrupted proof-key creation, silent
episodic deletion failure, synchronous member binding reads in async handlers
and an untyped session-creation refusal. The follow-up stages the complete key
before atomic publication, retains failed records with a visible retry, moves
binding reads off the event loop and returns the existing typed refusal before
allocating a session. Valid keys keep their identity; corrupt committed keys
are not automatically rotated. Publication requires hard-link support in the
protected data-home filesystem.

A source retrospective retained the required HTML report, V1/V2 naming and
isolation/recovery mechanisms. It removed the unreachable generic store-creation
modal and its labels. The reachable V1 owner editor remains an explicitly
disclosed shared UI addition. Current screenshot review also led to one muted
Global source-group notice, proposal-specific provenance with equally weighted
choices, and reduced-motion layout fixes. These source changes are not claimed
as executed browser evidence before the next CI capture.

The legacy setup error now carries typed recovery metadata only for an eligible
unowned binding. The dashboard links to the selected member's Crew Manager editor,
omits ineffective Continue and Resume actions, and keeps ordinary Send available.
It hides the diagnostic prefix in display while preserving stored diagnostics.
Standalone SDK transcripts keep a router-free link. Browser CI follows the real
setup link through Place and Initialize instead of navigating directly in its
fixture. Old errors without metadata are not inferred from their text.

The async audit also covers the common channel turn-admission path, initial
vector-store construction and consolidation identity/profile reads. These reads
run off-loop while preserving cache generation checks and the original V1
write policy. New tests wrap real storage seams and assert off-loop execution;
their execution remains delegated to CI.
