# OPEN-QUESTIONS — record ownership and row-level ACL

@BABOK Related: BR-ACL-001, FR-ACL-001-01, FR-ACL-001-02, FR-ACL-001-03, FR-ACL-001-04
Status: **Open — decisions required**
Date: 2026-10-14

Ranked by **"how much damage does getting this wrong cost"** — the same criterion used
in [`ACL_Two_Approaches.md`](../ACL_Two_Approaches.md) §7. Each question states what was
decided in the requirement it came from, what is **still** undecided, and what breaks
if it is answered wrong.

Questions **Q1–Q8** are genuinely blocking. **Q9–Q13** are design confirmations.

---

## Blocking

### Q1 — Do `0_rbac_teams` / `0_rbac_team_members` survive, or is the group catalogue rebuilt?

**Where:** FR-ACL-001-01 §3.3, §9 · **Source:** BR-ACL-001 R5

The two tables exist, are empty **[V]**, and have no PHP consumer. But
`0_rbac_team_members` carries a real `UNIQUE (team_id, user_id, inactive)` that the
per-request policy cache depends on (FR-ACL-001-02 §4).

| Option | Cost |
|---|---|
| **(a) Keep both.** Groups = whatever is in `0_rbac_teams`; `group_kind` lives on the membership row. | Lowest. But `0_rbac_teams.team_type` (`individual \| explicit \| org_direct \| org_indirect \| service_account`) is an **org-chart vocabulary**, which is exactly what R5 says groups must *not* be. Two overlapping vocabularies. |
| **(b) Rebuild `0_rbac_teams`** with a `group_kind` that admits `project`/`ad_hoc`/`org_unit`, and widen `team_type`. | Clean. It is a **schema change to a table outside this FR's scope**, and the membership index would need re-verification. |
| **(c) New group catalogue** (`0_rbac_group`), leave the old two orphaned. | Cleanest boundary; two catalogues to migrate. |

**Damaged if wrong (a):** a project group has to be faked as an `explicit` team, so
`group_kind` on the membership row is the only thing distinguishing a project from a
team — which works, but leaves `0_rbac_teams.team_type` actively misleading to anyone
reading it directly.
**Damaged if wrong (b)/(c):** the policy cache's group resolution (§4 of FR-ACL-001-02)
is written against a table that changed.

> **Recommendation: (b).** One catalogue, one vocabulary. The tables are empty, so this
> is a rename-plus-widen, not a migration.

---

### Q2 — Default posture: when a record has no owner and no groups, who sees it?

**Where:** FR-ACL-001-01 §6, §3.4 (`row_level`) · FR-ACL-001-02 §4.2 · **Source:** BR-ACL-001 R6

This is the same question as `ACL_Two_Approaches.md` §7 OD-2, asked on the row axis.
It has **no safe default** and it must be chosen before any policy row is written,
because every unclassified record in the system resolves through it.

| Option | Failure mode |
|---|---|
| **(a) deny-all** — a record with no owner and no group is visible to nobody until it is classified. | Fail-closed. Existing pages return **zero rows** the moment a table is row-ACL-managed. Safe, and immediately visible as a bug. |
| **(b) allow-all** — visible to anyone the group policy admits at `row_level = 'other'`. | Fail-open. Every unclassified record in 243 tables is exposed to every group with `row_level='other'`. **This is the option that turns a half-finished migration into a data breach.** |
| **(c) owner-or-group-only** — a record is visible only if it has an owner or a group; unclassified records are invisible. | Fail-closed, and no policy rows are needed to make it safe. |

> **Recommendation: (c)**, as the framework default, with (a) available per group.
> (b) should require an explicit, audited opt-in per `(group, resource)` and nothing
> else. This is the single highest-leverage decision in the set.

---

### Q3 — Which sensitivity classes exist, and which columns are in each?

**Where:** FR-ACL-001-04 §5.1 · **Source:** BR-ACL-001 §2.2

FR-ACL-001-04 names three classes — `core`, `pii`, `contact` — but **the membership of
each class is empty**. This is `ACL_Two_Approaches.md` §5 **phase 3**, and it is
documented there as blocking *all* of the view work.

Nothing can be generated from a classification that does not exist. This is not a
design question; it is a **task**, and it needs an owner.

