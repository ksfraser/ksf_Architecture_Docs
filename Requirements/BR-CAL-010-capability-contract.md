# BR-CAL-010 — The Calendar capability contract

@BABOK Related: BABOK 8.1 Solution Strategy, 9.1 Requirements Analysis
Status: **Proposed** — mostly **already implemented**; this BR records and closes the gaps
Module: `ksf_FA_Calendar` (capability provider), any workflow module (consumer)
Date: 2026-10-14
Consumed by: [BR-ACL-010](./BR-ACL-010-event-driven-ownership.md) §2.3 (`orphaned_record`
task-filing responder)

> **Documentation only.** No Calendar code was changed, no hook was added, and no DTO was
> written.

---

## 1. Business driver

> **[D] The core Calendar module must NOT create review/follow-up tasks itself. That is
> a WORKFLOW concern. Calendar exposes capability; the workflow module composes the
> response.**

This restates standing decision **#3** in
[`ksf_Architecture_Docs/README.md`](../README.md): *responders return data, consumers
render; no cross-module table access.* Decision **#2** is its schema half.

The concrete driver is the `orphaned_record` consumer in
[FR-ACL-010-03](./FR-ACL-010-03-lifecycle-events.md) §2.3 and the admin-queue responder
in [FR-ACL-010-05](./FR-ACL-010-05-orphaned-records.md): something must file a task when
a record is orphaned. That consumer needs to create a task and **has no business** knowing
Calendar's schema.

## 2. What Calendar already provides **[V]**

**This is the most important finding in this document: the capability contract largely
already exists.** `ksf_FA_Calendar/hooks.php`, class `hooks_ksf_FA_Calendar extends
hooks` (`:25`), already exposes four hook methods, with the FA-conventional signature
`($data by reference, $opts)` and **`null` = "not handled"** stated in the file's own
convention comment (`hooks.php:195-198`):

| # | Hook method | Location | Delegates to |
|---|---|---|---|
| 1 | `calendar_entry_create` | `hooks.php:213` | `FA_Calendar_Module::create_entry($data)` (`:476`) → `CalendarService::createEntry()` |
| 2 | `calendar_entry_update` | `hooks.php:238` | `update_entry($id, $data)` (`:501`) |
| 3 | `calendar_entry_delete` | `hooks.php:263` | `delete_entry($id)` (`:522`) — **soft** delete |
| 4 | `calendar_entries_query` | `hooks.php:289` | `get_entries($start, $end, $filters)` (`:376`) → `getEntriesForDateRange()` |

**Both capabilities the brief asks for are already delivered:**

| Brief's ask | Already provided? |
|---|---|
| "a function/hook to CREATE a task (an event) at a specified date/time" | **Yes** — `calendar_entry_create`, with `start_date` / `end_date` supported **[V — `CalendarService::createEntry()`, `vendor/ksfraser/ksf-calendar/.../CalendarService.php:84-98`]** |
| "a function/hook to LIST events in active modules, so a workflow responder can scan for conditions (e.g. find events for employee X in window Y)" | **Yes** — `calendar_entries_query`, with `start` / `end` **and** filters including `assigned_to`, `user_id`, `source`, `source_type`, `status`, `status_open`, `customer_id`, `project_id`, `direction` **[V — `CalendarService::getEntriesForDateRange()`, `:390-480`]** |

So "find events for employee X in window Y" is `start`, `end`, `filters => ['assigned_to' => X]`.

**A task already exists as a first-class concept.** `0_fa_cal_entries.source_type` is
documented as `event, task, call, meeting, reminder, birthday, anniversary, renewal,
timetracking` **[V — `sql/install.sql:15`]**, and a `my_tasks` view is dispatched
(`cal.php:537`). There is a separate `reviews` view backed by
`ReviewManager` (`src/Ksfraser/FA/Calendar/Rules/ReviewManager.php`, with
`createReview` / `getPendingReviews` / `resolveReview`) **[V]**.

## 3. The gaps — what is actually missing

Four real gaps. Everything else in the brief is already satisfied.

### Gap 1 — No discovery contract **[V]**

`grep` for `getModuleCapabilities|hasCapability|respondToCapabilityRequest|getModuleConstants`
in `hooks.php` returns **zero** matches. AGENTS_ARCH.md §11 records a **4-method
discovery contract** a module may expose to others.

A consumer therefore has to know the hook method names **a priori**. It cannot ask
"does anything provide task creation?" — it must hardcode `calendar_entry_create` and
discover absence only by calling it and getting `null`. This makes the capability
**un-discoverable**, which is the main reason the contract feels unsafe to depend on.

### Gap 2 — The list contract returns a **render DTO**, not a domain DTO **[V]**

`calendar_entries_query` returns `CalendarEntryDTO::fromEntity($entry)->toFullCalendarArray()`
**[V — `FA_Cal_Module.php:403`]**. That is a **FullCalendar render shape**, produced for
a JavaScript calendar widget.

This is the substantive problem for the stated purpose. A workflow responder scanning for
conditions needs `status`, `assigned_to`, `source_type`, `customer_id` as **stable domain
fields**; it gets whatever FullCalendar's event schema happens to carry, and that schema is
driven by the view's rendering needs, not the consumer's. Coupling a workflow engine to a
render DTO means the calendar UI can break the workflow engine.

