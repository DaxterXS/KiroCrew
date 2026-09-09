# Memory V2 adversarial review resolution

This record maps the supplied Fable synthesis for the earlier `40c` revision to
the current implementation. It covers B1, H1 through H17 and the grouped medium
findings. It does not claim that all 13 original lane reports were available or
that the approximately 35 unlisted low findings were reviewed.

A CI result applies only to its recorded source revision. Earlier branch runs
do not validate later repairs.
“Implemented” means the source contains the repair and the cited regression
describes its intended behavior. It does not mean those tests passed on the
current revision. No local tests, builds, lint, browser sessions or model runs
were performed for this record. Historical measurements remain evidence for
their recorded source snapshots, not measurements of the final integrated PR.

The product has two versions: Global Memory V1 and isolated member Memory V2.
V1 retains its retrieval, decay, capacity and automatic conflict policy. Shared
editing, transport, backup and embedding infrastructure changes are disclosed
below; “V1 unchanged” does not mean every shared component is byte-identical.

The subsequent PR review also identified an import failure that left V1's SQLite
transaction open. `set_semantic_if_absent` now rolls back record and audit writes
on failure in either version. The regression injects a failure after an actual
audit write and checks that a new transaction and a clean retry remain possible.
Channel memory failures redact host paths before showing the reason. These
repairs do not change V1's admission or conflict decisions.

A further source review found that eager allocation could create an ordinary
provider before a member's first turn established private ownership. V2 leaves
session allocation and resume to the real turn instead of speculating before
that validation. Restored store identity and concurrent slot changes are checked
before allocation. Global and valid named V1 stores retain eager behavior. The
existing runtime isolation-mismatch refusal remains intact; the regression
coverage in `test/test_eager_spawn.py` awaits CI execution.

CodeQL also reported four inherited cron regex performance alerts. Wildcard
presence and assignment-boundary scans now avoid repeated suffix searches while
preserving the existing refusal limits and assignment captures. Boundary
regressions cover long unmatched brackets, long whitespace and the exact limits.
Two wildcard alerts no longer appear in the next analysis. The two assignment
alerts still appear, but their reported repeated-name input cannot restart the
name scan at an interior position because the boundary lookbehind refuses it.
The additional history-path alert reaches a constructor that replaces path
separators and drive colons, then appends `.jsonl` to one basename under a fixed
session directory. That disproves the reported request-driven path traversal;
it does not prove protection from independently planted host symlinks. Each
remaining alert has its own source-flow response on the PR. None was dismissed,
and this record does not claim that CodeQL passed.

## Withdrawing V2 without reverting shared repairs

The release is one commit as requested. A whole-commit revert also removes the
shared embedding, permission, editing and cron repairs. V2 has no runtime
kill-switch and no released earlier V2 implementation to select. The following
is a release-engineering rollback plan, not an available dashboard action or a
claim that an emergency build has been tested.

1. Stop the gateway and its scheduled/delegated work. Preserve an owner-only
   copy of the data home while writers are stopped, including configuration,
   binding records, every store, restore journals and recovery copies. Record
   the installed source and backup checksums. Do not open V2 databases with an
   older V1 binary or change their lineage markers.
2. Branch from the installed release and make a narrow withdrawal patch. In
   `memory_stores.py`, refuse new allocations in `provision_member_memory` and
   member execution in `require_member_memory_store` with an explicit temporary
   unavailability reason. In `require_memory_store`, refuse the branch for a
   declared private owner or V2 record, including calls that skip directory
   validation. Keep the explicit Global return and named V1 branch intact.
   Separately refuse private owner mutations in the backup, restore, cancel and
   prune entry points: those paths can validate identity directly and do not
   all pass through `require_memory_store`. Preserve owner status/list reads.
   The withdrawal patch must cover both the runtime guards and these direct
   administrative writers. It is intentionally a temporary service withdrawal,
   not a migration or a weaker isolation mode.
3. Keep the database schema, ownership manifests, session/PID checks, sandbox
   fences, shared worker, V1 policies, permission fixes, cron fixes and Email
   removal intact. Do not revert whole shared files. In
   `apply_pending_member_restores`, skip private pending-restore activation
   before calling `apply_pending_restore`, without rewriting its journal. That
   startup path validates identity directly and is not fenced by the store
   guards alone. Leave all member data in place, and explicitly select the
   `default` assistant for new V1 work.
