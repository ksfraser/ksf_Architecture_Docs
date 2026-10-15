# Schema Derivation — how a module's schema is obtained for the registry

> ## ⚠️ PARTIALLY SUPERSEDED — 2026-10-15, by [`Schema_Codegen_Design.md`](./Schema_Codegen_Design.md)
>
> **Superseded: §6.1 ("when schema is derived") and §7.2 items 11–13.**
> Schema is now generated at **development time**, the output is **committed**, and a
> **unit test** compares the committed file to the live database. Nothing parses SQL
> at runtime. See `Schema_Codegen_Design.md` §1–§3 and its §6 (the replacement
> phased plan).
>
> **NOT superseded — and this is the reason the file was kept: everything in
> **Part 0 (Verification), Part 0bis (§0.9–§0.12), Part 1, Part 2 and Part 3 is the
> evidence base for the codegen design and is cited by it, not re-derived.**
> In particular the verified findings stand: the three disagreeing ordering
> authorities and A2's live win (§0.9, §0.12), the corpus census (§0.3), the
> `db_import` semantics and its three corrections (§0.1a, §0.2, §0.2a), FA's splitter
> being correct and to be **extracted, not rewritten** (§0.11, §2.6), the PM blocker
> confirmed live at **0 of 11 objects** (§0.5, §0.12), the accumulator state and
> mutation rules (§0.10), and the overlay separation with `R-POL-1/2/3/4` (§3.4).
>
> **§5.1 (the five sources) still holds as the problem statement** — codegen resolves
> it by making the derived half a regenerable *artefact* rather than a *copy*, which
> is a different answer to the same question, not a different question.
>
> **Content below is preserved verbatim, including the superseded sections, so the
> superseded reasoning remains auditable.**

**Date:** 2026-10-15 · **Revision 2** (same day)
**Status:** DESIGN + VERIFICATION. **No production code was written, no hook was
added, no commit was made.**

> ## Revision 2 — the premise correction
>
> An earlier draft of this document parsed **one file** (`sql/install.sql`) and
> called the result "A′". That was still wrong, and Revision 2 fixes it:
>
> 1. **The unit of derivation is REPLAY, not a file.** A module's schema is the
>    accumulated result of executing **every SQL file the module's installer will
>    run**, in the installer's order, against a virtual empty database. Upgrade
>    files are **differential** (`ALTER TABLE` / `CREATE INDEX` / `DROP INDEX`),
>    so a single-file parse is structurally incapable of producing the schema.
> 2. **The ordering authority is not a directory listing, but neither is it
>    `$updates` alone.** There are **three** competing authorities in this tree
>    and **they disagree**. Verified in §0.9 with a per-module census.
> 3. **Two claims in Revision 1 are corrected as factually wrong** — §0.10
>    (`CREATE INDEX` is *not* discarded by the whitelist; it is a prefix match)
>    and §0.1's claim that a manifest entry naming a missing file "fatals
>    activation" (it returns `true` — silently).
> 4. **The splitter is not to be written.** FA already solves multi-statement
>    framing, and its framing is *correct* on the exact file Revision 1 used as
>    proof that a new splitter was needed. §0.11: extract, do not reimplement.
> 5. **New live verification against the Integration database** (§0.12),
>    including the v0 PM blocker — **confirmed, not inferred** — and a
>    demonstration that the directory-scan authority has *already* beaten the
>    manifest in production.
>
> Parts 3–6 (the overlay, DTOs, eliminating the copies, when to derive) are
> **carried forward unchanged**, with the overlay separation restated in §3.4 as
> required.
**Scope:** how a module supplies schema to the registry proposed in
[`Schema_Registry_Design.md`](./Schema_Registry_Design.md), settled against the
real `sql/` trees in `~/Documents/ksf_Infrastructure/fa_modules/*/sql/`, the real
FA 2.4.3 installer, and the one module that uses `TableDefinition` today.
**Supersedes nothing.** `Schema_Registry_Design.md` §D.4 (`schema_advertise()` /
`schema_resolve()`) is unaffected in shape; this document decides **what those two
hooks return**, and that decision **changes its cost model**.

**Tag key — the same convention used by the sibling documents:**
**[V]** verified against source or by execution in this session.
**[D]** proposed design — nothing exists.
**[UNVERIFIED]** explicitly not known.
Untagged text is reasoning or a decision.

**BABOK:** `@BR-SD-001` (Business Requirement: one schema declaration),
`@FR-SD-001-001` … `@FR-SD-001-007` (the seven functional requirements resolved
in §P7). Revision 2 adds `@FR-SD-001-008` (multi-file differential replay) and
`@FR-SD-001-009` (ordering-authority resolution across three authorities).
Requirement *files* are not created by this document; it names the
identifiers the follow-on implementation will file under
`ProjectDcs/`, per `AGENTS.md` §"ProjectDcs Structure".

---

# PART 0 — Verification first

Everything in this part is **[V]**. It changes the question's premise: option
(A) is not "parse the module's own `sql/install.sql`", because **most modules do
not have one, and the file that does exist is not what FA runs.**

## 0.1 The installer does not read `sql/`. It reads a map in `hooks.php` **[V]**

FA 2.4.3, `includes/hooks.inc:31-63`:

```php
function update_databases($comp, $updates, $check_only=false)
{
    …
    foreach($updates as $file => $update) {
        $table      = @$update[0];
        $field      = @$update[1];
        $properties = @$update[2];

        $ok = check_table($con['tbpref'], $table, $field, $properties) == 0;

        if (!$check_only && !$ok) {
            $ok = db_import($path_to_root.'/modules/'.$this->module_name.'/sql/'.$file, $con);
        }
```

`check_table()` (`admin/db/maintenance_db.inc:948-973`) returns:

| Return | Meaning |
|---|---|
| `1` | no such table → **run the file** |
| `2` | table exists, field missing → **run the file** |
| `3` | table + field exist but a property differs → **run the file** |
| `0` | already satisfied → **skip** |

Three consequences that decide the whole design:

1. **FA never lists `sql/`.** The *`$updates` array literal in `hooks.php`* is the
   operative schema manifest. A file in `sql/` that no map names is **never run**.
   A file the map names but that does not exist **does not fatal — it succeeds
   vacuously** (**corrected in Revision 2**, see §0.1a).
2. **`install.sql` is not privileged.** It is just a filename. Calendar's
   manifest is `install.sql` plus **12** `upgrade_*.sql` entries, each gated on
   its own `(table, field)` pair (`ksf_FA_Calendar/hooks.php:54-64`).
3. **The gate can be unsatisfiable, and that is the documented normal case.**
   Calendar's own comment (`hooks.php:67-84`) records two live failures caused by
   gates naming tables the module does not own —
   *"update_databases() runs a script when its (table, field) gate is MISSING, so
   any gate naming a table that install.sql never creates is unsatisfiable: the
   script runs on every activation and aborts the whole upgrade"* — with the real
   error strings *"Table '0_fa_cal_preferences' doesn't exist"* and *"Table
   '0_ksf_contact_types' doesn't exist"*.

**PM is in exactly that state today [V]** — `ksf_FA_ProjectManagement/hooks.php:92-97`:

```php
// Apply sql/install.sql using update_databases()
// This handles @TB_PREF@ replacement automatically
if (file_exists(dirname(__FILE__) . '/sql/install.sql')) {
    $updates = array('install.sql' => array($this->module_name));
```

`array($this->module_name)` = `array('ksf_FA_ProjectManagement')` — a **table
name PM's `install.sql` never creates** (`CREATE TABLE` there yields 9 tables,
none of them that). So the gate is unsatisfiable and `install.sql` re-runs on
**every** activation of every company. It is idempotent only because every
statement is `CREATE TABLE IF NOT EXISTS`.

