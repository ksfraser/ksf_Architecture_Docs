# HRM Controller Consolidation

**Module:** `ksf_FA_HRM`
**Date:** 2026-10-12
**Repo:** `/home/kevin/Documents/ksf_FA_HRM` (branch `main`)
**Deployed to:** `/home/kevin/Documents/ksf_Infrastructure/fa_modules/ksf_FA_HRM` (bind-mounted, edits are live)
**Verified against:** `ksfii_app-fa` on `http://localhost:8090`, PHP 7.4.33, FA 2.4.3

---

## 1. What was consolidated

Four standalone procedural page scripts under `pages/` — `leave.php`,
`payroll.php`, `recruitment.php`, `reports.php` — were consolidated behind a
single front controller at the module root, `hrm.php`, wired through the
extension machinery that already existed in the shared `ksfraser/ksf-fa-common`
package (`AbstractAppShell`, `AbstractTabController`, `TabRegistration`).

No new framework was invented. `HrmAppShell` already declared all twelve tabs
with real security areas and controller classes; the four page-backed tabs were
the only ones still carrying a `pageFile`.

### Files added

| File | Role |
|------|------|
| `hrm.php` | The single front controller. `page=` (read) / `action=` (mutation) dispatch. |
| `src/Controller/TabActionRouting.php` | Trait: the shared `action=` vocabulary (`save` / `delete` / `edit`). |
| `src/Controller/FilteredTabController.php` | Adds the filter bar to `AbstractTabController`; renders the entry form with FA's own row helpers rather than Bootstrap. |
| `src/Controller/LeaveTabController.php` | Replaces `pages/leave.php`. |
| `src/Controller/PayrollTabController.php` | Replaces `pages/payroll.php`. |
| `src/Controller/RecruitmentTabController.php` | Replaces `pages/recruitment.php`. |
| `src/Controller/ReportsTabController.php` | Replaces `pages/reports.php`. |

### Files changed

| File | Change |
|------|--------|
| `src/App/HrmAppShell.php` | All twelve tabs registered with `registerTabFromArray()`; no `page_file` left; `createController()` overridden to inject the tab key; menu now renders `?page=`. |
| `index.php` | Reduced to a forwarder onto `hrm.php`. |
| `pages/{leave,payroll,recruitment,reports}.php` | Reduced to forwarder shims. |
| `src/Controller/{Benefits,Departments,Employees,Grades,LeaveTypes,Positions,Roles,Teams}TabController.php` | One line each: `use TabActionRouting;` so `action=` works app-wide. |
| `README.md` | Added the routing section and the "Adding an HRM tab from another module" guide. |

`hooks.php` was **not** modified — verified byte-identical to `HEAD`
(`md5 0560b0b0a95db767c4d783132311c3fb`) before and after the work.

---

## 2. Before / after URL map

### Before

| URL | Served by |
|-----|-----------|
| `modules/ksf_FA_HRM/index.php?view=employees` | `index.php` → `HrmAppShell::dispatch()` → `EmployeesTabController::run()` |
| `modules/ksf_FA_HRM/index.php?view=payroll` | `index.php` → `dispatch()` → `include pages/payroll.php` |
| `modules/ksf_FA_HRM/index.php?view=leave` | `index.php` → `dispatch()` → `include pages/leave.php` |
| `modules/ksf_FA_HRM/index.php?view=recruitment` | `index.php` → `dispatch()` → `include pages/recruitment.php` |
| `modules/ksf_FA_HRM/index.php?view=reports` | `index.php` → `dispatch()` → `include pages/reports.php` |
| `modules/ksf_FA_HRM/pages/payroll.php` | Standalone WebERP-style page: own `session.inc`, own `page()`, own `end_page()`, own POST routing via `simple_page_mode()` |
| `modules/ksf_FA_HRM/pages/leave.php` | as above |
| `modules/ksf_FA_HRM/pages/recruitment.php` | as above |
| `modules/ksf_FA_HRM/pages/reports.php` | as above |
| *(no URL-addressable mutation route)* | mutations were reachable only by submitting a rendered form |

### After

