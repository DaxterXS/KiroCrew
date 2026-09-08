---
title: Agent SDK provider onboarding — is the remaining boundary work worth it?
status: draft
revision: v1
author: zejiangg, with Kiro
created: 2026-09-08
last-audited: 2026-09-08
audited-at: 575a8390e
doc-pr:
implementation-prs: []
tracking-issues: []
supersedes: []
superseded-by: []
---
# RFC: Agent SDK provider onboarding — is the remaining boundary work worth it?

- Status: draft. This is a **decision document**, not a design. It asks whether the
  remaining PRs of [`rfc-crew-agent-sdk-boundary.md`](rfc-crew-agent-sdk-boundary.md)
  should be built, and answers three questions that RFC leaves open.
- Companion to [`rfc-crew-agent-sdk-boundary.md`](rfc-crew-agent-sdk-boundary.md).
  Section references written as §N refer to that RFC unless this document says
  otherwise.
- Every count in this document is measured, and **every count's source is a table
  headed with the commit it was measured at**. Prose does repeat the headline
  figures, in §2, §3.4 and §7. Those repetitions are quotations, not independent
  measurements: the tables in §3.1, §3.3 and §3.4 are authoritative, and a revision
  to one must update the prose that quotes it in the same commit.
- **A Chinese twin travels with this document**:
  [`rfc-agent-sdk-provider-onboarding.zh-CN.md`](rfc-agent-sdk-provider-onboarding.zh-CN.md).
  It is the repo's first translated doc, so it comes with a rule rather than only a
  disclaimer. **If you revise this file, update the twin in the SAME commit and bump
  its `translates-revision`.** If that is not worth doing, delete the twin in that
  commit instead — a translated decision record that silently falls behind is worse
  than none, because it misleads exactly the readers it was added for. The twin pins
  the `revision` it translates in its own front matter, so a mismatch against this
  file's `revision` is detectable.

## 1. The question, and the rule it is judged by

The boundary RFC's stated purpose is to make adding an agent provider cheap. The
rule this document judges it by is the plain one:

> If onboarding a provider costs the same after the refactor as before, do not
> refactor. Record why, and start adding providers directly.

So the measurement is not "how much coupling is removed". It is **how many files a
person adding provider number five has to open**, before and after each remaining
PR. Coupling that falls without changing that number is real work with a different
justification, and it has to be argued on that other justification.

## 2. The answer

**No-go on the onboarding rationale.** The remaining six-PR stack takes a
selectable, permission-enforced onboarding from 38 files to 37. That is one file,
and it is a relocation rather than a removal.

The reason is a single fact the RFC does not state: **authentication is the
majority of onboarding cost, and no PR in the stack removes any of it.** Two of them
relocate a piece of it, which is not the same thing and buys a provider nothing
(§3.3, §3.4). §4's non-goal 2 says so directly — the host-contract seams are out of
scope — and bucket 3, *Identity and auth*, is not one of the two contracts promoted
into PR 3. §10 treats every auth surface as an invariant to preserve, not a seam to
build.

The change that does move the number is not in the RFC at all. An auth seam —
one declaration on the driver, §5.3's presence-tested style — costs about 20 files
once and takes a new provider's auth cost from 24 files to 2. It depends on none of
PR 2 through PR 6, so it can land on today's `main`.

Recommendation, argued in §7: **stop the boundary stack on onboarding grounds,
ship the auth seam, then add the next provider.**

## 3. The measurement

### 3.1 What a provider costs today

Measured at `575a8390e` on 2026-09-08.

| Landing state | Files | What it means |
|---|---|---|
| Dormant, known but not selectable | 20 | The floor. Vocabulary, spawn path, frame corpus, host-contract column, install probe, parity tests |
| Selectable and permission-enforced | 38 | Adds the tool-permission route, the credential floor, the sandbox mask, the panel caveat and 13 locale files |
| Live, wired through every host surface | 49 | Adds the dashboard, MCP-gateway, readiness and doctor spill §7's onboarding doc calls stage 7 |

