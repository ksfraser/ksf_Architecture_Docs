# PM `AbstractFrontController` adoption

**Module:** `ksf_FA_ProjectManagement`
**Repo:** `ksfraser/ksf_FA_ProjectManagement` — the FA module, deployed in place at
`~/Documents/ksf_Infrastructure/fa_modules/ksf_FA_ProjectManagement` (itself a git
checkout; there is no separate dev tree for the module shell).
**Target:** `http://localhost:8090` — container `ksfii_app-fa`, PHP **7.4.33**
**Commit pushed to `origin/main`:** **`f1a0bc7`** (rebased onto `8788ed1`)
**Local deployed checkout:** `4161fd8` — see §7 for why it is not the same SHA.
**Date:** 2026-10-13

> **Repo note.** The brief pointed at `~/Documents/ksf_ProjectManagement`. That is a
> *different* repository (`ksfraser/ksf_ProjectManagement`) holding the standalone
> CPM/Gantt library only — namespace `Ksfraser\ProjectManagement\`, no `index.php`,
> no `hooks.php`, no `src/Ksfraser/FrontAccounting/`. The FA module lives in
> `fa_modules/ksf_FA_ProjectManagement` and has its own repo and remote. All work was
> done there. `~/Documents/ksf_ProjectManagement` was not modified.

---

## 1. Before / after URL status

### 1a. Unauthenticated sweep — 39 URLs, byte-identical

`curl` with no session. FA serves its login form inline (HTTP **200**, not 302), so
200 means *the page bootstrapped and reached `session.inc`*. Both status code **and**
body signature are recorded for every URL.

| URL group | count | before | after |
|---|---|---|---|
| site root `/`, `/index.php`, `/admin/inst_module.php`, `/sales/sales_order_entry.php` | 4 | 200 | 200 |
| `/modules/ksf_FA_HRM/hrm.php`, `?tab=employees` | 2 | 200 | 200 |
| `/modules/ksf_FA_CRM/index.php`, `?view=dashboard` | 2 | 200 | 200 |
| `/modules/ksf_FA_Calendar/index.php` | 1 | **404** | 404 (not an entry point — see §6) |
| PM app shell: `/index.php`, six `?view=` tabs, `?view=bogus_tab`, `?tab=projects`, `?view=&page=2`, `?view=&action=save`, `?page=3` | 12 | 200 | 200 |
| PM legacy `pm.php` (+2 param forms) | 3 | 200 | 200 |
| PM legacy `pages/*.php` (8 files) | 8 | 200 | 200 |
| non-entry-points probed for completeness (`bootstrap.php`, `FA_PM_Module.php`, `includes/pm_ui.inc`, `hooks.php`) | 4 | 200 / 200 / 200 / **500** | identical |

`diff` of the complete before/after sweep (status **and** signature) is **empty**.
`hooks.php` 500 is expected and pre-existing: it is `class hooks_… extends hooks`, and
the base `hooks` class does not exist when the file is requested directly.

### 1b. Authenticated sweep — every tab *renders*, proved by content hash

An authenticated `curl` session exists on this pod (company 0, user `opencode`),
so this is the real rendered page, not the login form. Each body has FA's volatile
bits (`_token`, timestamp) stripped and is then md5'd — two tabs that render the same
content must hash identically, and a tab that renders nothing but the menu is visible
as such.

| URL | before (hash / bytes) | after (hash / bytes) | verdict |
|---|---|---|---|
| `index.php?view=dashboard` | `eacddcd65c35` / 8214 | `eacddcd65c35` / 8214 | **identical** |
| `index.php?view=projects` | `fb6889f8c8ce` / 11084 | `fb6889f8c8ce` / 11084 | **identical** |
| `index.php?view=tasks` | `31577958893a` / 10788 | `31577958893a` / 10788 | **identical** |
| `index.php?view=team` | `b270685645e3` / 9154 | `b270685645e3` / 9154 | **identical** |
| `index.php?view=reports` | `f9ff8d80b368` / 7481 | `f9ff8d80b368` / 7481 | **identical** |
| `index.php?view=project_types` | `4f33b0bd6abb` / 12607 | `4f33b0bd6abb` / 12607 | **identical** |
| `index.php` (no parameter) | `eacddcd65c35` / 8214 | `eacddcd65c35` / 8214 | **identical** (dashboard) |
| `index.php?view=bogus_tab` | `eacddcd65c35` / 8214 | `eacddcd65c35` / 8214 | **identical** (falls back to dashboard) |
| `index.php?view=projects&page=2` | `dc0ad1623645` / 10593 | `dc0ad1623645` / 10593 | **identical** (pager works) |
| `index.php?page=3` | `eacddcd65c35` / 8214 | `eacddcd65c35` / 8214 | **identical** (page ≠ tab selector) |
| `index.php?tab=projects` | `eacddcd65c35` / 8214 | `b7be1726548e` / 11083 | **CHANGED — intentional** (see below) |
| `index.php?view=projects&action=save` | *(projects tab)* | `586b501b94c2` / 11100 | projects tab, see §2.2 |
| `pm.php` | `371b83ec5ac0` / 1079 | `371b83ec5ac0` / 1079 | **identical** |
| `pages/*.php` (all 8) | `e138f01d5574` / 1082 | `e138f01d5574` / 1082 | **identical** |

**The one intentional delta: `?tab=` is now accepted.** Before, `index.php` read only
`$_GET['view']`, so `?tab=projects` silently fell through to the dashboard — the tab
key was lost. The base class is configured with `tab_param = 'view'` and
`alias_param = 'tab'`, so `?tab=<tab>` now reaches the same tab. Line-level diff of
`?view=projects` vs `?tab=projects`: the **only** difference is the echoed form
`action`, which is `$_SERVER['REQUEST_URI']` verbatim and therefore correctly keeps
whichever URL you arrived on. Nothing else changes. HRM and CRM already behave this
way; PM now matches the house convention.

**`?view=…&action=…` is unchanged.** `diff` of `?view=projects` against
`?view=projects&action=save` shows one line: the echoed form `action` URL. The tab
renders; the base class's "This action is not available for the selected tab"
message never appears.

### 1c. Neighbour sweep after the change

All authenticated, all HTTP 200, none showing FA's denial string:

| URL | code | title | bytes |
|---|---|---|---|
| `/` | 200 | Main Menu | 16353 |
| `/index.php` | 200 | Main Menu | 16353 |
| `/admin/inst_module.php` | 200 | Install/Activate extensions | 30740 |
| `/sales/sales_order_entry.php` | 200 | — | 5963 |
| `/modules/ksf_FA_HRM/hrm.php` | 200 | HRM | 9702 |
| `/modules/ksf_FA_HRM/hrm.php?tab=leave` | 200 | HRM | 10344 |
| `/modules/ksf_FA_CRM/index.php` | 200 | CRM | 6843 |
| `/modules/ksf_FA_CRM/index.php?view=contacts` | 200 | CRM | 11167 |
| `/modules/ksf_FA_Calendar/cal.php` | 200 | Calendar | 29022 |

A 237-entry sweep of every `fa_modules/**/*.php` file that is not a class file or a
CLI runner returned 159×200, 1×302, 1×000 (`Shipping Cart.php`, a literal space in
the name), and 76×500. **All 76 are `class.*` model files, `test*.php` / `run_tests.php`
CLI runners and library `.inc`-as-`.php` files requested directly as web pages** —
structurally not entry points, matching the class of failure already recorded in
`CRM_FrontController_Adoption.md` §1. None is a PM file, and PM's changes are confined
to `fa_modules/ksf_FA_ProjectManagement/` (its own `vendor/` tree), which no other
module loads.

`journalctl -t ksfii_app-fa` over the whole window shows exactly two fatals, both from
my own deliberate direct probe of `hooks.php` (`Class 'hooks' not found`). No fatal
came from the change.

---

## 2. Did the six tab controllers implement `runAction()`? **No — none of them.**

### 2.1 The finding

```
DashboardTabController      class DashboardTabController                 (plain class, no base)
ProjectsTabController       extends AbstractTabController
TasksTabController          extends AbstractTabController
TeamTabController           extends AbstractTabController
ProjectTypesTabController   extends AbstractTabController
ReportsTabController        class ReportsTabController                    (plain class, no base)
```

`grep -n "function runAction"` across the six returns **nothing**.
`AbstractTabController` itself does **not** define `runAction()` either, so there is
nothing for a subclass to inherit. They own their verbs inside
`run()` → `handlePost()`: the `edit_<pk>` / `delete_<pk>` row buttons detected by
`MasterSummaryTable::getPostedAction()`, and the `<pk>_submit` / `<pk>_cancel` footer
buttons read straight out of `$_POST`.

Two further facts that shape the decision:

- **PM mints no `action=` link anywhere.** `grep -rn "action=" src/ hooks.php index.php`
  returns nothing. So `resolveAction()` reads `''` on every request the app itself
  generates, and `dispatchAction()` is unreachable in normal use.
- **Two of the six are not `AbstractTabController` subclasses at all**, so "add a
  `runAction()` to the controllers" is not a uniform change — it would mean inventing
  a verb contract for four controllers that have none and writing two from scratch.

### 2.2 What I did: **overrode `dispatchAction()`** (the CRM precedent)

```php
protected function dispatchAction(TabRegistration $tab, string $action): void
{
    $this->getAppShell()->dispatch($tab->getKey());
}
```

**Why override rather than add `runAction()`:**

1. **Behaviour preservation.** Adding `runAction()` would be *new* contract surface on
   six controllers whose verbs are already, deliberately, owned by `handlePost()`. It
   would have to decide verb semantics (`save`? `update`? `delete`?) that nobody has
   specified, and any wrong guess becomes a new way to lose data.
2. **The override is exact.** The old `index.php` dispatched the tab unconditionally,
   ignoring `action` entirely. Dispatching the tab unconditionally reproduces today's
   behaviour character for character — verified above at `?view=projects&action=save`.
3. **It is safe by construction.** `AbstractFrontController::run()` enforces security
   *before* choosing the dispatch path, so overriding cannot widen access. This is the
   documented contract for that seam.
4. **It removes the CRM-class hazard.** Without the override, a hand-crafted
   `?view=projects&action=save` would render "This action is not available for the
   selected tab" **instead of** the projects page. If any future form or bookmark ever
   emits `action=`, that becomes a silent no-op on the tab.

**And it is now pinned by a test** — `testNoPmTabControllerImplementsRunAction()`
walks the real `PmAppShell`'s tabs and fails if any controller ever grows a
`runAction()`. That is the guard CRM's adoption lacks: when someone eventually does
add a verb, the test tells them to delete the override rather than leave it shadowing
their work.

---

## 3. Base-class options needed, and why

`PmFrontController::defaultOptions()` pins all four; each is also asserted by
`testDefaultOptionsPinPmsPublishedUrlSurface`.

| Option | Value | Why PM needs it |
|---|---|---|
| `tab_param` | `'view'` | PM publishes `?view=`. The sub-menu (`PmAppShell` → `FAModuleMenu`) mints `index.php?view=<key>`, and every canonical URL in the wild uses `view`. The base's default is `tab`, which would have silently broken all of them. |
| `alias_param` | `'tab'` | The base's default alias is `view`, which would collide with the canonical param. Flipping it makes `?tab=` the accepted house-standard alias and `?view=` stay canonical — the only behaviour change (§1b). |
| `normalise_get` | `false` | **The load-bearing one.** The base normally rewrites `$_GET['tab']` and **unsets** the alias. With `tab_param='view'` that means `unset($_GET['view'])`. `AbstractTabController::preserveParams()` defaults to `['view']` and `MasterSummaryTable::pagerUrl()` copies each name in that list **verbatim** out of `$_GET` — so normalising would strip the tab off **every pager link in the app** and drop the reader back on the dashboard. Leaving `$_GET` untouched is what makes the base's "`page` is never a tab selector" guarantee the *only* new routing rule PM gains. |
| `load_ui_includes` | `false` | `includes/ui.inc` reads `$path_to_root` as a global in its including scope, so the proven path is a global-scope include in `index.php` — the HRM and CRM shape. (v1.0.14 also seeds the variable inside `loadUiIncludes()`, so this is belt-and-braces, not a limitation.) |

Subclass seams supplied: `getPageTitle()` → `_("Project Management")`,
`getPageJs()` → the date-picker bundle **unconditional on the tab key** (PM has always
shipped it on every tab; narrowing it would be a behaviour change), and
`dispatchAction()`.

### 3.1 Enforcement PM gains

The old preamble resolved the area before `boot()` and **never re-checked a
hook-contributed tab against its own area**. The base closes that: `run()` boots,
re-resolves, then enforces against the contributed tab's *own* area. Proved in
`tests/probe_pm_register_tabs.php` (run inside the container on PHP 7.4.33):

```
register hook    = pm_register_tabs
core tabs        = 6
pre-boot area    = SA_ksf_FA_ProjectManagementVIEW   <- structural: the hook cannot fire before session.inc
pre-boot tab     = dashboard
after boot tabs  = 7
contributed tab  = true
resolved tab     = probe
areas checked    = SA_THIRDPARTY_PROBE_VIEW          <- its OWN area, not the fallback
TAB-RENDERED                                           <- the contributed controller actually ran
menu has probe   = yes
```

---

## 4. Vendor cleanliness (the burned-by-PHPUnit check)

`composer update --no-dev` then `composer install --no-dev` in the deployed tree.

| Check | Result |
|---|---|
| `vendor/bin/` | **absent** (0 entries) |
| `vendor/composer/installed.json` → `dev-package-names` | **`[]`** |
| Installed packages | `ksfraser/exceptions v1.3.0`, `ksfraser/html 2.0.7`, `ksfraser/ksf-common-db v1.0.1`, **`ksfraser/ksf-fa-common v1.0.14`** — 4 packages, no dev |
| `vendor/{phpunit,sebastian,doctrine,myclabs,nikic,phar-io,theseer}` | **0 present** |
| `platform_check.php` | requires `>= 7.4.0`, consistent with `config.platform.php = 7.4.33` |
| `composer install --no-dev` re-run | "Nothing to install, update or remove" — the lock reproduces the tree exactly |

Package moves: `ksf-fa-common` **dev-master → v1.0.14** (the vendored copy had **no
`src/App/AbstractFrontController.php` at all**); `ksf-common-db` dev-main → v1.0.1
(`diff -rq` confirms `src/` is byte-identical to what was deployed, so this is a
version-label change, not a code change).

**Pre-existing, proved pre-existing** (present in a `cp -a` of the vendor taken before
any of this work): `vendor/ksfraser/html/vendor/` — the `ksfraser/html` package's own
nested vendor — ships `phpunit 9.6.34`, `sebastian/*`, `doctrine/instantiator`,
`myclabs/deep-copy`, `nikic`, `theseer`, `phar-io`. It came in with the published
`ksfraser/html 2.0.7` dist, nothing under `vendor/ksfraser/html/src` references it,
and it is not reachable from PM's `ClassLoader`. Same finding as CRM §4; the fix
belongs in that package's `.gitattributes`, not here.

### 4.1 Three composer.json changes were unavoidable

1. **Dropped the two dead `path` repositories** (`../ksf_FA_Common`,
   `../ksf_common_db`). Composer 2.5 **hard-errors** — `The 'url' supplied for the path
   (../ksf_FA_Common) repository does not exist` — so no `composer update` of any kind
   could run until they were removed. Those paths resolve relative to the *deployed*
   module directory (`fa_modules/ksf_FA_Common`), which does not exist. The third
   path repo (`../ksfraser/html`) does resolve and was kept.
2. **Pinned `config.platform.php = 7.4.33`.** Without it the vendor resolves against
   the host's PHP 8.1 while the container runs 7.4 — the site-wide 500 hazard in
   `AGENTS.md`. CRM already pins this.
3. **`require-dev`: `phpunit/phpunit` `^10.0` → `^9.6`.** PHPUnit 10 requires
   `php >= 8.1`, so with the platform pin in place it **cannot be resolved at all** and
   the update failed outright. PM's tests are PHPUnit 9-era (no PHP 8 attributes, no
   `#[DataProvider]`, classic `assertStringContainsString`), so `^9.6` is both the
   correct constraint and the one that unblocks the deploy. See §5 — this is also why
   the suite is now green.

---

## 5. Tests

Suite: `/home/kevin/Documents/ksf_Infrastructure/fa_modules/ksf_FA_ProjectManagement/tests`.
There is **no test runner in the deployed tree** — by design, `--no-dev` means no
PHPUnit there — so the suite is driven from an external binary against the deployed
files.

| Run | Result |
|---|---|
| **Baseline before the change**, old vendor, PHPUnit 10.5.63 | `Tests: 110, Assertions: 187, Errors: 4, Failures: 39` |
| Baseline before the change, old vendor, PHPUnit 9.6.37 | `Tests: 110, Assertions: 246, Errors: 6` |
| **Full suite after**, PHPUnit **9.6.37** (the now-declared constraint) | **`OK (131 tests, 317 assertions)`** |
| Full suite after, PHPUnit 10.5.63 (external binary, does not match `composer.json`) | `Tests: 131, Errors: 4, Failures: 39` |
| **`PmFrontControllerTest` only**, PHPUnit 9.6.37 | `OK (21 tests, 57 assertions)` |
| `PmFrontControllerTest` only, PHPUnit 10.5.63 | `OK (21 tests, 57 assertions)` |

**The suite was red before this work and is green now — but the reason is the PHPUnit
constraint, not the front controller.** PM declared `require-dev: phpunit ^10.0` and
was being run with a PHPUnit 10 binary; ~40 DAO/repository tests fail under PHPUnit
10 semantics (e.g. `assertStringContainsString(): Argument #2 must be of type string,
null given` in `ProjectTypeServiceTest`) and pass under 9.6. Pinning `^9.6` (§4.1.3)
resolves the requirement and the suite is `OK 131/131`. The vendor update independently
fixed 4 `AssignmentRepositoryTest` errors that the old `dev-main` `ksf-common-db` had
introduced (proven by `comm` on the two sorted failure lists: 4 failures removed, **0
added**).

### 5.1 `tests/Unit/PmFrontControllerTest.php` — new, 21 cases

`?view=` canonical · `?tab=` alias · `view` beats `tab` · unknown view → default ·
**`page` is never a tab selector** · pager position resolved and clamped · `$_GET` not
normalised · security area is the tab's own · fallback for a tab with no area ·
**empty fallback area throws** · `run()` dispatches the requested tab and checks its
area · `$_GET` reaches the tab controller verbatim · **an action verb renders the tab
and never emits "not available"** · **a `pm_register_tabs` contribution is reachable
and checked against its OWN area** · **a contributed tab is invisible to the
pre-session area resolution** · the real shell publishes `pm_register_tabs`, default
`dashboard` and six controller-backed core tabs · **no PM tab controller has
`runAction()`** · `defaultOptions()` pins the URL surface · explicit options override
· **`index.php` still resolves the area before `session.inc` and calls `run()` exactly
once** · **`run()` is inherited from the base and `final`, `enforceSecurity()` is
`final`**.

### 5.2 `tests/probe_pm_register_tabs.php` — new, in-container proof

Not a PHPUnit test (it lives outside `tests/Unit` on purpose). Run it inside the
container to prove `pm_register_tabs` end to end against real PHP 7.4.33:

```
podman exec -w /var/www/html/modules/ksf_FA_ProjectManagement ksfii_app-fa \
  php tests/probe_pm_register_tabs.php
```

### 5.3 Syntax and PHP-version safety

| Check | Result |
|---|---|
| `php -l` on `index.php`, `PmFrontController.php`, `PmFrontControllerTest.php`, `probe_pm_register_tabs.php` — host PHP 8.1 | clean |
| Same four files **inside the container on PHP 7.4.33** | clean |
| `composer.json` parses (`json_decode`) inside the container | clean |
| PHP-8-only construct scan (`match(`, `?->`, `readonly`, `fn(`, union types, `#[`) on the changed files | **none found** |

---

## 6. POST actions persist (end-to-end, real DB)

Driven over authenticated HTTP through the new controller. Every write was reverted
afterwards; the DB is back to its pre-test state (`0_fa_pm_projects` = `PRJ-0001` only,
probe activity-log rows deleted).

| Step | Mechanism | Result |
|---|---|---|
| **Create** | `POST project_id_submit=Save` on `?view=projects` | `PRJ-0002` inserted — `budget 4242.00`, `status Planning`, `project_manager opencode` |
| **Edit pre-load** | `POST edit_PRJ-0001=PRJ-0001` | form prefilled with the stored record, footer flipped `Save` → `Update`, hidden `project_id` set, **DB untouched** |
| **Update** | `POST project_id_submit=Save` with `project_id=PRJ-0002` | row updated to `budget 7777.00`, `status Active`, `project_manager kevin` |
| **Delete** | `POST delete_PRJ-0002=PRJ-0002` | row removed |
| **Bonus** | `0_fa_pm_activity_log` rows 6/7/8 | `created` / `updated` / `deleted` were written — the `pm_*` pre/post-save workflow hooks fired through the new controller |

Nothing silently no-opped.

---

## 7. What changed, and what was left alone

| File | Change |
|---|---|
| `index.php` | 59 → 99 lines, but *less* logic: the preamble is replaced by `new PmFrontController(new PmAppShell(), 'SA_ksf_FA_ProjectManagementVIEW', $path_to_root)`, `getSecurityArea()` → `$page_security` → `session.inc` → `add_access_extensions()` → global `ui.inc` → `run()` |
| `src/Ksfraser/FrontAccounting/ProjectManagement/App/PmFrontController.php` | **new**, 170 lines. Thin subclass: title, head JS, the four options, `dispatchAction()` |
| `tests/Unit/PmFrontControllerTest.php` | **new**, 21 cases |
| `tests/probe_pm_register_tabs.php` | **new**, in-container hook proof |
| `composer.json` | dead `path` repos removed; `config.platform.php = 7.4.33`; `require-dev` phpunit `^9.6` |
| `composer.lock` | **created** (gitignored — not committed) |
| `vendor/` | refreshed, `--no-dev` (gitignored) |
| **`hooks.php`** | **UNTOUCHED** — `git diff HEAD -- hooks.php` = **0 lines**, md5 `6e10ab3adb0f5a3f36f1a20e44fdfc4e` on both sides, **14 methods** before and after |

### The two SHA story

`origin/main` was **8+ commits ahead** of the deployed checkout, carrying BR-007
feature work (`3558506 feat(pm): BR-007 event-close membership responder + task
time-window close`) that adds 89 lines to `hooks.php`, 28 to `sql/install.sql` and
seven new `src/` services — **none of it installed or deployed on this pod**. Rebasing
in the live tree would have deployed that untested feature work into the integration
box and edited `hooks.php`, which the brief explicitly forbids.

So the commit was rebased onto `origin/main` **in a throwaway git worktree under
`/tmp`**, pushed from there as **`f1a0bc7`**, and the worktree removed. Verified
`diff`-identical between the pushed tree and the live tree for both changed source
files. The live deployed checkout stays at **`4161fd8`**, which is content-identical
to `f1a0bc7` for every file this task touched, and lags `origin/main` only by the
undeployed BR-007 work. **Deploying BR-007 to this pod is a separate decision and
needs its own `sql/install.sql` run.**

---

## 8. Deferred / limitations

1. **`SA_…_MANAGE` is declared but unused.** `hooks.php` declares both
   `SA_ksf_FA_ProjectManagementVIEW` and `SA_ksf_FA_ProjectManagementMANAGE`, and
   **all six core tabs are registered against the VIEW area**; nothing in the module
   reads the MANAGE area. Every tab therefore has identical read/write access. This
   is **pre-existing and unchanged** — it does not block the adoption — but it is a
   real authorisation gap: anyone who can view PM can also create, edit and delete
   projects, tasks and project types. Worth closing by registering the mutating tabs
   against `…MANAGE`. Not done here because it would change access behaviour, and the
   brief is behaviour-preserving.
2. **Two of six tabs are not `AbstractTabController` subclasses** —
   `DashboardTabController` and `ReportsTabController` are plain classes with a
   `run()` method. They work through `AbstractAppShell::dispatch()`, which only
   requires `run()`, so nothing is broken, but they get none of the base class's form
   lifecycle and would need subclassing before an `action` verb could be routed to
   them.
3. **The legacy entry points are dead and were left dead.** `pm.php` and all eight
   `pages/*.php` gate on `$session->check_access('PM_VIEW_PROJECT')` — an area that
   does not exist in FA — so every one of them renders a 1 082-byte "Access denied"
   page. They are **byte-identical before and after**, and deliberately **not** routed
   through the front controller. Whether they should be deleted or re-pointed at the
   app shell is a product decision, not a refactor.
4. **`ksf_FA_Calendar/index.php` is a 404** — it is not an entry point. Calendar's
   entry point is `cal.php`, which is 200 (§1c). No action.
5. **`ksfraser/html`'s nested vendor** still ships dev packages (§4). Fix belongs in
   that package's export rules.
6. **`APP_TAB_ARCHITECTURE.md` §11 was not updated** with a PM adoption row. It is
   hardlinked across the module repos and follows an intentional-write ritual, so it
   is a cross-repo edit, not a local one.
7. **BR-007 remains undeployed** (§7).
8. **The two `path` repositories that were removed** (`../ksf_FA_Common`,
   `../ksf_common_db`) may have been intended to point at a dev tree that used to sit
   beside the deployed module. Nothing references them now; if a future workflow needs
   them they should point at a path that exists.

---

## 9. Related documents

- `ksf_Architecture_Docs/AbstractFrontController_Design.md` — the base class.
- `ksf_Architecture_Docs/CRM_FrontController_Adoption.md` — the closest precedent
  (same `?view=` shape, same `dispatchAction()` override, same `normalise_get` reason).
- `ksf_Architecture_Docs/HRM_Controller_Consolidation.md` — the `page` → `tab` rename.
- `ksf_Architecture_Docs/How_To_Add_Tabs_To_A_Module.md` §2 and §8 — **now stale for
  PM**: it says "PM does not adopt `AbstractFrontController`" and lists PM under the
  failure mode "a hook-contributed tab is served under the host's area". Both are no
  longer true.