| URL | Served by |
|-----|-----------|
| `modules/ksf_FA_HRM/hrm.php?page=<tab>` | `hrm.php` → `HrmAppShell::dispatch()` → `<Tab>TabController::run()` |
| `modules/ksf_FA_HRM/hrm.php?page=<tab>&filter_<x>=…` | same, with filters applied |
| `modules/ksf_FA_HRM/hrm.php?page=<tab>&action=edit&id=N` | `TabActionRouting::runAction('edit')` → 302 onto the tab with the pk set |
| `modules/ksf_FA_HRM/hrm.php?page=<tab>&action=save` | `runAction('save')` → service → PRG redirect (**POST only**) |
| `modules/ksf_FA_HRM/hrm.php?page=<tab>&action=delete&id=N` | `runAction('delete')` → service → PRG redirect (**POST only**) |
| `modules/ksf_FA_HRM/hrm.php?page=<n>&view=<tab>` | pager link; `page` numeric = pager position, `view` = tab |
| `modules/ksf_FA_HRM/hrm.php` | default tab (`employees`) |
| `modules/ksf_FA_HRM/index.php` | forwarder → `hrm.php` |
| `modules/ksf_FA_HRM/index.php?view=<tab>` | forwarder, maps `view` → `page` |
| `modules/ksf_FA_HRM/pages/<tab>.php` | forwarder shim → `hrm.php?page=<tab>` |

All twelve tabs are now served by exactly one code path. Every old URL still
resolves and renders the same content.

---

## 3. The `page` / `action` contract

### `page` — the read selector

`page` is what the user types and what the menu renders. It is **also** what
`AbstractTabController::page()` reads for pager paging, and what
`MasterSummaryTable::pagerUrl()` writes into its pager links (`?page=<n>`).
The two collide, so `hrm.php::hrm_resolve_view()` resolves by rule:

1. a `page` value that names a **registered tab key** is the tab;
2. anything else (a number) is the **pager position**, and the tab comes from
   `view`;
3. neither → the shell's default view, never an error — a stale bookmark lands
   on a working tab.

Because the shared pager emits `?page=<n>` and re-reads `$_GET['view']` for
`preserveParams()`, pager links come out as `?page=<n>&view=<tab>` and resolve
correctly through the same rule. `hrm.php` normalises the resolved tab back
into `$_GET['view']` before dispatch so `preserveParams()` has something to
carry.

### `action` — the mutation selector

`hrm.php` reads `action=` from `$_REQUEST` and hands it to the resolved tab's
controller as `runAction($verb)`. The vocabulary is uniform across all twelve
tabs (implemented once in the `TabActionRouting` trait, used by the four
filtered tabs via `FilteredTabController` and added to the eight catalogue
controllers with one line each):

| Verb | Method | Notes |
|------|--------|-------|
| `save` | POST | `createRecord()` when no pk is set, else `updateRecord()`. |
| `delete` | POST | `deleteRecord()`. **POST-only by design.** |
| `edit` | GET | 302 back onto the tab with the pk set, pre-loading the entry form. |

`action=delete` is POST-only on purpose. A GET-addressable delete is a
cross-site request forgery: any third-party page could issue
`<img src="…/hrm.php?page=payroll&action=delete&id=7">` and the record would be
gone. The summary table's own Delete buttons are POST submit buttons, so they
remain the only reachable delete path.

Both routes coexist: `hrm.php?page=x&action=save` and the legacy
`<pk>_submit` form POST both end in the same `createRecord()`/`updateRecord()`
calls, so there is one write path, not two.

### `$path_to_root` depth

`hrm.php` sits at the **module root**, two levels below the FA root, so
`$path_to_root = '../..'`. That is the whole reason the consolidation works
cleanly where the old scripts did not: `pages/*.php` is three levels down and
PHP resolves a relative `include` against the **main script's** directory, so
those files needed `chdir()` gymnastics before they could forward. The shims
now do that explicitly:

```php
// hrm.php bootstraps FA with $path_to_root = '../..', which PHP resolves
// against the MAIN script's directory. This shim is the main script and lives
// one level deeper (pages/), so move to the module root first.
chdir(__DIR__ . '/..');
require __DIR__ . '/../hrm.php';
```