The 38-file figure is the honest comparison point, because it is the state a
provider has to reach to be usable. It is derived from the four merged PRs that
onboarded Codex — a dormant seam, an enforced tool-permission route, a probe
caveat, and a host-contract column — whose union is 58 distinct files, minus the
ones specific to building the gates themselves.

Two obligations arrived **after** Codex landed and are in the 20-file floor now:
the per-backend frame-replay corpus under `test/fixtures/acp_frames/`, whose gate
`test_acp_frame_replay.py` is a hard failure rather than a skip, and the
per-backend column in `docs/system-specs/modules/agent-host-contract.md`, enforced
by `test_agent_host_contract_parity.py`. Onboarding got **more** expensive during
the boundary work, not less.

### 3.2 PR2a and PR3a have not landed

The brief for this document asked that the baseline assume PR2a (the `EVENT_*`
constants moving to `agent_sdk/events.py`) and PR3a (`acp_backends` and
`acp_tool_gate` moving into `agent_sdk/`, and the remaining identity checks
becoming capability questions) are in flight and will land.

Measured at `575a8390e`, neither has. No `agent_sdk/events.py` exists; all the
`EVENT_*` constants are still in `src/kiro_crew/acp/types.py`, and
`src/kiro_crew/providers/base.py` still re-exports them alongside the
`LLMEvent = AcpEvent` alias. `src/kiro_crew/acp_backends.py` and
`src/kiro_crew/acp_tool_gate.py` are still at the package top level. All six
identity checks §PR 3 names are live, in `src/kiro_crew/config/loader.py`,
`src/kiro_crew/dashboard/chat_handlers.py`, `src/kiro_crew/dashboard/chat_runner.py`
and `src/kiro_crew/knowledge/llm_pool.py`. Two more the RFC does not list are also
live, both in `src/kiro_crew/dashboard/handlers/agents.py` — a
`provider.is_claude_backend` read and a separate config-level comparison against
`ACP_BACKEND_CLAUDE`. So the live count is eight, not the six §PR 3 names.

**The assumption costs nothing, which is itself the finding.** Neither removes a
file from the onboarding list. PR2a moves constants no provider ever adds. PR3a
renames the path of two files a provider still edits. The baseline stands at
20 / 38 / 49 either way.

### 3.3 Per-PR delta

Measured at `575a8390e` on 2026-09-08. Columns (a) and (b) are the
selectable-and-enforced count unless the row says otherwise. Column (d) counts the
files the PR itself touches, from the boundary gate's own baseline where the PR is
a migration wave.