> **Needed:** for each table that gets a view, the ordered list of columns per class.
> Concretely, the first three are `ksf_FA_CRM` contacts, `ksf_FA_HRM` payroll, and
> `ksf_FA_Attachments`/`ksf_FA_Documents`.

---

### Q4 — Are write paths policed at all?

**Where:** FR-ACL-001-02 §6 · BR-ACL-001 R10

The row predicate is a **read** construct and has no `INSERT` counterpart. FR-ACL-001-02
§6 says `UPDATE`/`DELETE` should carry the predicate in the `WHERE`, but whether that is
*required* is undecided.

| Option | Consequence |
|---|---|
| (a) Reads only. | A user who cannot see a record can still `UPDATE` it if they know the id. Row ACL becomes a **display** control, which is often not what a compliance requirement means. |
| (b) `UPDATE`/`DELETE` carry the predicate. | Real enforcement. Requires every write statement to declare its table — i.e. Stage 2 covers writes, not just reads. |
| (c) Full authorisation model with operation-level capability checks. | Correct, and a much larger project. |

> **Recommendation: (b).** It is the minimum that makes row ACL mean anything, and it
> costs one extra clause in statements Stage 2 is already rewriting.

**Damaged if wrong (a):** PIPEDA/GDPR erasure cannot be evidenced from the system,
because "cannot be seen" and "cannot be touched" are different claims.

---

### Q5 — Confirm the `live_flag NULL` uniqueness trick on this server

**Where:** FR-ACL-001-01 §4.2

The design relies on `UNIQUE (a, b, c, d, live_flag)` permitting **exactly one live row**
(`live_flag IS NULL`) and **any number** of retired rows (`live_flag = 1`), because
MariaDB/InnoDB does not treat `NULL`s as equal in a unique index. **[A — SQL semantics;
NOT executed. No table was created.]**

This is standard SQL semantics and is very likely correct, but the entire membership
table's integrity rests on it, and AC1/AC2 exist to prove it. **It must be executed
before FR-ACL-001-01 is adopted.**

Fallback if it does not hold: a generated column, e.g.
`live_key VARCHAR(...) AS (IF(live_flag IS NULL, 'L', CONCAT('R', id))) STORED`, indexed
`UNIQUE` instead of `live_flag`. Slightly uglier, same behaviour.

**Damaged if wrong:** duplicate live memberships, which the row predicate then
double-counts — silently, because `EXISTS` does not care how many rows match.

---

### Q6 — Is a deactivated FA user's access revoked, or does it persist to their groups?

**Where:** FR-ACL-001-02 §4.1 · FR-ACL-001-01 §6

`0_users` has **no active/inactive flag** — verified `DESCRIBE 0_users` **[V]**. FA
decides user validity in `session.inc`, which was not analysed here.

Meanwhile `0_rbac_team_members.inactive` and `0_rbac_teams.inactive` exist. Is
"membership retired" the same as "user disabled"?

| Question | Why it matters |
|---|---|
| When FA disables a user, are their `0_rbac_team_members` rows retired? | If not, a disabled user's group ids are still returned by the policy cache, and their **session-less** grants outlive the account. |
| Is FA's notion of "inactive user" observable to the ACL layer at all? | If it is only in-session, the ACL layer cannot honour it in a query — and the only honest answer is that revocation is a session concern, not a row-ACL concern. |

> **Recommendation: document explicitly that row ACL does not own account
> deactivation**, and require that deactivating an FA user **retires their membership
> rows** as an operational step. Otherwise the answer is "we do not know", which is the
> worst available answer to a compliance question.

**Damaged if wrong:** grants survive account closure indefinitely.

---

### Q7 — Where do deny-exceptions live: SQL or PHP?

**Where:** FR-ACL-001-01 §6 (level 1), FR-ACL-001-02 §3.2 (note 4)

Deny is **first in the resolution order and absolute**. But
`0_rbac_record_exception` is a **table**, and the predicate in
FR-ACL-001-02 §3.2 does **not** reference it — exceptions are applied in PHP when the
cache is built.

