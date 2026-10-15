# ksf_FA_HRM — Page Rebuild (filter → list → form)

**Date:** 2026-10-12
**Scope:** `pages/leave.php`, `pages/payroll.php`, `pages/recruitment.php`, `pages/reports.php`
**Served at:** http://localhost:8090 (`ksfii_app-fa`, PHP 7.4.33)
**Repos:** dev `/home/kevin/Documents/ksf_FA_HRM` (branch `main`), deployed `/home/kevin/Documents/ksf_Infrastructure/fa_modules/ksf_FA_HRM`
**Commit:** `709bd94` (dev repo; **not pushed**)

---

## 1. The reported bug

`pages/leave.php` and `pages/payroll.php` had no FrontAccounting bootstrap at all —
no `$page_security`, no `$path_to_root`, no `includes/session.inc`, no `page()` /
`end_page()`. They nevertheless called `db_query()`, `db_fetch_assoc()` and used
`TB_PREF`, all of which only exist after FA has booted. Both returned **HTTP 500
with an empty body** (fatal `Call to undefined function db_query()`, masked because
`display_errors` is off).

They also emitted **Bootstrap CSS** markup — `<div class="card">`,
`<table class="table table-sm table-striped">`, `<thead class="thead-dark">`,
`class="text-muted"`, `class="text-right"`. FA uses none of this; its own
stylesheet (`themes/default/default.css`) has no rules for any of it.

Before → after:

| URL | Before | After |
|---|---|---|
| `pages/leave.php` | **500** | 200 |
| `pages/payroll.php` | **500** | 200 |
| `pages/recruitment.php` | 200 (Bootstrap card, no bootstrap, would have 500'd once the shell included it) | 200 |
| `pages/reports.php` | 200 (Bootstrap card, no bootstrap) | 200 |
| `index.php?view=leave` etc. | 200 | 200 |
| site root `/` | 200 | 200 (unchanged throughout) |

---

## 2. The pattern applied

Modelled on `ksf_FA_CRM` (principally `pages/leads.php` and
`src/FrontAccounting/CRM/Controller/ContactsTabController.php`) and on core FA list
pages such as `admin/fiscalyears.php`.

Every page now follows this shape, top to bottom:

1. **Filter controls** — `start_table(TABLESTYLE2)` + `table_section_title(_('Filter'))`,
   with `array_selector_row()` / `text_row()` and a Filter submit.
2. **Summary / list table** — `start_table(TABLESTYLE)` + `table_header()`,
   `start_row()` / `label_cell()` / `qty_cell()` / `amount_cell()` / `end_row()`,
   and per-row `edit_button_cell('Edit'.$id, …)` / `delete_button_cell('Delete'.$id, …)`
   with `submit_js_confirm()` on destructive actions.
3. **Data-entry form** — `start_table(TABLESTYLE2)` +
   `submit_add_or_update_row()` / `submit_add_or_update_center()`.

Mechanics used, all core FA:

- `simple_page_mode(true)` resolves the submit button into `$Mode` / `$selected_id`,
  including FA's `Edit<id>` / `Delete<id>` button-name convention.
- One `start_form()` … `end_form()` spans all three sections, so the filter is
  preserved across an edit, a save or a delete without any URL plumbing.
- **Zero** Bootstrap classes. No inline `<div>`/`<table>` HTML at all.

`reports.php` has no third section by design — it is read-only, so the third slot
carries the "what these figures include / do not include" notes that used to be a
static "coming soon" list.

---

## 3. Security areas — and how each was verified

Each area below was read out of `hooks_ksf_FA_HRM::install_access()` in
`ksf_FA_HRM/hooks.php` (lines 39–78) and confirmed to be **defined there**, not
invented. `hooks.php` itself was **not modified** — it is on the bootstrap path of
every FA page, so touching it risks taking the whole site down.

| Page | `$page_security` | Defined in `install_access()` as |
|---|---|---|
| `pages/leave.php` | `SA_HRM_LEAVE` | `SS_ksf_FA_HRM \| 7`, "Leave Management" |
| `pages/payroll.php` | `SA_HRM_PAYROLL` | `SS_ksf_FA_HRM \| 5`, "Payroll" |
| `pages/recruitment.php` | `SA_HRM_RECRUITMENT` | `SS_ksf_FA_HRM \| 8`, "Recruitment" |
| `pages/reports.php` | `SA_ksf_FA_HRMVIEW` | `SS_ksf_FA_HRM \| 1`, "View HRM" |

Two notes:

- The four areas **match exactly** the areas `HrmAppShell::registerCoreTabs()` already
  declares for the same four tabs, so the direct-URL route and the app-shell route
  enforce identical access. There is no page that is *more* or *less* protected
  depending on how it was reached.
- `reports.php` deliberately uses the module-wide read-only area
  (`SA_ksf_FA_HRMVIEW`) rather than the narrower per-function areas, because the
  reports expose company-wide headcount and pay aggregates.

---

## 4. What each page does now

### `pages/leave.php` — leave balances (employee / leave type / year)

- **Filter:** employee, leave type, leave year.
- **List:** leave balances — employee, type, year, allocated, carried over, used, balance.
- **Form:** allocate a balance, or adjust an existing one. Submitting against an
  existing `(person, type, year)` **adds** to the stored allocation rather than
  creating a second row.
- Delete is refused once `used_days > 0`, because the append-only day book
  (`0_hrm_leave_request_days`) references approved leave and deleting the allocation
  would orphan that audit trail.

### `pages/payroll.php` — payroll run headers

- **Filter:** employee, status, pay-period overlap window.
- **List:** payroll runs — employee, period start/end, pay date, gross, deductions,
  net, status, GL-posted flag.
- **Form:** create or edit a payroll run.
- **Net pay is recomputed server-side** as `gross − deductions`; the value in the
  form is a display preview only and is never what gets stored.

### `pages/recruitment.php` — structure only, no data model

Rendered with the full filter → list → form structure, but the candidate list is
empty because **ksf_FA_HRM ships no vacancy / candidate / application tables**.
See §6.

### `pages/reports.php` — five real aggregates

Filter (report, year, department) then one summary table. All read-only:

1. Employee Headcount
2. Department Summary
3. Payroll Summary (per-employee totals + grand-total row)
4. Benefits Summary (catalogue + enrolment counts)
5. Leave Balance Report (per-employee allocation for the year)

---

## 5. Business-logic and data-model problems found and fixed

These were found while rebuilding; most pre-date this work.

### 5.1 `leave.php` queried a table and columns that do not exist — **fixed**

The old page read `TB_PREF."leave_balances"` selecting `entitlement`, `used` and
`balance`. The real table is `0_hrm_leave_balances`, and its columns are
`allocated_days`, `used_days`, `carried_over` (`balance` is a *computed* expression,
not a column). Verified against `information_schema`. The page now goes through
`LeaveBalanceRepository::listBalances()`, which computes
`allocated + carried_over − used_days` correctly.

### 5.2 `upsertBalance()` could not execute at all — **fixed (pre-existing)**

FA's `db_escape()` returns a **pre-quoted** SQL literal (`'value'`, and `''` for
empty) — it is not `mysqli_real_escape_string`. `LeaveBalanceRepository` and
`LeaveRequestRepository` wrapped its result in a *second* pair of quotes:

```php
"updated_at = '" . $this->escape(date('Y-m-d H:i:s')) . "'"
```

producing `updated_at = ''2026-10-12 06:08:55''`, which is a SQL syntax error.
`upsertBalance()` therefore **always** threw — the leave page could not save
anything. Confirmed empirically before fixing. Same pattern existed in
`LeaveRequestRepository::updateState()`, `listForPerson()`, `listApprovedInRange()`
and `insertDay()`, which are on the leave-request workflow path. Fixed in both files.

### 5.3 `0_leave_types` does not exist — **made resilient, not created**

`0_leave_types` is documented in this module's own `sql/ksf_hrm_leave_requests.sql`
header as **ksf_FA_Leave's** master. ksf_FA_Leave is not part of this deployment and
no module's `sql/` creates the table. Four read paths `LEFT JOIN` it —
`LookupRepository::getLeaveTypes()` and `LeaveBalanceRepository::listBalances()`.
MariaDB rejects a query naming a missing table **even inside a LEFT JOIN**, so these
failed on every call.