| Remaining PR | (a) before | (b) after | (c) what drops, and why | (d) cost of the PR, and risk |
|---|---|---|---|---|
| **PR2b/2c** — the rest of the types: `AgentEvent` and its shims, `ApprovalToken`, the error taxonomy | 38 | 38 | **Nothing. No onboarding value — infrastructure only.** A provider never defines an event type | **33 files.** 201 event-field reads across 19 files, worst `src/kiro_crew/dashboard/chat_runner.py`; plus 145 approve/reject call sites across 31 files. The RFC measured 131 reads over 17 files — the surface has grown by about half since. **Risk: high.** §10.1 makes `ApprovalToken` the security boundary, and §7 warns that dropping `raw_tool_params` without its derived members sends every shell call into deny-by-default. What it is **for**: type ownership — the SDK, not `src/kiro_crew/providers/base.py`, defines the event a consumer reads |
| **PR3b** — the rest of the capability mechanism, plus the two promoted host-contract contracts | 38 | 38 | **Nothing. No onboarding value — infrastructure only.** §PR 3 translates each capability set into "a semantic question on `SessionCapabilities`". The per-provider membership decision survives verbatim in a new spelling | **6 files across 7 sites**, plus relocating two leaf modules and threading protocols through every session-construction path. **Risk: medium-high.** §10.7 inverts the polarity of the logout-recycle set; getting it backwards lets a host logout retire a foreign provider's live child. What it is **for**: ownership clarity — the id-keyed dispatch tables move inside the boundary, so a policy module stops reading a leaf's tables from outside it |
| **PR4** — the supervisor takes the lifecycle | 38 | 38 | **Nothing. No onboarding value — infrastructure only** | **9 baselined files, 24 edges**, led by `src/kiro_crew/session.py`. **Risk: medium** — the move must carry the kill-tree helper and the managed-agent markers, which the work-class sweeps consume as safety input rather than as shared code. What it is **for**: PID ownership and cycle removal. Its cheap half already landed |
| **PR5 wave 1** — `dashboard/` | 38 | 38 | **Nothing. No onboarding value — infrastructure only.** The dashboard files on the live list need per-provider *behaviour*, not an ACP import; rerouting the import leaves the branch | **17 files, 26 edges. Risk: low-medium.** Each wave also deletes the PR 2 shims it was the last reader of. What it is **for**: import hygiene |
| **PR5 wave 2** — `messaging/` and the transports | 38 | 38 | **Nothing. No onboarding value — infrastructure only.** No channel module is on the onboarding list in any landing state | **8 files, 12 edges. Risk: low.** What it is **for**: import hygiene |
| **PR5 wave 3** — `apps/`, `workflows/`, `knowledge/` | 38 | 38 | **Nothing. No onboarding value — infrastructure only** | **8 files, 10 edges. Risk: low**, and it carries one real security cleanup: `src/kiro_crew/knowledge/llm_pool.py` stops reading a private ACP attribute from outside the package. What it is **for**: import hygiene |
| **PR5 wave 4** — `cli_*`, `config/`, `platform/`, `eval/`, `connections/`, top level | 49 (live) | 47 (live) | **Two files, and they are the only genuine onboarding wins in the stack.** `src/kiro_crew/config/loader.py` drops **if** its Claude comparison becomes a capability a provider answers where it declares itself. `src/kiro_crew/cli_doctor.py` drops on the same condition. Both are conditional on PR3b's translation being genuinely provider-agnostic; if the capability still needs a per-provider branch at the call site, this row is zero too | **25 files, 58 edges** — the largest wave, and the RFC's catch-all. **Risk: medium-high** — it owns `src/kiro_crew/session.py` and the modules split out of it. What it is **for**: import hygiene, plus those two branch removals |
| **PR6** — seal the boundary | 38 | 37 | **One file.** `src/kiro_crew/providers/acp.py` drops, because PR 6 deletes its shim surface and the provider-label branch relocates into `src/kiro_crew/agent_sdk/drivers/acp.py`, which is already on the list. The mirror registry does **not** drop — it changes path and is still edited | Whatever the waves left of the baseline, plus deleting the shim modules, relocating the mirror tree, and updating the pinned exempt-set test. 28 modules outside the boundary still import from `kiro_crew.providers`. **Risk: high, and it is the only irreversible step.** It also cannot start: §12.5's mirrors question gates it, and §4 answers it. What it is **for**: import hygiene, finalized |

**Stack total: 38 → 37 selectable-and-enforced. 49 → 46 live, best case, and one of
those three is conditional on a decision PR3b has not made.** That is roughly 6% of
onboarding cost, bought with six PRs, about 90 files and about 106 import edges.

### 3.4 Where the cost actually is

Classifying the 38-file selectable-and-enforced census by what each file is *about*.
Measured at `575a8390e` on 2026-09-08.

| Class | Files | Share |
|---|---|---|
| **Auth** — credential floor, sandbox mask, permission routing, install and doctor probe, the panel's sign-in caveat | **21** | 55% |
| Protocol and type — id vocabulary, provider label, frame corpus, mirror registry, capability-set membership | 12 | 32% |
| Mixed — the spawn path, the contract and parity docs | 4 | 11% |
| Neither — the formatting ratchet | 1 | 3% |