| Option | Consequence |
|---|---|
| (a) PHP-side deny list. | Simple. But a deny list is **per user × per record**; a user in 40 groups with 5 exceptions makes the cache large, and a **list** cannot be expressed in the `EXISTS` predicate without becoming an unbounded `NOT IN`. |
| (b) `AND NOT EXISTS (SELECT 1 FROM rbac_record_exception e WHERE … AND e.group_id IN (…))` in the emitted SQL. | Correct and set-based. Costs one more correlated subquery on the hot path, and interacts awkwardly with the `OR` of the three positive `EXISTS`. |
| (c) Only ever `allow` exceptions (no deny), which fit the positive `EXISTS` naturally. | Simple, but cannot express a PIPEDA erasure carve-out. |

> **Recommendation: (b),** accepting the extra subquery. Deny-exceptions are by
> definition rare and are the compliance-critical case. **Decide before the first
> exception row is written**, because changing this changes the generated SQL for
> every managed table.

---

### Q8 — Is `expires_at` a SQL residual or a PHP pre-filter?

**Where:** FR-ACL-001-02 §3.2 note 5, FR-ACL-001-01 §7

FR-ACL-001-02 recommends **omitting** the expiry residual from the SQL and instead
dropping expired groups during policy resolution — but that only works for
*group-derived* access. **Record-level expiry** (`0_rbac_record_group.expires_at`,
`0_rbac_record_exception.expires_at`) has no other home.

| Option | Consequence |
|---|---|
| (a) No SQL residual; sweeper deletes expired rows on a schedule. | Simplest SQL. Access persists **until the sweeper runs** — an unbounded window that is exactly wrong for a temporary grant. |
| (b) `(expires_at IS NULL OR expires_at > NOW())` in each subquery. | Correct immediately. Non-indexable residual in two of three subqueries. |
| (c) Sweeper **plus** a coarse SQL residual. | Belt and braces. |

> **Recommendation: (b),** plus the sweeper for hygiene. Also **unresolved:** whose
> `NOW()` — MariaDB's container time zone versus FA's session time zone was not
> verified **[UNVERIFIED]**, and a grant that expires an hour early or late on a
> compliance deadline is a real failure.

---

## Design confirmations

### Q9 — Is the per-request policy cache ever shared across requests?

**Where:** FR-ACL-001-02 §4.1

The design says **request-scoped, never `$_SESSION`, never APcu/Redis**. Request scope
is free because FA opens a fresh connection per request **[V]**.

| If yes | Cost |
|---|---|
| Add APCu/Redis | Every query re-reads group ids and policies; adds a cache-invalidation requirement and a new failure mode (a stale cache silently over-grants). |
| Keep request-scoped | Group-membership changes take effect on the next request, which is almost certainly correct, at a cost of ~2 indexed queries per request that touches an ACL table. |

> **Recommendation: keep request-scoped.** It is the only option with no staleness
> window. AC9 verifies it. Raised only because it is a decision someone will ask about.

---

### Q10 — Is `SRP_DB_Query` a hard naming requirement, or a placeholder?

**Where:** FR-ACL-001-03 §2.1, §2.2

The brief's Stage 1 transform specifies `SRP_DB_Query::db_query(`. FR-ACL-001-03 uses
`\ksfraser\FrontAccounting\Rbac\Security\DbQuery::dbQuery(` because the brief's
spelling is neither PSR-4 nor legal under `AGENTS.md`'s conventions.

**The sed *shape* is unaffected** — a fully-qualified, absolute class name, either way.
Only the class name differs.

> **Recommendation: adopt the convention-compliant name.** But if `SRP_DB_Query` is
> load-bearing for some reason not visible from the repo, say so now — it is one string
> in one expression.

---

### Q11 — Is `sed` adequate, or does Stage 1 need a tokenizer?

**Where:** FR-ACL-001-03 §2.4

The sed rewrite also hits `db_query(` inside **string literals and comments** — a
docblock quoting FA's call, an error message, a `$fn = 'db_query'` callable reference.

| If the residue is small | If it is not |
|---|---|
| `grep -n` review, hand-fix the few hits. | A PHP-tokenizer script or a PCRE-based phpcs rule. More work, zero false positives. |

**Unverified.** The census (FR-ACL-001-03 §2.5) counts *call-shaped* occurrences only
and cannot distinguish them from string occurrences.

> **Recommendation:** run the §2.4 dry-run grep and count. If under ~20 hits, hand-fix.

