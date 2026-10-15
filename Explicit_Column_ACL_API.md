# Explicit-Column API with ACL Enforcement — `ksfraser/ksf-common-db` Query Builder

**Date:** 2026-10-13
**Status:** DESIGN + DOCUMENTATION. No production code written.
**Scope:** `ksfraser/ksf-common-db` (`~/Documents/ksf_common_db`, tree tagged `v1.0.1`)
`src/Query/QueryBuilder.php` + `src/Dictionary/TableDefinition.php`, integrated with
`ksf_FA_RBAC` (`~/Documents/ksf_Infrastructure/fa_modules/ksf_FA_RBAC`).
**Companion:** `Column_Level_ACL_Design.md` (same directory) — push-down vs post-fetch and
the inference-oracle matrix. This document does not redo that work; it builds on it and
covers (a) the legacy array DSL, (b) the explicit-column API shape, (c) where enforcement
lives, (d) the `SELECT *` rejection rule, (e) join-skipping.

Standing decisions applied: `ksf_Architecture_Docs/README.md` §1–6; `AGENTS.md`
(`ksf_common_db` stays transport-agnostic; FA runtime uses native `db_*`; no third parallel
DB abstraction).

Proof-of-concept (scratch, outside the repo, **not** production code):
`/tmp/opencode/explicit_column_acl_poc.php`. It drives the **real** `QueryBuilder` and
`PdoDbAdapter` against in-memory SQLite and every number quoted in §6 is measured from it.

---

## 1. Verdict on the proposed design, up front

| # | Proposal | Verdict |
|---|---|---|
| 1 | Prevent `SELECT *` when ACL is active | **ADOPT, strengthen.** Throw, never silently expand (§5). Expansion is an explicit opt-in, not the default. |
| 2 | Callers pass an explicit array of table-column pairs | **ADOPT.** Two accepted shapes (§4.1): a string list and a normalised pair/expression list. |
| 3 | The builder checks the array and **removes** non-permitted columns | **ADOPT with a change: redact by default (`NULL AS col`), drop only on explicit opt-in.** Silent removal changes result shape and, with `DISTINCT`/`GROUP BY`, changes results (§4.4). |
| 4 | Drop a joined table that contributes no permitted column | **REJECT AS STATED. ADOPT IN RESTRICTED FORM.** Safe only for `LEFT JOIN`, only when nothing references the table, and never in an aggregate/`GROUP BY`/`DISTINCT` query (§6). |
| 5 | Use `ksf_modules_common`'s array-driven builders as the design precedent | **ADOPT THE SHAPE, REJECT THE COMPILER.** Its value rendering **interpolated unescaped user-reachable values into SQL** (§2.3). The DSL *shape* is reusable; its code generator is an injection sink and must not be revived. |

---

## 2. Legacy `ksf_modules_common` — how it actually worked

Source: `~/Documents/ksf_modules_common` (procedural PHP, pre-ORM). Two generations of the
same idea: `class.table_interface.php` (base, 590 lines) and `class.MODEL.php`
("adapted from legacy GENERICTABLE", 1773 lines) with `class.fa_MODEL.php` as the FA subclass.

### 2.1 The data dictionary

`fields_array` — an ordered list of column rows; `table_details` — table name, primary key,
indexes, engine, charset.

```php
// class.MODEL.php:1380-1383 (define_table(), derived from the class name)
$this->fields_array[] = array('name' => 'id_'.$tablename, 'type' => 'int(11)',
                              'auto_increment' => 'yes', 'readwrite' => 'read');
$this->fields_array[] = array('name' => 'updated_ts', 'type' => 'timestamp',
                              'null' => 'NOT NULL', 'default' => 'CURRENT_TIMESTAMP',
                              'readwrite' => 'read');
$this->table_details['tablename'] = $this->company_prefix . $tablename;
$this->table_details['primarykey'] = $ind;
```

Real subclass rows (`class.fa_dimensions.php:60-65`) confirm the shape:

```php
$this->fields_array[] = array('name' => 'name     ', 'type' => 'varchar(60)',
                              'null' => 'NOT NULL', 'readwrite' => 'readwrite');
```

Two observations that matter for us:

- **`readwrite` is the one piece of sensitivity metadata that ever existed here**
  (`'read'` vs `'readwrite'`), and it is consumed only to compute
  `write_properties_array` (`class.MODEL.php:1389-1415`, test at `:1402`
  `strncmp($row['readwrite'], "read", 4) <> 0`). It was **never** consulted when building
  a SELECT list. This is the direct ancestor of the `sensitivity` field proposed in
  `Column_Level_ACL_Design.md` §4.4.
- Column names are stored **space-padded** (`'name     '`) in at least one subclass, and
  `define_table()` derives the table name by string surgery on the class name
  (`:1369-1377`). A dictionary that lets column names carry whitespace and lets the
  *class name* be the schema authority is not safe to feed a policy engine. `TableDefinition`
  must not inherit this.

### 2.2 The array-driven clause DSL (the "small scripting language")

State is a set of arrays (`class.MODEL.php:43-55`): `select_array`, `from_array`,
`where_array`, `groupby_array`, `having_array`, `orderby_array`, `join_array`,
`limit_startrow`, `limit_numberrows`. `buildSelectQuery()` (`:1175-1291`) calls one
`build*()` per clause and concatenates the results (`:1282-1288`).

Documented shapes:

| Clause | Array shape | Compiler |
|---|---|---|
| SELECT | `array('col', 'expr AS alias', …)` | `buildSelect()` `:877-903`, raw `$sql .= $val` (`:897`) |
| FROM | `array('table', 'table AS a', …)` | `buildFrom()` `:913-935` |
| WHERE | `array('col' => value)` or `array('col' => array($op, $value))` | `buildWhere()` `:945-979` |
| ORDER BY / GROUP BY / HAVING | `array('col', …)` | `:989-1111` |
| JOIN | `array( array('table1'=>t,'type'=>'INNER','table2'=>t2,'field1'=>f1,'field2'=>f2) )` | `buildJoin()` `:1129-1174` |