4. Require CI on the withdrawal patch to exercise Global and named V1 chat and
   recall, refusal of private DM/Crew/schedule/resume, refusal of provisioning
   and private HTTP mutations, and preservation of all V2 files and journals.
   Ship only that reviewed patch. This document supplies no execution evidence
   for such a build.
5. Re-enable V2 by removing only the withdrawal guards after the underlying
   defect is fixed and the same compatibility, isolation and recovery checks
   pass. Restart with the retained bindings and stores. Do not replace the
   whole data home with the earlier snapshot, which would discard newer V1
   work; use that snapshot only for explicit, scoped recovery if needed.

This plan retains the shared repairs and avoids converting private data. Its
cost is a reviewed maintenance release and temporary V2 unavailability. A live
configuration toggle or automated downgrade is outside the implemented scope.

## Upgrade communication for the release

Existing non-default members require the owner's **Initialize private memory**
action, including a member selected as the default assistant. Until then its
chat refuses with that action named in the message. Initialization creates an
empty private store; existing V1 records are retained for an explicit copy.
The installation guide names the action and the browser scenario covers refusal,
initialization and retained Global/peer records. Current screenshots still require
a completed CI attempt.

The release PR should carry this upgrade instruction in its changelog. This
feature PR follows the repository rule that only a version-bump PR writes
`CHANGELOG.md`; it does not claim a release note has already shipped.

## Blocking and high findings