Excluding the mixed and unclassifiable rows, auth is **21 of 33, or 64%**, of the
classifiable cost. On the live-harness list it is **24 of 49**. Thirteen of the 21
are locale files carrying one string whose entire content is that Codex signs in on
its own.

In the host contract itself, **four of nine buckets are auth**: 3 Identity and auth,
4 Sandbox, 7 Security and permission parity, 8 Auxiliary runtimes.

**No remaining PR removes any of it, and the RFC says so.** Two of them do
*touch* it: §PR 3 translates `ACP_BACKENDS_KIRO_IDENTITY_STORE` into a capability
question, and it must give `src/kiro_crew/acp_tool_gate.py` a named home. Both
relocate the per-provider entry rather than retiring it, which is why §3.3 scores
them zero — a provider still declares logout-recycle membership and still adds a
credential-mask row, at a new path. §4's non-goal 2
excludes host-contract seam work including sandbox delegation; the two contracts
promoted into PR 3 are per-session MCP injection and transcript ownership, neither
of which is auth; bucket 3 appears in the RFC's deferred list. §10.2 says deny-rule
parity "is host contract, not SDK". §10.5 requires the credential scrub to move
with the spawn code rather than be re-derived above the boundary. §10.8 keeps
sandbox delegation fail-closed where it is.

So the RFC as written does not achieve its stated onboarding goal. It is not that
the goal was missed by a margin — the majority of the cost is in a region the RFC
declares out of scope.

## 4. Where `providers/mirrors/` lives after PR 6

### 4.1 Recommendation

**`src/kiro_crew/agent_sdk/mirrors/`, relocated in a commit of its own before PR 6
starts** — and, under §7's recommendation, not urgent, because nothing forces the
move until PR 6 is attempted. Today's `src/kiro_crew/providers/mirrors/` is a
working state, not a debt accruing interest.

A mirror projects one agent spec onto one host's native configuration. That is
driver work, which is the argument §12.5 already records for this option. The
counter-argument §12.5 also records — that the rulings encode per-host *decisions* a
driver should not be free to restate — is answered by keeping the ruling vocabulary
and the registry shared inside `mirrors/`, rather than splitting them per driver.

The third candidate, a mirror file per driver, has no referent. `drivers/` holds one
module per harness *family*, and there is exactly one today. Claude is not a driver;
it is a backend served by the ACP driver. All four mirror entries belong to that one
driver, so a per-driver mirror file would hold all four — which is the shared
package under a different path.

### 4.2 Two prerequisites, both verified

Neither is optional, and both are the work §12.5 warns against discovering during
PR 6.

**The mirror's ACP import must become function-local first.**
`src/kiro_crew/providers/mirrors/claude_code.py` imports the session-MCP translator
from `kiro_crew.acp` at module scope, and the package's own `__init__` reaches it
eagerly through the registry. Moving that under `agent_sdk/` would put a
module-scope ACP import inside the SDK tree, and **nothing currently catches that.**
The boundary gate cannot, because `agent_sdk/` is exempt wholesale. The pinned test
`test_agent_sdk_provider_identity.py` cannot either: its subprocess imports
`kiro_crew.agent_sdk.provider_identity` specifically, so an unexported
`agent_sdk.mirrors` submodule with an eager ACP import keeps it green while every
consumer of the mirror starts loading the ACP package. This is an uncovered
invariant, not a guarded one. So PR 6 owes two things rather than one: defer the
import into the method that needs it, matching every other function in
`src/kiro_crew/agent_sdk/drivers/acp.py`, **and** extend that probe to the relocated
mirror package so the invariant is enforced.

**The one production caller must become function-local too.**
`src/kiro_crew/acp/client.py` imports the mirror lookup at module scope. With the
mirror under `agent_sdk/`, that makes the foundation eagerly import the SDK — the
exact inversion §5.1's diagram forbids.

