# FR-ACL-001-03 — Two-stage enforcement migration

@BABOK Related: BR-ACL-001, BABOK 5.1 Solution Evaluation, 8.3 Solution Design, 9.3 Requirements Traceability
Status: **Proposed**
Module: cross-module (`ksf_FA_*`), `ksf_common_db`
Date: 2026-10-14

> **Documentation only.** No `sed` was run against any module, no file was modified,
> and no commit was made. Every command below is a **proposal** with a dry-run gate
> stated before it.

---

## 1. The two stages, and the honest description of each

| | **Stage 1 — Tripwire** | **Stage 2 — Enforcement** |
|---|---|---|
| Mechanism | `sed` rewrite of `db_query(` → a fully-qualified static call | Modules move to the query builder, which *declares* the table |
| Blocks undeclared queries? | **No.** Nothing is blocked. | **Yes.** |
| Blocks `SELECT *`? | **No.** It *detects and logs* it. | **Yes.** Rejects outright. |
| Emits the ACL predicate? | **No.** | **Yes.** |
| Row-ACL enforcement? | **No.** | **Yes.** |
| Purpose | One choke point. Query-shape census. Population data for the ACL tables. A regression alarm when Stage 2 lands. | Actual enforcement. |
| Blast radius if wrong | Log noise, or a broken call — **no silent data exposure** | Enforcement is real; a wrong predicate hides data |

> **This must be stated in the code, the commit message, and the module docs.**
> Stage 1 is a **tripwire**, not a control. Any document, dashboard, or status report
> that describes Stage 1 as "ACL enforcement active" is wrong and must be corrected.

Stage 1's value is real but bounded: it produces the **query census** that FR-ACL-001-01
needs (which tables are actually read, from which files, with what predicates), it
gives **one place** to put a future hard failure, and it makes Stage 2's coverage
measurable rather than asserted.

## 2. Stage 1 — the transform

### 2.1 Why the replacement is a **fully-qualified** class name

```bash
# WRONG — requires a `use` statement that sed cannot add.
sed -i 's/\bdb_query(/SRP_DB_Query::db_query(/g'

# RIGHT — self-resolving from the global namespace, in any file, namespaced or not.
sed -i 's/\bdb_query(/\\ksfraser\\FrontAccounting\\Rbac\\Security\\DbQuery::db_query(/g'
```

| Reason | Detail |
|---|---|
| **`sed` cannot add a `use`.** A short name resolves only if a `use …\DbQuery;` already exists in the file. Many `ksf_FA_*` files are in namespaces and many are not; a single `sed` cannot know which, and prepending a `use` would collide with existing ones and would be inserted *after* code in files with a shebang/header. |
| **Namespace-relative resolution differs per file.** In `namespace ksfraser\FrontAccounting\Rbac\Storage;`, the bare name `SRP_DB_Query` resolves to `ksfraser\FrontAccounting\Rbac\Storage\SRP_DB_Query`. In a file with no namespace it resolves to `\SRP_DB_Query`. **One sed, two different classes.** The fully-qualified `\ksfraser\...` name is identical in both. |
| **The leading `\` is load-bearing.** Without it, `Foo::bar()` inside a namespace is *also* resolved against the current namespace first (PHP falls back to the global class only if the namespaced one does not exist), so the failure would be a late "class not found" at an unpredictable call site rather than a deterministic parse error. With `\`, resolution is absolute. |
| **Class names are case-insensitive in PHP**, so an already-capitalised `\KSFRASER\...` also resolves. Cosmetic only. |

### 2.2 The shim

```php
<?php
declare(strict_types=1);

namespace ksfraser\FrontAccounting\Rbac\Security;

/**
 * Stage-1 tripwire. NOT an access-control control.
 *
 * @BABOK Related: FR-ACL-001-03
 * @since 1.0.0
 */