| ID | Disposition and source rationale |
| --- | --- |
| **B1: Linux Global MCP provenance and stale PIDs** | **Implemented.** Global sandbox children can prove the namespace pair published by their trusted launcher, instead of being compared only with the host namespace. Process start identities are checked before and after namespace inspection to reject reused PIDs. An unverifiable caller still cannot borrow Global authority. See `protected_member_session_for_pid` and `_matches_published_sandbox_namespace` in [member_memory_auth.py](../../../../../src/kiro_crew/member_memory_auth.py). |
| **H1: editable transcripts mint private authority** | **Implemented.** Private preparation requires a protected assignment. Unsigned transcript metadata cannot create one. Trusted dispatch establishes the assignment before preparing memory, and a conflicting transcript is refused. This applies to channel entry paths as well as dashboard sessions. See `store_of_session`, `prepare_store_vectors` and `inherit_session_memory` in [context.py](../../../../../src/kiro_crew/context.py), with [member API regressions](../../../../../test/test_member_memory_api.py). |
| **H2: private delegation reaches Global or a peer** | **Implemented.** Delegation and schedule creation check the protected caller identity. A member cannot assign its own work to Global or another member to read that memory by proxy. Coordinator assignment remains distinct from member self-delegation. Schedule binding and dispatch retain member ownership. Trigger text controls automatic Crew matching, not an owner-selected schedule or a member scheduling its own work. See `require_memory_delegation` in [context.py](../../../../../src/kiro_crew/context.py), [cron.py](../../../../../src/kiro_crew/cron.py) and the member API regressions. |
| **H3: a selected store is authorized, then ignored** | **Implemented.** Import writes to the selected tier. Legacy Markdown migration and automatic promotion reject unsupported private targets instead of performing a Global operation under a member label. Context preview and observability resolve their actual target. See [memory handlers](../../../../../src/kiro_crew/dashboard/handlers/memory.py) and [shared store resolution](../../../../../src/kiro_crew/dashboard/handlers/_shared.py). |
| **H4: `/proc/$PPID/root` bypasses Linux masks** | **Source-falsified hypothesis; kernel evidence pending.** The claimed escape assumes access through a host process's procfs magic link. Linux ptrace credential checks across the user-namespace boundary, followed by capability removal and the namespace-escape syscall filter, are part of this launch path. Absence of a PID namespace alone does not establish the bypass. No new PID-namespace mechanism was added solely for this claim. See [sandbox.py](../../../../../src/kiro_crew/sandbox.py). The real kernel canary remains the required execution evidence; source reasoning is not a kernel test result. |
| **H5: hidden runtime prerequisites** | **Disclosed operational contract.** Private execution requires Crew's enforceable outer OS sandbox. Native Windows is refused and directs the user to WSL/Linux. macOS requires outer Seatbelt, including disabling Kiro internal sandbox delegation where it bypasses Crew's fence. Codex ACP cannot run the required private MCP tools directly and is explicitly refused. See `_private_memory_execution_failure` in [member_memory_auth.py](../../../../../src/kiro_crew/member_memory_auth.py) and [installation guidance](../../../../guides/install.md). |
| **H6: old aliases and default-agent selections stop working** | **Intentional initialization boundary, with recovery guidance.** A non-default member must be explicitly initialized before private execution, including when selected as the default agent alias. Initialization does not adopt or convert an old V1 store. The UI provides initialization and explicit record copying; doctor reports an unavailable default binding instead of hiding it. Named V1 stores remain separately addressable. See [agent settings](../../../../../website/src/pages/KiroCrewAgentsPage.tsx), [copy API](../../../../../src/kiro_crew/dashboard/handlers/memory_member.py), [binding resolver](../../../../../src/kiro_crew/config/loader.py) and [doctor](../../../../../src/kiro_crew/cli_doctor.py). |
| **H7: one V1 soft deletion disables acceleration** | **Implemented without changing V1 ranking.** FAISS and numeric scoring operate on active vector rows and validate the active mapping. Deleted rows no longer make every later request reject the accelerated population. See the FAISS/scoring helpers in [vector_memory.py](../../../../../src/kiro_crew/vector_memory.py). |
| **H8: missing vectors receive a ranking bonus** | **Implemented for V2.** Embedded and vectorless candidates now use the same semantic/lexical weights. A missing vector contributes no semantic score; it does not promote the row merely because embedding is pending. See `rank_score` in [memory_v2.py](../../../../../src/kiro_crew/memory_v2.py). This changes the prior operating point, so historical accuracy numbers do not validate this final ranking adjustment. |
| **H9: escaped Unicode removes all recalled evidence** | **Implemented for V2.** Payload packing accounts for serialized size and trims oversized evidence instead of discarding the entire result. The final long-fragment repair also retains a bounded, identified snippet when an admitted fact or episode exceeds its section budget, with an explicit truncation flag. Full stored content is retained. Extremely small requested caps can still return no fragment. See [memory_recall.py](../../../../../src/kiro_crew/memory_recall.py) and `recall.fit` in [vector_memory.py](../../../../../src/kiro_crew/vector_memory.py). |
| **H10: private NULL vectors never recover** | **Implemented.** One gateway-owned repair loop visits cached private stores, revalidates ownership and repairs bounded pages using the existing embedding executor. It covers later seeds, queued writes and reconciliation, without creating a model just to check for work. Failed rows do not starve later rows or stores. See `_repair_member_memory` in [gateway.py](../../../../../src/kiro_crew/slack/gateway.py) and [startup regressions](../../../../../test/test_memory_startup.py). An unopened store is not eagerly scanned. |
| **H11: bad restore journals prevent recovery** | **Implemented, including the later design correction.** Status and cancellation remain owner-accessible. Invalid journals are quarantined only when independently verified current data proves cancellation safe; ambiguous rename state is preserved with named recovery files. The single deferred pass records failures per canonical store and continues. A failed member no longer blocks Global or healthy peers; failed Global initialization skips only Global migration. Cancellation preserves the failed-store fence until restart. After preparation, the owner can stage a valid backup even when current memory is unreadable. See [restore implementation](../../../../../src/kiro_crew/member_memory_backup.py), [startup state](../../../../../src/kiro_crew/memory_startup.py) and [three-store recovery regressions](../../../../../test/test_memory_startup_isolation.py). |
| **H12: three V1 conflict tests demand V2 proposals** | **Test contract corrected.** V1 keeps its existing automatic-write policy. The tests now assert the appropriate behavior for each algorithm version and use an explicit owner correction where that is the V1 operation. Production V1 was not changed to satisfy V2 proposal expectations. See [test_memory_edit.py](../../../../../test/test_memory_edit.py). |
| **H13: test temporary home remains inside real data** | **Implemented.** Root [conftest.py](../../../../../conftest.py) selects a system-temp floor independently of inherited temporary-directory variables and rejects overlap with real data homes in both ancestry directions. [Home-pin regressions](../../../../../test/test_home_pin_survives_monkeypatch_undo.py) cover hostile temp variables and parent/child paths. This is test infrastructure, not a product data migration. |
| **H14: OS isolation tests can skip the real mechanism** | **CI definitions strengthened; execution pending.** [Filesystem canaries](../../../../../test/test_member_memory_filesystem.py) exercise actual Linux namespace/procfs and macOS Seatbelt behavior. [CI](../../../../../.github/workflows/ci.yml) requires the Linux namespace probe and checks expected V1/private cases for both platforms without accepting skips. This does not certify every operator kernel, sandbox policy or backend. Runtime preflight still refuses unsupported private execution. |
| **H15: thresholds presented as calibrated** | **Claim narrowed.** The 0.62/0.57 floors remain provisional values informed by the same corpus used for scoring, not held-out validation. Near-threshold cases and repeat-run cosine variation limit the conclusion. V2 diagnostics report active, stored and reference identities, and label custom/registered or unknown models as unvalidated. Matching signatures prove declared model ID and dimension only. See the [algorithm report](algorithm-effectiveness-report.md) and `operating_point` in [memory_recall.py](../../../../../src/kiro_crew/memory_recall.py). |
| **H16: package sync persists members without stores** | **Implemented.** Package synchronization persists member records and their store ownership together under the config mutation lock. Cache cleanup follows the identities actually removed by the committed update. See the sync path in [agents.py](../../../../../src/kiro_crew/dashboard/handlers/agents.py) and [memory_stores.py](../../../../../src/kiro_crew/memory_stores.py). |
| **H17: reinstall collides with retained ownership** | **Implemented with data preservation.** Deleted or pruned members retain archived stores for owner recovery. Recreating the same display name allocates a fresh private identity; it cannot silently rebind the previous store. Archived records are excluded from automatic backups and normal runtime access. See `provision_member_memory`, `active_store_names` and `persist_member_config` in [memory_stores.py](../../../../../src/kiro_crew/memory_stores.py). |

