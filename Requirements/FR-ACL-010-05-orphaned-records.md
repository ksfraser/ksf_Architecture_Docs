# FR-ACL-010-05 — Orphaned records: the bucket and the three causes

@BABOK Related: BR-ACL-010 R6, R7, BABOK 8.2 Solution Analysis, 9.3 Requirements Analysis
Status: **Proposed**
Module: `ksf_FA_RBAC` (bucket, sweeper), admin UI (queue)
Date: 2026-10-14

> **Documentation only.** No table was created, no migration was written, and no schema
> was changed.

---

## 1. Requirement — the orphaned bucket

> **[D] A record with no resolvable owner goes to an explicit, admin-visible bucket.**

### 1.1 Why neither shortcut is acceptable

| Shortcut | How it fails |
|---|---|
| **Silently deny** | Presents to the user as **data loss**. Support tickets read "my contacts disappeared", and no amount of log-reading reassures them. |
| **Silently allow** | Presents as a **breach**. The single moment the system is most likely to be in an inconsistent state is the moment it is most permissive. |

The bucket is the third option: the record is neither granted nor hidden by accident —
it is **surfaced to someone whose job is to decide**. This is also what makes R7's three
causes tractable, because the admin has to classify it anyway.

### 1.2 Bucket requirements

| # | Requirement |
|---|---|
| 1 | The bucket is **visible in the admin UI**, not queryable only by SQL. An operator who cannot see it will not clear it. |
| 2 | Each entry records `module`, `record_type`, `record_id`, time first seen, and last-known owner if any. |
| 3 | An entry is **idempotent**: one row per record, updated not duplicated, or the admin queue is unusable within a day. |
| 4 | Resolving an entry **dismisses** it and records who resolved it and how. |
| 5 | The bucket is **company-scoped**. Ownership rows are per-company (`TB_PREF`); a shared global bucket would leak across entities. |

**[UNVERIFIED]** — whether the bucket is a dedicated table, a projection over
"governed records with no ownership row", or a flag on a claims table. A projection is
always correct and always slow; a table is fast and can drift. **Q-ACL-010-8.**

## 2. The orphan sweeper

**[D]** A sweeper scans for governed records with no resolvable owner and routes them to
the bucket.

| Property | Requirement | Reason |
|---|---|---|
| Trigger | Manual admin action **and** a scheduled pass | Manual for correctness on demand; scheduled so corruption is found without someone noticing |
| **Never auto-grants** | The sweeper's only output is a bucket entry | Auto-granting makes the sweeper a silent security hole |
| Never auto-deletes | — | Deleting business data as a side effect of an ACL sweep is unacceptable |
| Idempotent | Re-running changes nothing already bucketed | It will be run repeatedly; non-idempotence makes it dangerous |
| Records its own run | Count scanned, count bucketed, count already present | Otherwise it is an invisible process |

## 3. Three causes, three treatments

**[D]** BR-ACL-010 R7. "Unowned" is one state with **three distinct causes**, and
treating them uniformly is how a system ends up either masking real corruption or
mass-reassigning legitimate records.

| Cause | How it arises | Detection | **Treatment** |
|---|---|---|---|
| **(a) ACL just enabled** on a table | The table had 40,000 rows and no ownership rows before the toggle flipped | The admin action that enabled it is a **known, deliberate event** | **One-time bulk assign migration** |
| **(b) Data corruption** | A lost write, a deleted parent, a manual `DELETE` outside the framework | Not directly detectable — it presents *identically* to (a) at query time | **Route to the admin bucket** (§1) |
| **(c) User removed** | The owner identity no longer exists | Not detectable — see §4 | **Cascade reassign on deactivation** |

### 3.1 Why (a) must not be handled by the sweeper

**[D]** Cause (a) is **entirely predictable and entirely known at the moment it happens**:
the admin just enabled ACL on a specific table. Running the sweeper against it would
bucket 40,000 legitimate, correctly-owned-in-practice records as "corrupt", which
destroys the signal the bucket exists to carry. It is a **migration**, and it is the
only one of the three that should be automated end to end.

**Requirement:** enabling ACL on a table **must offer** the bulk assign as part of the
same operation, and must record which tables have been migrated.

### 3.2 Why (c) cannot be built yet

**[V]** See [BR-ACL-010](./BR-ACL-010-event-driven-ownership.md) §3.1. `0_users.inactive`
**exists** as a column but **no FA code path writes it**, and `delete_user()` hard-deletes
the row. So:

- there is no deactivation event to hang a cascade on;
- a hard delete leaves ownership rows pointing at a `user_id` that no longer exists —
  i.e. it manufactures cause (b) out of what was cause (c).

Cascade reassign on deactivation therefore **requires a soft-delete path first**. That is
a change to FA core's user maintenance, which is outside this requirement set, and it is
tracked as **Q-ACL-010-4**.

## 4. What the sweeper can and cannot distinguish today

Stated plainly, because it constrains what the bucket can promise:

| Question | Answerable? |
|---|---|
| Is this record governed and ownerless? | **Yes** |
| Is it owned by a `user_id` that no longer exists in `0_users`? | **Yes** — and this is the *only* cause that can be positively identified |
| Is it cause (a) — ACL just enabled? | **No**, at query time. Only the enabling event knows. §3.1. |
| Is it cause (b) — corruption? | **No.** It is the residual after (a) and (c) are excluded, which is a *definition*, not a detection. |

**[UNVERIFIED]** — how expensive the "owner `user_id` does not exist" check is at
production row counts, and whether it belongs in the same pass as the ownership scan or
is a separate query. **Q-ACL-010-8.**

## 5. Acceptance criteria

| # | Criterion |
|---|---|
| AC1 | A governed record with no ownership row appears in the admin bucket, and is **not** silently denied and **not** silently granted. |
| AC2 | The sweeper run twice in a row produces no duplicate bucket entries. |
| AC3 | The sweeper never creates an ownership row and never deletes a business record. |
| AC4 | Enabling ACL on a table with existing rows offers the bulk assign in the same operation. |
| AC5 | A record whose owner's `user_id` is absent from `0_users` is identified as such and labelled cause (c), not cause (b). |
| AC6 | Resolving a bucket entry records actor, timestamp and resolution. |
| AC7 | Company 2's bucket contains no company 1 entries. |
| AC8 | Bucket size after enabling ACL on a populated table and completing the migration is **zero**. (Catches (a) leaking into (b).) |

## 6. Explicitly unverified

| Item | Status |
|---|---|
| Bucket storage mechanism (§1.2) | **Not decided.** **Q-ACL-010-8.** |
| Row counts for a real governed table | Never measured. AC8's "populated table" is unquantified. |
| Sweeper scan strategy at production scale | **[UNVERIFIED]** — a full scan per run is probably unacceptable; no batch/partition scheme is designed here. |
| Whether FA's `audit_trail` is usable as the audit consumer's store instead of `0_rbac_audit_log` | **[UNVERIFIED]** — both exist; no comparison made. |

## 7. Related

- [BR-ACL-010](./BR-ACL-010-event-driven-ownership.md) R6, R7, §3.1
- [FR-ACL-010-03](./FR-ACL-010-03-lifecycle-events.md) §2.3 — `orphaned_record` emission
- [BR-CAL-010](./BR-CAL-010-capability-contract.md) — the task-filing responder for bucket entries
- [`OPEN-QUESTIONS.md`](./OPEN-QUESTIONS.md) — Q-ACL-010-4, Q-ACL-010-8