---

### Q12 — Is CRM-first the right migration order, or payroll-first?

**Where:** FR-ACL-001-03 §3.3

The order given is **CRM → HRM payroll → ProjectManagement (hard prerequisite) →
Calendar → Notes/Attachments/Documents → DataIntegrity → Square → tail**. Volumes are
measured **[V]**; **the priority judgement is not** — it is mine, argued from
"sensitivity × blast radius", and it is arguable in both directions:

- **CRM first** argues that contacts are the canonical Owner/Group exercise and the
  cheapest place to prove the mechanism.
- **Payroll first** argues that payroll is the requirement that *justifies the project*
  (BR-ACL-001 §1), and that the worst outcome is discovering the design is fail-open
  there.

The third entry, `ksf_FA_ProjectManagement`, is **not** a preference — it is a hard
prerequisite (8 `select('*')` sites and an already-malformed `join()` call,
`ACL_Two_Approaches.md` §5.1 **[V]**), because it is the only existing `ksf-common-db`
consumer and Stage 2 is untestable without it.

> **Decision needed.** If there is a compliance deadline, payroll moves to first and
> CRM to second. Nothing else in the order depends on it.

---

### Q13 — What does a backup/restore do to the masking views?

**Where:** FR-ACL-001-04 §3.4

`db_export()` enumerates objects with `show table status` (`:607`) and filters only by
prefix (`:611-613`). In MariaDB that **includes views**, and `SHOW CREATE TABLE` on a
view returns a `CREATE … VIEW` statement — **not** `CREATE OR REPLACE VIEW`. The
preceding `DROP TABLE IF EXISTS <view>` **does** run through `db_import` (V-5 aside,
that one is in the allow-list).

So a backup/restore cycle may **drop every masking view and then recreate it in a form
`db_import` did not intend**.

**[UNVERIFIED] — no backup was taken and no restore was attempted.** This is the single
highest-risk unverified item in the requirement set: it is the one path that could
silently remove the column-axis control.

> **Needed:** an AC9 dry run on UAT **before** any masking view is deployed.

---

## Decisions already taken (recorded so they are not re-litigated)

| Decision | Requirement |
|---|---|
| Two orthogonal axes: row via ownership tables, column via views. | BR-ACL-001 §2.1 |
| Column axis is **views per sensitivity class**, joinable, join only what you are entitled to. | BR-ACL-001 §2.2, FR-ACL-001-04 §5 |
| Row axis is UNIX-like: one Owner, many Groups, plus Other. | BR-ACL-001 §2.3 |
| Groups are orthogonal to the org chart; `group_kind` on the membership row. | BR-ACL-001 §2.4, FR-ACL-001-01 §3.3 |
| **One data query per request**; policy loaded once into memory. | FR-ACL-001-02 §1 |
| Stage 1 is a **tripwire, not enforcement**, and must say so in code and commit messages. | FR-ACL-001-03 §1 |
| Stage 2 requires the builder to **declare the table**; enforcement may not be enabled before the module is migrated. | FR-ACL-001-03 §3 |
| FA core is **never** touched — 870 call sites permanently out of scope. | BR-ACL-001 R9, FR-ACL-001-03 §2.5 |
| Separate owner and group tables; identity and capability are not fused. | FR-ACL-001-01 §1 |
| `CREATE OR REPLACE VIEW` is the **only** view verb available through `db_import`. | FR-ACL-001-04 V-3 |
| Views are named `0_<table>_<class>` — prefixed, never `v_`-prefixed. | FR-ACL-001-04 V-8 |

## Corrections to the brief this question set was written against

Two premises in the originating brief did not survive checking. Both are documented in
full; recorded here so they are not silently carried forward.

| # | Brief said | Reality | Where |
|---|---|---|---|
| 1 | `0_rbac_record_access.record_lookup` is **UNIQUE** on `(module, record_type, record_id, inactive)`, permitting one row per record and so blocking multi-group membership — "a schema change that must happen first". | **There is no unique constraint.** `SHOW INDEX` returns `Non_unique = 1`; the live DDL says `KEY`. Multiple groups per record are **already** expressible. The real defects are different: **no** uniqueness at all (duplicates possible), **no `user_id` column** (ownership unexpressible), and `team_id NOT NULL` (no group membership unrepresentable). | BR-ACL-001 §3.1, FR-ACL-001-01 §4.1 |
| 2 | 2,860 `db_query(` call sites across 304 files in our modules. | **Not reproducible.** Measured: **1,510 sites / 299 files** (dev trees, vendor excluded); **1,542 / 305** (deployed `fa_modules`); **2,637 / 604** including `vendor/`. FA core's **870** is confirmed exactly. | FR-ACL-001-03 §2.5 |

