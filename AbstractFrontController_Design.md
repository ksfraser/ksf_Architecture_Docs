# `AbstractFrontController` — Design

**Package:** `ksfraser/ksf-fa-common` (`~/Documents/ksf_FA_Common`)
**Namespace:** `ksfraser\FrontAccounting\Common\App`
**Status:** new, uncommitted, untracked in the working tree
**PHP:** 7.3-compatible source, verified under a real PHP 7.4.33 runtime

Extracts the preamble that every module was hand-rolling at the module root into
one reusable base. Reference implementation that was extracted:
`ksf_FA_HRM/hrm.php`.

---

## 1. Files added (all new; nothing existing was touched)

| File | Purpose |
|---|---|
| `src/App/AbstractFrontController.php` | The base class |
| `src/App/FrontControllerSecurityException.php` | Fail-closed signalling |
| `src/App/FrontControllerRoutingException.php` | "No tab could be resolved" |
| `tests/Unit/App/AbstractFrontControllerTest.php` | 43 unit tests |
| `tests/Unit/App/FaHookStub.php` | Test fixture: global `hook_invoke_all()` stub |

---

## 2. Responsibilities

`AbstractFrontController` owns the *whole* request preamble and nothing else:

1. **Resolve the tab** from `?tab=` (canonical), with `?view=` as a deprecated
   alias.
2. **Resolve the security area** so the host can set `$page_security` and
   include `session.inc`.
3. **Boot the app shell**, firing `hook_invoke_all('<appId>_register_tabs', $data)`
   so third-party tabs merge in, then **re-resolve** so a contributed tab is
   reachable.
4. **Normalise `$_GET`** so every link the app emits carries the canonical
   parameter.
5. **Render the page wrapper and the tab menu.**
6. **Enforce access** — once, ahead of both dispatch paths.
7. **Dispatch** either the action verb or the tab.
8. **Close the page**, and include FA's `includes/ui.inc` first so tab
   controllers get `text_row()`, `amount_row()`, `submit_row()`, etc.

### The `tab` / `page` separation

`tab` is the tab selector. `page` is the pager position and is **never** read as
a tab selector. `normaliseRequest()` also leaves `$_GET['page']` untouched,
because `MasterSummaryTable::pagerUrl()` copies each name in its
`preserve_params` list verbatim out of `$_GET` — which is what makes pager links
come out as `?page=3&tab=leave`. `AbstractTabController::page()` reads
`$_GET['page']` as the PAGER and is correct as written; nothing here changes it.

A test registers a tab literally keyed `"3"` and asserts that `?page=3` still
resolves the *default* view — the collision cannot come back.

### URL shape

```
hrm.php?tab=<tab>                read
hrm.php?tab=<tab>&page=3         tab + pager position
hrm.php?tab=<tab>&action=save    mutation
```

---

## 3. Constructor contract

```php
public function __construct(
    AbstractAppShell $appShell,        // required — the tabs being served
    string            $fallbackSecurity, // REQUIRED, must be non-empty
    string            $pathToRoot = '',   // used to include includes/ui.inc
    array             $options = []
)
```

`$fallbackSecurity` is deliberately a **required** positional argument, not an
option. It is what makes enforcement fail closed for a third-party tab that
registers without an area of its own, so there is no way to construct the class
without it. An empty or whitespace-only value throws
`FrontControllerSecurityException`.

| Option | Default | Purpose |
|---|---|---|
| `tab_param` | `'tab'` | Tab selector parameter |
| `alias_param` | `'view'` | Deprecated tab alias; `''` disables |
| `action_param` | `'action'` | Action verb parameter |
| `page_param` | `'page'` | Pager position parameter |
| `normalise_get` | `true` | Write the resolved tab back into `$_GET` |
| `load_ui_includes` | `true` | Include `includes/ui.inc` before dispatch |
| `security_checker` | FA's `check_page_security()` | DI seam: `callable(string): void` |

`$options` is also retained on `$this->options` for subclasses.

---

## 4. How a module adopts it

The module root file goes from ~120 lines of preamble to this:

