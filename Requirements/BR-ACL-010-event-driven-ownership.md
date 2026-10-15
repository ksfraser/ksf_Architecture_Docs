# BR-ACL-010 — Event-driven ownership: an ACL event framework

@BABOK Related: BABOK 8.1 Solution Strategy, 8.2 Solution Analysis, 9.1 Requirements Analysis
Status: **Proposed**
Module: `ksfraser/ksf-common-db` (builder), `ksf_FA_RBAC` (framework), all `ksf_FA_*` modules (responders)
Date: 2026-10-14
Depends on: [BR-ACL-001](./BR-ACL-001-record-ownership-and-access-control.md),
[FR-ACL-001-01](./FR-ACL-001-01-ownership-schema.md),
[FR-ACL-001-02](./FR-ACL-001-02-row-acl-predicate.md)
Scope: **the lifecycle/ownership layer.** The row predicate shape itself is
FR-ACL-010-02; the column axis remains
[`ACL_Two_Approaches.md`](../ACL_Two_Approaches.md).

> **Documentation only.** No production code was written, no schema was changed, no
> SQL was executed against `ksf_fa`, and no commit was made in producing this
> document. Everything marked **[V]** was verified by reading a file or dumping a
> schema; everything marked **[D]** is a decision recorded here; everything marked
> **[UNVERIFIED]** is explicitly not known.

---

## 1. Business driver

[BR-ACL-001](./BR-ACL-001-record-ownership-and-access-control.md) specifies a *static*
access model: a record has an owner and a set of groups, and the query builder filters
on them. It is necessary and it is not sufficient, for one reason:

> **The BR-ACL-001 model has no answer to "the ownership just changed."**

Ownership is not a static attribute. It changes when:

- an account manager leaves the CRM and their contacts are reassigned;
- an employee is removed from a team, and every record they reached **only through**
  that team becomes unreachable;
- a table is brought under ACL for the first time, and 40,000 existing rows have no
  owner;
- a write rolls back halfway and leaves an ACL row pointing at a row that does not
  exist.

A predicate that is correct at time T is wrong at time T+1. This BR is about the
**transitions**, and it makes the central architectural claim that produces all of the
rest:

> **[D] The framework does not own any ownership semantics. It emits *facts*
> (`record_changed`, `user_changed`, `orphaned_record`) and each module decides what
> those facts mean for its own tables.**

## 2. What is decided

### R1 — Modules never write ACL SQL. They declare, and the builder emits.

A module declares that a table is ACL-governed and provides module-specific rule
fragments. The framework builder composes the row predicate and the column mask.
When the table is not ACL-governed, the builder emits **nothing**.

| Rule | Consequence |
|---|---|
| Modules must not hand-write `0_rbac_*` predicates | There is exactly one place that knows the predicate shape, so it can be fixed in one place. |
| Absent declaration ⇒ no clause | The predicate is driven by data, not by a code path someone forgot. |
| `SELECT *` is **rejected** when ACL is active for the table | A wildcard cannot be column-masked. This is the same requirement as [`ACL_Two_Approaches.md`](../ACL_Two_Approaches.md) §2.2. |

Scope of the adoption: **~1,510 `db_query(` call sites across 299 files** in our dev
trees (vendor excluded). FA core's ~870 are explicitly out of scope **[V — count taken
from the brief; not independently re-run]**.

### R2 — One query, no N+1. Row predicate and column mask in the same statement.

The agreed shape (full worked form and the fan-out argument in
[FR-ACL-010-02](./FR-ACL-010-02-row-and-column-predicates.md)):

```sql
LEFT JOIN 0_rbac_record_owner o
       ON  o.module = ? AND o.record_type = ? AND o.record_id = t.id AND o.user_id = ?
WHERE  …
  AND ( o.record_id IS NOT NULL
        OR EXISTS (SELECT 1 FROM 0_rbac_record_group g
                    WHERE … AND g.group_id IN (:myGroups))
        OR <other-rule> )
```

with the mask in the **same** statement, `CASE WHEN :canReadX = 1 THEN col ELSE NULL END`.

### R3 — Three lifecycle events, emitted **post-commit**.