One further correction, to RBAC's own DDL rather than to the brief:
`0_rbac_teams.owner_id` and `0_rbac_team_members.user_id` carry
`COMMENT 'FK to 0_users.id'`, but `0_users.id` is a `smallint`. The natural key is
`0_users.user_id varchar(60)`. **The schema is right; the comment is wrong**, and an
implementer who trusts it produces a silent join that drops rows. See
FR-ACL-001-01 §2.1.

---

# Open questions — ACL-010 event framework, and CAL-010 Calendar contract

@BABOK Related: BR-ACL-010, FR-ACL-010-01 … 05, BR-CAL-010, FR-CAL-010-001
Date: 2026-10-14
Ranked by the same criterion as Q1–Q13 above: **"how much damage does getting this
wrong cost."** `Q-ACL-010-*` are blocking; `Q-CAL-010-*` are design confirmations.

> This section was **appended** to the existing Q1–Q13 list, not merged into it. The
> numbering runs `Q-ACL-010-n` / `Q-CAL-010-n` so the earlier IDs stay valid.

---

## Blocking

### Q-ACL-010-1 — What is the builder API that carries the declared table? **(highest)**

**Where:** FR-ACL-010-01 §2, §5

**[V]** `from()` stores an opaque string (`QueryBuilder.php:83`), `$select` defaults to
`['*']` (`:26`), `toSql()` implodes raw fragments (`:174-207`), and there are **no public
getters**.

| Option | Cost |
|---|---|
| **(a) Extend the builder** — a declarative table reference + ACL methods | Matches BR-ACL-010 R1, but is a `ksf-common-db` API change on a published package (v1.0.1). |
| **(b) Decorator** — wrap `toSql()` and rewrite the string | **Cannot work.** It cannot distinguish an ACL table from an ordinary one reliably, and cannot reject `SELECT *` before emission. Rejected on capability grounds, not preference. |
| **(c) Caller passes `(module, record_type)` explicitly** on every query | No package change, but 1,510 call sites each restate the fact, and it drifts. |

**Wrong answer cost:** a decorator that *looks* like it enforces ACL but cannot reject
`SELECT *` is a silent bypass.

### Q-ACL-010-2 — Does `prefixTables()` corrupt the column mask?

**Where:** FR-ACL-010-01 §8, FR-ACL-010-02 §2.2, §6

**[V]** The regex at `FaDbAdapter.php:56` matches the bare token `TABLE` after
`FROM|JOIN|INTO|UPDATE|TABLE`. The column mask is
`CASE WHEN :canReadX = 1 THEN col ELSE NULL END`, emitted per column.

**Unverified and genuinely risky:** whether a column named `table`, a column alias
containing one of those tokens, or a string literal containing `FROM` is mangled. The ACs
in FR-ACL-010-02 do **not** cover this. Cheap to test, cheap to be wrong.

### Q-ACL-010-3 — Is there a post-commit point for **non-cart** module writes?

**Where:** FR-ACL-010-03 §1.2, §6

**[V]** FA's `hook_db_postwrite` is **cart/transaction scoped** — it fires for the sales
document types in `AGENTS_ARCH.md` §10.1 and nothing else. **[V]** In
`write_sales_delivery()` it runs at **line 200**, *before* `commit_transaction()` at
**line 201**, so it is post-**write**, not reliably post-**commit**.

For CRM contacts, HRM employees and PM tasks there is **no such hook**. If most module
writes are bare `db_query()` with no explicit transaction, "post-commit" degrades to
"post-statement" — which is safe, but must be *decided*, not assumed.

**Wrong answer cost:** emitting before commit manufactures the dangling ACL rows that
FR-ACL-010-05's sweeper then has to clean up.