---

## 4. How the appId / hook name works

`HrmAppShell`'s first constructor argument is the **app id**, and
`AbstractAppShell::getRegisterHook()` derives the hook name from it:

```php
public function __construct(string $defaultView = 'employees')
{
    parent::__construct('hrm', 'hrm.php', 'page', $defaultView);
    //  ^appId  ^baseUrl ^viewParam ^defaultView
}

// inherited from AbstractAppShell:
public function getRegisterHook(): string
{
    return $this->appId . '_register_tabs';   // => "hrm_register_tabs"
}
```

`boot()` fires it:

```php
$data = ['tabs' => []];
hook_invoke_all($this->getRegisterHook(), $data);   // hook_invoke_all('hrm_register_tabs', $data)
foreach ($data['tabs'] as $def) {
    $this->registerTab($def instanceof TabRegistration ? $def : TabRegistration::fromArray($def));
}
```

**So the hook name is `hrm_register_tabs`.** Verified live: a temporary
`hrm_register_tabs(&$data)` responder added to the deployed `hooks.php` made
its tab appear in the HRM menu (13 items instead of 12) and made
`hrm.php?page=probe_tab` resolve to it. The probe was then removed and
`hooks.php` restored byte-identical to `HEAD`.

### Lifecycle ordering, and why it matters

1. `hrm.php` constructs `HrmAppShell`. The twelve **core** tabs are registered
   in the constructor — deliberately, because `$page_security` must be resolved
   **before** `session.inc`, and firing a hook needs a session. Core tabs
   therefore have their real per-tab security area checked pre-session.
2. `include session.inc` + `add_access_extensions()`.
3. `$appShell->boot()` fires `hrm_register_tabs`; responders' tabs are merged
   into the menu and dispatch, carrying their **own** security area.
4. `hrm.php` re-resolves the view, so a tab that only appeared at step 3 is
   still reachable by a direct `?page=` URL. This cannot widen access:
   `dispatch()` re-checks the tab's real security area *after* `boot()`.
5. `page()` → `renderMenu()` → `dispatch($view)` → the controller's `run()`.

### What another module must implement

Exactly one method on its FA hooks class. Full worked example in
`ksf_FA_HRM/README.md` § "Adding an HRM tab from another module".

```php
class hooks_ksf_FA_Timesheets extends hooks
{
    var $module_name = 'ksf_FA_Timesheets';
    var $version     = '2.4.3-1';

    public function hrm_register_tabs(&$data, $opts = null)
    {
        $data['tabs'][] = array(
            'key'              => 'timesheets',      // hrm.php?page=timesheets
            'label'            => _('Timesheets'),
            'security'         => 'SA_TIMESHEETS',  // your install_access() area
            'controller_class' => \Vendor\Hrm\TimesheetsTabController::class,
            'priority'         => 40,                // lower = earlier
            'order'            => 0,
        );
    }
}
```

Required of the contributor:

- `key` unique across the app (it is the `?page=` value);
- `label` already translated;
- `security` an FA security area from the contributing module's
  `install_access()`;
- **either** `controller_class` (FQCN of an `AbstractTabController` or
  `FilteredTabController` subclass) **or** `page_file` (absolute path to a
  fragment included inside the shell's already-open `page()`/`end_page()` —
  it must **not** call `page()`/`end_page()` itself and must **not** redefine
  `$path_to_root`).

A `TabRegistration` instance may be pushed instead of an array, or
`ksfraser\FrontAccounting\Common\Traits\TabRegistrationTrait::respondToAppRegister()`
may be used, which additionally records the registration in the generic
`ExtensionRegistry` under `hrm_tabs`.

---

## 5. Architectural decisions worth recording

**A `FilteredTabController` intermediate, not a change to the shared base.**
`AbstractTabController` has no slot for a filter bar and its default entry form
delegates to `FieldForm`, which emits Bootstrap grid markup. The consolidated
tabs must keep the FA-native filter / summary-table / data-entry-form layout
they had as standalone pages. Rather than fork the shared package, HRM adds one
subclass that inserts the filter section and re-renders the control grid with
FA's `ui_input.inc` row helpers. The shared package is untouched and still the
contract for all twelve tabs.

