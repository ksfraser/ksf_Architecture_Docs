# FR-ACL-010-03 — The three lifecycle events and post-commit ordering

@BABOK Related: BR-ACL-010 R3, R6, BABOK 8.2 Solution Analysis
Status: **Proposed**
Module: `ksf_FA_RBAC` (emitter), `ksf_FA_*` (responders)
Date: 2026-10-14
Depends on: `AGENTS_ARCH.md` §10.1 (the verified FA lifecycle hook map)

> **Documentation only.** No hook was wired and no responder was registered.

---

## 1. Post-commit is a hard requirement

> **[D]** The framework emits its three events **after the transaction commits**, never
> before.

**The reason is not tidiness.** An ACL row written inside a transaction that later
rolls back is a **dangling ACL row** — the framework manufacturing, on every failed
write, precisely the orphaned-record condition R6 exists to detect. The sweeper would
then have to clean up after the framework that exists to keep the data clean.

### 1.1 The verified mechanism, and its trap

**[V]** `AGENTS_ARCH.md` §10.1 (*FA lifecycle hooks — the verified map*, verified
2026-10-08 against FA 2.4.3) records:

| Event | Dispatcher | Payload |
|---|---|---|
| Sales order / quote write | `hook_db_prewrite` / `db_postwrite` | `$cart`, `ST_SALESORDER` / `ST_SALESQUOTE` |
| Sales delivery write | same | `$cart`, **`ST_CUSTDELIVERY` (13)** — *not* `ST_SALESDELIVERY` |
| Sales invoice write | same | `$cart`, `ST_SALESINVOICE` |
| Credit note | same | `$cart`, `ST_CUSTCUSTOMERCREDIT` |
| Customer payment | same | `$args`, `ST_CUSTPAYMENT` |
| **Void** | `hook_db_prevoid` | `($trans_type, $trans_no)` — fires in **13** places |

`hook_db_postwrite` is the **verified** post-commit-adjacent mechanism. Two constraints
from the same section are binding on responders and are reproduced here because getting
them wrong is expensive:

1. **Never `exit` from `db_postwrite`.** In `write_sales_delivery()` the order is
   `hook_db_postwrite` at **line 200** and `commit_transaction()` at **line 201**.
   Terminating the request there leaves the delivery uncommitted. A responder that
   redirects or calls `exit` from these hooks **corrupts the write**.
2. **`hook_db_prewrite` responders cannot abort a write.** `write_sales_delivery()`
   ignores the dispatcher's return value.

**[V] Correction to the brief's framing.** `hook_db_postwrite` is described in
`AGENTS_ARCH.md` §10.1 as firing **before** `commit_transaction()` in at least the
sales-delivery path. So it is **post-write, not reliably post-commit**. This FR's
ordering requirement is therefore stated against a *verified* post-commit point rather
than against this hook name — see §3.

### 1.2 Scope limit that must not be glossed

**[V]** These core hooks are **cart/transaction scoped, not per-row CRUD**. They fire
for the sales document types listed above and nothing else. They are **not** a general
"a row changed" notification, and there is no per-row CRUD hook in FA core.

**Therefore the two event sources are different things and must not be conflated:**

| Event | Source |
|---|---|
| `record_changed` for a sales document | FA core's `db_postwrite` — verified, transaction-scoped |
| `record_changed` for **any other module's** row (CRM contact, HRM employee, PM task) | **The framework's own emitter at its own commit point** — not provided by FA core |

**[UNVERIFIED]** — whether a single framework-level post-commit hook can be placed for
non-cart writes at all, given that most module writes use bare `db_query()` without an
explicit transaction. If they do not, "post-commit" degrades to "post-statement, no
transaction to roll back", which is safe but must be stated rather than assumed.
**Q-ACL-010-3** — this is the single largest unverified assumption in this set.

## 2. The three events

**[D]** Payloads below are the **agreed minimum**. Field names are indicative; the
*set* is the requirement.

### 2.1 `record_changed`

> Fires at the CRUD boundary when a governed record is created, updated or deleted.

| Field | Meaning |
|---|---|
| `module`, `record_type`, `record_id` | The record identity, matching the ACL key triple |
| `action` | `create` \| `update` \| `delete` |
| `user` | Acting user (`user_id`, the **string** natural key — see BR-ACL-010 §3.2) |

| Consumer | Responsibility |
|---|---|
| **Audit log** | Append to `0_rbac_audit_log`. **[V]** the table exists and is currently empty. |
| **Ownership evaluation** | Hand to the module's registered transition responder ([FR-ACL-010-04](./FR-ACL-010-04-ownership-transitions-and-provenance.md)). |

