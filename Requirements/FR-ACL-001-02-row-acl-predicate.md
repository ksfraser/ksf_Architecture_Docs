# FR-ACL-001-02 — The row-ACL predicate emitted by the builder

@BABOK Related: BR-ACL-001, BABOK 8.3 Solution Design, 5.6 Solution Evaluation
Status: **Proposed**
Module: `ksfraser/ksf-common-db` (`src/Query/QueryBuilder.php`), `ksf_FA_RBAC`
Date: 2026-10-14
Package state verified at: `v1.0.1-1-g31fee8d` (`~/Documents/ksf_common_db`)

> **Documentation only.** No SQL was executed against `ksf_fa`, no index was created,
> no plan was measured, and no code was changed.

---

## 1. Performance target: one data query per request

BR-ACL-001 R7. The requirement is not "an ACL check per query" and not "an ACL check
per record". It is:

> The policy is loaded **once per request** into memory. The ACL predicate is emitted
> as a JOIN or EXISTS using the existing composite indexes and resolved by the database
> **in the same round trip** as the data itself.

Three separate costs, and how each is avoided:

| Cost | How many | Mechanism |
|---|---|---|
| Resolve the user → their groups | **1 per request** | Cached in memory (§4), one indexed query on `0_rbac_team_members.user_id` |
| Resolve group → capability policy | **1 per request** | Cached in memory (§4), one indexed query on `0_rbac_group_policy.resource_lookup` |
| Filter the records | **0 extra round trips** | The predicate is part of the data statement (§3) |

**N + 1 is the failure mode this requirement exists to prevent.** A design that
"checks access, then fetches" costs one round trip per record. This design costs
exactly one.

> **No performance number is claimed anywhere in this document.** No query was timed.
> The argument below is about *plan shape* and *round-trip count*, both of which are
> structural, not empirical.

## 2. What the builder can and cannot do today **[V]**

The predicate must be emitted by `ksfraser\CommonDb\Query\QueryBuilder`. Verified by
reading `src/Query/QueryBuilder.php` at `v1.0.1-1-g31fee8d`:

| Fact | Location | Consequence |
|---|---|---|
| `$select` defaults to `['*']` | `:26` | `toSql()` emits `SELECT *` unless `select()` is called. This is what FR-ACL-001-03 Stage 2 rejects. |
| `from()` stores one **opaque string** | `:83` | The builder does not parse the table name, so it **cannot know what it is selecting from** and cannot derive `(module, record_type)` from it. |
| `toSql()` implodes raw fragments | `:174-207` | It is a string concatenator over `$select`, `$from`, `$joins`, `$where`, … There is no clause model. |
| **No public getters** for `$select` or `$from` | — | Nothing outside the class can introspect the statement it is about to emit. |
| `join(string $clause)` takes the **whole** clause | `:112-117` | A structured join is not expressible. `ksf_FA_ProjectManagement`'s `TaskDependencyRepository.php:75` already calls `join('INNER', $table, $on)`; PHP discards the extra arguments and the builder emits malformed `… FROM 0_task_dependencies d INNER WHERE …` **[V — recorded in `ACL_Two_Approaches.md` §5.1]**. |
| `FaDbAdapter::prefixTables()` regex | `src/Adapter/FaDbAdapter.php:55-78` | Matches only the token after `FROM\|JOIN\|INTO\|UPDATE\|TABLE`. Consequences below. |

### 2.1 `prefixTables()` constraints on the emitted predicate **[V]**

Confirmed by reading the regex at `FaDbAdapter.php:56`:

```php
'/(\b(?:FROM|JOIN|INTO|UPDATE|TABLE)\s+)(`?)([a-zA-Z_][a-zA-Z0-9_]*)(`?)(\s+[a-zA-Z_][a-zA-Z0-9_]*)?/i'
```

| Consequence | Rule for this FR |
|---|---|
| Only the **first** table of a comma-join is prefixed | **The ACL predicate must never use a comma-join.** Use `EXISTS` (§3.2), which needs no extra `FROM` token at all. |
| `FROM` already prefixed is skipped (`:70-72`) | Tables may be named unprefixed and left to the adapter, or pre-prefixed. **But** see company 2. |
| `WITH` is not in the token list | **CTEs cannot be used** to express the predicate. They are prefixed as if they were tables, breaking the statement. |
| `IN (…)` subquery is not in the token list | An `IN`-list form (§3.3) would need **explicit `TB_PREF`** on the inner tables, because nothing will prefix them. |
| Line 70 checks `strpos($name, $this->tablePrefix) === 0` | With prefix `0_`, a table literally named `0_…` is skipped — fine. **With prefix `1_`, `strpos('0_crm_contacts', '1_')` is false, so it *would* be prefixed to `1_0_crm_contacts`.** Naming an ACL table with a hardcoded `0_` in builder code is therefore **wrong for company 2+**. **Always name ACL tables unprefixed in builder code.** |

## 3. The three candidate predicates

All three are written against the FR-ACL-001-01 schema. `crm` / `contacts` stands in
for `module` / `record_type`.

### 3.1 INNER JOIN — **rejected**

```sql
SELECT c.id, c.name
FROM   crm_contacts c
JOIN   rbac_record_owner o
       ON  o.module = 'crm' AND o.record_type = 'contacts'
       AND o.record_id = c.id
WHERE  …
```

| For | Row multiplicity is correct, the filter is in the same round trip, and the plan is a simple ref lookup on `record_owner_lookup`. |
|---|---|
| Against | **Only expresses ONE axis.** Owner **and** Group cannot both be represented — an inner join to both is an N×M product that duplicates rows, and a `LEFT JOIN … OR` is not constructible here. It also cannot express "owner **OR** any of my 7 groups" without a `UNION` of two joins, which duplicates columns. And an inner join to the ACL tables **silently drops** records that have no owner row — which makes "no ownership" indistinguishable from "not permitted", violating BR-ACL-001 R6. |

**Verdict:** cannot express Owner-OR-Group. Rejected.

### 3.2 EXISTS — **recommended**

```sql
SELECT c.id, c.name
FROM   crm_contacts c
WHERE  …
  AND (
         EXISTS (SELECT 1 FROM rbac_record_owner o
                  WHERE o.module = 'crm' AND o.record_type = 'contacts'
                    AND o.record_id = c.id AND o.owner_id = ?)
      OR EXISTS (SELECT 1 FROM rbac_record_group rg
                  WHERE rg.module = 'crm' AND rg.record_type = 'contacts'
                    AND rg.record_id = c.id
                    AND rg.live_flag IS NULL
                    AND rg.group_id IN (?, ?, ?, ?))
      OR EXISTS (SELECT 1 FROM rbac_group_policy gp
                  WHERE gp.module = 'crm' AND gp.record_type = 'contacts'
                    AND gp.group_id IN (?, ?, ?, ?)
                    AND gp.inactive = 0 AND gp.row_level IN ('other', 'group', 'owner_only'))
      )
```

The `group_id IN (…)` lists are **the user's group ids, resolved once per request into
memory** (§4) and bound as parameters. They are **not** a subquery, and they are the
whole reason the design costs one round trip.

**Why this shape:**

1. **Owner OR Group is exactly what `EXISTS … OR EXISTS` means.** No row
   multiplication: `EXISTS` is a boolean, so the outer result cardinality is the base
   table's cardinality. Uniqueness of the inner rows is irrelevant.
2. **It survives `prefixTables()`.** `FROM` inside the subqueries will be prefixed by
   the adapter — one table per `FROM`, no comma-joins, no CTEs. Each subquery has
   exactly one `FROM`.
3. **`live_flag IS NULL` is sargable.** It is the **last** column of
   `record_lookup (module, record_type, record_id, live_flag)`, so a point lookup on
   the triple still constrains all four.
4. **The third `EXISTS` is the Other axis.** Note it is deliberately *not* restricted
   to `row_level = 'other'` — a policy with `row_level IN ('other','group','owner_only')`
   admits the record regardless of ownership, which is the correct reading of BR-ACL-001
   §6's level 4. Deny-exceptions (§6 level 1) are applied in PHP before the query is
   built, and are recorded as **Q7** — pushing them into SQL would require a `NOT
   EXISTS` that interacts badly with the `OR` above.
5. **`expires_at`** is omitted from the SQL above on purpose. Adding
   `(expires_at IS NULL OR expires_at > NOW())` per subquery adds a non-indexable
   residual to each. **Recommendation:** the per-request policy resolution (§4) already
   drops groups whose memberships are all expired, so the residual is redundant for
   group-derived access and is only needed for record-level expiry. **Q8.**

### 3.3 IN-list — **rejected**

```sql
AND c.id IN (SELECT rg.record_id FROM rbac_record_group rg
              WHERE rg.module='crm' AND rg.group_id IN (?,?,?))
```

| For | Short, and a semi-join is usually planned as a materialised subquery the outer query probes. |
|---|---|
| Against | Three of them (`owner`, `group`, `policy`) must be `OR`-ed, so the statement still needs the same parentheses. Worse, an `IN (SELECT …)` **can** multiply rows in MariaDB when the subquery is not provably unique — `record_group_lookup` is unique only on the five-column key including `live_flag`, so a retired duplicate can make `IN` semantically a join. `EXISTS` has no such exposure. |

**Verdict:** `EXISTS` dominates. Rejected, but retained here because it is the shape
someone will reach for first.

### 3.4 Comparison

| | INNER JOIN | **EXISTS** | IN-list |
|---|---|---|---|
| Owner OR Group | ✗ | ✓ | ~ |
| Row multiplication risk | ✗ high | ✓ none | ✗ possible |
| Works with `prefixTables()` | ~ (one join per axis) | ✓ | ✗ (inner tables unprefixed) |
| Commas / CTEs required | ✗ | ✓ no | ✓ no |
| Cost in round trips | 0 extra | 0 extra | 0 extra |
| Default posture expressible | ✗ | ✓ | ~ |

## 4. Per-request policy cache

The predicate above binds the user's **group ids**. Those are resolved once per
request. **[D]**

```
Request begins
  └─ PolicyCache::forUser($userId)          ← one lazily-populated object per request
       ├─ groupIds        = SELECT group_id FROM rbac_team_members
       │                     WHERE user_id = ? AND inactive = 0 AND approved = 1
       │                     AND (removed_at IS NULL)
       │                   ← served by 0_rbac_team_members.user_id (user_id, inactive)
       ├─ policies        = SELECT * FROM rbac_group_policy
       │                     WHERE module = ? AND record_type = ? AND inactive = 0
       │                     AND group_id IN (…groupIds)
       │                   ← served by rbac_group_policy.resource_lookup
       └─ notMembersOf    = groups the user is NOT in   (only if the default posture
                             is deny-all; see Q2 — otherwise never populated)
```

### 4.1 Cache rules

| Rule | Value | Reason |
|---|---|---|
| Scope | **Process request only.** A static, per-request object; never persisted to `$_SESSION`. | A session cache would let a permission change take effect only at next login. FA opens a fresh DB connection per request **[V — recorded in `ACL_Two_Approaches.md` Appendix B item 2]**, so request scope costs nothing extra. |
| Population | Lazy, on first ACL use. | Not every request touches a protected table. |
| Invalidation | None within a request. | A request is atomic; mid-request revocation is not a requirement. |
| Cross-request | **None.** APcu/Redis is explicitly **not** specified. | Would introduce a staleness window and a new failure mode. **Q9.** |
| Size | `O(groups × policies for the touched resource)`. | Only policies for the `(module, record_type)` actually queried are fetched. |
| Empty | If the user is in **zero** groups and the posture is deny-all, the query short-circuits: `PolicyCache::isDenylist()` and the builder emits **no ACL clause at all** and returns nothing. | Must be **explicit**, never an absent-clause-means-allow. |

### 4.2 The short-circuit is the security-critical case

A builder that emits "no predicate" when it has no policy is a fail-open. The rule is:

> If a table is row-ACL-managed and the cache cannot produce a policy, the statement is
> **refused**. It is not emitted unfiltered. **[D]** — mirrors
> `ACL_Two_Approaches.md` §4.1's "deny wins, never silently widened".

## 5. Interaction with Stage 2's `SELECT *` rejection

FR-ACL-001-03 Stage 2 makes the builder *declare* the table so it can (a) emit this
predicate and (b) reject `SELECT *`. Those are the same requirement, because both need
what the builder currently lacks:

> `from()` stores an opaque string and nothing can read it back. **A builder that
> cannot see its own `FROM` cannot key a policy lookup on it.** Declaration is the
> prerequisite, not a nicety. **[V — `QueryBuilder.php:83`, no getters]**

The minimal declaration shape, **illustrative, not an API** **[D]**:

```php
$qb->fromTable('crm_contacts')                    // logical, unprefixed
   ->rowAcl('crm', 'contacts')                    // module, record_type
   ->select(['id', 'name', 'email']);
```

Which requires, in `ksf-common-db`, all of: a readable table reference; a policy
contract; and `SELECT *` rejection. `ACL_Two_Approaches.md` §5.2 phases 1–2 scope that
work. **This FR does not add a fourth axis to it.**

## 6. Writes

The predicate is a **read** construct. It has no `INSERT` counterpart and should not
get one: a row ACL governs *visibility*, not *authorisation to mutate*.

| Operation | Requirement |
|---|---|
| `UPDATE` / `DELETE` | The target row set **must** be resolved through an ACL-filtered read first, or the statement must carry the same predicate in a `WHERE`. Emitting `DELETE FROM t WHERE … AND <acl predicate>` is legal and should be supported. **[D]** |
| `INSERT` | Row ACL does not apply. Column ACL does (FR-ACL-001-04 §3.6 — views cannot be written through). |
| Ownership/group rows | Writing to `0_rbac_record_owner` / `0_rbac_record_group` is a **grant**, and is authorised by `can_edit` on the resource, not by the row predicate. |

Whether write paths are policed at all is **Q4** (BR-ACL-001 R10).

## 7. Acceptance criteria

| # | Criterion |
|---|---|
| AC1 | With `groupIds = []` and posture deny-all, the builder **refuses** to emit. It does not emit an unfiltered `SELECT`. |
| AC2 | `EXPLAIN` on the `record_group_lookup` subquery shows index use and **no full scan**, at a representative `ksf_fa` table size. |
| AC3 | `EXPLAIN` on `0_rbac_team_members` with `WHERE user_id = ?` uses `user_id` index. |
| AC4 | A record owned by the user **and** attached to two of the user's groups appears **exactly once** in the result. (Catches the `IN`-list and INNER-JOIN multiplication bugs.) |
| AC5 | A record owned by nobody and attached to no group the user is in appears **once** iff the user's policy `row_level` is `other` or higher; **zero times** if `none`. |
| AC6 | The same query against company 2 (`TB_PREF = '1_'`) resolves to `1_rbac_*` and `1_crm_contacts` with no `0_` remnant and no `1_0_` double-prefix. |
| AC7 | The generated SQL contains **no comma-join** and **no `WITH`**. |
| AC8 | `PolicyCache` is constructed at most once per request (assert via a counter). |
| AC9 | Group membership changes take effect on the **next** request, with no cache purge. |

## 8. Explicitly unverified

| Item | Status |
|---|---|
| **Every plan shape in §3.** No index was created and no `EXPLAIN` was run. AC2/AC3 exist precisely because this is unmeasured. | **[UNVERIFIED]** |
| Any timing, row estimate, or "this is fast" claim | **None made, deliberately.** |
| Whether MariaDB chooses semi-join over the three `EXISTS` subqueries on a real table | **[UNVERIFIED]** |
| `NOW()` expiry semantics under the MariaDB container's time zone vs FA's session time zone | **[UNVERIFIED]** — this is why §3.2 recommends omitting the expiry residual from the SQL. |
| Whether `0_users` has any "inactive user" concept that row ACL must honour | **[UNVERIFIED]** — **Q6**. FA decides user validity in `session.inc`; whether a deactivated user's grants must lapse is not answered by anything read here. |
| That `EXISTS` is never planned as a multiplying semi-join on this server | **[A — SQL semantics]**; AC4 is the guard. |

## 9. Related

- [BR-ACL-001](./BR-ACL-001-record-ownership-and-access-control.md) — R7, R10
- [FR-ACL-001-01](./FR-ACL-001-01-ownership-schema.md) — the indexes §3 relies on (§7 there maps each)
- [FR-ACL-001-03](./FR-ACL-001-03-two-stage-enforcement-migration.md)
- [OPEN-QUESTIONS.md](./OPEN-QUESTIONS.md) — Q2, Q4, Q7, Q8, Q9
- `ksf_common_db/src/Query/QueryBuilder.php` — `:26`, `:83`, `:112-117`, `:174-207`
- `ksf_common_db/src/Adapter/FaDbAdapter.php` — `:49-78` (`prefixTables`)
- [`ACL_Two_Approaches.md`](../ACL_Two_Approaches.md) §5 — the phase this slots into