**And the comment above it is false [V].** `db_import()` substitutes only the
literal `0_`. It does not handle `@TB_PREF@`. The same false claim appears in
`ksf_FA_Assets/hooks.php:18` and `:87` (*"Use sql/install.sql with @TB_PREF@
placeholders"*, *"This handles @TB_PREF@ replacement automatically"*) and
`ksf_FA_API/hooks.php:18`. The only module that documents the truth is
`ksf_FA_Warehouse/sql/install.sql:3-5`:

> FA's `db_import()` substitutes ONLY the literal "0_" with the company table
> prefix — it does not understand `{TB_PREF}`, `@TB_PREF@` or `{{MDB}`.

### 0.1a CORRECTION — a wired-but-missing file succeeds silently **[V]**

Revision 1 asserted: *"A file the map names but that does not exist **fatals
activation**."* **That is wrong**, and the correction matters because it changes
what a derivation must do with an unreachable manifest entry.

Verified by reading `db_import()` through to its return
(`maintenance_db.inc:267-490`):

| Line | Behaviour on a nonexistent `$filename` |
|---|---|
| `:325` | `$lines = file("". $filename);` → returns `false` + a PHP warning |
| `:328-374` | `foreach($lines …)` over `false` → no iterations; `$table_queries`, `$data_queries`, `$drop_queries`, `$set_names` all remain `null` |
| `:429-467` | every execution block is guarded by `if (is_array(...))` → all skipped |
| `:483-490` | `count($sql_errors) == 0` → **`return true;`** |

**Consequence:** a manifest entry whose file is absent is a **silent no-op that
reports success**. Two live instances in this tree:

- `ksf_FA_AsteriskPBX/hooks.php:54` — `$updates = array('sql/update.sql' => …)`.
  `update_databases()` builds the path as `modules/<module>/sql/` **`.`** `$file`
  (`hooks.inc:50`), so this resolves to
  `modules/ksf_FA_AsteriskPBX/sql/sql/update.sql` — a **doubled `sql/`**. The
  file does not exist, and the gate (`ksf_FA_AsteriskPBX`, not a table) is
  unsatisfiable, so this line runs on **every activation** and always reports
  success. AsteriskPBX's three tables come from `ensure_asterisk_schema()` in
  PHP (`hooks.php:63-107`), which is why nobody noticed. **This is the clearest
  live demonstration that a derivation must report unreachable manifest entries
  rather than treat them as satisfied.**
- `ksf_FA_Customer/hooks.php` — wires `install.sql`; the module has **no `sql/`
  directory at all** **[V]**.

**Design consequence [D]:** the derivation's manifest walker MUST emit a
`ManifestEntryUnreachable` finding for every entry whose resolved path does not
exist, and the reconcile step (§6.2) MUST compare against `information_schema`
rather than trusting a "success" return. See `R-ORD-4` in §0.9.

## 0.2 What `db_import()` actually does — and must not be disagreed with **[V]**

`admin/db/maintenance_db.inc:267-377`:

| Line | Behaviour |
|---|---|
| `:274-286` | **A whitelist of 11 case-insensitive PREFIXES**, matched against the *start of the trimmed line*: `create`, `delimiter`, `alter table`, `insert`, `update`, `set names`, `drop table if exists`, `drop function if exists`, `drop trigger if exists`, `select`, `delete`. **CORRECTION (Revision 2): `create` is a bare 6-character prefix, not the phrase "create table".** Any line starting with `CREATE` matches it. See §0.2a. |
| `:337` | `if ($init) $line = str_replace("0_", $connection["tbpref"], $line);` — **unconditional, whole-line, no lexical awareness.** `$init` defaults `true`; `update_databases()` never passes it. |
| `:341-364` | A line only enters a statement buffer if it *starts with* a whitelisted prefix. |
| `:368-374` | Statement termination is **"does the trimmed line end with `;`"** — a line test, not a tokenizer. Everything up to that point is concatenated with `"\n"`, including trailing `--` comment lines and any part of a multi-line quoted string. |
| `:429-467` | **Execution order inside one file is NOT textual order.** Three separate loops run in sequence: `$drop_queries` → `$table_queries` → `$data_queries`. A `DROP TABLE` textually *after* a `CREATE TABLE` in the same file still executes **first**. |
| `:293-300` | Errors `1022, 1050, 1060, 1061, 1062, 1091` are ignored — i.e. **`CREATE TABLE` failing because the table exists is not an error, and neither is `ADD COLUMN` failing because the column exists.** |

### 0.2a CORRECTION — `CREATE INDEX` is **not** discarded **[V]**

Revision 1 (§0.2 and §2.5) stated that `CREATE INDEX`, `CREATE VIEW`,
`RENAME TABLE` and `CREATE PROCEDURE` are *"silently discarded"* by
`db_import()`. **The first three of those claims are wrong.**

The test at `maintenance_db.inc:344` is
`strtolower(substr($line, 0, strlen($cmd))) == $cmd`. With `$cmd = 'create'`,
that is a six-character prefix test. Probed by execution **[V]**:

| Statement | Bucket | Real consequence |
|---|---|---|
| `CREATE INDEX \`i\` ON \`0_t\` (\`c\`)` | `create` → `table_queries` | **EXECUTED** |
| `CREATE UNIQUE INDEX \`u\` ON \`0_t\` (\`c\`)` | `create` → `table_queries` | **EXECUTED** |
| `CREATE OR REPLACE VIEW v AS SELECT 1` | `create` → `table_queries` | **EXECUTED** |
| `CREATE PROCEDURE p() BEGIN END` | `create` → `table_queries` | **EXECUTED** (and then fails, no `DELIMITER`) |
| `RENAME TABLE \`0_a\` TO \`0_b\`` | — | **discarded** |
| `DROP INDEX \`i\` ON \`0_t\`` | — | **discarded** (only three `DROP …` prefixes are listed) |
| `DROP VIEW v` / `TRUNCATE TABLE \`0_t\`` | — | **discarded** |

**So the true rule is:** *everything beginning `CREATE`, `INSERT`, `UPDATE`,
`SELECT`, `DELETE`, `SET NAMES`, `ALTER TABLE`, or one of three exact `DROP …
IF EXISTS` phrases runs; everything else is dropped on the floor.*

This does **not** change the practical answer, because a swept census found
**zero** statements in the corpus that begin with a discarded prefix **[V]** —
there is no `RENAME`, no `DROP INDEX`, no `DROP VIEW`, no `TRUNCATE`, no
`CREATE INDEX`, no `CREATE VIEW` and no `CREATE PROCEDURE` anywhere in the 148
files. The whitelist gap is **latent, not active** — but Revision 1 asserted the
wrong shape of it, and a derivation that silently skipped `CREATE INDEX` would
be wrong the day a module uses one.

**The correct derivation rule is therefore `R-WL-1` (§2.5): bucket by FA's
prefix test, execute the `create` bucket as schema-bearing, and *warn* on any
line that is neither a continuation nor a prefix match.**

Two facts a derivation layer must respect:

- **The `0_` substitution is textual, not lexical.** It rewrites `0_` *inside
  string literals and inside `--` comments too*. `ksf_FA_RBAC/sql/install.sql:114`
  seeds a description containing the literal text
  `'FA system user account linked via 0_crm_contacts.entity_id = 0_users.id'`,
  which reaches the database as `…linked via 1_crm_contacts…` for company 1.
  A parser that mirrors this faithfully will see mangled text; a parser that
  skips literals will not. **Neither is "wrong" — but the derivation must declare
  which one it is, and must not claim the other.**
- **`0_` is a prefix of nothing else in practice, but `{{MDB}}`-style names are
  not substituted at all.** 33 files still contain the text `TB_PREF`
  **[V]**, including `ksf_FA_Logging/sql/install.sql:11`, which creates
  `` `@TB_PREF@ksf_log_levels` ``. MySQL accepts that as a legal backticked
  identifier, so the statement **succeeds and creates an unprefixed,
  wrong-named table.** *This is a latent live defect; see §A.2 item 1 for what I
  did not verify.*

## 0.3 Coverage census — the statements that actually run **[V]**

**Revised in Revision 2.** Revision 1 counted verbs by grepping raw lines. That
counts the wrong thing twice over: it counts statements FA **discards**, and it
counts statements **twice** where one `.sql` file contains two. The census below
frames every file with FA's *own* framing algorithm (§0.11) and buckets by FA's
*own* prefix whitelist (§0.2a), so it measures what `db_import()` would execute.

148 `.sql` files across 42 module directories in `fa_modules/`, framed with
`db_import()`'s exact algorithm, `0_` → `1_` **[V]**:

| Bucket | FA-framed statements |
|---|---|
| `create` → `table_queries` (schema-bearing) | **215** — *all* of them `CREATE TABLE IF NOT EXISTS` |
| `alter table` → `table_queries` (schema-bearing) | **46** |
| `insert` → `data_queries` | 40 (incl. `INSERT IGNORE`, `INSERT … ON DUPLICATE KEY`) |
| `drop table if exists` → `drop_queries` | 18 — **all in `uninstall.sql`, none wired** (§0.3a) |
| `update` → `data_queries` | 14 |
| `select` → `data_queries` | **0** |
| **Total framed** | **333** |

Sub-clause census of the **215 `CREATE TABLE`** statements **[V]**:

| Clause | Occurrences |
|---|---|
| `IF NOT EXISTS` | **215 / 215** (100%) |
| `KEY \`…\`` | 291 |
| `PRIMARY KEY` | 214 |
| `ENGINE=…` | 196 |
| `UNIQUE KEY \`…\`` | 85 |
| `CONSTRAINT` / `FOREIGN KEY` | 38 / 39 |
| `CHECK (…)` | **0** (Revision 1 reported 2; both were `CHECK` inside a *comment string*. **Corrected.**) |

Sub-clause census of the **46 `ALTER TABLE`** statements — this is the
differential vocabulary the accumulator must implement, and the answer to *"what
do I actually have to support"* **[V]**:

| Action keyword | Count | Where |
|---|---|---|
| `ADD COLUMN` | **32** | ProductAttributes, Calendar (all 11 upgrades), Attachments, Notes, bank_import |
| `MODIFY` | **15** | 12 on **FA core** tables + 2 ProductAttributes |
| `ADD INDEX` | **10** | Calendar ×7, bank_import ×3 |
| `ADD CONSTRAINT … UNIQUE` | **2** | bank_import only |
| `ADD KEY` | **1** | Calendar `upgrade_2.1.0.sql` (orphaned — §0.9) |
| `DROP INDEX` | **1** | bank_import `add_occurrence_count_to_bi_partners_data.sql:18` |
| `ADD PRIMARY KEY` / `DROP COLUMN` / `CHANGE <col>` / `RENAME` | **0** | — (Revision 1 reported `CHANGE` ×1 and `CHECK` ×2; all three were **false positives from words inside `COMMENT` strings**. **Corrected.**) |

**Statements with zero occurrences in the corpus — therefore NOT in scope for v1,
but specified anyway (§2.5) so a future file cannot silently break the replay:**
`DROP COLUMN`, `RENAME TABLE`, `RENAME COLUMN`, `RENAME INDEX`, standalone
`CREATE INDEX`, `CREATE VIEW`, `CREATE PROCEDURE|FUNCTION|TRIGGER`,
`ALTER TABLE … ALGORITHM=|LOCK=`, `TRUNCATE`, `CONVERT TO CHARACTER SET`.
**[V]** — swept across all 148 files.

`AFTER \`col\`` positional insertion appears **27 times** across 11 files **[V]**
and must be honoured by the accumulator (§2.1).

## 0.3a Every `DROP TABLE` in the tree is in an unwired `uninstall.sql` **[V]**

All 18 `DROP TABLE IF EXISTS` statements live in `uninstall.sql` files
(`ksf_FA_ProjectManagement`, `ksf_FA_PurchaseOrderTracking`,
`ksf_FA_StockReservations`, `ksf_FA_StockTurnover`,
`ksf_FA_ManufacturerConsolidation`) **[V]**. **Not one is named by any
`$updates` manifest** (§0.9 census). **No file in the corpus mixes `DROP` with
`CREATE`** **[V]**, so the drop-before-create reordering at `maintenance_db.inc:429`
has no effect on this corpus today — but a derivation must still implement it,
because it is a live behaviour of the thing it is modelling.

**23 of those 42 module directories have no `sql/install.sql` at all** **[V]**.
The largest schemas are the ones that do not have one:

| Module | `.sql` files | Has `install.sql`? |
|---|---|---|
| `FA_ProductAttributes` | 36 | **no** |
| `ksf_FA_CRM` | 21 | **no** — one file per table, all 21 named in `$updates` (`hooks.php:102-123`) |
| `ksf_FA_HRM` | 19 | **no** |
| `ksf_FA_Calendar` | 15 | yes, but **3 tables' columns live only in upgrade files** (§0.4) |
| `ksf_FA_EmailManager` | 6 | **no** |
| `ksf_FA_Notes` | 3 | **no** — one file per table (`hooks.php:201-204`) |
| `ksf_FA_ProjectManagement` | 2 | yes |

**And two modules create their tables in PHP, not in SQL at all [V]:**
`ksf_FA_AsteriskPBX/hooks.php:63-107` (`fa_asterisk_extensions`,
`fa_asterisk_calls`, `fa_asterisk_voicemail`) and
`ksf_bank_import/hooks.php:167-250` (`bi_config`, `bi_config_history`,
`bi_uploaded_files`, `bi_file_statements`, `bi_bank_accounts`).

**A single-file parse cannot see nine tables that exist.**

One more **[V]**: `ksf_FA_Assets/sql/install.sql` creates
`fa_asset_categories`, `fa_assets`, `fa_asset_depreciation`,
`fa_asset_maintenance`, `fa_asset_transfers` — **with no `0_` prefix**. Per
`:337` no substitution occurs, so those five tables are created *outside* the
company's prefix space. Latent defect; see §A.2 item 2.

## 0.4 A live, already-installed case where `install.sql` alone is WRONG **[V]**

`ksf_FA_Calendar/sql/install.sql` creates five tables. Three columns that the
Calendar code uses exist **only in `upgrade_*.sql`**:

| Column | In `install.sql`? | Defined in |
|---|---|---|
| `direction` | yes (1×) | — |
| `parent_entry_id` | yes (3×) | — |
| `recurrence_end_date` | yes (2×) | — |
| `delta` | **no** | `upgrade_1.9.0.sql:41` — `ADD COLUMN \`delta\` JSON DEFAULT NULL` |
| `closed_at` | **no** | `upgrade_2.3.0.sql:6` — `ADD COLUMN IF NOT EXISTS \`closed_at\` DATETIME NULL DEFAULT NULL` |
| `contact_type_fa_user` | **no** | *nowhere* — it is `upgrade_1.7.0.sql`'s **gate**, and that file's body is a data `UPDATE` only |

A derivation layer that reads `install.sql` produces a `0_fa_cal_entries` schema
**missing three live columns**, including `closed_at`, which
`Workflow_Engine_Design.md` and the event-close flow both depend on. The correct
unit is not "the `install.sql` file" — it is **"the ordered replay of the
`$updates` map against a fresh database"**.

## 0.5 The drift the brief names is real, and it is three bugs, not one **[V]**

`ksf_FA_ProjectManagement` dev tree,
`src/Ksfraser/FrontAccounting/ProjectManagement/Dictionary/Schema.php`:

| Fact | Line |
|---|---|
| 10 `const T_*` table-name constants | `:38-47` |
| 10 `public static function *(): TableDefinition` | `:65,92,137,156,175,191,215,240,260,280` |
| `createSqls()` iterates **10** entries | — |
| `definitionFor()`'s `$map` has only **9** — `T_TASK_DEPENDENCIES` is absent | — |
| ⇒ `definitionFor('fa_pm_task_dependencies')` returns `new TableDefinition($table)`, **column-less** | — |
| `taskDependencies()` at `:137` is therefore **unreachable from `definitionFor()`** | — |

But that is the *smallest* of the three. Diffing the dev tree against the
deployed copy **[V]**:

```
diff ~/Documents/ksf_FA_ProjectManagement/sql/install.sql
     ~/Documents/ksf_Infrastructure/fa_modules/ksf_FA_ProjectManagement/sql/install.sql
```

| Difference | Consequence |
|---|---|
| Deployed copy has **9** tables; dev tree has **10**. Deployed **lacks `0_fa_pm_task_dependencies` entirely.** | The table `TaskDependencyRepository` queries is never created on the Integration pod by any deploy-and-activate cycle. |
| Deployed `0_fa_pm_tasks` lacks **10 CPM columns**: `is_milestone, is_constrained, constraint_type, constraint_date, es, ef, ls, lf, slack, is_critical` and 2 keys (`idx_milestone`, `idx_critical`). | `Schema::tasks()` `:105-116` declares them; the deployed database does not have them. |
| PM has **no `upgrade_*.sql`**, and every statement is `CREATE TABLE IF NOT EXISTS`. | **These gaps are structurally unreachable.** `db_import` ignores error `1060` (duplicate column) and every statement is `IF NOT EXISTS`. Re-running `install.sql` on an existing `0_fa_pm_tasks` **cannot add the ten columns**. There is no migration path at all. |

So the dictionary/table disagreement `Schema_Registry_Design.md` §0.4 found is not
a mapping omission — **it is a missing migration mechanism**, which is a strictly
more serious finding and which any derivation design must address first.

A second **[V]** defect, in the same family: `ksf_FA_ExpenseReport/src/ExpenseTypeCatalogue.php:16`

```php
use ksfraser\FrontAccounting\Common\TableDefinition;
$this->tableDef = new TableDefinition('0_ksf_fa_expense_type');
```

The class does not exist anywhere; the real one is
`ksfraser\CommonDb\Dictionary\TableDefinition` with `name()`, not `tableName()`;
and the table name has `0_` **baked in**, which `ksf_FA_Warehouse/sql/install.sql:9-10`
explicitly forbids for runtime SQL. The file is a hand-written fourth copy of
both the schema *and* the repository, and it is broken.

## 0.6 A schema-migration ledger already exists in this tree **[V]**

`ksf_FA_Common/src/Utils/SchemaMigrationRunner.php` (198 lines), and
`ksf_FA_Calendar/sql/install.sql:198-204`:

```sql
CREATE TABLE IF NOT EXISTS `0_ksf_schema_migrations` (
    `module`     VARCHAR(100) NOT NULL,
    `filename`   VARCHAR(200) NOT NULL,
    `checksum`   VARCHAR(64)  NOT NULL DEFAULT '',
    `applied_at` TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`module`, `filename`)
)
```

The runner globs `sql/upgrade_*.sql`, `md5_file()`s each one, diffs against the
ledger, applies what is pending, and re-runs any file whose **checksum changed**
(`:120-172`). Callers: `ksf_FA_Calendar/cal.php` and
`ksf_FA_Common/src/compat.php`. **One module uses it.**

**Its statement splitter is broken, and I proved it by execution [V].**
`:191-197`:

```php
$sql = preg_replace('/--[^\n]*/', '', $sql);
$sql = preg_replace('/\/\*.*?\*\//s', '', $sql);
$parts = explode(';', $sql);
```

Run against `ksf_FA_Calendar/sql/upgrade_1.1.0.sql`:

```
--- fragment 0 (507 bytes): ALTER TABLE `0_fa_cal_entries`     ADD COLUMN IF NOT EXISTS `online_url` …
--- fragment 1 (390 bytes): CREATE TABLE IF NOT EXISTS `0_fa_cal_invitees` (     `id`  …
--- fragment 2 (460 bytes): NULL for ad-hoc',     `name`         VARCHAR(200) …   <-- INVALID
--- fragment 3 (514 bytes): 0 = person invitee',     `invited_at`   DATETIME …    <-- INVALID
```

Fragments 2 and 3 begin *inside* a `COMMENT '…;…'` string and would each be
handed to `db_query()` at `:157`. The cause is not hypothetical: **9 files in
`fa_modules` contain a semicolon inside a quoted `COMMENT`**, including
`ksf_FA_Calendar/sql/install.sql:51,58,151,168`,
`ksf_FA_ImportStagingProcessing`, `ksf_FA_Notes/sql/ksf_notes.sql:16,19`, and
`FA_ProductAttributes/sql/31_product_variation_combos.sql:16`.

**Any derivation or replay layer in this stack must use a quote- and
backslash-aware tokenizer. `explode(';')` is proven insufficient on this tree's
own files, not merely theoretically insufficient.**

## 0.7 What the one live dictionary contains, and what it omits **[V]**

`ksf-common-db`'s `TableDefinition` carries **five** keys per column — `name,
type, null, auto_increment, default` (`src/Dictionary/TableDefinition.php:66-72`)
— and nothing else. Against the SQL in §0.1's census, `install.sql` additionally
carries, per column: `UNSIGNED`, `CHARACTER SET`, `COLLATE` (implied),
`AUTO_INCREMENT` order position, and `COMMENT`. Per table it carries: engine,
charset, collation, `PRIMARY KEY` (possibly composite), `KEY`/`UNIQUE KEY`
(with column lists and order), and `CONSTRAINT … FOREIGN KEY … ON DELETE …`.

None of that reaches the registry today. `writableColumns()` excludes **only**
`auto_increment` (`:122-131`), which is why `ProjectRepository.php:132`
subtracts `project_id` and `created_at` by hand **[V]** — five hand-written
`array_diff` calls across the PM repositories are the current implementation of
a concept the schema should own.

## 0.8 DTOs — the empirical case against (B) **[V]**

54 `*DTO.php` files outside `vendor/`. Findings:

| Finding | Evidence |
|---|---|
| **Zero** DTO classes declare a table binding. | grep for `0_fa_\|0_ksf_\|0_rbac_` across all `*DTO.php`/`*Entity.php` returns only three `Staging*DTO` files, and there it is query text, not an annotation. |
| **Zero** PHP-8 attributes exist to carry metadata. | `grep '^\s*#\['` over `ksf_FA_Calendar`, `ksf_FA_ProjectManagement`, `ksf_FA_RBAC`, `ksf_FA_Square`, `ksf_FA_Woocommerce`, `ksf_CRM`, `ksf_FA_Notes` → **0 hits in every one.** |
| **Reflection cannot see the fields** for a large share of DTOs. | `SchedulingContextDTO::__construct(array $payload)` — **one** parameter, not thirteen. `StagingItemDTO`, `StagingPaymentDTO`, `StagingTransactionDTO`: **no constructor at all.** `ProductDTO`, `OrderDTO`, `CustomerDTO`, `SchedulingContextDTO`: `array $data`/`array $payload`. |
| Coverage of tables is ~20%. | PM has 10 `TableDefinition`s; the PM DTOs are `ProjectDTO` and `TaskDTO`. |
| **Field set ≠ column set, measured.** | See below. |

`SchedulingContextDTO` has 13 `private` props typed only in `@var` **docblocks**.
Comparing its fields to the real `0_fa_cal_entries` columns (§0.4, 44 columns):

| DTO field | is a column? |
|---|---|
| `assigned_to`, `timezone`, `priority` | yes |
| `operation`, `entry_type`, `current_user_id`, `current_time`, `requested_date`, `requested_time`, `default_start`, `default_end`, `default_duration_minutes`, `metadata` | **no — 10 of 13** |
| `id, source, source_id, source_type, title, description, start_date, end_date, all_day, location, direction, …` | **no DTO field — 41 of 44** |

**~23% field overlap.** And `ProjectDTO` — the one DTO that *is* a row shape,
with PHP-7.4 typed properties (`private string $projectId`, `private float
$budget`, …) — is worse:

| | Fields |
|---|---|
| `ProjectDTO` (17, camelCase) | `projectId name description startDate endDate budget customerId projectManager priority status **taskCount completedTaskCount overallProgress files team** createdAt updatedAt inactive` |
| `0_fa_pm_projects` (13, snake_case) | `project_id name description start_date end_date budget customer_id project_manager priority status **project_type_id** created_at updated_at` |

- **5 DTO fields have no column** — all five are *aggregates across tables*
  (`task_count`, `completed_task_count`, `overall_progress`, `files`, `team`).
- **1 column has no DTO field** — `project_type_id`.
- **The naming convention is camelCase vs snake_case**, and no mapper exists.
- The types carry **no** length, nullability, default, key, index or FK. `string`
  is consistent with `VARCHAR(20)` and `TEXT` alike — and PM has both
  (`project_id VARCHAR(20)` vs `description TEXT`).

---

# PART 0bis — The multi-file differential correction

Everything above was the *premise* census. This part is the substance of
Revision 2, and it answers questions 1–5 of the brief directly.

## 0.9 The ordering authority — and it is **not one thing** **[V]**

### 0.9.1 There are three competing authorities, and they disagree

| # | Authority | Where it lives | What it executes |
|---|---|---|---|
| **A1** | `hooks.php` `$updates` array **literal order** | `hooks::update_databases()`, `includes/hooks.inc:31-63` | `db_import()` on `modules/<mod>/sql/<file>` |
| **A2** | `SchemaMigrationRunner::findMigrationFiles()` — **`glob(sql/upgrade_*.sql)` + `sort($files, SORT_STRING)`** | `ksf_FA_Common/src/Utils/SchemaMigrationRunner.php:61-84`, invoked from `ksf_FA_Calendar/cal.php:2383,2393` | `db_query()` per `explode(';')` fragment |
| **A3** | plain directory listing / alphabetical | — | nothing (no code does this, but it is the *default assumption* a naive derivation makes) |

**They are not reconcilable, and A2 has already beaten A1 in production.**
Verified live in §0.12: `0_fa_cal_entries.fork_group_id` **exists** in the
Integration database, and that column is added **only** by
`ksf_FA_Calendar/sql/upgrade_2.1.0.sql` — which **A1 never names** and **A2's
glob always picks up**. A2's own docblock (`findMigrationFiles()`:57) claims it
returns files *"sorted by version"*; it calls `sort($files, SORT_STRING)`, which
is **lexicographic**, so `upgrade_10.0.0.sql` sorts *before* `upgrade_2.0.0.sql`.
The claim is false and the code will break at v10.

### 0.9.2 The A1 manifest has four different syntactic shapes **[V]**

A static extractor that only looks for `$updates = array(…)` finds **19 of 28**
modules and silently misses the rest:

| Shape | Example | Modules affected |
|---|---|---|
| `S1` — `$updates` assigned to a variable | `ksf_FA_Calendar/hooks.php:54` | 19 |
| `S2` — array literal passed **inline** to `update_databases()` | `ksf_FA_Notes/hooks.php:201-204` | 1 (**missed by a `$updates` grep**) |
| `S3` — array built in a loop from a hand-written `$files` list | `FA_ProductAttributes/hooks.php:134-186` | 1 (**built, not literal**) |
| `S4` — **no manifest at all**; `db_import()` called directly | `ksf_FA_Attachments/hooks.php:145-160`, `ksf_FA_Logging/hooks.php:115`, `ksf_FA_API/hooks.php:90` | 3 |

`FA_ProductAttributes` (`S3`) is the most instructive **[V]**:

```php
$files = array( '01_…sql', …, '35_…sql' );      // 35 entries, hand-maintained
foreach ($files as $file) {
    if (file_exists($sqlDir . '/' . $file)) {   // missing → SILENTLY SKIPPED
        if ($file === '30_product_attribute_extras.sql') {
            $updates[$file] = array('product_attribute_values', 'color'); // per-file gate override
        } else {
            $updates[$file] = array($this->module_name);
        }
    }
}
```

Three facts: the list is **hand-maintained and ordered**, missing files are
**silently skipped** (not fatal — same failure mode as §0.1a), and **per-file gate
overrides** are expressible. `ksf_FA_Calendar` adds a **fourth** construct: a
second `$conditional` map whose entries are emitted only if
`company_table_exists()` (`hooks.php:86-92`).

### 0.9.3 The census: manifest vs directory, per module **[V]**

Extracted every `.sql` filename reachable from `$updates` / `update_databases(`
/ `db_import(` in each `hooks.php`, and diffed against `ls sql/*.sql`.

**Class 1 — manifest is an exact, ordered superset of the directory (safe).** 11
modules: `ksf_FA_Assets`, `ksf_FA_CRM` (21/21), `ksf_FA_DataIntegrity`,
`ksf_FA_EmailManager` (6/6), `ksf_FA_ImportStagingProcessing`,
`ksf_FA_QuickBudget`, `ksf_FA_RBAC`, `ksf_FA_Rep_SalesGroups`,
`ksf_FA_SerialNumber`, `ksf_FA_Square`, `ksf_fa_downloader`,
`ksf_FA_SuggestedPurchaseOrder`, `ksf_FA_Upc2Item`, `ksf_FA_Warehouse`,
`ksf_FA_Workflow`, `ksf_payment_destinations`. **Every file wired, every wired
file exists, order preserved.**

**Class 2 — a file is present but never wired (`Orphan`).** The dangerous class,
because it is invisible to FA and invisible to a manifest-driven derivation:

| Module | Orphaned `.sql` files | Consequence |
|---|---|---|
| **`ksf_FA_Calendar`** | **`upgrade_2.1.0.sql`** | **Adds `fa_cal_entries.fork_group_id` + `KEY idx_fork_group`. Column is read by `EventController.php` and `FA_Cal_Module.php` **[V]**. Reachable only by A2 — and §0.12 proves A2 *did* apply it.** |
| **`ksf_FA_HRM`** | **15 of 19** (`fa_departments`, `fa_positions`, `fa_grades`, `fa_contacts_pii`, `fa_contacts_banking`, `fa_contacts_employment`, `fa_dependent_details`, `fa_salary_structure`, `fa_separation_reasons`, `fa_pay_elements`, `ksf_hrm_benefits`, `ksf_hrm_employee_benefits`, `ksf_hrm_leave_balances`, `ksf_hrm_payroll`, `crm_categories`) | **They are not merely unwired — they are unprefixed duplicates.** `fa_departments.sql:7` is `` CREATE TABLE IF NOT EXISTS `hrm_departments` `` with **no `0_`**, while `install.sql` creates `` `0_hrm_departments` ``. If anyone ever wires them, **15 unprefixed tables get created outside the company prefix space.** Treat as delete candidates, not as replay input. |
| `FA_ProductAttributes` | `seed.sql` | Data seed, never applied |
| `ksf_bank_import` | **4 of 5** — only `update.sql` is wired | `add_occurrence_count_to_bi_partners_data.sql` (the only `ADD INDEX`/`DROP INDEX`/`ADD CONSTRAINT` in the whole corpus), `add_pattern_matching_config.sql`, `bi_config_system.sql`, `mantis_2708_uploaded_files.sql` |
| `ksf_FA_Mail` | `preference_values.sql` | |
| 7 modules | `uninstall.sql` | **Correct** — must not be replayed |
| `ksf_FA_Wallet` | `fa_wallet_transactions.sql` | **File contains only the text `SQL for wallet tables`** — a placeholder with zero SQL. FA's framing yields **0 statements** **[V]** |
| `ksf_FA_Notes`, `ksf_FA_Attachments`, `ksf_FA_Contacts`, `ksf_FA_Employee`, `ksf_FA_ExpenseReport`, `ksf_FA_Logging`, `ksf_FA_Users`, `ksf_FA_Woocommerce`, `ksf_FA_API` | see §0.9.4 | |

**Class 3 — a file is wired but does not exist (`Dangling`).** 2 instances:
`ksf_FA_AsteriskPBX` (`'sql/update.sql'` → doubled path, §0.1a) and
`ksf_FA_Customer` (`install.sql`, no `sql/` dir at all) **[V]**. Both **return
success**. See `R-ORD-4`.

### 0.9.4 Four modules have SQL that FA has no mechanism to run **[V]**

`ksf_FA_Contacts`, `ksf_FA_Employee`, `ksf_FA_ExpenseReport` (4 tables) and
`ksf_FA_Users` have `sql/install.sql` **and no `activate_extension()` method at
all** **[V]**. `ksf_FA_Woocommerce` has an `activate_extension()` that does not
touch SQL (`hooks.php:178-184`). Their tables are therefore **never created by
FA at all**. This is the mirror image of §0.5: a derivation that trusts the
directory would invent 7 tables the database does not have, and only the
reconcile step (§5.3) would notice.

### 0.9.5 Verdict and rules **[D]**

> **The `hooks.php` manifest (A1) is authoritative for *ordering*; the directory
> is authoritative for *completeness reporting*; A2 must be replayed as a second,
> independent pass because it is a real second executor.**

Neither alone is sufficient. Concretely:

| Rule | Statement |
|---|---|
| **R-ORD-1** | **Order comes from the manifest, never from the filename.** `ksf_FA_Calendar/hooks.php:54-64` orders `1.1.0 … 2.3.0` and then `retag_contact_types.sql`; `ksf_FA_CRM` interleaves `retag_contact_types.sql` **between** `ksf_crm_option_lists.sql` and `upgrade_2.4.3-1.sql`. Alphabetical order is wrong for both. `ksf_FA_Notes/hooks.php:199-200` states the reason in a comment: *"Notes before links, so the link table is never created ahead of the table it points at."* |
| **R-ORD-2** | **A manifest extractor must handle all four shapes (S1–S4)** plus the `$conditional` second map, or it will silently miss 5 modules. It must be a **PHP-syntax-aware** read (or a `token_get_all()` pass over `hooks.php`), not a regex. |
| **R-ORD-3** | **Replay A1 and A2 as two passes, then take the UNION of their schemas.** Where both touch the same file the mutations are idempotent (all 215 `CREATE TABLE`s are `IF NOT EXISTS`; `db_import` ignores `1050/1060/1061/1062/1091`), so union is safe and **mandatory** — A1-only derivation produces a false `column_undeclared` for `fork_group_id`. |
| **R-ORD-4** | **Every directory file not reached by either pass is a reported finding, never silent.** Three severities: `OrphanNeverApplied` (Calendar `2.1.0`, bank_import ×4, HRM ×15), `NotReplayable` (`uninstall.sql`, `seed.sql`, a comment-only file), `Unreachable` (Class-3 dangling). |
| **R-ORD-5** | **A2's `sort(SORT_STRING)` must be version-compared in the derivation**, not reproduced. Use `version_compare()` on the `upgrade_<v>.sql` stem with a natural-sort tiebreak, and emit `MigrationOrderRisk` where the two orders differ. `upgrade_2.4.3-1.sql` (CRM, EmailManager) is not a parseable version and must sort last by filename. |

## 0.10 The replay accumulator — specified **[D]**, with corpus evidence **[V]**

### 0.10.1 The state that must be carried across files

```
SchemaAccumulator {
    tables : ordered map<logical_table_name, TableState>
    //   logical name = the name with the literal `0_` stripped (§0.2 :337)
    //   ORDERED, because AFTER <col> is positional (§0.3, 27 uses)
    warnings : list<Finding>          // orphans, dangling, non-whitelisted lines
    provenance : map<entity, file:line>  // which file last mutated each column
}

TableState {
    engine, charset, collation, comment
    columns : ordered map<column_name, ColumnState>
    primaryKey : list<column_name>          // composite: 214 PKs, several composite
    uniqueKeys : map<name, list<column_name>>
    indexes    : map<name, list<(column_name, direction)>>
    foreignKeys : list<{name, columns, refTable, refColumns, onDelete, onUpdate}>
    owner : 'module' | 'core' | 'foreign'    // see §0.10.4
}

ColumnState {
    name, ordinal, type, length, scale, unsigned, zerofill
    nullable : bool
    default  : {kind: 'none'|'literal'|'expression', value}
    autoIncrement : bool
    comment  : string | null
    enumValues : list<string> | null          // 30+ real ENUMs
    onUpdate : string | null                 // ON UPDATE CURRENT_TIMESTAMP
    charset, collation
}
```

Why each field exists, and whether the corpus actually needs it **[V]**:

| Field | In corpus? | Evidence |
|---|---|---|
| `ordinal` | **yes, load-bearing** | `AFTER \`col\`` ×27 across 11 files; Calendar positions `online_url AFTER location`, `phone_number AFTER online_url`, `send_invites AFTER phone_number` in **one** statement (`upgrade_1.1.0.sql:9-17`) |
| `type/length/scale` | yes | `DECIMAL(15,2)`, `DECIMAL(5,4)`, `VARCHAR(500)`, `MEDIUMTEXT`, `JSON`, `LONGTEXT` |
| `unsigned` | yes | `INT(11) UNSIGNED` (RBAC) |
| `nullable` | yes, **two encodings** | implicit (`budget DECIMAL(15,2) DEFAULT 0.00`) and explicit (`end_date DATE NULL DEFAULT NULL`). **Absence of `NOT NULL` means nullable** |
| `default` | yes, **three classes** | numeric `0`/`0.00`; quoted `'Medium'`/`'pending'`/`'UTC'`/`'ad_hoc'`; **expression** `CURRENT_TIMESTAMP` + `ON UPDATE CURRENT_TIMESTAMP` |
| `comment` | yes, **40+ files** | doubles as the de-facto enum documentation (`COMMENT 'pending, accepted, declined, tentative'`) — see §2.4 |
| `enumValues` | yes, 30+ | `ENUM('inbound','outbound')`, `ENUM('view','edit')`, `ENUM('open','invitees_only','owner_only')` |
| `composite PK` | yes | `PRIMARY KEY (\`team_id\`,\`user_id\`,\`inactive\`)` (RBAC); `ksf_schema_migrations` uses `(module, filename)` |
| `index direction` | **yes — 1 instance** | `bank_import/…:27 ADD INDEX \`idx_occurrence_count\` (\`occurrence_count\` DESC)` |
| `foreignKeys` | yes, 39 | `ON DELETE CASCADE` / `SET NULL` / `RESTRICT` in use |
| `CHECK` | **no** | zero in corpus |

### 0.10.2 How each statement mutates the accumulator

| Statement | Corpus count **[V]** | Mutation |
|---|---|---|
| `CREATE TABLE [IF NOT EXISTS]` | 215 (all `IF NOT EXISTS`) | If absent → create with the full state above. **If present → NO-OP.** *This is the single most important rule in the document*: `db_import` suppresses error `1050`, so a second `CREATE TABLE IF NOT EXISTS` against an existing table changes **nothing**. A derivation that "helpfully" merged the new definition would describe a table MySQL never altered. **This rule is exactly why PM's ten missing columns are unreachable (§0.5, §0.12).** |
| `ALTER TABLE … ADD COLUMN [IF NOT EXISTS]` | **32** | Insert at `AFTER <col>` / `FIRST` / append. With `IF NOT EXISTS` → no-op if present; without → error `1060`, suppressed, **also a no-op**. Both paths converge on idempotence, so the rule is simply *"add if absent"*. **Multiple actions in one statement (`ADD c1 …, ADD c2 …, ADD INDEX …`) must all apply** — Calendar `upgrade_1.4.0.sql:89` has three `ADD INDEX` in one statement, `upgrade_1.1.0.sql:9-17` has three `ADD COLUMN`. |
| `ALTER TABLE … MODIFY <col> <def>` | **15** | **Overwrite** the whole `ColumnState` (`db_import` does not suppress the error, so this always applies). 12 of the 15 target **FA core tables** (`stock_master`, `item_codes`, `loc_stock`, `stock_moves`, `prices`, `purch_data`, `sales_order_details`, `supp_invoice_items`, `debtor_trans_details`, `workorders`, `wo_requirements`, `grn_items`, `purch_order_details`, `bom`) — see §0.10.4 |
| `ALTER TABLE … ADD INDEX [IF NOT EXISTS] / ADD KEY` | **11** | Add to `indexes`. `1061` suppressed ⇒ idempotent |
| `ALTER TABLE … ADD CONSTRAINT … UNIQUE(…)` | **2** | Add to `uniqueKeys` (`1061` suppressed ⇒ idempotent) |
| `ALTER TABLE … DROP INDEX` | **1** | Remove from `indexes`. `1091` suppressed ⇒ idempotent |
| `DROP TABLE IF EXISTS` | 18, **all unwired** | Remove the table, then re-create per execution order (§0.3a) |
| `INSERT` / `INSERT IGNORE` / `UPDATE` / `DELETE` / `SELECT` | 54 | **No schema mutation.** Must be *skipped*, not mis-parsed. (`INSERT` is the only place some enum members appear outside `ENUM()` — §2.4.) |
| `SET NAMES` | 0 | charset only |
| **`CREATE INDEX` / `CREATE VIEW` / `CREATE PROCEDURE`** | **0** | Not in corpus. Under `R-WL-1` they **would** execute; the accumulator must handle `CREATE [UNIQUE] INDEX` at minimum, because it is the obvious future way to add an index. |
| **`DROP COLUMN`, `RENAME`, `CHANGE`, `TRUNCATE`, `CONVERT TO`** | **0** | Specified in §2.5 as no-ops-on-accumulator + warning, **except** `DROP COLUMN`/`RENAME COLUMN`, which the accumulator *must* implement before any module uses them. **They are out of v1 scope because the corpus proves they are unused — not because they are hard.** |
| any line matching no whitelist prefix and not a continuation | **0** | **Warning, not a parse failure** — that is a *real defect report* about the module, not about the parser |

### 0.10.3 Gate semantics must be modelled, because they decide whether a file runs **[D]**

The accumulator is not a naive "apply every statement in every file". For each
manifest entry, `check_table()` decides whether `db_import()` is invoked at all
(`hooks.inc:44-51`; `check_table()` at `maintenance_db.inc:948-973`):

| `check_table()` | Meaning | Replay action |
|---|---|---|
| `1` — table absent | gate names a table that does not exist | run the file |
| `2` — table present, field absent | | run the file |
| `3` — table + field present, `$properties` differs | | run the file |
| `0` — satisfied | | **skip the file entirely** |

**On a fresh virtual database every entry returns `1`, so a fresh replay applies
every file in manifest order.** That is the correct and simplest definition, and
it is what makes "declared" == "live" by construction. But the derivation must
**also** emit, for each entry, the gate's *satisfaction predicate*, because §0.1
shows **11 of the entries in this tree have gates that can never be satisfied** —
which is precisely the defect that makes PM's schema re-run on every activation
and drift silently.

### 0.10.4 The ownership flag — a module's replay produces **tables it does not own** **[V]**

`FA_ProductAttributes/sql/32_widen_stock_id.sql` is **15 `MODIFY` statements
against 14 FA core tables** (`0_stock_master`, `0_item_codes`, `0_loc_stock`,
`0_stock_moves`, `0_prices`, `0_purch_data`, `0_sales_order_details`,
`0_supp_invoice_items`, `0_debtor_trans_details`, `0_workorders`,
`0_wo_requirements`, `0_grn_items`, `0_purch_order_details`, `0_bom`), widening
`stock_id` from `VARCHAR(20)`-class to `VARCHAR(32) NOT NULL`.

So a naive replay of ProductAttributes' 35-file manifest yields **14 core tables
in the output**, which would make the registry claim ProductAttributes owns them,
and would make `uninstall`/ownership routing wrong. **The accumulator therefore
carries `owner`**, set by a simple, declared rule **[D]**:

| Rule | Meaning |
|---|---|
| `R-OWN-1` | A table **first created** by this module's replay → `owner = 'module'`. |
| `R-OWN-2` | A table **only referenced** by an `ALTER` (never `CREATE`d in the replay) → `owner = 'core'`. It is emitted as a **dependency edge, not a schema entry**, and is not offered to the registry for ACL or workflow. |
| `R-OWN-3` | This is a *narrow* carve-out that does **not** reopen §A.2 item 6 of the appendix: FA core tables that no module `.sql` mentions remain entirely outside the derivation. Only tables a module demonstrably mutates are surfaced. |

## 0.11 Multi-statement framing — **reuse FA's, do not write a new one** **[V]**

### 0.11.1 The prior finding, restated

`SchemaMigrationRunner::splitSqlStatements()` (`:191-197`) is:

```php
$sql = preg_replace('/--[^\n]*/', '', $sql);
$sql = preg_replace('/\/\*.*?\*\//s', '', $sql);
$parts = explode(';', $sql);
```

Run against `ksf_FA_Calendar/sql/upgrade_1.1.0.sql` it yields **4** fragments, of
which **2 begin mid-`COMMENT` string** and are invalid SQL. Reproduced **[V]**.

### 0.11.2 But FA's *own* framing is **correct on that exact file** **[V]**

The design implication of Revision 1 was "therefore we must write a quote- and
backslash-aware tokenizer". **That conclusion is wrong, and the evidence is
adverse.** FA's framing — line-oriented, terminate when the *trimmed line* ends
with `;` — was implemented against all 148 files. Result **[V]**:

| File | FA framing | `explode(';')` (non-empty) |
|---|---|---|
| `ksf_FA_Calendar/sql/upgrade_1.1.0.sql` | **2 statements, both valid** | 4 (2 invalid) |
| `ksf_FA_Calendar/sql/install.sql` | **6** | 10 |
| `ksf_FA_Calendar/sql/upgrade_1.5.0.sql` | **2** | 6 |
| `ksf_FA_Calendar/sql/upgrade_1.1.0.sql` stmt 0 | `ALTER TABLE \`1_fa_cal_entries\` ADD COLUMN … AFTER \`phone_number\`` — **complete and correct** | — |

**FA's splitter is not merely adequate — it is strictly better than
`explode(';')` on every file where the two differ, because it requires the `;`
to be at end-of-line, which a `;` inside a `COMMENT` almost never is.** Across
the corpus the two agree on **139 of 148 files** and FA wins on all 9
disagreements. Corpus total: **333 statements**.

This is a genuine "do not reimplement what FA already solves" result, and it
reverses an `[UNVERIFIED]`-flavoured recommendation in Revision 1.

### 0.11.3 So: extract, don't write **[D]**

`db_import()`'s framing loop is `maintenance_db.inc:328-374` — **~40 lines, no
dependencies beyond `file()` and `str_replace()`, all state in four local
variables** (`$query_table`, `$delimiter`, `$skip`, and the four accumulator
arrays). It is mechanically extractable as
`FaSqlFramer::frame(array $lines, string $tbpref): array{buckets, statements, lineNos}`.

**But two facts must be carried with it, because they are easy to lose:**

1. **`DELIMITER` support exists and is unused.** `:346-350` parses a `DELIMITER`
   line into `$delimiter`, and `:480` restores it. **Zero files in the corpus use
   `DELIMITER` [V]** — so a naive extraction that drops the branch loses nothing
   *today* and everything the day someone adds a trigger or procedure. Keep the
   branch; add a fixture test that pins the current zero.
2. **Line numbers are part of the error contract.** `db_import` reports
   *"SQL script execution failed in line %d"* using the `$line_no+1` captured at
   statement start (`:349`, `:484`). The derivation must carry the same
   provenance or its findings will not be actionable.

**The three modules that bypass FA entirely must be reported, not silently
skipped** **[V]**: `ksf_FA_Attachments/hooks.php:157`,
`ksf_FA_Logging/hooks.php:~120` and `ksf_FA_API/hooks.php:~95` all
`file_get_contents()` their own `install.sql` and run `explode(';')` —
**i.e. three modules are running the proven-broken splitter in production
today**, outside both A1 and A2. They currently survive because none of their
`install.sql` files contains a `;` inside a quoted string **[V]** — verified, all
three clean. That is luck, and it is one file edit away from breaking.

**Unresolved [UNVERIFIED]:** FA's framing is *line*-based, so it will still
mis-frame a statement whose `COMMENT` string happens to end a line with a `;`.
No such file exists in the corpus **[V]**. Whether MySQL would accept the result
was not tested.

## 0.12 Live verification against the Integration database **[V]**

Revision 1 left the PM gap as *"inferences from files, not observations"*
(§A.2 item 2). Revision 2 queried `ksf_fa` on `ksfii_app-mariadb`
(**MariaDB 10.11.14**, schema `ksf_fa`, company prefix `0_`) **[V]**:

| Query | Result | Reading |
|---|---|---|
| tables `LIKE '%pm_%'` | **9** PM tables: `projects, tasks, assignments, project_types, activity_log, files, task_progress, project_sales_orders, project_revenue` | matches deployed `install.sql` exactly |
| `0_fa_pm_task_dependencies` exists? | **0 rows** | **v0 blocker CONFIRMED — the table does not exist** |
| `0_fa_pm_tasks` has any of the 10 CPM columns? | **0 rows** | **v0 blocker CONFIRMED — none of `is_milestone, is_constrained, constraint_type, constraint_date, es, ef, ls, lf, slack, is_critical` exists** |
| `0_fa_cal_entries` columns `fork_group_id, closed_at, delta, online_url, needs_review, recurrence_count` | **all 6 present** | `closed_at`/`delta` via A1 upgrades; **`fork_group_id` via A2 only** |

**Two conclusions, one of them load-bearing for the design:**

1. **The PM gap is real, live, and structurally unreachable — confirmed
   independently, not inferred.** Deployed `install.sql` has **9 `CREATE TABLE`,
   0 `ALTER`**, every statement is `CREATE TABLE IF NOT EXISTS`, `db_import`
   suppresses `1050`/`1060`, **and `find -name 'upgrade*'` returns nothing in
   either the deployed module or the dev tree** **[V]**. There is no code path by
   which those 11 objects can ever be created. `TaskDependencyRepository` queries
   a table that does not exist. **This is v0 and it is a prerequisite.**
2. **`fork_group_id` proves the ordering-authority question is not academic.**
   That column is defined *only* in the orphaned `upgrade_2.1.0.sql`. `hooks.php`
   never names it. It exists in the database. Therefore **A2
   (`SchemaMigrationRunner`) has already diverged from A1 in production**, and a
   derivation built on A1 alone would report `fork_group_id` as
   `column_undeclared` — a false drift report on the very first run.
   **`R-ORD-3` (replay both passes, union the result) is not a nicety; it is the
   difference between a working reconciliation and a permanently red one.**

**Not verified:** the rootless `ksf-fa` / `ksf_fa` pod (8080) was not reachable in
this session — only the rootful `ksfii_app` stack answered. The UAT box was not
queried. Per §6.3 item 3, drift is per-company and per-pod, so the other stacks
may differ.

---

> ## **(D), and specifically: A″ + C, where A″ = MULTI-FILE DIFFERENTIAL REPLAY of both ordering authorities, and C is reduced to an overlay of POLICY only. (B) is rejected outright.**
>
> *(Revision 2 renamed A′ → A″. Revision 1's A′ already meant "replay the
> manifest" in intent, but its write-up in Part 2 still described **parsing one
> file**. The distinction is the whole point of this revision — see §1.1.)*

| Option | Verdict | One-line reason |
|---|---|---|
| **(A) parse `sql/install.sql`** | **Rejected as stated; salvaged as A″.** | 23 of 42 modules have no `install.sql` **[V]**; two create tables in PHP **[V]**; **upgrade files are differential `ALTER`s that `install.sql` cannot express** (§0.4, §0.10.2); **three ordering authorities disagree and one has already won in production** (§0.9.1, §0.12); PM has no migration path at all **[V]**. |
| **(B) reflect over blank DTOs** | **Rejected.** | 10 of 13 reflected fields of one DTO are not columns; 1 of 13 columns has no field; 0 DTOs bind to a table; 0 attributes exist; 20% table coverage **[V]**. |
| **(C) a per-module schema config** | **Accepted, but demoted from *source* to *overlay*.** | SQL cannot express labels, writability, sensitivity or relationship semantics (§P3); but a config that also restates types/lengths/nullability is a **fifth copy**. |
| **(D) combination** | **Adopted** | A″ is the only source that can be *provably* reconciled with the live database; C supplies what SQL cannot; B is not a source at all. |

### 1.1 Why A″ (multi-file differential replay) and not A (single-file parse)

The distinction is not pedantic — it is the difference between a design that can
be verified and one that cannot.

- **A (`install.sql`)** is a *file*. It has no notion of which statements FA will
  run, in what order, under what condition. Calendar would be derived wrong
  (§0.4). PM would be derived wrong (§0.5). Nine tables would be invisible (§0.3).
- **A is also *categorically* incapable**, which is the point Revision 2 adds.
  Upgrade files are **differential**: `ALTER TABLE … ADD COLUMN`,
  `MODIFY`, `ADD INDEX`, `DROP INDEX`, `ADD CONSTRAINT … UNIQUE`
  (§0.3, 46 statements). A parser reading only `install.sql` has **no way to
  know an `ALTER` exists**, so every differential statement is invisible by
  construction — not by oversight. Conversely a parser reading only an upgrade
  file has no table to attach it to. **Neither file is a schema; only the
  sequence is.**
- **A″ (replay of both ordering authorities)** is a *function of the same inputs
  FA itself uses*: manifest order, `check_table()` gate semantics, `db_import()`'s
  11-prefix whitelist, its drop→create→data execution order, the textual
  `0_`→`TB_PREF` rule, its ignore-list of errors
  `1022/1050/1060/1061/1062/1091`, and — per §0.9 — **both** A1 (`$updates`)
  **and** A2 (`SchemaMigrationRunner`'s glob). A″ and FA consume the same inputs,
  so a derivation built on A″ cannot disagree with what FA built — *by
  construction rather than by discipline*. §0.12 shows this is not theoretical:
  getting it wrong produces a false drift report on day one.

The gate is why A″ is tractable. `check_table()` returns `0` when a
statement would be a no-op. **Replaying the manifest against a virtual empty
database in the manifest's order, and treating each statement as executed iff
`check_table()` would have run it, reproduces the database FA builds on a fresh
company** — the one case where "declared" and "live" are guaranteed equal.

### 1.1a Replay order, and what happens when an upgrade file fails mid-way **[D]**

**Replay order** (`@FR-SD-001-008`):

```
A″(module) =
    replay(A1 manifest, in literal order, each file framed by FaSqlFramer)
  ∪ replay(A2 glob, in version_compare order,  each file framed by FaSqlFramer)
  then apply R-OWN-1/2 to split 'module' from 'core' tables
```

Within a **file**, statements execute in FA's own bucket order — **drop, then
create/alter, then data** — regardless of textual position (§0.2 `:429-467`).
No corpus file mixes the buckets **[V]**, so this is currently unobservable, but
it is implemented because it is real.

Across **files**, order is A1's literal order then A2's version order. The union
is safe because every mutation in the corpus is idempotent **[V]**: 215/215
`CREATE TABLE`s are `IF NOT EXISTS`, `ADD COLUMN`/`ADD INDEX` without
`IF NOT EXISTS` fail with a suppressed `1060`/`1061`, and `DROP INDEX` fails with
a suppressed `1091`. `MODIFY` is **not** idempotent in the sense of being
skipped — it always applies — which is why last-writer-wins is the rule and why
A2 must never re-apply a `MODIFY` that A1 also contains (none do **[V]**).

**Failure semantics — an upgrade file that fails part-way:**

Read from `db_import()` and `update_databases()` **[V]**:

| Fact | Evidence |
|---|---|
| DDL is **not** transactional. There is no `BEGIN`/`ROLLBACK` anywhere in the path. | `maintenance_db.inc:429-467` — statements are executed in bare loops |
| `db_import` executes statements until one fails, **collects all errors, then reports only the first** and `return false`. Statements after the failure are **not** attempted. | `:429-467`, `:483-490` |
| `update_databases` then does `$result &= $ok; if (!$result) break;` — **the whole activation aborts and every remaining manifest entry is skipped.** | `hooks.inc:52-59` |
| The partially-applied file is **left applied**. No rollback, no marker. | — |

**Therefore [D]:**

- **R-FAIL-1 — the derivation must be able to report a *partial* file.** The
  accumulator is a total function only if every statement succeeds; a real
  activation can stop halfway. A `MigrationPartial` finding must carry the
  statement index that would have failed next, so the drift report can say
  *"file N applied statements 1–k, statement k+1 is the one your database is
  missing"* rather than the useless "activation failed".
- **R-FAIL-2 — retry is self-healing, and the derivation must model that.**
  On the next activation the gate is still unsatisfied, the file re-runs from the
  top, and every already-applied prefix statement now fails with a **suppressed**
  `1050/1060/1061/1091` and is skipped by `db_import`; the remaining statements
  execute. **So a mid-way failure converges on retry** — provided the
  suppressed errors are genuinely idempotent. `MODIFY` is safe (re-applying the
  same definition is a no-op in effect). A non-idempotent statement inside a
  file would break this, and the derivation should **flag any file containing
  one** (`INSERT` without `IGNORE`/`ON DUPLICATE KEY` inside a DDL file is the
  realistic instance; the corpus has `INSERT IGNORE` and `ON DUPLICATE KEY`
  **[V]**, so this is currently clean).
- **R-FAIL-3 — the derived schema is the schema of a *successful* activation.**
  That is the correct and honest target. When reconcile finds a live database
  that is a *failed* activation's partial result, that is not drift — it is a
  **failed activation**, and it must be reported as such rather than as a set of
  `column_missing` warnings, because the fix is "re-run activation", not
  "reconcile".

### 1.2 Why B is rejected, and specifically why the "blank instance" part fails

The user's proposal is *module returns a list of DTO classes; engine requests a
blank instance and reflects its fields*. Three independent failures, all **[V]**:

1. **There is nothing to reflect.** The codebase's DTOs are **hook-payload**
   DTOs, not row DTOs. `SchedulingContextDTO` is *"passed between Calendar and
   hook responders"* — a command object. `Staging*DTO` are import staging rows.
   No DTO in the tree is bound to a table.
2. **The reflection surface does not exist.** Zero PHP-8 attributes. A large
   share take `array $payload` or have **no constructor**. PHP-7.3/7.4 reflection
   therefore exposes **one array parameter**, or nothing. The only readable
   metadata is `@var` docblock text, which requires a PHPDoc parser and which
   carries `string` — compatible with `VARCHAR(20)` and `TEXT` alike.
3. **Even where reflection works, it produces the wrong answer.** On the one DTO
   that *is* a row shape, `ProjectDTO`, 5 of 17 fields do not exist in the table
   and 1 of 13 columns is missing (§0.8). Producing a "schema" from that is not a
   slightly-wrong schema — it is a schema for a **table that does not exist**.

**But the DTO idea is not worthless, and the middle path in the brief is correct.**
See §P4.3.

---

# PART 2 — What the replay engine (A″) yields

> **Revised in Revision 2.** This part was titled *"What parsing `install.sql`
> actually yields"*, which described the wrong unit. It is now scoped to the
> **accumulator's output** (state: §0.10.1; mutation rules: §0.10.2). The
> per-field yieldability tables below are **unchanged in substance** — the fields
> replay can recover are the fields SQL can state — but they are now produced by
> a **multi-file differential replay** of 333 statements, not by a single-file
> parse of one of 215 `CREATE TABLE`s.

Field-by-field, against the real files. "Yielded" means *reliably recoverable by
a quote-aware tokenizer replaying both ordering authorities*.

## 2.1 Per column

| Attribute | Yielded? | Evidence / caveat |
|---|---|---|
| **name** | **Yes, exactly** | Backtick-quoted identifiers throughout. |
| **type** | **Yes** | `VARCHAR`, `TEXT`, `INT`, `TINYINT`, `DECIMAL`, `DATE`, `DATETIME`, `TIMESTAMP`, `JSON`, `ENUM`, `BLOB`. |
| **length** | **Yes** | `(20)`, `(15,2)` — second arg is scale, not length. |
| **scale** | **Yes** | `DECIMAL(15,2)` → 15/2 **[V]** throughout PM. |
| **UNSIGNED** | **Yes** | `INT(11) UNSIGNED` in RBAC (`install.sql:36,61,89`) **[V]**. |
| **nullable** | **Yes — and note the encoding differs by module.** | Two idioms both in use: `budget DECIMAL(15,2) DEFAULT 0.00` (nullable, implied by no `NOT NULL`) and `end_date DATE NULL DEFAULT NULL` / `role VARCHAR(32) NULL DEFAULT NULL` (explicit `NULL`). PM uses the implicit form; RBAC and Warehouse use the explicit one **[V]**. A parser must treat **absence of `NOT NULL` as nullable** — the same inversion `Schema_Registry_Design.md` §B.2 flags as a bug surface. |
| **default** | **Yes, with three literal classes** | (a) numeric: `DEFAULT 0`, `DEFAULT 0.00`; (b) quoted: `DEFAULT 'Medium'`, `DEFAULT 'Planning'`, `DEFAULT 'Team Member'`, `DEFAULT 'application/octet-stream'`; (c) **function**: `DEFAULT CURRENT_TIMESTAMP`, and `ON UPDATE CURRENT_TIMESTAMP` **[V]**. `TableDefinition`'s five-key shape has **no slot for (c)** — `CURRENT_TIMESTAMP` must not be stored as the string `"CURRENT_TIMESTAMP"` and compared as a value. |
| **AUTO_INCREMENT** | **Yes** | `id INT(11) NOT NULL AUTO_INCREMENT` **[V]**. |
| **`COMMENT`** | **Yes, but see the caveat.** | Present in 40+ files **[V]**. Used as the **de facto enum documentation**: `COMMENT 'work_based, status_based'`, `COMMENT 'fa_user, crm_contact, resource, ad_hoc'`, `COMMENT 'member | owner'`, `COMMENT 'grant | revoke | elevate | …'` **[V]**. This is the single most useful thing SQL parsing buys and it is **prose, not data** — see §2.4. |
| **explicit `ENUM(...)`** | **Yes** | 30+ distinct `ENUM('a','b')` declarations across the tree **[V]**. |
| **column position** | **Yes**, and only from `ALTER … AFTER \`x\`` | Positional `ALTER` is used **[V]**. |
| **sensitivity / ACL class** | **No.** | Never present in any form. §0.3 `ACL_Two_Approaches.md` §6.2: *"there is no column-protection inventory."* |
| **label / description** | **No** — only the raw `COMMENT`, which is developer prose, frequently an FK hint, and already known to be wrong in at least one place (`0_rbac_team_members`' FK comment, per `Schema_Registry_Design.md` §B.6). | |

## 2.2 Per table

| Attribute | Yielded? | Caveat |
|---|---|---|
| **table name** | Yes | `0_` prefixed; A″ must strip `0_` and record the logical name, because `FaDbAdapter` prefixes bare names at runtime **[V — §0.5, Warehouse `install.sql:9-10`]**. |
| **primary key** | **Yes — and it is sometimes composite** | `PRIMARY KEY (\`project_id\`, \`employee_id\`)` (PM assignments), `PRIMARY KEY (\`team_id\`,\`user_id\`,\`inactive\`)` (RBAC UNIQUE) **[V]**. `TableDefinition` has **no composite-PK support today** — one field, one name. |
| **UNIQUE constraints** | Yes | `UNIQUE KEY \`idx_task\` (\`task_id\`)` **[V]**. |
| **indexes** | Yes — name + column list + order | `KEY \`idx_entity\` (\`entity_type\`, \`entity_id\`)` **[V]**. |
| **engine / charset / collation** | Yes | `ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci` **[V]**. |
| **table `COMMENT`** | Yes where present | |

## 2.3 Relationships — the answer is "both, inconsistently" **[V]**

| Style | Where | Example |
|---|---|---|
| **Real `FOREIGN KEY` constraint** | 23 files. PM, Calendar, CRM, HRM, Notes, StockReservations, SuggestedPurchaseOrder, PurchaseOrderTracking, ManufacturerConsolidation, Upc2Item, bank_import | `CONSTRAINT \`fk_task_project\` FOREIGN KEY (\`project_id\`) REFERENCES \`0_fa_pm_projects\` (\`project_id\`) ON DELETE CASCADE` |
| **Comment-only "FK"** | RBAC, Warehouse, Attachments, Notes, Downloader, Logging | `` `owner_id` VARCHAR(64) NULL DEFAULT NULL COMMENT 'FK to 0_users.id or synthetic ID…' ``; `` `team_id` VARCHAR(64) NOT NULL COMMENT 'FK to 0_rbac_teams.id' `` |

So: **relationships appear, but only about half the time as machine-readable
constraints**, and the two halves cannot be merged without a policy for
"unparseable comment." Note also that the `REFERENCES` target is written as a
`0_`-prefixed name and is therefore **rewritten by the textual substitution** —
A″ must un-prefix it the same way it un-prefixes the table, or every FK points at
a non-existent company-0 table.

**Practical rule [D]: a real `FOREIGN KEY` yields a relationship edge
automatically; a comment-only FK yields a *candidate* edge that the module must
confirm in its overlay.** Never auto-promote a comment.

## 2.4 The enum problem, stated precisely

Two different mechanisms exist for the same concept, and they disagree **[V]**:

- **PM** stores `priority`, `status`, `dependency_type`, `progress_mode` as
  `VARCHAR` with a **hardcoded PHP default** (`'Medium'`, `'Planning'`, `'FS'`,
  `'work_based'`) and, at most, a prose `COMMENT` listing the members.
- **HRM / Assets / ManufacturerConsolidation / ImportStaging** use a real
  `ENUM('…')`, which A″ can read exactly.

`Workflow_Engine_Design.md` §D.2 calls a dropdown of declared enum values *"the
highest-leverage UI decision in the whole document."* A″ delivers it **only for
the ENUM half.** For the VARCHAR half, the members are recoverable only by
parsing a `COMMENT` string with an ad-hoc `a, b | c` grammar, or by finding the
hardcoded PHP default in the module's source — neither of which is derivation, and
both of which are fragile.

**Therefore: `enumValues` is a POLICY-overlay field, not a derived field.**
Where an `ENUM` exists, the overlay need not restate it. Where it does not, the
module must declare the members.

## 2.5 Statement classification — `R-WL-1` **[V] for the rule, [D] for the design**

**Corrected in Revision 2.** The whitelist is a set of **11 case-insensitive
prefixes** matched against the start of the trimmed line, and the `create` entry
is the bare string `'create'` — so **every** `CREATE …` statement matches
(§0.2a). The classification rule is therefore:

| Line matches prefix | Bucket | Replay treatment |
|---|---|---|
| `create` | `table_queries` | **schema-bearing.** `CREATE TABLE` → §0.10.2. `CREATE [UNIQUE] INDEX` → index set. `CREATE VIEW`/`PROCEDURE`/`TRIGGER` → **zero occurrences **[V]**; if present, emit `UnsupportedSchemaObject` rather than guess. |
| `alter table` | `table_queries` | **schema-bearing** — the differential vocabulary (§0.10.2) |
| `delimiter` | — | sets `$delimiter`; **zero occurrences **[V]**; keep the branch (§0.11.3) |
| `insert`, `update`, `select`, `delete` | `data_queries` | **no schema mutation** — skipped, not mis-parsed. (`INSERT`/`INSERT IGNORE`/`INSERT … ON DUPLICATE KEY` is where some enum members appear outside `ENUM()`, see §2.4.) |
| `set names` | — | connection charset only |
| `drop table if exists`, `drop function if exists`, `drop trigger if exists` | `drop_queries` | table/function removal; **executed before all creates in the same file** (§0.2) |
| **anything else** | **discarded by FA** | **warn loudly.** `RENAME TABLE`, `DROP INDEX`, `DROP VIEW`, `DROP COLUMN`, `TRUNCATE`, `CREATE OR REPLACE` is *not* here (it matches `create`) — **all zero occurrences in the corpus [V]**. A warning here is a *real defect report about the module*, not a parse failure. |

**The two out-of-v1-scope cases are specified so a future file cannot silently
break the replay [D]:**

- `DROP COLUMN` → remove from `columns`; if it is in the `primaryKey`, clear the
  PK; drop it from any `indexes`/`uniqueKeys`/`foreignKeys` entry.
- `RENAME TABLE a TO b` / `RENAME COLUMN a TO b` → key rename, **preserving
  ordinal and all state**, and rewriting inbound FK targets.
- `ALTER TABLE … CHANGE old new <def>` → a rename **plus** a redefinition, i.e.
  a `RENAME COLUMN` and a `MODIFY` in one step.

These are **out of v1 scope because the corpus proves they are unused** — zero
occurrences, swept **[V]** — **not because they are difficult.** They are the
first thing to implement the day a module needs them.

## 2.6 Statement framing — **reuse `db_import`'s, do not write a new one** **[V]**

**This reverses Revision 1's recommendation.** Revision 1 proved (correctly)
that `explode(';')` breaks on `upgrade_1.1.0.sql`, and concluded that a quote-
and backslash-aware tokenizer was therefore required. §0.11.2 tested the
alternative: **FA's own line-based framing is correct on that exact file** and
strictly better on the corpus.

| | `explode(';')` | FA's framing (`maintenance_db.inc:328-374`) |
|---|---|---|
| `upgrade_1.1.0.sql` | 4 fragments, **2 invalid** | **2 statements, both valid** |
| corpus (148 files) | 499 non-empty fragments | **333 statements** |
| agrees on | — | **139 / 148 files**; **FA wins all 9 disagreements** |
| needs a full SQL tokenizer | yes | **no** |
| handles `DELIMITER` | no | **yes** (`:346-350`) |
| matches what actually ran | no | **yes, by construction** |

**Decision [D]: extract `db_import`'s framing loop verbatim** as
`FaSqlFramer::frame()` (`~40` lines, no dependencies beyond `file()` and
`str_replace()`, all state in four locals), preserve the `DELIMITER` branch, and
carry the `$line_no+1` provenance because `db_import`'s error contract is
*"SQL script execution failed in line %d"* (`:484`).

**The residual risk is stated rather than dismissed [UNVERIFIED]:** FA's framing
is *line*-based, so a `COMMENT` string that itself ends a line with a `;` would
still be mis-framed — and so would MySQL executing the result. **No such file
exists in the corpus **[V]**, and I did not test what MySQL does with such a
statement. Matching FA exactly remains the right call regardless: **where A″ and
FA disagree about where a statement ends, FA wins, because FA is what built the
database.**

**Separately — three modules bypass both authorities and must be reported [V]:**
`ksf_FA_Attachments`, `ksf_FA_Logging` and `ksf_FA_API` each
`file_get_contents()` their own `install.sql` and run `explode(';')` in
`activate_extension()` — i.e. **the proven-broken splitter is running in
production today, in three modules.** All three files are currently clean of
`;`-inside-string **[V]**, so nothing is broken *yet*. That is luck, not design,
and it is one edit away from an incident.

---

# PART 3 — What SQL cannot express, and where the overlay lives

## 3.1 The gap table

| Need | Consumer | In SQL? | In `information_schema`? |
|---|---|---|---|
| column name, type, length, scale, unsigned | all | **yes** | yes |
| nullable, default (incl. expression) | workflow coercion | **yes** | yes (default only as text) |
| primary key, unique, indexes | builder | **yes** | yes |
| `AUTO_INCREMENT` | builder | **yes** | yes |
| relationship edge | workflow `related_count` | **partly** (§2.3) | yes, but only for *real* constraints |
| **display label** | workflow UI picker | **no** | **no** |
| **description / help text** | UI, tooltips | **no** (only free-text `COMMENT`, already unreliable) | **no** |
| **user-writable vs derived** | workflow actions (`set_field` vs `modify_field`) | **no** | **no** |
| **sensitivity class (ACL)** | column ACL, workflow UI filtering | **no** | **no** |
| **format hint** (currency/percent/date) | `modify_field` previews, `round(n)` | **no** | **no** |
| **enum members** (for VARCHAR columns) | the highest-leverage UI item | **no** (only for real `ENUM`) | **no** |
| **ownership / which module owns this table** | registry routing, uninstall | **no** | **no** |
| **table-level: is it a view or a table?** | two-shape rule (`ColumnListSchema` vs `TableSchema`) | **no** — but derivable from `information_schema` | yes |

This is the same conclusion `Schema_Registry_Design.md` §0.7 reached from the
opposite direction: *"The engine only reads `information_schema`. … It does not
give: a display label, a description, an enum member list, user-writable vs
derived, a sensitivity class, or a relationship edge."*

## 3.2 The overlay is POLICY, overlaid on DERIVED SCHEMA — and here is the argument

The alternative is a **single merged schema document** that contains both types
and nullability and labels, authored by hand. That is what `Schema::definitionFor()`
is today. It fails for a specific, demonstrable reason:

> **A merged document cannot be checked against anything.** The instant a
> `VARCHAR(100)` and a label `'Budget'` live in the same hand-written record,
> there is no way to ask "does the database have this column?" without first
> believing the record — including its type and length. Separation is what makes
> the §P5 reconciliation possible at all.

So the two artefacts have **different failure modes and therefore different
custodians**:

| | DERIVED SCHEMA | POLICY OVERLAY |
|---|---|---|
| Produced by | A″ replay of the `$updates` manifest | module's `hooks.php` resolver |
| Content | only what SQL can state | only what SQL cannot |
| Custodian | the installer contract | the module's authors |
| Failure looks like | `column_missing` / `type_changed` in a DriftReport | a mis-classified field silently absent from a picker |
| May be wrong about | nothing — it is a replay | everything semantic |
| Cross-checkable against | `information_schema`, per company | **nothing — by design** |

Three rules make the separation enforceable rather than aspirational:

- **R-POL-1 — The overlay MUST NOT restate type, length, scale, nullability,
  default, key-ness or index membership.** If it does, the derivation layer
  rejects it. This is a one-line check and it is what stops the overlay becoming
  the fifth copy.
- **R-POL-2 — The overlay MAY supply `enumValues` for a `VARCHAR` column** (§2.4),
  and **MUST NOT** supply them for a column whose derived type is `ENUM` — there
  the derived values win and a mismatch is a DriftReport `enum_member_lost`.
- **R-POL-3 — Absence means unclassified, never hidden.** Carried forward from
  `Schema_Registry_Design.md` §B.3 caveat 2: an unclassified column is **visible**,
  so an empty overlay cannot make a table disappear from every picker. A
  mis-classification is the dangerous direction and it is silent.

### 3.3 Where the overlay lives

**Recommendation [D]: in the module's `schema_resolve()` hook, in PHP, next to
the module's code — not in a separate `schema.yml`.**

Reasoning, weighed:

1. It is **already the hook the registry design specifies**
   (`Schema_Registry_Design.md` §D.4), so it adds no new surface.
2. It is **reviewable in the same PR as the label change**. A separate config file
   is a separate thing to forget.
3. It is **type-safe** — a typo is a PHP error, not a silently ignored key.
4. The strongest argument *against*: a policy file diffs more cleanly than PHP and
   can be edited by a non-programmer. **Rejected**, because in this stack the
   people who classify sensitivity are the same people who write the resolver, and
   a policy that can be edited without a code review is a policy that will be
   edited without one.

The overlay must still be **serialisable**, because `schema_refs` hashes it (§P5).
A `->policy()` / `->overlay()` fluent form that produces a canonical array is
sufficient; no file format is needed in v1.

### 3.4 The separation is unchanged by multi-file replay — and now *more* load-bearing **[D]**

**Restated explicitly for Revision 2, because the correction moves the boundary.**

Revision 2 changes what the derived schema *is* (a replay of 333 statements
across many files, not one file). It does **not** move the boundary between
derived and overlay. The separation is restated here as a hard invariant:

> **DERIVED SCHEMA is whatever the replay of the ordering authorities produces.
> POLICY OVERLAY is everything else. They are two artefacts, stored separately,
> with different custodians, different failure modes, and different
> checkability — and they are never merged into one document.**

Four rules make that invariant enforceable rather than aspirational. `R-POL-1/2/3`
are carried forward unchanged from §3.2; `R-POL-4` is new.

| Rule | Statement | Enforced by |
|---|---|---|
| **R-POL-1** | The overlay **MUST NOT** restate type, length, scale, nullability, default, key-ness, index membership or FK. | one-line check at overlay-merge time; a violation is an exception, not a warning |
| **R-POL-2** | The overlay **MAY** supply `enumValues` for a `VARCHAR` column, and **MUST NOT** for a column whose derived type is `ENUM`. | §2.4; mismatch → `enum_member_lost` in the DriftReport |
| **R-POL-3** | **Absence means unclassified, never hidden.** | registry side; carried from `Schema_Registry_Design.md` §B.3 caveat 2 |
| **R-POL-4** *(new)* | **The overlay is keyed by logical column name, and MUST be validated against the derived schema at merge time. A key that does not exist in the derived schema is an error — because the derived schema is now the output of a *replay*, and a replay that is missing an `ALTER` would otherwise let the overlay silently compensate.** | `OverlayPolicyResolver` decorator; throws on unknown column/table |

**`R-POL-4` is the rule that Revision 2 earns.** Under single-file parsing, a
missing column in the derived schema was already a detectable divergence. Under
multi-file replay it becomes **much easier to get wrong in exactly one way** —
forget an upgrade file, or take the manifest order from the directory instead of
the manifest (§0.9) — and the overlay, being unchecked, would quietly paper over
it. Validating overlay keys against the replayed schema makes that failure
*loud* instead of silent. It is the same reason the derived schema must be
checkable against `information_schema` (§5.3): **two independent checks, on the
two halves, is what keeps the split honest.**

---

# PART 4 — DTOs, honestly

## 4.1 The user's specific idea, scored

| Criterion | Verdict **[V]** |
|---|---|
| Can the engine obtain a blank instance? | Sometimes. `newInstanceWithoutConstructor()` works, but yields **every property at its default** — which tells you nothing the class already didn't declare. For a class with no constructor, there is nothing to skip. |
| Can it reflect the field *set*? | Only by reading **private** properties. PHP 7.3/7.4 reflection will list them. |
| Can it reflect field *types*? | Only where properties are typed (`ProjectDTO`: `private string $budget`… actually `private float`). For `array $payload` constructors, only the `@var` docblock — **zero attributes exist** (§0.8). |
| Does the field set equal the column set? | **No.** `ProjectDTO`: 5 phantom fields, 1 missing column. `SchedulingContextDTO`: 10 phantom fields, 41 columns unrepresented. |
| Does a reflected type map to a SQL type? | **No.** `string` → `VARCHAR(20)`? `TEXT`? `ENUM`? Undecidable. |
| Is there a table binding to read? | **No.** 0 of 54. |
| Coverage | 2 of PM's 10 tables. |

**Overall: worse than reading the schema, not better.** Reflection on a hand-
written DTO is a *fourth* copy that is (a) incomplete, (b) untyped at the level
that matters, (c) unbindable to a table, and (d) already demonstrably divergent.

## 4.2 Why reflection is *structurally* the wrong tool here

The deeper reason is that **a DTO and a table answer different questions.**

| | DTO | Table |
|---|---|---|
| Question | "what does this operation carry?" | "what can be stored here?" |
| Cardinality | subset (views/projection) | complete |
| Nullability | defaults fill it in (`'Team Member'`, `max(1, …)`) | a fact |
| Aggregates | allowed and common (`taskCount`, `overallProgress`) | impossible |
| Naming | application-shaped (`startDate`) | storage-shaped (`start_date`) |

`SchedulingContextDTO` is not a bad DTO. It is a good DTO of a *command*. Using
it as a schema would be a category error.

## 4.3 The middle path — DTOs for serialisation, a TEST for equality **[D]**

> **This is correct and it is the recommendation.** Adopt it, with one
> amendment: the test asserts against **A″-derived** schema, never against
> `information_schema`, so it runs in unit CI with no database.

```
DTO PROPERTY        must equal   DERIVED COLUMN
────────────────────────────────────────────────────────────
projectId         ⇔  project_id           (name, after camel→snake)
budget            ⇔  budget               (type: float/decimal ⇒ decimal)
projectTypeId     ⇔  project_type_id
<no property>     ⇒   may be a column only if declared non-writable/derived
taskCount         ⇒   MUST be listed in the overlay as derived
```

The value is not "the test passes". The value is that **it converts a silent
divergence into a red build**, which is exactly what
`Schema_Registry_Design.md` §0.4 says nothing currently does.

Three rules keep the test from becoming a new source of truth:

- **R-DTO-1 — The test is one-directional.** It may assert *DTO ⊆ derived ∪
  declared-derived*. It must **never** assert *derived ⊆ DTO*, or every
  non-projected column becomes a test failure and the DTO is forced to mirror the
  table — which is the failure mode this design is trying to avoid.
- **R-DTO-2 — A phantom DTO property must be declared, not merely tolerated.** If
  `taskCount` is not in the overlay as `derived`, the test fails. Otherwise the
  convention erodes and every DTO accumulates undeclared computed fields.
- **R-DTO-3 — The mapper (`camelCase → snake_case`) is one shared function** in
  `ksf-common-db`, unit-tested once, not reimplemented per module. There is no
  such function today **[V]**; there are at least two naming conventions in the
  DTO set (`SchedulingContextDTO` is snake_case-on-the-wire, `ProjectDTO` is
  camelCase).

**Where the test runs:** in the module's own `tests/`, as a unit test with the
`.sql` files as fixtures. It needs no database and no FA bootstrap. This is the
cheapest high-value check in the entire design.

---

# PART 5 — Eliminating the copies

## 5.1 The five sources, re-ranked

`Schema_Registry_Design.md` SR-1 lists five. Verdict on each:

| # | Source | Verdict |
|---|---|---|
| 1 | `sql/install.sql` + the whole `$updates` manifest | **AUTHORITATIVE — but as a REPLAY, not a file.** Revised in Revision 2: source 1 is not a file, it is *"every SQL file either ordering authority will run, in that authority's order"* (§0.9, §0.10). |
| 2 | Hand-written dictionary (`Schema.php`) | **DELETE as a source.** Demote to a *consumer* of the registry (it may cache, it may not originate). |
| 3 | Registry cache | **Not a source.** A cache of (1) + overlay. Must be reconstructible by deleting it. |
| 4 | `schema_refs` snapshot | **Not a source.** A *record of what source (1) looked like at author-time*. It is the drift detector's input, never a resolver's input. |
| 5 | `information_schema` | **Not a source.** The *observed* schema. Used **only** as the assertion target in §5.3. |

**Five sources → two (the replay = declared; `information_schema` = observed),
plus one derived artefact that is provably equal to the first.** The overlay
(§P3) is a *third* input but it is orthogonal — it states nothing the first two
can contradict, and `R-POL-4` (§3.4) enforces that at merge time.

**One caveat Revision 2 adds:** source 1 is authoritative for **what a module
declares**, and §0.9.4 shows **four modules declare tables FA never creates**.
Authority over *intent* is not authority over *fact* — which is exactly why §5.3
exists and why `R-REC-5` makes "declared table absent from the database" an
error rather than a curiosity.

## 5.2 The decision SR-1 explicitly deferred

> *"Decide **now** whether the dictionary or `install.sql` generates the other;
> do not leave it as a docblock."* **[V — SR-1]**

> **DECISION: the replay (the `$updates` manifest **and** the
> `SchemaMigrationRunner` glob) generates the dictionary. The dictionary never
> generates DDL.** *(Revised in Revision 2: "the replay", not "`install.sql`" —
> see §0.9 for why both authorities must be replayed, and §0.12 for the live
> evidence that omitting one produces a false drift report.)*
>
> Rationale: the manifest is what FA executes. A dictionary that generated DDL
> would have to reproduce `db_import`'s whitelist, its textual prefix rule, its
> error-ignore list, and its line-based delimiter — four behaviours to reimplement,
> any one of which can silently diverge, and the divergence would be **a schema
> that FA never built**. The direction is forced by physics, not preference.
>
> Corollary, and it is the uncomfortable half: **`Schema.php` becomes
> redundant.** `Schema::projects()` and friends should be deleted, not
> maintained, once the registry can answer `definitionFor('fa_pm_projects')`.
> `Schema_Registry_Design.md` §F.1 step 4 says *"fix the missing map entry"*; this
> document says **that fix is the wrong fix** — it repairs one omission in a copy
> that should not exist.

## 5.3 Should `information_schema` be the runtime check against the replay?

> **Yes — as an activation-time and scheduled assertion, never as a request-time
> dependency.** When, where, and at what cost: §6.1 (`R-REC-1` … `R-REC-5`).

Concretely, one query per table, run at `activate_extension()`, nightly, and on
demand from a health screen:

| Compare | Severity |
|---|---|
| declared column absent in DB | **error** — `column_missing` |
| DB column absent in declaration | **warning** — `column_undeclared` (see §5.4) |
| declared type/length ≠ DB type/length | **error** — `type_changed` |
| declared PK/unique ≠ DB | **warning** |
| declared index missing | **warning** |

`FA_ProductAttributes` and `ksf_bank_import` use `check_table()` with a
`$properties` triple **[V]** — `SHOW COLUMNS FROM` is already FA's own
comparison primitive. Reuse that shape rather than inventing one.

Cost: one `SHOW COLUMNS`/`information_schema` query per table, on activation
only. For PM's 10 tables, negligible. This is the same affordability argument
`Schema_Registry_Design.md` §C.2.3 makes for `schema_refs`.

**It must not be a request-time dependency** — that is `FR-CLAC-103`'s
`NullColumnPolicy` guarantee (`Schema_Registry_Design.md` §A.6) inverted: a
registry miss must be *permissive*, and a database round-trip per request to
populate it would make the ACL path depend on DB latency and on the DB being up.

## 5.4 When a company database has drifted (someone hand-ALTERed it)

This is not hypothetical; §0.5 is a live instance on the Integration pod. The
policy:

| Situation | Meaning | Action |
|---|---|---|
| DB has a **column the declaration lacks** (`column_undeclared`) | someone ALTERed by hand, or a migration ran through a path the derivation missed | **Warning, never auto-adopted.** The declaration stays authoritative. Report the column name and table. |
| Declaration has a column the DB lacks (`column_missing`) | migration not applied, or `install.sql` changed without an `upgrade_*.sql` | **Error.** This is exactly PM's ten CPM columns **[V, live-confirmed §0.12]**. |
| Types differ | a hand-ALTER or an unapplied `MODIFY` | **Error.** |
| **A manifest entry that is `Unreachable`** (§0.1a) | FA reports success and applies nothing | **Error**, and it is a *pre-existing* error: AsteriskPBX and `ksf_FA_Customer` are in this state right now **[V]** |
| **An `OrphanNeverApplied` file** (§0.9.3) | the module has DDL FA will never run | **Warning naming the file** — and an **error** if replaying it would have produced a column the DB lacks |
| A **partial** migration (half a file applied) | a failed activation (§1.1a) | **Report as `FailedActivation`, not as drift.** The fix is re-run activation, not reconcile |

**Why "never auto-adopt":** auto-adoption would make `information_schema` the
source (rank 5 in §5.1), which is the failure this whole document exists to
prevent — a hand-typed `ALTER` in a shell becomes permanent schema, unversioned
and unowned. A warning that a human must resolve is the correct friction.

**The remediation for PM is concrete [V, live-confirmed §0.12]:** write
`ksf_FA_ProjectManagement/sql/upgrade_2.x.0.sql` containing the `CREATE TABLE
0_fa_pm_task_dependencies` and the `ALTER TABLE 0_fa_pm_tasks ADD COLUMN` ×10
plus its two `KEY`s, and wire PM into `SchemaMigrationRunner`. The ledger
already exists (`ksf_schema_migrations`) and PM does not use it. **This is a
five-file change and it is a prerequisite for the registry being worth
building for PM** — the live database has **0 of 11** of those objects and no
code path can ever create them.

---

# PART 6 — When schema is derived

## 6.1 The three candidates

| Trigger | Verdict | Reasoning |
|---|---|---|
| **At activation time** (inside `activate_extension()`, right after `update_databases()`) | **Yes — this is the v1 trigger.** | It is the only moment guaranteed to coincide with a schema change. It is where `$check_only` already distinguishes "would this run?" from "run it" — and **that distinction is now doubly useful**, because §0.10.3's gate predicate can be evaluated against `information_schema` *before* the DDL runs, so a dry run reports exactly what the real run would do. |
| **At first request** | **No.** | Pays replay cost on the hot path, couples page latency to file I/O, and — decisively — *a hand-ALTERed column added months later is never noticed*, because nothing marks the moment a schema became stale. |
| **On a scheduled refresh** | **Partially — as the *reconciliation*, not as the *derivation*.** | A nightly declared-vs-`information_schema` sweep over all active modules is what catches a hand-ALTER (§5.4) and a deploy that skipped activation. It is **not** how the schema is produced. |

**Answering the brief's question 5 directly — *when and where does the
`information_schema` assertion run?*** **[D]**

| # | When | Where | Cost | Fails closed? |
|---|---|---|---|---|
| 1 | **Activation, dry run** (`$check_only = true`) | inside `activate_extension()`, *before* `update_databases()` | 1 `SHOW COLUMNS` per owned table | no — reports only |
| 2 | **Activation, real run** | immediately *after* `update_databases()` returns | same | no — activation proceeds; findings are recorded |
| 3 | **Nightly** | a sweep over every `(company, active module)` | ~10 tables × N companies | no — reports only |
| 4 | **On demand** | an admin health screen | same | no |

**Design rules [D]:**

- **R-REC-1 — Reconcile must run unconditionally at activation.** Not behind a
  config flag. ~10 `SHOW COLUMNS` per module is negligible against the DDL that
  activation just ran, and a flag is a flag somebody turns off.
- **R-REC-2 — Reconcile is per `(company, module)`, never global.** Activation is
  per-company **[V]**; two FA pods share one module tree but not one database
  **[V]**. §0.12 queried company `0_` on `ksfii_app` only — the rootless `ksf-fa`
  pod and the UAT box were not reachable and may legitimately differ.
- **R-REC-3 — Reconcile must compare the replay of *both* authorities
  (`R-ORD-3`).** If it derived from A1 only, it would flag `fork_group_id` as
  `column_undeclared` on every run forever, because A2 — not A1 — created it.
- **R-REC-4 — A reconcile finding must never block activation.** The registry is
  a *consumer* of schema; a broken registry must not be able to break FA's
  extension activation. Findings go to the drift report (§6.3 item 2), and only
  an *error*-severity finding on the **table or column the module is currently
  writing to** may degrade that module's registry entry to `unresolved()` —
  which is `Schema_Registry_Design.md` §A.6's permissive-miss rule, not a
  hard failure.
- **R-REC-5 — The one thing reconcile must be able to catch that nothing else
  can** is the §0.9.4 class: a module whose `.sql` exists but which FA never
  runs. Directory-only derivation invents those tables; reconcile reports them
  as `declared_table_absent`. **That is a schema-installation defect, and today
  nothing reports it.**

## 6.2 The design

```
DECLARED  = A″(A1 manifest order ∪ A2 version order, framed by FaSqlFramer)
            — deterministic, pure, cacheable, no DB needed
OBSERVED  = information_schema, per company                 — queried only at reconcile time
REGISTRY  = DECLARED ∘ POLICY overlay                       — built at activation, cached
RECONCILE = DECLARED ⊕ OBSERVED                             — at activation + nightly + on demand
```

**`DECLARED` is now provably a pure function** — of the `.sql` files, `hooks.php`,
and nothing else. No database, no network, no company state. That is what makes
the golden-file fixture test (§7.2 item 11) possible and free.

## 6.3 The hand-ALTER problem, answered concretely

> *"Consider that a hand-ALTERed column would then never be noticed."*

It would, at the **next reconcile**, and it produces a `column_undeclared`
warning that names the table and the column. Three decisions follow:

1. **Reconciliation is cheap enough to be unconditional at activation.** ~10
   `SHOW COLUMNS` per module. Do it every time; do not make it a config flag
   somebody turns off (`R-REC-1`).
2. **The result must be *visible*.** A warning written to the error log is not
   visible. `Schema_Registry_Design.md` §F.3 already defers a health screen; this
   document promotes it: **drift reporting is a v1 deliverable, not v2**, because
   it is the only thing standing between "the registry is populated" and "the
   registry is populated and *true*."
3. **Reconcile per company, not globally** (`R-REC-2`). The drift report is
   therefore `per (company, module)`, never global.

---

# PART 7 — Phased plan

Sized by the verified facts: **one live consumer module, zero workflow tables,
148 SQL files framing to 333 statements, three ordering authorities of which two
have already diverged in production, four modules whose SQL FA never runs, seven
modules with SQL FA will never run, and eleven live schema objects with no
creation path.**

## 7.1 v0 — the fixes that are not the registry **[D]**

*`@FR-SD-001-001` — the derivation layer is worthless if the declarations it reads
are wrong. Ship these first, as their own commits.*

**Revised in Revision 2, and *resequenced*.** Revision 1's v0 began with PM's
missing migration and ended with code-quality fixes. Under multi-file replay the
**ordering-authority defects are now v0 too**, because a wrong authority
produces a wrong *declared* schema for every module, not just PM. v0 is now
ordered **blockers first, then authority, then hygiene**.

| # | Deliverable | Evidence it fixes | Exit criterion |
|---|---|---|---|
| **1** | **PM `sql/upgrade_2.x.0.sql`**: `CREATE TABLE 0_fa_pm_task_dependencies` + `ALTER TABLE 0_fa_pm_tasks ADD COLUMN ×10` + `KEY idx_milestone`, `KEY idx_critical` | §0.5 + **§0.12 live-confirmed: 0 of 11 objects exist** **[V]** | `information_schema` on the Integration pod shows the table and all 10 columns. |
| **2** | Wire PM into `SchemaMigrationRunner`, **and** add PM's new file to its `$updates` map | §0.6, §0.9 | PM's ledger has rows after activation **and** the file is reachable by *both* authorities (`R-ORD-3`) |
| **3** | **Wire `ksf_FA_Calendar/sql/upgrade_2.1.0.sql` into `hooks.php`'s `$updates`** with gate `('fa_cal_entries','fork_group_id')` | §0.9.3 — orphaned DDL for a column the code reads and the DB already has **[V]** | The manifest and the directory agree; the gate is satisfiable |
| **4** | **Decide `SchemaMigrationRunner`'s status and make it stop being a second, divergent authority.** Minimum: version-compare instead of `SORT_STRING`, and document it as an executor the derivation must also replay (`R-ORD-3`). | §0.9.1 — it has already diverged in production **[V]** | Either it is retired in favour of `$updates`, or its contract is documented and tested |
| **5** | **Fix `SchemaMigrationRunner::splitSqlStatements()` — by delegating to the extracted `FaSqlFramer`**, not by writing a new tokenizer | §0.6, §0.11 — broken **[V]**, **and the fix is an extraction, not a rewrite** | The 4 fragments of `upgrade_1.1.0.sql` become 2 valid statements. Unit test on that exact file. |
| **6** | **Convert the 3 `explode(';')` call sites** (`ksf_FA_Attachments:157`, `ksf_FA_Logging`, `ksf_FA_API`) to `FaSqlFramer` | §0.11.3 — the broken splitter is **running in production** **[V]** | grep `explode(';'` → 0 in `fa_modules/*/hooks.php` |
| **7** | **Fix `ksf_FA_AsteriskPBX/hooks.php:54`** — `'sql/update.sql'` → `'update.sql'` (or delete the dead entry) | §0.1a — doubled path, reports success, applies nothing **[V]** | The manifest entry resolves to a real file, or is gone |
| **8** | **Delete the 15 unwired, unprefixed HRM `sql/fa_*.sql` files** (or prefix and wire them) | §0.9.3 — unwired **and** would create tables outside the prefix space **[V]** | HRM's `sql/` has no file that disagrees with `install.sql` |
| **9** | Fix `ksf_FA_Assets/sql/install.sql` — add `0_` to 5 tables | §0.3 **[V]** | No unprefixed `fa_asset*` table |
| **10** | Fix `ksf_FA_Logging/sql/install.sql:11` — `@TB_PREF@` → `0_` | §0.2 **[V]** | 33 → 32 files containing `TB_PREF` |
| **11** | Correct the false `@TB_PREF@` comments in PM/Assets/API `hooks.php` | §0.1 **[V]** | grep *"@TB_PREF@ replacement automatically"* → 0 |
| **12** | Fix `ExpenseTypeCatalogue.php:16` (import + `tableName()` + hardcoded `0_`) | §0.5 **[V]** | Class resolves |
| **13** | PM `Schema::definitionFor()` map entry — **or**, per §5.2, delete `Schema.php` | §0.5 **[V]** | The §0.4 defect is either fixed or no longer exists |
| **14** | **Add `activate_extension()` to the 4 modules that have SQL and no activation** (`ksf_FA_Contacts`, `ksf_FA_Employee`, `ksf_FA_ExpenseReport`, `ksf_FA_Users`) | §0.9.4 — 7 declared tables FA never creates **[V]** | Every module with `sql/*.sql` reaches its own DDL, or the files are deleted |

**v0's acceptance:** *PM's declared schema, its dictionary, and the live
`information_schema` are the same 10 tables and the same columns — verified by
query, not by reading the file.* Then: *`fa_modules/*/sql/` and the set of files
reachable from `hooks.php` differ by **zero** schema-bearing entries.*

## 7.2 v1 — A″, the replay engine **[D]**

*`@FR-SD-001-008` (multi-file differential replay), `@FR-SD-001-009`
(ordering-authority resolution), `@FR-SD-001-002` (accumulator), `@FR-SD-001-003`
(statement framing), `@FR-SD-001-004` (whitelist parity).*

| # | Deliverable | Notes |
|---|---|---|
| 9 | **`FaSqlFramer::frame()`** — extract `maintenance_db.inc:328-374` verbatim, including the `DELIMITER` branch and `lineNo` provenance. **~40 lines, no new tokenizer.** | §0.11.3. Ship this **first** — v0 items 5 and 6 depend on it. |
| 10 | **`ManifestReader`** — PHP-syntax-aware read of `hooks.php` extracting the ordered manifest **in all four shapes** S1–S4 plus `$conditional` (`token_get_all()`, not regex). Emits `R-ORD-4` findings for orphans and dangling entries. | §0.9.2, §0.9.3. A regex extractor silently misses 5 modules **[V]**. |
| 11 | **`SchemaAccumulator`** in `ksfraser\CommonDb\Schema\Derive\` — the state of §0.10.1 and the mutation rules of §0.10.2. **Order-preserving** (27 `AFTER` uses **[V]**). Handles `ADD COLUMN`/`MODIFY`/`ADD INDEX|KEY`/`ADD CONSTRAINT`/`DROP INDEX`/`CREATE [UNIQUE] INDEX`; **warns** on `DROP COLUMN`/`RENAME`/`TRUNCATE`. Applies `R-OWN-1/2`. | Depends on nothing but `php`. |
| 12 | **Whitelist parity** — bucket by FA's **prefix** test (§0.2a), not by verb; reproduce the `0_`→prefix rule *textually* including inside literals; reproduce the drop→create→data execution order within a file. | §0.2, §0.3a. |
| 13 | **`SchemaReplayer`** — `replay(A1) ∪ replay(A2)`, `R-ORD-3`, `R-ORD-5` version ordering. The single entry point everything else consumes. | §0.9.5. |
| 14 | **Golden-file fixtures over all 148 real `.sql` files + all 42 `hooks.php`** — asserting the derived schema **and** the findings list. Runs in CI with **no database**. | The strongest coverage claim available, and it is free. Pins the 333-statement count **[V]**. |
| 15 | `TableDefinition` gains composite PK, `UNSIGNED`, `ordinal`, and `CURRENT_TIMESTAMP`-class defaults. **Additive; the existing 5 tests must pass unchanged.** | `Schema_Registry_Design.md` §F.1 step 2 discipline. |
| 16 | **DTO ↔ derived-schema equality test**, per §4.3, with `R-DTO-1/2/3`. Run against PM's `ProjectDTO` first — it **fails today** (§0.8), which is the correct demonstration. | §4.3. |

**v1's acceptance:** *A″ replays PM's manifest to the same **9** tables the live
database has (§0.12 — 9, not 10, until v0 item 1 lands), replaying Calendar's
two authorities produces `closed_at`, `delta` **and `fork_group_id`** (§0.12), and
the 148-file fixture suite reproduces **333** statements and **zero**
unclassified lines.*

## 7.3 v2 — the registry **[D]**

*`@FR-SD-001-005` (overlay), `@FR-SD-001-006` (reconcile), `@FR-SD-001-007`
(drift report).*

| # | Deliverable | Notes |
|---|---|---|
| 14 | `SchemaResolverInterface` + `DerivedSchemaResolver` (wraps A″) + `OverlayPolicyResolver` (decorator). Overlay enforces `R-POL-1/2/3` **and the new `R-POL-4` unknown-column check**. | §3.2, §3.4. |
| 15 | `schema_advertise()` / `schema_resolve()` per `Schema_Registry_Design.md` §D.4, returning **derived** data. | No new hook surface. |
| 16 | **Reconcile** declared ⊕ `information_schema` at `activate_extension()`, per company, **unconditionally** (`R-REC-1/2/3`), plus nightly and on-demand. | §5.3, §6.1, §6.3. |
| 17 | **Drift report** — visible in an admin screen, not just a log. Must carry the **ordering findings** too: `OrphanNeverApplied`, `Unreachable`, `MigrationOrderRisk`, `MigrationPartial`. | §6.3 item 2. Promotes `Schema_Registry_Design.md` §F.3's deferral. |
| 18 | Delete `ksf_FA_ProjectManagement/src/.../Dictionary/Schema.php` once (15) answers for all 10. | §5.2. |

## 7.4 v3 — deferred **[D]**

| Item | Why deferred |
|---|---|
| Adopting A″ for the other 41 modules | v1 validates the replay against 148 files and 42 `hooks.php`; adoption is mechanical per module but is 41 PRs. |
| `ksf_FA_AsteriskPBX` / `ksf_bank_import` PHP-created tables | **Not deferrable forever** — these 9 tables have no `.sql` and A″ cannot see them. Either move them to `.sql` or give the registry a `->fromDdl(string)` escape hatch. **Flagged as the one genuine hole in A″.** |
| `DROP COLUMN` / `RENAME` / `CHANGE` in the accumulator | **Zero occurrences in the corpus [V]** — specified in §2.5, deferred because unused, not because hard. Implement on first use. |
| Enum extraction from prose `COMMENT` | §2.4 — fragile grammar; do it in the overlay, by hand, for 4 PM columns. |
| Workflow consumption | `Schema_Registry_Design.md` §F.2 steps 8-12. |

---

# Appendix A — Evidence

## A.1 Files read / executed (2026-10-15)

| Path | Used for |
|---|---|
| `ksf_Infrastructure/FA/2.4.3/admin/db/maintenance_db.inc:267-490` (`db_import` end-to-end, incl. `:325` `file()`, `:328-374` framing, `:344` prefix test, `:429-467` bucket execution order, `:483-490` return), `:293-300`, `:948-973` (`check_table`) | §0.1, §0.1a, §0.2, §0.2a, §0.11 |
| `ksf_Infrastructure/FA/2.4.3/includes/hooks.inc:31-63` (`update_databases`), `:50` (path construction) | §0.1, §0.1a, §0.9 |
| **Executed**: FA's framing + prefix whitelist, reimplemented 1:1 in Python, over **all 148 `.sql` files** → **333 statements**, verb/sub-clause census, prefix-match probe table, FA-vs-`explode(';')` comparison | §0.3, §0.3a, §0.10.2, §0.11.2, §2.5, §2.6 |
| **Executed**: manifest-vs-directory diff for **all 42** module `sql/` dirs (regex extract + set diff, then hand-verified every mismatch) | §0.9.3 |
| **Executed**: live `information_schema` queries against `ksfii_app-mariadb` (MariaDB 10.11.14, schema `ksf_fa`) — PM table/column presence, Calendar column presence | **§0.12** |
| `fa_modules/ksf_FA_Calendar/hooks.php:47-113` (`$updates`, `$conditional`, `company_table_exists`) | §0.1, §0.4, §0.9.2 |
| `fa_modules/FA_ProductAttributes/hooks.php:134-196` (S3 loop, `file_exists` skip, per-file gate override) | §0.9.2 |
| `fa_modules/ksf_FA_Notes/hooks.php:181-206` (S2 inline array) | §0.9.2 |
| `fa_modules/ksf_FA_Attachments/hooks.php:145-165`, `ksf_FA_Logging/hooks.php:115`, `ksf_FA_API/hooks.php:90` (S4 direct `db_import`, `explode(';')`) | §0.9.2, §0.11.3 |
| `fa_modules/ksf_FA_AsteriskPBX/hooks.php:53-61` (`'sql/update.sql'` doubled path) | §0.1a |
| `fa_modules/ksf_FA_HRM/sql/fa_departments.sql` (unprefixed `hrm_departments`) vs `install.sql` (`0_hrm_departments`) | §0.9.3 |
| `fa_modules/ksf_FA_Calendar/sql/upgrade_2.1.0.sql` (`fork_group_id`) | §0.9.3, §0.12 |
| `fa_modules/ksf_FA_Calendar/sql/{install,upgrade_1.1.0,1.3.0,1.4.0,1.5.0,1.6.0,1.8.0,1.9.0,2.1.0,2.3.0}.sql` | §0.3, §0.4, §0.10.2, §0.11.2 |
| `fa_modules/ksf_bank_import/sql/add_occurrence_count_to_bi_partners_data.sql` (the only `ADD INDEX`/`DROP INDEX`/`ADD CONSTRAINT`) | §0.3, §0.10.1 |
| `fa_modules/FA_ProductAttributes/sql/32_widen_stock_id.sql` (15 `MODIFY` on 14 **core** tables) | §0.10.2, §0.10.4 |
| `ksf_FA_Common/src/Utils/SchemaMigrationRunner.php:57-84` (`glob` + `sort(SORT_STRING)`), `:119-172`, `:191-197`; caller `ksf_FA_Calendar/cal.php:2383,2393` | §0.6, §0.9.1 |
| **diff** `ksf_FA_ProjectManagement/sql/install.sql` (dev, 10 `CREATE TABLE`) vs `fa_modules/ksf_FA_ProjectManagement/sql/install.sql` (deployed, 9 `CREATE TABLE`, 0 `ALTER`) | §0.5 |
| `find -name 'upgrade*'` across both PM trees → **empty** | §0.5, §0.12 |
| `fa_modules/ksf_FA_ProjectManagement/src/…/Dictionary/Schema.php` (10 constants, 10 methods, 9-entry map) | §0.5, §0.7 |
| `fa_modules/ksf_FA_ExpenseReport/src/ExpenseTypeCatalogue.php:16` | §0.5 |
| 54 `*DTO.php` files; `SchedulingContextDTO`, `ProjectDTO`, `Staging*DTO` | §0.8, §P4 |
| `ksf_common_db/src/Dictionary/TableDefinition.php` (5 keys: `name,type,null,auto_increment,default`) | §0.7 |

## A.2 Not verified — explicitly

*(Revision 2 closes the two most important open items and adds four.)*

1. ~~**The state of the live databases.**~~ **PARTIALLY CLOSED in Revision 2.**
   The **Integration / `ksfii_app` pod (company `0_`, schema `ksf_fa`) was queried**
   and is the basis of §0.12. **Still unverified:** the rootless `ksf-fa` pod
   (8080) did not answer in this session, and the **UAT box was not queried at
   all.** So the `ksf_FA_Logging` `@TB_PREF@ksf_log_levels` and `ksf_FA_Assets`
   five-unprefixed-tables claims remain **inferences from `db_import`'s code path
   [V], not observations** — they must be checked on the other two stacks before
   v0 items 9–10 are actioned.
2. ~~**Whether the 11 PM gaps are present in the live Integration database.**~~
   **CLOSED — they are NOT.** `0_fa_pm_task_dependencies`: **0 rows** in
   `information_schema.tables`. The 10 CPM columns on `0_fa_pm_tasks`: **0 rows**
   in `information_schema.columns`. §0.12. **Independently confirmed, not
   inferred.**
3. **Whether `TaskDependencyRepository` calls `definitionFor()` at all.**
   `Schema_Registry_Design.md` §A.2 item 2 carries this forward; still open.
   (Moot for the *table*, which does not exist at all **[V]**, but still open for
   the *method*.)
4. **Whether the deployed PM `install.sql` is stale or intentionally reverted.**
   Git history was not inspected. **The live database was checked (§0.12) and it
   matches the deployed file, not the dev tree** — so whatever happened, it did
   not happen on this pod.
5. **Column-level `SHOW COLUMNS` output format** — `check_table()` reads
   `$row['Field']`, `$row[$property]`; the exact `Type` string MySQL returns
   (`varchar(20)` vs `VARCHAR(20)`) was **not** observed, and a type comparison in
   §5.3 depends on it.
6. **`information_schema` for FA core tables** (`0_debtors_master`, `0_users`,
   `0_crm_categories`) — those have no module `.sql` at all, so they are outside
   A″ entirely. Whether the registry must cover them is **an open question this
   document does not answer.** It is the largest scope gap and it is not in
   `Schema_Registry_Design.md`'s risk list. *(Narrowed in Revision 2 by `R-OWN-2/3`:
   only tables a module demonstrably `MODIFY`s are surfaced — currently **14 core
   tables**, via `FA_ProductAttributes` **[V]**.)*
7. **No timing was measured.** No replay cost, no `SHOW COLUMNS` cost, no
   reconcile cost. §6.3 item 1's "negligible" is an estimate from file size, not a
   measurement.
8. **NEW — what MySQL does with a statement FA's framing mis-frames.** FA's
   framing is line-based (§2.6); a `COMMENT` string ending a line with a `;`
   would break it. **No such file exists in the corpus [V]** and I did not
   construct one and execute it. The `[UNVERIFIED]` stands.
9. **NEW — the rootless `ksf-fa` pod and the UAT box were not queried.** Only
   `ksfii_app` answered. Per `R-REC-2`, drift is per-company *and* per-pod, so
   §0.12's findings are **specific to the Integration pod, company `0_`**.
10. **NEW — whether `SchemaMigrationRunner` is run against the *rootless* pod's
    Calendar.** §0.12 proves `fork_group_id` exists on `ksfii_app`, which
    implies A2 ran there. It does not prove A2 runs anywhere else, and its only
    callers are `ksf_FA_Calendar/cal.php` and `ksf_FA_Common/src/compat.php`
    **[V]** — whether `compat.php` is invoked on a normal page load was not
    traced.
11. **NEW — `db_import()`'s `$protect` and `$force` arguments are always at their
    defaults on this path** (`update_databases()` calls
    `db_import($path, $con)` — `maintenance_db.inc:267-290`, `:50`). The
    derivation therefore models `force = true, init = true, protect = false,
    return_errors = false`. **A caller that passes different values would change
    the result**; no such caller was found in `fa_modules/`, but the extraction
    should assert them rather than assume them.

## A.3 Related

- [`Schema_Registry_Design.md`](./Schema_Registry_Design.md) — **SR-1** is the risk
  this document resolves; §0.4's defect is re-diagnosed in §0.5 as a *migration*
  problem; §D.4's hooks are unchanged in shape; §B.3's sensitivity caveat is
  carried into `R-POL-3`; §F.1 step 4 ("fix the missing map entry") is **revised
  in §5.2**
- [`Workflow_Engine_Design.md`](./Workflow_Engine_Design.md) — §A.2 is the
  `information_schema` field-type registry this design supersedes; §D.2 is the
  enum dropdown that only the `ENUM` half of §2.4 delivers automatically
- [`ACL_Two_Approaches.md`](./ACL_Two_Approaches.md) §6.2 — the missing
  column-protection inventory, which the overlay creates
- [`Explicit_Column_ACL_API.md`](./Explicit_Column_ACL_API.md) §3.1 `FR-CLAC-104` —
  *"TableDefinition MUST remain policy-free"*; `R-POL-1` is how that is enforced
  mechanically rather than by convention
- [`Column_Level_ACL_API.md`](./Column_Level_ACL_API.md) §9 `Q1` — still open;
  §5.3's per-column comparison makes it decidable per column
- [`../AGENTS.md`](../AGENTS.md) — PHP 7.3 floor (which is why `R-DTO-1`'s mapper
  cannot use PHP-8 reflection features, and why `ManifestReader` must use
  `token_get_all()` rather than an AST library); `FA extension install &
  activation mechanics`, whose `db_import()` notes this document verifies against
  source and finds **partially wrong** in three places, all now corrected in
  place: `@TB_PREF@` is not substituted (§0.1), a missing manifest file **does
  not fatal** (§0.1a), and the whitelist is a **prefix** match so `CREATE INDEX`
  **is** executed (§0.2a)

---

# Appendix B — Revision 2 change log

| § | Revision 1 said | Revision 2 says | Why |
|---|---|---|---|
| Header | "A′ = replay the `$updates` manifest" | **A″ = replay BOTH authorities**, and the document's Part 2 was actually single-file | The brief's correction; confirmed by §0.9 and §0.12 |
| §0.1 | a wired-but-missing file **fatals activation** | **returns `true` — silent success** (§0.1a) | read `db_import` to `:490` |
| §0.2 | `CREATE INDEX`/`VIEW`/`PROCEDURE` are **discarded** | **`create` is a 6-char prefix — they are EXECUTED** (§0.2a) | `:344` is `substr($line,0,6)=='create'`; probed |
| §0.2 | — | **drop → create → data execution order within a file** (`:429-467`) | new |
| §0.3 | raw-line verb grep; `CHANGE` ×1, `CHECK` ×2 | FA-framed census; **`CHANGE` and `CHECK` are 0** — those were false positives from words inside `COMMENT` strings | re-executed with FA's own framing |
| §0.3 | — | **`ALTER` sub-clause census** (the differential vocabulary) | new — §0.10.2 is built on it |
| §0.9 | — | **three ordering authorities; per-module mismatch census; four manifest shapes** | new |
| §0.10 | — | **accumulator state + mutation rules**, with ownership flag | new |
| §0.11 | "we must write a quote-aware tokenizer" | **extract FA's splitter — it is correct on the file that proved `explode` wrong** | executed on all 148 files |
| §0.12 | — | **live `information_schema` queries**; PM blocker **confirmed**; `fork_group_id` **proves A2 has beaten A1** | new |
| §1.1 | — | **replay order + mid-way-failure semantics** (`R-FAIL-1/2/3`) | new |
| §2.5 | non-whitelisted statements are silently dropped | **prefix buckets** (`R-WL-1`); `DROP COLUMN`/`RENAME`/`CHANGE` specified | §0.2a |
| §2.6 | tokenizer required | **`FaSqlFramer` extraction** | §0.11 |
| §3.4 | — | **overlay separation restated**, plus `R-POL-4` unknown-column check | required by the brief; §0.10 |
| §5.1/§5.2 | "the `$updates` manifest" | **"the replay of both authorities"** | §0.9 |
| §6 | activation + nightly | **`R-REC-1` … `R-REC-5`**, incl. per-`(company, module)` and never-blocking | required by the brief |
| §7.1 | 8 v0 items, PM first | **14 items, resequenced**: blockers → authority defects → hygiene | §0.9 findings are now v0 |
| §A.2 | PM gap "unverified" | **CLOSED — confirmed absent** | §0.12 |