# FR-ACL-001-04 — The column axis: views per sensitivity class

@BABOK Related: BR-ACL-001, BABOK 8.3 Solution Design, 8.4 Solution Construction
Status: **Proposed**
Module: `ksf_FA_RBAC` (`sql/views.sql`), `ksfraser/ksf-common-db` (future view builder)
Date: 2026-10-14
Verified against: `FA/2.4.3/admin/db/maintenance_db.inc` (read directly, 2026-10-14)
and `ksfii_app-mariadb` (MariaDB 10.11.14-ubu2204, schema `ksf_fa`, read-only)

> **Documentation only.** **No view was created.** Zero views exist in `ksf_fa` at the
> time of writing (`information_schema.views` → **0** **[V]**), and the schema has
> **243** base tables **[V]**.

---

## 1. Scope and relationship to the row axis

This FR covers the **column axis only**. The design decision that both axes exist and
are orthogonal is BR-ACL-001 §2.1. The prior design work for the column axis is in
[`Column_Level_ACL_Design.md`](../Column_Level_ACL_Design.md),
[`Explicit_Column_ACL_API.md`](../Explicit_Column_ACL_API.md) and
[`ACL_Two_Approaches.md`](../ACL_Two_Approaches.md). **This document does not restate
them.** It specifies the three installer/MariaDB constraints that decide how views must
be *written*, and the naming that satisfies them.

The three constraints in §2–§4 were each re-derived from source for this document, not
inherited from the brief. Line numbers are from
`ksf_Infrastructure/FA/2.4.3/admin/db/maintenance_db.inc`.

## 2. Constraint 1 — `NULL AS` makes a view non-insertable (MariaDB 1471)

### 2.1 The rule

A view containing any `NULL AS col` or `CASE … ELSE NULL` masked column is
**not insertable**. MariaDB error **1471** `ER_NON_INSERTABLE_TABLE` —
*"The target table %s of the %s is not insertable-into"*. Updating a masked column
fails with **1348**. **[V — measured matrix in `ACL_Two_Approaches.md` §3.6, against this
same server]**

| View | `INSERT … VALUES` | `INSERT … SELECT` | `UPDATE` masked col | `DELETE` |
|---|---|---|---|---|
| `SELECT id, name, NULL AS ssn, salary` | **1471** | **1471** | **1348** | works |
| same, partial column list | **1471** | **1471** | works on pass-through cols | works |
| `SELECT id, name, salary` (no masking) | works | works | works | works |

### 2.2 The good news, and the architectural consequence

**It fails loudly.** No row is inserted and the caller's value does **not** leak into
the base table **[V — row id checked and absent, `ACL_Two_Approaches.md` §3.6]**. MariaDB
does not silently substitute the `NULL` default and drop the write.

> **A masked view is READ-ONLY by construction. Every write path must target the base
> table.**

Consequence for this FR: a masked view may **not** be used as an `INSERT`/`UPDATE`
target anywhere, and any module that reads through a view and writes through it will
break on insert with a 1471 that surfaces as FA's uncatchable `E_USER_ERROR`.

### 2.3 Requirement

| ID | Requirement |
|---|---|
| **V-1** | Module SQL shall never `INSERT` to or `UPDATE` a masking view. All writes target the base table. |
| **V-2** | The write-path contract shall be documented in every module that reads through a view. |

## 3. Constraint 2 — `db_import`'s allow-list discards `DROP VIEW` and `ALTER VIEW`

### 3.1 The allow-list, read from source

`maintenance_db.inc:274-286`:

```php
$allowed_commands = array(
    "create"  => 'table_queries',
    "delimiter" => 'table_queries',
    "alter table" => 'table_queries',
    "insert" => 'data_queries',
    "update" => 'data_queries',
    "set names" => 'set_names',
    "drop table if exists" => 'drop_queries',
    "drop function if exists" => 'drop_queries',
    "drop trigger if exists" => 'drop_queries',
    "select" => 'data_queries',
    "delete" => 'data_queries',
    );
```

The parser loop (`:339-364`) matches only lines whose **lowercased prefix** equals one
of these keys. **A line that matches nothing is silently dropped** — there is no
"unrecognised statement" warning.

### 3.2 Consequence table