**`action=` implemented as a trait, not as controller logic.** `createRecord()`
and friends are `protected`, so `hrm.php` cannot reach them. The trait supplies
`runAction()` once and is `use`d by all twelve controllers, so the vocabulary is
identical everywhere and there is a single write path.

**Refusals re-render instead of redirecting.** When a service rejects a payload
(validation error, a leave balance that cannot be released), the controller sets
`skipRedirect`; `finishAction()` then re-renders the tab rather than
PRG-redirecting away from the message. The rejected POST values are re-injected
into the entry form so the user corrects rather than retypes. Payroll overrides
the hook to re-derive net pay, otherwise a refused save would show a net figure
different from the one that was refused.

**The PRG target is built from `$_GET`, not `REQUEST_URI`.** FA html-escapes
`$_SERVER['REQUEST_URI']` somewhere on the POST path, which turned
`?a=1&b=2` into `?a=1&amp;b=2` in the `Location` header — a broken target that
silently dropped the rest of the query string. `hrmActionUrl()` builds from
`PHP_SELF` + `$_GET` via `http_build_query()` instead, and strips `action`, `id`
and `view` so the redirected GET cannot replay the mutation.

**Leave allocation stays additive, but an edit no longer compounds.**
`LeaveBalanceService::allocate()` adds to the stored figure by design (that is
how accrual works). The old `pages/leave.php` called it for both ADD and
UPDATE, so editing a balance and saving doubled the days. `updateRecord()`
now passes the *difference* against the stored allocation, so an edit replaces
rather than compounds, and the form headings read "Allocate Leave" /
"Adjust Leave Balance" to match.

**Recruitment refuses mutations explicitly.** The module ships no
vacancy/candidate/application table. The tab renders its full filter /
summary / entry-form structure and refuses every write with an explicit
message, instead of silently accepting an entry that is not stored.

---

## 6. Verification performed

Everything below was run against the live container, authenticated as a real
FA user (an anonymous request returning FA's login page with HTTP 200 is the
healthy signal for a protected page).

| Check | Result |
|-------|--------|
| `php -l` on all 12 changed/added files (host PHP) | clean |
| `php -l` inside `ksfii_app-fa` | clean |
| `php -l` on deployed `hooks.php` | clean, and **unmodified** (`md5` matches `HEAD`) |
| `vendor/bin/phpunit` | **OK (252 tests, 673 assertions)** |
| All twelve tabs render (`?page=<tab>`, logged in) | 12/12 HTTP 200, complete footer, no fatal |
| Layout preserved on the four consolidated tabs | filter section + summary table + entry form present; reports keeps its notes block |
| Old `pages/*.php` URLs (4) | HTTP 200, full content rendered |
| `index.php`, `index.php?view=payroll` | HTTP 200, full content rendered |
| `hrm.php`, `hrm.php?page=<tab>` (12) | HTTP 200 |
| `?page=2&view=departments` (pager link shape) | resolves to the departments tab |
| `?page=99` (bogus numeric) | falls back to `employees`, HTTP 200 |
| `action=edit&id=N` (GET) | 302 → `hrm.php?page=departments&department_id=3` |
| `action=save` (POST, valid) | 302 → `hrm.php?page=payroll&filter_status=Draft`; record created |
| `action=delete&id=N` (POST) | 302; record removed |
| `action=delete&id=N` (**GET**) | **refused**: "Delete must be submitted as a POST"; tab re-rendered |
| `action=save` (POST, invalid) | "Employee is required."; entry form re-rendered with the rejected values |
| Legacy `<pk>_submit` / `delete_<pk>` POST route | still works (soft-deactivate for departments, as designed) |
| `hrm_register_tabs` hook | temporary responder's tab appeared in the menu and resolved by URL; probe removed, `hooks.php` restored byte-identical |
| Site root `http://localhost:8090/` | HTTP 200 |

Test records created during verification (departments `ZZ1`/`ZZ2`, one payroll
run) were removed afterwards; `0_hrm_departments` and `0_hrm_payroll` are back
to empty.