final class DbQuery
{
    /** @return mixed */
    public static function dbQuery($sql, $msg = '', $qarray = false, $deadlock_rerun = false)
    {
        // delegate to FA's native entry point; no interception in v1
        return \db_query($sql, $msg, $qarray, $deadlock_rerun);
    }
}
```

> **Naming.** The brief specifies the rewritten token `SRP_DB_Query::db_query(`. That
> spelling is **not used** — it is neither a valid PSR-4 class name nor legal under the
> module conventions in `AGENTS.md` (`InterfaceNameInterface`, `PascalCase`, PHP 7.3
> floor, `ksfraser\FrontAccounting\<Module>\` namespace). If the exact string
> `SRP_DB_Query` is a hard requirement, say so (**Q10**) — it is one `sed` expression
> and one class name away, but it should be a decision, not a default.
>
> The **sed shape** is what matters and it is unaffected: a fully-qualified, absolute
> name.

### 2.3 What the shim must also do in v1

`db_query()` has **four** parameters (`$sql`, `$msg`, `$qarray`, `$deadlock_rerun` —
`admin/db/maintenance_db.inc:63-65` shows the first three in use). A shim that declares
fewer parameters will fatal on any call site that passes three. It must forward all
four.

### 2.4 Dry-run gates before any file is written

```bash
# 1. Census. No writes.
grep -rIn --include=*.php --include=inc -E '\bdb_query[[:space:]]*\(' . | wc -l
grep -rIl  --include=*.php --include=inc -E '\bdb_query[[:space:]]*\(' . | wc -l

# 2. Dry run: -n prints, writes nothing. Review the printed lines.
grep -rIl --include=*.php --include=inc -E '\bdb_query[[:space:]]*\(' . \
  | xargs -r sed -n 's/\bdb_query[[:space:]]*(/\\ksfraser\\FrontAccounting\\Rbac\\Security\\DbQuery::dbQuery(/gp'

# 3. Check for cases the sed will NOT catch, and handle them by hand.
grep -rIn --include=*.php --include=inc -E 'db_query[[:space:]]*$|["'"'"']db_query[[:space:]]*\(' .
grep -rIn --include=*.php --include=inc -E '\$db_query|->db_query|::db_query' .
```

The third command is the one that catches real residue: a call whose `(` is on the
next line, a *string* containing `db_query(` (which the sed will corrupt), and any
callable reference (`$fn = 'db_query';`) that has nothing to do with SQL.

> **Known sed hazard [A, not tested here]:** the rewrite also hits occurrences of
> `db_query(` inside **string literals and comments** — e.g. a docblock quoting FA's
> call, or an error message. The grep in step 2 is the gate for this. A token-aware
> rewrite (PHP tokenizer, or PCRE-based phpcs ruleset) is the alternative if the string
> hits are more than a handful; **Q11**.

### 2.5 Scope — what the sed runs over

| In scope | Count | Verified |
|---|---|---|
| `ksf_FA_*` module trees, `vendor/` **excluded**, `.php` + `.inc` | **1,510 call sites / 299 files** | **[V]** measured 2026-10-14 |
| Same, across the deployed Integration tree `ksf_Infrastructure/fa_modules` | **1,542 / 305** | **[V]** |
| `ksf_FA_*` **including** `vendor/` | 2,637 / 604 | **[V]** |
| **FA core** `ksf_Infrastructure/FA/2.4.3/` | **870 call sites / 131 files** | **[V]** |
| FA core — **EXCLUDED, permanently** | — | BR-ACL-001 R9 |

> **Correction to the brief.** The brief stated "2,860 `db_query(` call sites across
> 304 files" for our modules. **That figure is not reproducible.** The measurements
> above are the real ones. The **file count is close** (299/305 vs 304) but the **call
> site count is not**: 2,860 appears to include vendored copies. The migration must be
> scoped to the **1,510 / 299** figures; the 2,637 figure would mean rewriting
> `vendor/` and must not be used as a target.
>
> FA core's **870** is confirmed **exactly**. That exclusion is unaffected.

### 2.6 What Stage 1 does *not* do

- It does **not** reject `SELECT *`. It **counts** them.
- It does **not** filter rows. It **counts** which `(module, record_type)` pairs are
  read, which is what populates `0_rbac_group_policy` and drives the FR-ACL-001-01
  table design.
- It does **not** apply to the one other query-builder fork,
  `ksf_payment_destinations/src/QueryBuilder/QueryBuilder.php`, which has its own
  `toFaSql()` and never calls `ksf-common-db`'s `toSql()` **[V —
  `ACL_Two_Approaches.md` §1.2 item 3]**. It is **also** covered by this sed, because
  it emits through `db_query()`; it just gets no ACL predicate until it declares its
  tables.

## 3. Stage 2 — real enforcement

### 3.1 What makes it real

Stage 2 moves a module's reads to a builder that **declares the table**, which is the
precondition for three things Stage 1 cannot do:

1. Emitting the row-ACL `EXISTS` predicate (FR-ACL-001-02 §3.2).
2. Rejecting `SELECT *` — which requires knowing the table's column list, which is
   what `TableDefinition` supplies.
3. Rejecting a clause that references a denied column (e.g. `WHERE salary > :g`),
   which requires knowing the column is sensitive.

Today `from()` stores an opaque string with no getter, so **none** of the three is
possible **[V — `QueryBuilder.php:83`]**. Declaration is not a stylistic preference;
it is the entire mechanism.

### 3.2 The readiness gate — do not skip

`ACL_Two_Approaches.md` §5.1 verified that `ksf_FA_ProjectManagement` (the **only**
current `ksf-common-db` consumer) has **8 `select('*')` sites** and ~40 raw
`where()`/`orderBy()`/`groupBy()` calls, and that
`TaskDependencyRepository.php:75` **already emits malformed SQL** against the shipped
one-argument `join()`.

> **Constraint: Stage 2 enforcement must not be switched on in any pod until the
> target module's call sites are migrated.** Under FA's `E_USER_ERROR` semantics a
> rejected statement is a silent mid-render death, not a catchable exception
> **[V — `ACL_Two_Approaches.md` §5.1]**.

### 3.3 Module migration order

Ordered by **(data sensitivity × blast radius)**, lowest first, so the first pod
enforced proves the mechanism on the least damaging failure.

| # | Module | `db_query(` (no vendor) | Files | Why here |
|---|---|---|---|---|
| — | `ksf_FA_CRM` | **359** | 77 | **First for ACL, despite being the 2nd largest module.** Contacts are the reference implementation for "a record with an owner and many groups", and are the row-axis case the whole design exists for. Small blast radius per call site; high documentation value. |
| — | `ksf_FA_HRM` | **102** | 26 | **Second, and the highest-stakes.** Payroll is the requirement that justifies the project (BR-ACL-001 §1) and is the worst possible place to discover a fail-open. Goes immediately after CRM only because CRM is *smaller*. |
| — | `ksf_FA_ProjectManagement` | 65 | 17 | **Third, and it is a hard prerequisite, not a preference.** It is the only existing `ksf-common-db` consumer and has 8 `select('*')` + the broken `join()` (§3.2). Until it is clean, Stage 2 is untestable on real code. |
| — | `ksf_FA_Calendar` | 144 | 31 | Entry 4. Events are naturally owned-by-a-user and shared-with-a-team; a clean Owner/Group exercise. |
| — | `ksf_FA_Notes` / `ksf_FA_Attachments` / `ksf_FA_Documents` | 110 / 95 / 21 | Entries 5–7. All three are *attached-to-a-record* — the natural test of whether the predicate composes when the owning record is itself ACL-managed. |
| — | `ksf_FA_DataIntegrity` | 138 | 33 | Entry 8, deliberately late. It reads broadly by design; migrating it early would demand broad ACL coverage before any exists. |
| — | `ksf_FA_Square` | **540** | 79 | **Last.** Largest module by an order of magnitude. Not before entries 1–7 are enforced and stable. |
| — | remainder (60+ modules) | ~336 | ~112 | Tail. `ksf_FA_Common`, `ksf_FA_Classes`, `ksf_FA_Upc2Item`, `ksf_FA_Woocommerce`, `ksf_FA_Logging` are next in the tail by volume. |

> **The ordering above is [D], not [V].** Volumes are measured; **priority is a
> judgement call** and is put to the user as **Q12**. If the compliance deadline
> makes payroll the true first, swap entries 1 and 2 — nothing else depends on the
> order.

### 3.4 Per-module Stage 2 exit criteria

| # | Criterion |
|---|---|
| 1 | Zero `select('*')` and zero raw `where()`/`orderBy()`/`groupBy()` on ACL-managed tables. Verified by CI grep, not review. |
| 2 | Every read of an ACL-managed table goes through a builder call that declares `module` + `record_type`. |
| 3 | The module's own test suite is green **before** the ACL policy is registered, and green **after**. |
| 4 | `SELECT * FROM <table>` from the module's own SQL returns **exactly** what the module's ACL-filtered query returns — i.e. the module never reads an unmanaged table directly. |
| 5 | A `db_query(` census diff shows a **net decrease** in the module's raw call count, and no new raw calls. |

## 4. Rollback

| Stage | Rollback |
|---|---|
| 1 | `git revert` the sed commit per module. The shim is a pure delegation, so reverting restores byte-identical behaviour. |
| 2 | Unregister the policy. `ACL_Two_Approaches.md` §7 OD-2 recommends **allow-all when no policy object is registered**, which makes rollback a one-line config change and not a deploy. |

## 5. Acceptance criteria

| # | Criterion |
|---|---|
| AC1 | Stage 1 census on `ksf_FA_CRM` reports **359** call sites in **77** files, matching this document. |
| AC2 | Zero `db_query(` remain in the repo root of any Stage-1-migrated module, and zero occurrences of the literal string inside a PHP string literal (sed damage check). |
| AC3 | A namespaced file and a non-namespaced file both resolve the rewritten call to the **same** class. |
| AC4 | The shim forwards all four `db_query()` parameters; a 3-argument call site does not fatal. |
| AC5 | Zero files under `ksf_Infrastructure/FA/2.4.3/` are modified by Stage 1 (`git status` on the FA tree is clean). |
| AC6 | `0_…` FA core `db_query(` count is still exactly **870** after Stage 1. |
| AC7 | Stage 1's own documentation, commit message, and status output say **"tripwire, not enforcement"**. |
| AC8 | With no policy registered, a migrated module's generated SQL is **byte-identical** to the pre-migration SQL. |
| AC9 | With a policy registered on one module, no other module's behaviour changes. |

## 6. Explicitly unverified

| Item | Status |
|---|---|
| **The sed was not run.** No count in §2.4/§2.5 came from a sed dry run; they came from `grep`. Which exact patterns the sed catches vs misses is **[UNVERIFIED]** until a `-n` dry run is inspected. |
| Per-module `db_query(` counts | **[V]** for the counts shown. Volumes may differ from the deployed tree; CRM and HRM were counted in the dev trees. |
| The migration **order** (§3.3) | **[D]** — see **Q12**. |
| Whether `SRP_DB_Query` is a hard naming requirement | **UNRESOLVED** — **Q10**. |
| Whether the string-literal sed damage is small enough for `sed` or needs a tokenizer | **[UNVERIFIED]** — **Q11**. |
| Whether FA's `E_USER_ERROR` on a rejected statement is *silent* mid-render | **[V]** as recorded in `ACL_Two_Approaches.md` §5.1; not re-verified here. |

## 7. Related

- [BR-ACL-001](./BR-ACL-001-record-ownership-and-access-control.md) — R8, R9
- [FR-ACL-001-01](./FR-ACL-001-01-ownership-schema.md)
- [FR-ACL-001-02](./FR-ACL-001-02-row-acl-predicate.md) — §5 is the declaration Stage 2 enables
- [OPEN-QUESTIONS.md](./OPEN-QUESTIONS.md) — Q10, Q11, Q12
- [`ACL_Two_Approaches.md`](../ACL_Two_Approaches.md) §5 — phases 1–2, `ksf-common-db` side
- [`Explicit_Column_ACL_API.md`](../Explicit_Column_ACL_API.md) §5 — the `SELECT *` rejection rule
- `ksf_common_db/src/Query/QueryBuilder.php` — `:26`, `:83`, `:112-117`