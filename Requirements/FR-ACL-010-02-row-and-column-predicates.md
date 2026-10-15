# FR-ACL-010-02 — Row predicate and column mask in one statement

@BABOK Related: BR-ACL-010 R2, R8, BR-ACL-001 R7, BABOK 8.2 Solution Analysis
Status: **Proposed**
Module: `ksfraser/ksf-common-db` (`src/Query/QueryBuilder.php`, `src/Adapter/FaDbAdapter.php`)
Date: 2026-10-14

> **Documentation only.** No SQL was executed, no `EXPLAIN` was run, and no index was
> created. No performance number is claimed anywhere in this document.

---

## 1. Requirement

> **One query, no N+1.** The row predicate and the column mask are emitted **in the
> same statement**, so ACL costs zero extra round trips.

| Cost | How many | Mechanism |
|---|---|---|
| Resolve user → their groups | **1 per request** | Cached in memory (FR-ACL-001-02 §4) |
| Resolve group → capability policy | **1 per request** | Cached in memory |
| Filter the records | **0 extra round trips** | The predicate is *in* the data statement |

N+1 — "check access, then fetch" — is the failure mode this requirement exists to
prevent.

## 2. The agreed predicate shape

**[D]** As briefed. `:myGroups` and `?` are bound parameters, never interpolated.

```sql
SELECT t.id,
       t.customer_id,
       CASE WHEN :canReadTotal = 1 THEN t.total      ELSE NULL END AS total,
       CASE WHEN :canReadRate  = 1 THEN t.rate       ELSE NULL END AS rate
FROM   0_sales_invoices t
LEFT JOIN 0_rbac_record_owner o
       ON  o.module     = ?
    AND o.record_type = ?
    AND o.record_id   = t.id
    AND o.user_id     = ?
WHERE  t.inactive = 0
  AND ( o.record_id IS NOT NULL                                        -- explicit owner
        OR EXISTS (SELECT 1 FROM 0_rbac_record_group g
                    WHERE g.module     = ?
                      AND g.record_type = ?
                      AND g.record_id   = t.id
                      AND g.live_flag IS NULL
                      AND g.group_id IN (:myGroups))                   -- group
        OR EXISTS (SELECT 1 FROM 0_rbac_group_policy p
                    WHERE p.module     = ?
                      AND p.record_type = ?
                      AND p.group_id IN (:myGroups)
                      AND p.inactive = 0)                               -- other-rule
```

### 2.1 Why a `LEFT JOIN` for the owner axis but `OR EXISTS` for the rest

**[D]** This is the specific shape agreed, and the asymmetry is deliberate:

| Axis | Mechanism | Why |
|---|---|---|
| Owner | `LEFT JOIN` + `o.record_id IS NOT NULL` | `0_rbac_record_owner` carries `UNIQUE KEY record_owner_lookup (module, record_type, record_id)` **[V — FR-ACL-001-01 §3.1]**, so the join can match **at most one** row. **Fan-out is impossible by construction.** |
| Group, Other | `OR EXISTS` | Each contributes a boolean, so the outer cardinality stays the base table's. Adding joins here would multiply rows — and joining to *two* ACL tables would be an N×M product, which is precisely why [FR-ACL-001-02](./FR-ACL-001-02-row-acl-predicate.md) §3.1 rejected the INNER JOIN. |

**The `LEFT JOIN` is what makes "unowned" survivable.** An inner join silently drops
records that have no owner row, which makes *no ownership* indistinguishable from *not
permitted* — the exact failure BR-ACL-010 R6 forbids. The `LEFT JOIN` keeps such rows
in the result set and lets the `[UNVERIFIED]`-flagged orphaned bucket logic see them.

### 2.2 Constraints inherited from `prefixTables()`

**[V]** `FaDbAdapter.php:56` matches only the token after `FROM|JOIN|INTO|UPDATE|TABLE`.
Therefore the emitted predicate must:

| Constraint | Rule |
|---|---|
| One table per `FROM`/`JOIN` token | **No comma-joins.** |
| No `WITH` | CTEs are not in the token list and get prefixed as tables. |
| `IN (…)` subqueries are not prefixed | Either use bound group-id lists (as above) or write inner tables with explicit `TB_PREF`. |
| Already-prefixed names are skipped (`:70-72`) | Name ACL tables **unprefixed** in builder code. |

## 3. The column mask

`CASE WHEN :canRead<Col> = 1 THEN <col> ELSE NULL END`, **aliased**, emitted in the same
SELECT list.