| Statement | Matched? | Runs? | Why |
|---|---|---|---|
| `CREATE OR REPLACE VIEW 0_x AS SELECT …` | ✓ `create` | **YES** | `:275` `"create"` is a **prefix** match, so `create or replace view` matches. **[V — read at `:343`]** |
| `CREATE VIEW 0_x AS SELECT …` | ✓ `create` | runs, but errors **1050** on an existing view | 1050 *"Table already exists"* is in `$ignored_mysql_errors` (`:295`) → **silently ignored; the stale view survives** |
| `DROP VIEW IF EXISTS 0_x` | ✗ | **NO** | not in the list |
| `DROP VIEW 0_x` | ✗ | **NO** | not in the list |
| `ALTER VIEW 0_x AS …` | ✗ | **NO** | only `alter table` is listed |
| `DROP TABLE IF EXISTS 0_x` (naming a **view**) | ✓ `drop table if exists` | **YES — and drops the view** | `information_schema` treats views and tables alike; the `DROP TABLE` succeeds against a view |

> **The brief's claim is confirmed by source.** `DROP VIEW` and `ALTER VIEW` are
> silently discarded, so **`CREATE OR REPLACE VIEW` is the only view-creation verb
> available** through a module's `sql/*.sql`.

### 3.3 Mandatory operational rules

| # | Rule |
|---|---|
| **V-3** | Module `sql/*.sql` shall use **`CREATE OR REPLACE VIEW`** and nothing else for view DDL. There is no drop verb. |
| **V-4** | `CREATE OR REPLACE VIEW` shall **respecify the entire column list** on every run. A view whose column list changes between module versions must not be updated in place by an `ALTER`. **[V — `OR REPLACE` accepts a changed column list; *column removal* by `OR REPLACE` is [UNVERIFIED]]** |
| **V-5** | Module SQL shall **never** contain `DROP TABLE IF EXISTS <a view name>`, even though it is the only drop verb that runs. It is a foot-gun in a file that also declares base tables. |
| **V-6** | View removal outside an upgrade shall be performed by application code (`db_query("DROP VIEW …")`), never by `sql/*.sql`. |
| **V-7** | Views are created with **`DEFINER=<creator> SQL SECURITY DEFINER`** **[V — `ACL_Two_Approaches.md` Appendix A finding 13]**. A view created by one FA login and later used after that account is dropped raises **1449** *"Definer of view/routine no longer exists"*. Module view DDL shall therefore be created by the install path's own connection, and the deployment documentation shall record the creating account. |

### 3.4 A backup-path risk not in the brief **[A — inferred from reading, NOT executed]**

`db_export()` (`:546-758`) enumerates objects with `show table status` (`:607`) and
filters only by prefix (`:611-613`):

```php
if (($conn["tbpref"] == "" && !preg_match('/[0-9]+_/', $row['Name'])) ||
    ($conn["tbpref"] != "" && strpos($row['Name'], $conn["tbpref"]) === 0))
        $all_tables[] = $row;
```

In MariaDB, `SHOW TABLE STATUS` **includes views** (with `Type = 'VIEW'`), and
`SHOW CREATE TABLE` on a view returns a `CREATE … VIEW` statement. So `db_backup()`/`db_export()`
will very likely emit view DDL as `CREATE ALGORITHM=… VIEW` — **not**
`CREATE OR REPLACE VIEW` — preceded by `DROP TABLE IF EXISTS <view>`, which per §3.2
*does* run.

If that is what happens, a backup/restore cycle **drops every masking view and then
fails to recreate it** (a bare `CREATE VIEW` on a name that no longer exists succeeds,
but the emitted form includes `ALGORITHM`/`DEFINER` clauses whose exact behaviour
through `db_import` was not tested here).

> **[UNVERIFIED]** — no backup was taken and no restore was attempted. **This must be
> tested before any masking view is deployed**, because it is the one path that could
> silently remove the control. Tracked as **Q13**.

## 4. Constraint 3 — the `0_` substitution is whole-line and unconditional

### 4.1 The line

`maintenance_db.inc:336-337`:

```php
if ($init)
    $line = str_replace("0_", $connection["tbpref"], $line);
```

Three properties, each of which matters:

1. **It is a blanket `str_replace` on the whole line**, not a table-name-aware pass.
   Every occurrence of the two characters `0_` anywhere in the line is rewritten —
   **including inside string literals, comments, and column defaults**.
2. **It runs per company.** Installing or updating a module for company 2 rewrites
   `0_` → `1_` throughout.
