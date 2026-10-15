# Schema Registry — one declaration, three consumers

> ## ⚠️ §F SUPERSEDED — 2026-10-15, by [`Schema_Codegen_Design.md`](./Schema_Codegen_Design.md)
>
> **Superseded: Part F (the phased plan), and §D.4's `schema_advertise()` /
> `schema_resolve()` *mechanism*.** The runtime-registry mechanism this document
> proposes is replaced by: **generate the schema at development time from the SQL
> files, commit the artefact, and let a unit test compare the committed file to the
> live database.** Nothing parses SQL at runtime. See
> `Schema_Codegen_Design.md` §1–§3, and its §6 for the replacement phased plan.
>
> **NOT superseded — Parts A, B, C, D.1–D.3, D.5 and E remain valid and are relied
> on by the codegen design.** Specifically:
>
> | Kept | Where the codegen design uses it |
> |---|---|
> | §0.1–§0.7 verification (one `TableDefinition` consumer; three query-builder forks; **no column-protection inventory exists**; `QueryBuilder` cannot see its own query; `$select` defaults `['*']`) | §4.2.1, §4.2.2 |
> | §A.6 permissive miss (`unresolved()`) | §3.4.1 — the only permitted degradation |
> | §B.3 **the three `sensitivity` caveats**, including *absence means visible, never hidden* and *a mis-classification is a silent denial* | the overlay's `sensitivity` key (§2.4.2) |
> | §B.4 writable vs derived; §B.5 relationships | the overlay's `writable`/`derived`/`relationships` keys |
> | §C.2 drift detection | §3, the comparison test |
> | §D.1–D.2 (`ksf-common-db` is the right home) | §1.1, the CLI's location |
> | §D.3 the contracts | §4.2, loaded from the committed artefact |
> | §E.1 `QueryBuilder` changes; §E.3 `humanise()` label fallback | §4.2.1, §4.2.2, §5.2 |
>
> The **column-protection inventory §0.3 says is missing** is now supplied by the
> committed overlay's `sensitivity` keys — that problem is *solved* by codegen, not
> by the runtime registry.
>
> **Content below is preserved verbatim, including Part F, so the superseded plan
> remains auditable.**

**Date:** 2026-10-15
**Status:** DESIGN + VERIFICATION. **No production code was written, no hook was
added, no commit was made.**
**Scope:** `ksfraser/ksf-common-db` (`~/Documents/ksf_common_db`, tree
`v1.0.1-1-g31fee8d`), `ksf_FA_ProjectManagement` (the only live
`TableDefinition` consumer), `ksf_FA_RBAC`, `ksf_FA_Calendar`, and the design
docs in this directory.

**Tag key — the same convention used by `Workflow_Engine_Design.md`:**
**[V]** verified against source, a vendor tree, or a grep in this session.
**[D]** proposed design — nothing exists. **[UNVERIFIED]** explicitly not known.
Untagged text is reasoning or a decision.

**The three consumers this serves:**

| # | Consumer | What it needs from a schema declaration |
|---|---|---|
| 1 | Query builder (`QueryBuilder`) | the declared table, so row-ACL can key on it; the column list, so `*` is rejectable or expandable |
| 2 | ACL layer (`ColumnPolicyInterface`, per `Explicit_Column_ACL_API.md`) | per-column classification — which columns are protected |
| 3 | Workflow engine + its UI (`Workflow_Engine_Design.md` §A.2, §D.2) | field labels, types, enums, writability, so the "which field" pickers populate and publish-time validation is real |

Standing decisions applied: `README.md` §1–6 (no cross-module table access;
responders return data, consumers render; contracts are consumer-owned until a
second consumer justifies a package; `E_USER_ERROR` is uncatchable; three repos
per module). `AGENTS.md` (PHP 7.3 floor; `ksf-common-db` must not depend on any
module; FA runtime uses native `db_*`).

---

# PART 0 — Verification first

This part is entirely **[V]**. It materially changes the plan, and one item in
it is a defect nobody has reported.

## 0.1 Is `TableDefinition` used, or dead?

> **Used, but by exactly one module, and that module already contains a live
> instance of exactly the drift this design is meant to prevent (§0.4).**

| Claim | Evidence **[V]** |
|---|---|
| `TableDefinition` exists and is 256 lines | `ksf_common_db/src/Dictionary/TableDefinition.php` |
| It carries **only** `name, type, null, auto_increment, default` per column | `column()` stores that five-key array, `:66-72` |
| `columnDef()` is **private** | `:139` |
| `writableColumns()` excludes **only** `auto_increment` | `:122-131` — the primary key, `created_at`, and derived columns are all "writable" |
| Its unit tests | `tests/Unit/Dictionary/TableDefinitionTest.php` — **5 tests** |

**Consumer census.** Grepping every non-vendor `.php` under
`~/Documents/` and `~/Documents/ksf_Infrastructure/fa_modules` for
`ksfraser\CommonDb` / `Ksfraser\CommonDb`:

| Module | Uses `TableDefinition`? | Uses `QueryBuilder`? |
|---|---|---|
| **`ksf_FA_ProjectManagement`** (dev + deployed) | **Yes** — `src/…/Dictionary/Schema.php`, 10 `TableDefinition`s | Yes — 6 repositories + `ReportService` |
| `ksf_ProjectManagement` (standalone package) | **No** — imports `DbConnectionInterface` only | No |
| `ksf_FA_RBAC` | No | No — hand-written SQL |
| `ksf_FA_Calendar` | No | No |
| `ksf_FA_ManufacturerConsolidation` | No | No |
| `ksf_FA_StockTurnover` | No | No |
| `ksf_FA_PurchaseOrderTracking` | No | No |
| `ksf_FA_Warehouse` | No | No |
| `ksf_FA_ExpenseReport` | **imports a class that does not exist** — see §0.5 | No |

**19 `composer.json` files require `ksfraser/ksf-common-db`. Exactly one module
uses `TableDefinition` or `QueryBuilder`.**

Three separate query builders exist in this stack, which matters for §E:

| Builder | Status |
|---|---|
| `ksfraser\CommonDb\Query\QueryBuilder` | canonical, 240 lines, SELECT-only |
| `ksf_bank_import/src/Ksfraser/{Application,FaBankImport}/database/QueryBuilder.php` | a second, unrelated class |
| `ksf_payment_destinations/src/QueryBuilder/QueryBuilder.php` | a third fork with its own `toFaSql()` using `addslashes()` |

## 0.2 `QueryBuilder` cannot see its own query **[V]**

| Fact | Line |
|---|---|
| `$select` **defaults to `['*']`** | `:26` |
| `from(string $table)` stores an **opaque string** | `:83-88` |
| `toSql()` implodes raw fragments | `:174-207` |
| Public methods: `select, addSelect, from, where, join, groupBy, having, orderBy, limit, toSql, getParams, fetch` — **no getter for `$select` or `$from`** | whole file |
| `TableDefinition` is **never** consulted by the builder | whole file |
| Unit tests | **3** |

`FR-ACL-010-01.md` §5 already states the consequence verbatim: *"A builder that
cannot see its `FROM` cannot key an ACL policy on it."* That is still true and
is the blocker this design must not repeat.

**8 live `select('*')` call sites** exist in `ksf_FA_ProjectManagement`:
`ProjectTypeRepository.php:42,53,63`, `ProjectRepository.php:73`,
`TaskRepository.php:75,114`, `AssignmentRepository.php:83,143`.

## 0.3 The ACL work is blocked on exactly this **[V]**

`ACL_Two_Approaches.md` §6.2, verbatim:

> **There is no column-protection inventory.** Nothing in this stack states which
> columns are sensitive. Specifically: `TableDefinition` has no `sensitivity`
> field and **no `TableDefinition` in any module declares one**.