A third fact makes the "leave `providers/` alive as the mirror layer" option worse
than it reads. The mirror package is importable today only by load order: the shim
`__init__` pulls the ACP package first, so by the time the mirror package's own body
runs, the cycle is already resolved. Deleting the shim's re-exports — which is
exactly what PR 6 does — inverts that order, and a standalone
`import kiro_crew.providers.mirrors` then raises a partially-initialized-module
`ImportError`. This was reproduced on a copy of the tree. So that option is not a
pure deletion either: it needs the same import deferral, and it additionally keeps a
third exempt tree, which falsifies PR 6's own "reduced to two trees" claim, and it
leaves the forbidden-roots list self-contradictory — `kiro_crew.providers` stays
forbidden while `kiro_crew.providers.mirrors` is the sanctioned home of a live
layer, with a shrink-only baseline and no opt-out marker, so a future non-exempt
consumer of the mirror lookup has no legal remedy at all.

### 4.3 What PR 6's deletion exit becomes

Replacing §PR 6's two mirror-conditional exit lines:

- `src/kiro_crew/providers/` is deleted in full, `mirrors/` included, having been
  relocated to `src/kiro_crew/agent_sdk/mirrors/` in a **prior** commit.
- The gate's exempt set is exactly `agent_sdk/` and `acp/`, with the pinned
  exempt-set test updated in the same commit. The "reduced to two trees" sentence
  becomes true as written.
- The relocated mirror's ACP import is function-local, and the no-eager-ACP-import
  probe is **extended to import the relocated mirror package**, so the invariant is
  enforced rather than merely unviolated.
- `src/kiro_crew/acp/client.py`'s mirror lookup is function-local, so the
  foundation does not eagerly load the SDK.
- The forbidden-roots list drops `kiro_crew.providers`, and the test that currently
  asserts that root is present is rewritten rather than deleted.

Two obligations no current exit covers, under **any** of the three options:

- `src/kiro_crew/acp/session_provider.py` imports the cancel-outcome and provider
  types from `src/kiro_crew/providers/base.py`. Deleting that module requires those
  to have a new home first. It sits inside the exempt tree, so the gate never
  flagged it.
- `scripts/check_agent_sdk_boundary.py` carries two comments that contradict each
  other about whether `providers/` is scheduled for deletion. Whichever option is
  taken, one of them has to change.

## 5. The auth seam

### 5.1 What a provider touches for auth today

Measured at `575a8390e` on 2026-09-08, for a provider that brings its own sign-in
and needs no in-product login UI — the Codex shape.

| Area | File | The auth-specific edit |
|---|---|---|
| Credential floor | `src/kiro_crew/security/paths.py` | The credential leaf, its `$HOME`-override anchor, and a resolved-roots field |
| Adapter's own token | `src/kiro_crew/acp_tool_gate.py` | The one leaf excluded from the OS mask, or the child cannot read its own token |
| Logout policy | `src/kiro_crew/acp_backends.py` | In or out of the logout-recycle set, and of the pod home remap |
| Sandbox | `src/kiro_crew/sandbox.py` | Whether the credential mask applies; hidden leaves if it stores under the crew home |
| Install probe | `src/kiro_crew/agent_sdk/backend_install.py` | A probe entry, and the recorded decision that credentials are not probed |
| Driver resolver | `src/kiro_crew/agent_sdk/drivers/acp.py` | The resolver the probe calls |
| Expiry signal | `src/kiro_crew/acp/client.py` | The auth-required raise site and the not-logged-in classification |
| Expiry signal | `src/kiro_crew/acp/session_provider.py` | The dead-child translation to auth-required |
| Doctor | `src/kiro_crew/cli_doctor.py` | A sign-in row, or the recorded decision not to have one |
| Host contract | `docs/system-specs/modules/agent-host-contract.md` | The bucket 3 column. A hard gate |
| Panel | `website/src/pages/developer/AgentBackendTab.tsx` | The caveat chain — the only place a user learns the provider signs in separately |
| Panel copy | 13 locale files under `website/src/i18n/locales/` | The caveat string |

