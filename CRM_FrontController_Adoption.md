# CRM `AbstractFrontController` adoption

**Module:** `ksf_FA_CRM` (dev tree `~/Documents/ksf_FA_CRM`, deployed
`~/Documents/ksf_Infrastructure/fa_modules/ksf_FA_CRM`)
**Target:** `http://localhost:8090` — container `ksfii_app-fa`, PHP **7.4.33**
**Commit:** `a81db58` — *refactor(crm): adopt the shared AbstractFrontController for
the CRM front page* (pushed to `origin/main`)
**Date:** 2026-10-13

---

## 1. Before / after URL status

Unauthenticated `curl` probes. FA serves its login form inline (HTTP 200, not a
302) when there is no session, so "200" means *the page bootstrapped and reached
`session.inc`* — which is exactly the boundary the old fatal sat in front of.

| URL | before | after |
|---|---|---|
| `/modules/ksf_FA_CRM/index.php` | **500** | 200 |
| `…/index.php?view=dashboard` | **500** | 200 |
| `…/index.php?view=contacts` | **500** | 200 |
| `…/index.php?view=customers` | **500** | 200 |
| `…/index.php?view=leads` | **500** | 200 |
| `…/index.php?view=opportunities` | **500** | 200 |
| `…/index.php?view=communications` | **500** | 200 |
| `…/index.php?view=meetings` | **500** | 200 |
| `…/index.php?view=quotes` | **500** | 200 |
| `…/index.php?view=tags` | **500** | 200 |
| `…/index.php?view=customer_types` | **500** | 200 |
| `…/index.php?view=territories` | **500** | 200 |
| `…/index.php?view=opportunity_sources` | **500** | 200 |
| `…/index.php?view=opportunity_types` | **500** | 200 |
| `…/index.php?view=opportunity_realms` | **500** | 200 |
| `…/index.php?view=opportunity_stages` | **500** | 200 |
| `…/index.php?view=admin` | **500** | 200 |
| `…/index.php?view=bogus_tab` (unknown tab) | **500** | 200 (falls back to dashboard) |
| `…/index.php?view=contacts&page=2` | **500** | 200 |
| `…/index.php?tab=contacts` (new alias) | **500** | 200 |
| `…/index.php?view=leads&action=save` | **500** | 200 |
| `…/pages/*.php` (19 standalone pages, incl. `convert_lead.php?lead_id=1`) | 200 | 200 |
| `…/pages/index.php` | 500 | 500 (see §3.3 — dead scaffold) |
| `/modules/ksf_FA_HRM/hrm.php`, `?tab=leave` | 200 | 200 |
| `/`, `/index.php`, `/admin/inst_module.php`, `/sales/sales_order_entry.php` | 200 | 200 |

Site root stayed **HTTP 200** throughout, including during the deploy and during
the `git stash`/fast-forward dance in the deployed checkout (the working-tree
window between reverting and re-applying the commit was re-probed immediately
and is byte-identical to the final probe: `/tmp/crm_status_final.txt` ==
`/tmp/crm_status_after.txt`).

Neighbour-module sweep after the change — every module root entry point in
`fa_modules/` returns 200 except two files that are not web entry points and
were already fatal before this work:
`ksf_FA_ImportStagingProcessing_UI/class.bi_counterparty_model.php`
(`_()` undefined — a class file requested directly) and
`ksf_FA_Square/run_tests.php` (`strict_types` not the first statement — a CLI
test runner).

---

## 2. What changed

| File | Change |
|---|---|
| `src/FrontAccounting/CRM/App/CrmFrontController.php` | **new**, 156 lines. Thin subclass of `ksfraser\FrontAccounting\Common\App\AbstractFrontController`. Supplies the page title (`"CRM"`), the `<head>` date-picker bundle, the CRM controller options, and `dispatchAction()`. |
| `index.php` | 68 → 118 lines, but *less* code: preamble replaced by `new CrmFrontController(new CrmAppShell(), 'SA_CRM_DASHBOARD', $path_to_root)`, `getSecurityArea()` → `session.inc` → `add_access_extensions()` → global `ui.inc` → `run()`. |
| `tests/Unit/CrmFrontControllerTest.php` | **new**, 16 cases (see §5). |
| `tests/Unit/PageStructureTest.php` | Two structural tests re-pointed at the new shape (they asserted `getDefaultView`/`getTab`/`renderMenu` string literals in `index.php`, which now live in the inherited base and the shell). |
| `tests/Unit/TabExtensionTest.php` | `testIndexPageBootsBeforeResolvingViewAndSecurity` re-pointed at the new structure — see §5.2. |
| `composer.lock` | `ksfraser/ksf-fa-common` v1.0.12 → **v1.0.14** (`composer update ksfraser/ksf-fa-common` in the dev tree; `composer install --no-dev` in the deployed tree). |
| `hooks.php` | **untouched** — `git diff HEAD -- hooks.php` is 0 lines; function count 26 before and after, verified in both trees. |