## Second review round

The supplied [round-two synthesis and disposition tracker](fable-round-2-resolution.md) records N1 through N22 against PR revision `201eb6e1`. It distinguishes reported observations, source repairs and pending CI evidence. The original per-lane files were not supplied.

## Grouped medium findings

The final recovery correction also covers cached and directly constructed
Markdown, vector and JSONL lesson stores, including named V1 stores. Healthy
stores do not inherit another store's failure. The dashboard returns `null` for
unavailable Global lesson counts instead of reporting zero or failing the recovery
shell. See [lesson access regressions](../../../../../test/test_memory_startup_lessons.py)
and `_count_lessons` in [dashboard state](../../../../../src/kiro_crew/dashboard/state.py).

**Filesystem isolation and provenance: implemented, with explicit trust costs.**
The private view withholds Global snapshots, shared sessions and broker namespaces,
including later atomic replacements. Private execution rejects protected memory
hard links, and private database admission rejects multiple links to one inode.
A durable private database marker prevents a missing manifest from reopening an
established V2 database under V1 policy. Snapshot validation checks that marker
and its owner before replacing current memory; older markerless snapshots retain
their documented compatibility path. See [sandbox.py](../../../../../src/kiro_crew/sandbox.py),
[vector_memory.py](../../../../../src/kiro_crew/vector_memory.py) and
[member_memory_backup.py](../../../../../src/kiro_crew/member_memory_backup.py).

Unverifiable internal callers are intentionally refused once private boundaries
are active. A shared secret alone cannot authorize Global impersonation. Verified
Global callers and the authenticated owner dashboard retain their access.
OS process lookup and proof verification still have per-request costs. Gateway
MCP dispatch uses the existing subprocess executor for these checks without a
new per-call deadline. Shared-pool saturation is an operational limitation, not
a performance issue this PR has demonstrated solved. See
[member_memory_auth.py](../../../../../src/kiro_crew/member_memory_auth.py) and
[gatewayd.py](../../../../../src/kiro_crew/mcp_gateway/gatewayd.py).