I did **not** create the table (it is another module's master, and inventing it
would fork the model). Instead `FatRepositoryTrait::tableExists()` probes
`information_schema` once per instance and the join is emitted only when the table is
present; the balance page falls back to the numeric type id. As a side effect the
**Leave Types tab stops erroring** too.

### 5.4 `PayrollService` referenced an unimported class — **fixed (pre-existing)**

`PayrollService::personOptions()` instantiated `LookupRepository` but only
`PayrollRepository` was imported, so the name resolved to
`HRM\Service\LookupRepository`, which does not exist — a fatal on first call.
Added the `use` statement.

### 5.5 `date_row()` silently corrupts optional date filters — **fixed**

FA's `date_cells()` writes **today's date** into any date field that arrives empty.
Using `date_row()` for an *optional* filter therefore turns "no filter" into
"filtered to today" and hides the rest of the data. Filter dates are `text_row()`
now, and `FatRepositoryTrait::dateVal()` rejects anything that is not `Y-m-d` before
it is inlined, so malformed input is ignored rather than narrowing or breaking the
query.

### 5.6 `index.php` never included `includes/ui.inc` — **fixed**

FA's bootstrap loads only `ui_view.inc`, `ui_controls.inc` and `ui_msgs.inc`.
**Nothing** loads `ui_input.inc` or `ui_lists.inc` — each FA page must include
`ui.inc` itself. `ksf_FA_CRM/index.php` does exactly this, with a comment saying
so; `ksf_FA_HRM/index.php` did not.

Consequently, in the app-shell flow, every helper these pages use —
`text_row()`, `amount_row()`, `date_row()`, `array_selector_row()`, `submit_row()`,
`submit_center()`, `label_row()`, `hidden()`, `edit_button_cell()`,
`delete_button_cell()`, `submit_js_confirm()`, `submit_add_or_update_row()` — would
be **an undefined function**. This is latent for the eight existing
`AbstractTabController` tabs as well, not just these four pages.

Fixed in both places: `index.php` now includes `ui.inc` (matching CRM), and each
page includes it unconditionally so it is self-sufficient regardless of who
includes it. Verified that all 39 FA helpers the pages call resolve after the
bootstrap + `ui.inc`.

### 5.7 Pages are dual-use, and that needed handling — **fixed**

`HrmAppShell` registers these four tabs **with page scripts**, and
`AbstractAppShell::dispatch()` does `include $pageFile`. So each page is reachable
both directly *and* as an include inside an already-rendered document. Adding
`session.inc` + `page()` + `end_page()` blindly would have nested a second HTML
document inside the shell's.

`index.php` now defines `HRM_APP_SHELL_DISPATCH` immediately before `dispatch()`.
Each page checks it: when set, the page skips its own bootstrap and `page()` /
`end_page()` and renders only its body. When reached directly it bootstraps fully.
Both paths were exercised.

---

## 6. What could NOT be fixed, and why

### Recruitment has no data model

`recruitment.php` renders the complete filter → list → form structure and a real,
enforced security area (`SA_HRM_RECRUITMENT`), but the candidate list is empty and
the Add Candidate button cannot store anything, because **ksf_FA_HRM ships no
vacancy, candidate or application tables**. Its own `sql/` creates 26 tables and none
of them is recruitment-related.

The page says so in plain language on screen rather than presenting an empty form as
if it worked. Implementing it means a **schema decision** — new `0_hrm_vacancies` /
`0_hrm_candidates` / `0_hrm_applications` tables, or reuse of an external ATS — which
is beyond a page rebuild. The page is structured so that only the three
`HrmRecruitmentService` calls need real bodies when that decision is made.

### Leave *requests* are not on the leave page

`pages/leave.php` manages **balances**. The request workflow (`LeaveService::submit()`
/ `approve()` / `reject()`) is a separate `BR-COM-02` `StateMachine` driven through
`LeaveWorkflowFactory` with an approver chain and notifiers. Wiring that into the page
is a workflow feature, not a rendering fix, so I left it alone — but note the page's
on-screen text points at it as the mechanism that actually consumes balance.

### Not authenticated end-to-end in a browser