`buildJoin()` assembles the clause positionally from the fixed key order
`array('table1','type','table2','field1','field2')` (`:1145`), inserting the literal
`on` after `table2` and `=` after `field1` (`:1157-1161`). Every element is concatenated
raw (`:1156`).

The intended **condition** form is visible in a live caller —
`class.fa_bank_trans.php:106-110`:

```php
$this->select_array[] = "sum(amount)";
$this->from_array[]   = $this->table_details['tablename'];
$this->where_array['bank_act']  = $this->bank_act;
$this->where_array['trans_date'] = array( 'lte', $sql_date);   // operator tuple
$this->buildSelectQuery();
```

So the intended DSL is `column => value` for equality and `column => [op, value]` for
`>`, `>=`, `LIKE`, etc. **This is the single most valuable idea in the legacy code and the
shape we keep.** The `LIKE` variant exists elsewhere as hand-written SQL:
`class.VIEW.php:444` (`$s . " LIKE " . db_escape(...)`) and
`class.generic_fa_interface_model.php:222,244` (`LIKE '%" . $oldstring . "%'`).

### 2.3 Quoting and escaping — the explicit verdict

**The legacy DSL interpolated values into SQL with no escaping, and it is an injection
risk. It must not be revived.** Stated plainly and with evidence:

- `buildWhere()` — `class.MODEL.php:972`:
  `$sql .= "$col = '$val' ";`
  The value is wrapped in hand-written quotes and concatenated. No escaping function is
  called. `$col` is equally unescaped, so the identifier is attacker-influenced too.
  Measured reproduction (PoC §E):
  `WHERE name = 'x' OR '1'='1'` from `['name' => "x' OR '1'='1"]`.
- `buildOrderBy()` `:1018`, `buildGroupBy()` `:1062`, `buildHaving()` `:1104` — all three
  emit `" '$col' "` (a **string literal** in `ORDER BY`, i.e. additionally invalid SQL).
  `buildSelect()` `:897` and `buildJoin()` `:1156` concatenate raw.
- `select_row()` `:359` and `delete_table()` `:472`/`update_table()` `:508` interpolate
  the primary-key **property value** raw: `WHERE $key='" . $this->$key . "'`. A property is
  settable from an inbound payload (`set()`, `:173`).
- `count_filtered($where)` `:770` concatenates a caller-supplied WHERE string verbatim.
- `class.generic_fa_interface_model.php:222,244` interpolate `$oldstring`/`$newstring`
  into `LIKE`/`REPLACE(...)` literals raw.

Two places that were *not* unsafe, and why the distinction matters: FA 2.4.3's
`db_escape()` **does** add the quotes — `includes/db/connect_db_mysqli.inc:135-158`
returns `"'" . mysqli_real_escape_string($db, $value) . "'"` for strings, `''` for empty,
`NULL` when `$nullify`. So `insert_table()` (`:583-585`) and `ReplaceQuery()` (`:854-856`)
escape values correctly. The defect is specifically the **hand-written quoting in the
clause compilers**, not a lack of an escape function.

Two further facts that show the DSL was abandoned rather than merely unsafe:

- `class.MODEL.php:213` documents `db_encode()` for `select_table()` (`:249`), and
  `db_encode` **does not exist anywhere in FA 2.4.3** (verified: `grep -rl db_encode` over
  `~/Documents/ksf_Infrastructure/FA/2.4.3` returns nothing). `select_table()` therefore
  fatals if called.
- `class.fa_loc_stock.php:75`, `class.fa_prices.php:203`,
  `class.fa_sales_order_details.php:117`, `class.fa_stock_moves.php:133` all call
  `buildDeleteQuery()`, which is **never defined** in `class.MODEL.php`. And
  `class.fa_loc_stock.php:67,85` write `$this->select_array() = array('*')` — invoking a
  property as a method. All four files are broken at the call site.

**Conclusion:** revive the *array shapes* (`column => value`, `column => [op, value]`,
reusable field lists) and the *declarative* intent; replace the compiler with
bound-parameter emission and an operator whitelist. Never concatenate a value.

### 2.4 Keep / reject list

| Keep | Reject |
|---|---|
| `column => [op, value]` condition tuples (`:109`) | Interpolated values (`:972`, `:1018`, `:1062`, `:1104`) |
| `column => value` equality sugar (`:213`) | Identifiers/aliases concatenated raw (`:897`, `:1156`) |
| Ordered `fields_array` as one reusable projection list (`class.fa_dimensions.php:78-80`) | `'readwrite'` as the *only* sensitivity bit — promote to a real `sensitivity` field with a level, not a boolean |
| Declarative clause assembly order in `buildSelectQuery()` (`:1282-1288`) | `buildSelectQuery()`'s `KSF_FIELD_NOT_SET` swallowing (`:1198-1207`) — "not mandatory, continue" is exactly the silent-skip failure mode this design must avoid |
| `fields_array` reuse via `import_fields_array()` (`:1692-1704`) | Class-name-derived table names (`:1369-1377`) and space-padded column names |

---

## 3. Where enforcement should live

### 3.1 Recommendation

**A dedicated policy-collaborator object, invoked from `QueryBuilder::toSql()`, with the
gate keyed on "a policy object is registered", not on "is RBAC installed".**

Concretely: add `ksfraser\CommonDb\Security\ColumnPolicyInterface` (consumer-owned contract,
already specified in `Column_Level_ACL_Design.md` §4.1) plus a compiler
`ksfraser\CommonDb\Security\ColumnProjectionCompiler` that `toSql()` calls once, before the
existing `implode()` chain. It is factored into its own class for testability but is
invoked *from inside* the builder.