---

## 7. Known limitations / deferred

1. **`page=` is overloaded.** A URL reader cannot tell `?page=leave` (a tab)
   from `?page=2` (a pager position) without knowing the tab list. The rule is
   documented and deterministic, but a second parameter name (`tab=`) would be
   cleaner. It cannot be done without changing the vendored shared package
   (`MasterSummaryTable::pagerUrl()` hardcodes `page=`), which is a separate
   repo with its own release cycle.

2. **Pager links carry both `page` and `view`.**
   `?page=<n>&view=<tab>` is slightly noisy. `view` is required because
   `MasterSummaryTable` hardcodes the pager parameter.

3. **`action=` verbs are only `save` / `delete` / `edit`.** There is no `filter`
   verb — the Filter button is a POST named `filter_submit` and the tab
   re-renders in place. That is deliberate: filtering is a read, and routing it
   through `action=` would have meant a second path for the same thing.

4. **Recruitment remains a placeholder.** It needs `0_hrm_vacancies`,
   `0_hrm_candidates` and an `HrmRecruitmentService` before it can store
   anything. The tab refuses writes explicitly rather than pretending.

5. **No `pageFile` fallback tab was exercised.** Every HRM tab is
   controller-backed, so the `AbstractAppShell::dispatch()` branch that
   `include`s a legacy fragment is now unused here. It remains the documented
   option for a third-party contributor that cannot ship a controller.

6. **Shims are one release old.** `index.php` and `pages/*.php` are documented
   as `@deprecated 1.1.0` and should be removed in the next major version.

7. **`hooks.php` still hardcodes the sidebar menu** (`modules/ksf_FA_HRM/index.php`
   + a `view` list) rather than deriving it from `HrmAppShell`. It was
   deliberately left untouched — it loads during FA bootstrap, so a mistake
   there breaks every page in the application — and `index.php` still forwards
   correctly, so those links keep working. Deriving the sidebar from the shell
   would remove the last hardcoded tab list and is worth doing as a separate,
   carefully-reviewed change.
---

## 8. Tab selector renamed `page` -> `tab` (resolves §7 items 1 and 2)

§7.1 and §7.2 recorded `?page=` as overloaded and blamed the vendored shared
package. Both are now closed. `page` means pagination and nothing else; the tab
selector is `tab`.

### Old -> new URL map

| Before (worked) | After (works) | Note |
|---|---|---|
| `hrm.php?page=leave` | `hrm.php?tab=leave` | |
| `hrm.php?page=payroll` | `hrm.php?tab=payroll` | |
| `hrm.php?page=leave&filter_year=2026` | `hrm.php?tab=leave&filter_year=2026` | filters untouched |
| `hrm.php?page=leave&page=3` | `hrm.php?tab=leave&page=3` | the old form was unreadable; this is the point of the rename |
| `hrm.php?page=payroll&action=edit&id=7` | `hrm.php?tab=payroll&action=edit&id=7` | |
| `hrm.php?page=payroll&action=save` | `hrm.php?tab=payroll&action=save` | POST only, unchanged |
| `hrm.php?page=payroll&action=delete&id=7` | `hrm.php?tab=payroll&action=delete&id=7` | POST only, unchanged |
| `hrm.php?page=3&view=leave` | `hrm.php?page=3&tab=leave` | the old pager-link shape |
| `hrm.php?view=employees` | `hrm.php?tab=employees` | **kept working** — deprecated alias, see below |
| `index.php?view=employees` | `index.php?tab=employees` | **kept working** — `index.php` rewrites `view` -> `tab` |
| `pages/leave.php` | `pages/leave.php` | **kept working** — shim now sets `$_GET['tab']` |
| `hrm.php?page=leave` (tab read) | `hrm.php` (default tab `employees`) | **clean break** — see below |

### Why the heuristic is gone

The old controller decided by rule: "a `page` that names a registered tab key IS
the tab; anything else is a pager position, and the tab then comes from `view`."
That rule is deterministic but it is a guess about intent. A future tab whose key
happened to look numeric would have been silently routed to a pager position
instead. With `tab` and `page` separated there is nothing left to infer: `tab` is
read for the tab, `page` is read by `AbstractTabController::page()` for the pager
position, and the two never meet.