### Q-ACL-010-4 — How is "user removed" made detectable? *(the cause (c) blocker)*

**Where:** FR-ACL-010-05 §3.2, BR-ACL-010 §3.1

**[V] Correction to the premise.** `0_users.inactive tinyint(1) NOT NULL DEFAULT 0`
**does exist** (`ksf_fa_current.sql`, `0_users` CREATE TABLE at line 2456). But:

| Path | Behaviour |
|---|---|
| `users_db.inc:75` `get_users()` | reads it (`AND !u.inactive`) |
| `users_db.inc:39-52` `update_user()` | **never sets it** |
| `users_db.inc:14-26` `add_user()` | omits it, relies on `DEFAULT 0` |
| `users_db.inc:118-122` `delete_user()` | **hard `DELETE`** |
| `users_db.inc:130` `get_user_auth()` | **does not check it** |

| Option | Cost |
|---|---|
| **(a) Use `0_users.inactive`** and add the missing write path | **Requires changing FA core's user maintenance** — out of scope for this set. Also must fix `get_user_auth()`, or the flag is not a security control. |
| **(b) Soft-delete in RBAC's own layer** | Leaves FA core deleting rows underneath; ownership rows still dangle. |
| **(c) Accept hard-delete; detect dangling `user_id`** | Feasible now — the sweeper can positively identify cause (c). But **no `user_changed` event fires**, so nothing cascades proactively. |

**Wrong answer cost:** a hard delete leaves ownership rows pointing at a `user_id` that no
longer exists, converting cause (c) into cause (b) — i.e. the system labels a normal
staff departure as "data corruption".

### Q-ACL-010-5 — Correct the misleading FK comments, or the schema?

**Where:** BR-ACL-010 §3.2

**[V]** `0_rbac_teams.owner_id VARCHAR(64)` and `0_rbac_team_members.user_id VARCHAR(64)`
carry `COMMENT 'FK to 0_users.id'` (`ksf_FA_RBAC/sql/install.sql:19-20, 39-40`), but
`0_users.id` is `smallint(6)`; the natural key is `0_users.user_id varchar(60)`.

**The types are already correct — only the comment is wrong** (independently re-derived
here; the same finding is already recorded in `FR-ACL-001-01 §2.1`).

**Recommendation: fix the comment, do not touch the type.** Someone trusting the comment
would join a `VARCHAR(64)` to a `smallint` and get a silent coercion that drops rows.
`VARCHAR(64)` vs `varchar(60)` is harmless over-provisioning.

### Q-ACL-010-6 — Does `hook_invoke_first` treat `null` as "not handled" and `false` as "stop"?

**Where:** FR-ACL-010-03 §2.1, §4 · FR-ACL-010-04 §1.1

The entire R4 protocol ("**`null` return means 'not my concern'**") rests on this. If
`false` and `null` are conflated, a responder that declines is indistinguishable from one
that handled the event, and ownership transitions silently stop applying.

Related: **responder ordering is not guaranteed** across modules **[UNVERIFIED]**, which is
why FR-ACL-010-03 requires audit-log and ownership evaluation to be **two sequential
dispatches**, not one broadcast.

## Design confirmations

### Q-ACL-010-7 — Does the builder detect fan-out from *non-ACL* joins?

**Where:** FR-ACL-010-01 §6

The no-fan-out rule is about **ACL** joins. A business join that multiplies rows still
breaks the caller's row count, and nothing detects it. Out of scope or not?

### Q-ACL-010-8 — What is the orphaned bucket's storage mechanism?

**Where:** FR-ACL-010-05 §1.2, §4, §6

| Option | Cost |
|---|---|
| Dedicated table | Fast; can drift from reality |
| Projection over "governed rows with no ownership row" | Always correct; scans every governed table |
| Flag on a claims table | Cheap; only works for records that have a claims row |

Also unverified: whether the "owner `user_id` absent from `0_users`" check is affordable
at production row counts, and whether it belongs in the sweep or is a separate query.

### Q-ACL-010-9 — Are the proposed ownership tables a hard dependency?

**Where:** BR-ACL-010 §4, FR-ACL-010-04 §4

