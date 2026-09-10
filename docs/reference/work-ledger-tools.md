# `@kirocrew-work` tools — quick reference

**This page is not a mirror.** It is Kiro Crew's own reference for the four work-ledger MCP tools, authored locally and derived from the code in this repository. Preserve it across any re-fetch of this directory.

The server is `kirocrew-work` (version `1.0.0`), opt-in rather than always-on: a spec that wants the set hand-builds the `mcpServers` entry and adds `@kirocrew-work` to `tools`. It carries no `autoApprove` key, so every call still reaches the `hooks.on_tool_call` gate.

All four tools are advertised to every caller and dispatch by resolved identity at call time, so one session can be a worker to its parent and a conductor to its own children. A caller with a binding file but no ledger directory gets the worker pair and `no_ledger` from the conductor pair; a caller with a ledger directory but no binding gets the reverse; a second-level conductor gets all four; a caller with neither gets `not_bound` / `no_ledger`.

Identity is resolved, never supplied. Every tool routes through `mcp_core.require_strict_session_key`, and no tool takes a session key, a conductor id, or an item id from the worker side. A subagent, which inherits no strict identity, gets a plain error string rather than a coded refusal.

Source: `/workspace/KiroCrew/src/kiro_crew/mcp_work.py`

## `work_brief` — worker

Called by the **worker**. Reads the one item this session was dispatched for: title, acceptance, round, the conductor's latest decision, and the worker's own last reported status. Backed by `GET /api/work-ledger/brief`.

| Parameter | Type | Required | Caps |
|---|---|---|---|
| _(none)_ | — | — | The `inputSchema` has no properties; the item is resolved from the caller's own binding. |

Error codes:

| Code | HTTP | Condition |
|---|---|---|
| `internal_auth_required` | 403 | The caller is not the gateway's internal-secret principal (a browser caller). |
| `restricted_session` | 403 | Incognito, temporary, or guest session. |
| `channel_session` | 403 | The caller is a channel session, or has an outbound channel mirror — re-checked after the read, so a mirror added mid-call still refuses. |
| `not_bound` | 403 | The caller has no binding file, so it is not a dispatched worker. |
| `unknown_item` | 404 | The binding names an item that is gone or unreadable. |

Sources: `/workspace/KiroCrew/src/kiro_crew/mcp_work.py`, `/workspace/KiroCrew/src/kiro_crew/dashboard/handlers/work_ledger.py`

## `work_report` — worker

Called by the **worker**. Writes a schema-bounded status against its own item; nothing here can write a verdict, a state, or an acceptance condition, because no parameter carries one. Backed by `POST /api/work-ledger/report`.

| Parameter | Type | Required | Caps |
|---|---|---|---|
| `status` | string | yes | One of `progress`, `done`, `blocked`, `question`. |
| `summary` | string | yes | ≤ 500 characters, refused rather than truncated. |
| `artifacts` | object | no | String→string map, ≤ 16 keys, key ≤ 64 characters, value ≤ 512 characters. |
| `pr` | integer | no | 1 to 1,000,000,000. A claim only — it does not move the item's acceptance bar. |

Error codes, in addition to the four gate refusals `work_brief` shares (`internal_auth_required`, `restricted_session`, `channel_session`, `not_bound`):

| Code | HTTP | Condition |
|---|---|---|
| `invalid_json` | 400 | The body is not parseable JSON. |
| `invalid_body` | 400 | The body is JSON but not an object. |
| `invalid_status` | 400 | `status` is outside the four-value vocabulary. |
| `field_too_long` | 400 | A length or item-count cap was exceeded. |
| `invalid_value` | 400 | Any other schema refusal, including an unknown field name. |
| `item_closed` | 409 | The item has a terminal state, so reporting has stopped. |
| `unknown_item` | 404 | The bound item is no longer in the store. |
| `ledger_write_failed` | 503 | The write raised `OSError`; retryable. |

A null-valued key is dropped, so an omitted optional field and an explicit null mean the same thing. An unknown key is refused rather than dropped, so a worker never reads a 200 as proof its write landed where it aimed it.

Sources: `/workspace/KiroCrew/src/kiro_crew/mcp_work.py`, `/workspace/KiroCrew/src/kiro_crew/dashboard/handlers/work_ledger.py`

## `work_ledger_read` — conductor

Called by the **conductor**. Returns the conductor record, every item with all its fields, the derived `orphaned` and `stale` flags, the newest events per item (capped at 20), and an `accept_batch` document built from each item's `acceptance` alone — never from a worker's claimed `pr`. Backed by `GET /api/work-ledger`.

| Parameter | Type | Required | Caps |
|---|---|---|---|
| _(none)_ | — | — | The `inputSchema` has no properties; the ledger is the caller's own. |

`orphaned` asks whether the conductor's slot is still open. `stale` is the conjunction of "quiet past the window" and "the worker's slot has no turn in flight", so a worker in a long build is never flagged.