3. **It is gated on `$init`**, which is `true` by default for the extension install
   path.

### 4.2 Consequence: unprefixed view names are actively dangerous

| Naming | What `db_import` does | Verdict |
|---|---|---|
| **`0_crm_contacts_core`** (prefixed, FA convention) | Rewrites **both** the view name **and** the `FROM 0_crm_contacts` in its body → company 2 gets `1_crm_contacts_core` over `1_crm_contacts`. Self-consistent. | **REQUIRED** |
| `v_crm_contacts_core` / `crm_contacts_core` (unprefixed) | The **name** is untouched, but the **body's** `FROM 0_crm_contacts` **is** rewritten. Company 2's install **mutates the single global view** to point at `1_crm_contacts`. Company 1's masked reads then silently return **company 2's data**. | **PROHIBITED** |

> An unprefixed view name is **not** "one view for everyone". It is a **shared object
> whose body is rewritten in place by every subsequent company install** — a
> cross-company data leak that no test in a single-company setup would catch.

### 4.3 Requirement

| ID | Requirement |
|---|---|
| **V-8** | Every ACL view shall be named **`0_<logical>`** — obeying FA's company-prefix convention — using the literal `0_`, never `{TB_PREF}` or `@TB_PREF@` (which `db_import` does not touch, per `AGENTS.md`). |
| **V-9** | A view body shall contain **no** `0_` sequence except as the intended table prefix. A `0_` inside a string literal, a comment, or a column default will be silently rewritten per company. |
| **V-10** | A view's `COMMENT`, if any, shall be free of the literal `0_`. |
| **V-11** | Builder code shall reference views **unprefixed** (`from('crm_contacts_core')`), because `FaDbAdapter::prefixTables()` adds the prefix. Naming `0_crm_contacts_core` in builder code produces `1_0_crm_contacts_core` for company 2 **[V — `FaDbAdapter.php:70-72` tests `strpos($name, $prefix) === 0`]**. |

## 5. The view design

### 5.1 Naming — one view per sensitivity class

Views are named `<table>_<class>`, prefixed:

| View (company 1) | Sensitivity class | Contains |
|---|---|---|
| `0_crm_contacts_core` | Core | Non-personal operational fields: `id`, `ref`, `name`, `category_id`, `notes`, `inactive` |
| `0_crm_contacts_pii` | PIPEDA/GDPR personal data | Everything in `core` **plus** `email`, `phone`, `date_of_birth`, `ssn`, … |
| `0_crm_contacts_contact` | Physical contact details | Everything in `pii` **plus** mailing address fields |

The classes are **cumulative**, so a caller joins **only the class it is entitled to**
and never a broader one. Naming is `<table>_<class>`; do **not** use a `v_` prefix
(§4.2), and do not use a bare `<table>_masked` for a set that has more than one class.

### 5.2 Why views, and why a caller joins only what it is entitled to

BR-ACL-001 §2.2: because the caller **must name the view** to get a column out of it,
and because joining a view is an explicit act, a column cannot leak through a join the
caller did not intend. This structurally closes the "join leaks a value without naming
the column" class of problem.

**Residual oracles that this does NOT close** (carried forward from
`ACL_Two_Approaches.md` §1.3 — stated here so no reader over-reads this FR):

- `WHERE <masked col> >= :g`, `ORDER BY <masked col>`, `AVG()`, `COUNT()` on a masked
  view operate on the `NULL` literal and do **not** throw. **[A]** — constant-folding
  not separately benchmarked.
- A caller that names the **base table** bypasses the view entirely. Per
  `ACL_Two_Approaches.md` §1.4 and OD-1, the view is only a **control** if base-table
  reads are denied — which today they are not (`ksf_user` holds
  `ALL PRIVILEGES ON ksf_fa.*`, **a single non-system account** **[V]**).

### 5.3 A masking view gets no `TableDefinition`

A view is not a table. It has no independently meaningful DDL, `INSERT` or `UPDATE`
(§2.1). Therefore:

| Rule | |
|---|---|
| **V-12** | A view **must not** get a `TableDefinition`. It would generate `createSql()`/`insertSql()`/`updateSql()` that are wrong or fail. |
| **V-13** | A view **does** need a column list, for the explicit-column API to check against. A **view-shaped dictionary type** is required. **[D — not designed here]** |
| **V-14** | `TableDefinition::sensitivity()` stays the **declaration** of which columns are candidates. The **view generator** is what applies policy. The dictionary remains policy-free; it does not become an ACL table. |