```php
<?php
// modules/ksf_FA_HRM/hrm.php

require_once __DIR__ . '/ComposerDependencies.php';
\ksfraser\FrontAccounting\HRM\Utils\ComposerDependencies::ensure(__DIR__);

if (file_exists(__DIR__ . '/vendor/autoload.php')) {
    require_once __DIR__ . '/vendor/autoload.php';
}

$path_to_root = '../..';

$frontController = new \ksfraser\FrontAccounting\HRM\HrmFrontController(
    new \ksfraser\FrontAccounting\HRM\App\HrmAppShell(),
    'SA_ksf_FA_HRMVIEW',   // fallback area — never empty
    $path_to_root
);

$page_security = $frontController->getSecurityArea();
include_once($path_to_root . "/includes/session.inc");
add_access_extensions();

$frontController->run();
```

And the module's subclass is pure declaration:

```php
namespace ksfraser\FrontAccounting\HRM;

use ksfraser\FrontAccounting\Common\App\AbstractFrontController;
use ksfraser\FrontAccounting\Common\App\TabRegistration;

class HrmFrontController extends AbstractFrontController
{
    protected function getPageTitle(): string
    {
        return _("HRM");
    }

    protected function getPageJs(TabRegistration $tab): string
    {
        if (!in_array($tab->getKey(), ['payroll', 'leave'], true)) {
            return '';
        }
        if (!function_exists('user_use_date_picker') || !user_use_date_picker()) {
            return '';
        }
        return function_exists('get_js_date_picker') ? get_js_date_picker() : '';
    }
}
```

### Why `session.inc` is NOT inside `run()`

FA's `session.inc` reads `$page_security` and `$path_to_root` as **globals** in
the including scope. From inside a method they would be method locals and the
include would see nothing. So the two-phase split is structural, not stylistic:

- **Phase A** (global scope): `getSecurityArea()` → `$page_security` →
  `include_once session.inc` → `add_access_extensions()`.
- **Phase B**: `run()`.

Phase A is what `hrm.php` already does; `run()` is the rest of it.

---

## 5. How security fails closed

Five independent guarantees:

1. **The constructor rejects an empty fallback area** — there is no
   "no area configured, no check performed" state.
2. **`run()` is `final`.** A subclass cannot replace the dispatch sequence, and
   therefore cannot reorder or omit enforcement. Asserted by a reflection test.
3. **`enforceSecurity()` is `final protected`.** A subclass cannot weaken or
   bypass the check itself. Also asserted by reflection.
4. **Enforcement happens once, before the action path is chosen.** Both the read
   path and the action path go through the same single call, so an
   `?action=save` request cannot route around the check the read path would
   have made. In `hrm.php` this was a manual re-check inside
   `hrm_dispatch_action()` — a step each hand-rolled controller had to remember.
   Two tests cover it: denial stops the read path, denial stops the action path.
5. **No checker means refusal, not rendering.** If `check_page_security()` does
   not exist (no FA session — CLI, a bare test host), the request throws
   `FrontControllerSecurityException` rather than serving an unchecked tab.

### The pre-session gap, and how it is closed

`getSecurityArea()` runs *before* `session.inc`, and the register hook fires on
`boot()`, which needs a session. So a tab contributed by another module does not
exist yet when the security area is chosen, and `?tab=<third-party>` resolves
onto the default view.

`run()` closes that: after `boot()` it re-resolves, and enforcement runs against
the *contributed tab's own* area — not the area the session was opened with.
`testAHookRegisteredThirdPartyTabIsCheckedAgainstItsOwnAreaNotTheFallback` pins
this: the area checked is `SA_ksf_FA_RECRUITVIEW`, not `SA_ksf_FA_HRMVIEW`.

`dispatchAction()` is deliberately **overridable** (a module may pre-handle a
verb before its controller sees it) — safe to do so because enforcement has
already completed by then. A test overrides it and asserts the check still ran.

---

## 6. How third-party tabs register

Unchanged from `AbstractAppShell`. The base calls `$this->appShell->boot()`,
which fires:

```php
hook_invoke_all('hrm_register_tabs', $data);
```

A responder pushes a `TabRegistration` (typically via `TabRegistrationTrait`):

```php
public function respondToHrmRegisterTabs(&$data)
{
    $data['tabs'][] = new TabRegistration(
        'recruit',
        'Recruitment',
        'SA_ksf_FA_RECRUITVIEW',
        \Vendor\MyModule\RecruitmentTabController::class
    );
}
```

It then flows through the base untouched: re-resolved, rendered in the menu,
checked against `SA_ksf_FA_RECRUITVIEW`, and dispatched. Three tests cover
dispatch, area enforcement, and refusal when the area is not granted.

A third-party tab should still declare its own `security` — that is what gets
checked. The fallback exists for tabs that do not, and for the pre-session
resolution only.

---

