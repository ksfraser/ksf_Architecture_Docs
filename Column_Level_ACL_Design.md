# Column-Level Access Control — Design & Assessment

**Date:** 2026-10-13
**Status:** Design proposal — no production code written
**Scope:** `ksfraser/ksf-common-db` (`~/Documents/ksf_common_db`) query builder +
data dictionary, integrating with the existing `ksf_FA_RBAC` module
(`~/Documents/ksf_Infrastructure/fa_modules/ksf_FA_RBAC`).
**Research basis:** source read 2026-10-13 at the paths above, plus an executable
scratch proof-of-concept (`/tmp/opencode/column_acl_poc.php`, outside the repo)
driving the **real** `QueryBuilder` + `PdoDbAdapter` against in-memory SQLite.

Standing decisions applied: `ksf_Architecture_Docs/README.md` §1–6 (no duplicate
core tables; no cross-module table access — ask by hook; responders return DTOs,
consumers render; contracts are consumer-owned) and `AGENTS.md`
(`ksf_common_db` must stay transport-agnostic and must not depend on the FA
module layer; FA runtime must use native `db_*`).

---

## 1. Current capability of QueryBuilder / TableDefinition

### 1.1 What `QueryBuilder` actually is

`src/Query/QueryBuilder.php` is a **string concatenator**, not an AST. Its entire
state is four arrays of raw SQL fragments plus two integers:

| State | Line | Type |
|---|---|---|
| `$select` | `src/Query/QueryBuilder.php:26` | `array<int,string>`, **defaults to `['*']`** |
| `$from` | `:29` | `string` (nullable, opaque — just a table name) |
| `$where` | `:32` | `array<int,string>` |
| `$joins` | `:35` | `array<int,string>` |
| `$groupBy` | `:38` | `array<int,string>` |
| `$having` | `:41` | `array<int,string>` |
| `$orderBy` | `:44` | `array<int,string>` |
| `$limit` / `$offset` | `:47` / `:50` | `int\|null` |
| `$params` | `:53` | `array<string,mixed>` |

Rendering is a single `implode()` chain in `toSql()` (`src/Query/QueryBuilder.php:174-207`).

### 1.2 The extension surface: what exists and what does not

**Verified absent** (`grep -rn 'TableDefinition\|Hook\|Visitor\|Policy\|policy\|sensitiv' src/Query/`
returns no matches; `grep -rni 'acl\|security\|permission\|rbac' src/` across the
whole package returns no matches):

- **No select-list concept.** `select()` (`src/Query/QueryBuilder.php:59-64`) does
  `is_array($columns) ? $columns : [$columns]` — it stores whatever strings it is
  given, and `addSelect()` (`:72-77`) appends a raw string. Nothing distinguishes
  `salary` from `SUM(salary)` from `salary AS hidden`.
- **No column introspection at all.** There is **no public getter** for the
  selected columns or for the FROM table. `$select` and `$from` are private with
  no reader. Any policy pass has to be given a new accessor, or the rendering has
  to be refactored.
- **No hook, visitor, or listener point.** No interface is consulted at any point
  in `select()`/`where()`/`toSql()`.
- **No link to `TableDefinition`.** `from(string $table)` (`:83-88`) stores a
  `string`. `TableDefinition` is never consulted by the builder, so `SELECT *`
  **cannot be expanded** by the builder today — it has no schema.
- **No validation of any clause.** `where()` (`:98-104`), `join()` (`:112-117`),
  `groupBy()` (`:123-128`), `having()` (`:137-143`), `orderBy()` (`:149-155`) all
  accept opaque strings that reach `toSql()` verbatim.
- **No `fetchScalar()` convenience**, although `DbConnectionInterface` has one
  (`src/Contract/DbConnectionInterface.php:56`). The PoC hit this: an
  aggregate query has to be run as
  `$db->fetchScalar($qb->toSql(), $qb->getParams())`.

### 1.3 What `TableDefinition` offers

`src/Dictionary/TableDefinition.php` is the only place that knows a table's shape:

- `column()` (`:64-75`) stores exactly `name, type, null, auto_increment, default`
  (`:66-72`). **There is no sensitivity/classification field.**
- `columns()` `:101-104`, `hasColumn()` `:112-115`,
  `writableColumns()` `:122-131` (excludes auto-increment only, `:128`).
- `columnDef()` `:139-148` is **`private`** — an external policy cannot read a
  column's type or nullability without a new public accessor.
- `insertSql()` `:215-223` / `updateSql()` `:231-245` / `deleteSql()` `:252-255`
  are entirely ACL-unaware; `updateSql()` writes every writable column unless the
  caller filters.

### 1.4 Verdict on Q1

**Yes it can be done in the query builder, but only after a structural change to
both classes.** There is no existing hook to hang on. The minimum additive change
set is in §4.4.

---

## 2. Push-down vs post-fetch, and the inference-leakage problem

### 2.1 The two candidates

**Push-down** rewrites the SQL so the hidden column never leaves the database:
`NULL AS salary` (constant redaction) or `CASE WHEN <predicate> THEN salary END`
(per-row conditional redaction).

**Post-fetch** issues the real query and blanks the column in PHP.

### 2.2 Two facts that reframe the choice

**(a) `CASE WHEN <policy> THEN col END` is not a redaction mechanism when the
policy is constant.** PoC §B:

```
SELECT id, name, CASE WHEN 1=1 THEN salary END AS salary FROM emp
→ ann 100000 / bob 70000 / cam 90000
```

The expression is arithmetically identical to `col`. `CASE WHEN` earns its keep
only for **per-row** predicates (`CASE WHEN <row-level ACL> THEN col END`), which
is what makes it composable with record-level ACL — that is the SuiteCRM shape
(`ACLFields` + per-record projection). For a caller-level "you may never read
this column" policy, `NULL AS col` is the only honest push-down form.

**(b) Push-down protects exactly one channel: the projection.** Every other
channel (predicate, ordering, grouping, aggregation, join) reads the *real*
column regardless of what the SELECT list says. Post-fetch protects the same
single channel and does it *worse*, because the raw values have already crossed
the process boundary (PoC §G: `SELECT *` ran; only the PHP array was blanked — any
debug/logging/error path downstream sees the real salary).

So push-down is **strictly stronger** than post-fetch for the same work: same one
channel protected, but the plaintext never exists in PHP. The real question is
therefore not "push-down or post-fetch" but **"how do we close the other five
channels?"**

### 2.3 The inference-leakage matrix

Every row below was executed against the real `QueryBuilder` (PoC
`/tmp/opencode/column_acl_poc.php`). Table `emp(id, name, salary)`;
`salary` is the hidden column.

