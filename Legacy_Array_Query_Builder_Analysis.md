# Legacy Array-Driven Query Builder — Analysis and Mapping to the Modern Fluent Design

@BABOK Related: BR-ACL-001, FR-ACL-001-02, FR-ACL-001-04
Status: **Research only. No source file in `ksf_modules_common` or `ksf_common_db` was modified.**
Date: 2026-10-14
Subject tree: `/home/kevin/Documents/ksf_modules_common` (`ksfraser/ksf_modules_common`)
Subject file: `class.MODEL.php`, 1773 lines
Verdict in one line: **the array-driven query builder was never reachable, and the parts that were reachable interpolate unescaped user data into SQL. Do not revive any of its patterns.**

---

## 0. Corrections to the prior investigation

Two of the premises handed to this task are wrong, and one is subtly wrong in a useful way.

| Prior note | Status |
|---|---|
| "AGENTS_ARCH.md describes the legacy framework" | **Wrong file.** `rg -i 'modules_common\|MODEL\.php\|generic_fa_interface'` over `/home/kevin/Documents/AGENTS_ARCH.md` returns **zero hits**. The description lives in `/home/kevin/Documents/AGENTS.md:120-141` ("The 'generic data-dictionary + query-builder' direction", item 2 "Legacy `ksf_modules_common`"). |
| `buildWhere()` at ~:972, `select_row()` at ~:359, `delete_table()` at ~:472 | **Right line, wrong anchor.** Those are the *interpolating* lines, not the declarations. The declarations are `buildWhere()` **:945**, `select_row()` **:344**, `delete_table()` **:463**. The stated numbers all land exactly on the SQL-building line, so the prior analysis was reading the same code — just labelling the statement rather than the function. |
| "classes which extended the description of their related table" | **Directionally right, but nothing extended the query builder.** See §1.3 — this is the single most decisive finding. |
| `db_encode()` undefined, `buildDeleteQuery()` undefined | **Both confirmed.** See §7. `buildUpdateQuery()` is also undefined (4 call sites). |

---

## 1. How it actually worked

### 1.1 The intended hierarchy

```
origin                      class.origin.php:??  — reflection/property bag
  └── MODEL                 class.MODEL.php:27   — data dictionary + array clause builders + CRUD
        └── fa_MODEL        class.fa_MODEL.php:13 — sets company_prefix = TB_PREF
              └── (nothing)
```

The user's memory is a faithful description of the **design intent**, expressed in the
`MODEL` property block (`class.MODEL.php:39-63`):

```php
39: var $table_details;   //!< array definition details about the table
41: var $fields_array;    //!< array
42: /***GENERICTABLE***/
43: var $select_array;
44: var $from_array;
45: var $where_array;
46: var $groupby_array;
47: var $having_array;
48: var $orderby_array;
49: var $sort_dir;        //!< ASC or DESC
50: var $limit;
55: var $join_array;
56: protected $select_clause;   //!< string SQL sub-string (clause)
...
63: protected $join_clause;
```

Each clause is built by a small method that reads its array and sets its string
counterpart, and `buildSelectQuery()` (`:1175`) concatenates them:

```php
1282: $this->sql = $this->select_clause
1283:     . $this->from_clause
1284:     . $this->where_clause
1285:     . $this->groupby_clause
1286:     . $this->having_clause
1287:     . $this->orderby_clause
1288:     . $this->limit_clause;
```

`select_table()` (`:382`) is the *other*, older API and is a completely separate code
path from the clause builders — it does not call any of them.

### 1.2 The real array shapes

| Array | Shape | Evidence |
|---|---|---|
| `select_array` | flat list of **raw SQL fragments** — column names, `*`, or whole expressions with aliases | `class.fa_stock_moves.php:149-150`: `$this->select_array = array( '*' ); $this->select_array[] = "abs( sum( qty ) ) as sum";` |
| `from_array` | flat list of **raw table names**, already carrying `TB_PREF` | `class.fa_bank_trans.php:107`: `$this->from_array[] = $this->table_details['tablename'];` and `class.fa_users.php:134`: `$this->from_array = array( TB_PREF . 'stock_master' );` |
| `where_array` | `column => value` (scalar), **or** two different tuple forms (see §2) | `class.fa_stock_moves.php:110-112`: `$this->where_array['stock_id'] = $stock_id;` |
| `groupby_array` / `orderby_array` | flat list of raw column strings | `class.fa_stock_moves.php:157`: `$this->groupby_array[] = "stock_id";` |
| `having_array` | flat list (identical treatment to groupby) | `class.MODEL.php:1098-1107` |
| `join_array` | list of 5-key associative rows, order-significant | see §1.4 |

The whole "query" was therefore **object state, mutated in place, then compiled** —
exactly the "arrays as a poor-man's builder" pattern.

### 1.3 The fatal structural finding: nothing extended `MODEL`

```
$ rg 'extends fa_MODEL|extends MODEL\b' --glob '*.php' ~/Documents
./ksf_modules_common/class.fa_MODEL.php:13:class fa_MODEL extends MODEL
./ksf_FA_Classes/legacy/class.fa_MODEL.php:13:class fa_MODEL extends MODEL
```

`fa_MODEL` is the **only** subclass of `MODEL` in existence, and **nothing anywhere
subclasses `fa_MODEL`**. So the array-driven builder had **zero** subclasses. The
"subclass replaces `select_array` / `from_array` as needed" pattern from the user's
memory was **never realised in any shipped code**.