`record_changed`, `user_changed`, `orphaned_record`. Each carries a defined payload and
a defined consumer set. Post-commit is a **hard requirement**, not a preference: an
ACL row written against a transaction that later rolls back is a dangling ACL row,
which is the same defect as an orphaned record but self-inflicted by the framework.
Mechanism and its trap are in
[FR-ACL-010-03](./FR-ACL-010-03-lifecycle-events.md) §1.

### R4 — Ownership *transitions* are registered responders, not a ruleset.

The framework knows nothing about invoices versus customers. Neither does RBAC. Each
module registers its own semantics. **Returning `null` means "not my concern"** — this
is what makes the mechanism extensible without a central registry edit.

| Module | Event | Transition |
|---|---|---|
| `ksf_FA_Sales` | `quote` / `sales_order` / `cust_invoice` | `Transition::none()` — historical documents, ownership never transfers |
| `ksf_FA_CRM` | `contact` | `Transition::transferTo($newAccountManager)` |
| `ksf_FA_HRM` | `user_changed` + isTeamChange | revoke group-derived ownership where the group no longer includes the user |

### R5 — Ownership records its **provenance**.

Every ownership row must carry how it came to exist: `explicit | group | inherited`.

This is a **core requirement, not a nicety.** Without provenance the `ksf_FA_HRM`
responder above and any group-policy responder are writing to the same record with no
way to coordinate. Two responders will overwrite each other, and the loser will
silently strip a grant. Provenance makes "do not touch `inherited` ownership" a
checkable statement instead of a hope.

### R6 — Unowned records land in an explicit, admin-visible **orphaned bucket**.

Neither of the two easy answers is acceptable:

| Wrong answer | How it fails to the user |
|---|---|
| Silently **deny** | Looks like data loss. Support tickets: "my contacts disappeared." |
| Silently **allow** | Looks like a breach. The one moment the system is most likely to be wrong is the moment it is most permissive. |

### R7 — Unowned has **three causes** requiring **three different treatments**.

| Cause | Detection | Treatment |
|---|---|---|
| (a) ACL **just enabled** on a table | Deliberate admin action | One-time bulk assign migration |
| (b) Data corruption / lost write | Orphan sweeper | Route to the admin queue (R6) |
| (c) **User removed** | — see §3 | Cascade reassign on deactivation |

### R8 — The action axis (read / write / delete / export) is an **application-boundary**
### check, **not** a SQL predicate.

> **Reads may be filtered in SQL. Writes must not be.**

Encoding a write rule as a `SELECT` predicate either **never fires** (the predicate runs
on the read that precedes the edit, not on the write) or **fires wrongly** (it is
evaluated against the row *as it currently is*, when what needs authorising is the row
*as it is being made*). This is recorded as an explicit non-requirement so that it is
not re-litigated during implementation.

### R9 — Read and write column rules are independent.

Example, not a hard rule: support desk may **view** invoices, quotes and contracts but
only sales may **edit** them. A masked view is a *read* device; it cannot express an
edit restriction.

## 3. Two corrections to the premises this BR was drafted from

Both were checked against FA 2.4.3 source and the live schema dump. The original
concerns were **real**; the stated causes were **wrong**.

### 3.1 `0_users` **does** have an inactive flag — but nothing ever writes it

> Brief's claim: *"`0_users` has NO active flag, so 'user removed' is undetectable."*

**[V]** `0_users.inactive tinyint(1) NOT NULL DEFAULT 0` **exists**
(`ksf_Infrastructure/init-sql/ksf_fa_current.sql`, `0_users` CREATE TABLE at line 2456;
`inactive` is the second-to-last column). `0_users.user_id varchar(60)` carries
`UNIQUE KEY user_id`.

The column is real but **dead**:

| Path | Behaviour |
|---|---|
| `admin/db/users_db.inc:75` | `get_users()` reads it: `if (!$all) $sql .= " AND !u.inactive";` |
| `admin/db/users_db.inc:39-52` | `update_user()` — **does not** set it |
| `admin/db/users_db.inc:14-26` | `add_user()` — omits the column, relies on `DEFAULT 0` |
| `admin/db/users_db.inc:118-122` | `delete_user()` — **hard `DELETE`** |
| `admin/db/users_db.inc:130` | `get_user_auth()` — **does not** check it |