`HrmAppShell` now passes `'tab'` as `AbstractAppShell`'s `viewParam` (it used to
pass `'page'`), so `renderMenu()` emits `hrm.php?tab=<key>` for every tab without
any HRM-specific link building.

### Pager links carry the tab — WITHOUT touching the shared package

§7.1 assumed this needed a shared-package change. It does not.
`MasterSummaryTable` already has the hook: its `preserve_params` constructor
option takes a list of `$_GET` key names and `pagerUrl()` copies each one
verbatim onto the links it builds (`MasterSummaryTable.php:154`, `:657`). The
mechanism was simply being pointed at the wrong key.

So the fix is entirely HRM-side:

1. `src/Controller/TabActionRouting::preserveParams()` returns `['tab']`
   (was `['view']`). Every HRM controller inherits this via the trait.
2. `hrm.php` normalises the resolved tab back into `$_GET['tab']` before
   dispatch, so the preserved value is the *resolved* tab — which also covers a
   tab contributed by another module through `hrm_register_tabs` after `boot()`,
   and normalises an arrival on the deprecated `?view=` alias.
3. `$_GET['page']` is deliberately left untouched. It is the pager position and
   must survive verbatim into pager links, `TabActionRouting::hrmActionUrl()`
   redirect URLs, and `formAction()`.

Generated pager URL: `?page=<n>&tab=<key>`.

**`vendor/ksfraser/ksf-fa-common` was NOT modified.** It is byte-identical to
what composer installed (`diff -rq` against the deployed tree is empty). If a
future change does need `MasterSummaryTable` to know about the tab, the correct
route is a new release of `ksf-fa-common` plus `composer update`, not a vendor
edit — see `AGENTS_ARCH.md` §7 on the package/consumer split.

### Backward compatibility policy

- **`?view=<tab>` — KEPT, one release.** `index.php` used `?view=` long before
  `hrm.php` existed, so those bookmarks predate the consolidation and may be
  real. `hrm.php` reads `view` only when `tab` is absent, and rewrites it onto
  `tab` on arrival, so it is normalised away and never propagated.
  `index.php` rewrites `?view=` -> `?tab=` before requiring `hrm.php`.
- **`?page=<tab>` — NOT KEPT. Clean break, documented.** It was published for
  minutes and nothing depends on it. Keeping it would mean keeping the exact
  ambiguity this change removes, and the heuristic that came with it. Such a URL
  now lands on the default tab at page 1. That degrades safely rather than
  erroring: every read of the pager position clamps with `max(1, ...)`, so a
  non-numeric `page` becomes 0 and is clamped to 1.

### `AbstractTabController` audit (task 4)

`src/App/AbstractTabController.php` in the shared package reads `$_GET` exactly
once for paging:

- **line 557** — `page()`: `return (int) ($_GET['page'] ?? 1);`

That is the pager position and is *correct* under the new scheme; it is the
reason `page` had to stop meaning "tab". It is backed by
`HTML/TabContext::fromPost()` (line 63-64) which also casts `page` to `(int)` for
the POST round-trip — same meaning, consistent.

`AbstractTabController::preserveParams()` (line 577) returns `['view']` as a
**default**, which the HRM controllers override to `['tab']`. Nothing in the
package assumes `page` is a tab selector, and no vendor change was required for
any of this.

### Verification performed

- `php -l` on every changed file, on the host (PHP 8.1) and inside the
  `ksfii_app-fa` container (PHP 7.4.33).
- HTTP 200 on `hrm.php?tab=leave`, `?tab=payroll`, `?tab=employees`,
  `?tab=leave&page=3`, `pages/leave.php`, `pages/payroll.php`,
  `index.php?view=leave`, `index.php?tab=leave`, `hrm.php` bare and the site
  root. (`?page=leave` also returns 200 — it degrades to the default tab.)
