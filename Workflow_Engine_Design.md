# Workflow Engine — assessment of `ksf_FA_Workflow` and a design for its replacement

**Date:** 2026-10-14
**Status:** ASSESSMENT + DESIGN RECOMMENDATION. **No production source was modified.**
**Scope:** the deployed module `ksf_FA_Workflow`, the standalone package
`ksfraser/ksf-workflow`, and the design of a SuiteCRM-style flow-automation engine
consuming the three lifecycle events in
[`Requirements/FR-ACL-010-03-lifecycle-events.md`](./Requirements/FR-ACL-010-03-lifecycle-events.md).

**Tag key:** **[V]** verified against source, a live DB, or a test run in this
session. **[D]** proposed design — *not implemented*. Untagged text is reasoning.
Every implementation-status claim is tagged; nothing else is.

---

# PART 1 — ASSESSMENT: what actually exists

## 1.1 There are three things called "Workflow". Only one is the engine, and it is the weakest.

**[V] Three separate artifacts exist.** They are unrelated and do not share code.

| Path | What it is | Git? | Tests |
|---|---|---|---|
| `~/Documents/ksf_FA_Workflow/` | Dev tree of the **FA module** (`hooks.php`, `includes/wf_db.inc`, `pages/`) | yes | **none** — no `tests/`, no `Tests/`, no `composer.json`, no `phpunit.xml` |
| `~/Documents/ksf_Workflow/` | Standalone Composer package **`ksfraser/ksf-workflow`**, namespace `Ksfraser\Workflow\` | yes | **50 tests / 130 assertions, green** (PHPUnit 10.5.63, PHP 8.1.18) |
| `~/Documents/ksf_Workflow_UI/` | UI shell (5 files: `index.php`, `pages/index.php`, `includes/ksf_Workflow_UIDB.php`, `composer.json`) | yes | none |

**[V] The deployed copy is stale relative to the dev tree.** `diff -rq` between
`ksf_Infrastructure/fa_modules/ksf_FA_Workflow/` and `ksf_FA_Workflow/` shows
`pages/workflows.php` and `pages/actions.php` differ. The only functional
difference is `$path_to_root`:

- deployed: `"../../.."` — **correct** (`pages/` → module → `modules/` → FA root)
- dev tree: `"../.."` — **wrong**, one level short; `session.inc` would not resolve

**[V] The deployed copy is ahead** on this line only. Every other difference is
documentation drift. All remaining code (`hooks.php`, `wf_db.inc`, `sql/install.sql`,
`_init/config`) is byte-identical.

**[V] The standalone package's one real consumer is `ksf_FA_Woocommerce`**, and it
uses only the *state machine* half (`src/Woocommerce/Workflow/WooSyncStateMachine.php`).
No consumer of the *engine* half (`WorkflowService`, `WorkflowTrigger`,
`WorkflowAction`) was found anywhere.

---

## 1.2 The direct question: is there a workflow DEFINITION UI today?

> **There is a partial one, and it is the only part of this module that exists in
> code. It is not an engine, and it is unreachable.**

**[V] What `pages/workflows.php` does.** It is a CRUD form over a single
`fa_wf_triggers` row — one field, one operator, one value, plus active/priority.
That is a **definition** screen, not a run/execution screen. So the answer to
"definition UI or only execution view" is: **a definition UI exists in form, and
it models exactly one flat condition.**

**[V] What `pages/actions.php` does.** Same: a CRUD form over `fa_wf_actions`,
where the action's entire configuration is typed as **raw JSON into a textarea**
(`pages/actions.php:93`). There is no field picker, no operator-specific widget,
no validation of the JSON.

**[V] There is no execution/run view at all.** No page lists `fa_wf_log`. The
logging function exists (`wf_db.inc:259`) and is called by **nothing**.

**[V] Nothing on either page is reachable.** `hooks_ksf_FA_Workflow::install_options()`
(`hooks.php:54`) is **an empty method body**. No `add_module()`, no
`add_lapp_function()`, no menu entry. The pages exist as files that a user can only
reach by typing a URL.

**[V] Both pages would fatal on load anyway.** Three independent defects:

1. `include_once($path_to_root . "/modules/FA_Workflow/includes/wf_db.inc")`
   (`pages/workflows.php:11`, `pages/actions.php:11`) — the installed directory is
   `modules/**ksf_**FA_Workflow`. The include never resolves; every
   `get_triggers()` call is an undefined-function fatal.
2. `get_triggers()` returns a **PHP array** (`wf_db.inc:30-54`), but
   `pages/workflows.php:124` calls `db_fetch_assoc($triggers)` on it. Same bug at
   `pages/actions.php:100` with `get_actions()`.
3. `$page_security = 'SA_CUSTOMER'` — the module defines
   `SA_ksf_FA_WorkflowVIEW` / `SA_ksf_FA_WorkflowMANAGE` in `install_access()`
   (`hooks.php:63-74`) and then **uses neither**. Workflow definition is a
   privilege-escalation surface; it is currently gated behind a *customer* role.

---

## 1.3 The data model: none of it exists

**[V] `sql/install.sql` is three lines of SQL comments.** Its entire content:

```sql
-- ksf_FA_Workflow Module Schema
-- Placeholder: Add module-specific tables here
-- Uses @TB_PREF@ for table prefix
```

So `activate_extension()` (`hooks.php:83-94`) calls `update_databases()` against a
file with no statements in it. **The module creates zero tables.**

**[V] Confirmed against the live Integration DB** (`ksfii_app-mariadb`, schema `ksf_fa`):

```sql
SHOW TABLES LIKE '%wf%';        -- 0_ksf_wf_e2e_probe, 0_ksf_wf_jobs, 0_ksf_wf_run_log
SHOW TABLES LIKE '0_fa_wf%';    -- (no rows)
```

**None of `0_fa_wf_triggers`, `0_fa_wf_actions`, `0_fa_wf_workflows`,
`0_fa_wf_log` exists.**

**[V] The `0_ksf_wf_*` tables are a different subsystem and must not be mistaken
for this module's.** They belong to **`ksf_FA_Common`'s scheduler** —
`ksf_FA_Common/src/Scheduler/FaJobsAdapter.php` and `ksf_FA_Common/sql/install.sql`
are the only definitions. They are scheduled-job storage (`job_key`, `interval_p`,
`resolver`, `next_run_at`), which is a cron table, not a rule engine. Naming
collision only; no shared code.

**[V] The intended model, as implied by the code's own SQL.** It is *flat*, and it
is worth stating precisely because it is the baseline we are replacing:

| Intended table | Columns implied by `wf_db.inc` | Doc claim |
|---|---|---|
| `fa_wf_triggers` | `id, name, entity_type, field_name, operator, field_value, trigger_type, is_active, priority` | matches |
| `fa_wf_actions` | `id, trigger_id, name, action_type, action_config (JSON TEXT), action_order, is_active` | matches |
| `fa_wf_workflows` | — **never referenced by any code** | `README.md:81`, `ProjectDcs/Architecture.md:184-187` |
| `fa_wf_log` | `id, workflow_id, trigger_id, action_id, entity_type, entity_id, status, error_message` | matches |

**[V] Two schema facts that constrain the design.** (a) There is no
`company_id` on any intended table, so the model is not multi-company safe even in
theory. (b) There is no `created_at`/`updated_at` and no version column, so
draft/publish and immutable-version semantics (Part C.6) have **no** starting point.

---

## 1.4 What the engine can actually DO, versus what the docs claim

### What actually works **[V]**

| Capability | Reality |
|---|---|
| Condition evaluation | `evaluate_trigger()` (`wf_db.inc:140-161`) — a `match` over 9 operators, real PHP comparison logic. **This is the one genuinely working piece of the module.** |
| Chain execution | `run_workflows()` (`wf_db.inc:230-257`) — fetch triggers → evaluate → fetch actions → execute. Logically sound, linearly ordered by `priority DESC, id` (`wf_db.inc:46`). |
| Field set / unset-by-assignment | `wf_update_field()` / `wf_assign_to()` (`wf_db.inc:179-213`) — mutate an in-memory PHP array. Work. |

### What does not work

| Capability | Reality **[V]** |
|---|---|
| **Anything that touches the database** | Every "action" mutates a **local PHP array** (`&$entity`). No action issues a single `db_query()`. **The engine cannot persist anything.** There is no save, and the user asked for "a save" — it does not exist. |
| `send_email` | `wf_send_email()` (`wf_db.inc:220-222`) — `{ return true; }`. A stub that reports success. |
| `add_note` | `wf_add_note()` (`wf_db.inc:225-227`) — `{ return true; }`. |
| `trigger_event` (the **event emitter** the user asked for) | `wf_trigger_event()` (`wf_db.inc:215-218`) — `{ return true; }`. |
| `webhook` | Listed in the `pages/actions.php` dropdown (`:88`) but **absent from the `match` in `execute_action()`**, so it silently falls to `default => true`. Reports success, does nothing. |
| **PSR-14 events** | `README.md:173-180` documents `workflow.before_execute`, `workflow.after_execute`, `workflow.trigger_fired`, `workflow.action_executed`. `grep` for all four in the module: **zero matches**. No `composer.json`, no PSR-14 dependency, no dispatcher. |
| `calculate` | `wf_db.inc:204`: `eval("return $expression;")` on an admin-typed string. **Remote code execution by design**, reachable by any user granted `SA_CUSTOMER`. Also broken: the placeholder loop (`:200-202`) substitutes `{key}` for every entity key, so a legitimate expression is mangled, and a `{field}` that resolves to `0` is replaced with `0` not `'0'`. |
| Execution log | `log_workflow_execution()` exists but has **zero callers** (`wf_db.inc:259`). The table it inserts into does not exist. |

### Documentation verdict

**[V]** `README.md:22-24` states **"Status: IMPLEMENTED — Ready for Testing."** It is
not implemented. `ProjectDcs/Functional Requirements.md:8` states
**"Status: Implemented"** while its own acceptance checklist is **0 of 20 boxes
ticked** (`:382`, and throughout). `ProjectDcs/Test Plan.md` and `UAT Plan.md` are
entirely unticked `[ ]`.

**The one honest description in the repo is the shared
`MODULE_DIRECTORY.md:185`: `| ksf_FA_Workflow | 1.0.0 | Workflow management | Schema placeholder |`.**
That is correct.

**[V]** Against this org's stated convention that PHP 7.3 is the compatibility floor:
`ksf_Workflow/composer.json` requires `"php": ">=8.1"`, and
`WorkflowTrigger::evaluate()` calls `str_starts_with()` / `str_ends_with()`
(PHP 8.0+). The standalone package **cannot run in the FA 7.4 container as written.**

---

## 1.5 Deployment state **[V]**

- **Not registered in either instance.** `grep -i workflow` over
  `FA/ksf_fa/installed_extensions.php` (3590 B), `FA/ksfii_app/installed_extensions.php`
  (9318 B), and both `company/0/installed_extensions.php` files: **no match**.
  The **container's own** `/var/www/html/installed_extensions.php` inside
  `ksfii_app-fa` also has no match — so this is not the known stale-bind artefact.
- **The module directory *is* present** in the container at
  `/var/www/html/modules/ksf_FA_Workflow` (present since 2025-09-15), it is simply
  not registered and not activated.
- **Net: the module is dormant.** It is source on disk with no install, no schema,
  no menu, no wiring, and no runtime behaviour of any kind. Nothing in production
  depends on it, and nothing will break if it is replaced.

---

## 1.6 Test suite state

| Suite | State **[V]** |
|---|---|
| `ksf_FA_Workflow` (the FA module) | **None.** No `tests/`, no `composer.json`, no `phpunit.xml`. The engine's `evaluate_trigger()` / `run_workflows()` have **zero** coverage. |
| `ksfraser/ksf-workflow` (standalone) | **Green: 50 tests, 130 assertions.** But see below — the green is misleading. |
| `ksf_FA_Calendar/tests/Unit/Capability/` | **Green: 89 tests, 495 assertions.** Reference baseline for how this org tests a capability surface. |

**[V] The standalone package's green suite is not evidence of a working engine:**

- `WorkflowService::loadTriggers()` and `::loadActions()` (`WorkflowService.php:20-30`)
  are **hardcoded to return `[]`**. `runWorkflows()` therefore iterates an empty
  array and returns zero triggers, always. The service has **no persistence and no
  wiring**; `$dbAvailable` is computed and never used.
- **10 of 14 action types are `return true;` stubs** — `create_record`, `trigger_event`,
  `send_email`, `add_note`, `webhook`, `http_request`, `condition`
  (`WorkflowAction.php:167-206`). A `return true` stub passes its test.
- `WorkflowAction::executeCalculate()` and
  `WorkflowService::evaluateExpression()` both `eval()`.
- `WorkflowEvents.php` declares `WorkflowTriggeredEvent` / `WorkflowActionExecutedEvent`
  against `Ksfraser\Event\Event` — but **nothing dispatches them**, and no test file
  for that class exists.
- `tests/Unit/Entity/WorkflowChainTest.php` tests `WorkflowAction`; there is **no
  `WorkflowChain` class in `src/`**.

**Assessment: the standalone package is a typed sketch. Its green suite tests
structs, operator tables and `toArray()`/`fromArray()`, i.e. it confirms the
scaffolding holds together, not that any business behaviour is correct.**

---

## 1.7 Is it wired to the lifecycle events? **[V] No — and neither is anything else.**

- `grep -rn "record_changed|orphaned_record|user_changed"` across `ksf_FA_RBAC`
  (dev **and** deployed): **zero matches.** The emitters specified in
  `FR-ACL-010-03` **do not exist yet.**
- `grep -rn "run_workflows"` in the module: matches appear **only in
  `README.md`, `ProjectDcs/*`, and the function definition itself.** There is no
  caller in any repo.
- The `entity_type` vocabulary in the UI (`debtor`, `contact`, `opportunity`,
  `ticket`, `lead` — `pages/workflows.php:78-84`) is **CRM marketing vocabulary**,
  unrelated to the ACL key triple (`module`, `record_type`, `record_id`) that
  `FR-ACL-010-03` §2.1 specifies. There is no mapping between them, and none is
  proposed in any of the docs.

**[V] `0_rbac_audit_log` exists and contains 0 rows**, as `FR-ACL-010-03` §2.1
states. Also live: `0_rbac_record_access`, `0_rbac_teams`, `0_rbac_team_members`.

**[V] One correction to the brief I was given.** I was asked to treat Calendar as
already exposing `calendar_task_create` / `calendar_entries_query_domain` /
`calendar_capability_probe`. That is **correct**, but `BR-CAL-010` is **stale on
this point**: it is headed *"Proposed — mostly already implemented"* and lists four
open Gaps, and Gaps 1–4 are in fact **closed in code**. `ksf_FA_Calendar/hooks.php`
now carries all four, with passing tests (§1.6):

| BR-CAL-010 gap | Status in code **[V]** |
|---|---|
| Gap 1 — no discovery contract | **Closed.** `calendar_capabilities()` (`:349`), plus the full 4-method contract `getModuleConstants` (`:555`), `getModuleCapabilities` (`:575`), `hasCapability` (`:589`), `respondToCapabilityRequest` (`:628`). |
| Gap 2 — returns a render DTO | **Closed.** `calendar_entries_query_domain()` (`:437`) returns a `CalendarEntrySet` of domain DTOs. |
| Gap 3 — silent month default | **Closed.** `start` and `end` are mandatory; omission returns `null` and sets `error`/`error_field`. |
| Gap 4 — no creation DTO | **Closed.** `calendar_entry_create_typed()` (`:482`) and `calendar_task_create()` (`:519`), both returning `CalendarEntryCreateResult`, with `source_type = 'task'` set explicitly so the caller cannot forget it. |

So the worked example in Part E can be built **now**, against a real contract.

---

# PART 2 — DESIGN

**Naming.** The existing `ksf_FA_Workflow` is taken and its content is inaccurate.
**[D]** The engine is a generic platform capability, so per standing decision #6
(the three-repo convention) it becomes **`ksf_Workflow`** (business, Packagist,
namespace `Ksfraser\Workflow\`) + **`ksf_FA_Workflow`** (FA module: menu, pages,
security areas, schema). `ksf_Workflow_UI` is reused for list/filter views.
The current `ksfraser/ksf-workflow` package is the seed, not the answer: keep
`WorkflowTrigger`/`WorkflowAction` as value objects and the state-machine files
if anything uses them (Woocommerce does), and **replace** `WorkflowService`.

**A hard rule inherited from `AGENTS.md`:** the engine must not contain any module's
business logic, must not name another module's table, and must cross **no** table
boundary (standing decision #2). Actions talk to other modules **only** through
`hook_invoke*`, the same rule the ACL work is built on.

---

## A. Condition model

### A.1 The DSL

**[D]** A condition is a **JSON document**, not a string. Reasons: it must be
diffable and versionable (§C.6), it must be renderable in a UI without parsing,
and a string DSL hands an attacker a parser (`eval()` in the existing
`wf_calculate()` is the cautionary tale).

```json
{
  "op": "AND",
  "children": [
    { "field": "owner_id", "operator": "is_null" },
    { "field": "amount", "operator": "gte", "value": 50000, "value_type": "number" },
    { "op": "NOT", "children": [ { "field": "status", "operator": "eq", "value": "Closed" } ] }
  ]
}
```

**Node kinds [D]:**

| `node.kind` | Meaning |
|---|---|
| `group` | `op` ∈ `AND` \| `OR` \| `NOT`, with `children` |
| `field` | `field` + `operator` + optional `value` / `value_type` |
| `source` | A value read from outside the record (see A.4) — not a comparison |

**Operators [D]** — a closed enum, validated at *publish* time (§D.3), never at
run time:

| Group | Operators |
|---|---|
| Presence | `is_null`, `is_not_null`, `is_empty`, `is_not_empty` |
| Comparison | `eq`, `neq`, `gt`, `gte`, `lt`, `lte` |
| String | `contains`, `not_contains`, `starts_with`, `ends_with`, `matches_regex` |
| Change | `changed`, `changed_from`, `changed_to` |
| Set membership | `in`, `not_in` |
| Related count | `related_count_gt`, `related_count_lt` (deferred, §A.4) |
| Context | `user_role_is`, `today_is`, `days_until_gt`, `days_until_lt` |

`gte`/`lte` are additions over the existing table, which has only
`greater_than`/`less_than` — "at least 50000" is a real requirement and must not be
expressed as `gt 49999.99`.

### A.2 Type coercion — the rule that makes this safe **[D]**

The single most important correctness decision:

> **Coercion is decided by the *column's* declared type, never by the operand's
> PHP type, and never by PHP's own `==`.**

Coercion happens in exactly one place, `TypeCoercer`, driven by a **field type
registry** the engine builds at publish time from the target table's metadata.
There is one table — the target module's own — and the engine only *reads*
`information_schema` to populate the registry. It never reads another module's
*rows*, so this does not violate standing decision #2.

| Declared type | Comparison rule | Rationale |
|---|---|---|
| `int`, `decimal`, `float` | Both sides cast to `(float)`. Non-numeric literal → **publish error**, never a runtime false. | Silent coercion of `"abc"` to `0` makes `amount > 0` true for empty amounts. |
| `date`, `datetime` | Both sides parsed by a **single** strict parser; native `YYYY-MM-DD` wins. | |
| `char`, `varchar`, `text` | **Never** coerced. Compared as strings. | A numeric-looking string is a string. See A.3. |
| `enum`/`set` | Literal must be a declared member or **publish error**. | Catches `status = 'closed'` when the enum has `'Closed'`. |
| `bool` | `tinyint(1)` → bool. | |

**Why this matters concretely [D].** The existing code does
`$currentValue == $fieldValue` (`wf_db.inc:150`). In PHP 7, `"abc" == 0` is `true`.
So today's rule *"amount greater than 0"* **fires on every record whose amount is
empty**. A rule engine whose comparisons depend on PHP's loose-equality table is
not a rule engine; it is a coin flip. The engine must use `===` semantics after a
declared-type-driven cast, and PHP 8's saner string/number comparison must not be
relied on either (the floor is 7.3, where it does not apply).

### A.3 Avoiding SQL's three-valued logic **[D]**

This is the trap, and it is worth being precise about because it silently
produces rules that never fire.

**The trap.** If conditions were ever compiled to SQL `WHERE` clauses, then
`amount <> 100` against a record where `amount IS NULL` yields `NULL`, which is
not `TRUE`, so the row does **not** match. A user writing "amount is not 100"
believes it means "100 or nothing"; SQL says "100, and definitely not nothing".
Worse, under `AND`, one `NULL` poisons the whole clause; under `OR`, it is
invisible. Neither is what the author meant, and neither is visible at authoring time.

**How the design avoids it — three rules:**

1. **Conditions never compile to SQL.** They are evaluated in PHP against an
   already-materialised row. This is not an accident of implementation; it is the
   design's central guarantee. It is what allows §A.2's declared-type coercion to
   exist at all, because SQL comparison semantics are fixed by the column and
   cannot be mediated by a type registry.
2. **NULL is a *value*, not an absence of truth.** The engine normalises every
   field read into an explicit `FieldValue` with one of three states —
   `NULL`, `EMPTY`, or a concrete value. **Only `is_null` / `is_not_null` may test
   NULL.** For every other operator, a NULL operand is a **defined, documented
   outcome, not an error and not an unknown**:
   - `eq` / `neq` → `false`
   - `gt` / `gte` / `lt` / `lte` → `false` (a missing amount is not "greater than 0")
   - `contains` / `starts_with` / … → `false`
   - `in` → `false` unless the set itself contains NULL
   - `and a NULL operand makes the whole rule *inert*: the rule is skipped and the
     run is logged as `skipped_null_operand`, not as `matched`.**
3. **The UI says so, at authoring time.** Because the engine knows the field's
   declared type, the rule editor renders `amount > 0` with a literal warning:
   *"applies only where `amount` is set."* The three-valued failure is prevented
   by making it visible, not by hoping.

**Residual [D].** `is_empty` and `is_not_empty` need an explicit, published
definition, because "empty" is otherwise a PHP-truthiness accident (`'0'` and
`false` are `empty()` but are neither blank nor null). Proposed: `EMPTY` = NULL,
`''`, or whitespace-only **after** trimming. A number column's `0` is **never**
empty. Published in the UI, tested, and stated in the operator's help text.

### A.4 Nested boolean grouping

**[D] Nesting is required at v1 — but one level deep.**

Rationale: the user's stated scope is *"field is set / not set"* and
*"value > < >= <= = !="*. A flat AND-list covers that. But the first real
requirement in this organisation that needs nesting is the ACL orphan flow
(§E): *"orphaned **and** (was a customer **or** was a supplier)"* — three
predicates, two connectives, one level of nesting. A system that ships flat AND
only and then adds nesting later must migrate every stored rule; shipping an
`op`/`children` node from day one means the **storage format never changes**.

Constraint **[D]**: groups may nest, but a **published** rule is limited to
**depth 3 and 50 leaf nodes**. The limit is enforced at publish, and the reason is
loop-protection cost (§C.1) and UI comprehension, not engine capability.

### A.5 Special conditions the brief did not name

| Condition | Why it earns its place **[D]** |
|---|---|
| **`changed`** | The single most-requested condition in every flow tool; and `FR-ACL-010-03` §2.1 already carries `action` ∈ `create`/`update`/`delete`, which makes it a free discriminat-or. Requires the engine to receive a **before-image**, not just the new row — see §C.7. |
| **`changed_from` / `changed_to`** | `changed` alone cannot express "only *now* has it become Closed"; you need the prior value. |
| **`is_empty`** | Distinct from `is_null` under the explicit empty rule in A.3 — `''` is not `NULL`. |
| **`related_count_gt`** | *"file a task when a customer has more than 3 overdue items."* Real, but **deferred to v2** (Phase F): it requires a related-records capability contract, which is a second instance of the BR-CAL-010 problem and should not be improvised. |
| **`user_role_is`** | Cheap and high-value: it makes rules *audience-scoped* (only accountants see this one) without a second permission system. Pairs with the `SS_`/`SA_` security-area convention in `AGENTS_ARCH.md`. |
| **`today_is` / `days_until_gt`** | Time-window rules ("escalate if unresolved for > 5 days"). **Requires a scheduled trigger, which the module does not have — defer both to v2**, behind the `ksf_FA_Common` scheduler whose `0_ksf_wf_jobs` table already exists. |

**Deliberately rejected [D]:** `matches_regex`. It is a ReDoS vector and an
expression-injection vector, and nothing in the stated scope needs it. If it is
ever wanted, it ships with a bounded, non-backtracking engine, never `preg_match`.

---

## B. Action model

### B.1 The catalogue

**[D]** The brief's list (math, set, unset, format, save, emit-event) is the
right list. SuiteCRM's remaining useful actions, added:

| # | Action | v1? | Notes |
|---|---|---|---|
| 1 | `set_field` | **v1** | Literal, or a reference to a previous step's output |
| 2 | `unset_field` | **v1** | Explicit NULL, distinct from `set_field ''` — a real distinction for nullable columns |
| 3 | `modify_field` (format: `upper`, `lower`, `title`, `trim`, `round(n)`, `prefix`, `suffix`) | **v1** | The brief's "change/format". A **whitelist of named transforms**, not a format string. |
| 4 | `math` | **v1** | **Named operators only**: `add`, `subtract`, `multiply`, `divide`, `percent_of`, `round`. Operands are field references or literals. **No expression language — this deletes the `eval()` RCE.** |
| 5 | **`save_record`** | **v1** | The brief's "a save". **This is the action the whole module exists for** and the one that does not exist today (§1.4). Must be the *only* action that writes, and it runs once at the end of the chain (§B.3). |
| 6 | **`emit_event`** | **v1** | The brief's event emitter, replacing `wf_trigger_event()`'s `return true`. `hook_invoke_all($name, $payload)`. This is what makes the engine compose with the rest of the stack. |
| 7 | `assign_owner` | **v1** | SuiteCRM's most-used non-email action. Sets the ACL ownership field — the direct bridge to `FR-ACL-010-04`. |
| 8 | `create_related` | v2 | Creates a record in **another module** — only ever through that module's capability hook, never its tables (standing decision #2). The §E task-filing flow is an instance of this; at v1 it is a *built-in* (§E) rather than a generic action, because the contract does not exist generically yet. |
| 9 | `notify` | v2 | Email/notification. Deferring is a **deliberate** call: it is the only action that can be slow, flaky, and externally visible, and it is the wrong thing to debug while the loop and transaction semantics are unproven. SuiteCRM's action, not a v1 need. |
| 10 | `run_modifier_set` | **defer indefinitely** | SuiteCRM's named sets of field operations. Our `save_record` + step list covers it; a second abstraction over the same thing is pure overhead. |

**[D] Explicitly excluded from v1:** `http_request` / `webhook`. The existing code
offers `webhook` and it is a stub. An outbound HTTP call from an engine that runs
inside the user's transaction is the worst possible combination — it is slow,
non-transactional, non-idempotent, and an SSRF vector. If it ships, it ships in
v2 **outside** the transaction, via a job row (§C.4), never inline.

### B.2 Action shape

**[D]** Uniform, so the UI can render any action generically:

```json
{
  "id": "a3",
  "type": "modify_field",
  "config": { "field": "in_dis_name", "transform": "title" },
  "on_failure": "abort",          // abort | continue
  "label": "Title-case account name"
}
```

`config` is validated per-type by that type's own schema class at **publish** time
(§D.3), so a malformed action is a publish-time error, never a runtime surprise.

### B.3 Composition, and whether actions return values

**[D] Actions run in declared order over a single working copy of the record.
Later steps see earlier steps' effects. `save_record` is *not* an ordinary step —
it is the chain's terminal write, and the engine commits at most once per chain.**

**Return values: yes, and they must be namespaced.**

**[D]** An action may declare an `output` name; the engine stores it in the
run-scoped `StepOutputs` map. Subsequent actions and conditions reference it as
`${a3.created_id}`.

Three properties make this safe:

1. **Outputs are run-scoped, never persisted to the record**, and never visible
   across chains. Two workflows on one record cannot see each other's outputs.
2. **Outputs are a *reference* in conditions and actions, never *interpolated*
   into SQL.** Every use goes through the same `TypeCoercer` as a field value, so
   an output cannot become an injection vector.
3. **Actions that return nothing simply declare no output**, and referencing an
   undeclared output is a **publish-time** error, not a runtime `null`.

**[D] One rule that prevents a whole class of bug:** *writing the record is
terminal and idempotent*. The chain accumulates mutations in memory and performs
at most one `UPDATE` at the end. This is what makes §C.1 (loop protection)
tractable — there is exactly **one** write per chain to attribute.

### B.4 Failure semantics per action **[D]**

`on_failure: abort | continue` is per action, but the chain outcome is the
aggregate:

- `abort` (default) → stop the chain; `save_record` **does not run**; the run is
  logged `failed`. The user's save is unaffected (§C.2).
- `continue` → log `degraded`, run the rest, still `save_record`.

---

## C. The hard problems

### C.1 Loop / recursion protection — the most important design decision

**[D] This is the problem to get right first.** A workflow that writes a record
re-triggers the workflow that wrote it. The existing module has **no protection
whatsoever** — no guard, no depth limit, no exclusion, and (because no action
writes) not even the ability to loop. Adding `save_record` introduces the failure
mode and it must not be introduced without the defence in the same change.

**Four independent mechanisms, all required — they defend against different
failures, and none of them alone is sufficient:**

**(a) Re-entrancy guard — a per-request in-memory stack.**

```php
$key = $recordType . ':' . $recordId;
if (in_array($key, $this->activeRecords, true)) {
    $this->log('skipped_reentrant', $key);
    return;                       // not an error — a legitimate, expected stop
}
```

Cheap, exact, and it catches the direct case: workflow A saves record R, R's save
event re-enters the engine for R, and A is already running for R. **Note the
asymmetry with (b): the guard is keyed on the *record*, the limit is keyed on the
*chain*.**

**(b) Depth limit — a hard cap on nesting.**

`MAX_CHAIN_DEPTH = 5`. Beyond it, the run stops and is logged
`skipped_depth_exceeded`. This catches the indirect case the per-record guard
misses: A saves R1, which saves R2, which saves R3… — 200 distinct records, no
re-entrancy, still an infinite chain.

**[D] Why 5.** It permits the legitimate shapes — orphan-sweep touching a task,
task completion touching its parent, a two-level cascade — and stops the
pathological case long before it exhausts a request. It is a constant in one
place, named `MAX_CHAIN_DEPTH`, not a magic number.

**(c) Origin marking — every write is attributed, and the engine can exclude it.**

**[D]** This is the mechanism that actually solves SuiteCRM's problem, and it is
the one that is *not* optional. Every save the engine performs carries:

```php
$context = [
    'engine_run_id'   => $runId,      // which chain is responsible
    'engine_workflow' => $workflowId, // which workflow
    'engine_depth'    => $depth + 1,
    'origin'          => 'workflow',  // vs 'user' | 'import' | 'api'
];
```

and a workflow may declare **`ignore_own_writes`** (default **on**): a change whose
`engine_run_id` descends from this workflow's own run does not re-trigger it.

**[D] This is strictly stronger than SuiteCRM's "ignore self-triggered" checkbox,
and the difference matters.** SuiteCRM's version is a boolean asking "did I cause
this?" — unanswerable, because nothing records causation, so it can only be
approximated by guessing from field values. Here the run id is *in the payload*, so
the answer is exact, transitive (the run id is carried into the child run, so a
3-hop cascade back to the origin is still recognised), and auditable — the run log
can reconstruct the exact cascade that happened.

**[D] Crucially, the marking must be available to *other* modules' listeners too.**
`origin` is part of the standard `record_changed` payload proposed in
`FR-ACL-010-03` §2.1, so an ownership responder can distinguish "a user changed
the owner" from "a workflow reassigned it". **Recommend adding `origin` and
`engine_run_id` to that FR's payload table** — it is a two-field change to a
Proposed document and it materially improves the orphan story: a workflow-induced
reassignment should not itself be able to orphan a record.

**(d) Cycle detection over a *rule graph*, as a publish-time check.**

**[D]** `emit_event` and `create_related` can form a cycle across workflows
(A emits `x`, B listens for `x` and emits `y`, C listens for `y` and emits `x`).
Runtime guards (a)–(c) bound the damage but cannot *prevent* it. Therefore
**publish validates the event-routing graph** and rejects a workflow set that
introduces a cycle, reporting the exact cycle path. This is a static check, it
costs nothing at runtime, and it converts a class of runtime incident into a
publish-time error with a legible message.

**What is deliberately *not* done [D]:** a per-workflow "max runs per request"
counter as the primary defence. It bounds the blast radius but not the shape, and
it produces the worst possible failure — a rule that works on small data and
silently half-works on bulk, which is exactly the class of bug nobody reports.

---

### C.2 Transaction boundary

**[D] The engine runs its writes in its own transaction, **after** the originating
transaction has committed. It never runs inside the caller's transaction.**

**The trade-off, stated honestly:**

| | Inside the caller's transaction | After commit **[D] — chosen** |
|---|---|---|
| Atomicity | Total: workflow + user save commit or roll back together | Split: the user's save is already durable; the workflow's is a separate commit |
| Failure blast radius | **A failed workflow action rolls back the user's save.** The user typed "Save", got "Saved", and their data is gone because a notification webhook 500'd. | A failed workflow leaves the record saved and the workflow run logged `failed`. The user's intent is honoured; the automation is degraded. |
| Visibility | Workflow writes are invisible to concurrent readers until commit | Same, but the record is already visible to everyone; the workflow's changes land a moment later and are briefly absent |
| Retrying | Cannot retry without replaying the user's save | Can retry the workflow run alone, because it has its own unit of work |

**[D] The first row is decisive.** Inside-transaction execution makes the *user's*
data hostage to the *automation*. A workflow engine that can lose a user's saved
record is worse than no engine, because the failure is invisible and rare. After
commit, the worst case is "the automation did not happen", which is visible in the
run log and recoverable by retry.

**The known trap — and how it is handled. [V]** `hook_db_postwrite` fires **before**
`commit_transaction()` in at least the sales-delivery path
(`write_sales_delivery()`: `hook_db_postwrite` at line 200, `commit_transaction()`
at 201 — per `AGENTS_ARCH.md` §10.1, and `FR-ACL-010-03` §1.1 states this as
verified). So **`hook_db_postwrite` is post-write, not post-commit, and the engine
must not treat it as a commit boundary.** It is still a *usable dispatch point* for
*deferring* (§C.4) — which is precisely the point: the engine's handler's job at
that hook is to **enqueue**, not to execute.

**[D] The mechanism, therefore, is a deferred run queue:**

1. The `record_changed` emitter (whoever owns it — RBAC per `FR-ACL-010-03`) fires.
2. The engine's handler **does not evaluate anything.** It writes one row to
   `0_wf_runs` with `status = 'pending'` and returns immediately.
3. The queue is drained at a real post-commit point:
   - **end of request**, in a registered shutdown handler, *after* FA's transaction
     has closed; and
   - by the `ksf_FA_Common` scheduler job for anything not drained (crash, timeout,
     fatal). **`0_ksf_wf_jobs` already exists with `next_run_at`, `fail_count` and
     `last_error` — verified live — so the drain worker is a row, not a subsystem.**
4. Drain opens `begin_transaction()`, runs the chain, commits.

**[D] One non-negotiable guard.** Per `FR-ACL-010-03` §1.1, **no engine code path
may `exit`** — not from `db_postwrite`, not from the drain, not from an action. A
workflow engine that can terminate a request corrupts whatever transaction was open.
This gets a dedicated test (it is `FR-ACL-010-03` AC3) and a lint rule.

**[D] The residual weakness, stated rather than hidden.** Between step 2 and step 3
there is a window in which the record is committed but its workflow has not run.
A crash in that window leaves a `pending` row that the scheduler picks up — correct —
but if the scheduler job is also not running, the run sits pending indefinitely. The
run log must therefore show `pending` rows prominently, not just failures, and the
admin UI needs a visible **"workflow backlog"** indicator. **An engine whose health
is invisible is not trustworthy**, which is §C.7.

---

### C.3 Ordering and determinism

**[D] Sequential, in a total order, always. No parallelism.**

**Ordering key: `(priority DESC, created_at ASC, id ASC)` — a strict total order,
always evaluated from a single indexed query, never from a cached in-memory list
that another workflow may have mutated.**

**[D] Determinism is a correctness property, not a performance one.** Two workflows
that both set `status` must produce the same result on every run, on every
instance, forever. Concretely, for every run, log the ordered `workflow_id` list
into the run row — so "why did it end up Closed?" is answerable from the log alone
rather than by re-deriving it.

**[D] The write-conflict rule.** Actions accumulate into one working copy (§B.3) and
there is one write, so two workflows cannot interleave writes on the same record.
The *only* remaining conflict is two chains on the same record in the same request;
those are serialised by the per-record active stack (C.1a).

**[D] Priority semantics: later wins.** Higher priority runs first, so a
lower-priority workflow observes (and can override) the result. This must be stated
in the UI's rule editor, because the alternative — first wins — is equally
defensible and silently choosing either one is how rules become unexplainable.

**[D] Deferring a rule is not pausing it.** The draft/publish model (§C.6) means an
edit never affects a run in flight: a run pins the workflow version it started with
(§C.6). Combined with the total order, this makes a run fully reproducible from its
own log.

---

### C.4 Bulk operations

**[D] A save touching 500 records must not run 500 workflow chains synchronously.
The queue (§C.2) is what makes this fall out for free, but two rules are needed on
top.**

**Rule 1 — the emitter batches. [D]** The `record_changed` emitter writes **one
`0_wf_runs` row per affected record** via a single multi-row `INSERT`. For 500
records that is one statement, not 500. The run table carries
`batch_id` so the batch is queryable as a unit.

**Rule 2 — the drain is bounded and resumable. [D]**

| Bound | Value | Why |
|---|---|---|
| `MAX_RUNS_PER_REQUEST` | 100 | Keeps the post-commit drain under a second; the rest is picked up next time. |
| `MAX_CHAIN_DEPTH` | 5 | C.1(b). |
| Total wall-clock per request | 2 s | Checked between chains; a chain in progress always finishes (never half-applied). |
| Per-chain timeout | 10 s | A chain that exceeds it is killed, logged `timeout`, and the record is left unsaved. |

**[D] Rule 3 — bulk suppression, opt-in and visible.** A source that already knows
it is bulk (`origin = 'import'`) may be configured to **queue only** rather than
evaluate, with workflows declaring `run_on_import = yes|no` (default `no`). This
is what stops a 500-row import from generating 500 review tasks.

**[D] The consequence that must be stated to users:** for bulk operations the
engine is **eventually consistent** — a record saved in a batch may have its
workflow applied seconds later. The run log is the place that is visible, and the
UI must say "pending" rather than pretending a batch is done.

---

### C.5 Idempotency and failure handling

**[D] The idempotency key is `(workflow_id, workflow_version, record_type, record_id,
source_event_id)`.**

This makes "exactly once" the default by construction: an event replayed by a retry,
a queue redelivery, or a double-emitter produces the **same key**, and a unique
index turns the second attempt into a no-op at the database level rather than a
race in PHP. `source_event_id` must come from the emitter, so this depends on
`FR-ACL-010-03` AC2 ("exactly one `record_changed` per committed write") being met;
where it is not yet, the queue's own de-dup on `(record, pending)` is the fallback.

**[D] Retry policy — by failure class, not by a blanket retry count:**

| Class | Examples | Policy |
|---|---|---|
| **Transient** | deadlock, lock wait timeout, DB connection loss | Retry in-run, up to 3, exponential backoff (50 ms / 250 ms / 1 s). |
| **Deterministic** | `emit_event` to a module that declined the event; `create_related` rejecting a required field | **No retry.** Retrying a deterministic failure is pure cost. Log `failed`, surface. |
| **Developer error** | an action type or field that no longer exists | **No retry. Fail loudly, and disable the workflow.** A published workflow referencing a deleted column is a deploy-time defect; leaving it firing-and-failing every save is worse than stopping it. |
| **Guard rejection** | re-entrancy, depth exceeded | **Not a failure.** Log at `info`. These are the system working (§C.1). |

**[D] Dead-letter: a manual requeue, not an automatic one.** A `dead_letter` flag on
`0_wf_runs` plus an admin "Requeue" action. Automatic dead-lettering hides
automation rot inside a queue; a visible list of things that need a human is how
they get fixed. Combined with §C.7's health view, an owner sees the backlog.

**[D] What surfaces to the user, and what does not — the split is the design:**

| Surfaces to the user | Never surfaces |
|---|---|
| Workflow authored **by this user**, failing on **a record they just saved** — a single unobtrusive line: *"1 workflow did not complete. [View]"* | Failures on records the user did not touch |
| Any failure on a **security/ownership** workflow (orphan, de-assignment) | Per-action noise on ordinary edits |
| Anything when the **backlog** is non-empty or growing | Guard rejections (C.1) |

**[D] Rationale.** The engine will be attached to saves on tables users care about.
Surfacing every automation hiccup trains users to ignore the message, which
guarantees the one message that matters — the ownership one — will be ignored too.
The bar is: **surface when a human can plausibly act on it.**

---

### C.6 Draft / published lifecycle and versioning **[D] — required, not optional**

**[D] A running workflow must never be editable in place. Rules are immutable
versions; editing creates a new draft.**

| Table | Holds |
|---|---|
| `0_wf_workflows` | `workflow_id, name, record_type, status (draft\|published\|archived), published_version_id, company_id, created_by, created_at` |
| `0_wf_versions` | `version_id, workflow_id, version_no, definition (JSON), hash, published_at, published_by, retired_at` |
| `0_wf_runs` | `run_id, workflow_id, **version_id**, batch_id, record_type, record_id, source_event_id, idempotency_key (UNIQUE), status, depth, parent_run_id, origin, error, started_at, finished_at` |
| `0_wf_run_steps` | `run_id, step_id, action_id, status, input, output, error, duration_ms` |

**Rules [D]:**

1. **Publish snapshots.** The editor mutates a draft; publishing writes an
   immutable `0_wf_versions` row. Runs pin `version_id`.
2. **A run in flight is unaffected by an edit.** It already holds `version_id`. This
   is the direct answer to "can you edit a live workflow without it taking effect
   mid-execution" — **yes, by construction, not by locking.**
3. **Every definition change increments the version** and is visible in the UI.
   "What changed in this rule between 3 and 4" must be answerable.
4. **The `hash` on each version** is what makes §C.3's "reproduce the run" claim
   checkable: log `version_id` + `hash` in the run row; the run log links to the
   exact JSON that executed.
5. **Archive ≠ delete.** Archiving stops new runs; existing runs and history remain.
   Hard delete of a version with runs is refused.

**[D] Reuse the existing `0_ksf_wf_jobs` scheduler rather than building a second
time source.** **[V]** That table exists live with `interval_p`, `next_run_at`,
`fail_count` and `last_error`. The workflow scheduler is *one more job* in it.

---

### C.7 Audit / execution log **[D] — required for trust; without it none of the above is operable**

**[D]** `0_wf_runs` + `0_wf_run_steps`, as tabled in C.6. Non-negotiable fields:
the **exact** workflow id, version id and hash; the record identity; the
**ordered** workflow id list for the record; the depth and parent run; the origin;
per-step input/output/error/duration; the trigger evaluation outcome **including
which condition matched and which did not**; and the outcome.

**[D] Three specific requirements that make the log trustworthy rather than merely
present:**

1. **Explain the negative.** A rule that did not fire must be answerable: *"triggered
   for record 4821? No — condition 2 (`owner_id is_null`) was false because
   `owner_id` = `u07`."* Without this, "my workflow doesn't work" is unanswerable
   and support cost is unbounded. **[D] log the per-condition evaluation, always,
   including on match.**
2. **Never log secrets.** Action configs and step inputs are truncated and
   redacted; a `Notify` action's recipient list is masked. **[D] A log viewer that
   shows a password in a textarea is a data-breach vector with a UI.**
3. **Retention.** Runs and steps are operational data and must be pruned
   (`retention_days`, default 90), while **the published version history is
   business data and is never auto-pruned.** Conflating them means either losing
   audit history or letting the table grow without bound.

---

## D. The definition UI

### D.1 Does the existing module have one? **[V] — partially, and it does not work**

**[V]** Two CRUD forms exist and neither loads: wrong include path, array/mysqli
confusion, wrong `$path_to_root` in dev, wrong security area, no menu registration,
no schema. Action configuration is **raw JSON in a textarea**
(`pages/actions.php:93`) with no validation. There is no run log viewer, no
test-against-a-record, no draft/publish, no version history.

**So the UI is a rewrite, not an extension.** What to keep: nothing. What to keep
*conceptually*: FA's `start_form()` / `start_table()` / `simple_page_mode()`
idiom, which is the house style and should be followed — a bespoke JS rule-builder
is not required at v1 and would not be idiomatic.

### D.2 The rule editor shape **[D]**

A single page, three bands:

```
┌ Workflow: "Flag high-value orphans"   Status: ● PUBLISHED  v4  ──────────┐
│ Record type: [customer ▾]   Trigger: [record_changed ▾]  Action: on update │
├────────────────────────────────────────────────────────────────────────────┤
│ WHEN  ( all must match )                                                    │
│  1  [owner_id ▾] [is empty ▾]                          ☰ ✎  Condition       │
│  2  [amount     ▾] [is greater or equal ▾] [50,000.00]        Condition    │
│  3  [+ condition]                                                        │
├────────────────────────────────────────────────────────────────────────────┤
│ THEN ( in order )                                                            │
│  1  ⚙ Assign owner  →  [Accounts Review Team ▾]                     ☰ ✎    │
│  2  ⚙ Modify field  →  [review_state] [set] [Pending review]         ☰ ✎    │
│  3  ⚙ Save record                                    (always last, fixed) │
├────────────────────────────────────────────────────────────────────────────┤
│ [Test against a record…]  [Save draft]  [Publish]  [History]  [Run log]     │
└────────────────────────────────────────────────────────────────────────────┘
```

**[D] Rules that make the editor correct rather than merely present:**

- **The value widget is type-driven.** §A.2's field type registry means
  `amount` renders a numeric input, `start_date` a date picker, `status` a
  **dropdown of the declared enum values**. `status = 'closed'` when the enum has
  `'Closed'` becomes impossible rather than merely warned about. This is the
  highest-leverage UI decision in the whole document: it is what makes
  §D.3's validation nearly free.
- **`gte`/`lte` are distinct buttons**, not a raw operator dropdown, because
  "at least" is the intent and `> 49999.99` is an implementation detail nobody
  should be asked to express.
- **The NULL/empty warning from A.3 renders inline**, under the condition it
  affects.
- **`save_record` is fixed at the end**, not an action you can drag. One write per
  chain, always (§B.3).
- **An action that cannot be reached** (an action type the module doesn't
  register) is a **publish error**, never a silently-absent row.

### D.3 Validation **[D] — publish-time, comprehensive, and the reason drafts exist**

Publishing rejects the definition unless **all** of these hold:

1. Every field reference resolves to a real column of the target table.
2. Every literal is valid for its column's declared type (§A.2) — non-numeric
   into `decimal`, non-member into an enum, unparseable into a date.
3. Every action type is registered, and its `config` validates against that type's schema.
4. Every `${output}` reference names an output declared by an **earlier** step.
5. Nesting ≤ depth 3, ≤ 50 leaves (§A.4).
6. The event graph introduces no cycle (§C.1d).
7. The record type has a registered trigger source.

**[D] Validation is skipped when nothing can change** — `is_empty` needs no value,
and §A.2's enum check must not demand one.

**[D] A statically-impossible condition is a publish *warning*, not an error**
("`amount > 50000` and `amount < 100` can never match"), because it is far more
often a mistake in the intent than in the typing, and hard-blocking it teaches
users to publish without reading.

### D.4 Draft / publish **[D]**

Drafts are visible and editable, obviously labelled **DRAFT**, and **never
evaluated**. Publish snapshots a version and makes it live. The version history
lists each version with its publish time, author, and a diff. Archive stops new
runs without deleting history.

### D.5 Execution log viewer **[D]**

Three views, in increasing detail:

1. **Health** — backlog depth, failures in last 24 h, workflows that errored and were
   auto-disabled. This is the view that answers "is automation working?" (§C.5's
   residual weakness).
2. **Run list** — filter by workflow, record, status, date range, batch.
3. **Run detail** — the per-step trace, **including every condition that did not
   match and why** (C.7.1), plus a **Requeue** button for dead-lettered runs.

### D.6 "Test against a record" **[D] — build this first; it is the highest-value UI affordance**

SuiteCRM has it and it is the single best reason to trust a flow tool. **[D]** It
is also nearly free, because the engine already computes the per-condition trace
for the log (C.7.1).

Given a record id, the engine:

1. Loads the row and **evaluates every published workflow without executing
   anything** — no writes, no events, no email.
2. Shows, per workflow: the ordered list of workflows that *would* run, each
   condition green/red with the actual value and the comparison, and each action
   with its resolved parameters.
3. Optionally shows the resulting record diff.

**[D] Implementation is a pure function of what C.7 already requires**, which is
why it belongs in v1 rather than later: a dry-run evaluator is the *same code path*
with the executor stubbed, so the test affordance and the audit trail cannot drift
apart. A user who can see exactly what will happen has no reason to fear the loop,
the transaction, or the failure semantics — the three things in Part C.

---

## E. Relationship to the ACL work — the orphaned-record worked example

### E.1 The standing constraint **[D]**

> The workflow module is **generic**. It contains no Calendar schema, no ACL
> policy, and no orphan rule. It is the *instrument*; the ACL work is the
> *composition*.

Concretely, the engine must not name `0_fa_cal_entries`, `0_rbac_*`, or the string
`'orphaned_record'` in a conditional. It exposes two **generic** primitives the
composition needs — a `create_related` action and an `emit_event` action, both
`hook_invoke*`-only — and the actual rule is data in a workflow row.

### E.2 The composition **[D] — a workflow *definition*, not code**

**Prerequisites [V — these do not exist yet]:** the `record_changed` /
`orphaned_record` emitters of `FR-ACL-010-03` (zero matches in `ksf_FA_RBAC`
today), and the `0_rbac_audit_log` / `0_rbac_*` tables (which **do** exist).

**Workflow 1 — "Ownership audit row"** *(the simplest consumer; listed because
`FR-ACL-010-03` AC4 makes it a correctness requirement, not a nicety)*

| | |
|---|---|
| Trigger | `record_changed`, `action` = `create` \| `update` \| `delete` |
| When | `record_type` **is not empty** |
| Then | 1. `assign_owner` → *(no-op placeholder)* · 2. **`emit_event`** → `acl.audit_append`, payload `{module, record_type, record_id, action, user, origin}` · 3. `save_record` |

**[D]** Note the ordering requirement from `FR-ACL-010-03` §2.1 — the audit consumer
must run **before** ownership evaluation. In this engine that is expressed as
**workflow priority**, not as a dispatch hack: the audit workflow has higher
priority, and §C.3's total order guarantees it. That is the cleanest resolution of
that FR's open **Q-ACL-010-6** (no ordering guarantee across modules) available
today, and it is worth telling whoever owns the FR.

**Workflow 2 — "Orphan review task"** *(the worked example proper)*

| | |
|---|---|
| Trigger | `orphaned_record` |
| When | **all** of: `record_type` **is not empty** · `previous_owner` **is not null** *(re-sweep of an already-filed orphan must not duplicate)* |
| Then | 1. **`create_related`** → capability `task.create`, payload `{title: "Review orphaned {record_type} {record_id}", start_date: now + 1 day, assigned_to: {previous_owner} ?? review_pool, description: {module, record_type, record_id, previous_owner}}` · 2. `set_field` → `orphan_task_id` = `${a1.created_id}` · 3. `save_record` · 4. **`emit_event`** → `acl.orphan_task_filed`, payload `{record_type, record_id, task_id}` |

**[D] Why this respects the contract.** Step 1 is one `hook_invoke` to Calendar's
`calendar_task_create` (`ksf_FA_Calendar/hooks.php:519`, **[V]**). It crosses **no
table boundary** — the engine holds **no** SQL knowledge of
`0_fa_cal_entries`. Calendar sets `source_type = 'task'` explicitly, so the caller
cannot receive a silently-event-shaped entry (**BR-CAL-010 AC5**, **[V]** satisfied).
And step 2 gives the engine its **first real use of action return values** (§B.3):
`created_id` comes back from Calendar, is stored on the ACL record, and the emit in
step 4 lets the admin-queue UI (`FR-ACL-010-05`) link the two. **The engine has no
idea any of this is about orphans** — swap `orphaned_record` for
`quote_over_threshold` and the identical three steps work.

**[D] Loop exposure, stated plainly.** This is the flow most likely to loop: it
touches the record, which emits `record_changed`, which can orphan again. The
defences apply as designed — `origin = 'workflow'` marks the write, `ignore_own_writes`
(default on) prevents Workflow 2 re-triggering itself, the per-record stack stops
the direct case, and depth 5 stops the indirect. **A workflow that re-orphans a
record it was told to fix is a defect in the ownership logic, and the engine should
make it visible in the run log rather than prevent it silently** — that is the
correct behaviour for an ownership system.

---

## F. Phased plan

### v1 — the smallest thing that is genuinely useful

**[D] Build in this order; each step is independently valuable and testable.**

| # | Deliverable | Rationale |
|---|---|---|
| 1 | **Schema + value objects + type registry + coercer + condition evaluator**, with a full unit suite | The whole design rests on A.2/A.3. Nothing else is worth building until `TypeCoercer` and the NULL rules are tested to 100%. Zero FA coupling, so it lives in `ksf_Workflow` and is unit-testable standalone — exactly as `ksfraser/ksf-workflow` is today, but correct. |
| 2 | **Action registry + the 7 v1 actions + `save_record`** | Replaces `eval()` with whitelisted transforms. |
| 3 | **Re-entrancy guard, depth limit, origin marking** (§C.1 a/b/c) | **Must ship with `save_record`, in the same change.** Shipping the write without the guard is the one unrecoverable mistake in this plan. |
| 4 | **Run log + per-condition trace** (§C.7) | Cheap, and it is what makes the dry-run and the health view possible. |
| 5 | **Definition UI: draft → validate → publish** (§D.2, D.3) | Validation earns its keep here. |
| 6 | **Test-against-a-record** (§D.6) | Nearly free given step 4, and the highest-trust-per-line-of-code in the document. |
| 7 | **Wiring to `record_changed` / `user_changed` / `orphaned_record`**, queued, drained post-commit | Depends on the emitters existing. |
| 8 | **Workflow 2 (§E.2)** — the orphan task flow | The proof the engine composes. |

**[D] v1's acceptance test is one sentence:** *change a record, and within a second
the run log shows which workflows ran, in what order, which condition matched, what
each action did, and what it changed — and a second run of the same edit does the
same thing.* Nothing in v1 requires nesting beyond depth 3, `related_count`,
time-window triggers, notifications, or webhooks.

### v2 — deferred, with the reason stated

| Item | Why deferred |
|---|---|
| `notify` / `send_email` | The only slow, externally-visible, non-idempotent action. Wrong thing to debug while loop and transaction semantics are unproven. |
| `create_related` as a **generic** action | §E works because Calendar's contract exists. A generic action needs a *general* capability discovery contract (standing decision #3: a shared contract needs a second consumer). |
| `related_count_*` conditions | Same reason — needs a related-records capability contract. |
| Time-window triggers (`today_is`, `days_until_*`) | Need a scheduled trigger. `0_ksf_wf_jobs` exists **[V]**, so this is cheap — but it is a *new trigger class*, not a new condition. |
| `http_request` / `webhook` | SSRF + non-transactional + non-idempotent. Only ever outside the transaction, via a job row. |
| Hard deletes of workflow definitions | Archival is sufficient; deletion is a data-integrity question with no v1 pressure. |

### Explicitly not doing **[D]**

`matches_regex` (ReDoS/injection), `run_modifier_set` (redundant with the step
list), parallel execution (non-determinism), any expression language (the `eval()`
RCE), and any cross-module table access (standing decision #2).

---

## G. Explicitly unverified

| Item | Status |
|---|---|
| Whether a single **post-commit** point exists for non-cart module writes | **[UNVERIFIED]** — `FR-ACL-010-03` §1.2 / Q-ACL-010-3. **[D] The design is insulated:** the engine only *enqueues* at the dispatch point and drains at end-of-request, so a post-write-not-post-commit hook is sufficient. It would only matter if the enqueue itself must be transactional. |
| FA `hook_invoke_all` ordering across modules | **[UNVERIFIED]** — Q-ACL-010-6. **[D] Not relied upon:** §E's ordering uses engine priority, not module dispatch order. |
| `hook_invoke_first` decline semantics | **[UNVERIFIED]** — Q-ACL-010-6. **[D] Not relied upon:** the engine uses `hook_invoke_all` for its own emits. |
| Whether `0_ksf_wf_jobs`' drain is already running | **[UNVERIFIED]** — the table exists **[V]**; nothing was traced that reads it. |
| PHP floor for the redesigned engine | **[D] Recommend targeting 7.3 explicitly.** The current `ksfraser/ksf-workflow` requires `>=8.1` **[V]** and would not load in the 7.4 container. |
| Whether any deployed consumer relies on `ksfraser/ksf-workflow`'s **engine** classes | **[V] None found.** Only `ksf_FA_Woocommerce`'s state machine uses the package. Replacable. |

## H. Related

- [`Requirements/FR-ACL-010-03-lifecycle-events.md`](./Requirements/FR-ACL-010-03-lifecycle-events.md) — the three events; **recommend adding `origin` + `engine_run_id` to the `record_changed` payload (§C.1c)**
- [`Requirements/BR-ACL-010-event-driven-ownership.md`](./Requirements/BR-ACL-010-event-driven-ownership.md)
- [`Requirements/FR-ACL-010-05-orphaned-records.md`](./Requirements/FR-ACL-010-05-orphaned-records.md) — the admin queue
- [`Requirements/BR-CAL-010-capability-contract.md`](./Requirements/BR-CAL-010-capability-contract.md) / [`FR-CAL-010-001`](./Requirements/FR-CAL-010-001-task-creation-and-event-listing.md) — **[V] all four of this BR's gaps are closed in `ksf_FA_Calendar/hooks.php`; the BR's status line is stale**
- [`Shared_Responder_Traits_Design.md`](./Shared_Responder_Traits_Design.md) — the same mechanical-vs-policy line, applied to responders
- [`README.md`](./README.md) — standing decisions #2, #3, #6
- `../AGENTS.md` — three-repo convention, PHP 7.3 floor, `hook_db_postwrite` timing