### 2.1 Three options were needed to keep CRM's behaviour identical

`CrmFrontController::defaultOptions()` pins them, and the unit tests assert them:

1. **`tab_param => 'view'`.** CRM has always published `?view=`, and three
   emitters would have broken otherwise: the in-page sub-menu
   (`CrmAppShell::renderMenu()` → `FAModuleMenu`), `AdminHubTabController`
   (`'index.php?view=' . rawurlencode(...)`) and the RBAC application menu in
   `hooks.php` (`new FAModuleMenu('modules/ksf_FA_CRM/index.php', 'view', '')`).
   `?tab=` is kept as the accepted alias (`alias_param => 'tab'`), so the house
   convention resolves too, but it is never emitted.
2. **`normalise_get => false`.** The base normally rewrites `$_GET[tab]` and
   unsets the alias. That would have been a silent, total breakage of CRM's
   pagination: `AbstractTabController::preserveParams()` defaults to `['view']`
   and `MasterSummaryTable::pagerUrl()` copies those `$_GET` keys *verbatim*
   onto the pager links it builds, so every CRM pager link would have lost the
   tab and landed on the dashboard. `OptionListsTabController` also reads
   `$_GET['view']` (line 44) to tell the four option-list tabs apart — the same
   break. Leaving `$_GET` alone is what makes the base's "`page` is never a tab
   selector" guarantee the *only* new routing rule CRM gains.
3. **`load_ui_includes => false`.** `includes/ui.inc` reads `$path_to_root` as a
   global in its including scope, so it is included by `index.php` at global
   scope (the HRM pattern). v1.0.14 also seeds the variable inside
   `loadUiIncludes()`, so this could now be left on, but CRM's file already does
   it at global scope and the global include is the proven path.

### 2.2 `dispatchAction()` is overridden — deliberately

`AbstractFrontController::run()` routes a non-empty `action` verb to
`$controller->runAction($action)` and renders "this action is not available" if
the controller has no such method. **CRM's tab controllers never implemented
`runAction()`** — they own their verbs inside `run() → handlePost()`
(`edit_<pk>` / `delete_<pk>` submit buttons), and the old `index.php` dispatched
the tab unconditionally. Adopting the base unmodified would therefore have
turned **every POST save into a silent no-op**. `CrmFrontController::dispatchAction()`
dispatches the tab, reproducing today's behaviour exactly. Overriding it is safe
in the way the base documents: `enforceSecurity()` has already run.

### 2.3 One intentional behaviour delta (access control, in the safe direction)

Old `index.php` hard-coded `$page_security = 'SA_CRM_DASHBOARD'` **before**
`session.inc`, so every CRM tab opened its session under the dashboard area and
the tab's own area was enforced only later by
`AbstractAppShell::dispatch()`. `getSecurityArea()` now resolves the *requested*
tab's own area pre-session (which the old file's own comment says it wanted).

Net effect: a user who holds a tab's area but not `SA_CRM_DASHBOARD` is no
longer refused at `session.inc` — they were refused there by accident and
allowed nowhere anyway. A user holding neither is refused at the same place as
before. Enforced once by the base, then again by `dispatch()`; both are
`check_page_security()` on the same area, so the double call is idempotent.

---

## 3. Root cause of the 500s

### 3.1 `index.php` and every `?view=` URL — **the deployed vendor autoloader was stale**

Reproduced and confirmed from the container's journald (`journalctl -t
ksfii_app-fa`; `podman logs` is empty because the container's log driver is
`journald`):

```
PHP Fatal error: Uncaught Error: Class 'ksfraser\FrontAccounting\CRM\App\CrmAppShell' not found
  in /var/www/html/modules/ksf_FA_CRM/index.php:24