No FA account password was available in this environment, so the pages could not be
driven through a real login. Instead every page body was executed directly against the
live database with FA's exact helper signatures (see §7). That exercises all the SQL,
all the POST handlers, all validation branches and all filter branches — but it does
not cover the browser's rendering of the emitted markup, nor the `simple_page_mode()`
button-name round trip through a real POST.

---

## 7. Verification performed

- **`php -l`** on every changed file, on the host (PHP 8.1) **and inside the
  container (PHP 7.4.33)** — all clean.
- **PHP 8 syntax scan** over all changed files for `match(`, `?->`, `readonly`,
  union return types `: X|Y`, `#[Attr]`, `fn() =>`. Only hits were `preg_match`.
- **HTTP sweep** — all four pages standalone, all four via `?view=`, the other HRM
  tabs, the site root and the FA index all return **200**; site root 200 throughout.
  CRM checked as a regression control (see §8).
- **Full behavioural test against the live database.** Every page was executed with
  representative request state, covering:
  - leave: unfiltered list, filter by year, filter matching nothing, create,
    adjust-existing (idempotent add), delete, delete-refused-when-used,
    delete-of-missing-row, and all four validation failures
  - payroll: unfiltered list, filter by status, filter by date window, malformed
    date filter, create, edit, delete, and all four validation failures
  - reports: all five report keys, the unknown-key fallback, and the totals
    arithmetic (gross 8,000.00 / deductions 1,950.00 / net 6,050.00)
  - Test rows were removed afterwards; the three HRM tables are back to 0 rows.
- **Unit tests: 252 pass, 673 assertions, 0 failures** (was 251 with 1 failure after
  the `tableExists()` guard; the stub now models the `information_schema` probe and
  one test was added for the absent-catalogue branch).
- **`git status --porcelain`** on the deployed module is shown in §8.
- `hooks.php` untouched in both repos, confirmed with `git status --porcelain hooks.php`.

---

## 8. Changed files

```
 M index.php
 M pages/leave.php
 M pages/payroll.php
 M pages/recruitment.php
 M pages/reports.php
 M src/Repository/FatRepositoryTrait.php
 M src/Repository/LeaveBalanceRepository.php
 M src/Repository/LeaveRequestRepository.php
 M src/Repository/LookupRepository.php
 M src/Repository/PayrollRepository.php
 M src/Service/DepartmentService.php
 M src/Service/PayrollService.php
?? src/Service/HrmReportService.php      (new)
?? src/Service/LeaveBalanceService.php   (new)
```

Plus, in the dev repo only: `tests/stubs.php`, `tests/Unit/LookupRepositoryTest.php`.
`AGENTS_ARCH.md` and `APP_TAB_ARCHITECTURE.md` were already modified before this work
began and were deliberately left unstaged.

Dev and deployed trees are byte-identical for every changed file.

---

## 9. Issues found but deliberately NOT changed

1. **`ksf_FA_CRM/index.php` returns HTTP 500** — `Class CrmAppShell not found`.
   CRM's `vendor/composer/autoload_psr4.php` maps the **old** namespace
   `Ksfraser\FA\CRM\`, while the source has been renamed to
   `ksfraser\FrontAccounting\CRM\`. The generated autoloader is stale and needs
   `composer dump-autoload` in that module. Pre-existing, unrelated to this work,
   CRM's git tree is clean.
2. **`access/login.php` returns HTTP 500** — `Call to undefined function _()`.
   Pre-existing; that script is not a valid direct entry point. `index.php` is the
   working login page.
3. **Remaining `$this->escape()` double-quoting elsewhere.** §5.2 fixed it in
   `LeaveBalanceRepository` and `LeaveRequestRepository`, the files on this page's
   code path. A survey of `src/Repository/` found no other instances — the other
   repositories correctly inline `escape()` without adding quotes.
4. **`0_leave_types` has no owner in this deployment** (§5.3). It needs either
   ksf_FA_Leave installed or a decision to move the master into HRM. Until then the
   Leave Types tab has nothing to show.
5. **`0_crm_persons` has a UNIQUE `ref` column** but HRM employees are joined from
   it; `LookupRepository::personOptions()` filters `inactive = 0` while
   `getCrmPersons()` does not. Both are used by different callers. Left as-is; worth
   a decision on whether HRM headcount should follow `crm_persons.inactive` at all,
   or a dedicated HRM employment flag.