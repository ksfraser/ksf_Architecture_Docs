# Column-Level ACL — Two Approaches (App-Layer and DB-Layer)

**Date:** 2026-10-14
**Status:** DECISION RECORD + design of the new DB-layer half. **No production code
written. Nothing in this document is implemented.**
**Scope:** `ksfraser/ksf-common-db` (`~/Documents/ksf_common_db`, tree at
`v1.0.1-1-g31fee8d`), `ksf_FA_RBAC`
(`~/Documents/ksf_Infrastructure/fa_modules/ksf_FA_RBAC`), the live Integration
database (`ksfii_app-mariadb`, schema `ksf_fa`).
**Companions:** `Column_Level_ACL_Design.md` (push-down vs post-fetch, the
inference-oracle matrix) and `Explicit_Column_ACL_API.md` (the explicit-column
API, enforcement location, join pruning). This document does **not** restate
those; it records a decision that both are built, and designs the DB-layer half
which has no prior design.

Every claim in this document is tagged. **[V]** = verified by executing against
the live MariaDB 10.11 instance or against the real source on 2026-10-14.
**[A]** = asserted from reading source or from SQL semantics, not executed.
**[D]** = design proposal, nothing exists. Anything not marked is a decision.

> **Read this first if you are short on time.** §3.3 contains a hard MariaDB
> finding that kills the obvious dynamic-masking design, and §3.2 contains a
> finding about FA's installer that decides how views may be named. Both were
> found by experiment, not by reading documentation.

---

## 1. The decision

### 1.1 What was decided

**Both approaches will be built.**

| | **A — App-layer** | **B — DB-layer views** |
|---|---|---|
| Enforced by | `ksfraser\CommonDb\Query\QueryBuilder` | MariaDB |
| Mechanism | explicit column contract + projection push-down (`NULL AS col`) | masking `VIEW`s over base tables |
| Scope | queries built through the package | **every** query against the table, from any code path |
| Status | designed in two prior docs, not built | **new design, this document** |

This is not a hedge and it is not a "pick one later" position. Each covers a
class of bypass the other provably cannot, and both are needed.

### 1.2 Why A alone is not enough

A is enforced at exactly one place: `QueryBuilder::toSql()`. Everything that
reaches `db_query()` without passing through that method is unguarded. Concrete
bypasses, all of which exist in this stack today or are one line away:

1. **Any hand-written SQL.** `db_query("SELECT ssn FROM 0_crm_contacts WHERE …")`
   placed directly in a page or a report. A cannot see it. B does.
2. **FA core.** `admin/inst_module.php`, `reporting/rep_*.php`, the GL and
   stock reports, `company/0/` pages. A is only as good as the adoption of
   `ksf-common-db`, and adoption is currently **one module**
   (`ksf_FA_ProjectManagement` — verified 2026-10-14).