Its three other findings:

- `ACL_Two_Approaches.md` §3.7: *"A view **must not** get a `TableDefinition`"* —
  a view has no writable columns and no independent DDL, so a **separate
  column-list-shaped dictionary type is already required**. The design in §D of
  this document is that type, generalised.
- `Explicit_Column_ACL_API.md` §3.1 `FR-CLAC-104`: *"**`TableDefinition` MUST
  remain policy-free; it supplies schema only**"* — with a `sensitivity`
  annotation explicitly permitted as *"a default answer the policy MAY use."*
- `0_rbac_record_access.projection` (`VARCHAR(32)`) is **never read or written by
  any PHP** **[V]** — it is a name, not a mask.

So the DB-layer view builder is blocked on a column-protection inventory that
does not exist. This design is one way to create it.

## 0.4 A live drift instance, already **[V]**

`ksf_FA_ProjectManagement/src/…/Dictionary/Schema.php`:

| Fact | Line |
|---|---|
| `T_TASK_DEPENDENCIES = 'fa_pm_task_dependencies'` is declared | `:40` |
| `taskDependencies(): TableDefinition` is defined | `:137-149` |
| `createSqls()` iterates a list that **omits** `T_TASK_DEPENDENCIES` | `:305-315` |
| `definitionFor()` map **omits** `T_TASK_DEPENDENCIES` | `:333-343`, so it falls to `return new TableDefinition($table)` — an **empty** definition with no columns |

`TaskDependencyRepository` builds queries against that table. `definitionFor()`
silently returns a column-less `TableDefinition` for it. **Nothing catches this,
because nothing checks that the map is complete.** This is the exact failure this
design prevents, and it is present today in the only module using the class.

Two more **[V]** facts from the same file:

- `writableColumns()` includes `created_at` and the primary key, so
  `ProjectRepository::update()` defensively subtracts both by hand
  (`ProjectRepository.php:132`) — the "derived vs writable" concept the brief asks
  about **already exists as scattered consumer-side workarounds**.
- The file's own docblock: *"install.sql remains the source of truth applied by
  FA at activation; these definitions mirror it"* (`:22-25`). **A mirror already
  exists, with no drift check.** §C is about making the mirror accountable.

## 0.5 One broken import **[V]**

`ksf_Infrastructure/fa_modules/ksf_FA_ExpenseReport/src/ExpenseTypeCatalogue.php:16`

```php
use ksfraser\FrontAccounting\Common\TableDefinition;
...
$this->tableDef = new TableDefinition('0_ksf_fa_expense_type');
```

`find` for `TableDefinition.php` outside `ksf_common_db` returns **only vendored
copies**; no `ksfraser\FrontAccounting\Common\TableDefinition` exists anywhere.
The call is also incompatible — it invokes `->tableName()`, which
`ksf-common-db`'s class does not have (it has `name()` at `:155`). **This file
would fatal on instantiation.** It is a second, independent `TableDefinition`
concept already in the tree.

## 0.6 What the capability contract actually looks like today **[V]**

| Fact | Evidence |
|---|---|
| **18 module directories** implement all four methods (`getModuleConstants` / `getModuleCapabilities` / `hasCapability` / `respondToCapabilityRequest`) in `hooks.php` | grep across `ksf_FA_*` / `ksf_*` |
| `ksf_FA_RBAC` implements **0 of 4** | `grep -c` → `0` |
| `ksf_FA_ProjectManagement` implements **4 of 4** | `hooks.php:165,181,220,243` |
| Calendar's manifest is a **DTO** with `contract_version`, `module`, `version`, `generated_at`, `capabilities`, `methods`, `constants`, `notes` | `CalendarCapabilities.php:43,470`; `hooks.php:349-372` |
| A capability *method* carries `capability, hook, summary, dispatch, signature, returns, required[], optional[], errors[], stability, since` | `CalendarCapabilityMethod.php:105-186` |
| PM's manifest is a **bare associative array** with a **different** shape (`description, methods[], events[]`) | `hooks.php:181-206` |

**So there are two incompatible capability-manifest shapes already in production,
and no `contract_version` on PM's.** Any schema contract added to this surface
must not assume the manifest is uniform.

## 0.7 The workflow engine's own field-type registry **[V]**

`Workflow_Engine_Design.md` §A.2 already specifies:

> "Coercion is decided by the **column's declared type** … driven by a **field
> type registry** the engine builds at publish time from the target table's
> metadata. … The engine only *reads* `information_schema`."

`information_schema` gives `data_type`, `is_nullable`, `column_key`. It does
**not** give: a display label, a description, an enum member list, user-writable
vs derived, a sensitivity class, or a relationship edge. **The design already
needs a schema registry and reaches for the wrong source.** That is the seam this
document closes.

---

# PART A — Verdict: should activated modules return schemas?

## A.1 The answer

> **Yes — modules should publish schemas, as a two-part surface: an
> **advertisement** in the capability manifest (name, version, column count, the
> resolver to call) and a **resolver** hook that returns one table's full column
> metadata on demand. Inline-every-column in the manifest is rejected.**

## A.2 The case *against* inline schemas, which is the real question

| Argument | Weight |
|---|---|
| **Volume.** `0_fa_cal_entries` has ~45 columns **[V — `BR-CAL-010.md` Gap 4]**. `Schema::tasks()` has 26 **[V]**. PM's 10 tables total ~180 columns. A full manifest across 18 contract-bearing modules is on the order of a thousand-plus columns per request. | **Decisive.** |
| **`getModuleCapabilities()` is called for *discovery*, not for rendering.** Every capability lister — admin screens, the workflow rule editor's module dropdown, `hasCapability()` probes — would pay for the entire schema set to answer a question about one capability. | Decisive |
| **It couples the ACL layer to the capability layer.** Column ACL is designed per `Explicit_Column_ACL_API.md` to be gated on `isActive()` + `manages($table)`, with `NullColumnPolicy` as the backward-compatibility guarantee (`FR-CLAC-103`). A registry that is *only* populated when the capability manifest is fetched makes the ACL layer depend on an unrelated code path having run. | **Decisive** — this would break `FR-CLAC-103`. |
| **Two incompatible manifest shapes already exist** (§0.6). Adding an inline payload to a contract that PM and Calendar already serialise differently guarantees a third shape. | Strong |
| **Schema is not capability.** A module's capability is *"I can create a task"*. Its schema is *"a task has 45 columns, 6 of which are sensitive"*. Bundling them means a caller who needs one drags in the other's cost and coupling. | Strong |
| **Standing decision #3** — *contracts are consumer-owned until a second consumer justifies a shared package* — argues against one bloated return value serving three consumers with different cadences. | Supports the split |

## A.3 The case *for*, which is much stronger than the brief suggests