Error codes:

| Code | HTTP | Condition |
|---|---|---|
| `internal_auth_required` | 403 | The caller is not the internal-secret principal. |
| `restricted_session` | 403 | Incognito, temporary, or guest session. |
| `channel_session` | 403 | Channel session or outbound mirror, re-checked after the read. |
| `no_ledger` | 404 | This session owns no ledger yet; open one with `action=goal` or `action=create`. |

Sources: `/workspace/KiroCrew/src/kiro_crew/mcp_work.py`, `/workspace/KiroCrew/src/kiro_crew/dashboard/handlers/work_ledger.py`

## `work_ledger_record` — conductor

Called by the **conductor**. One action per call, because the field sets are disjoint. `goal` and `create` also bootstrap the ledger; every other action answers `no_ledger` until one exists. Backed by `POST /api/work-ledger/record`.

| Parameter | Type | Required | Caps |
|---|---|---|---|
| `action` | string | yes | One of `create`, `bind`, `decide`, `verdict`, `close`, `goal`, `accept`. |
| `item_id` | string | no | ≤ 16 characters, must match `^it_[0-9a-f]{8}$`. Required by every action but `create` and `goal`. |
| `title` | string | no | ≤ 200 characters. `create`. |
| `acceptance` | object | no | Stored verbatim. `create` and `accept`. |
| `worker_session_key` | string | no | ≤ 512 characters. `bind`. |
| `decision` | string | no | ≤ 2000 characters. `decide` and `close`. |
| `verdict` | string | no | One of `pass`, `fail`, `pending`, `refused`, `error`. `verdict`. |
| `state` | string | no | The tool's own schema offers `accepted`, `rejected`, `abandoned`; the validation schema also admits `open`. `close`. |
| `goal` | string | no | ≤ 2000 characters. `goal`. |
| `round` | integer | no | 0 to 1,000,000. `goal`, `decide`, `create`. |
| `fails` | integer | no | 0 to 1,000,000. `verdict`. |

A field an action has no use for is generally ignored rather than refused, so a 200 is not proof every field sent was read. The store refuses only where a wrong field would change meaning — a `round` on an action that carries none, or a `verdict` or `state` outside its vocabulary, is `invalid_value`.

Error codes:

| Code | HTTP | Condition |
|---|---|---|
| `internal_auth_required` | 403 | The caller is not the internal-secret principal. |
| `restricted_session` | 403 | Incognito, temporary, or guest session. |
| `channel_session` | 403 | Channel session or outbound mirror. |
| `invalid_json` | 400 | The body is not parseable JSON. |
| `invalid_body` | 400 | The body is JSON but not an object. |
| `invalid_action` | 400 | `action` is missing or outside the seven-value vocabulary. |
| `field_too_long` | 400 | A length or item-count cap was exceeded. |
| `invalid_value` | 400 | Any other schema or store refusal, including an unknown field name. |
| `no_ledger` | 404 | Any action but `goal` and `create`, before a ledger exists. |
| `unknown_item` | 404 | `item_id` names no item in this ledger. |
| `unknown_worker_session` | 404 | `bind`: that worker session is not open. |
| `already_bound` | 409 | `bind`: the item already holds a binding. |
| `worker_already_dispatched` | 409 | `bind`: that worker session has been bound before. One binding per session, ever. |
| `worker_not_owned` | 403 | `bind`: the worker session was not created by this conductor. |
| `worker_cross_workspace` | 403 | `bind`: the worker session is in a different workspace. |
| `item_closed` | 409 | The item has a terminal state. |
| `item_cap_exceeded` | 409 | `create`: the conductor is at its item cap. |
| `depth_exceeded` | 409 | Bootstrapping would nest a ledger past the depth cap. |
| `parent_unreadable` | 409 | Bootstrapping from a bound session whose conductor's own record cannot be read, so the depth cannot be established. |
| `ledger_write_failed` | 503 | The write raised `OSError`; retryable. |

Sources: `/workspace/KiroCrew/src/kiro_crew/mcp_work.py`, `/workspace/KiroCrew/src/kiro_crew/dashboard/handlers/work_ledger.py`

## Codes shared by all four

Every one of the four routes first passes the recognition gate, which contributes its own refusals: `missing_session_key` (400) when no `X-Session-Key` is sent, `unknown_session` (400) when the key names no known session, and `restricted_session` (403) for a persisted-mode block.

A store code absent from the route layer's status map degrades to 400 rather than 500, because every store code is a caller-input failure. Refusal bodies always carry `error`, `code`, and `field` (null where there is none); the MCP layer quotes `code` and `field` into the string the model reads, so a caller dispatches on the code rather than parsing prose.

Sources: `/workspace/KiroCrew/src/kiro_crew/dashboard/handlers/work_ledger.py`, `/workspace/KiroCrew/src/kiro_crew/dashboard/handlers/cron.py`