3. **The other query-builder fork.** `ksf_payment_destinations/src/QueryBuilder/QueryBuilder.php`
   is a second builder with its own `toFaSql()` (already documented in
   `Explicit_Column_ACL_API.md` §7.2 #5). It does not call A's `toSql()`.
4. **Raw `db_query()` in any of the ~150 FA modules.** Verified: A's blast radius
   is exactly the modules that require `ksfraser/ksf-common-db`.
5. **A future maintainer.** A protects only what uses the builder. B protects
   what the *database* will hand back, whoever asks.

### 1.3 Why B alone is not enough

B is enforced on read paths to a view. It says nothing about a query built
against the base table, and it stops none of the inference oracles
`Column_Level_ACL_Design.md` §2.3 measured, because **every one of those oracles
is a query against a view whose masked column is already `NULL`**:

- `WHERE salary >= :g` on a masked view → `salary` is a `NULL` literal; the
  predicate is constant-folded, so it returns the unfiltered row count. **[A]**
  (MariaDB constant-folds `WHERE NULL` expressions; not separately benchmarked).
  Either way, B does not make it throw.
- `ORDER BY salary`, `GROUP BY salary`, `AVG(salary)`, `COUNT(salary)` on a
  masked view → all operate on the `NULL` literal. No error, no signal.
- B also has **no clause-level policy at all**. It cannot express "you may sort
  by `discount_pct` but not `net_price`", because it never sees the statement's
  intent — only the column list.

B also **cannot stop the projection at all if the caller names the base table.**
B only bites when the caller is *cooperating* by querying the view. It is a
strong control against accidental exposure and against non-cooperating code that
happens to point at the view; it is **not** a control against a caller who
knows the base table exists.

### 1.4 How they are intended to compose

Defence in depth, with a **strict hierarchy** (see §4). In one line each:

| Threat | Caught by | Why the other misses it |
|---|---|---|
| Hand-written `db_query()` reading a protected column | **B** | A is not in the call path |
| A repository query that asked for `*` | **A** (`StarNotPermitted`) | B cannot see `SELECT *` from the view either — it happily returns its (masked) full column list, which is a *silent* answer rather than a loud failure |
| A query filtering/ordering/grouping on a protected column | **A** (clause rejection) | B sees only `NULL`; it cannot throw |
| A caller that queries the **base table** directly | **B**, by **denying base-table grants** (requires §4's DB-account work) | A cannot help — the statement never reached the builder |
| The mirroring-column leak (`payroll.gross` reveals `emp.salary`) | **neither** | Accepted residual — see §2.6 |
| A **write** to a protected column | **neither** | Out of scope for both; see §7 OD-7 |

The single most important sentence in this section:

> **B is only a control if reading the base table is denied. A view next to an
> open base table is documentation, not enforcement.**

Whether we do that grant work is OD-1 (§7). It is the difference between B
being a control and B being a convenience.

---

## 2. Approach A — app-layer (summary; not re-derived here)

Full treatment: `Explicit_Column_ACL_API.md` (API, enforcement location, join
pruning) and `Column_Level_ACL_Design.md` (push-down vs post-fetch, oracle
matrix). This section records only what this document needs.

### 2.1 The explicit-column contract **[D]**

Enforcement lives in `QueryBuilder::toSql()` — the single point where the whole
statement exists and before it becomes a string. It sits above both adapters, so
`FaDbAdapter` and `PdoDbAdapter` inherit it with zero duplication and neither
can bypass it.

The contract, as already specified in `Explicit_Column_ACL_API.md` §5.1
(unchanged by this decision):

```php
namespace ksfraser\CommonDb\Security;

interface ColumnPolicyInterface
{
    public function isActive(): bool;                                // FR-CLAC-120
    public function manages(string $table): bool;                    // FR-CLAC-121
    public function canRead(string $table, string $column): bool;    // FR-CLAC-122
    public function visibleColumns(string $table): array;           // FR-CLAC-123
}
```

`NullColumnPolicy` returns `isActive() === false`, which is the
backward-compatibility guarantee: with no policy registered, `toSql()` output is
byte-identical to today (**FR-CLAC-103**, verified achievable — see §6.4).

`manages()` is per-table and is the lever that keeps the release non-breaking:
a policy that does not manage `stock_master` leaves ~99% of queries untouched.

### 2.2 The loud `SELECT *` rejection

`StarNotPermitted`, thrown from `toSql()`, never warned, never auto-expanded
(**FR-CLAC-121**, **FR-CLAC-124**). Two reasons it must be loud:

1. **A silent answer is a wrong answer.** `SELECT *` from a masked view returns
   the full *view* column list with masked values `NULL`. The caller gets rows
   and never learns that a policy was in force. A `SELECT *` from a policy-active
   builder tells them immediately.
2. **`db_query()` failure is uncatchable.** A malformed statement reaching FA
   raises `E_USER_ERROR` (`ksf_Architecture_Docs/README.md` standing decision
   #4), so the builder must never emit SQL it has not validated.

### 2.3 Join pruning rules

Adopted in the narrowed form (`Explicit_Column_ACL_API.md` §6.2), because the
naive rule is unsafe. **JD-3 — INNER/CROSS/RIGHT/FULL join with no permitted
columns → hard error, never silently dropped (FR-CLAC-131).** The measured
reason **[V via PoC, reproduced in the cited doc]**:

| Statement | Result |
|---|---|
| `SELECT COUNT(*) FROM emp e INNER JOIN dept d ON d.id=e.dept_id AND d.cost_code='CC-1'` | **2** |
| same, join dropped | **3** |

Dropping an inner join turns the statement into a `COUNT(*)` existence oracle on
a denied column. Pruning is limited to `LEFT JOIN` in non-aggregate statements
without `GROUP BY`/`DISTINCT` (**JD-4/JD-5**, FR-CLAC-132), and every automatic
prune is audited and exposed (**JD-6**, FR-CLAC-133).

### 2.4 Where the data dictionary fits **[V]**

`TableDefinition` stays policy-free (**FR-CLAC-104**). It needs two additive
changes, both verified as absent today: `columnDef()` is `private`
(`src/Dictionary/TableDefinition.php:139`) and there is no `sensitivity` field
(`column()` stores only `name,type,null,auto_increment,default`, `:64-75`).

### 2.5 RBAC is not ready **[V — updated from the prior doc]**

`Explicit_Column_ACL_API.md` §3.2 described RBAC's working tree as having
uncommitted deletions. Confirmed and **now precisely characterised**:
`git status` in `ksf_FA_RBAC` shows **15 tracked deletions and 8 untracked
directories**. The untracked directories are a PSR-4 move — `src/RbacService.php`
→ `src/Ksfraser/FrontAccounting/Rbac/RbacService.php`, matching the
`composer.json` PSR-4 declaration. So the restructuring is real work in progress,
not damage. But three classes are **genuinely gone, not moved**:

- `Repository/FaRecordAccessRepository.php` (247 lines)
- `Repository/FaTeamRepository.php` (257 lines)
- `Provisioner/UserProvisioner.php` (169 lines)

No `Repository/` or `Provisioner/` directory exists under
`src/Ksfraser/FrontAccounting/Rbac/`. Consequence, unchanged and confirmed:
**there is no live record-level data source for column policy to hang on.**
Phase 0 of the plan remains blocking.

### 2.6 The known residual, stated plainly **[V via PoC]**

A join can surface a protected value through a **different table's column** with
no reference to the protected column anywhere in the statement:

```sql
SELECT e.id, e.name, pr.gross FROM emp e INNER JOIN payroll pr ON pr.emp_id = e.id
```

with `emp.salary` denied and `payroll.gross` permitted, returned the real
salary values. **Neither A nor B closes this.** The only control is per-table
classification — `payroll.gross` must be classified sensitive in its own right.
This is recorded as an accepted residual risk, not as a solved problem.

---

## 3. Approach B — DB-layer masking views (new design)

Target: **MariaDB 10.11** **[V — `SELECT VERSION()` returns
`10.11.14-MariaDB-ubu2204`]**. There is **no Postgres-style row-level
security**, so this is the only DB-native option available. Current state of
schema `ksf_fa`: **243 base tables, 0 views** **[V]**.

### 3.1 Static masking syntax

The two masking forms, both **[V]** accepted by MariaDB 10.11:

```sql
-- (a) unconditional redaction: value never leaves the server
CREATE OR REPLACE VIEW 0_crm_contacts_masked AS
  SELECT id, name, email, NULL AS ssn, NULL AS tax_id
  FROM   0_crm_contacts;

-- (b) conditional redaction: needs a *stable, server-side* predicate
CREATE OR REPLACE VIEW 0_crm_contacts_v AS
  SELECT id, name, email,
         CASE WHEN <predicate> THEN ssn ELSE NULL END AS ssn
  FROM   0_crm_contacts;
```

Form (b) only earns its keep for a **per-row** predicate, exactly as
`Column_Level_ACL_Design.md` §2.2(a) established: `CASE WHEN 1=1 THEN salary END`
is arithmetically identical to `salary` and is not redaction.

### 3.2 Can masking be DYNAMIC per session? — the decisive finding

**The obvious answer — MySQL/MariaDB session variables — does not work.**

```sql
CREATE OR REPLACE VIEW 0_crm_contacts_dyn AS
  SELECT id, name, CASE WHEN @acl_role = 'hr' THEN ssn ELSE NULL END AS ssn
  FROM 0_crm_contacts;
```

**[V]** MariaDB 10.11.14 rejects this at CREATE time:

```
ERROR 1351 (HY000): View's SELECT contains a variable or parameter
```

This is not a configuration issue and there is no workaround flag; a view body
may not reference a user variable or a stored-program parameter. **Any design
that assumes "set a session variable, then read the view" is dead on arrival in
MariaDB.** It is worth stating bluntly because the `ksf_db_security` prior art
(`~/Documents/ksf_db_security`) is built on per-role *static* views plus
per-user `GRANT`, which fails for a different reason (§3.5) — so neither codebase
currently holds a working answer.

#### 3.2.1 What does work: a server-side context table keyed by `CONNECTION_ID()`

**[V]** — this compiles, and returns the real value when the context row says
`hr`:

```sql
CREATE TABLE 0_acl_ctx (conn_id BIGINT PRIMARY KEY, role VARCHAR(20));

CREATE OR REPLACE VIEW 0_crm_contacts_v AS
  SELECT t.id, t.name, t.email,
         CASE WHEN (SELECT c.role FROM 0_acl_ctx c
                     WHERE c.conn_id = CONNECTION_ID()) = 'hr'
              THEN t.ssn ELSE NULL END AS ssn
  FROM 0_crm_contacts t;
```

`SHOW CREATE VIEW` confirms the definition is stored and evaluated as expected.
**Why it survives where `@var` does not:** the view body references no variable;
`CONNECTION_ID()` is a function, and the context lives in a table the server can
read.

Its limits, stated precisely:

- **It requires a write on every request** before any masked query. FA opens a
  fresh, non-persistent connection per request **[V — `connect_db_mysqli.inc:32`
  and `:205` call `mysqli_connect()` with no `p:` persistent host]**, so
  `CONNECTION_ID()` is stable within a request and changes between them. That is
  favourable, but it means an `INSERT INTO 0_acl_ctx` on the hot path.
- **No context row ⇒ deny.** Verified: in a connection with no matching row the
  `EXPLAIN` reports `no matching row in const table` and the query returns the
  `NULL` branch. **This fails closed, which is the right default** — but a
  missed write degrades every masked page to "all columns NULL" with no error.
  That is a silent-availability failure mode and needs monitoring.
- **Connection recycling is not a leak.** A dead connection's row is garbage,
  never consulted by anyone else, because `CONNECTION_ID()` is not reused within
  a `max_connections` window in any way I could test. **[A — not stress-tested
  under connection churn; treat as unproven.]**
- **This is not per-row.** It is per-*connection*, i.e. per-request. Per-record
  projection (SuiteCRM semantics) would need `CASE WHEN <record predicate>` and is
  OD-5.

`CURRENT_USER()` **also compiles inside a view** **[V]** and is useful for
coarse, per-DB-account masking — but §3.5 shows FA has exactly one DB account, so
it is currently useless for per-FA-user policy.

### 3.3 Naming, versioning, and the company prefix — a hard installer finding

FA's convention: every table is `{TB_PREF}logical`, and module SQL files use the
literal `0_` prefix. FA's installer, `db_import()`
(`FA/2.4.3/admin/db/maintenance_db.inc:267`), does the substitution at **line
338**:

```php
$line = str_replace("0_", $connection["tbpref"], $line);
```

Two properties of that single line decide everything:

1. **It is a whole-line, unconditional, textual replacement** — not a
   table-name-aware pass. Every occurrence of `0_` anywhere in the line is
   rewritten, including inside string literals and comments.
2. **It runs per company.** Installing/updating a module for company 2 rewrites
   `0_` → `1_` throughout.

**Consequence for views — the risk the brief asked about, stated:**

| Naming | What `db_import` does | Verdict |
|---|---|---|
| `0_crm_contacts_masked` (prefixed, FA convention) | Rewrites **both** the view name and the `FROM 0_crm_contacts` in its body → company 2 gets `1_crm_contacts_masked` over `1_crm_contacts`. Self-consistent. **[V via code path + live test of the same statement]** | **RECOMMENDED** |
| `v_crm_contacts_masked` / `crm_contacts_masked` (unprefixed) | The name is untouched, but the body's `FROM 0_crm_contacts` **is** rewritten. Company 2's install **mutates the single global view** to point at `1_crm_contacts`. Company 1's masked reads then silently return company 2's data (masked, or worse, unmasked if the target has different columns). | **REJECT** |

So a non-prefixed view name is not "one view for everyone" — it is a shared
object whose body is rewritten in place by every subsequent company install.

**Recommended naming: `0_<logical>_masked`** — obeys FA's convention, is
per-company, and is rewritten coherently by the installer. For versioned
masking sets (a second, stricter profile), `0_<logical>_masked_v2`; do **not**
use a `v_` prefix, for the reason above.

**Second installer finding — `db_import`'s allow-list.** Lines 274-286 admit only
`create`, `delimiter`, `alter table`, `insert`, `update`, `set names`,
`drop table if exists`, `drop function if exists`, `drop trigger if exists`,
`select`, `delete`. Simulating that exact loop over a candidate `sql/*.sql`
**[V — line-by-line simulation against the real allow-list]**:

| Statement | Verdict |
|---|---|
| `CREATE OR REPLACE VIEW 0_x AS SELECT … FROM 0_y` | **runs** (matched by `create`) |
| `CREATE VIEW 0_x AS SELECT …` (no `OR REPLACE`) | runs, but on an existing view raises error **1050**, which is in `$ignored_mysql_errors` (`:298`) → **silently ignored, stale view survives** |
| `DROP VIEW IF EXISTS 0_x` | **silently dropped — never runs** |
| `DROP VIEW 0_x` | **silently dropped — never runs** |
| `ALTER VIEW 0_x AS …` | **silently dropped — never runs** |
| `DROP TABLE IF EXISTS 0_x` | runs — **and would silently drop the view**, since `information_schema` treats views and tables alike |

Three operational rules follow, and they are mandatory:

- **Only `CREATE OR REPLACE VIEW` is available.** There is no drop verb.
  **[D]** Any view removal must go through `DROP VIEW` issued by application
  code (`db_query`), never through `sql/*.sql`.
- **`CREATE OR REPLACE VIEW` must respecify the entire column list.** Verified
  it accepts a changed column list **[V]**. Column *removal* by `OR REPLACE` was
  not separately tested **[— not verified]**.
- **Never write `DROP TABLE IF EXISTS <view>`** in module SQL to reset a view.
  It works, and it is the only "drop" that runs — which makes it a foot-gun in a
  file that also declares base tables.

### 3.4 Performance **[V — for the specific case measured]**

The commonly assumed penalty — "a view is a derived table, so queries get
slower" — **does not apply to simple masking views in MariaDB 10.11.** The
optimizer **merges** the view into the outer query. Measured on an indexed table
(`KEY(name)`), `EXPLAIN` is byte-identical between the base table and the view:

```
SELECT id,name FROM 0_big WHERE name='ann'          -- base
  type: ref  key: name  rows: 1  Extra: Using where; Using index
SELECT id,name FROM 0_big_masked WHERE name='ann'   -- through the masked view
  type: ref  key: name  rows: 1  Extra: Using where; Using index
```

Same `key`, same `Using index` (covering index preserved).

**Caveats, so this is not over-read:**

- Measured on a 4-row table. The plan shape is what matters, not the timings;
  **no timings were taken**.
- The `CONNECTION_ID()` subquery form (§3.2.1) is **not** a mergeable view — it
  adds a `SUBQUERY` node to the plan **[V]**. It is a correlated subquery
  evaluated per outer row unless the optimizer can prove otherwise. On a large
  table this is the case that needs benchmarking before use.
- **Unmeasured:** cost of the masked view on FA's real report queries, and
  behaviour on a large table for both forms. Do not quote a number.

### 3.5 Why the `ksf_db_security` view design does not port, re-verified **[V]**

`ksf_db_security/src/MySql/ViewManager.php:146` names views
`{prefix}{table}_mod_{role}_v` and `:102` does `GRANT SELECT ON <view> TO
'user'`. Verified against the live server: **there is exactly one non-system
MySQL account.**

```
ksf_user@%   GRANT ALL PRIVILEGES ON `ksf_fa`.* TO `ksf_user`@`%`
```

`mysql.user` contains only `ksf_user`, `root`, `mariadb.sys`, `healthcheck`.
Per-user `GRANT` therefore **cannot** distinguish FA users — every FA user shares
`ksf_user`. Role-keyed views + per-user grants are structurally impossible
without giving every FA user a database account, which is a far larger change
than the ACL.

`ksf_db_security` also has a live leak in `Dao/VirtualView.php:150-159`
(`hasColumn('id')` then `SELECT *`), and no tests, no git repo, no consumers.
**Its view/DAO half should be retired, not ported.** The static-masking *idea*
is what this document carries forward.

### 3.6 The write path — a hard constraint **[V]**

A view containing **any** `NULL AS` or `CASE … ELSE NULL` masked column is
**not insertable**. Measured matrix, against MariaDB 10.11:

| View | `INSERT … VALUES` | `INSERT … SELECT` | `UPDATE` masked col | `DELETE` |
|---|---|---|---|---|
| `SELECT id,name,NULL AS ssn,salary` | **1471 not insertable-into** | **1471** | **1348 not updatable** | **works** |
| `SELECT id,name,NULL AS ssn,salary` (partial) | **1471** | **1471** | works on pass-through cols | **works** |
| `SELECT id,name,salary` (no masking) | works | works | works | works |

(1471 = `The target table … of the INSERT is not insertable-into`; 1348 =
`Column 'salary' is not updatable`.)

Good news buried in that: **it fails loudly. No row was inserted, and the
caller's supplied value did not leak into the base table** **[V — row id 70
checked and absent]** — i.e. MariaDB does not silently substitute the `NULL`
default and quietly drop the write.

Architectural consequence: **B is read-only by construction.** Every write path
must target the base table. Any module that reads through a view and writes
through it will break on insert with a 1471 that surfaces as FA's uncatchable
`E_USER_ERROR`.

### 3.7 Interaction with `TableDefinition` and the query builder

**`TableDefinition` (§3.4 of the prior docs):** a view is not a table. It has no
independently meaningful DDL, `INSERT` or `UPDATE` — §3.6 shows the last two do
not work. Therefore:

- A view **must not** get a `TableDefinition`. **[D]** It would produce
  `createSql()`/`insertSql()`/`updateSql()` that are wrong or fail.
- A view **does** need a column list for the explicit-column API to check against
  — a new, view-shaped dictionary type is required. **[D]**
- `TableDefinition::sensitivity()` stays the declaration of which columns are
  candidates; the view generator consumes it. The dictionary remains policy-free
  (**FR-CLAC-104**); the *view builder* is what applies policy.

**Query builder table resolution — verified behaviour of
`FaDbAdapter::prefixTables()` (`src/Adapter/FaDbAdapter.php:49-78`), executed
against the real adapter:**

| Input SQL | Output (prefix `0_`) | Verdict |
|---|---|---|
| `SELECT id FROM crm_contacts_masked` | `SELECT id FROM 0_crm_contacts_masked` | **works** |
| `… FROM crm_contacts a LEFT JOIN crm_contacts_masked m ON …` | both prefixed | **works** |
| `… FROM crm_contacts, crm_contacts_masked` | **only the first prefixed** | **broken** (pre-existing) |
| `WITH x AS (SELECT id FROM crm_contacts) SELECT id FROM x` | `… SELECT id FROM 0_x` | **broken** — CTE aliases are prefixed as if they were tables; CTEs are unusable with this adapter |
| `SELECT id FROM 0_crm_contacts` with prefix `1_` | unchanged | **broken for company 2** |

**[D] Consequences for view naming, and they are firm:**

1. **Reference views unprefixed in builder code** (`from('crm_contacts_masked')`),
   never `from('0_crm_contacts_masked')`. The adapter adds the prefix.
2. **The comma-join bug must be fixed before B can be used**, because a masked
   view joined by comma to a base table would silently leave one unprefixed.
   This is a pre-existing bug in the adapter, not caused by B.
3. **CTEs are not available** as a way to layer masking in the builder.

---

## 4. How the two compose

### 4.1 The hierarchy — one rule, no ambiguity **[D]**

> **A is authoritative for *intent* (what a caller may ask for).
> B is authoritative for *transport* (what the server will hand back).
> Where they disagree, the request is DENIED — never silently widened, never
> silently narrowed.**

Stated operationally:

1. **A's denial wins over B's permission.** If the builder refuses to emit a
   statement because it names a denied column, the statement does not run — even
   though a view would have masked it. Rationale: a denied request that silently
   succeeds teaches the caller nothing and hides the bug. B's masking is a
   safety net for when A is *not present*, not a licence to skip A when it *is*.
2. **B's masking is never visible to A as a permission.** A masked column is
   still a denied column to A. This is what makes the hierarchy coherent rather
   than confusing: **the view does not change the policy, it changes what an
   absent policy can leak.**
3. **Never both.** A query must target either the base table (with A active) or
   the view (with A inactive or not managing that table). Mixing — "A allows this
   column, and I read it from the view" — means the column is `NULL` for no
   reason the caller can see, which is the most confusing state possible and is
   prohibited.
4. **Write paths always target the base table** (§3.6), always with A active.
   B is never in the write path.

The diagnostic that keeps this honest: if a page shows a column as empty and no
denial was raised, **B masked it**. If a page errors, **A refused it**. If a page
works and shows the column, **neither blocked it** — which is either correct or
a finding.

### 4.2 The one bypass A uniquely closes **[V]**

`SELECT *` from a masked view returns the view's **complete** column list with
masked values `NULL`. The caller gets rows and no signal that a policy exists.
Under A the same query raises `StarNotPermitted` **before any SQL is issued**.
This is not a theoretical difference: it is the difference between "a report
that quietly omits salary" and "a report that tells you it cannot show salary."

---

## 5. Phased plan

Ordering is load-bearing. The constraint below is verified, not assumed.

### 5.1 The ordering constraint **[V, 2026-10-14]**

`ksf_FA_ProjectManagement` is the **only** consumer of `ksf-common-db` that uses
`QueryBuilder`, and it is not ready:

- **Exactly 8 `select('*')` call sites**, matching the brief precisely:
  `ProjectTypeRepository.php:42,53,63`; `ProjectRepository.php:73`;
  `TaskRepository.php:75,114`; `AssignmentRepository.php:83,143`.
- **Raw-clause filter builders: 4 methods, ~10 raw `where()` clauses**
  (`ProjectRepository.php:172,175,178`; `TaskRepository.php:244,247,250,253`;
  `AssignmentRepository.php:162,165`; plus `ProjectTypeRepository.php:44`,
  `ReportService.php:91-94`) and **~30 further raw `where()`/`orderBy()`/
  `groupBy()` calls** across the repositories.

The brief's "6 raw-clause filter builders" is a conservative subset of what I
counted; the true figure is larger. Either way the conclusion is the same, and
it is the governing constraint:

> **App-layer enforcement cannot be switched on in any pod until those call
> sites are migrated.** With `NullColumnPolicy` this is free (byte-identical SQL);
> the moment a policy is registered, every raw clause becomes unverifiable and
> every `select('*')` becomes a hard error. A single `active => true` on a pod
> with the current ProjectManagement code is a page-failure event, and under FA's
> `E_USER_ERROR` semantics it is a silent mid-render death, not a caught
> exception.

**One incidental finding, verified by executing the real builder today:**
`TaskDependencyRepository.php:75` calls `$qb->join('INNER', $table, $on)` against
the shipped one-argument `join(string $clause)`
(`src/Query/QueryBuilder.php:112`). PHP silently discards the extra arguments, and
the builder emits:

```sql
SELECT d.task_id FROM 0_task_dependencies d INNER WHERE t.project_id = :project_id
```

That is malformed SQL and it is **already broken today, independent of any ACL
work.** Fixing it (adding `joinStructured()`) is a prerequisite for A anyway,
because that call site is one of the raw-clause sites A must migrate.

### 5.2 Sequence

| Phase | Track | Deliverable | Exit criteria |
|---|---|---|---|
| **0** | both **(blocking)** | Stabilise `ksf_FA_RBAC`: commit the PSR-4 move, resolve the 15 deletions (three classes are genuinely gone), settle the `php>=7.4` vs 7.3 floor | Clean tree, module tests green |
| **1** | A | Builder introspection, **no behaviour change**: read-only accessors, public `TableDefinition::columnDef()`, `sensitivity()`, alias→table map, `joinStructured()`, fix the comma-join and CTE defects in `prefixTables()` | Existing tests unchanged; `toSql()` byte-identical. Ship **v1.1.0** |
| **2** | A | Policy contract + `SELECT *` rejection + `NULL AS` push-down + clause rejection, all **opt-in** | New tests; null policy ⇒ identical SQL. Ship **v1.2.0** |
| **3** | **inventory** | **Column-protection inventory** — decide which columns, on which tables, are sensitive (§6 is blocked on this) | A reviewed list exists. **Blocks all of B.** |
| **4** | A | Migrate `ksf_FA_ProjectManagement` off the 8 `select('*')` sites and the raw clauses | CI grep check: no `select('*')`, no raw `where()` under a policy |
| **5** | B | **Read-only view builder** (§6) + `sql/views.sql` using **only** `CREATE OR REPLACE VIEW` with literal `0_` | Views created for company 1; `EXPLAIN` parity with the base table (§3.4) |
| **6** | B | **Per-company view install** verified for company 2 | `1_*` views exist and point at `1_*` tables (§3.3) |
| **7** | B | Decide and implement the base-table grant posture (**OD-1**) | Without this, B is documentation only (§1.4) |
| **8** | both | `RbacColumnPolicy`, storage, admin UI; post-fetch assertion layer; inference regression suite | Regression suite fails if a leak vector is reintroduced |

**Phase 3 sits before Phase 5 deliberately.** Building a view generator before
knowing which columns need protecting produces a general-purpose view factory
with no consumer — and §6 explains why that is the wrong thing to build first.

---

## 6. The future view builder in `ksf_common_db`

### 6.1 Scope

A `ksfraser\CommonDb\Dictionary` (or new `Security`) component that turns a
column-protection declaration into `CREATE OR REPLACE VIEW` SQL, plus the
`ColumnDefinition`-shaped dictionary needed to describe a view's columns without
pretending a view is a table.

**Explicitly out of scope** (§3.6): `INSERT`/`UPDATE`/`DELETE` against views,
DDL for views, and any drop path.

### 6.2 Why it is blocked **[D — decision]**

**There is no column-protection inventory.** Nothing in this stack states which
columns are sensitive. Specifically:

- `TableDefinition` has no `sensitivity` field **[V — `:64-75`]** and no
  `TableDefinition` in any module declares one.
- RBAC's `0_rbac_record_access.projection` (`sql/install.sql:67`) is a 32-char
  *name*, is never read or written by any PHP **[V — grepped]**, and is not a
  mask.
- The legacy `ksf_modules_common` had exactly one sensitivity bit,
  `'read'` vs `'readwrite'`, consumed **only** to compute
  `write_properties_array` — never consulted when building a SELECT list **[V
  — documented in `Explicit_Column_ACL_API.md` §2.1]**.
- `ksf_FA_ProjectManagement`'s `budget` and `revenue_amount` were used as the
  worked example throughout the prior docs. **Those are illustrative, not a
  finding.** No one has confirmed `0_ksf_pm_projects.budget` is actually
  sensitive.

Building a view factory before that inventory means guessing. Guessing wrong is
expensive in a way that is specific to B: a masking view duplicates the schema,
so **a column added to the base table does not appear in the view** **[V]**. The
application then reads a view, gets a stale column list, and either errors or —
worse — a newly-added column containing sensitive data is *not in the view at
all*, so it is not even `NULL`, it is absent, and no amount of A-side policy
knows to look for it.

**This is the single biggest schema-drift hazard in B**, and it is the reason
B's cost is not "one extra query" but "one extra thing that must be kept in
step with the base table forever." **[D]**

### 6.3 Interface sketch — illustrative only, **[D]**, not an API

```php
namespace ksfraser\CommonDb\Dictionary;

/**
 * A view's column list. Distinct from TableDefinition: a view has no
 * writable columns (§3.6) and no independent DDL.
 */
interface ColumnListDefinition
{
    /** @return string[] logical column names, in view order */
    public function columns(): array;

    public function hasColumn(string $name): bool;
}

/**
 * Emits CREATE OR REPLACE VIEW for one company prefix.
 *
 * Emits nothing else. In particular it MUST NOT emit DROP VIEW or
 * DROP TABLE: FA's db_import allow-list silently discards both (§3.3),
 * and DROP TABLE on a view succeeds by accident.
 */
interface ViewBuilderInterface
{
    /**
     * @param string         $table     logical (UNPREFIXED) table name;
     *                                  FaDbAdapter adds the prefix, so it
     *                                  MUST NOT be pre-prefixed (§3.7)
     * @param string[]       $masked    columns to redact
     * @param string[]       $visible   permitted columns, in order
     * @param string         $prefix    the company TB_PREF, e.g. '0_'
     * @param string|null    $contextTable
     *                                  server-side context table for the
     *                                  dynamic form (§3.2.1); null emits
     *                                  the static NULL AS form
     *
     * @return string SQL containing ONLY CREATE OR REPLACE VIEW
     */
    public function createMaskedViewSql(
        string $table,
        array $masked,
        array $visible,
        string $prefix,
        ?string $contextTable = null
    ): string;

    /** View name only, for query-builder resolution. 0_<logical>_masked */
    public function viewName(string $table, string $suffix = '_masked'): string;
}
```

Deliberately absent: anything that executes DDL. The builder emits SQL; a caller
in the module's install path runs it through `db_query()`. Emission and
execution are separated so the SQL is unit-testable without a database — which,
given that §3.2.1 and §3.6 are the two findings most likely to be re-derived
wrongly by a future maintainer, is where the tests should live.

### 6.4 Why this is additive and non-breaking **[V]**

`FaDbAdapter::prefixTables()` returns the SQL unchanged when
`$this->tablePrefix === ''` (`:51-53`), and `NullColumnPolicy` keeps the
compiler uninvoked. So a package at v1.x with a view builder present but unused
behaves exactly like v1.0.1. **[D]** the no-op guarantee is sound; it has not
been regression-tested with a view builder present because one does not exist.

---

## 7. Open decisions — ranked

Ordered by "how much damage does getting this wrong cost".

### OD-1 — Is the base table actually denied? (highest)

If `ksf_user` keeps `ALL PRIVILEGES ON ksf_fa.*`, **B is not a control** — it is
documentation. Any code can query `0_crm_contacts` and read `ssn` in full, and
B stops nothing (§1.4). Granting per-view `SELECT` and revoking base-table
`SELECT` means **renaming existing tables** or introducing a
`FA`-compatible "secure schema" — an enormous change to FA core's
`db_escape`/`prefixTables` assumptions.

Without this decision, phases 5-6 may be building something that enforces
nothing. **Decide before Phase 5, not after.** This is the one open item that
can invalidate the whole of B.

### OD-2 — Default posture: allow-all or deny-all?

Unchanged from `Column_Level_ACL_Design.md` §7 Q1 and
`Explicit_Column_ACL_API.md` §9 Q1, and still open. A's answer is already
recommended: **allow-all when no policy object is registered; deny-all for any
table a registered policy does not list** (`manages()` returns false otherwise).
That makes enabling column ACL a deliberate, table-by-table act.

For **B the question has no good default**, because a view is opt-in by
construction: there is no view for a table nobody has classified, so every
unclassified table is implicitly unprotected. There is no fail-closed posture
available at the DB layer without classifying every table first.

### OD-3 — Where is policy authoritative: code, or the `0_rbac_column_policies` table?

If A and B disagree because one reads RBAC's table and the other reads a PHP
array, the hierarchy in §4 has nothing to enforce. Single source, or §4 collapses
into "two systems, two answers". Recommend the table, with the view generator
reading it at install time and A reading it per request.

### OD-4 — Is dynamic (per-request) masking required at all, or is static enough?

§3.2.1 shows dynamic masking is achievable via a `CONNECTION_ID()` context table
but costs a write on every request and a correlated subquery in every masked
query's plan. If the real requirement is **role-based** (a small number of fixed
masks), one static view per role, selected by the caller, is far cheaper — at the
cost of not being a per-user control. This decision determines whether §6.3 needs
the `contextTable` parameter at all.

### OD-5 — Per-request static mask, or per-record projection?

Carried forward from `Column_Level_ACL_Design.md` §7 Q3. Unchanged: v1 is
per-request. A per-record mask needs `CASE WHEN <record predicate> THEN col END`
and composes with record-level ACL, which RBAC does not have (§2.5).

### OD-6 — Retire `ksf_db_security`?

Recommend **yes** — untested, no consumers, structurally broken by the single
`ksf_user` account (§3.5), and carrying a live `SELECT *` leak. Its
encryption-at-rest half (`Encrypted/EncryptedFields.php`) is a different concern
and should be evaluated separately — it reuses one key for AES and HMAC with no
key separation, which is a defect worth its own decision.

### OD-7 — Write path.

Reads only, or also `INSERT`/`UPDATE`? Note `TableDefinition::updateSql()`
(`:231-245`) writes every writable column unless the caller filters — a
mass-assignment hazard that **exists today, independent of RBAC**. Independently,
§3.6 means B can never be in the write path at all.

### OD-8 — Namespace normalisation.

`Ksfraser\FrontAccounting\Rbac\` (capital K, in `composer.json:20`) vs
`ksfraser\` (lowercase, everywhere else). PHP treats these as different class
names. A `ColumnPolicyInterface` type-hint crossing that boundary will not match
if the two sides disagree. **Decide before Phase 8.**

---

## Appendix A — What was verified, and how

Live system: `ksfii_app-mariadb`, image `docker.io/library/mariadb:10.11`,
database `ksf_fa`. All probe databases (`aclprobe`, `aclprobe2`) were **dropped**
after use; no schema in `ksf_fa` was modified.

| # | Finding | How |
|---|---|---|
| 1 | MariaDB **10.11.14-ubu2204** | `SELECT VERSION()` |
| 2 | `ksf_fa` has **243 base tables, 0 views** | `information_schema.TABLES` / `.VIEWS` |
| 3 | **One** non-system DB account: `ksf_user@%`, `ALL PRIVILEGES ON ksf_fa.*` | `mysql.user`, `SHOW GRANTS` |
| 4 | `@var` in a view body → **ERROR 1351** | `CREATE VIEW` executed |
| 5 | `CASE … (SELECT role FROM ctx WHERE conn_id = CONNECTION_ID())` **compiles and works** | created, queried at two role values |
| 6 | `CURRENT_USER()` in a view body **compiles** | created and queried |
| 7 | View over a view **works** | created, queried |
| 8 | Simple masking views are **merged**; `EXPLAIN` identical to base table | `EXPLAIN` on both |
| 9 | The `CONNECTION_ID()` form adds a `SUBQUERY` node to the plan | `EXPLAIN` |
| 10 | Masked views are **not insertable**: 1471 (`VALUES` and `SELECT`), 1348 on `UPDATE`; `DELETE` works; **no silent write** | 4-view × 2-insert matrix, then checked the base table |
| 11 | `ALTER TABLE … ADD COLUMN` does **not** propagate to the view | `ALTER` then `SELECT *` from view |
| 12 | `CREATE OR REPLACE VIEW` accepts a changed column list | created 2-col then 3-col |
| 13 | Views are created with `DEFINER=<creator> SQL SECURITY DEFINER` | `SHOW CREATE VIEW` |
| 14 | `db_import` substitutes `0_` → TB_PREF on the **whole line** | read `maintenance_db.inc:338` |
| 15 | `db_import` allow-list **silently discards** `DROP VIEW`, `DROP VIEW IF EXISTS`, `ALTER VIEW`; accepts `CREATE*`; ignores 1050 for `CREATE VIEW` | line-by-line simulation of the real loop (`maintenance_db.inc:274-375`) |
| 16 | `prefixTables()` prefixes view names in `FROM`/`JOIN`; **leaves the 2nd table of a comma-join unprefixed**; **prefixes CTE aliases**; leaves `0_`-prefixed names alone under a `1_` prefix | real adapter, reflection-invoked |
| 17 | `TaskDependencyRepository.php:75`'s 3-arg `join()` emits `… FROM 0_x d INNER WHERE …` | real `QueryBuilder` executed |
| 18 | `ksf_FA_ProjectManagement` has **exactly 8** `select('*')` sites | `grep` |
| 19 | RBAC: 15 tracked deletions, 8 untracked dirs; `FaRecordAccessRepository` / `FaTeamRepository` / `UserProvisioner` genuinely gone | `git status` + directory listing |

## Appendix B — What I could NOT verify

1. **Anything at runtime in FA itself.** Every DB measurement was raw `mariadb`
   client. No masked view was exercised through `db_query()`, through FA, or
   through a page render. Whether FA's `db_query()` path handles a `FROM
   <view>` correctly is inferred from the adapter and from MariaDB, not observed.
2. **Whether `CONNECTION_ID()` context rows behave correctly under connection
   churn**, proxying, or a connection pool. FA currently opens a fresh
   non-persistent connection per request **[V]**, which is favourable, but the
   MariaDB container sits behind port 3307 and I did not test behaviour under
   `max_connections` pressure or connection recycling.
3. **`CREATE OR REPLACE VIEW` removing a column** (as opposed to adding one).
   I verified a column-list *change* is accepted; I did not test shrinking it.
4. **Any performance number.** §3.4 reports plan *shape*, not timings, on a
   4-row table. No cost has been measured on FA's real tables or its real report
   queries.
5. **Column drop on a base table when a view references it.** The mirror image of
   finding 11 and untested; MariaDB may block the `ALTER` or silently invalidate
   the view.
6. **Multi-company behaviour beyond the code path.** §3.3's per-company rewrite
   is derived from reading `db_import` and from the single-line substitution; I
   did **not** install a module for company 2 and observe the resulting view set.
7. **Whether anything else in the stack is an active consumer of
   `ksf-common-db`'s `QueryBuilder`.** I re-confirmed
   `ksf_FA_ProjectManagement` is the only one, by the same directory scan the
   prior doc used. A module vendoring the package under a different namespace
   would not be found by that method.
8. **RBAC's record-level capability.** The three deleted repository/provisioner
   classes are gone; whether they are being restored on another branch was not
   checked, and no live record-level data source was confirmed to exist.
9. **Per-row / per-record masking** was not exercised at all. Every "dynamic"
   result above is per-*connection*, not per-record.
---

## Appendix C — BABOK requirement set for the row axis (2026-10-14)

This document is the **column axis**. The **row axis** — ownership, group membership,
and the SQL predicate that enforces them — is specified separately as a BABOK
requirement set, written after this document, so that the two axes stay traceable to
each other rather than merely adjacent.

### C.1 The requirement files

| ID | File | Covers |
|---|---|---|
| **BR-ACL-001** | [`Requirements/BR-ACL-001-record-ownership-and-access-control.md`](./Requirements/BR-ACL-001-record-ownership-and-access-control.md) | Why there are two axes; the UNIX Owner/Group/Many-groups/Other model; groups orthogonal to the org chart; scope exclusion of FA core (R9) |
| **FR-ACL-001-01** | [`Requirements/FR-ACL-001-01-ownership-schema.md`](./Requirements/FR-ACL-001-01-ownership-schema.md) | The tables: `0_rbac_record_owner`, `0_rbac_record_group`, `0_rbac_group_policy`, `0_rbac_record_exception`. Indexes, keys, uniqueness strategy, and the disposition of `0_rbac_record_access` |
| **FR-ACL-001-02** | [`Requirements/FR-ACL-001-02-row-acl-predicate.md`](./Requirements/FR-ACL-001-02-row-acl-predicate.md) | The SQL the builder emits (`EXISTS` recommended; `INNER JOIN` and `IN`-list rejected, with reasons); the one-data-query-per-request argument; the per-request policy cache |
| **FR-ACL-001-03** | [`Requirements/FR-ACL-001-03-two-stage-enforcement-migration.md`](./Requirements/FR-ACL-001-03-two-stage-enforcement-migration.md) | Stage 1 tripwire vs Stage 2 enforcement; the `sed` transform and why the class name is fully qualified; module-by-module migration order |
| **FR-ACL-001-04** | [`Requirements/FR-ACL-001-04-column-axis-views.md`](./Requirements/FR-ACL-001-04-column-axis-views.md) | **This document, as requirements.** The three installer/MariaDB constraints, re-derived from `maintenance_db.inc`, and the naming rule that satisfies them |
| — | [`Requirements/OPEN-QUESTIONS.md`](./Requirements/OPEN-QUESTIONS.md) | Q1–Q13, ranked by blast radius. Row-axis questions; §7 above remains the column-axis set |

### C.1b The second requirement set — the event/lifecycle layer (2026-10-14)

C.1 above specifies the row axis as a **static** model: a record has an owner and a set
of groups, and the builder filters on them. That model has no answer to *"the ownership
just changed"* — ownership moves when an account manager leaves, when a user is removed
from a team, when a table is first brought under ACL, or when a write rolls back
half-way. The set below specifies the **transitions**, and is what composes with this
document's column mask.

| ID | File | Covers |
|---|---|---|
| **BR-ACL-010** | [`Requirements/BR-ACL-010-event-driven-ownership.md`](./Requirements/BR-ACL-010-event-driven-ownership.md) | Why a static model is insufficient; modules never write ACL SQL (R1); the three unowned causes (R7); **the action axis is an application-boundary check, not a SQL predicate (R8)**. Also records **two corrections to the premises it was drafted from** (§3) |
| **FR-ACL-010-01** | [`Requirements/FR-ACL-010-01-per-module-acl-toggle.md`](./Requirements/FR-ACL-010-01-per-module-acl-toggle.md) | The per-module toggle; `SELECT *` rejection (ties to §2.2 above); why the builder must be **extended** to carry the declared table rather than decorated |
| **FR-ACL-010-02** | [`Requirements/FR-ACL-010-02-row-and-column-predicates.md`](./Requirements/FR-ACL-010-02-row-and-column-predicates.md) | Row predicate and column mask in **one statement**; why the owner axis is a `LEFT JOIN` but the group/other axes are `OR EXISTS` (fan-out); **§4 records R8 as an explicit non-requirement** with the failed encodings tabulated |
| **FR-ACL-010-03** | [`Requirements/FR-ACL-010-03-lifecycle-events.md`](./Requirements/FR-ACL-010-03-lifecycle-events.md) | The three events; post-commit ordering; the `AGENTS_ARCH.md` §10.1 mechanism and its `exit` trap |
| **FR-ACL-010-04** | [`Requirements/FR-ACL-010-04-ownership-transitions-and-provenance.md`](./Requirements/FR-ACL-010-04-ownership-transitions-and-provenance.md) | Transitions as registered responders (`null` = not my concern); the three agreed registrations; **why provenance is load-bearing**, not bookkeeping |
| **FR-ACL-010-05** | [`Requirements/FR-ACL-010-05-orphaned-records.md`](./Requirements/FR-ACL-010-05-orphaned-records.md) | The admin-visible orphaned bucket; the sweeper; why cause (a) must **not** be handled by the sweeper |
| **BR-CAL-010** | [`Requirements/BR-CAL-010-capability-contract.md`](./Requirements/BR-CAL-010-capability-contract.md) | The Calendar capability contract. **Establishes that the contract largely already exists** (`calendar_entry_create` / `calendar_entries_query` in `hooks.php`) and records the four real gaps |
| **FR-CAL-010-001** | [`Requirements/FR-CAL-010-001-task-creation-and-event-listing.md`](./Requirements/FR-CAL-010-001-task-creation-and-event-listing.md) | Creation and listing as they exist today; the silent month default; the render-DTO problem |
| — | [`Requirements/OPEN-QUESTIONS.md`](./Requirements/OPEN-QUESTIONS.md) §Open questions — ACL-010 | `Q-ACL-010-1…9` and `Q-CAL-010-1…5`, appended to the Q1–Q13 list above |

**Two facts a reader of C.1 alone would not have:**

1. **The tables do not exist.** `0_rbac_record_owner`, `0_rbac_record_group` and
   `0_rbac_group_policy` are *proposed* by FR-ACL-001-01. No `.php` or `.sql` in either
   `ksf_FA_RBAC/` tree references them. Both requirement sets are blocked on FR-ACL-001-01
   landing first (**Q-ACL-010-9**).
2. **The row predicate in FR-ACL-010-02 deliberately differs from FR-ACL-001-02 §3.2.**
   It uses a `LEFT JOIN` for the owner axis rather than a third `EXISTS`, so that
   *unowned* records survive into the result set. An inner join makes "no ownership"
   indistinguishable from "not permitted" — the failure BR-ACL-010 R6 forbids. This is a
   refinement, not a reversal: the `UNIQUE (module, record_type, record_id)` on
   `0_rbac_record_owner` bounds the join to at most one row, so it cannot fan out.

### C.2 Where the two axes meet

| Concept | Column axis (this doc) | Row axis (requirement set) | Meeting point |
|---|---|---|---|
| Enforcement point | `QueryBuilder::toSql()` (A) and MariaDB (B) | `QueryBuilder` emits the predicate | Both need the builder to **declare its table**. `QueryBuilder::from()` stores an opaque string at `:83` with no getter, so **neither axis is achievable today**. |
| `SELECT *` | A rejects it; B cannot see it (§1.4) | The ACL predicate must be appended to *some* statement — a `SELECT *` from an ACL-managed table is still an unfiltered column read | One rejection rule, in Phase 2 (`ACL_Two_Approaches.md` §5.2), serving both axes |
| Write path | **Views are read-only by construction** (§3.6) — 1471/1348 | Row predicate has no `INSERT` counterpart (FR-ACL-001-02 §6) | Both point at the **base table** for writes. One rule: *reads may use views; writes never do* |
| Unanswerable oracles | `ORDER BY`/`AVG`/`COUNT` on a masked view (§1.3) | none — the predicate is set-based and does not leak a count | §1.3's residual list is **column-axis only** |
| Policy storage | `0_rbac_column_policies` (proposed; OD-3 open) | `0_rbac_group_policy` (FR-ACL-001-01 §3.4) | **OD-3 decides whether these are one table or two.** If they are two, the hierarchy in §4 has two sources of truth and collapses. **Unresolved.** |
| Adoption | 1 module (`ksf_FA_ProjectManagement`, §5.1) | Same module is the Stage 2 hard prerequisite | **One prerequisite, two axes.** Nothing in the row axis is testable before that module is clean |

### C.3 Corrections to two standing premises

Recorded here because this document is the one both corrections were measured against,
and a reader who arrives at §3.3 or §5.1 first should not carry them forward.

| # | Standing premise | Reality | Verified by |
|---|---|---|---|
| 1 | `0_rbac_record_access.record_lookup` is **UNIQUE** on `(module, record_type, record_id, inactive)`; the unique index permits one ACL row per record and blocks multi-group membership, and "must be dropped" first. | **There is no unique constraint.** `SHOW INDEX` returns `Non_unique = 1` on every `record_lookup` row; `SHOW CREATE TABLE` emits a plain `KEY`; `sql/install.sql:80` says `KEY`, not `UNIQUE KEY`. Multiple groups per record are **already** expressible. The actual blockers are different: no uniqueness at all, no `user_id` column (ownership unexpressible), and `team_id NOT NULL` (no membership unrepresentable). | BR-ACL-001 §3.1, FR-ACL-001-01 §2 and §4.1 |
| 2 | 2,860 `db_query(` call sites across 304 files in our modules. | **Not reproducible.** 1,510 sites / 299 files (dev trees, vendor excluded); 1,542 / 305 (deployed `fa_modules`); 2,637 / 604 including `vendor/`. **FA core's 870 is confirmed exactly** and its exclusion (R9) is unaffected. | FR-ACL-001-03 §2.5 |

### C.4 What this document's verification still stands on

Everything in Appendix A was re-read or re-measured for the requirement set on
2026-10-14 and is unchanged. In particular: finding **15** (the `db_import` allow-list
silently discards `DROP VIEW`/`ALTER VIEW`; only `CREATE*` runs) and finding **14** (the
`0_` → `TB_PREF` substitution is whole-line and unconditional) were re-derived directly
from `maintenance_db.inc:274-286` and `:336-337`, and FR-ACL-001-04 §§3–4 rest on those
line numbers rather than on Appendix A's summary.

**One item is added** and is new since Appendix A: `db_export()` (`maintenance_db.inc:546-758`)
enumerates objects via `show table status` filtered only by prefix (`:607`, `:611-613`),
which in MariaDB **includes views**. A backup may therefore emit view DDL as a bare
`CREATE … VIEW` preceded by a `DROP TABLE IF EXISTS` that **does** run. That would drop
every masking view and recreate it in a form `db_import` was not designed to accept.
**Not tested** — see FR-ACL-001-04 §3.4 and **Q13**. It is the only path identified that
could silently remove the column-axis control, and it should be exercised on UAT before
any masking view is deployed.