```

The deployed `vendor/composer/autoload_psr4.php` still carried the **pre-refactor**
PSR-4 map:

```
'Ksfraser\\FA\\CRM\\Services\\' => $baseDir . '/includes',
'Ksfraser\\FA\\CRM\\'            => $baseDir . '/src/Ksfraser/FA/CRM',
'Ksfraser\\FA\\'                 => vendor/ksfraser/fa-classes/src/Ksfraser/FA,
```

and had **no** entry for `ksfraser\FrontAccounting\CRM\` at all — i.e. it predates
commit `f3ee56d` ("refactor(crm): namespace to `ksfraser\FrontAccounting\CRM`").
`index.php:24` constructs `CrmAppShell` **before** `session.inc`, so the fatal
happened before any access check and every CRM URL was a bare HTTP 500 with an
empty body, authenticated or not. `src/Ksfraser/FA/CRM/Services/` still exists
in the module as empty leftover directories from that refactor.

**Fixed by** `composer install --no-dev` in the deployed tree, which regenerated
the map from the current `composer.json`:

```
'ksfraser\\FrontAccounting\\CRM\\'   => $baseDir . '/src/FrontAccounting/CRM'
'ksfraser\\FrontAccounting\\Common\\'=> vendor/ksfraser/ksf-fa-common/src
```

**Did adopting the controller fix it? No — and that is the honest answer.**
The 500 was a stale `vendor/`, not a routing bug; the controller adoption neither
caused nor cured it. `composer install --no-dev` cured it. The controller work is
independent: the old `index.php` would work just as well with a fresh vendor, and
the new one needs the fresh vendor just as much.

### 3.2 `access/login.php` — **pre-existing core-FA behaviour, not CRM**

```
PHP Fatal error: Uncaught Error: Call to undefined function _()
  in /var/www/html/access/login.php:13
```

Line 13 is the restricted-access guard:

```php
if (!isset($path_to_root) || isset($_GET['path_to_root']) || isset($_POST['path_to_root']))
    die(_("Restricted access"));
```

`access/login.php` is meant to be *included* by `session.inc` (which sets
`$path_to_root` and loads `includes/gettext.inc`, which defines `_()`). Requested
directly, `$path_to_root` is unset, so the guard fires — and calls `_()` before
gettext is loaded, so the intended `die("Restricted access")` becomes a fatal
500 instead. Nothing to do with CRM, unchanged by this work, and **not fixed**
here: the fix belongs in core FA (`FA/2.4.3`), which is a separate repo and out of
scope. It also means `login.php` is not a usable `curl` target for
authenticating — see §6.

### 3.3 `pages/index.php` — **still 500, and it always was**

```
PHP Fatal error: Uncaught Error: Class 'ksf\App' not found
  in /var/www/html/modules/ksf_FA_CRM/pages/index.php:5