**Continuation and lifecycle routing: implemented.** Protected assignment follows
hooks, control paths, TaskRunner continuations, delegated runs and private
consolidation. A legacy Crew retry with lost run identity refuses instead of
respawning against Global. Deletion releases cached SQLite, FAISS, Markdown and
lesson resources while retaining owner-recoverable files. Re-creation uses a
fresh store. Retained files and backup listings remain available to the owner,
but restoration still requires an active exclusive member binding. This PR does
not provide an archive reattachment or archived-store restoration workflow.
See [context.py](../../../../../src/kiro_crew/context.py),
[crew_chat.py](../../../../../src/kiro_crew/crew_chat.py),
[agents.py](../../../../../src/kiro_crew/dashboard/handlers/agents.py) and
[lifecycle/startup specification](../../../../system-specs/modules/slack-gateway.md).

**Pre-provider retries and essential guidance: implemented.** Environment failures
before an LLM call arm the existing durable consolidation backoff. Private profile
writes validate the assembled essential-context budget before committing, under
the same lock as the write, so an accepted preferences/projects update does not
make the next turn unusable. See
[history_consolidation.py](../../../../../src/kiro_crew/history_consolidation.py)
and `write_private_profile_validated` in [memory.py](../../../../../src/kiro_crew/memory.py).

**Shared embedding behavior: repaired and disclosed.** Model replacement reconciles
cached named stores as well as Global, including stores opened while the candidate
loads. Generation checks prevent old-space results from being committed after a
swap. The unwanted two-thread clamp was removed; explicit thread settings are
honored up to available CPUs, and the native-thread default remains four. One
shared inference worker and its bounded queue serve V1 and V2. No measured
latency improvement is claimed from that scheduling change. The knowledge library derives its signature from
the same model/dimension identity, so identity changes can require a substantial
re-embedding pass. A bounded background pass visits the active Global handle and
already-open named V1/V2 stores, revalidating readiness and ownership each time.
It repairs up to 16 rows per kind per visit, advances past an unavailable store,
and leaves Global to its boot migration until that task finishes. It does not
open idle stores or load an absent model. Existing startup/import repair remains
available; V1 retrieval, admission, decay and capacity decisions stay unchanged. See
[embedding model apply](../../../../../src/kiro_crew/dashboard/handlers/memory.py),
[embeddings.py](../../../../../src/kiro_crew/embeddings.py) and the
[shared memory specification](../../../../system-specs/modules/memory-skills-hooks.md).

**Audit retention and installation permissions: disclosed shared changes and limits.**
Both versions receive additive record/revision metadata. Revision snapshots and
proposals have no automatic retention limit or purge UI, so storage can grow even
when V1 live records are capacity-bounded. Forgetting a record does not erase those
audit snapshots. Data-home initialization tightens owner permissions on POSIX and
Windows, which can remove other users' access to a deliberately shared home. The memory
security scan covers multiple stores, lessons and revisions. These are shared
management/security changes, not a V1-to-V2 migration. See
[revision contract](../../../../system-specs/modules/memory-skills-hooks.md) and
[ensure_data_home](../../../../../src/kiro_crew/config/paths.py), plus `scan_memory`
in [security](../../../../../src/kiro_crew/security/__init__.py).

**Resource growth: partial repairs with retained limits.** Markdown snapshots now
validate ownership once per bounded snapshot while retaining per-file inode,
link and containment checks. Dashboard file reads run off the event loop.
Deletion evicts caches. Automatic backups visit only active member V2 stores;
they do not copy or prune Global or named V1 backups. Explicit manual backups
remain available for both versions. Archived private stores are excluded.
The first eligible heartbeat schedules one tracked backup pass; large ZIP work
does not occupy the heartbeat tick, and shutdown stops before another store or
pruning after the current atomic copy. See [resource regressions](../../../../../test/test_memory_resources.py).

V2 candidate retrieval still scales with the active population. The synthesis's
10,000/100,000-row latency and memory figures were reviewer measurements, not
new measurements made here. No sublinear-search or constant-memory claim is made.
Superseded restore copies remain outside `backup_keep` retention because journal
absence, timestamps and UUID names cannot prove an ambiguous recovery is safe to
delete. They require explicit owner cleanup. These limits remain in the current
scope; this record does not promise an untracked follow-up implementation.
The startup state belongs to one gateway lifetime. V2 restore admission also coordinates with live product store users through a lock outside the directory being replaced. This is a product-writer contract; arbitrary external programs that bypass it are not admitted writers. Source changes and their cross-platform CI evidence are tracked in the [second review resolution](fable-round-2-resolution.md).