**24 files.** A provider needing in-product interactive login — the KAS shape — adds
17 more: the whole `src/kiro_crew/auth/` package, its dashboard handlers and routes,
the frontend API client, and a login-gate component. **41 files**, with the locale
files then carrying about 52 keys each instead of one.

Two structural facts behind that count. Nothing in the tree is a per-provider auth
object: every touch is an edit to a shared table or an `if` chain in a host module.
And `docs/system-specs/modules/harness-onboarding.md` names seven onboarding stages,
**none of which is auth** — it appears only as a caveat inside one stage and as
unnamed spill in another.

Evidence this is not theoretical: the PR that made Claude Code selectable touched
zero auth files. Its OAuth token was added to the sensitive-path floor later, by the
**Codex** PR, whose own body records that a live agent-readable OAuth token had been
sitting off the floor while Claude Code was already shipping as selectable.

### 5.2 The proposal

A declaration and one optional protocol, in §5.3's presence-tested style — small
mandatory core, `runtime_checkable` optional protocol, tested with `isinstance`
rather than read as a flag.

`src/kiro_crew/agent_sdk/host_auth.py`, new:

- **`AgentAuthDeclaration`** (mandatory for a driver): the credential leaves it
  stores, the `$HOME`-override environment variables that relocate them, the one
  leaf its own child must still read, the sign-in remedy string, whether a host
  logout may retire its children, and where its entitlement comes from.
- **`AgentInteractiveLogin`** (`runtime_checkable`, optional): the flow list, and
  begin / poll / logout. A provider that brings its own sign-in simply does not
  implement it, and §5.3's rule applies — the absence is visible in the type system
  instead of arriving as a no-op.

Everything else derives. The credential floor, the sandbox mask and the
adapter-own-leaf exclusion all read the declaration instead of literals, so the
host keeps deciding what is fenced while the provider only declares what it stores.
That split matters: a driver that could edit the mask could unmask itself.

The frontend half is the same move. `GET /api/acp-backends` gains an auth object,
and the panel's caveat renders what arrives. The option list is **already** data —
candidates are a union of server answers and the display name falls back to the
wire id — so this finishes a pattern rather than starting one.

### 5.3 Cost, and what it buys

**20 files: 15 source and doc, 5 test.** After it, a new
brings-own-auth provider's auth cost is **2 files** — its declaration in the driver,
and the bucket 3 column the parity test demands.

The next three numbers sit on two different bases, so they are stated separately
rather than collapsed into one. Of the **24-file auth inventory** in §5.1, 22 stop
carrying an auth edit; the 2 touched for auth and nothing else —
`src/kiro_crew/security/paths.py` and `src/kiro_crew/acp/session_provider.py` —
leave the onboarding list outright. Of the **38-file selectable-and-enforced list**
in §3.1, **16 files leave entirely** on the server-rendered-remedy choice below: the
13 locale files, `src/kiro_crew/security/paths.py`,
`website/src/pages/developer/AgentBackendTab.tsx` and its test. The remaining auth
files on that list stay, because each also carries a non-auth onboarding edit.

Do not subtract one base from the other. §3.1's list and §5.1's list are different
lists, and mixing them is what produces a wrong post-seam figure.

One design constraint to settle inside the PR rather than discover:
`src/kiro_crew/security/paths.py` is imported very early and reads the identity-store
table precisely because that module is stdlib-only. The declaration table has to
live in a stdlib-only leaf on the same footing, or the floor cannot read it without
a cycle — the same trap the backend vocabulary module's own docstring records.

**The 13 locale files are the honest exception, and the PR chooses their fate.**
Render the declaration's remedy string verbatim from the server, exactly as the
panel already falls back to the wire id, and all 13 drop off the onboarding list
forever — at the price of one untranslated string per provider. Keep a translated
line instead and all 13 stay on the list forever, because a translated per-provider
string is a per-provider file edit by construction. **Recommend the first**: an
untranslated remedy that is correct beats a translated one nobody adds.

### 5.4 Which PR it is