### 3.2 Why, against the three candidates

| Candidate | Assessment |
|---|---|
| **`TableDefinition`** | **Rejected.** It is the *schema*, not the *policy*. It cannot see the FROM table, the joins, or the WHERE clause, so it cannot police a projection. Worse, it has no notion of the current caller. Making the dictionary decide visibility smuggles policy into schema and would make the dictionary unusable for DDL and migrations (`createSql()`/`insertSql()` `:178-255`). It does, however, need two additive changes: `columnDef()` must become **public** (it is `private` at `:139`) and a `sensitivity(string $column)` annotation must exist. |
| **Wrapper / decorator** | **Rejected as the enforcement point, for a hard structural reason: it cannot be written.** `QueryBuilder` exposes no getters — `$select`/`$from`/`$where`/`$joins` are private with no readers (verified: only `toSql()` and `getParams()` are public). A decorator holding a `QueryBuilder` cannot see a single clause. It becomes possible only *after* accessors are added — at which point the enforcement is trivially inside the builder, and a decorator adds a second object that can be forgotten. |
| **`toSql()`** | **Adopted.** It is the single point where the complete statement exists and before it becomes a string. It sits **above both adapters**, so `FaDbAdapter` and `PdoDbAdapter` inherit enforcement with zero duplication, and standalone/PDO users get the same guarantee. Nothing below `toSql()` can be bypassed by an adapter, because the adapter only ever receives the already-checked SQL. |

Two supporting notes:

- **Adapters stay dumb.** `FaDbAdapter::bindParams()` resolves `:name` with
  `str_replace(':' . $name, …)` (`FaDbAdapter.php:98`) and `prefixTables()` only rewrites
  tokens after `FROM|JOIN|INTO|UPDATE|TABLE` (`:56`). Any ACL-generated fragment must
  therefore avoid `:` followed by a bound-parameter name. `NULL AS col` and `CASE … END`
  are safe; the condition DSL in §4.3 should generate its own placeholder names
  (`:w1`, `:w2`) so collisions are structurally impossible.
- **Post-fetch stays, as an assertion only.** The defence-in-depth check from
  `Column_Level_ACL_Design.md` §4.5 (verify no non-permitted key carries a non-NULL value)
  catches queries that bypassed the builder. It is not the control.

### 3.3 Requirement statements

- **FR-CLAC-101** The query builder MUST obtain its visible-column set from a registered
  `ColumnPolicyInterface` and MUST NOT contain hard-coded column knowledge.
- **FR-CLAC-102** Enforcement MUST be applied once, in `toSql()`, above every
  `DbConnectionInterface` implementation, so that `FaDbAdapter` and `PdoDbAdapter` require
  no security logic and cannot bypass it.
- **FR-CLAC-103** When no policy is registered, `toSql()` output MUST be byte-identical to
  the pre-change output.
- **FR-CLAC-104** `TableDefinition` MUST remain policy-free; it supplies schema only.
  `TableDefinition::columnDef()` MUST become public and each column MAY carry a
  `sensitivity` level that the policy MAY use as a default answer.

---

## 4. The explicit-column API

### 4.1 Two accepted shapes

**Shape A — string list (the everyday form).** Identifiers only; no values, no arbitrary
SQL. Already what the builder stores today (`QueryBuilder.php:59-64`), so existing callers
keep working.

```php
$qb->select(['emp.id', 'emp.name', 'dept.dept_name']);
$qb->select(['p.project_id', 'p.name', 'p.budget',
             'COALESCE(SUM(r.revenue_amount), 0) AS revenue']);   // expression: refs required
```

**Shape B — normalised pairs (the policy-facing form).** Used when the builder must reason
about the list rather than merely render it, and as the target the string form normalises
to.

```php
$qb->selectItems([
    ['table' => 'emp',  'column' => 'id'],
    ['table' => 'emp',  'column' => 'name'],
    ['table' => 'emp',  'column' => 'salary'],        // denied  -> NULL AS salary
    ['expr' => 'COUNT(*)', 'as' => 'n'],               // refs: none
    ['expr' => 'COALESCE(SUM(r.revenue_amount), 0)', 'as' => 'revenue',
     'refs' => [['table' => 'revenue', 'column' => 'revenue_amount']]],
]);
```

Plus a shorthand for the single-table case, which is what most call sites want:

```php
$qb->selectColumns('emp', ['id', 'name', 'dept_id']);   // == the three pairs above
```

Rules:

1. **No bare `*` and no `alias.*` in either shape** — see §5.
2. **Expressions must declare their references** (`refs`). The builder does **not** parse
   expressions to find column names. This is deliberate: it removes the regex-parsing risk
   (R1 in `Column_Level_ACL_Design.md` §6) from the projection path entirely. An expression
   whose declared refs are all permitted is emitted verbatim; one that declares — or is
   found by validation to reference — a denied column is a **hard error** (§4.4).
3. **Aliases are explicit** (`AS`), and the alias is what appears in the result row.
4. A qualified column (`alias.col`) is resolved through the builder's alias→table map. A
   column with no qualifier resolves to the FROM table; if the statement has joins and the
   column is unqualified, that is ambiguous in SQL and MUST be rejected under a policy
   (`AmbiguousColumnReference`).
5. The builder keeps an **alias→real table map** so every reference resolves to a real
   table name before the policy is consulted. `from('stock_master p')` and
   `fromDefinition($def, 'p')` both populate it.

### 4.2 End-to-end example (ACL active, one column denied)

```php
$policy  = new RbacColumnPolicy();          // from ksf_FA_RBAC
$schema  = Schema::projects();              // TableDefinition

$qb = (new QueryBuilder())
    ->withColumnPolicy($policy)
    ->fromDefinition($schema, 'p')
    ->selectColumns('projects', ['project_id', 'name', 'budget', 'internal_notes'])
    ->whereColumn('projects.status', '=', 'active')
    ->orderByColumn('projects.name')
    ->limit(50);

$qb->toSql();
```