**Ordering constraint:** the audit-log consumer must be **registered before** the
ownership consumer, so the audit row exists even if ownership evaluation throws.
`hook_invoke_all` gives no ordering guarantee across modules **[UNVERIFIED]** — this is
resolved by making the two *separate, sequentially-called* dispatches rather than one
broadcast. **Q-ACL-010-6.**

### 2.2 `user_changed`

> Fires when a user's identity, team membership or status changes.

| Field | Meaning |
|---|---|
| `user_id` | The user |
| `change_type` | e.g. `team_membership` \| `deactivated` \| `removed` |

| Consumer | Responsibility |
|---|---|
| **Ownership recalculation** | Re-evaluate group-derived ownership. |
| **Orphan sweeper** | Re-scan records whose only ownership came from that user. |

**[V] Blocker.** "User removed" is currently **not a detectable event**: no FA code path
sets `0_users.inactive`, and `delete_user()` **hard-deletes the row**. See
[BR-ACL-010](./BR-ACL-010-event-driven-ownership.md) §3.1. This event is required; it
**cannot be fully delivered** until Q-ACL-010-4 is answered.

### 2.3 `orphaned_record`

> Fires when a governed record has no resolvable owner.

| Field | Meaning |
|---|---|
| `module`, `record_type`, `record_id` | The record |
| `previous_owner` | Last known owner, if any |

| Consumer | Responsibility |
|---|---|
| **Admin queue** | The visible bucket (R6). |
| **Task-filing responder** | Files a review task — **by capability, not by table access** ([BR-CAL-010](./BR-CAL-010-capability-contract.md)). |

> **This is the concrete reason BR-CAL-010 exists.** The task-filing consumer needs to
> create a task in the Calendar and has **no business** knowing Calendar's schema or
> reading `0_fa_cal_entries`. It asks Calendar to create one; Calendar renders nothing and
> creates it.

## 3. Ordering requirement

**[D]** Within a single governed write:

1. The **data write** completes.
2. The transaction **commits**.
3. **Then** the three events fire, each dispatched **once**.

| Prohibited | Consequence |
|---|---|
| Firing before commit (§1) | Dangling ACL row on rollback |
| Firing more than once per write | Duplicate ownership transitions; an idempotency requirement nobody asked for |
| A responder `exit`ing (§1.1) | Uncommitted write — data loss |
| A responder depending on another responder's side effects | Ordering is not guaranteed **[UNVERIFIED]** |

## 4. Dispatch mechanism

**[D]** Use FA's existing `hook_invoke_all` / `hook_invoke_first` — zero new dispatcher
infrastructure, consistent with `AGENTS_ARCH.md` §11.

| Dispatch | Used for | Why |
|---|---|---|
| `hook_invoke_all` | `record_changed` | Every responder must see it |
| `hook_invoke_first` | `orphaned_record` | First responder to claim it should handle it; **`null` = "not mine"** (R4) |

**[UNVERIFIED]** — whether `hook_invoke_first` treats a `false` return as "stop" or as
"not handled", and therefore how a responder declines without being mistaken for a
success. **Q-ACL-010-6.** The R4 "return `null` to decline" convention is only safe if
`null` is genuinely the non-claiming value in the installed FA version.

## 5. Acceptance criteria

| # | Criterion |
|---|---|
| AC1 | A write that is rolled back emits **no** `record_changed`. |
| AC2 | A committed write emits exactly one `record_changed`. |
| AC3 | A responder that calls `exit` causes an observable **failing test**, not a silent commit loss. |
| AC4 | An audit row exists for every `record_changed`, even when ownership evaluation throws. |
| AC5 | A responder returning `null` leaves the event to the next responder. |
| AC6 | An `orphaned_record` produces exactly one admin-queue entry and at most one filed task. |
| AC7 | No responder causes an ACL row to exist for a record that does not exist. |
| AC8 | A `delete` emits `record_changed` with `action = delete` **and** the ownership rows are retired — not orphaned. |

## 6. Explicitly unverified

| Item | Status |
|---|---|
| That a single post-commit point exists for non-cart module writes | **[UNVERIFIED]** — §1.2. The largest assumption here. |
| FA hook dispatch ordering across modules | **[UNVERIFIED]** |
| `hook_invoke_first` decline semantics | **[UNVERIFIED]** |
| Whether any module's writes are transactional at all | **[UNVERIFIED]** — ~1,510 `db_query(` call sites were never audited for transaction wrapping. |

## 7. Related

- `AGENTS_ARCH.md` §10.1 — the verified hook map and the two traps
- [BR-ACL-010](./BR-ACL-010-event-driven-ownership.md) §3.1 — the `0_users.inactive` blocker
- [FR-ACL-010-04](./FR-ACL-010-04-ownership-transitions-and-provenance.md)
- [BR-CAL-010](./BR-CAL-010-capability-contract.md) — the `orphaned_record` task responder