```

Same stale-autoloader symptom, but a *different* root cause underneath it: the
file is an untouched scaffold stub whose `$app = new \ksf\App();` names a class
that does not exist anywhere in the module (the real namespace is
`ksfraser\FrontAccounting\CRM\...`). Refreshing the vendor cannot fix it.
`tests/Unit/PageStructureTest.php` even pins `new \ksf\App()` in the file. Left
alone deliberately: it was 500 before, no other module links to it, and "fixing"
it means deciding whether that page should exist at all — a separate decision.

---

## 4. Vendor cleanliness (the burned-by-PHPUnit check)

`composer update ksfraser/ksf-fa-common` in the dev tree, then
`composer install --no-dev` in the deployed tree:

| Check | Result |
|---|---|
| `vendor/bin/` in the deployed tree | **empty / absent** (0 entries) |
| `vendor/composer/installed.json` → `dev-package-names` | `[]` |
| Installed packages (deployed) | `ksfraser/exceptions@1.3.0`, `fa-classes@1.7.0`, `gedcom@dev-main`, `html@2.0.7`, **`ksf-fa-common@1.0.14`**, `ksf-modules-dao@0.5.3`, `rbac@dev-master`, `traits@1.3.0`, `validation@0.1.0`, `psr/event-dispatcher@1.0.0`, `psr/log@1.1.4` — 11 packages, no dev |
| `find vendor -iname '*phpunit*' -o -iname '*sebastian*' -o -iname '*doctrine*' -o -iname '*myclabs*' -o -iname '*php-parser*' …` (top level) | **nothing** |
| `platform_check.php` | consistent with `config.platform.php = 7.4.33` |

One caveat, **pre-existing and proved pre-existing** (present in a `cp -a` of the
vendor taken before any of this work): `vendor/ksfraser/html/vendor/` — the
`ksfraser/html` **package's own nested** vendor tree — ships `phpunit 9.6.34`,
`sebastian/*`, `doctrine/instantiator`, `myclabs/deep-copy`, `nikic`, `theseer`,
`phar-io`. It came in with the published `ksfraser/html 2.0.7` dist, nothing in
`vendor/ksfraser/html/src` references it, and it is **not** reachable from
CRM's `ClassLoader`, so it is dead weight rather than the eager-autoload
`Parse error` hazard the AGENTS notes describe. Left in place: deleting files
from inside a Composer-managed package creates drift that the next
`composer install` silently reintroduces. It should be raised against
`ksfraser/html`'s own packaging (ship a `.gitattributes` export-ignore).

---

## 5. Tests

Suite: `/home/kevin/Documents/ksf_FA_CRM/tests`, run with the dev tree's
`vendor/bin/phpunit` (PHPUnit 9.6.37, host PHP 8.1).

| Run | Result |
|---|---|
| Baseline before the change (with `ksf-fa-common` v1.0.14 already installed) | `OK (195 tests, 570 assertions)` |
| After the change | **`OK (211 tests, 605 assertions)`** — +16, none broken |

### 5.1 `tests/Unit/CrmFrontControllerTest.php` (new, 16 cases)

- `?view=` is the canonical selector; `?tab=` resolves; `view` beats `tab`.
- Unknown view falls back to the default tab; **`page` is never a tab selector**.
- `$_GET` is not normalised, so `['view','page']` survive verbatim for pager links.
- `getSecurityArea()` returns the *tab's own* area, and falls back to
  `SA_CRM_DASHBOARD` for a tab that declares none.
- `run()`: a tab contributed through `crm_register_tabs` is reachable **and** is
  checked against `SA_INSURANCE_VIEW` (not the fallback); `$_GET` is handed to the
  tab controller unchanged.
- An `action` verb still reaches the tab controller, and the access check has
  already run by then.
- The real `CrmAppShell` publishes hook `crm_register_tabs` and default view
  `dashboard`; `defaultOptions()` pins the URL surface; explicit options override.

### 5.2 The source-order guard was re-pointed, not deleted

`TabExtensionTest::testIndexPageBootsBeforeResolvingViewAndSecurity` used to
assert that `index.php` calls `$appShell->boot()` before resolving `?view=` and
before assigning `$page_security`. Those three statements no longer exist in
`index.php` — the ordering now lives inside `run()`. The invariant is still
pinned, harder:

- `getSecurityArea()` appears before `session.inc` in the source, and `run()`
  appears after it, and `run()` is called **exactly once**;
- `AbstractFrontController::run()` is `final` (reflection);
- `CrmFrontController::run()` is **inherited** from the base, not overridden
  (reflection on the declaring class) — so boot-then-enforce cannot be
  reordered or dropped from CRM.

### 5.3 Syntax

`php -l` on all five changed/added files: clean on host PHP 8.1 **and** inside
the container on PHP 7.4.33 (`php -l` in `/var/www/html/modules/ksf_FA_CRM`).
PHP 8-only construct scan (`match(`, `?->`, `readonly`, `fn`): none.

### 5.4 Runtime proof inside the container (PHP 7.4.33)

```
php -r 'require bootstrap.php; $s=new CrmAppShell(); $c=new CrmFrontController($s,"SA_CRM_DASHBOARD","../..");'
tabs=16
hook=crm_register_tabs
area=SA_CRM_DASHBOARD
view=contacts -> contacts
tab=contacts  -> contacts
page=contacts -> dashboard      <- page is not a selector
```

### 5.5 The deployed tree has no test runner

By design: `--no-dev` means no PHPUnit in the deployed vendor, so the suite runs
in the dev tree only. The deployed files are byte-identical to the committed
ones (`diff -rq` between the two trees reports only the four hardlinked shared
docs), so the green suite covers the deployed code.

---

## 6. Deferred / limitations

1. **Authenticated rendering was not exercised over HTTP.** No credentials are
   available for company 0, and FA's `SessionManager::preventHijacking()` binds
   a session to `REMOTE_ADDR` + user-agent, so the live browser sessions in
   `/tmp/sess_*` cannot be replayed from `curl` (10.89.1.1 ≠ 192.168.1.147) — they
   are wiped on use. Every "200" in §1 is FA's inline login form, proving the
   pre-session path (the one that used to fatal) and nothing more. Coverage of
   the authenticated path comes from the 16 new unit tests, which drive the real
   `run()` sequence — menu render, single access check, dispatch — and from the
   container CLI run in §5.4. **Recommended follow-up: one authenticated
   browser pass over the CRM tabs on 8090.**
2. **`pages/index.php` remains a 500** (§3.3). Needs an owner decision: delete
   the scaffold, or implement it. Not fixed here.
3. **`access/login.php` remains a 500 when requested directly** (§3.2). Core FA
   fix (`FA/2.4.3`), separate repo, out of scope.
4. **`ksfraser/html`'s nested vendor** still ships dev packages (§4). Fix belongs
   in that package's export rules.
5. **CRM's `$path_to_root` in `pages/*.php` is three levels** and its front page is
   two; that asymmetry is real (`dd94bc4` fixed the pages side) and is now
   documented in both file headers.
6. **`src/Ksfraser/FA/CRM/Services/`** — empty leftover directories from the
   `f3ee56d` namespace refactor. Harmless, but they are what made the stale
   autoloader look plausible. Worth deleting in a separate cleanup.
7. **`APP_TAB_ARCHITECTURE.md` §11 was not updated** with the CRM adoption row.
   It is hardlinked across the module repos and follows the intentional-write
   ritual, so it is a cross-repo edit, not a local one.