Worse — and this is what makes the builder provably dead rather than merely unused:

| Class calling `buildSelectQuery()` | Actually extends | Has the method? |
|---|---|---|
| `fa_stock_moves` (`class.fa_stock_moves.php:22`) | `table_interface` | **No** |
| `fa_stock_category` (`class.fa_stock_category.php:23`) | `fa_table_wrapper` → `table_interface` | **No** |
| `fa_bank_trans`, `fa_prices`, `fa_users`, `fa_loc_stock`, `fa_sales_order_details` | `table_interface` | **No** |
| `fa_dimensions`, `fa_documents`, `fa_purch_orders`, `fa_sales_orders`, `fa_salesman`, `fa_shippers`, `fa_purchase_order_details`, `fa_document_type` | `fa_table_wrapper` → `table_interface` | **No** |

`rg 'function build.*Query' --glob '!vendor' .` returns exactly one hit in the whole
tree: `class.MODEL.php:1175  function buildSelectQuery(...)`. `table_interface`
(`class.table_interface.php:36`) has **no** `build*` method, **no** `$sql` property, and
**no** `db_fetch()` method — yet `class.fa_stock_moves.php:177` calls
`return $this->db_fetch( $res );`.

> **Every one of the 15 files that call `buildSelectQuery()` would fatal with
> "Call to undefined method".** The array-driven query builder was not merely unused —
> it was unreachable from every class in its own repository. The `MODEL` class was
> superseded by `table_interface` for real use (see the comment at `class.MODEL.php:13-14`:
> *"A lot of the code inherited from generictable class framework, migrated out of
> table_interface"*), but the clause builders were migrated with it and the subclasses
> were not re-pointed.

The one genuine subclass pattern in the tree is `class pod_test extends fa_stock_category`
(`class.fa_stock_category.php:190`), which does exactly what the user remembers —
mutates the inherited arrays and reuses the inherited builders:

```php
190: class pod_test extends fa_stock_category
193:     parent::__construct;
194:     $this->clear_sql_vars();
195:     $this->order2deliverydays();
197:     var_dump( $this->sql );
```
…but it is a commented-out test harness (`/**********TESTING****/`, and the whole
`fa_stock_moves` testing block at `:242` is inside `/* */`).

### 1.4 Joins: built, then thrown away

Joins **were** supported in intent. `buildJoin()` (`:1129`) documents a 5-key row shape:

```php
1118: * Expecting
1119: * 	array[0] = array( 'table1' => tbname,
1120: * 			'table2' => tbname,
1121: * 			'field1 => fdname,
1122: * 			'field2 => fdname,
1123: * 			'type' => INNER_JOIN /...
```

and assembles it by walking a **fixed key order** with special-cased glue:

```php
1145: $FIELDS = array( 'table1', 'type', 'table2', 'field1', 'field2' );
1152:     foreach( $FIELDS as $col )
1156:         $sql .= $arr[$col] . " ";
1157:         if( $col == 'table2' )      $sql .= "on ";
1159:         else if( $col == 'field1' )  $sql .= "= ";
1165:         else throw new Exception( "Mandatory field $col not set" );
```

**But `buildSelectQuery()` never concatenates `$this->join_clause`.** Look at
`:1282-1288` in §1.1 — the join clause is absent from the assembly. `buildJoin()` is
called at `:1255` inside a `try` whose non-`KSF_FIELD_NOT_SET` branch is an **empty**
`else` (`:1264-1266`), so a successful join build is silently discarded and a failed one
is silently swallowed.

> **Verdict: joins were half-implemented and never emitted.** Any join written in the
> documented `table1/type/table2/field1/field2` shape would produce SQL with the
> joined table missing from the `FROM` entirely. There is also **no call site anywhere**
> in the tree that populates `$join_array` — `rg 'join_array'` finds only the
> declaration (`:55`) and the builder (`:1129`).

---

## 2. The operator vocabulary

### 2.1 What the compiler supported: exactly one operator, `=`

`buildWhere()` in full (`:963-974`):

```php
963:     foreach( $this->where_array as $col => $val )
964:     {
965:         if( $b_validate_in_table )
966:         {
967:         //	if( $val != "*"  AND ! in_array( $tabledef, $val ) )
968:         //	throw new Exception( "Select variable not in table definition", KSF_FIELD_NOT_CLASS_VAR );
969:         }
970:         if( 0 < $fieldcount )
971:             $sql .= " and ";
972:         $sql .= "$col = '$val' ";
973:         $fieldcount++;
974:     }
```

There is **no operator switch, no operator lookup table, no comparison of `$val` against
a keyword**. The `=` is a hard-coded character in the format string at `:972`. There is
no `IN`, `LIKE`, `<`, `>`, `!=`, `BETWEEN`, `IS NULL` anywhere in the compiler.

### 2.2 What callers *wrote* — and what it compiled to

Four tuple shapes appear in call sites. **None of them were ever handled.**

| Call site | Written as | Compiles to |
|---|---|---|
| `class.fa_bank_trans.php:109` | `$this->where_array['trans_date'] = array( 'lte', $sql_date);` | `trans_date = 'Array'` |
| `class.fa_stock_moves.php:209` | `$this->where_array['tran_date'] = array( 'gt', $startdate );` | `tran_date = 'Array'` |
| `class.fa_stock_moves.php:211` | `$this->where_array['tran_date'] = array( 'lt', $enddate );` | `tran_date = 'Array'` |
| `class.fa_prices.php:122` | `$this->where_array['stock_id'] = array( 'like', $stock_id_match );` | `stock_id = 'Array'` |
| `class.fa_stock_category.php:180` | `$this->where_array['dflt_dim1']['in'] = $instring;` | `dflt_dim1 = 'Array'` |
| `class.fa_users.php:135`, `fa_tax_types.php:66`, `fa_tax_groups.php:64` | `array( "like" => $stock_id_match )` | `stock_id = 'Array'` |

Note the **two incompatible tuple conventions** coexisting: positional
`array('gt', $x)` (`fa_stock_moves:209`) and associative `array('like' => $x)`
(`fa_prices:122`), plus a third, nested-key form `['dflt_dim1']['in']` that collides
with the outer `column => value` shape and **overwrites** any earlier predicate for the
same column. `class.fa_stock_moves.php:209` and `:211` assign to the **same key**
`$this->where_array['tran_date']` in sequence, so the `lt` overwrites the `gt` —
a date-range filter that silently collapses to one bound.

**Verified by execution** (PHP 8.1, reproducing `:972` verbatim):

```
PHP Warning:  Array to string conversion
buildWhere tuple  => [trans_date = 'Array' ]
```

> **Verdict on the prior finding: CONFIRMED, and worse than stated.** The `lte` tuple
> is not "accepted as a shape but rendered wrong" — *no* tuple is recognised, and the
> `$b_validate_in_table` guard that might have caught it is **commented out** at
> `:967-968` (and identically at `:892-893` in `buildSelect`, `:1012-1013` in
> `buildOrderBy`, `:1057-1058` in `buildGroupBy`). The parameter is threaded through
> `buildSelectQuery()` → every builder → and **never used**.

### 2.3 Two more vocabulary gaps

- **`sort_dir` (`:49`) is declared and never read.** `buildOrderBy()` never consults it,
  so there is no `ASC`/`DESC` support at all. Worse, `clear_sql_vars()` at `:1301` sets
  `$this->sortdir = "ASC"` — a **different, undeclared property** (typo: missing `_`).
- **`buildLimit()` (`:824`)** has a PHP operator-precedence bug: `.` binds looser than
  `-`, so `(int)$startrow - 1 . "," . (int)$numrows` evaluates as arithmetic-then-concat.

**Verified by execution:**
```
buildOrderBy      => [ ORDER BY 'tran_date' ]
buildLimit        => [ LIMIT -1,10]
```
`ORDER BY 'tran_date'` sorts by a string constant — valid SQL, silently no-op.
`LIMIT -1,10` is invalid SQL. **Every paged query through this builder was broken.**

---

## 3. SQL injection assessment — the verdict

**Confirmed, unescaped, and trivially exploitable.** This is the finding that decides
the matter: not one of the legacy design's *patterns* may be revived, only its *ideas*.

### 3.1 `buildWhere()` — raw interpolation, no escaping, no binding

`class.MODEL.php:972`
```php
$sql .= "$col = '$val' ";
```
Neither `$col` nor `$val` is escaped, quoted, whitelisted, or parameterised. The
hand-written quotes around `$val` are the *only* defence, and they are defeated by a
single quote in the value.

**Verified by execution:**
```
buildWhere inject => [ tran_date = 'x' OR '1'='1' ]
```
A `$val` of `x' OR '1'='1'` yields a tautology — **every row in the table is returned**.
The `where_array` was the *primary* query filter for the whole framework.

### 3.2 `buildOrderBy()` / `buildGroupBy()` / `buildHaving()` — same, plus broken

```php
class.MODEL.php:1018:   $sql .= " '$col' ";
class.MODEL.php:1062:   $sql .= " '$col' ";
class.MODEL.php:1104:   $sql .= " '$col' ";
```
Raw string fragments, single-quoted, unescaped. Because they are *fragments* rather
than values, the intended use was `orderBy_array[] = 'd.item_code'` — i.e. **raw SQL by
design**, with quoting added on top, producing both an injection sink (`:1018` for
`ORDER BY`) and a correctness defect (`GROUP BY 'col'` collapses the entire result set
to one arbitrary row).

### 3.3 `select_row()` and `delete_table()` — raw property interpolation

```php
class.MODEL.php:359:  $sql = "SELECT * from `" . $this->table_details['tablename'] . "` WHERE $key='" . $this->$key . "'";
class.MODEL.php:472:  $sql = "DELETE from " . $this->table_details['tablename'] . " WHERE " . $pri . " = '" . $this->$pri . "'";
```
The **same two lines exist in the older base class**, so this is not a regression in a
newer file:
```php
class.table_interface.php:185:  $sql = "SELECT * from `" . $this->table_details['tablename'] . "` WHERE $key='" . $this->$key . "'";
class.table_interface.php:296:  $sql = "DELETE from " . $this->table_details['tablename'] . " WHERE " . $pri . " = '" . $this->$pri . "'";
```
`$this->$key` is whatever was last `set()` on the object — which is populated straight
from a request (`assoc2var()` `:1315`, `array2var()` `:1470`, `stdClass2var()` `:1333`).
So: **`DELETE … WHERE <pk> = '<attacker value>'`** off a value that arrived from input.
Note `:359` and `:472` also fail to quote the *identifier* `$key`/`$pri`, unlike the
table name which is backticked.

### 3.4 Where escaping *was* attempted — and where it was skipped

`insert_table()`, `update_table()` and `ReplaceQuery()` **do** call `db_escape()`
(`:584`, `:503`, `:855`), so the write paths were defended and the read/delete paths
were not. That asymmetry is the tell: escaping was applied ad hoc per method, not
enforced by an abstraction. Two consequences:

- **`update_table()` `:508` is broken anyway:**
  ```php
  $sql .= " WHERE '" . $pri . "'='" . $this->$pri . "'";
  ```
  It quotes the *primary key column name* as if it were a value (`WHERE 'id'='5'`),
  comparing a constant — **no row ever matches, so `update_table()` silently updates
  zero rows.** Identical bug at `class.table_interface.php:330`.
- **`select_table()` `:413` calls an undefined `db_encode()`** — see §7.

### 3.5 Two more, for completeness

- **`check_table_for_id()` `:540`**:
  ```php
  $sql = "select count('id') as count from $this->table_details['tablename']";
  ```
  PHP simple interpolation cannot parse `$this->prop['key']` — it stops at the `[`.
  **Verified by execution:** the SQL becomes `… from Array['tablename']`. Fatal.
  (The next line, `:541`, is a correctly concatenated string and is fine.)
- **`class.generic_fa_interface_model.php:218-246`** — four query-building helpers
  (`replace_field_substring_query`, `replace_field_start_substring_query`,
  `field_append_string_query`, `field_prepend_string_query`) interpolate `$field`,
  `$oldstring`, `$newstring` and `$string` raw into `UPDATE … SET … LIKE '%…%'`. Same
  class of defect, different file.

**Net verdict: the legacy framework had no parameter binding anywhere, no identifier
quoting discipline, and no central choke point through which escaping could be
enforced.** `ksf_common_db`'s `FaDbAdapter::bindParams()` (`:87-115`) resolving every
`?`/`:name` through `quote()` → `mysqli_real_escape_string` (`:120-138`) is a categorically
different design, and is the reason the modern package is safe.

---

## 4. What is worth keeping vs. what must be discarded

### 4.1 Subclass-overrides-the-parent (template method) — **keep the shape, reject this instance**

The *shape* is right: a base class that owns the algorithm and a subclass that supplies
data is textbook Template Method, and it is what makes a table's query definitions
reusable. `QueryBuilder`'s own docblock names this lineage
(`src/Query/QueryBuilder.php:15-18`).

The *instantiation* is wrong in four ways, and it is worth naming them so the mistake is
not repeated:

1. **The override target was mutable object state, not input.** A subclass had to assign
   `$this->select_array` as a *side effect* and then hope `buildSelectQuery()` was called
   in the right order. `class.fa_stock_moves.php:205-212` shows the failure mode: three
   methods mutate shared state in sequence, and the two `tran_date` assignments overwrite
   each other. State that a caller can mutate between compile steps is not a template
   method, it is a shared buffer.
2. **`clear_sql_vars()` had to be called first, by convention.** `fa_stock_moves.php:108,125,231`
   all open with `$this->clear_sql_vars()`. A forgotten call silently *merges* into the
   previous query. Note `clear_sql_vars()` also **fails to clear `join_array`** (`:1292-1301`)
   and sets the misspelled `$this->sortdir` (`:1301`).
3. **Nothing extends `MODEL`** (§1.3) — so the pattern was never exercised, and the one
   subclass that exists (`pod_test`) is dead commented-out test code.
4. **It mixed "definition" with "execution".** `select_table()` (`:382`) both declares and
   runs a query, while `buildSelectQuery()` only compiles and requires a separate
   `$this->query()` call. Two incompatible lifecycles in one class.

**Verdict: keep the concept (a table declares its queries; callers run them), reject the
mechanism (inherited mutable arrays + compile-then-run).** In the modern design this
becomes a query object returned by a factory, not state on a table object.

### 4.2 Declarative field lists — **keep, and this is the strongest idea to survive**

`fields_array` (`class.MODEL.php:41`) was a real data dictionary with
`name`/`type`/`null`/`auto_increment`/`default`/`readwrite`/`external_name`
(see a full instance at `class.fa_crm_persons_model.php:58-70`), plus
`table_details['tablename'|'primarykey'|'index'|'engine'|'charset']`. It drove
`create_table()` (`:601`), `alter_table()` (`:681`), `select_row()` hydration (`:362-369`),
`insert_table()` (`:574`), `build_write_properties_array()` (`:1389`) and the read-only
filter (`:1400-1407`).

**This survived verbatim into `TableDefinition` and is the one part already done right:**
`src/Dictionary/TableDefinition.php` has `column()`, `index()`, `columns()` (`:101`),
`hasColumn()` (`:112`), `writableColumns()` (`:122`), `name()` (`:155`), `primaryKey()`
(`:165`) and `createSql()`/`insertSql()`/`updateSql()`/`deleteSql()`.

The specific legacy features worth carrying forward:

| Feature | Legacy | Modern equivalent |
|---|---|---|
| `readwrite => 'read'` marking generated columns (`updated_ts`) | `:1381` | `TableDefinition::writableColumns()` |
| `external_name` mapping a column to a different name for external systems (WOO, SuiteCRM) | `:1432-1448` | **Not yet in `TableDefinition`.** Needed for column views. |
| Primary key declaration driving `select_row`/hydration | `:347-369` | `TableDefinition::primaryKey()` |
| One `build_interestedin()` to declare lifecycle participation | `:110-115` | Workflow hooks (separate concern — see below) |

**Two things to drop:** the type strings were free-form (`'varchar(' . DESCRIPTION_LENGTH . ')'`
at `class.fa_crm_persons_model.php:55` — a runtime string, not a declared type), and
`create_table()` hard-defaults to `ENGINE=MyISAM` (`:664`) and `utf8` (`:672`), both of
which are now wrong (`TableDefinition.php:46` correctly defaults to `InnoDB`/`utf8mb4`).

### 4.3 The operator-by-keyword idea — **keep the intent, it is the best thing here**

The framework *intended* `['lte', $date]` to mean `trans_date <= ?`. That intent is
right and it is exactly what a fluent builder should expose — the compiler simply never
implemented it.

**Mapping to a fluent API:**

| Legacy (intended) | Modern fluent | Notes |
|---|---|---|
| `['lte', $v]` | `->whereLte('col', $v)` / `->lte('col', $v)` | ≤ |
| `['lt', $v]` | `->lt('col', $v)` | < |
| `['gte', $v]` | `->gte('col', $v)` | ≥ |
| `['gt', $v]` | `->gt('col', $v)` | > |
| `['like', $v]` | `->like('col', $v)` | `%` wildcards must be the **caller's** choice, not added by the builder |
| `['in', $sqlfrag]` | `->whereIn('col', $v1, $v2, …)` | **Must generate one placeholder per element.** The legacy version had the caller hand-build the `IN (…)` text (`class.fa_stock_category.php:180`, via `array_to_sql_in()`) — that is exactly the raw-fragment pattern that must not survive. |
| `['=', $v]` (scalar form) | `->whereEq('col', $v)` | |
| *never expressed* | `->whereNull()` / `->whereNotNull()` / `->whereBetween()` / `->orWhere*()` / `->whereRaw()` (explicit, audited) | `orWhere` is genuinely missing — the legacy builder was AND-only (`:971`). |

**Two rules the modern version must enforce that the legacy one had no concept of:**

1. **Column names are identifiers, not values.** `->lte('col', $v)` must emit `` `col` <= ? ``.
   The legacy `ORDER BY 'col'` (`:1018`) shows the failure mode when you treat an
   identifier as a value — it becomes a constant.
2. **`whereIn()` expands to N placeholders, always.** Never `IN (:ids)` with a
   pre-joined string.

### 4.4 Other genuinely good ideas

- **`getPrimaryKey()` (`:775`) throwing a typed exception when the dictionary is
  incomplete.** Error-on-missing-metadata is right and should survive. (Though the
  legacy version had **two different exception codes** for the same condition —
  `KSF_PRIKEY_NOT_DEFINED` at `:352` and `KSF_PRIKEY_NOT_SET` at `:357` for
  "not declared" vs "not assigned" — which is actually a good distinction that got lost
  in `table_interface.php:182-184`, where both messages are plain strings.)
- **`define_table()` (`:1363-1388`) deriving the table name from the class name**, with
  a documented `model_` prefix-strip rule (`:1369-1377`). Convention-over-configuration
  for the table↔class binding. Worth keeping *only* as an explicit, inspectable
  declaration — magic name derivation is exactly the kind of thing that makes a
  builder unable to know what table it is selecting from (§5.3).
- **`assoc2var()` / `stdClass2var()` / `var2caller()` (`:1315`, `:1333`, `:1344`)** —
  hydrating declared fields from a result row and ignoring undeclared keys. That
  whitelisting discipline is worth keeping; the legacy version did it by looping
  `fields_array`, which is right.

### 4.5 The lifecycle/eventloop idea — keep the concept, it was never wired

`build_interestedin()` (`:110-115`) declares interest in `NOTIFY_INIT_TABLES` mapped to
`create_table`. The full dispatch census in `class.MODEL.php`:

```
164  NOTIFY_LOG_DEBUG      ← logging noise, 164 occurrences
  2  NOTIFY_LOG_ERROR
  1  NOTIFY_INIT_TABLES    ← the only real declaration
```

So: **one** declared lifecycle event, and it is table *creation*, not CRUD. Nothing
fires pre/post insert, update, or delete. The `@deprecated` banner at `:20-25` is honest.
The modern `WorkflowHooksTrait` / `CrudOperationsTrait` (per `AGENTS.md:159-176`) is
the correct successor. **Do not resurrect `tell_eventloop()`.**

---

## 5. Mapping to the modern fluent design

### 5.1 Legacy query #1 → `QueryBuilder`

**Legacy** (`class.fa_bank_trans.php:105-113`), the EOD balance query:

```php
$this->select_array[] = "sum(amount)";
$this->from_array[] = $this->table_details['tablename'];
$this->where_array['bank_act'] = $this->bank_act;
$this->where_array['trans_date'] = array( 'lte', $sql_date);   // → renders 'Array'
$this->buildSelectQuery();
$this->query( "Can't calculate EOD balance", "select" );
```

**Modern, against today's `QueryBuilder`:**

```php
$rows = $qb->select(['SUM(amount) AS amount'])
         ->from(TB_PREF . 'bank_trans')
         ->where('bank_act = :acct',   ['acct' => $bankAccount])
         ->where('trans_date <= :dte', ['dte' => $sqlDate])   // lte → a real <=
         ->fetch($db);
```
Every value is bound; `trans_date <= ?` actually works; `FaDbAdapter` escapes and
prefixes. The `fetch()` convenience (`QueryBuilder.php:225-228`) collapses the legacy
`buildSelectQuery()` + `query()` two-step.

### 5.2 The same query as a legacy subclass would have expressed it

**Legacy "subclass variant"** (the pattern the user remembers — a subclass replacing the
inherited arrays):

```php
class fa_bank_trans_eod extends fa_bank_trans {
    function __construct() {
        parent::__construct();
        $this->select_array   = array('sum(amount)');
        $this->from_array     = array(TB_PREF . 'bank_trans');
        $this->where_array    = array();          // clobbers the parent's
        $this->where_array['bank_act']   = $this->bank_act;
        $this->where_array['trans_date'] = array('lte', $date);
    }
}
```
Two failure modes visible in the shape itself: the subclass **clobbers** the parent's
arrays rather than extending them, and `$this->bank_act` is read at construct time so
the query is frozen before the object is populated.

**Modern — same specialisation, composition instead of inheritance:**

```php
final class BankTransRepository
{
    /** Query for EOD balance, parameterised by the *inputs*, not by object state. */
    public function eodBalance(string $bankAccount, string $asOfDate): array
    {
        return $this->qb->select(['SUM(amount) AS amount'])
                       ->from(TB_PREF . 'bank_trans')
                       ->where('bank_act = :acct', ['acct' => $bankAccount])
                       ->where('trans_date <= :dte', ['dte' => $asOfDate])
                       ->fetch($this->db);
    }
}
```
The "specialised query" is now a **named method on a repository**, not a subclass whose
constructor mutates inherited state. This is strictly better: it is testable, it takes
its inputs as arguments, it cannot leak state between calls, and it costs no inheritance.

For a genuinely *shared* query the modern form is a private helper plus a query object,
never a class hierarchy:

```php
private function baseQuery(): QueryBuilder {
    return $this->qb->from(TB_PREF . 'bank_trans');
}
// caller: $this->baseQuery()->select(['SUM(amount)'])->where(...)->fetch($this->db);
```

### 5.3 Against the planned table-declaring builder

`QueryBuilder` today **cannot** express the ACL predicate, for one mechanical reason:

| Fact | Location |
|---|---|
| `$from` is a `private string|null` | `src/Query/QueryBuilder.php:29`, set by `from()` at `:83-88` |
| **No public getter for `$select`** | — |
| **No public getter for `$from`** | — |
| Only `toSql()` and `getParams()` are public inspection points | `:174`, `:214` |
| `toSql()` is a string concatenator, not a clause model | `:174-207` |
| `join(string $clause)` takes one opaque fragment | `:112-117` |

**Confirmed: no getters for the select list or the table.** The consequence is precise
and it is the same one recorded in `Requirements/FR-ACL-001-02-row-acl-predicate.md:47`:

> **A builder that cannot read its own `FROM` cannot key a policy lookup on it.**

So a row-ACL layer cannot be bolted onto `QueryBuilder` as a decorator — there is nothing
to decorate *with*. It has to be a capability of the builder itself, which means the
builder must first **know** the table. That is exactly what `ACL_Two_Approaches.md` §5.2
Phase 1 ("Builder introspection, no behaviour change: read-only accessors… Ship v1.1.0")
sequences first, and why the minimal declaration shape in `FR-ACL-001-02:216-219` is
`fromTable('crm_contacts')->rowAcl('crm','contacts')->select([...])`.

**The declared-table form for §5.1's query, once Phase 1 lands:**

```php
// Before (today)                        After (table-declaring)
$qb->from(TB_PREF.'bank_trans')          $qb->fromTable('bank_trans')      // logical, unprefixed
    ->where('bank_act = :acct', …)           ->rowAcl('banking', 'trans')  // module, record_type
    ->where('trans_date <= :dte', …)         ->where('bank_act = :acct', …)
                                             ->where('trans_date <= :dte', …);
```

Note `fromTable('bank_trans')` must be **unprefixed** — `FaDbAdapter::prefixTables()`
(`:49-78`) adds `TB_PREF` itself, and hardcoding `0_` breaks company 2+
(`FR-ACL-001-02:67`).

### 5.4 `SRP_DB_Query` — what it actually is

**Correction to the brief.** `SRP_DB_Query` is **not** a planned builder in
`ksf-common-db`. Per `Requirements/FR-ACL-001-03-two-stage-enforcement-migration.md:41`
it is the target of a **Stage-1 mechanical rewrite of RBAC's own procedural call sites**:

```
sed -i 's/\bdb_query(/SRP_DB_Query::db_query(/g'
```

i.e. a drop-in replacement for FA's `db_query()` that injects the ACL predicate. Its
naming is **UNRESOLVED** — `Requirements/OPEN-QUESTIONS.md:212-223`, **Q10** asks whether
`SRP_DB_Query` is a hard requirement or a placeholder.

The two layers are complementary and should not be conflated:

| Layer | Job | Transport |
|---|---|---|
| `SRP_DB_Query::db_query()` (RBAC) | Catch procedural/raw SQL that bypasses the builder. Defence in depth. | FA `db_*` |
| `QueryBuilder::rowAcl()` (ksf-common-db) | Emit the predicate for queries that *do* go through the builder. The primary control. | via `DbConnectionInterface` |

The builder cannot catch `SRP_DB_Query`'s traffic and vice versa; both are needed.

---

## 6. What the modern design must do that the legacy one could not

### 6.1 Row ACL — emit a predicate given a declared table

The legacy builder's model was **"the caller has already decided which rows"** — `where_array`
*was* the filter, and nothing outside the class could add to it or even read it. There was
no seam for a cross-cutting predicate. Today's requirement
(`FR-ACL-001-02`, `BR-ACL-001` R7: *one data query per request*) needs the builder to
**append** three `EXISTS` subqueries to whatever the caller wrote:

```sql
WHERE … AND (
    EXISTS (SELECT 1 FROM rbac_record_owner  o  WHERE … o.record_id = c.id AND o.owner_id = ?)
 OR EXISTS (SELECT 1 FROM rbac_record_group  rg WHERE … rg.group_id IN (?, ?, ?, ?))
 OR EXISTS (SELECT 1 FROM rbac_group_policy  gp WHERE … gp.row_level IN ('other','group','owner_only'))
)
```

Three requirements the legacy shape actively prevented:

1. **Append-only injection.** The predicate must be added *after* the caller is done, so
   `where()` cannot be final until compile time. Legacy mutated shared arrays instead.
2. **Refuse-to-emit, not emit-unfiltered.** `FR-ACL-001-02:196-202`: if the table is
   ACL-managed and the policy cache cannot produce a policy, the builder must **throw**.
   A builder that silently omits a clause is fail-open — the worst possible default, and
   exactly the shape of the legacy "required field not set → skip the clause" handling
   (`buildSelectQuery()` `:1198-1207`, `:1213-1219`, `:1225-1230`, `:1242-1247` — every
   optional clause swallows `KSF_FIELD_NOT_SET` and continues).
3. **`EXISTS`, never a comma-join or CTE.** `FaDbAdapter::prefixTables()`'s regex
   (`src/Adapter/FaDbAdapter.php:56`) only prefixes the token after `FROM|JOIN|INTO|UPDATE|TABLE`,
   so `WITH` is out and `IN (SELECT …)` leaves inner tables unprefixed
   (`FR-ACL-001-02:61-67`). **The legacy builder's comma-join `from_array`
   (`class.MODEL.php:925-931` — `implode(", ")`) would be exactly the wrong shape here.**

### 6.2 Column views / column ACL

`FR-ACL-001-04` + `ACL_Two_Approaches.md` §3.7 require the select list to be *derived*
from the data dictionary and a policy, with `SELECT *` **rejected** (not merely discouraged)
and denied columns replaced by `NULL AS <col>`. That needs:

- the **select list readable and mutable** — `QueryBuilder` exposes neither (`:26`, no getter);
- an **alias→table map** — you cannot write `SELECT c.ssn` for a policy lookup on table
  `crm_contacts` if the builder stored `from()` as an opaque string;
- the `external_name` mapping from the legacy dictionary (§4.2), which
  `TableDefinition` does **not** yet carry.

### 6.3 Parameter binding — the thing the legacy design fundamentally lacked

FA has **no prepared statements**. `FaDbAdapter` closes the gap by resolving placeholders
to escaped literals before `db_query()`:

- `bindParams()` (`:87-115`) handles both `:name` (assoc) and `?` (positional), with a
  safe fallback when the placeholder count mismatches (`:105-107`);
- `quote()` (`:120-138`) returns `NULL` for null, casts int/float, maps bool to `1`/`0`,
  and otherwise `mysqli_real_escape_string($db, …)` — falling back to `addslashes()` if
  the global `$db` is unset (`:132-135`).

The legacy framework had **no equivalent choke point**. `db_escape()` appeared in three
methods (`:503`, `:584`, `:855`) and nowhere else; the read path, the delete path and all
three fragment clauses were raw. That is the structural difference: *binding must be
something you cannot forget*, not something each method remembers to do.

**One caveat worth recording:** `quote()`'s `addslashes()` fallback (`:135`) is **not**
equivalent to `mysqli_real_escape_string` — it does not handle multi-byte character sets
and is known to be bypassable under some configurations. If `$db` is not a live mysqli
link, the "safe" path degrades to a weaker one silently. This should be an explicit
throw, not a fallback. *(Noted as an observation, not verified against a live attack.)*

---

## 7. Abandoned / broken code found along the way

All verified by `rg` over the whole tree (excluding `vendor/`).

| # | Item | Evidence | Verdict |
|---|---|---|---|
| 1 | **`db_encode()` called, never defined** | called at `class.MODEL.php:413` and `class.table_interface.php:249`; `rg 'function db_encode'` → **0 hits**. It is not an FA core function (FA has `db_escape`). | **Confirmed.** Both call sites are inside `select_table()`, so **`select_table()` fatals on any `$where`** — the one method that *was* reachable from real subclasses. |
| 2 | **`buildDeleteQuery()` called, never defined** | `class.fa_stock_moves.php:133`, `class.fa_sales_order_details.php:117`, `class.fa_prices.php:203`, `class.fa_loc_stock.php:75` — **4 call sites**. `rg 'function build.*Query'` → only `buildSelectQuery` at `class.MODEL.php:1175`. | **Confirmed** — 4 files, as the prior note said. |
| 3 | **`buildUpdateQuery()` called, never defined** (not in the prior note) | `class.fa_stock_moves.php:115`, `class.fa_prices.php:123,145,185` — **4 call sites**. Same grep. | **New finding.** Together with #2: **8 call sites into two non-existent methods.** |
| 4 | **`$this->db_fetch()` called as a method, never defined** (not in the prior note) | `class.fa_stock_moves.php:135,177,203,214,222,236`; `db_fetch` exists only as FA's **global function** (`class.table_interface.php:187` uses it bare). | **New finding.** Fatal. |
| 5 | **`class fa_document_type` declared in two files** | `class.fa_documents.php:15` and `class.fa_document_type.php:15`, both `extends fa_table_wrapper`. | **Copy-paste bug.** Loading both fatals with a redeclaration error. |
| 6 | **`class pod_test` declared in 7 files** | `class.fa_dimensions.php:135`, `fa_purchase_order_details.php:263`, `fa_purch_order_details.php:263`, `fa_purch_orders.php:257`, `fa_salesman.php:255`, `fa_shippers.php:251`, `fa_stock_category.php:190` | **Redeclaration fatal** if any two are loaded together. Dead test scaffolding shipped alongside production classes. |
| 7 | `clear_sql_vars()` does not clear `join_array`; sets misspelled `$this->sortdir` | `:1292-1301` — `join_array` absent from the reset list; `:1301` writes `sortdir` while `:49` declares `sort_dir` | Minor, but a real state-leak bug. |
| 8 | `buildHaving()` (`:1082`) takes **no** `$b_validate_in_table` parameter but is **called with one** at `:1238` | Signature vs call site | Harmless in PHP (extra args ignored) but shows the clause API drifted. |
| 9 | `$this->select_array() = array('*')` — **array literal on a method call** | `class.fa_stock_moves.php:126` | Fatal (`Cannot use object of type array as function`). `:126` is inside `delete_item_price()`, which also calls the undefined `buildDeleteQuery()` (#2). |
| 10 | `clear_sql_vars()` sets `$this->limit_startrows` (plural, undeclared) | `:1303` vs `:51` | State never reset. |
| 11 | `alter_table()` builds SQL but ignores `$sql` prefix content — it executes `ALTER TABLE t\n` with an `ADD COLUMN (...)` fragment concatenated but never verified | `:693-735` | Latent; low priority. |
| 12 | `db_result2rows()` iterates `$result` (undefined) and reads `$this->header_row`/`$this->col_type` (undeclared) | `:122-163` | Dead VIEW functionality. |
| 13 | Composer PSR-4 points at `src/`, which **does not exist** | `composer.json` — `"Ksfraser\\ModulesCommon\\": "src/"`; the tree is flat `class.*.php` at the root | The package is not autoloadable as declared. Consistent with the `no-op` state. |

---

## 8. Summary of verdicts

| Prior claim | Verdict |
|---|---|
| `where_array['trans_date'] = ['lte', $date]` renders as `trans_date = 'Array'` | **Confirmed by execution.** No operator vocabulary exists at all — `=` is a hard-coded character at `class.MODEL.php:972`. Four other tuple shapes in the tree are equally unhandled. |
| `buildWhere()` interpolates values with no escaping | **Confirmed.** `:972`. Executed proof yields `tran_date = 'x' OR '1'='1'` — a working tautology. |
| `buildOrderBy`/`GroupBy`/`Having` interpolate raw | **Confirmed.** `:1018`, `:1062`, `:1104`. |
| `select_row()`/`delete_table()` interpolate raw | **Confirmed.** `:359`, `:472` (and `:185`, `:296` in `table_interface`). |
| `db_encode()` called but never defined | **Confirmed.** `:413`, `class.table_interface.php:249`. |
| `buildDeleteQuery()` called by four files, never defined | **Confirmed.** Plus `buildUpdateQuery()` by four more. |
| Joins supported | **Half.** Designed and built (`:1129`), **never emitted** (`:1282-1288` omits `join_clause`), **never populated** by any call site. |
| Subclasses replace the inherited arrays | **Never happened.** Zero subclasses of `MODEL`/`fa_MODEL` exist. The 15 classes that call `buildSelectQuery()` extend `table_interface`, which does not have it. |

---

## 9. Explicitly unverified

| Item | Status |
|---|---|
| Whether `ksf_modules_common` was ever *loaded* in a running pod (i.e. whether these fatals ever fired) | **Unverified** — no runtime evidence was sought. The static evidence is that the fatals are unavoidable for any code path reaching those methods. |
| Whether any consumer outside `/home/kevin/Documents` (e.g. a deployed `fa_modules/` tree) subclasses `MODEL` | **Unverified** — only `~/Documents` was searched. `ksf_FA_Classes/legacy/class.fa_MODEL.php:13` is the only other `extends MODEL` in that tree, and it is itself a subclass with no children. |
| Any claim about MySQL/MariaDB *execution* of the malformed SQL (e.g. that `GROUP BY 'col'` returns one row) | **Not executed against a database.** Stated from SQL semantics and marked as reasoning, not measurement. |
| The `addslashes()` fallback weakness in `FaDbAdapter::quote()` (`:135`) | **Not demonstrated.** Raised as an observation only. |
| `AGENTS_ARCH.md`'s silence on `ksf_modules_common` being intentional | **Unverified.** `AGENTS.md:130-141` carries the description and cross-references `AGENTS_ARCH.md` for conventions; possibly the legacy write-up was meant to live in one and landed in the other. |