## 6. Acceptance criteria

| # | Criterion |
|---|---|
| AC1 | `sql/views.sql` contains **only** `CREATE OR REPLACE VIEW` for view DDL — verified by grep for `DROP VIEW`, `ALTER VIEW`, and bare `CREATE VIEW` (must be 0 hits). |
| AC2 | Every view name in `sql/views.sql` begins with the literal `0_`. |
| AC3 | Every table reference inside every view body begins with the literal `0_`, and **no** `{TB_PREF}` or `@TB_PREF@` appears anywhere in the file. |
| AC4 | Installing the module for company 2 produces `1_crm_contacts_core` whose `FROM` clause references `1_crm_contacts` — and company 1's `0_crm_contacts_core` is **byte-identical** before and after. |
| AC5 | `INSERT INTO 0_crm_contacts_pii … VALUES (…, 'secret-ssn', …)` fails with **1471**, and the base table row is verified **unchanged**. |
| AC6 | `UPDATE 0_crm_contacts_pii SET ssn = …` fails with **1348**. |
| AC7 | `EXPLAIN` through `0_crm_contacts_core` shows the same access type and key as the base table — i.e. the optimizer **merged** the simple masking view rather than materialising it **[V — measured for the simple form in `ACL_Two_Approaches.md` §3.4; a 4-row table, no timings]** |
| AC8 | Re-running `CREATE OR REPLACE VIEW` with a changed column list succeeds and takes effect. |
| AC9 | **`db_backup()` → restore → the masking views still exist and are correct.** (See §3.4 — **[UNVERIFIED]**, this is the test that closes **Q13**.) |
| AC10 | Builder code referencing `from('crm_contacts_core')` resolves correctly for company 1 **and** company 2, with no `0_` remnant and no `1_0_` double-prefix. |

## 7. Explicitly unverified

| Item | Status |
|---|---|
| **No view was created.** Everything in §2.2 is measured (by the prior document, on this server); nothing in §5 was executed. | — |
| The `db_export` → `db_import` behaviour with views present (§3.4) | **[UNVERIFIED]** — inferred from reading `:607-621`. **Q13.** This is the highest-risk unverified item in this FR. |
| `CREATE OR REPLACE VIEW` **removing** a column | **[UNVERIFIED]** — accepting a changed column list is **[V]**; shrinking one was not tested. |
| Which columns on which tables actually belong to which sensitivity class | **NOT STARTED.** This is `ACL_Two_Approaches.md` §5 phase 3, and it **blocks** all view work. No classification exists. |
| `EXPLAIN` parity on FA's real tables and real report queries | **[UNVERIFIED]** — measured only on a 4-row table. **Do not quote a performance claim.** |
| `FaDbAdapter::prefixTables()` behaviour was re-read from source here, not re-executed | **[V by reading]**, previously **[V by execution]** in `ACL_Two_Approaches.md` Appendix A finding 16. The comma-join and CTE defects stand. |
| Whether the masking views must be created by a specific MySQL account to avoid 1449 | **[V]** that `DEFINER` is set to the creator; **[UNRESOLVED]** which account should be canonical. Part of V-7. |
| Multi-company behaviour (§4.2) is **derived from reading `db_import`**, not observed on a live company 2 | **[UNVERIFIED]** — AC4 is the test. |

## 8. Related

- [BR-ACL-001](./BR-ACL-001-record-ownership-and-access-control.md) — R1, §2.2
- [FR-ACL-001-01](./FR-ACL-001-01-ownership-schema.md) — the row axis
- [FR-ACL-001-02](./FR-ACL-001-02-row-acl-predicate.md) — the row axis
- [FR-ACL-001-03](./FR-ACL-001-03-two-stage-enforcement-migration.md)
- [OPEN-QUESTIONS.md](./OPEN-QUESTIONS.md) — Q13, and the sensitivity-classification blocker
- [`ACL_Two_Approaches.md`](../ACL_Two_Approaches.md) §3.2, §3.3, §3.4, §3.6 — the prior verification this builds on
- [`Column_Level_ACL_Design.md`](../Column_Level_ACL_Design.md) §2.3 — the inference-oracle matrix
- `FA/2.4.3/admin/db/maintenance_db.inc` — `:274-286`, `:293-300`, `:336-337`, `:339-364`, `:546-758`