1. **It is the only way the column ACL work can start.** `ACL_Two_Approaches.md`
   §6.2 is blocked on *"there is no column-protection inventory"* **[V]**. A
   masking-view factory built before that inventory guesses — and guessing wrong
   is *specifically* expensive for views, because **a column added to the base
   table does not appear in the view at all**, so it is not even `NULL`, it is
   absent, and no application-side policy knows to look for it **[V — that
   document's own words]**.
2. **It makes drift detectable at all (§C).** Without a registry, a workflow rule
   naming `0_pm_projects.budget` and a physical column renamed to
   `project_budget` are two facts in two systems with nothing relating them. With
   a registry, the rename is an observable event.
3. **The workflow engine has already decided it needs one** (§0.7) and has
   reached for `information_schema`, which cannot supply the four attributes the
   UI actually needs.
4. **`TableDefinition` exists.** The unique asset already exists, is published on
   Packagist, has a PHP-7.3 floor, is transport-agnostic, and — critically — is
   **unique** among the three competing DB packages (`DB_DAO_OVERLAP_ANALYSIS.md`
   §2A.3: *"Only `TableDefinition` is unique"*) **[V]**. Rebuilding it would be
   the "third parallel abstraction" `AGENTS.md` forbids.
5. **Adoption risk is near zero.** One module uses it **[V]**. A breaking change
   to `TableDefinition` has one consumer, and that consumer is
   `ksf_FA_ProjectManagement`, whose 8 `select('*')` sites are already on the ACL
   migration list (`Explicit_Column_ACL_API.md` §7.2 #1).

## A.4 The bootstrapping problem, and the deadlock that is *avoidable*

Schemas reference each other: `tasks.parent_task_id → tasks`, `tasks.project_id →
projects`, `assignments.project_id → projects`, `revenue.project_id → projects`.
Naive population — resolve A's definition, which needs B's, which needs A's —
is exactly the deadlock the brief warns about.

**It is avoidable, and the fix is structural: the registry must never resolve
during registration.**

| Phase | What happens | What it may NOT do |
|---|---|---|
| **1. Advertise** | Every module publishes a **descriptor** per table: `{name, module, version, column_count, resolver, writes}`. Descriptors are self-contained. | Must not touch another module. Must not call a hook. |
| **2. Register** | A consumer-side sweep collects descriptors via `hook_invoke_all('schema_advertise')` and inserts them into a name→descriptor map. **O(n) hooks, zero resolution, order-independent.** | Must not resolve a column, a type, or an FK. |
| **3. Resolve (lazy, pull)** | `resolve(string $table): Schema` pulls one table's columns. A relationship reference is stored as an **unresolved** `(target_table, target_column)` pair plus an optional hint. | Resolution is never triggered by registration, so **a cycle cannot deadlock registration — there is nothing to recurse into.** |
| **4. Expand relationships (explicit, bounded)** | `relationshipsOf($table, $depth = 1)` walks edges with a **visited-set** keyed on table name and a hard depth cap. | Must refuse to re-enter a visited table and must return `[]` on a cycle rather than throwing. |

Four rules that make this safe:

- **R-BOOT-1 — Register never resolves.** Order-independence is a property of the
  design, not of module load order. FA's `hook_invoke_all` iterates extensions in
  registry order and that order is not a contract (`README.md` Q-ACL-010-6 is
  explicitly unresolved **[V]**), so a design that depends on it is already
  broken.
- **R-BOOT-2 — A dangling FK is a WARNING at register, an ERROR at expansion.**
  A module may reference `0_ksf_sales.sales_order` whether or not
  `ksf_FA_Sales` is installed *for this company*. Extension activation is
  **per-company** **[V — `AGENTS.md`]**, so a module can be active in company 1
  and absent in company 2. Failing registration on a missing target would make
  the registry's health depend on which company is logged in.
- **R-BOOT-3 — Self-reference must be a first-class, tested case.** `tasks.parent_task_id`
  is a self-FK **[V — `Schema.php:97`]**. With depth 1 (the default) a
  self-reference is a leaf and terminates naturally. Any design that needs a
  depth-2 walk must have a visited-set, or `parent_task_id` is an infinite
  recursion on day one.
- **R-BOOT-4 — The `TableDefinition` stays a pure value object.** It holds no
  registry handle and performs no resolution. The *registry* holds definitions.
  A `TableDefinition` that could resolve would make DDL generation
  (`createSql()`, which must emit in declaration order) depend on load order.

## A.5 Cross-module references are declarations, not dependencies **[D]**

A `foreign_key` in the registry is a **string**. It is not a `use` statement, not
a class reference, and it must never cause module A to autoload module B. This
satisfies *"modules must not depend on each other"* directly: A depends on the
*existence of a name*, and the registry reports that name's absence as data.

The mirror-image risk is the one that matters: if a workflow rule for CRM says
*"when `opportunity.stage` is `Closed`"* and CRM renames it, the rule breaks. That
is §C.

## A.6 Decision **[D]**

| Decision | Rationale |
|---|---|
| Modules **do** publish schemas. | It unblocks the ACL work (§A.3.1), the workflow type registry (§0.7), and drift detection (§C). |
| Publication is **advertisement + resolver**, never inline. | §A.2. |
| The registry is a **consumer-side aggregator**, not a shared package, in v1. | README #3; and one implementation exists. §D. |
| Population is **two-phase** (advertise → register → lazy resolve). | §A.4. |
| ACL activation **must not** depend on the registry being populated. | `FR-CLAC-103`. A registry miss means *undeclared*, which is **unrestricted** for the ACL — never "deny". |

---

# PART B — The schema model

## B.1 Two shapes, not one **[D]**

`ACL_Two_Approaches.md` §3.7 already established that a view cannot be a
`TableDefinition`. That generalises: **one interface, two implementations.**

| | `TableSchema` | `ColumnListSchema` |
|---|---|---|
| Shape | table + columns | columns only |
| Primary key | required | none |
| `createSql` / `insertSql` / `updateSql` / `deleteSql` | yes | **must not exist** |
| Users | `TableDefinition`; DB-layer views get the *other* one **[V — §3.7]**, ACL-masked projections, `information_schema` reflection | view definitions, denormalised projections, the MariaDB view factory |
| Why two | Giving a view a `TableDefinition` produces `INSERT`/`UPDATE` SQL that fails (verified: MariaDB error 1471) **[V — that doc]**, and `createSql()` that is meaningless. |

`TableDefinition` **implements** `TableSchema`; it does not extend it.

## B.2 The column **[D]**

Every field below has a stated consumer. Fields with no consumer are listed as
rejected, deliberately.

| Field | Type | Consumer | Notes |
|---|---|---|---|
| `name` | `string` | all three | The identifier. **Rejecting** the legacy space-padded names (`'name     '`, `Explicit_Column_ACL_API.md` §2.1 **[V]**) — validate `^[a-z_][a-z0-9_]*$` at construction. |
| `type` / `length` / `scale` | `string`/`?int`/`?int` | builder, workflow §A.2 | `varchar(32)` today. The coercer needs the **semantic** type; parse it once, into `enum {string,int,decimal,float,bool,date,datetime,timestamp,text,json}`. |
| `nullable` | `bool` | workflow §A.3 | `null === null` today means "NOT NULL" **[V — `:69-75`]**. Inverted for the consumer. **This inversion is a bug surface**; add a `ColumnSchema` normaliser and unit-test the mapping. |
| `primaryKey` | `bool` | builder | |
| `autoIncrement` | `bool` | builder | `writableColumns()` excludes this today **[V — `:128`]**. |
| `writable` | `bool` | **workflow actions** | §B.4. Replaces the consumer-side `array_diff` workarounds **[V — `ProjectRepository.php:132`]**. |
| `derived` | `bool` | **workflow actions** | §B.4. Distinct from `writable`: a column can be writable *by a human* and not writable *by a rule*. |
| `label` | `string` | **workflow UI** | Human name for the picker. Without it the picker renders snake_case. |
| `description` | `?string` | **workflow UI**, help text | |
| `enumValues` | `?string[]` | **workflow UI** | `Workflow_Engine_Design.md` §D.2 calls a dropdown of declared enum values *"the highest-leverage UI decision in the whole document"* **[V]**. PM's `status`, `priority`, `dependency_type`, `progress_mode` are the live beneficiaries — all are `varchar` with a hardcoded PHP default (**`'Medium'`, `'Planning'`, `'FS'`** **[V — `Schema.php:76-77,109`]**) and therefore *cannot* be offered as a dropdown today. |
| `sensitivity` | `?Sensitivity` | **ACL + workflow** | §B.3. |
| `format` | `?Format` | **workflow actions** | `currency`, `date`, `datetime`, `percent`, `bool`, `text`. Drives `modify_field` previews and `round(n)` (§B.5 of the engine doc). `decimal(15,2)` on `budget` should render `50,000.00`, not `50000`. |
| `references` | `?Reference` | **workflow conditions** | §B.5. |

## B.3 The elegant part — `sensitivity` — verified, with three caveats

**The claim under test:** *"if the schema carries sensitivity, the workflow UI
automatically only offers fields the current user may read, and the rule
validator refuses conditions on fields the DEFINER could not read."*

**It holds.** Three properties make it true:

1. **The registry is the only source of "what fields exist".** If the picker
   enumerates `TableSchema::columns()` and filters by
   `Sensitivity::isReadableBy($user, $column)`, then a field the user cannot read
   is **never rendered**. This is stronger than hiding it after the fact: an
   unrendered option cannot be typed, copied from another user's screen, or
   reconstructed by hand-editing the JSON — because hand-editing JSON is exactly
   what `Workflow_Engine_Design.md` §D.3's publish-time validator exists to
   reject.
2. **The validator is a second, independent gate.** §D.3 item 1 already
   requires *"Every field reference resolves to a real column of the target
   table"* **[V]**. Adding *"…and is readable by the publishing user"* is the
   same walk, one more predicate. No new machinery.
3. **It composes with the ACL's existing null-object guarantee.** When no policy
   is registered, `NullColumnPolicy` reports everything visible **[V]** and the
   filter is a no-op — so the workflow UI works unchanged on an RBAC-disabled
   pod, satisfying `FR-CLAC-103`.

### The three caveats, stated rather than glossed

**Caveat 1 — `FR-CLAC-104` says `TableDefinition` must stay policy-free. Is a
`sensitivity` annotation a violation?**

**No, and the line is precise.** `ACL_Two_Approaches.md` §3.7 and
`Explicit_Column_ACL_API.md` §3.1 both draw the line at *who may read what*:

- **`TableDefinition` carries the classification** — "this column is
  `CONFIDENTIAL`". A fact about the data.
- **The policy carries the grant** — "role `accountant` may read
  `CONFIDENTIAL`". A fact about the caller.

`Explicit_Column_ACL_API.md` already anticipates this exactly: a `sensitivity`
annotation is permitted because *"the policy MAY use [it] as a default answer"*
**[V — §3.1]**. The registry is that policy's input; it is not the policy. **The
test to keep it honest: if a field's value would change if the current user
changed, it belongs in the policy and must not be added here.**

**Caveat 2 — the schema can only ever *suppress*, never *grant*. This is a hard
invariant and must be enforced in code, not documented.**

`Sensitivity` on a column is an **upper bound on visibility**, never a grant. A
column with no annotation is **unclassified = visible**; a column annotated
`CONFIDENTIAL` is visible only to whoever the policy says. Therefore:

- **Absence must mean "visible", never "hidden."** If absence meant hidden, every
  module's existing tables would vanish from every picker on day one, and the
  failure is silent — an empty dropdown that looks like "this record type has no
  fields."
- **A mis-classification is a denial, and it is a silent one.** A module that
  over-classifies a column as `CONFIDENTIAL` **removes it from every workflow rule
  editor in the system** and nobody sees an error. *This is the single biggest
  operational risk in §B and the reason §F puts classification behind an explicit
  `->sensitive()` call rather than defaulting it.*
- **A *run-time* workflow cannot be governed by the definer's current rights.**
  §B's second clause is about *definition*-time. At run time the engine must
  evaluate against a **policy snapshot taken at publish**, not against whoever
  happens to be logged in when the rule fires — otherwise a rule authored by an
  administrator silently changes behaviour when their role is revoked, and the
  change is invisible in the run log.

**Caveat 3 — "readable by the definer" is not "readable by the engine."** The
workflow engine runs as the **system**, not as a user. A rule the definer could
not read is correctly refused at publish; a rule the definer could read and the
system now also runs correctly is a **data-export** path — a user who can read
`budget` can now make the system write `budget` into a note, an email, or a
`create_related` payload, on a schedule, without a UI. The publish-time check
must therefore also require that the rule's **actions** cannot exfiltrate the
columns its **conditions** read. **[D] — no mechanism exists for this today, and
it is out of scope for v1 (§F). It is recorded here because it is a consequence
of the design, not a separate idea.**

## B.4 `writable` vs `derived` — why both, and why the engine needs both

The brief asks for "user-writable vs derived/system", and the engine's
`set_field` action (§B.1 of the engine doc) is where it bites:

| Column | `writable` | `derived` | Workflow behaviour **[D]** |
|---|---|---|---|
| `name` | ✅ | ❌ | offer `set_field` |
| `created_at` | ✅ | ✅ | offer **`modify_field` with the `DEFAULT CURRENT_TIMESTAMP`-preserving transforms only**; never `set_field` |
| `is_critical` (CPM output) **[V — `Schema.php:116`]** | ❌ | ✅ | **never offer `set_field`** — the engine computes it from the dependency graph and a rule writing it is silently overwritten by the next schedule run |
| `slack`, `es`, `ef`, `ls`, `lf` **[V — `Schema.php:111-115`]** | ❌ | ✅ | same |
| `progress`, `percent_complete` **[V — `Schema.php:105`, `Schema.php:250`]** | ✅ | ✅ | offer, but warn: "also computed from logged work" |
| `auto_increment` PK | ❌ | ✅ | never offered |

`TableDefinition::writableColumns()` answers **none** of this today — it excludes
`auto_increment` and nothing else **[V — `:122-131`]**, which is why
`ProjectRepository::update()` subtracts `project_id` and `created_at` by hand
**[V — `:132`]**. Five hand-written `array_diff` calls across the PM
repositories are the current implementation of a concept the schema should own.

## B.5 Relationships — for `related_count_*` **[D]**

`related_count_gt` is deferred to v2 by `Workflow_Engine_Design.md` §A.5,
correctly, because it *"requires a related-records capability contract"*. But
the **declaration** is cheap now and expensive later:

```php
->references(table: 'fa_pm_tasks', column: 'project_id',
             cardinality: ONE, module: 'ksf_FA_ProjectManagement')
```

The registry consumes exactly this: `relationshipsOf('fa_pm_projects', 1)`
returns "has many tasks, via `tasks.project_id`". The engine then needs
**one new thing** — a capability that *counts* related records, because
`related_count_gt` must not become cross-module table access (standing decision
#2 **[V]**). The registry tells it *what to ask for*; it does not answer.

**A relationship is an offer, not a guarantee.** If the owning module is inactive
for this company **[V — activation is per-company]**, the picker should show the
condition greyed with *"requires ksf_FA_ProjectManagement"*, not offer it and
fail at publish. This is the same "advertise vs resolve" split as §A.4.

## B.6 Rejected fields, with reasons **[D]**

| Rejected | Why |
|---|---|
| `comment` (SQL `COMMENT`) | Nothing consumes it; `install.sql` comments **[V]** are already drifting from the dictionary **[V — `0_rbac_team_members`' FK comment is wrong, per `FR-ACL-001-01` Q-ACL-010-5]**. Adding a third copy makes it four. |
| Encryption-at-rest flags | Different concern (confidentiality *at rest*, not read authorisation). `ksf_db_security`'s `Encrypted/EncryptedFields.php` is the existing attempt and it is untested with no consumer **[V]**. |
| Query hints / optimiser hints | No consumer; would invite per-module SQL into a schema object. |
| Anything about the ACL **grant** | §B.3 caveat 1. |

---

# PART C — Drift detection: the strongest argument, stated rigorously

## C.1 The problem, precisely

Three subsystems read column names. None of them can currently detect that a
name has moved:

| Consumer | Stores/uses | Detects a rename? |
|---|---|---|
| The DB | the column | trivially — the rename happens here |
| A workflow rule | `{"field": "budget", "operator": "gte", "value": 50000}` in `0_wf_versions.definition` JSON | **no** |
| An ACL policy | `(module, table_name, column_name)` in `0_rbac_column_policies` | **no** |

The failure is silent in both directions and **worse than an exception**:

- **A condition on a deleted column** evaluates against a missing key. Per
  `Workflow_Engine_Design.md` §A.3, a missing operand must be a *defined
  outcome*, not an error — so `budget gte 50000` on a vanished `budget` would
  evaluate to **`false`**, and the rule simply never fires. The user's rule is
  gone and the run log says `skipped_null_operand`.
- **A condition on a *renamed* column** is worse: `budget` is now absent, the
  value reads as NULL, `gte` → `false`, and the rule is inert. The automation
  that used to file every high-value orphan review task now files **nothing**,
  and **no page shows an error anywhere.**
- **A protected column that is renamed** while `0_rbac_column_policies` still
  names the old one: the policy no longer matches anything. Whether that fails
  open or closed depends entirely on the `manages()` semantics
  (`Q1` in `Column_Level_ACL_API.md` §9, still open **[V]**).

`Workflow_Engine_Design.md` §C.5 already names the correct policy for this class
of failure — *"Developer error: an action type or field that no longer exists …
**No retry. Fail loudly, and disable the workflow.** A published workflow
referencing a deleted column is a deploy-time defect; leaving it firing-and-
failing every save is worse than stopping it"* **[V]**. **The registry is what
makes that policy implementable**, because without it the engine cannot tell
"the column is gone" from "the column is NULL this time."

## C.2 The mechanism

### C.2.1 Version stamping

**[D]** Every `TableSchema` carries an explicit `version: string`. **Default: a
content hash**, not a counter, because a counter must be maintained by hand and
a hand-maintained counter is the thing that drifts.

- Content hash over the **canonical projection** of the schema: sorted
  `(name, type, nullable, writable, derived, sensitivity, enumValues, format)`
  tuples, plus the sorted relationship list. Explicitly **excluded**:
  `label`, `description`, `engine`, `charset`, index names — otherwise editing a
  label bumps the version and flags every rule, and the version stops meaning
  "the wire format may have changed".
- A module may pin a literal (`->version('2.4.4')`) when it has a migration
  story. The registry records *both* and reports a mismatch as drift, because a
  pinned version that no longer matches its own content is the definition of
  drift.

### C.2.2 Rules store the version they were authored against

**[D]** `0_wf_versions` (§C.6 of the engine doc) gains:

```
schema_refs   JSON    {"fa_pm_projects": "sha256:9f2c…", "fa_pm_tasks": "sha256:41ab…"}
```

Written **at publish**, from the registry, not typed by the user. `0_rbac_column_policies`
likewise carries `schema_version_at_write`.

### C.2.3 The validator — and the design decision that makes it affordable

**[D]** `SchemaRegistry::validateRules(array $rules): DriftReport`, run:

1. **at publish** — synchronous, blocking, a publish error (§C.2.4);
2. **on `activate_extension()`** — the sweep **[V — `hooks.php:93` is the hook]**,
   so a schema change that breaks published rules is caught **at the moment the
   change is deployed**, not when a rule next fires;
3. **on demand** from a `ksf_FA_Workflow_UI` health screen — the
   `Workflow_Engine_Design.md` §D.5 **Health** view already exists as a design
   and is the natural home;
4. **never at run time.** A run-time check cannot distinguish drift from a NULL
   value, and blocking a user's save on a schema-version check would be the
   engine holding the user's data hostage — precisely the failure
   `Workflow_Engine_Design.md` §C.2 rejects in full **[V]**.

The design decision that makes this affordable: **`schema_refs` is stored
denormalised on the rule version, not resolved through a foreign key.** A
validator run over 200 rule versions is 200 dictionary lookups against an
in-memory map built once per request. **No table is queried.** This is why drift
detection can be run on *every* activation instead of as a nightly job that
everyone defers.

### C.2.4 What the report says

| Finding | Severity | Meaning |
|---|---|---|
| `column_missing` | **error** | The rule references a column the schema no longer declares. Blocks publish; auto-disables the workflow if already published (**per the engine doc's own §C.5 developer-error policy**). |
| `column_renamed` | **error** | A column present in the rule's referenced set at `schema_refs` time but absent now, **and** a column of the same type newly present that the rule's own module renamed. Reported as a *suggestion*, never applied automatically. |
| `version_moved` | **warning** | Version differs but every referenced column still resolves and no type changed. "This rule was authored against an older schema but is still valid." |
| `type_changed` | **error** | `varchar` → `int`. The engine's coercion table (§A.2) changes meaning, so a stored literal may become invalid. |
| `enum_member_lost` | **error** | `status IN ('Open','Closed')` and `Closed` was removed. §A.2 already requires a publish error for a non-member **[V]**. |
| `relationship_target_missing` | **warning** | A `related_count` rule whose target module is inactive **for this company**. `[V — activation is per-company]`. |

**`column_renamed` must never be auto-applied.** A rename detection is a
heuristic (same type + same position + declared `->renamedFrom('budget')` on the
new column is a *confirmation*, not an inference). The registry should let a
module **declare** the rename:

```php
->column('project_budget', 'decimal(15,2)')
->renamedFrom('budget')          // explicit, reviewable, greppable
```

…which turns `column_renamed` from an error into a warning and hands the
remediation to the human, with the old name in the message.

## C.3 The case, made strictly **[D]**

1. **It converts a silent, permanent automation failure into a deploy-time
   error.** Today a renamed column produces a rule that quietly never fires, and
   the run log reports `skipped_null_operand` **[V — §A.3]** — which reads like
   normal behaviour. That is the worst possible failure mode: it cannot be
   reported by a user because nothing looks wrong.
2. **It makes the ACL layer's failure mode decidable.** `Q1`
   (`Explicit_Column_ACL_API.md` §9) — allow-all vs deny-all for an unknown
   table — is currently unanswerable partly because there is no way to know that
   a table's *columns* changed. With the registry, "the policy names a column
   this table no longer has" is a **detectable fact**, and the answer to Q1
   becomes decidable per column rather than per table.
3. **It is cheap enough to run on every deployment.** §C.2.3.
4. **It closes an already-open blocker.** `ACL_Two_Approaches.md` §6.2 **[V]**.
5. **It catches the defect that is already in the tree.** §0.4's missing
   `T_TASK_DEPENDENCIES` map entry is precisely this check, one level up: *"the
   registry knows a table and cannot produce its definition."* That is a
   register-time error, not a run-time one, and it costs three lines to detect.

**And the honest counter-case, which is stronger than it looks:** drift detection
is only worth building if there are rules to drift. There are **zero** — the
workflow module creates **no tables** (`sql/install.sql` is three comment lines),
`0_fa_wf_triggers` / `actions` / `workflows` / `log` **do not exist** in the live
database, and the module is not registered in either FA instance **[V —
`Workflow_Engine_Design.md` §1.3, §1.5]**. **Today, drift detection has zero
rows to protect.** It is a design that must land *before* the data, not after,
which is an argument for doing the registry in v1 and the drift *report* in v2 —
and an argument for not treating drift detection as the *only* justification.

---

# PART D — Interfaces and where they live

## D.1 The decision **[D]**

> **The schema interfaces live in `ksf-common-db`, in a new
> `ksfraser\CommonDb\Schema\` namespace. The *registry* is a separate,
> consumer-side component. `ksf-common-db` gains no dependency on any module,
> RBAC, or the workflow engine.**

## D.2 Why in `ksf-common-db` and not a neutral package

| Option | Assessment |
|---|---|
| **`ksf-common-db` (chosen)** | The query builder is the **first** consumer and already lives there **[V]**. `TableDefinition` already lives there and is the **only** unique asset of the three competing DB packages **[V — `DB_DAO_OVERLAP_ANALYSIS.md` §2A.3]**. RBAC already requires it and the arrow is already one-way **[V]**. `ksf-common-db` depends on nothing but `php` and `ext-pdo` **[V — `composer.json`]**, so RBAC and workflow consuming from it adds **no new edge**. |
| **A new neutral package (`ksf_schema`)** | Cleaner naming, but it splits `TableDefinition` away from the builder that must consume `TableSchema`, and README #3 says a shared contract needs a second consumer to justify a package **[V]** — and today there is **one implementation**. **Defer until a second `TableSchema` implementation exists** (the DB-layer view factory is the obvious second, and `ACL_Two_Approaches.md` §6.1 already sketches a `ColumnListDefinition` for it **[V]**). |
| **`ksf_FA_Common`** | Rejected: FA-flavoured, and the whole point of `ksf-common-db` was to escape that **[V — `AGENTS.md`]**. |
| **Each module defines its own** | Exactly the divergence problem. Rejected. |

## D.3 Proposed contracts **[D]** — *illustrative, not an API*

```php
namespace ksfraser\CommonDb\Schema;

/** Describes a set of columns. A table, a view, a projection. */
interface ColumnListSchema
{
    /** @return ColumnSchema[] keyed by column name, in declaration order */
    public function columns(): array;

    public function hasColumn(string $name): bool;
    public function column(string $name): ?ColumnSchema;
    public function columnNames(): array;
}

/** Adds identity and DDL to a ColumnListSchema. A view must NOT have one. */
interface TableSchema extends ColumnListSchema
{
    /** Logical, UNPREFIXED name — FaDbAdapter prefixes it. */
    public function name(): string;
    public function primaryKey(): ?string;
    public function version(): string;      // §C.2.1

    /** @return Relationship[] */
    public function relationships(): array;
}
```

```php
namespace ksfraser\CommonDb\Schema;

/** One column. Immutable. */
final class ColumnSchema { /* name, type, length, scale, nullable, primaryKey,
                              autoIncrement, writable, derived, label, description,
                              enumValues, sensitivity, format, references */ }

enum-like class Sensitivity   // null = unclassified = VISIBLE. §B.3 caveat 2.
enum-like class SensitivityLevel { INTERNAL, CONFIDENTIAL, SECRET }

final class Relationship     // table, column, cardinality, module, one/many
final class Reference         // target table + optional target column
```

```php
namespace ksfraser\CommonDb\Schema;

/**
 * The consumer-side aggregator. Lives wherever the consumer lives;
 * ksfraser\CommonDb\Schema\SchemaRegistry is the shipped implementation.
 */
interface SchemaRegistryInterface
{
    /** Registration NEVER resolves. Order-independent by construction. */
    public function advertise(SchemaDescriptor $d): void;

    /** Pull one table's full schema. Null if not advertised. */
    public function resolve(string $table): ?TableSchema;

    /** Bounded, visited-set walk. Depth 1 default. Returns [] on a cycle. */
    public function relationshipsOf(string $table, int $depth = 1): array;

    /** Advertised but unresolvable — the §0.4 failure. */
    public function unresolved(): array;

    /** §C.2.3 */
    public function validateRules(array $rules): DriftReport;
}
```

## D.4 The module-facing surface **[D]**

```php
// modules/<X>/hooks.php

/** Advertise. Self-contained. Calls no other module. Returns descriptors. */
function schema_advertise(&$data, $opts = null)   { /* descriptors */ }

/**
 * Resolve ONE table's columns.
 * $opts = ['table' => 'fa_pm_projects', 'if_version' => 'sha256:…']
 * Returns null when $table is not mine.
 */
function schema_resolve(&$data, $opts = null)     { /* full TableSchema */ }
```

Two rules:

- **`schema_resolve` is per-table and cacheable; `schema_advertise` is
  O(1)-per-table and returns only metadata.** This is the whole reason for the
  split (§A.2).
- **Both are `hook_invoke_all`, not `hook_invoke`.** There is exactly one
  provider per table name, and `hook_invoke_all`'s "everyone answers" semantics
  suits a registry sweep. **`hook_invoke_first`'s `null`/`false` semantics are
  explicitly unresolved (Q-ACL-010-6) [V]** — a registry must not be built on a
  documented-`null` contract that is still open.

## D.5 Cross-module dependency rules **[D]**

| Rule | Enforcement |
|---|---|
| `ksf-common-db` requires no module | Already true **[V — `composer.json`]**. A CI grep for `ksfraser\FrontAccounting\|ksfraser\Rbac\|ksfraser\Workflow` in `ksf_common_db/src/` enforces it going forward. |
| A module never `use`s another module's schema class | Relationships are **strings** (§A.5). A CI grep for `use` across module boundaries in `Schema` namespace files. |
| A module never calls another module's resolver | The registry does that, once, centrally. |
| The registry never depends on RBAC or the workflow engine | It does not know they exist. They depend on it. |
| The ACL does not depend on the registry being populated | A registry miss = *undeclared* = **unrestricted** (`FR-CLAC-103`). §A.6. |

---

# PART E — Relationship to the query builder

## E.1 What must change in `QueryBuilder` **[D]**

Ordered by dependency. Everything is **additive**; no existing signature changes,
so this is a **v1.1.0** release, not v2.

| # | Change | Why | Source of the requirement |
|---|---|---|---|
| 1 | **`fromDefinition(TableSchema $s, string $alias = '')`** — sets `$from` *and* retains the definition | **The blocker.** Row ACL keys on the declared table; `from(string)` gives an opaque string **[V — `:83`]**. | `FR-ACL-010-01.md` §5, verbatim |
| 2 | **`selectItems(): array`**, **`fromTable(): ?string`**, **`fromAlias(): ?string`**, `whereClauses()`, `joins()`, `groupByItems()`, `havingClauses()`, `orderByItems()` | No policy pass can exist without them **[V — no getters today]**. Read-only. | `Explicit_Column_ACL_API.md` §4.4.1 |
| 3 | **`withColumnPolicy(ColumnPolicyInterface $p)`** + `private $policy = null` | Gated on "an object is registered", never on "is RBAC installed". `NullColumnPolicy` ⇒ byte-identical SQL. | `FR-CLAC-101/103` |
| 4 | **`protected function renderSelect(array $cols): string`** extracted from `toSql()` `:176` | One place for the projection pass to act. | `Explicit_Column_ACL_API.md` §4.4.4 |
| 5 | **Structured clause API**: `whereColumn()`, `orderByColumn()`, `groupByColumn()`, `havingColumn()` — recording the referenced column **structurally** | Closes inference-matrix rows #3–#10 **without parsing SQL**, which is risk R1 (rated **High**) **[V]**. | `Column_Level_ACL_Design.md` §2.3 |
| 6 | **`select()` becomes mandatory under an active policy** (`MissingSelectClause`) | `$select` defaults to `['*']` **[V — `:26`]**, so a builder nobody told what to select emits a wildcard. | `Explicit_Column_ACL_API.md` §7.2 #2 |

## E.2 `SELECT *` — the verdict is unchanged, and the registry changes *why*

`FR-CLAC-121` and `FR-CLAC-110`: **`*` throws `StarNotPermitted` whenever
`isActive()` is true for any table in the statement** **[V]**. The registry does
**not** overturn this.

What changes is that **expansion becomes possible at all**. Today it is
impossible — the builder holds no schema, so `*` cannot be resolved to anything
**[V]**. With `fromDefinition()`, it can:

```php
$qb->fromDefinition($schema)->select('*');   // StarNotPermitted under a policy
$qb->fromDefinition($schema)->expandStar();  // explicit, greppable opt-in
```

**Recommendation, and it is stronger than the prior docs':** when a policy is
active, **`expandStar()` is still not the default.** Expansion would silently
change the result *shape* for report and CSV templates, and
`Explicit_Column_ACL_API.md` §4.4 already chose `REDACT` over `DROP` for exactly
that reason ("keeps result shape stable for report/CSV templates") **[V]**.
Expanding `*` to the permitted set produces a *narrower* shape than the caller
asked for and nobody is told. **Throw by default; expansion must be written
down.**

## E.3 The minimal accessor surface **[D]**

`TableDefinition` — **5 additions, all additive**:

```php
public function columnDef(string $name): ?array;   // make PUBLIC — it is private at :139
public function columnDefinitions(): array;        // FULL rows, not just names (:101)
public function writableColumns(): array;          // must honour 'writable' + exclude derived
public function relationships(): array;            // new
public function version(): string;                 // §C.2.1, default = content hash
```

Plus a fluent **explicit** declaration — never a default:

```php
->column('budget', 'decimal(15,2)', '', false, 0.00)
->label('budget', 'Budget')                       // or: ->column(...)->label(...)
->sensitive('budget', SensitivityLevel::CONFIDENTIAL)
->derived('slack', true)                          // CPM output
->enum('status', ['Not Started','In Progress','Done'])
->format('budget', Format::CURRENCY)
->references('project_id', 'fa_pm_projects', 'project_id', Cardinality::MANY)
```

**The `->label()` default.** A missing label must render a humanised column name
(`project_manager` → *"Project manager"*), not an empty picker entry. An empty
label is a silently broken UI, and this is the single most likely field to be
forgotten because it is the one with a natural fallback.

## E.4 Do **not** let the builder and the registry diverge **[D]**

The builder holds a `TableSchema`; the registry holds the same instances. Two
copies means two `version()`s. `QueryBuilder` should accept the definition **from
the registry**, not resolve one itself — otherwise the builder learns how to
discover modules, which is the registry's job and would put `hook_invoke_all`
inside `ksf-common-db`.

---

# PART F — Phased plan

Sized by the verified facts: **one consumer module**, **zero workflow rules**,
**one broken import**, **18 contract-bearing modules but a two-version manifest
contract**.

## F.1 v1 — the smallest useful thing

**Goal: make the registry real for one module, and prove drift detection on the
one defect that already exists (§0.4).** Nothing in v1 changes runtime behaviour.

| # | Deliverable | Exit criterion |
|---|---|---|
| **1** | `ksfraser\CommonDb\Schema\` — `ColumnListSchema`, `TableSchema`, `ColumnSchema`, `Sensitivity`, `Relationship`, `SchemaDescriptor`, `version()` (content hash). **All new; nothing modified.** | 100% covered. No existing test changes. |
| **2** | `TableDefinition implements TableSchema`; **5 additive methods** (§E.3); `columnDef()` public. `writableColumns()` **keeps its current behaviour by default** and gains an opt-in `writableColumnsStrict()`. | The existing **5** `TableDefinitionTest` cases pass **unchanged**. `ProjectRepository`'s hand-rolled `array_diff` still passes. Ship **v1.1.0**. |
| **3** | `SchemaRegistry` — `advertise()` (never resolves), `resolve()`, `relationshipsOf($depth=1)` with a visited set, `unresolved()`. | **The §0.4 defect is now reported**: `unresolved()` names `fa_pm_task_dependencies` as advertised-but-unproducible. Test with the self-FK `tasks.parent_task_id`. |
| **4** | Wire PM's `schema_advertise()` / `schema_resolve()` in `hooks.php`; **fix the missing map entry**. | `Schema::definitionFor('fa_pm_task_dependencies')` returns the real definition. |
| **5** | `DriftReport` + `validateRules()` over **fixtures only** — no `0_wf_*` table exists **[V]**. | Detects: column missing, column renamed (+ `->renamedFrom()`), version moved, type changed, enum member lost, relationship target missing. |
| **6** | Fix `ksf_FA_ExpenseReport/src/ExpenseTypeCatalogue.php:16` — the import names a class that does not exist **[V]**, and calls a method the real class lacks. | Class resolves, or is deleted. **Do it as its own commit** — it is unrelated to this design and is currently a latent fatal. |
| **7** | Delete the second and third query builders, or record why they stay (§0.1). | One builder, or three documented exceptions. |

**v1's acceptance is one sentence:** *the registry resolves `fa_pm_projects`,
reports `fa_pm_task_dependencies` as broken, and a rule referencing `budget`
against a registry that no longer declares it is reported as `column_missing`.*

**Explicitly NOT in v1:** `QueryBuilder` changes (that is `Explicit_Column_ACL_API.md`
Phase 1 and it should land as that phase, not smuggled in here), any hook in
RBAC, any change to `sensitivity` policy semantics, anything that runs at
request time on a page.

## F.2 v2 — consumption

| # | Deliverable | Note |
|---|---|---|
| 8 | `QueryBuilder` accessors + `fromDefinition()` + `withColumnPolicy()` + `renderSelect()` + structured clause API (§E.1). | This is `Explicit_Column_ACL_API.md` Phase 1. **Sequenced after the registry so the builder has something real to attach.** |
| 9 | Migrate PM's **8** `select('*')` sites **[V]** to explicit columns. | Prerequisite for enabling any policy. |
| 10 | Sensitivity → `ColumnPolicyInterface`. **Only now does `FR-CLAC-104`'s "policy MAY use it as a default answer" become live.** | Requires `Q1` (`Explicit_Column_ACL_API.md` §9) to be answered. |
| 11 | `sensitive()` classification of `budget` / `revenue_amount`. | **Caveat 2 applies**: an over-classified column silently vanishes from every workflow picker. Classify 2 columns, not 20. |
| 12 | Workflow engine consumes `TableSchema` for the field-type registry, **replacing `information_schema`** (§0.7). | Unblocks `enumValues` dropdowns (§B.2) and the §A.2 coercion table. |

## F.3 v3 — deferred, with reasons

| Item | Why deferred |
|---|---|
| `related_count_*` conditions | Need a *counting capability contract*, not just a declaration. §B.5. `Workflow_Engine_Design.md` §A.5 defers correctly. |
| The **view factory** (`ACL_Two_Approaches.md` §6) | Now unblocked in principle — the inventory can exist. Still needs `ColumnListSchema` (§B.1) and a decision on OD-4 (static vs per-request masking) **[V]**. |
| Drift check on `activate_extension()` | Needs v1's registry plus a real `0_wf_versions` table. Neither exists. |
| §B.3 **caveat 3** (rule exfiltration via actions) | Real, recorded in §B.3, no mechanism. Must not be forgotten. |
| Per-record projections (Q3/OD-5) | `[V]` carried forward unresolved in two documents. A static `TableSchema` cannot express it. |
| Making the registry a shared package | README #3 — needs a second implementation. The view factory is the candidate. |

## F.4 Risks **[D]**

| ID | Risk | Severity | Mitigation |
|---|---|---|---|
| **SR-1** | **The registry becomes a fifth copy of the schema.** `install.sql`, `Schema.php`, the registry cache, the `0_wf_versions.schema_refs` snapshot, and any `information_schema` reflection are five places that must agree. `ACL_Two_Approaches.md` §6.2 already names this exact hazard for views **[V]** — and `ksf_FA_ProjectManagement`'s own docblock says `install.sql` is the source of truth and the dictionary *mirrors* it **[V]**, with no check. | **High** | v1's `unresolved()` catches omission. What it does **not** catch is a dictionary that resolves but disagrees with the live table. **Add a drift check in v2: declared columns vs `information_schema`, run at `activate_extension()`.** Decide *now* whether the dictionary or `install.sql` generates the other; do not leave it as a docblock. |
| **SR-2** | **Registry misses are silent for ACL.** If the registry is unpopulated, `manages()` returns false, and a fail-open Q1 answer means **every column is readable**. | **High** | §A.6: a registry miss is *undeclared*, and `ColumnPolicyInterface::manages()` must have a **separate** "is the registry available at all?" check. A missing registry must be **loud in the log**, even if it is permissive in the query. |
| **SR-3** | **Over-classification silently removes fields** from every workflow picker (§B.3 caveat 2). | Medium | `->sensitive()` is always explicit; classify 2 columns first; surface the classification list in the registry's admin view so the effect is visible before it is felt. |
| **SR-4** | **Two capability-manifest shapes already exist** (§0.6) and PM's has no `contract_version` **[V]**. Adding a schema descriptor to both will produce a third divergence. | Medium | The registry's `advertise()` must not ride on `getModuleCapabilities()`. Separate hooks (§D.4) ⇒ separate shape ⇒ one shape to standardise, not two. |
| **SR-5** | **The `Ksfraser\` vs `ksfraser\` namespace split** (`Column_Level_ACL_Design.md` §3.1 **[V]**) breaks the type hint across the new boundary. `ksf_FA_RBAC` uses capital `Ksfraser` **[V]**. | Medium | Fix **before** a schema interface is type-hinted into RBAC. The existing open question is real and unanswered. |
| **SR-6** | **Only one module uses `TableDefinition`** (§0.1) — the registry's "many providers" shape is validated by **one** provider. | Medium | v1's exit criterion is deliberately PM-only. Do not generalise the *hook surface* until a second module exists; a two-provider contract designed from one provider is how the two-shape problem in §0.6 happened. |
| **SR-7** | **Adoption looks done because `TableDefinition` exists.** 19 `composer.json`s require the package; **1** module uses the class **[V]**. A reader of the manifest will conclude the dictionary is universal. | Low–Med | State the census in `README.md`. Do not let §A.3.4's "it exists and is published" be read as "it is adopted". |

---

# Appendix A — Evidence

## A.1 Files read (2026-10-15)

| Path | Used for |
|---|---|
| `ksf_common_db/src/Dictionary/TableDefinition.php` (256) | §0.1, §B.2, §E.3 |
| `ksf_common_db/src/Query/QueryBuilder.php` (240) | §0.2, §E |
| `ksf_common_db/src/Adapter/FaDbAdapter.php` (`prefixTables()` :49-78, `bindParams()` named path ~:92-98) | §0.2, SR-2 |
| `ksf_common_db/composer.json`, `APPENDIX.md`, tests (3 + 5 cases) | §0.1, §D.2 |
| `ksf_FA_ProjectManagement/src/…/Dictionary/Schema.php` (350) | §0.1, **§0.4**, §B.4 |
| `ksf_FA_ProjectManagement/src/…/Repository/*.php`, `Service/ReportService.php` | §0.2, §0.4, §E |
| `ksf_FA_ProjectManagement/hooks.php:125-275` | §0.6 |
| `ksf_FA_Calendar/hooks.php:349-410, 555-628`, `CalendarCapabilities.php`, `CalendarCapabilityMethod.php` | §0.6, §A.2 |
| `ksf_FA_RBAC/hooks.php` (grep for the 4 methods → 0), `sql/install.sql` | §0.6, §0.3 |
| `ksf_FA_ExpenseReport/src/ExpenseTypeCatalogue.php` | **§0.5** |
| `ksf_Infrastructure/fa_modules/ksf_payment_destinations/src/QueryBuilder/QueryBuilder.php`, `ksf_bank_import/src/…/database/QueryBuilder.php` | §0.1 |
| Consumer census greps across `~/Documents/**` and `ksf_Infrastructure/fa_modules/**`, vendor excluded | §0.1, §0.6 |
| `ksf_Architecture_Docs/`: `Workflow_Engine_Design.md`, `Shared_Responder_Traits_Design.md`, `Column_Level_ACL_Design.md`, `Explicit_Column_ACL_API.md`, `ACL_Two_Approaches.md`, `README.md`, `DB_DAO_OVERLAP_ANALYSIS.md`, `Requirements/{BR-CAL-010, FR-CAL-010-001, FR-ACL-010-01, FR-ACL-010-02, FR-ACL-010-03, BR-ACL-010, FR-ACL-001-01}` | throughout |

## A.2 Not verified

1. **Whether `ksf_FA_ProjectManagement` is the complete consumer set.** The census
   greps non-vendor `.php`. A module vendoring the package under a different
   namespace, or a Composer classmap alias, would not have been found.
2. **Whether §0.4's `T_TASK_DEPENDENCIES` omission is a live bug or dead code.**
   I read `Schema.php`; I did not trace every `definitionFor()` caller, and I did
   not run the module's tests. `TaskDependencyRepository` exists and builds
   queries against that table **[V]** — whether it calls `definitionFor()` is
   **not verified**.
3. **Whether `ksf_FA_ExpenseReport` is loaded on any pod.** The class is
   unresolvable as written **[V]**; whether that file is ever reached is not.
4. **The 18-module count for the 4-method contract** was taken from a grep over
   `hooks.php` files. Some directories appear twice (they are separate trees),
   so the distinct-module count may be lower.
5. **No performance figure is claimed anywhere in this document.** No SQL was
   executed, no `EXPLAIN` was run, no index was created.
6. **`relationship cardinality` in the PM dictionary** was not checked against
   the live schema; the declared `index()` calls suggest intent but are not proof.

## A.3 Related

- [`Explicit_Column_ACL_API.md`](./Explicit_Column_ACL_API.md) — §3.1 `FR-CLAC-104` is the
  line this design must not cross; §5 is the `SELECT *` rule; §7.2 is the
  consumer-migration list v2 step 9 reuses
- [`ACL_Two_Approaches.md`](./ACL_Two_Approaches.md) — **§6.2 is the blocker this
  design addresses**; §3.7 is the two-shape requirement
- [`Column_Level_ACL_Design.md`](./Column_Level_ACL_Design.md) §2.3 — the inference
  matrix the structured clause API closes
- [`Workflow_Engine_Design.md`](./Workflow_Engine_Design.md) §A.2 (`information_schema` field
  type registry), §A.3 (NULL rules — why drift is silent), §C.5 (developer-error
  policy), §C.6 (`0_wf_versions`), §D.2 (enum dropdowns), §D.3 (publish validation)
- [`Requirements/FR-ACL-010-01`](./Requirements/FR-ACL-010-01-per-module-acl-toggle.md) §5 — the
  builder-carries-the-table blocker, verbatim
- [`Requirements/BR-CAL-010`](./Requirements/BR-CAL-010-capability-contract.md) / [`FR-CAL-010-001`](./Requirements/FR-CAL-010-001-task-creation-and-event-listing.md) —
  the capability contract pattern, and the 45-column volume problem
- [`Requirements/OPEN-QUESTIONS.md`](./Requirements/OPEN-QUESTIONS.md) — `Q-ACL-010-1` (the
  builder API, now partly answered by §E), `Q-ACL-010-2` (`prefixTables` vs
  `CASE`), `Q-ACL-010-6` (hook ordering — why §D.4 uses `hook_invoke_all`)
- [`README.md`](./README.md) — standing decisions #2, #3, #4, #6
- `../DB_DAO_OVERLAP_ANALYSIS.md` — "only `TableDefinition` is unique"
- `../AGENTS.md` — PHP 7.3 floor; `ksf_FA_Common` is not the home for this