**A new PR, independent of the stack.** It is not PR 3b or PR 4b, because it depends
on none of PR 2 through PR 6: `src/kiro_crew/agent_sdk/` and its `drivers/` module
already exist, the declaration is stdlib-only by construction, and the API payload
and panel are untouched by every RFC PR. It lands on today's `main`.

Exits:

- Every existing provider has a declaration, and the parity test fails when a known
  provider has none.
- The credential floor, the sandbox mask and the adapter-own-leaf exclusion derive
  from declarations; the three hand-maintained literal tables are gone.
- The doctor's per-provider auth blocks are replaced by one declaration-driven row.
- The auth-required message comes from the declaration, not the kiro-cli literal.
- The panel's provider comparisons are gone; the caveat comes from the payload.
- `docs/system-specs/modules/agent-host-contract.md` bucket 3 moves from a text
  table to a declared seam, and the seam-status list drops it.
- `docs/system-specs/modules/harness-onboarding.md` gains an auth stage. It has
  none today.

## 6. Adding a provider, as it stands

This is the checklist to publish and follow if §7 is accepted. It is the **current**
cost, not a future one, and it is ordered so an unusable intermediate state is never
shipped.

### 6.1 Required by the ratchets

1. **Vocabulary.** `src/kiro_crew/acp_backends.py`: the id constant, the known set,
   the selectable baseline, the policy id, the routing entry, and an explicit
   in-or-out decision for **each** capability set. The parity and governance tests
   fail on a missing entry.
2. **Provider label.** `src/kiro_crew/acp/types.py` and the label branch in
   `src/kiro_crew/providers/acp.py`. A closed mapping that indexes resume,
   session-map persistence and cleanup routing.
3. **Spawn path and handshake.** `src/kiro_crew/acp/client.py`: adapter and binary
   constants, the dependency marker, the environment override, the resolution
   ladder, and its own protocol version. §5.5 keeps this inside the driver by
   design, and the onboarding doc measures it in the hundreds of lines. It is
   irreducible.
4. **Frame-replay corpus.** `test/fixtures/acp_frames/<policy id>/`, at least two
   files. `test_acp_frame_replay.py` is a **hard failure**, not a skip, and demands
   seven frame classes: an initialize response carrying the agent version, a
   session-new response carrying the session id, a message chunk, a tool call, a
   tool-call update, a permission request, and a response carrying a stop reason.
   Since the opt-in frame recorder landed, producing this is mechanical rather than
   hand-transcribed. Note that `test/fixtures/acp_frames/README.md` still says no
   recorder exists — that is stale.
5. **Host contract.** A column in **all nine** bucket tables of
   `docs/system-specs/modules/agent-host-contract.md`, plus a row in the
   column-meaning table. `test_agent_host_contract_parity.py` requires the resolved
   column set to equal the known set exactly, resolves each column's constant name
   against the vocabulary module, and rejects a second backend-shaped table under a
   heading. A cell reading `unknown` passes: it asserts existence, not truth.
6. **Install probe.** A probe entry in
   `src/kiro_crew/agent_sdk/backend_install.py` and the resolver it calls in
   `src/kiro_crew/agent_sdk/drivers/acp.py`. A missing probe degrades to unknown
   rather than raising, but shipping selectable with no probe is the regression one
   of the Codex PRs existed to fix.
7. **Selectability ratchet.** `test/test_agent_backend_editable.py` carries a
   hard-coded baseline literal and a not-shipped-selectable set. A new id trips both
   assertions.
8. **Mirror decision.** The registry needs either a mirror class or an explicit
   no-mirror entry with a prose reason. An id in neither raises at runtime.
9. **Capability opt-ins.** Several tests are parameterized over the known set and
   fail when a membership decision contradicts them. These are the tests that stop a
   provider from silently opting out of a decision.

### 6.2 Required by auth

The twelve rows of §5.1. Until the auth seam lands, every one is a hand edit to a
shared table.

### 6.3 Frontend

