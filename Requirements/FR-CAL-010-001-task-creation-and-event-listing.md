# FR-CAL-010-001 — Task creation and event listing

@BABOK Related: BR-CAL-010, BR-ACL-010 R6, BABOK 8.2 Solution Analysis
Status: **Proposed**
Module: `ksf_FA_Calendar` (provider); `ksfraser/ksf-calendar` (package, if the contract is
promoted); consumers: workflow module, ACL orphan responder
Date: 2026-10-14

> **Documentation only.** No hook signature was changed, no DTO was written, no Calendar
> code was touched.

---

## 1. The two capabilities, as they exist today **[V]**

Read from `ksf_FA_Calendar/hooks.php`. The FA convention used throughout is
`($data by reference, $opts = [])` with **`null` = "not handled"**, documented in the file
at `hooks.php:195-198`.

### 1.1 Create

```
hooks.php:213   calendar_entry_create(&$data, $opts = [])
  → FA_Cal_Module::create_entry($data)            FA_Cal_Module.php:476
    → CalendarService::createEntry($data)          ksf-calendar CalendarService.php:84
  returns int|null   (new entry id, or null on failure)
```

**[V] Required fields — exactly two**, enforced by `validateEntryData()`
(`CalendarService.php:804-821`):

| Field | Requirement |
|---|---|
| `title` | **Required.** `CalendarException('Title is required')` |
| `start_date` | **Required.** `CalendarException('Start date is required')` |
| `end_date` | Optional. If present must not precede `start_date` |
| *everything else* | Optional, defaults silently |

**[V] Silent defaults** (`CalendarService.php:90-93`): `source` → `CalendarEntry::SOURCE_USER`;
`source_type` → `CalendarEntry::TYPE_EVENT`. A consumer that omits `source_type` gets an
**event**, not a task — silently.

**[V] Failure is not an exception to the caller.** `create_entry()` catches `\Throwable`,
records the message via `getLastErrorMessage()`, and returns `false`
(`FA_Cal_Module.php:477-492`). The hook converts `false` → `null`.

### 1.2 List

```
hooks.php:289   calendar_entries_query(&$data, $opts = [])
  → FA_Cal_Module::get_entries($start, $end, $filters)   FA_Cal_Module.php:376
    → CalendarService::getEntriesForDateRange()            CalendarService.php:390
  returns array   (also placed in $data['entries'])
```

**[V] Window:** `start` / `end` as `Y-m-d`. **`FA_Cal_Module.php:378-379` defaults them to
the current calendar month if omitted — silently.**

**[V] Supported filters** (`CalendarService.php:411-480`):

| Filter | Notes |
|---|---|
| `source`, `source_type` | `source_type` accepts a scalar **or an array** → `IN (…)` |
| `assigned_to`, `user_id` | `VARCHAR` columns, **not** FKs — see §3 |
| `customer_id`, `project_id` | |
| `status` | Exact match |
| `status_open` | Boolean; expands to a hardcoded 9-status closed-list **[V: `:461-478` — the list is duplicated in SQL, a drift risk]** |
| `include_private` | |

**[V] Implicit filter:** `invitee_user_id` is set from `user_id` when the latter is present
and the former is not (`FA_Cal_Module.php:391-393`) — so `user_id` silently widens the
result to entries where the user is an **invitee**, not only where they are the owner.
A consumer relying on `user_id` to mean "assigned to" may get invitee rows too.

**[V] Return shape:** `CalendarEntryDTO::fromEntity($entry)->toFullCalendarArray()`
(`FA_Cal_Module.php:403`) — a **render** DTO, plus recurrence expansion via
`get_child_entries()` for overridden series (`:420-424`).

## 2. Requirement

> **[D]** A consumer can create a task and can scan for events **without any access to
> Calendar's tables**, and cannot silently receive the wrong answer.

| # | Requirement |
|---|---|
| F1 | Creation takes an explicit contract; only `title` and `start_date` are required, and this is **published** rather than implied by "etc." |
| F2 | Listing takes a **mandatory** window. Omitting it is an error. |
| F3 | Listing returns a **domain DTO** with stable named fields, separate from the FullCalendar render array. |
| F4 | `status_open`'s closed-status list is expressed **once** and reused, not duplicated in SQL. |
| F5 | The `user_id` → `invitee_user_id` widening is either removed or **published**. |
| F6 | Discovery: the module answers a capability question without the caller hardcoding a hook name. |

**[D] What this requirement does NOT do:** it does **not** create the DTO class, and it
does **not** choose where the DTO lives. Both are open — see
[`OPEN-QUESTIONS.md`](./OPEN-QUESTIONS.md) **Q-CAL-010-1** and **Q-CAL-010-2**.

## 3. Why `assigned_to` / `user_id` are weak keys **[V]**

`0_fa_cal_entries.assigned_to VARCHAR(100)` and `user_id VARCHAR(50)` **[V —
`sql/install.sql:34,35]`**. These are **free-text columns, not foreign keys**. There is no
`0_fa_cal_entries.employee_id`.

Consequence for the stated use case — *"find events for employee X in window Y"* — the
filter is a **string comparison against whatever the writing module put there**. Two
providers writing the same employee under different conventions yield two disjoint sets,
and nothing detects it.

**[UNVERIFIED]** — whether an actual convention is enforced today (a constant, an enum, or
nothing at all) was not traced. **Q-CAL-010-3.**

## 4. Acceptance criteria

| # | Criterion |
|---|---|
| AC1 | A creation request without `title` fails naming `title`; without `start_date`, names `start_date`. |
| AC2 | A creation request without `source_type` produces `source_type = 'event'`, and the caller can **tell** that is what it got. |
| AC3 | A list request omitting `start`/`end` raises a clear error; it does **not** return the current month. |
| AC4 | A list response exposes `id`, `source_type`, `status`, `assigned_to`, `start_date`, `end_date` as named, stable fields. |
| AC5 | Renaming or removing a key in the FullCalendar render DTO does not change the domain DTO. |
| AC6 | "Find events for employee X in window Y" returns entries where X is the **assignee**, and the consumer can state whether invitee matches are included. |
| AC7 | Adding a new closed status changes the `status_open` result in **one** place. |
| AC8 | A workflow module files a task for an orphaned ACL record with **no** SQL access to `0_fa_cal_entries`. |
| AC9 | A consumer can ask "is task creation available?" and get an answer without attempting a creation. |

## 5. Explicitly unverified

| Item | Status |
|---|---|
| The creation DTO's field set | **Open — Q-CAL-010-2.** Not invented here. |
| Where a domain DTO should live (module vs package) | **Open — Q-CAL-010-1.** README #3 requires a second consumer before a shared package is justified; the ACL responder would be that second consumer. |
| Whether `my_tasks` reads `source_type = 'task'` | **[UNVERIFIED]** |
| Whether the `status_open` closed-list in SQL matches `CalendarEntry::isOpenStatus()` | **[UNVERIFIED]** — the comment says it replicates that logic; drift between them is plausible and unchecked. **Q-CAL-010-5.** |
| Whether `hook_invoke_first`'s `null` convention (README #3) is what makes these four methods reachable | **[UNVERIFIED]** — these are `hook_invoke*` targets, not responders, so the convention is inverted; see Q-ACL-010-6. |

## 6. Related

- [BR-CAL-010](./BR-CAL-010-capability-contract.md) — what exists vs what is missing
- [FR-ACL-010-03](./FR-ACL-010-03-lifecycle-events.md) §2.3 — the consuming responder
- `ksf_FA_Calendar/hooks.php:190-302` — the contract in source
- [`README.md`](../README.md) standing decisions #2, #3