with `internal_notes` not permitted, emits:

```sql
SELECT `project_id`, `name`, `budget`, NULL AS internal_notes
FROM   proj p
WHERE  `status` = :w1
ORDER BY `name`
LIMIT 50
```

`getParams()` → `['w1' => 'active']`. Measured shape: PoC §B produced
`['e.id', 'e.name', 'NULL AS salary']` from a request of `['e.id','e.name','e.salary']`.

### 4.3 Condition DSL (the modern replacement for `column => [op, value]`)

The legacy intent — declarative, array-driven conditions — survives; the compiler does not.

```php
$qb->where()                                  // returns a ConditionGroup
   ->eq('emp.dept_id', $deptId)               // emp.dept_id = :w1
   ->gte('emp.salary', $min)                  // denied column -> ColumnAccessDenied
   ->likeStart('emp.name', $prefix)           // emp.name LIKE :w2   (:w2 = $prefix.'%')
   ->likeContains('dept.dept_name', $needle)  // dept.dept_name LIKE :w3 (:w3 = '%'.$needle.'%')
   ->notNull('dept.cost_code')                // dept.cost_code IS NOT NULL  (no bind)
   ->in('emp.id', $ids)                       // emp.id IN (:w4,:w5,:w6) — generated names
   ->orGroup(function (ConditionGroup $g) {    // explicit grouping, no operator strings
        $g->eq('dept.id', 1)->gt('dept.id', 5);
   });
```

- Every **value** becomes a bound parameter with a builder-generated name (`:wN`). No value
  ever reaches SQL as text.
- The **operator is chosen from a whitelist by method name** — `eq, neq, lt, lte, gt, gte,
  like, notLike, in, notIn, between, isNull, isNotNull`. Operators are never taken from
  caller or user input, which removes the whole "operator injection" class.
- The **left operand is a structured reference** (`table.column`), so the policy check is
  exact. This is what closes `Column_Level_ACL_Design.md` matrix rows #3–#10: `WHERE` on a
  denied column is caught *structurally*, not by parsing a string.
- An **expression operand** requires declared `refs` on the same terms as §4.1 rule 2.
- Raw strings stay supported for backward compatibility
  (`->where('stock_id = :id', ['id' => $x])`, used throughout
  `ksf_FA_ProjectManagement`), but under an active policy they are **unverifiable** and
  therefore rejected (§7).

### 4.4 Disposition of a non-permitted column: redact, drop, or error

Three dispositions, chosen by configuration, never inferred:

| Disposition | Emitted | When to use |
|---|---|---|
| `REDACT` (**recommended default**) | `NULL AS col` | Keeps result shape stable for report/CSV templates; the value never exists in PHP (strictly stronger than post-fetch — `Column_Level_ACL_Design.md` §2.2). |
| `DROP` | column omitted | Opt-in only. Changes result shape and, with `DISTINCT` or `GROUP BY`, changes results. |
| `THROW` | nothing | Opt-in for call sites that must never silently receive less data than they asked for. |