### Gap 3 — Silent default window **[V]**

`get_entries()` defaults `$start` to `date('Y-m-01')` and `$end` to `date('Y-m-t')` when
omitted **[V — `FA_Cal_Module.php:378-379`]** — i.e. **the current calendar month**, silently.

A consumer that forgets the window does not get an error. It gets *this month*, and a
rule that means "any event in window Y" quietly becomes "any event this month". For a
security-adjacent responder (the orphan sweeper) a silently-wrong window is a
**false-negative generator**.

### Gap 4 — No creation DTO or documented field contract **[V]**

`calendar_entry_create` takes an **untyped `array $data`** whose shape is documented only
in a docblock saying *"title, start_date, source, source_type, etc."* — the literal word
"etc." **[V — `hooks.php:204`]**.

Only **two fields are actually required**: `title` and `start_date`, enforced by
`validateEntryData()` **[V — `CalendarService.php:804-821`]**, which also rejects
`end_date < start_date`. Everything else is optional and defaults silently
(`source` → `SOURCE_USER`, `source_type` → `TYPE_EVENT`) **[V — `:90-93`]**.

Consequences: a consumer cannot know which of the ~45 columns in `0_fa_cal_entries`
**[V — `sql/install.sql:12-83`]** it is *supposed* to set, and two providers can disagree
about what a "task" is (`source_type = 'task'` vs `TYPE_EVENT`) with nothing to catch it.

## 4. Requirement

> **[D]** Calendar exposes capability through hooks and **creates no review or
> follow-up tasks of its own**. Consumers compose the response.

| # | Requirement | Status |
|---|---|---|
| C1 | Provide a hook to **create** a task/event at a specified date/time | **Already met** by `calendar_entry_create` |
| C2 | Provide a hook to **list** events in active modules for condition scanning | **Already met** by `calendar_entries_query` |
| C3 | Implement the 4-method **discovery contract** so a consumer can ask rather than assume | **Gap 1** |
| C4 | Publish a **stable domain DTO** for list results, distinct from the FullCalendar render array | **Gap 2** |
| C5 | Make the query window **mandatory** — no silent month default | **Gap 3** |
| C6 | Publish a **creation contract** (own DTO or documented required fields) — **does it need its own DTO? open question** | **Gap 4** |
| C7 | Calendar creates **no** review/follow-up task on its own initiative | Standing decision, restated |
| C8 | The task-filing path crosses **no** table boundary — the consumer asks Calendar | Restates README #2/#3 |

## 5. Acceptance criteria

| # | Criterion |
|---|---|
| AC1 | A consumer can determine that task creation is available **without** calling it and without hardcoding a class name. |
| AC2 | A list response exposes `id`, `source_type`, `status`, `assigned_to`, `start_date`, `end_date` as stable named fields, independent of the FullCalendar render shape. |
| AC3 | A list query omitting the window raises a clear error rather than defaulting to the current month. |
| AC4 | A creation request omitting `title` or `start_date` fails with a message naming the field. |
| AC5 | Creating a task sets `source_type = 'task'` **by explicit caller request**; the default is not silently task-shaped. |
| AC6 | Changing the FullCalendar render DTO does not change the domain DTO. (Guards Gap 2 from regressing.) |
| AC7 | A workflow module can file a task for an orphaned record having **no** SQL access to `0_fa_cal_entries`. |
| AC8 | Calendar, given no workflow instruction, creates zero review/follow-up tasks. |

## 6. Explicitly unverified

| Item | Status |
|---|---|
| Whether the domain DTO (C4) should live in the `ksf-calendar` **package** or the FA module | Not decided — it depends on who the second consumer is (README #3: a shared contract needs a second consumer to justify a package). **Q-CAL-010-1.** |
| The creation DTO's **field set** | **Not designed.** The question is explicitly open. **Q-CAL-010-2.** |
| Whether `ReviewManager`'s "review" is the same concept as this BR's "review task" | **Partly verified** — `ReviewManager` has `createReview` / `getPendingReviews` / `resolveReview` over calendar entries, and is UI-driven via `cal.php:2283` / `:2320`. Whether it is a rule-evaluation surface or a task queue is **not established**. **Q-CAL-010-4.** |
| That `my_tasks` is served from `source_type = 'task'` | **[UNVERIFIED]** — `cal.php:537` dispatches the view; the query behind it was not traced. |
| Whether any module currently *calls* these four hooks | **[UNVERIFIED]** — no consumer was traced. |

## 7. Related

- [FR-CAL-010-001](./FR-CAL-010-001-task-creation-and-event-listing.md) — the concrete contract
- [FR-ACL-010-03](./FR-ACL-010-03-lifecycle-events.md) §2.3 — the `orphaned_record` task responder
- [FR-ACL-010-05](./FR-ACL-010-05-orphaned-records.md) — the admin queue a filed task points at
- [`README.md`](../README.md) standing decisions #2 and #3
- `ksf_FA_Calendar/hooks.php:190-302` — the existing contract in source