| # | Channel | Example SQL emitted by the builder | Leaks? | PoC evidence | Required treatment |
|---|---|---|---|---|---|
| 1 | **Projection** | `SELECT id, name, NULL AS salary` | **No** | §A → all `salary` = NULL | push-down, always |
| 2 | Projection via `CASE` (constant policy) | `CASE WHEN 1=1 THEN salary END` | **Yes, fully** | §B → 100000/70000/90000 | never emit; `CASE` only for per-row predicates |
| 3 | **`WHERE` predicate** | `... WHERE salary >= :g` | **Yes — exact value recovery** | §C: `>=100000`→1 row, `>=70001`→2 rows; bisection recovers the value in ~⌈log₂(range)⌉ queries | **reject the query** |
| 4 | **`ORDER BY`** | `... NULL AS salary ... ORDER BY salary ASC` | **Yes — total ordering** | §D → row order `ann,bob,cam` = true salary order | **reject** (or order by an explicit permitted surrogate) |
| 5 | **`GROUP BY`** | `GROUP BY salary` | **Yes — the group key *is* the value** | §E → 3 groups keyed `[70000,90000,100000]` | **reject** |
| 6 | **`DISTINCT` / `SELECT DISTINCT col`** | `SELECT DISTINCT salary` | **Yes — enumerates the column** | identical to §E | **reject** |
| 7 | **`COUNT(col)`** | `SELECT COUNT(salary)` | **Yes — null-count oracle** (`COUNT(col) − COUNT(*)` = #NULLs) | §E → `COUNT(*)=3 COUNT(salary)=3` | **reject `COUNT(col)`; allow `COUNT(*)`** |
| 8 | `COUNT(*)` | `SELECT COUNT(*)` | **No** (row cardinality, not column data) | §E → 3 | **allow** |
| 9 | **`MIN`/`MAX`/`SUM`/`AVG`** | `SELECT AVG(salary)` | **Yes — exact statistics** | §E → `AVG=86666.67`, `MAX=100000` | **reject** |
| 10 | **`HAVING`** | `HAVING AVG(salary) > 0` | **Yes — predicate oracle**, same as #3 | §F → clean projection, leak survives | **reject** |
| 11 | **Window functions / subqueries** | `ROW_NUMBER() OVER (ORDER BY salary)`, `WHERE id IN (SELECT … WHERE salary…)` | **Yes** | not executed (SQLite/MySQL-version dependent) — **asserted from semantics, not measured** | **reject** (regex/lexer gap — see risk R1) |
| 12 | **JOIN onto a mirroring column** | `JOIN pay ON pay.emp_id=e.id` selecting `pay.gross` | **Yes — value never named** | §F: `pay.gross` held the identical salary; the `emp.salary` reference can be removed entirely and the leak persists | **cannot be closed by a single-table policy**; see §2.5 |

### 2.4 The `ORDER BY` question, answered

**Reject (throw).** The three candidate behaviours:

| Behaviour | Argument for | Argument against |
|---|---|---|
| **Throw** (recommended) | Fails loudly; a leak is a test-detectable failure; the caller cannot silently receive a *wrong* answer; matches "fail closed" for an ACL | Breaks legitimate UX: "sort by salary" on a list where salary is masked |
| Silently neutralise (e.g. drop the term) | Never breaks a page | Caller gets an **unsorted** result and no signal; makes the leak invisible in tests; the caller cannot tell a policy denial from a bug |
| Allow | Maximum compatibility | Confirmed full ordering leak (§D) plus, with `LIMIT`/paging, a total ranking oracle |

**Recommendation:** throw by default, and provide an explicit, opt-in
`orderBySurrogate($hiddenColumn, $permittedColumn)` so the "sort by a masked
column" case has a supported, auditable answer. Whether a surrogate column is
acceptable as a proxy is a **business** decision (does sorting by
`discount_pct` leak `net_price`?) — see §7 Q2.

### 2.5 The one thing push-down cannot close

Rows #3–#11 are all closable by inspecting the query being built. **Row #12 is
not**: a join can surface the hidden value through a *different* table's column,
with no reference to the protected table's column anywhere in the statement. In
the PoC the leak survived with a completely clean `emp.salary` reference.

Closing it requires the join target to carry its own policy (each table in the
statement must resolve its own visible set) plus a rule that a join predicate may
not be *derived from* a hidden column on either side. This is a genuine residual
risk and is called out in §6, not solved.

---

## 3. Current state of the RBAC side (verified, not assumed)

The brief asked me to verify what RBAC does today rather than assume it is inert.

### 3.1 Namespace — the inconsistency is real, but not the one described

`composer.json` declares PSR-4 `"Ksfraser\\FrontAccounting\\Rbac\\": "src/Ksfraser/FrontAccounting/Rbac/"`
and all 13 source files declare `namespace Ksfraser\FrontAccounting\Rbac\…`
(e.g. `src/Ksfraser/FrontAccounting/Rbac/RbacService.php:4`). The disk path and
the namespace **match exactly**, so autoloading is correct and there is no bug
inside the module.

The real problem is **cross-repo divergence**:

| Consumer | Root namespace segment |
|---|---|
| `ksf_common_db` (`composer.json`) | `ksfraser\CommonDb\` (lowercase) |
| `ksf_db_security` (`composer.json:12`) | `ksfraser\DbSecurity\` (lowercase) |
| `ksf_FA_RBAC` (`composer.json`) | `Ksfraser\FrontAccounting\Rbac\` (**capital K**) |
| Master convention (`AGENTS.md`, Naming Conventions) | `ksfraser\FrontAccounting\<ModuleName>\` (lowercase) |

PHP treats `Ksfraser\…\X` and `ksfraser\…\X` as **different class names**. A
column-ACL contract type-hinted across this boundary will fail to match if the
implementer and the consumer disagree on the capitalisation. Must be decided
before the contract exists (§7 Q5).

### 3.2 The module is NOT a no-op — but its record-level layer is dead

`AGENTS.md` describes `ksf_FA_Common` as gutted to a no-op; that claim is about
**ksf_FA_Common, not RBAC**. What RBAC actually does today:

- **Works, role-level, no DB required.** `RbacService::authorize()`
  (`RbacService.php:203-225`) polls registered voters; `CustomerVoter::doVote()`
  (`CustomerVoter.php:13-39`) inspects **only** `$roles` — no team lookup, no
  record lookup, no query.
- **Actively filters lists.** `hooks.php` `filterRecordList()` appends
  `AND 1=0` (deny-all) or a salesman `EXISTS` sub-query to a raw SQL string.
- **Dead, team/record-level.** `git status` in the deployed module shows
  **uncommitted deletions** of `Repository/FaRecordAccessRepository.php` (247
  lines), `Repository/FaTeamRepository.php` (257),
  `Provisioner/UserProvisioner.php` (169) and their three test files, plus a
  modified `hooks.php` (+152/−…). `hooks.php` still references
  `UserProvisioner`; the `file_exists()` guard causes `provisionCurrentUser()` to
  return early. **No users are provisioned → no teams exist → no rows can ever be
  written to `0_rbac_record_access` → no record-level grant can ever be
  evaluated.**
- `composer.json` on disk carries an **uncommitted** dependency swap
  (`zendframework/zend-permissions-rbac` → `laminas/laminas-permissions-rbac`) and
  declares `"php": ">=7.4"` while the cross-module floor is **7.3**
  (`ksf_common_db` lowered its own floor to `>=7.3` in commit `1486557` for
  exactly this class of problem).

**Consequence for this design: there is no live record-level data source to hang
column policy on.** Phase 0 (§5) is not optional.

### 3.3 The `projection` column is declared but never implemented

`sql/install.sql:67` defines
`` `projection` VARCHAR(32) NOT NULL DEFAULT 'public' `` on `0_rbac_record_access`.
Grepping the whole module for `projection` yields exactly **one** hit —
`hooks.php:294`, `'projection_ranking' => true`, a capability flag in
`_getAdvertisedValues()`. **No PHP reads or writes the column.** It is a
32-character *name* (SuiteCRM-style projection label), not a column mask.

`RBAC_V2_DESIGN.md:17` lists "Field-level security via encrypted columns" as a
feature. That is the encryption route, not the ACL route, and it is unimplemented.

### 3.4 Prior art that must not be duplicated: `ksfraser/ksf-db-security`

`~/Documents/ksf_db_security` (4 files, **no tests, no git repo, no consumer** —
not in any `composer.json` I checked) already attempts this problem:

| Class | What it does | Why it does not solve this |
|---|---|---|
| `Column/ColumnPermissions.php` | role → column list; `generateViews()` `:97-112` emits one `CREATE OR REPLACE VIEW` per role | role-keyed only (no user/team/projection dimension); policy is code, not data |
| `MySql/ViewManager.php` | creates those views; `grantToUser()` `:102-107` issues `GRANT SELECT ON view TO 'user'` | **Broken for FA.** Both FA pods connect as a single MySQL account `ksf_user` (per `AGENTS.md`), so MySQL grants cannot vary per FA user. View-per-role cannot work without per-user DB accounts. |
| `Dao/VirtualView.php` | post-fetch/PHP enforcement | **Contains a live leak:** `findById()` `:150-159` checks `hasColumn('id')` then runs `SELECT *` (`:156`) and returns the whole row. Also builds SQL by hand instead of using `QueryBuilder` — i.e. exactly the "third parallel DB abstraction" `AGENTS.md` forbids. `count()` `:229-234` reads `$row['COUNT(*)']`, a key FA's `db_fetch_assoc` does not reliably produce. |
| `Encrypted/EncryptedFields.php` | transparent at-rest encryption in a satellite `{prefix}{table}_ed` table | different concern (confidentiality at rest, not read authorisation); reuses the same `$key` for AES and HMAC (`:217`, `:225`) with no key separation |

Recommendation: **retire the view/DAO half, keep the encryption idea separate.**
Decide explicitly (§7 Q4).

---

## 4. Recommended design

### 4.1 The contract (lives in `ksf-common-db`, not in RBAC)

Following standing decision #3 (consumer owns the contract), the interface is
consumed by `QueryBuilder`, so it is defined in the package the builder lives in:

```php
namespace ksfraser\CommonDb\Security;

/**
 * Decides which columns of $table the current caller may read.
 *
 * FR-CLAC-001: the query builder MUST obtain its visible column set from a
 * ColumnPolicyInterface and MUST NOT contain hard-coded column knowledge.
 */
interface ColumnPolicyInterface
{
    /**
     * Columns of $table visible in $context.
     *
     * @return string[] ['*'] = unrestricted; [] = nothing visible (deny all)
     */
    public function visibleColumns(string $table, array $context = []): array;

    /** Single-column fast path; default impl may delegate to visibleColumns(). */
    public function canReadColumn(string $table, string $column, array $context = []): bool;
}
```

Companions, all in `ksfraser\CommonDb\Security`:

| Class | Purpose |
|---|---|
| `NullColumnPolicy` | returns `['*']`. **The backward-compatibility guarantee.** |
| `CachingColumnPolicy` | decorator; per-request memo keyed `company\|userId\|table` |
| `RedactedRow` / `ColumnRedactor` | post-fetch **assertion** layer (§4.5) |
| `ColumnAccessException` | thrown on hidden-column clause references |

`ksf-common-db` must never `require` RBAC. The arrow is one-way already: RBAC's
`composer.json` requires `ksfraser/ksf-common-db: ^1.0`.

### 4.2 Where the policy lives, and who supplies it

- **Contract + null object + cache:** `ksf_common_db` (`ksfraser\CommonDb\Security`).
- **Implementation:** `ksf_FA_RBAC` provides
  `Ksfraser\FrontAccounting\Rbac\Security\RbacColumnPolicy implements
  ksfraser\CommonDb\Security\ColumnPolicyInterface`.
- **Wiring:** performed by the **consumer** (the DAO / DAO base class) via
  explicit injection — `$qb->withColumnPolicy($policy)`. FA has no DI container
  for modules, so either a small consumer-owned service locator or the existing
  `ksf_FA_Common` `ComposerDependencies` bootstrap works. FA's
  `hook_invoke_first('column_policy', …)` is acceptable as **discovery** (resolve
  the object once per request) but must **not** be called per query.

### 4.3 Caching

The policy result depends on `(company, user, roles/teams, table)` and is stable
for the lifetime of a request. Without a cache every query built pays for a
lookup; with one, a page issuing 40 queries over 6 tables pays 6 lookups.

| Layer | Owner | Notes |
|---|---|---|
| **Request-scoped memo** | `CachingColumnPolicy` (in-package) | key `company\|userId\|table`; the cache **records the `userId` it was built for** and throws/refuses on mismatch rather than serving another user's policy |
| **Invalidation** | `$_SESSION` owner | `clear()` on login, logout, role/team change, and on any `0_rbac_*` write in the same request |
| **Storage** | new `0_rbac_column_policies` table | `(module, table_name, subject_kind[role\|team], subject_id, column_name)`; changes written to the existing `0_rbac_audit_log` (`sql/install.sql:88-105`) |

**Do not reuse `0_rbac_record_access.projection`** — it is per-record, `VARCHAR(32)`,
holds a *name* not a mask, and is never read today (§3.3).

### 4.4 Exact proposed additions to the query builder

All **additive**; no existing signature changes.

**`src/Query/QueryBuilder.php`**

1. **Introspection accessors** (required — nothing is readable today):
   `selectColumns(): array` (`:26`), `fromTable(): ?string` (`:29`),
   `whereClauses()/groupBy()/having()/orderBy(): array`.
2. **Policy collaborator**, null-object default:
   `withColumnPolicy(ColumnPolicyInterface $p): self` + `private $policy = null`.
   When null, `toSql()` output is **byte-identical to today**.
3. **Dictionary attachment** so `*` can be expanded:
   `fromDefinition(TableDefinition $d, string $alias = ''): self`, which sets
   `$from` *and* retains the definition for column resolution. Without a
   definition, `*` under an active policy must **throw** — expanding `*` is
   impossible without schema.
4. **Render split:** extract `protected function renderSelect(array $cols): string`
   from `toSql()` `:176`, and give the policy pass a single place to act.
5. **Typed clause API** (the important one for security):
   `whereColumn($col, $op, $value, array $params = [])`,
   `orderByColumn($col, $dir = 'ASC')`, `groupByColumn($col)`,
   `havingColumn($col, $op, $value)`. These record the referenced column
   *structurally*, so no parsing is needed.
6. **Fail-closed raw path:** raw `where()/join()/groupBy()/having()/orderBy()`
   strings still work, but **when a policy is active** they are scanned for
   column identifiers; an unparseable or unreviewable clause **throws**
   `ColumnAccessException`. (See risk R1 — this is the design's weakest point.)
7. **`fetchScalar()`** convenience mirroring `DbConnectionInterface:56`, for parity.
8. **`TableDefinition` needs a public `columnDef()`** — it is `private`
   (`src/Dictionary/TableDefinition.php:139`) — plus an optional
   `sensitivity(string $column, string $class)` annotation, and ACL-aware
   `writableColumns()` (`:122-131`) for the write path later.

**Adapter note (verified):** `FaDbAdapter::prefixTables()` only rewrites tokens
after `FROM|JOIN|INTO|UPDATE|TABLE` (`FaDbAdapter.php:56`), so push-down
expressions are safe from table prefixing. But `bindParams()` resolves named
placeholders with `str_replace(':' . $name, …)` (`FaDbAdapter.php:98`), so any
ACL-generated fragment must not contain `:` followed by a bound-parameter name.
`NULL` and `CASE WHEN` are safe.

### 4.5 Where post-fetch still earns its place

Not as the control, but as a **defence-in-depth assertion**: after `fetch()`,
verify that no column outside the policy's visible set is present with a non-NULL
value, and log/throw on violation. It catches queries that bypassed the builder
and it catches projection bugs in the builder itself. It is cheap (one `isset`
loop) because the push-down already produced NULLs.

---

## 5. Phased plan

| Phase | Deliverable | Exit criteria | Risk |
|---|---|---|---|
| **0. Stabilise RBAC** (blocking) | Finish or formally abandon the uncommitted deletion of `Repository/*` + `Provisioner/*`; decide the `php>=7.4` vs 7.3 floor; commit the laminas swap | Working tree clean; `git status` empty; module tests pass | Schedule. Nothing in Phases 2+ has a data source until this lands. |
| **1. Builder introspection** (no security behaviour) | Accessors + `fromDefinition()` + typed clause API + `fetchScalar()` | All 3 existing `QueryBuilderTest` cases still pass unchanged; `toSql()` byte-identical; ship as **v1.1.0** | Low. Purely additive. |
| **2. Policy contract + projection push-down** (opt-in) | `ColumnPolicyInterface`, `NullColumnPolicy`, `CachingColumnPolicy`, `renderSelect` push-down, hidden-column clause rejection | New tests: push-down blanks; hidden-column `WHERE`/`ORDER BY`/`GROUP BY`/`HAVING`/`COUNT(col)` **throw**; no-policy ⇒ SQL identical to today. Ship **v1.2.0**. | Medium (R1, R2). |
| **3. RBAC implementation** | `RbacColumnPolicy` + `0_rbac_column_policies` + migration + admin UI | Policies honoured end-to-end on the Integration pod | Medium |
| **4. Assertions + audit** | Post-fetch assertion layer; inference regression suite; audit rows for denials | Regression suite fails if a leak vector is reintroduced | Low |
| **5. (separate)** | Retire or re-align `ksfraser/ksf-db-security` | View/DAO half deleted; `VirtualView::findById` leak gone | Low |

**Release note:** Phase 1 and 2 are minor version bumps of a published Packagist
package (`ksfraser/ksf-common-db`, currently `v1.0.1` — the tree is at tag
`v1.0.1`, `APPENDIX.md` still says `v1.0.0`; the doc is stale).

---

## 6. Risks

| ID | Risk | Severity | Mitigation |
|---|---|---|---|
| **R1** | **Clause parsing false negatives.** Raw `where()` strings must be scanned by regex/tokenizer to find hidden-column references. A miss is a **silent leak**, and regex SQL parsing is provably incomplete (comments, `/*! */`, functions, CTEs). | **High** | Typed clause API as the primary path; raw path **fails closed** under an active policy; fuzz/corpus tests; prefer rejecting all raw strings that reference any column of a policy-managed table. |
| **R2** | **Default posture.** `NullColumnPolicy` returning `['*']` keeps existing consumers working (backward compatible) but is **fail-open**. Contrast `ksf_db_security`'s `ColumnPermissions::roleHasColumn()` which returns `false` for an unconfigured role (`:135-137`) = **fail-closed**. | **High** | See §7 Q1 — this is the decision that must be made before Phase 2. |
| **R3** | **Join-based inference** (matrix row #12) cannot be closed by a single-table policy. | High | Record as a **known, accepted residual risk** in Phase 3 docs; each joined table must resolve its own policy; add a rule that join predicates cannot derive from a hidden column. |
| **R4** | `FaDbAdapter::bindParams()` `str_replace(':'.$name)` (`FaDbAdapter.php:98`) can be corrupted by ACL-generated fragments containing `:`. | Medium | Document the constraint; add a guard test. |
| **R5** | **Namespace case split** (`Ksfraser\` vs `ksfraser\`) breaks the new cross-module type-hint. | Medium | Normalise before Phase 3 (§7 Q5). |
| **R6** | RBAC's working tree is mid-refactor and broken (§3.2) → Phase 3 blocked. | Medium | Phase 0. |
| **R7** | Push-down rewrites break **index-only covering plans** on large reports; `NULL AS col` is not sargable. | Low–Medium | Measure on the real report queries before enabling broadly; allow an opt-out per query. |
| **R8** | Policy lookup cost per table per request if the cache is not threaded correctly. | Low | `CachingColumnPolicy` is in-package and non-optional in the wiring. |
| **R9** | MySQL-view approach (prior art) cannot work in FA's single-`ksf_user` model (§3.4) — a future contributor may re-attempt it. | Low | Document the `ksf_user` finding in `ksf_db_security`'s own docs. |
| **R10** | `ext-pdo: *` in `ksf_common_db/composer.json` forces PDO on FA consumers, contradicting the "FA must never use PDO" rule (the rule is about *runtime transport*, but the packaging is misleading). | Low | Flag to the package owner; consider `suggest` instead of `require`. |

---

## 7. Open questions requiring the user's decision

**Q1 (most important) — Default posture when no policy is registered.**
`NullColumnPolicy` → allow all (backward compatible, **fail-open**) or a
"configured but unknown table" → deny all (fail-closed, but silently breaks every
existing consumer on day one). This single answer determines whether Phase 2 is a
transparent release or a breaking one. *My recommendation: allow-all when **no
policy object is registered at all** (so RBAC-disabled is a true no-op), and
**deny-all for any table the registered policy does not know** — so turning RBAC on
is a deliberate, table-by-table act and forgetting a table fails safe.*

**Q2 — `ORDER BY` on a hidden column.** Throw (recommended), or is there a real
requirement to "sort by salary" on a masked list? If yes, is an approved surrogate
column acceptable, and who certifies that the surrogate is not equivalent?

**Q3 — Granularity.** Is column ACL a **per-request** static mask (role/team →
columns) or **per-record** (SuiteCRM projection semantics, where the same column is
visible for some records and not others)? The DB already has a per-record
`projection` column (`sql/install.sql:67`) but it is unimplemented (§3.3), and
per-record masks cannot be expressed in a static push-down — they need
`CASE WHEN <record predicate> THEN col END`, which is a materially larger design.
*My recommendation: v1 is per-request only; per-record is a separate phase.*

**Q4 — `ksfraser/ksf-db-security`.** Retire it (recommended — untested, no
consumers, single-`ksf_user` breaks it, `VirtualView::findById()` leaks), or is
the MySQL-view approach still wanted for non-FA deployments?

**Q5 — Namespace normalisation.** Renormalise `Ksfraser\FrontAccounting\Rbac\`
→ `ksfraser\FrontAccounting\Rbac\` to match the master convention and the other
two packages, before the new contract is type-hinted across the boundary? (This
is a breaking change for anything already importing those classes.)

**Q6 — Redacted-key shape.** When a column is hidden, should the result row still
carry the key with a NULL value (chosen here; keeps result shape stable for
report/CSV templates) or should the key be **absent** entirely (stronger — reveals
that the column exists at all)? Chosen: key present, value NULL, and record a
"which keys were redacted" side-channel for the audit log, since the keys
themselves are schema information.

**Q7 — Write path.** Column ACL for **reads only** (the requested scope), or also
`INSERT`/`UPDATE`? `TableDefinition::writableColumns()` (`:122-131`) and
`insertSql()`/`updateSql()` (`:215-245`) are currently ACL-unaware, and
`updateSql()` writes every writable column unless the caller filters — which is a
mass-assignment hazard independent of RBAC. *My recommendation: reads now, write
path explicitly deferred and documented as out of scope for v1.2.0.*

---

## Appendix A — Things I could **not** verify

1. **Whether the deployed RBAC working tree is intentionally mid-refactor or
   accidentally broken.** `git status` shows uncommitted deletions of the
   repositories, provisioner and three test files; I did not check other branches
   (`agent/rbac-migration-wip`, `fix/restore-fa-rbac`) or the remote to see
   whether this is work-in-progress or damage.
2. **Whether any consumer actually calls `QueryBuilder`.** `AGENTS.md` lists
   "port other modules' DAOs onto `DbConnectionInterface`" as a *next step*, and
   the only known consumer (RBAC) uses `FaDbAdapter` directly with hand-written
   SQL. So the blast radius of a breaking change to `QueryBuilder` is currently
   **probably zero** — but I did not grep all 150+ modules for
   `use ksfraser\CommonDb\Query\QueryBuilder`.
3. **Whether `ksf_FA_RBAC` is actually loaded on a live pod.** It is
   `'active' => true` in `FA/ksfii_app/installed_extensions.php:104-111` and
   `FA/2.4.3/installed_extensions.php:104-111`, and **absent** from
   `FA/ksf_fa/installed_extensions.php`. I did not query the running containers.
   Per `AGENTS.md`, the global registry on `ksfii_app` may be a stale copy —
   **so its `active => true` is not reliable evidence.**
4. **Matrix row #11** (window functions, subqueries) was reasoned from SQL
   semantics, not executed — SQLite/MySQL version constraints in the PoC.
5. **Whether the 7.3 floor or the 7.4 declaration is correct** for RBAC's
   `composer.json`. `ksf_common_db` lowered its own floor to 7.3 (commit
   `1486557`); RBAC still declares `>=7.4` **uncommitted** while
   `_init/config` says `PHP-Version: 7.3`.
6. **Real report-query performance impact** of push-down rewrites (R7) — not
   benchmarked.