- A harness run **inside the container against the deployed files** exercised the
  real `hrm_resolve_view()`, the real `HrmAppShell`, the real
  `MasterSummaryTable::pagerUrl()` and the real `preserveParams()`:
  11 resolution cases, pager-URL generation, pager-link round-trip, the menu's
  emitted links, and the `preserveParams()` value. All passed.
- `hooks.php` was not touched: `git diff HEAD -- hooks.php` is empty. It still
  hardcodes the sidebar link to `modules/ksf_FA_HRM/index.php` with a `view`
  list, and `index.php` still forwards correctly, so those links keep working.

---

## 2026-10-13 — HRM adopts `AbstractFrontController` (ksf-fa-common v1.0.13)

**Commit:** `18fcba5` on `ksf_FA_HRM` main (pushed). Deployed to
`ksf_Infrastructure/fa_modules/ksf_FA_HRM`, live on `ksfii_app-fa` (PHP 7.4.33).

`hrm.php` no longer owns its preamble. `ksfraser\FrontAccounting\Common\App\AbstractFrontController`
(package `ksfraser/ksf-fa-common` v1.0.13) now owns the whole request sequence:
resolve the tab, resolve the security area, `boot()` the shell so
`hrm_register_tabs` can contribute, re-resolve, normalise `$_GET`, render the
page and menu, **enforce access once** ahead of both dispatch paths, dispatch,
close.

### Size

`hrm.php`: **251 → 92 lines**, of which 20 are executable. The rest is the
docblock, which grew rather than shrank — it now records why the two-phase split
exists and why `includes/ui.inc` stayed at global scope.

`src/App/HrmFrontController.php` (new, 77 lines) is pure declaration:
`getPageTitle()` returns `_("HRM")`, `getPageJs()` returns the date-picker
bundle for `payroll` and `leave` only. Nothing else.

### The published `loadUiIncludes()` does not work — do not rely on it

`AbstractFrontController::loadUiIncludes()` includes `includes/ui.inc` from
inside a method. FA's `includes/ui.inc` reads `$path_to_root` as a **global in
its including scope**, so from method scope every `include_once($path_to_root .
"/includes/ui/...")` inside it resolves to the *filesystem root* and fails
silently. The guard `is_file($this->pathToRoot . '/includes/ui.inc')` passes —
the outer file is found — so nothing looks wrong until a tab renders far enough
to call the first helper that never got defined.

Observed live, twice, in two distinct failure shapes:

| Symptom | Cause |
|---|---|
| Tab renders partway then dies, `FilteredTabController.php:235: Call to undefined function array_selector_row()` | no `ui_input.inc` |
| Every HRM page **500**s, `includes/sysnames.inc:22: Call to undefined function _()` | `ui_lists.inc` loaded *before* `session.inc` |

The second is the trap: hoisting the include above `session.inc` to "get it out
of the way" 500s every HRM page, because `session.inc` is what loads gettext.
The include must sit **after** `session.inc`/`add_access_extensions()` and
**before** `run()`.

**HRM's answer:** `hrm.php` includes `includes/ui.inc` itself at global scope,
in exactly the position the old preamble used, and passes
`['load_ui_includes' => false]`. A comment at the include records why, so the
next reader does not "tidy" it back into the base class.

**Follow-up owed by the package** (NOT done here — publishing a new
`ksf-fa-common` version was out of scope for a module migration):

```php
protected function loadUiIncludes(): void
{
    if (!$this->loadUi || $this->pathToRoot === '') {
        return;
    }
    $file = $this->pathToRoot . '/includes/ui.inc';
    if (!is_file($file)) {
        return;
    }
    $path_to_root = $this->pathToRoot;   // ui.inc needs it in including scope
    include_once $file;
}
```

That is a one-line fix and makes `load_ui_includes` default-true honest again.
Until it ships, **any** module adopting the base class must do the same dance.
Note the design doc's §4 only reasoned about `session.inc` needing globals and
concluded `ui.inc` could move into `run()`; the same constraint applies to it,
and the design doc's verification (unit tests only) could not see it.

### The throw on an empty shell did not fire