**No gate requires anything here**, and the option list is the one part of
onboarding that is already correct: the panel builds its candidates from server
answers and falls back to the wire id for a name. Genuinely optional: a display name
and an icon.

The auth caveat is **not** optional in practice, and that is why §3.1's 38-file bill
counts it and its 13 locale files. No test fails without it. It is still the only
place a user learns the provider signs in separately, so a provider shipping without
one ships a chip nobody can act on. It is on §5.1's auth list rather than this
section for that reason.

### 6.4 The bill

**Dormant: 20 files. Selectable and enforced: 38. Live: 49.** After the full RFC
stack: 37 and 46. After the auth seam instead: **22 selectable-and-enforced** on the
server-rendered-remedy choice, because 16 files leave the list — itemised in §5.3.
The comparison that matters is 16 files removed against the stack's 1.

## 7. Recommendation

**Recommendation 3, amended: stop the boundary stack on onboarding grounds,
document the checklist in §6 as it stands, ship the auth seam, and start the next
provider.**

The plain form of the argument:

- The stack's onboarding delta is one file out of 38. Measured, in §3.3.
- The majority of the cost is auth, and the RFC excludes auth by its own non-goal.
  Measured, in §3.4.
- One PR outside the stack takes the auth cost from 24 files to 2, and it depends on
  nothing in the stack. §5.
- Therefore the rule in §1 fires: onboarding costs the same after the refactor as
  before, so the refactor is not justified **on that ground**.

Why not recommendation 2, "do only the PRs with onboarding delta". Because there are
none worth naming. PR 6 buys one file and cannot start until §12.5 is decided; PR5
wave 4 buys two, both conditional on PR3b, and costs 25 files and the largest wave in
the stack. Recommendation 2 collapses into recommendation 3 on the numbers.

**What this does not say.** It does not say the boundary stack is worthless. It says
the boundary stack's justification is not onboarding, and it should be argued on
what it actually delivers:

- **Type ownership** (PR2b/2c). Today `src/kiro_crew/providers/base.py` aliases the
  ACP event as the provider-agnostic type, which is the channel that made the gate
  watch two roots. That is a real design defect.
- **PID ownership and cycle removal** (PR4). Its cheap half already landed and is
  why the baseline fell.
- **One security cleanup** (PR5 wave 3). `src/kiro_crew/knowledge/llm_pool.py` reads
  a private ACP attribute from outside the package. That is worth fixing on its own,
  and it does not need a wave.
- **Import hygiene** (PR5, PR6). Genuine, and worth doing when the tree is otherwise
  quiet — not ahead of a provider the product wants.

Each of those can be argued, sized and scheduled on its own. What none of them can
be argued on is the cost of adding provider number five.

**Sequence, if this is accepted.**

1. Publish §6 as the onboarding checklist, and fix the two doc drifts §6.1 names —
   the stale recorder note, and the capability-set count `harness-onboarding.md`
   reports, which is one short of what the code carries.
2. Ship the auth seam (§5), on the server-rendered-remedy choice.
3. Add the next provider against the §6 checklist, and record what it actually cost.
4. Re-open the boundary stack only on its own justification, PR by PR, with §7's
   list as the argument and the mirrors decision (§4) taken when PR 6 is attempted
   rather than before.

## 8. What would change this answer

- **A second provider needing in-product interactive login.** The auth seam's
  optional login protocol would then be load-bearing rather than forward-looking,
  and the 17 extra files of §5.1 come into scope. The seam gets cheaper relative to
  the alternative, not more expensive — so this strengthens §7 rather than weakening
  it.
- **A measured onboarding that comes in far above 38 files.** Step 3 of the sequence
  exists to find that out. If the real cost is dominated by something neither this
  document nor the RFC measured, both need re-reading.
- **The boundary stack being needed for a non-onboarding reason with a deadline** —
  an unresolvable import cycle, or a type defect that blocks a feature. Then the
  relevant PR ships on that reason, and this document's answer is untouched, because
  it was never an argument about the code's shape.