## 7. Public API

| Method | Notes |
|---|---|
| `getAppShell(): AbstractAppShell` | |
| `getSecurityArea(): string` | Call before `session.inc` |
| `getResolvedTab(): string` | Tab key from the last resolution |
| `resolveTabKey(?array $get = null): string` | `tab`, then `view` alias, then default |
| `resolvePagePosition(?array $get = null): int` | Pager position, `>= 1` |
| `resolveAction(?array $request = null): string` | `''` when absent |
| `normaliseRequest(?string $tabKey = null): void` | Writes `$_GET[tab]`, unsets the alias |
| `run(): void` | **`final`** |

## 8. Overridable seams

| Seam | Purpose |
|---|---|
| `getPageTitle(): string` | FA page title |
| `getPageJs(TabRegistration $tab): string` | Extra `<head>` JavaScript |
| `dispatchAction(TabRegistration $tab, string $action): void` | Pre-handle an action verb (post-enforcement) |
| `renderUnavailable(): void` | Message when a verb has nowhere to go |
| `openPage()` / `closePage()` | Page framing |
| `loadUiIncludes()` | `includes/ui.inc` bootstrap |

Not overridable: `run()`, `enforceSecurity()`, `resolveTabKey()`,
`resolveAction()`, `resolvePagePosition()`, `normaliseRequest()`.

## 9. Deliberately left to subclasses

- **Page title and `<head>` JS** — module-specific (HRM loads the date picker).
- **Pre-handling an action verb** — a module may want to intercept before its
  tab controller. Safe: enforcement already ran.
- **The unavailable-action message.**
- **Whether a verb requires POST, and CSRF.** The front controller reads the
  verb from `$_REQUEST` so a GET pre-load and a POST mutation read the same;
  deciding which verbs are mutations is the tab controller's contract, not the
  router's. `?action=edit&id=7` is a legitimate GET pre-load today.

## 10. New exceptions

- `FrontControllerSecurityException extends RuntimeException` — no area
  resolvable, or no way to check access.
- `FrontControllerRoutingException extends RuntimeException` — the shell has no
  tabs at all. Rendering an empty shell would be a silent fail-open.

Both are `final` and follow the house pattern of
`Scheduler/JobSkippedException`.

---

## 11. Verification

| Check | Result |
|---|---|
| `php -l` on all 5 new files (host PHP 8.1) | clean |
| `php -l` on all 5 new files (**real PHP 7.4.33**, `localhost/ksf-fa:php7.4`) | clean |
| PHP 8 syntax scan (`match`, `?->`, `readonly`, union types, ctor promotion, `#[`) | none found |
| Full suite before | `OK (334 tests, 716 assertions)` |
| Full suite after | `OK (377 tests, 774 assertions)` — **+43, none broken** |
| `git diff` | byte-identical to the pre-existing baseline |
| `git status --porcelain` | 5 untracked new files + 5 doc files already dirty before this work |

Tests cover: tab resolution, alias handling, `page`-is-never-a-selector, pager
passthrough and clamping, action resolution, action fall-through, security area
selection, denial on both paths, refusal with no checker, constructor rejection,
finality of `run()`/`enforceSecurity()`, overridable-seam ordering, and
hook-registered third-party tab dispatch / area enforcement / refusal.

---

## 12. Follow-ups for the human (not done here)

1. **`APP_TAB_ARCHITECTURE.md` was NOT updated.** The brief asked for it, but
   also required `git diff` to be empty. The two are mutually exclusive, and the
   additive-only constraint won. Note that file is **hardlinked 92 ways**
   (`stat -c%h` = 92) across the module repos and follows an
   "intentional-write ritual" (Appendix A: `chmod 644` → edit → `chmod 444` →
   `ln -f` per repo) — so editing it is a cross-repo operation, not a local one.
   Section 11 of that doc is where the new row belongs, alongside
   `AbstractAppShell` / `AbstractTabController`.
2. **Version.** Marked `@since 1.1.0` (additive minor) against a package
   currently at v1.0.12. `composer.json` was not touched.
3. **Not published, not committed.** All five files are untracked in the working
   tree.
4. **HRM has not been migrated.** `ksf_FA_HRM/hrm.php` is unchanged. Adoption is
   a follow-up: subclass, swap the preamble, verify live. Note the one
   behavioural difference — where `hrm_resolve_view()` silently falls back, a
   shell with no tabs now raises `FrontControllerRoutingException` rather than
   rendering an empty shell.