`FrontControllerRoutingException` replaces the old silent fallback when the
shell yields no tabs. `HrmAppShell` registers all twelve tabs in its
constructor, and `AbstractAppShell::resolveView()` only returns the empty
`TabRegistration('', '')` when the tab list is empty — so the throw is
unreachable in normal operation. Confirmed three ways: no exception in the
container log across the full probe sweep, all 26 URLs byte-identical to the
pre-migration baseline, and `testTheRealShellCanNeverTripTheThrow` /
`testAShellWithNoTabsThrowsRatherThanRenderingBlank`.

One genuine consequence, now pinned by a test: because `boot()` fires
`hrm_register_tabs`, a shell with **no** core tabs would still be rescued by a
third-party contribution. The throw-on-empty only means "nothing registered at
all, anywhere".

### Verification

- **Byte-for-byte identical** to the pre-migration build across 26 GET routes:
  all 12 tabs, bare `hrm.php`, `?tab=leave&page=3`, `?view=leave`,
  `?view=payroll`, `index.php?view=leave`, `index.php?view=payroll`, the four
  `pages/*.php` forwarder shims, `?tab=bogus`, GET-delete on two tabs, and the
  site root. Captured pre-migration, re-captured post-migration, `diff` empty.
  (An earlier run also re-captured the same set against the **old** `hrm.php`
  temporarily re-deployed, as a control — it matched the baseline too, so the
  comparison harness itself was trustworthy.)
- **POST mutation routes identical old vs new**: `action=delete` on leave and
  payroll → `No record was selected for deletion.`; `action=save` on leave and
  payroll → `Employee is required.` Both 200, no errors. Probe uses a
  non-existent id so nothing is written.
- **GET on a delete is still refused**: `Delete must be submitted as a POST.`
- Site root HTTP 200 throughout, including while two intermediate broken states
  were briefly deployed.
- `php -l` clean on every changed file, host (8.1), container (7.4.33), and the
  module's own `tools/lint-php73.sh` (113 files, PHP 7.3.33).
- `hooks.php` **byte-identical to git HEAD**, 41 methods before and after, and
  identical in the deployed tree. Never opened for edit.
- Unit tests: **OK (284 tests, 741 assertions)** — 252 pre-existing plus 32
  added.

### Deployed vendor

`composer install --no-dev` in `fa_modules/ksf_FA_HRM`:
`ksfraser/exceptions v1.3.0`, `ksfraser/html 2.0.7`,
`ksfraser/ksf-fa-common v1.0.13`. `installed.json` reports `dev: false`.
`vendor/bin/` is empty. A `find -maxdepth 2` for `phpunit`, `sebastian`,
`myclabs`, `nikic`, `phar-io`, `theseer`, `doctrine` returns **nothing**.
`platform_check.php` still only requires `>= 7.3`.

Source was synced dev → deployed with `rsync --delete` excluding `vendor`,
`.git` and the phpunit caches, then installed `--no-dev` separately — so the
deployed vendor can never inherit the dev tree's PHPUnit 10.

### Tests added (`tests/Unit/HrmFrontControllerTest.php`, 32)

Fixture `hook_invoke_all()` double answers `hrm_register_tabs` with a
third-party tab and counts calls. Covers: each of the 12 tabs resolving; tab
list order; `?page=` never being a selector; pager position and clamping; the
`?view=` alias resolving then normalising onto `tab` with `page` surviving
verbatim; `tab` beating `view`; unknown tab falling back; the tab's own area vs
the constructor fallback (including a tab with *no* area); the register hook
delivering a third-party tab that is then resolved, checked against **its own**
area and dispatched; the empty-shell throw and the real shell's inability to
trip it; action resolution incl. array input; declined-verb fall-through;
enforcement ahead of the action path; the unavailable-action message; page
title; `run()`/`enforceSecurity()` finality; the constructor's refusal of an
empty fallback area.

### Caution recorded

The POST probe initially included `?tab=benefits&action=save`, which passed
validation and inserted a junk row into `0_hrm_benefits` (benefit_id 1, empty
code/name). **Deleted**; the table is back to 0 rows, confirmed by
`SELECT COUNT(*)`. The mutation probes should only target routes that refuse.