## Frontend, test gates and evidence

The current UI retains Global V1's semantic and episodic browsers. Its owner bulk
editor mounts only when opened, avoiding an owner-only request on an ordinary
visit. Legacy schedule attribution remains supported alongside protected member
identity. These are compatibility repairs, not removal of existing V1 surfaces.
See [MemoryTab.tsx](../../../../../website/src/pages/overview/MemoryTab.tsx) and
[wakesCrew.ts](../../../../../website/src/components/crew/wakesCrew.ts).

| Grouped finding | Current disposition and remaining evidence |
| --- | --- |
| Memory drill-in absent from locale rendering | **Coverage source added.** The populated member-memory surface and owner-bound fact/episode fixtures appear in [i18n surfaces](../../../../../website/scripts/lib/i18n-surfaces.mjs) and [render checks](../../../../../website/scripts/check-i18n-render.mjs). No current rendered result or verification of the reported “183 strings across 12 locales” count is claimed here. |
| Reflection bypasses the seam gate | **Implemented for the reported literal forms.** [Seam scanner](../../../../../scripts/check_memory_store_seam.py) and [self-test](../../../../../test/test_memory_store_seam.py) cover `getattr`, `operator.methodcaller`, `vars(...)[...]` and `__getattribute__`. A syntactic scanner is not proof against arbitrary computed reflection. |
| Benchmark result JSON ships with the app | **Packaging rules corrected.** [setup.cfg](../../../../../setup.cfg) and [MANIFEST.in](../../../../../MANIFEST.in) exclude the member benchmark and editing-scale outputs while retaining the runtime golden fixture. Built-package inspection and the reviewer's exact size figure are not verified here. |
| FAISS tests always skip | **Current-source counterexample.** [CI](../../../../../.github/workflows/ci.yml) installs pinned FAISS in a dedicated environment and requires six cases with no skips, failures or errors: four V1/V2 invalidation cases and two V1 cases that verify NumPy and native FAISS scoring still execute after a record becomes ineligible. Whether that lane passes belongs to the current CI result. |
| CLI, retirement and install behavior is undisclosed | **Documentation corrected.** [CLI specification](../../../../system-specs/modules/cli.md) and [CLI help](../../../../../src/kiro_crew/cli.py) now describe active-store backups, staging for both versions and cancellation/restart behavior. The [memory specification](../../../../system-specs/modules/memory-skills-hooks.md) covers scoped retirement routes; the CLI lists provisioning, retired and carve. [Install guidance](../../../../guides/install.md) distinguishes V1/V2 recall and thread defaults. |
| Benchmark execution metadata was added later | **Historical evidence qualified; new instrumentation added.** [CI benchmark runner](../../../../../scripts/ci-member-memory-benchmark.py) records checkout/PR identity, source, model/runtime and output hashes plus execution status. Those new fields do not retroactively turn earlier publication annotations into instrument-generated evidence. The final ranker and payload fixes need their own result. |

Historical benchmark and media evidence must keep its original revision and
scope. The [media record](../../../../../temp-screenshots/memory-v2/README.md)
identifies the retained local pre-squash source and links a durable archive of
four historical source files, measured payload, log and publication metadata.
It is a partial source archive, not a complete environment lock. The earlier
remote-lookup failure and older media commit attribution were not independently
replayed for this document. The corrected record does not promise a public commit
URL or claim that historical media shows later repairs.

New [Playwright captures](../../../../../website/playwright/member-memory.spec.ts)
record the checkout, CI run, outcome and synthetic-gateway scope. Screenshots and
video remain requested review evidence outside the packaged app; repository
weight is still a tradeoff. Neither old nor new demo media establishes live-model
answer quality or a Crew delegation run that the recording did not exercise.

The remaining acceptance evidence is the remote CI outcome for the integrated
revision, including actual OS canaries, recall/payload checks, shared V1 behavior,
recovery and UI flows. This document records dispositions and their limits; it is
not an all-green or exhaustive-review certificate.