Hard rule regardless of disposition: **if the disposition would leave the select list
empty**, throw `NoPermittedColumns`. `SELECT` with no columns is not valid SQL, and
emitting `SELECT FROM t` would reach `db_query()` and raise the uncatchable `E_USER_ERROR`
(`README.md` standing decision #4). If the caller genuinely wants a redacted empty
projection, they must say so: `->allowEmptyProjection()` emits `NULL AS _redacted`.

Expressions are never silently dropped or truncated: an expression whose declared refs hit a
denied column is always `THROW` (PoC §B2, measured:
`ColumnAccessDenied: table.column emp.salary referenced by select item
"COALESCE(SUM(e.salary),0)" is not readable`).

- **FR-CLAC-110** Under an active policy the builder MUST NOT emit `*`.
- **FR-CLAC-111** A requested column that is not permitted MUST be redacted by default, and
  drop-instead-of-redact MUST require explicit opt-in.
- **FR-CLAC-112** Any disposition that would produce an empty projection MUST throw unless
  the caller explicitly allowed an empty projection.
- **FR-CLAC-113** An expression MUST declare every column it reads; the builder MUST NOT
  infer expression references by parsing. An expression that references a non-permitted
  column MUST throw.

---

## 5. The `SELECT *` rejection rule

### 5.1 How ACL-active is detected

**Not** by probing whether the RBAC module is installed, activated, or present in a
registry. Detection is a method on the policy object, and the default is a null object that
reports inactive.

```php
namespace ksfraser\CommonDb\Security;

interface ColumnPolicyInterface
{
    /** Is column ACL in force for this request at all? */
    public function isActive(): bool;                                  // FR-CLAC-120

    /** Does this policy manage $table? False => table is unrestricted. */
    public function manages(string $table): bool;                      // FR-CLAC-121

    /** May the current caller read $column of $table? Never true for '*'. */
    public function canRead(string $table, string $column): bool;      // FR-CLAC-122

    /** Permitted columns of $table, for redaction messages and '*' expansion. */
    public function visibleColumns(string $table): array;             // FR-CLAC-123
}
```

Shipped in-package: `NullColumnPolicy` (`isActive() === false` — the backward-compatibility
guarantee, `FR-CLAC-103`) and `CachingColumnPolicy` (request-scoped memo keyed
`company|userId|table`, per `Column_Level_ACL_Design.md` §4.3). `ksf-common-db` never
`require`s RBAC; the arrow is one-way, RBAC's `composer.json` already requires
`ksfraser/ksf-common-db`.

**Per-table granularity is the key compat lever**: `manages()` returning false for
`stock_master` means enabling column ACL for `emp` does not touch the other 90% of queries in
the application. This is what makes the release non-breaking.

### 5.2 Failure mode

`StarNotPermitted extends ColumnAccessDenied extends RuntimeException` — **thrown**, not
warned, not logged-and-continued, and never auto-expanded. Measured (PoC §A):

```
StarNotPermitted: SELECT * is not permitted while column ACL is active;
declare explicit table-column pairs (see Explicit_Column_ACL_API.md)
```

Design rules for the exception:

- **It names the table and lists what *is* visible**, so the caller can fix the query in one
  edit instead of guessing.
- **It is thrown from `toSql()`**, so it is caught before any SQL is issued — this matters
  because a malformed statement reaching `db_query()` produces an uncatchable
  `E_USER_ERROR` (standing decision #4). The builder must never emit SQL it has not
  validated.
- **It is a distinct class from the "column denied" error**, so a caller can distinguish
  "you used a shortcut" from "you asked for something you may not have".
- There is **no silent-expansion path by default**. If the builder holds a
  `TableDefinition` it *can* expand `*` to the permitted set; that is offered only as an
  explicit `->expandStar()` opt-in, so a caller who wants it must ask, and every occurrence
  is greppable. Silent expansion would defeat the stated purpose ("PREVENTION, so this must
  be loud, not silent").

Two additional stars must be rejected the same way: `alias.*` and bare `*` appearing inside
an undeclared expression.

- **FR-CLAC-121** `SELECT *` and `alias.*` MUST throw `StarNotPermitted` whenever
  `isActive()` is true for any table in the statement.
- **FR-CLAC-124** Star expansion MUST require explicit caller opt-in and MUST be emitted as
  an explicit column list, never as `*`.

---

## 6. Join skipping — verdict and rule set

### 6.1 Verdict on the proposed rule

**The rule as stated — "if a table contributes no permitted columns, drop it from the join" —
is unsafe and must be narrowed.** It is unsafe in three independent ways, all measured.

**(a) `COUNT(*)` after dropping an INNER JOIN is an existence oracle.** Measured (PoC §C),
with `dept.cost_code` denied:

| Statement | Result |
|---|---|
| `SELECT COUNT(*) FROM emp e INNER JOIN dept d ON d.id=e.dept_id AND d.cost_code='CC-1'` | **2** |
| same, join dropped | **3** |

The caller learns how many employees have a department with `cost_code = 'CC-1'` — a fact
about a denied column — from a statement that names no denied column and projects nothing.
This is precisely matrix row #3/#7 of `Column_Level_ACL_Design.md`, reached through a join.

**(b) `LEFT JOIN` + `WHERE` on the joined table is an INNER JOIN in disguise.** Measured:
`COUNT(*)` = 2 with the WHERE present. Any "safe because it is a LEFT JOIN" rule must
therefore be evaluated *after* predicate references are resolved, or it walks straight into
(a).

**(c) The naive contribution test breaks the most common real query shape.** A projection
`p.project_id, p.name, p.budget, COALESCE(SUM(r.revenue_amount),0) AS revenue` selects **no
raw column** from `r`. The proposed rule would drop `r`, and the revenue report would
silently become `0` for every project. This is not hypothetical — it is the live query in
`ksf_FA_ProjectManagement/src/…/Service/ReportService.php:118-131`:

```php
$qb->select(['p.project_id','p.name','p.budget','COALESCE(SUM(r.revenue_amount), 0) AS revenue'])
   ->from(Schema::T_PROJECTS . ' p')
   ->join('LEFT JOIN ' . Schema::T_REVENUE . ' r ON r.project_id = p.project_id')
   ->groupBy('p.project_id');
```

PoC §C2 confirms the rule must keep that join (measured: `joins kept` = the revenue join,
`joins dropped` = empty).

### 6.2 Rule set

**JD-1 — Candidate.** A joined table `T` (alias `a`) is a pruning candidate only when all
of: `T` is policy-managed; `T` is not the FROM table; `T` contributes no permitted
projected column; `T` contributes no column to any permitted expression; `T` is referenced
nowhere else in the statement.

**JD-2 — Predicates first.** References in `WHERE`, `GROUP BY`, `HAVING`, `ORDER BY`, and in
the `ON` clause of any *other* join are resolved and policy-checked **before** any pruning
is considered. A reference to a denied column there is `ColumnAccessDenied` (matrix rows
#3–#7, #10). A reference to a *permitted* column of a candidate table makes the table a
non-candidate and is preserved.

**JD-3 — INNER / CROSS / RIGHT / FULL with no permitted columns → HARD ERROR.** Never
silently dropped. The exception message names the table and the join type and tells the
caller to remove the join themselves (JD-8) or to re-state the query against the base
table. Measured (PoC §C3):

```
JoinRetained: join table "dept" has no permitted projected column and is an INNER JOIN;
dropping an inner join changes the row set (and COUNT(*)), which leaks whether matching rows
exist. Remove the join explicitly.
```

**JD-4 — LEFT JOIN with no permitted columns → droppable, but only in a non-aggregating
statement.** A `LEFT JOIN` cannot reduce the base row set, so row count and `COUNT(*)` are
invariant (measured §C: identical grouped output with and without the join). Additionally:

**JD-5 — Never prune inside an aggregate query.** If the projection contains any aggregate
function, or the statement has `GROUP BY` or `DISTINCT`, pruning is refused even for
`LEFT JOIN`, because a 1:N join multiplies rows and changing the fan-out changes `COUNT`,
`SUM`, and `DISTINCT` cardinality. The builder cannot know the join cardinality. The caller
may assert it: `->allowJoinPruneInAggregates()` — an explicit, greppable, auditable
override on the caller's own authority.

**JD-6 — A dropped table must leave a trace.** Every automatic prune emits an audit event
(`table`, `alias`, `join type`, statement id) and is reported through
`$qb->prunedJoins()`, so "why did my row count change" is answerable from the request log
and not from guesswork.

**JD-7 — Fail-closed on unparseable joins.** Today `join(string $clause)` accepts an opaque
string. Under an active policy an unparseable join clause is **rejected**, not pruned and
not passed through — the builder cannot know which table it names, so it cannot check it.

**JD-8 — Explicit caller control is the primary mechanism.** `->withoutJoin('r')` lets the
caller remove a join themselves, where the cardinality change is their decision. Automatic
pruning (JD-4) exists for the *accidental* case only: a permission change that empties a
projection. **Recommendation: make automatic pruning default-off in v1.1 (opt-in per query)
and revisit default-on once the RBAC side is live and measured.**

### 6.3 What pruning can and cannot achieve

Pruning is a **hygiene and least-privilege measure**, not the leak control. It prevents an
unpermitted table from participating in a row-set computation the caller did not intend.
It does **not** stop the mirroring-column leak (matrix row #12): measured (PoC §G), a policy
that denies `emp.salary` but permits `payroll.gross` returns 100000 / 70000 / 90000 with no
reference to `emp.salary` anywhere in the statement:

```sql
SELECT e.id, e.name, pr.gross FROM emp e INNER JOIN payroll pr ON pr.emp_id = e.id
```

The only control for that is **per-table policy** — every table in the statement resolves
its own visible set, and `payroll.gross` must be classified as sensitive in its own right.
This is a residual risk per `Column_Level_ACL_Design.md` §2.5 and it is not solved here.

- **FR-CLAC-130** Policy checks MUST be applied to `WHERE`/`GROUP BY`/`HAVING`/`ORDER BY`
  and join-`ON` references before any join pruning is considered.
- **FR-CLAC-131** A joined table with no permitted columns MUST NOT be pruned when the join
  is INNER, CROSS, RIGHT or FULL; the builder MUST throw.
- **FR-CLAC-132** Automatic join pruning MUST be limited to `LEFT JOIN` in statements with
  no aggregate function, no `GROUP BY` and no `DISTINCT`, unless the caller explicitly
  asserted otherwise.
- **FR-CLAC-133** Every automatic prune MUST be recorded in the audit trail and exposed on
  the builder.
- **FR-CLAC-134** An unparseable raw join clause MUST be rejected when a policy is active.

---

## 7. Backward compatibility

### 7.1 With no policy registered — nothing breaks

`NullColumnPolicy::isActive() === false` ⇒ the compiler is not invoked ⇒ `toSql()` output is
byte-identical. Measured (PoC §A2): `select(['*'])` returns `['*']` unchanged when no managed
table is present. The three existing cases in
`tests/Unit/Query/QueryBuilderTest.php` (including the two asserting `SELECT *`) continue to
pass unchanged.

### 7.2 What breaks the moment a policy is registered — enumerated

| # | Breaks | Evidence | Migration |
|---|---|---|---|
| 1 | `select('*')` in read-by-id / count / update / delete paths | 8 call sites, all in `ksf_FA_ProjectManagement`: `Repository/ProjectRepository.php:73`, `TaskRepository.php:75,114`, `ProjectTypeRepository.php:42,53,63`, `AssignmentRepository.php:83,143` | Convert each to `selectColumns()` or an explicit list; add a test that each repository compiles under a policy. |
| 2 | The **default** select is `['*']` — a builder with no `select()` call at all emits `SELECT *` | `QueryBuilder.php:26,59` | Either default to the FROM table's permitted columns when a definition is attached, or make `select()` mandatory under a policy (`MissingSelectClause` error). Recommend the latter: explicit is the point. |
| 3 | Raw string clauses (`where('status = :status', …)`, `orderBy('p.budget DESC')`) | `ProjectRepository::applyFilters():169-178`, `TaskRepository:241-253`, `ReportService:126-131`, `TaskDependencyRepository:76` | Under a policy, raw clauses are unverifiable ⇒ must migrate to the condition DSL, or be allowed via an explicit, greppable escape hatch. **This is the largest single piece of consumer work and the biggest compatibility decision (§8 Q3).** |
| 4 | `join()` signature is already mismatched in a live consumer | `TaskDependencyRepository.php:75` calls `join('INNER', $table, $on)` (3 args) against the shipped 1-arg `join(string $clause)` (`QueryBuilder.php:112`). Verified by executing a userland function with 3 extra args: PHP silently ignores them, so the emitted SQL is `FROM 0_… AS d INNER WHERE …` → `db_query` `E_USER_ERROR`, **uncatchable** (standing decision #4) | Add a structured `innerJoin()/leftJoin()/joinStructured()` rather than changing `join()`'s signature (a signature change is a breaking release). The structured form fixes this latent bug as a side effect. |
| 5 | A second, divergent fork of the same builder exists | `ksf_payment_destinations/src/QueryBuilder/QueryBuilder.php` (104 lines) — its own `select()/join($table,$on,$type)/where($col,$val,$op)`, plus `toFaSql()` that substitutes with **`addslashes()`** (`:99`), which is charset-dependent and weaker than `mysqli_real_escape_string` | Converge onto this package rather than extending the fork. Do not copy its API. |
| 6 | `TableDefinition::columnDef()` becomes public; columns gain optional `sensitivity` | `TableDefinition.php:139` is `private` | Additive; no break. |
| 7 | Semver | Tree tagged `v1.0.1`; `APPENDIX.md` still says `v1.0.0` (stale — a doc bug, not code) | Gated behaviour on an injected policy = **v1.1.0**. Anything that changes `select()`'s default or `join()`'s signature = **v2.0.0**, deferred. |

### 7.3 Compatibility rules

- **FR-CLAC-140** With `NullColumnPolicy` registered, `toSql()` output MUST be byte-identical
  to the pre-change builder for every input.
- **FR-CLAC-141** The package MUST remain usable with **no** security namespace referenced
  at all; the null policy is the default, not an opt-in.
- **FR-CLAC-142** Existing raw-string `where()/having()` methods MUST remain callable under a
  null policy and MUST be governed by one documented switch under an active policy.

---

## 8. Phased implementation plan

| Phase | Deliverable | Exit criteria | Risk |
|---|---|---|---|
| **0** (blocking) | Stabilise `ksf_FA_RBAC`: resolve the uncommitted `Repository/*` + `Provisioner/*` deletions, commit the laminas swap, settle the 7.3-vs-7.4 floor | Working tree clean, module tests green | Schedule. Per `Column_Level_ACL_Design.md` §3.2 there is no live record-level data source until this lands. |
| **1** | Builder introspection, no behaviour change: read-only accessors (`selectItems()`, `fromTable()`, `whereClauses()`, `joins()`, …), public `TableDefinition::columnDef()`, `sensitivity()` annotation, alias→table map, `joinStructured()`/`innerJoin()`/`leftJoin()`, `fetchScalar()` | Existing 3 tests unchanged; `toSql()` byte-identical; new tests for the accessors and structured joins. Ship **v1.1.0** | Low. Purely additive. Note `TaskDependencyRepository`'s 3-arg `join()` call starts working — that is a **behaviour change in a consumer**, so it needs its own test and release note. |
| **2** | Policy contract + `SELECT *` rejection: `ColumnPolicyInterface`, `NullColumnPolicy`, `CachingColumnPolicy`, `withColumnPolicy()`, `ColumnDenial::{REDACT,DROP,THROW}`, `expandStar()` opt-in | New tests: `*` and `alias.*` throw under a policy and pass under the null policy; denied raw column redacts to `NULL AS`; empty projection throws; declared expression refs denied throws. Ship **v1.1.0/v1.2.0**. | Medium (R1, R2). |
| **3** | Condition DSL: `ConditionGroup` with the operator whitelist, generated placeholder names, structured operand refs, `orGroup()` | Every matrix row #3/#4/#5/#6/#7/#9/#10 from `Column_Level_ACL_Design.md` has an executing test that throws; raw-string policy switch (fail-closed) lands with a deprecation notice | Medium. Largest consumer migration. |
| **4** | Join structure + pruning rules JD-1…JD-8 | Measured regression tests for the §6.1 numbers (2 vs 3), for the `ReportService` aggregate shape, and for each hard-error case; `prunedJoins()` + audit hook | Medium–High (R3, R4). Ship **default-off**. |
| **5** | RBAC implementation: `RbacColumnPolicy`, `0_rbac_column_policies` (module, table, subject kind, subject id, column), migration, admin UI; classify mirroring columns such as `payroll.gross` | Policies honoured end-to-end on the Integration pod | Medium |
| **6** | Consumer migration: `ksf_FA_ProjectManagement` repositories off `select('*')` and raw clauses; retire the `ksf_payment_destinations` fork | No `select('*')` in any consumer of this package; grep-based CI check | Medium |
| **7** | Post-fetch assertion layer + inference regression suite + audit rows for denials | The suite fails if a leak vector is reintroduced | Low |
| **8** (separate) | Retire or re-align `ksfraser/ksf-db-security` | `VirtualView::findById()`'s `SELECT *` leak (`Dao/VirtualView.php:150-159`) is gone | Low |

### 8.1 Risks specific to this design

| ID | Risk | Severity | Mitigation |
|---|---|---|---|
| **R1** | **Declared expression references can be a lie.** A caller declaring `refs: []` for `COALESCE(SUM(r.secret),0)` bypasses the check. | **High** | The declared-refs form is the only way to express an expression under a policy; it is greppable and reviewable. Optional defence: a conservative parse that **rejects** any expression whose parsed column identifiers are not a subset of the declared refs (a mismatch is an error, so over-declaring is harmless and under-declaring fails closed). |
| **R2** | **Default posture.** `NullColumnPolicy` is fail-open. | High | Already framed as an open decision (§9 Q1). Per-table `manages()` is the mitigation that keeps it safe in practice. |
| **R3** | **Mirroring-column leak** is unclosable by pruning (§6.3, PoC §G). | High | Accepted residual risk; every table must carry its own classification. Never claim pruning closes this. |
| **R4** | **Fan-out in aggregate queries.** Pruning a `LEFT JOIN` changes `COUNT`/`SUM`/`DISTINCT` when cardinality is 1:N. | High | JD-5: refuse to prune in aggregate/`GROUP BY`/`DISTINCT` statements unless the caller asserts otherwise. |
| **R5** | **`E_USER_ERROR` is uncatchable.** Any SQL the builder emits without validating its references becomes a silent mid-render page death. | High | The builder validates before emitting; the raw-clause path fails closed under a policy (JD-7). |
| **R6** | **Namespace case split** `Ksfraser\…\Rbac\` vs `ksfraser\…\` breaks the cross-module type hint. | Medium | Normalise before Phase 5 (`Column_Level_ACL_Design.md` §7 Q5). |
| **R7** | Consumer blast radius is wider than the prior doc assumed: **the doc said the blast radius was "probably zero"; that is now false** — `ksf_FA_ProjectManagement` has 8 `select('*')` sites, 6 raw-clause filter builders and 2 joins. | Medium | Phase 6 migration + CI grep check before Phase 2 is enabled in any pod. |
| **R8** | `FaDbAdapter::bindParams()` `str_replace(':'.$name)` can be corrupted by generated fragments containing `:`. | Low | Builder-generated placeholder names (`:wN`) that never appear in user data; add a guard test. |
| **R9** | Push-down `NULL AS col` is not sargable and can defeat covering indexes on report queries. | Low–Medium | Measure on the real report queries (`ReportService`) before enabling broadly. |

---

## 9. Open decisions needing the user

- **Q1 — Default posture when no policy is registered.** (Carried forward; still open.)
  Allow-all (fail-open, transparent release) or deny-all for tables the policy does not
  know (fail-closed, breaking on day one)? *Recommendation unchanged and reinforced by the
  `ksf_FA_ProjectManagement` evidence: allow-all when **no policy object is registered at
  all**, deny-all for any table a registered policy does not list.*
- **Q2 — Redact vs drop.** Is `NULL AS col` acceptable to every consumer, or do some
  consumers require the key to be *absent* (which itself leaks that the column exists)?
  `REDACT` is proposed as the default; this is a product decision.
- **Q3 — What happens to raw string clauses under an active policy?** Fail closed (secure,
  forces migration of 6+ filter builders) or allow with a deprecation warning (compatible,
  and leaves a live leak vector until every caller migrates)? This is the single biggest
  compatibility decision in the plan.
- **Q4 — Is automatic join pruning wanted at all?** Proposal: default **off** in v1.1,
  opt-in per query, default-on only after RBAC is live. Confirm, or should it be permanent
  opt-out?
- **Q5 — Should `*` be auto-expandable when a `TableDefinition` is attached?** Proposal:
  no by default; `->expandStar()` only. Confirm.
- **Q6 — Write path.** Column ACL for reads only, or also `INSERT`/`UPDATE`? Note
  `TableDefinition::updateSql()` (`:231-245`) writes every writable column unless the caller
  filters — a mass-assignment hazard that exists **today, independent of RBAC**.
  *Recommendation: reads only in v1.x; declare the write path out of scope explicitly.*
- **Q7 — Per-request static mask or per-record projections?** (Carried forward from
  `Column_Level_ACL_Design.md` §7 Q3.) A per-record mask cannot be expressed as a static
  projection — it needs `CASE WHEN <record predicate> THEN col END`, and RBAC's
  `0_rbac_record_access.projection` column is a *name*, not a mask, and is never read.
- **Q8 — Should `ksf_payment_destinations`' fork be retired now?** It is a third builder with
  `addslashes()` substitution. Converging removes a real divergence but is a separate repo's
  scope.
- **Q9 — Namespace normalisation** (`Ksfraser\` → `ksfraser\` in RBAC) before Phase 5?
  *Recommendation: yes, before the contract is type-hinted across the boundary.*

---

## Appendix A — Evidence and what could **not** be verified

### A.1 Files read (2026-10-13)

| Path | Used for |
|---|---|
| `ksf_common_db/src/Query/QueryBuilder.php` (240 lines) | §3, §4, §7 |
| `ksf_common_db/src/Dictionary/TableDefinition.php` (256) | §3.2, §4.1, §8 |
| `ksf_common_db/src/Contract/DbConnectionInterface.php`, `Adapter/FaDbAdapter.php`, `Adapter/PdoDbAdapter.php` | §3.2, §8 |
| `ksf_common_db/tests/Unit/Query/QueryBuilderTest.php` | §7.1 |
| `ksf_modules_common/class.MODEL.php` (1773), `class.table_interface.php` (590), `class.fa_MODEL.php`, `class.vardefs.php`, `class.fa_dimensions.php`, `class.fa_bank_trans.php`, `class.fa_loc_stock.php`, `class.fa_crm_contacts_model.php`, `class.VIEW.php:400-470`, `class.generic_fa_interface_model.php:180-270` | §2 |
| `ksf_Infrastructure/FA/2.4.3/includes/db/connect_db_mysqli.inc:96-165` | §2.3 (`db_escape` semantics) |
| `ksf_FA_RBAC/` — `sql/install.sql`, `RbacService::authorize():203-225`, `Voter/VoterInterface.php` | §5.1, §6 |
| `ksf_db_security/src/Column/ColumnPermissions.php`, `Dao/VirtualView.php` | §8 (not duplicated) |
| `ksf_Architecture_Docs/Column_Level_ACL_Design.md`, `README.md` | built upon, not redone |
| `ksf_FA_ProjectManagement/` repositories + `Service/ReportService.php` | §6.1(c), §7.2 |
| `ksf_payment_destinations/src/QueryBuilder/QueryBuilder.php` | §7.2 #5 |

### A.2 Not verified / not asserted

1. **Runtime behaviour of the FA pods.** Every measurement here is SQLite via
   `PdoDbAdapter` on in-memory PDO, plus PHP-level semantics. MySQL 5.7/8.0 and MariaDB
   were not exercised. In particular the `LEFT JOIN` invariance claim (JD-4) is standard SQL
   and was confirmed on SQLite; it should be re-confirmed on the target MariaDB before Phase
   4 ships.
2. **`TaskDependencyRepository::findAllByProject()` was not executed.** The claim that the
   3-argument `join()` call silently drops its arguments is verified at the PHP language
   level (I executed a userland function called with three arguments and confirmed the
   extras are ignored). That the resulting SQL actually triggers FA's `E_USER_ERROR` in a
   running request is inferred from `db_query()`'s documented behaviour, not observed.
3. **Whether `ksf_FA_ProjectManagement` is the complete consumer set.** I enumerated every
   directory whose `composer.json` requires `ksfraser/ksf-common-db` (12 directories, 10
   distinct modules) and grepped each for `QueryBuilder`/`TableDefinition`; only
   `ksf_FA_ProjectManagement` uses them. A module that requires the package but vendors it
   under a different namespace would not have been found.
4. **Whether the RBAC working tree is intentionally mid-refactor** (carried forward
   unchanged from the prior doc, Appendix A.1).
5. **The `RbacColumnPolicy` data model.** I have not designed `0_rbac_column_policies` in
   detail here; `Column_Level_ACL_Design.md` §4.3 proposes `(module, table_name,
   subject_kind, subject_id, column_name)` and that stands unendorsed until Phase 5.
6. **No performance figures.** R9 is unmeasured.