**Consequence, and it is sharper than the original concern:** "user removed" in this
system manifests as a **row deletion**, not a flag flip. There is no soft-delete
path, so there is no `user_changed` event to fire on a deactivation, because no
deactivation exists. R7(c) cannot be implemented until one of these is built. Tracked
as **Q-ACL-010-4**.

> Side finding, out of scope for this BR but worth recording: because
> `get_user_auth()` does not test `inactive`, the flag would not prevent login even if
> something did set it. **[V]** — do not rely on `0_users.inactive` as a security
> control without changing that function too.

### 3.2 The RBAC user-id type mismatch is a **comment** defect, not a type defect

> Brief's claim: *"`0_rbac_teams.owner_id` / `0_rbac_team_members.user_id` carry
> `COMMENT 'FK to 0_users.id'` but `0_users.id` is a smallint — the natural key is
> `0_users.user_id varchar(60)`."*

**[V]** The comment is wrong, and wrong in exactly the way described. The **type is
already correct**:

| Column | Actual | Comment says | Reality |
|---|---|---|---|
| `0_rbac_teams.owner_id` | `VARCHAR(64)` | `FK to 0_users.id or synthetic ID for service accounts` (`ksf_FA_RBAC/sql/install.sql:19-20`) | Already string-keyed. `0_users.id` is `smallint(6)`; the comment points at the surrogate. |
| `0_rbac_team_members.user_id` | `VARCHAR(64) NOT NULL` | `FK to 0_users.id` (`install.sql:39-40`) | Same. |

The comment is a **trap for the next reader**: it invites someone to "fix" the schema
by joining a `VARCHAR(64)` to a `smallint`, which will silently coerce. The remedy is
to correct the comment to name `0_users.user_id`, not to change a column type.
`VARCHAR(64)` against `varchar(60)` is over-provisioned but harmless. Tracked as
**Q-ACL-010-5**.

## 4. Explicitly unverified

| Item | Status |
|---|---|
| The 1,510-call-site / 299-file count | **[UNVERIFIED]** — taken from the brief, not re-run. Cheap to confirm with `grep -rc "db_query(" --include=*.php`. |
| `0_rbac_record_owner` / `0_rbac_record_group` / `0_rbac_group_policy` **exist** | **They do not.** They are *proposed* by [FR-ACL-001-01](./FR-ACL-001-01-ownership-schema.md) §3.1/§3.2. **[V]** — no `.php` or `.sql` file in either `ksf_FA_RBAC/` tree references them. Every predicate in R2 and in FR-ACL-010-02 is therefore **blocked on FR-ACL-001-01 landing first.** |
| Whether `hook_invoke_first` survives a responder returning `false` | **[UNVERIFIED]** — matters for the `orphaned_record` admin-queue responder. See FR-ACL-010-03 §4. |
| Current row counts in the four existing RBAC tables | Reported empty in the brief; **not re-queried** (documentation-only task). |
| Whether any responder can safely run a write from inside `db_postwrite` | **[UNVERIFIED]** — see the `exit` trap cited in FR-ACL-010-03 §1. |

## 5. Requirements in this set

| ID | Requirement |
|---|---|
| [FR-ACL-010-01](./FR-ACL-010-01-per-module-acl-toggle.md) | Per-module ACL toggle; modules never write ACL SQL |
| [FR-ACL-010-02](./FR-ACL-010-02-row-and-column-predicates.md) | Row predicate and column mask in one statement |
| [FR-ACL-010-03](./FR-ACL-010-03-lifecycle-events.md) | The three events and post-commit ordering |
| [FR-ACL-010-04](./FR-ACL-010-04-ownership-transitions-and-provenance.md) | Transitions as responders; ownership provenance |
| [FR-ACL-010-05](./FR-ACL-010-05-orphaned-records.md) | Orphaned bucket, sweeper, three unowned causes |
| [BR-CAL-010](./BR-CAL-010-capability-contract.md) | Calendar capability contract (the `orphaned_record` task-filing responder's dependency) |

## 6. Related

- [`ACL_Two_Approaches.md`](../ACL_Two_Approaches.md) — the column-axis design this BR's
  mask must compose with
- `AGENTS_ARCH.md` §10.1 — the verified FA lifecycle hook map cited by FR-ACL-010-03
- [`OPEN-QUESTIONS.md`](./OPEN-QUESTIONS.md) — Q-ACL-010-1 … Q-ACL-010-9