**[V]** `0_rbac_record_owner` / `0_rbac_record_group` / `0_rbac_group_policy` **do not
exist**. They are *proposed* by `FR-ACL-001-01 §3.1/§3.2`; no `.php` or `.sql` in either
`ksf_FA_RBAC/` tree references them. Every predicate in BR-ACL-010 R2 and FR-ACL-010-02 is
**blocked on FR-ACL-001-01 landing first.** Confirm that ordering is intended.

---

## Calendar — Q-CAL-010-*

**Context:** the Calendar capability contract **largely already exists** — see
[BR-CAL-010](./BR-CAL-010-capability-contract.md) §2. These are the gaps, not a redesign.

### Q-CAL-010-1 — Where does the domain DTO live: module or package?

**Where:** FR-CAL-010-001 §2 (F3), §5

The list hook currently returns a **FullCalendar render array**
(`toFullCalendarArray()`, `FA_Cal_Module.php:403`), which a workflow responder must not
couple to.

| Option | Cost |
|---|---|
| **(a) `ksf-calendar` package** | Correct if there are ≥2 consumers — README #3 requires this |
| **(b) `ksf_FA_Calendar` module** | Fine while one consumer; the ACL orphan responder would be the second, justifying (a) |

### Q-CAL-010-2 — Does task creation need its own DTO, and what fields does it carry?

**Where:** FR-CAL-010-001 §1.1, §2 (F1)

**[V]** The hook takes an untyped `array $data` documented only as *"title, start_date,
source, source_type, etc."* — the literal "etc." (`hooks.php:204`). Only **two** fields
are required: `title`, `start_date` (`CalendarService.php:804-821`). `0_fa_cal_entries`
has ~45 columns.

| Question | Why it is open |
|---|---|
| Own DTO, or document the required fields? | A DTO costs a second class to keep in sync; documentation drifts silently |
| Which columns are part of a *task*? | `source_type = 'task'` already exists **[V — `install.sql:15`]**, but nothing defines its required companions |
| Must `source_type` default to `task`? | **[V]** it silently defaults to `TYPE_EVENT` (`CalendarService.php:92`) |
| How is the **subject employee** identified? | **[V]** `assigned_to VARCHAR(100)` / `user_id VARCHAR(50)` are **free-text, not FKs** — no `employee_id` column exists |

**Wrong answer cost:** two providers disagreeing about what a "task" is, with nothing to
catch it.

### Q-CAL-010-3 — Is there an enforced convention for `assigned_to`?

**Where:** FR-CAL-010-001 §3

Unverified. Two providers writing the same employee differently produce two disjoint sets
for the exact query this capability exists to serve.

### Q-CAL-010-4 — Is `ReviewManager`'s "review" the same concept as this BR's "review task"?

**Where:** BR-CAL-010 §6

**[V]** `ReviewManager` has `createReview` / `getPendingReviews` / `resolveReview` over
calendar entries, driven by `cal.php:2283` / `:2320`. Whether it is a **rule-evaluation
surface** or an existing **task queue** is not established — and it bears directly on
BR-CAL-010's "Calendar must not create review tasks".

### Q-CAL-010-5 — Can the `status_open` closed-list drift from `CalendarEntry::isOpenStatus()`?

**Where:** FR-CAL-010-001 §1.2, §5

**[V]** The closed-status list is **hardcoded in SQL** at `CalendarService.php:461-478`,
with a comment that it replicates `CalendarEntry::isOpenStatus()` "for DB portability".
Two sources of truth, checked by nothing.

---

## Related

- [BR-ACL-001](./BR-ACL-001-record-ownership-and-access-control.md)
- [FR-ACL-001-01](./FR-ACL-001-01-ownership-schema.md)
- [FR-ACL-001-02](./FR-ACL-001-02-row-acl-predicate.md)
- [FR-ACL-001-03](./FR-ACL-001-03-two-stage-enforcement-migration.md)
- [FR-ACL-001-04](./FR-ACL-001-04-column-axis-views.md)
- [BR-ACL-010](./BR-ACL-010-event-driven-ownership.md)
- [BR-CAL-010](./BR-CAL-010-capability-contract.md)
- [FR-CAL-010-001](./FR-CAL-010-001-task-creation-and-event-listing.md)
- [`ACL_Two_Approaches.md`](../ACL_Two_Approaches.md) §7 — the column-axis open decisions, which these do not duplicate