| Rule | Rationale |
|---|---|
| Always `ELSE NULL`, never a default value | A masked column must be **absent**, not zeroed. `0` is a real amount. |
| Always aliased | The consumer needs a stable name regardless of masking. |
| Mask params are **bound**, not inlined | An inlined flag would be a literal the caller could forget to set. |
| Views are **not** used for column ACL | **Decided against**: column policy must be admin-configurable at runtime, and a view cannot be regenerated from a UI click. |

## 4. What this requirement explicitly does NOT do — the action axis

> **[D] BR-ACL-010 R8. The action axis (read / write / delete / export) is an
> application-boundary check, NOT a SQL predicate.**

This is recorded as a **non-requirement** so it is not re-litigated mid-implementation.

| Operation | Requirement |
|---|---|
| **Read** | Row predicate + column mask, in SQL. This document. |
| **Write** (`INSERT`/`UPDATE`/`DELETE`) | **Authorised in the application layer**, before the statement is issued. Row ACL does **not** apply. |
| **Export** | Application layer. A filtered `SELECT` is *not* an export authorisation — see below. |

**Why a write rule cannot be a `SELECT` predicate:**

| Attempted encoding | What actually happens |
|---|---|
| Filter the edit form's `SELECT` by the predicate | The check runs against the row **as it currently is**, authorising the *read*, not the *write*. A user who may view but not edit passes it. |
| Re-run the predicate inside the `UPDATE`'s `WHERE` | Legal SQL, but it authorises "edit rows you can see", which is the opposite of the intent, and it silently succeeds with zero rows affected on denial rather than raising. |
| Filter the `UPDATE` by column mask | The mask is a projection, not a write filter. It does not exist on the write path at all. |

**Export is the sharpest case.** A caller can read 10 permitted invoices one at a time
through the UI and concatenate them; that is not an export. An export is a *bulk*,
*machine-readable* extraction, and it must be authorised as such at the boundary — a
row-filtered `SELECT` handed to a CSV writer is not sufficient, because the row filter
answers "which rows", never "may this user extract this class of data at all".

**Read/write column rules are independent** (R9). Support desk may *view* invoices,
quotes and contracts; only sales may *edit* them. A masked view is a read device and
cannot express an edit restriction.

## 5. Acceptance criteria

| # | Criterion |
|---|---|
| AC1 | A record owned by the user **and** in two of the user's groups appears **exactly once**. (Catches fan-out.) |
| AC2 | A record with **no** owner row and no group still appears in the result set (LEFT JOIN preserves it). |
| AC3 | Every masked column is `NULL` for a caller without the capability, and equals the stored value for one with it. |
| AC4 | A masked column's value `0` is distinguishable from a masked value. |
| AC5 | `EXPLAIN` on the `record_group_lookup` subquery shows index use and no full scan, at representative `ksf_fa` table size. **[UNVERIFIED — not run.]** |
| AC6 | Generated SQL contains no comma-join and no `WITH`. |
| AC7 | The statement count is unchanged by enabling ACL on a table (zero extra round trips). |
| AC8 | A write to a row the caller can read but not edit is **rejected by the application layer**, and no `UPDATE` is issued. |
| AC9 | An export of a readable-but-not-exportable class is refused at the boundary. |
| AC10 | Under `TB_PREF = '1_'`, all emitted names resolve to `1_*` with no `0_` or `1_0_` remnant. |

## 6. Explicitly unverified

| Item | Status |
|---|---|
| Every plan shape in §2 | **Not measured.** AC5 exists precisely because of this. |
| Whether MariaDB plans these `EXISTS` as non-multiplying semi-joins here | **[UNVERIFIED]**; AC1 is the guard. |
| `NOW()`/expiry semantics across the container's time zone vs FA's session time zone | **[UNVERIFIED]** — and why no expiry residual is emitted here. |
| **Whether `prefixTables` corrupts the `CASE` mask** (it matches the bare token `TABLE`) | **[UNVERIFIED]** — genuine risk, not covered by the ACs. **Q-ACL-010-2.** |
| Whether the *orphan sweeper* can cheaply distinguish cause (a)/(b)/(c) at query time | **[UNVERIFIED]** — see [FR-ACL-010-05](./FR-ACL-010-05-orphaned-records.md) §4. |

## 7. Related

- [BR-ACL-010](./BR-ACL-010-event-driven-ownership.md) R2, R8, R9
- [FR-ACL-001-02](./FR-ACL-001-02-row-acl-predicate.md) — the pure-`EXISTS` predecessor and why this FR differs
- [`ACL_Two_Approaches.md`](../ACL_Two_Approaches.md) §1.4, §3.6 — composition and the write path