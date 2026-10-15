# How to Add a Tab to a KSF App Shell (CRM / HRM / PM)

**Audience:** a developer adding a tab to someone else's module. You do **not**
need to have read the design docs. Everything below was read out of the source in
the dev trees on 2026-10-13; where a fact could not be verified in code it is
called out as such.

**Prerequisites:** your module is an installed + activated FA extension, you have
`hooks.php` with a `hooks_<package>` class, and you know your module's own FA
security areas.

---

## 1. The 30-second version

Every "app" module (CRM, HRM, Project Management) has one entry-point page and a
list of tabs on it. To add your tab to another module's app you do **three**
things:

1. **Declare a security area** in *your own* `install_access()`.
2. **Expose one method on your `hooks` class**, named exactly
   `<appId>_register_tabs`, that pushes a `TabRegistration` definition array into
   `$data['tabs']`.
3. **Supply a tab controller class** — a subclass of
   `ksfraser\FrontAccounting\Common\App\AbstractTabController` — that does your
   data access and describes its fields.

You do **not** touch the host module at all.

---

## 2. The verified app ids and hook names

The hook name is **derived**, never configured independently:
`AbstractAppShell::getRegisterHook()` returns `$this->appId . '_register_tabs'`
(`ksf_FA_Common/src/App/AbstractAppShell.php:91-94`), and `boot()` fires
`hook_invoke_all()` on exactly that string (`AbstractAppShell.php:163-193`).

The `appId` is the first argument each shell passes to `parent::__construct()`.
Read them off the source — do not assume:

| App | Shell class | Source | `appId` | Register hook | URL selector | Default tab | Base URL |
|---|---|---|---|---|---|---|---|
| HRM | `ksfraser\FrontAccounting\HRM\App\HrmAppShell` | `ksf_FA_HRM/src/App/HrmAppShell.php:68` | `hrm` | **`hrm_register_tabs`** | `?tab=` | `employees` | `hrm.php` |
| CRM | `ksfraser\FrontAccounting\CRM\App\CrmAppShell` | `ksf_FA_CRM/src/FrontAccounting/CRM/App/CrmAppShell.php:63` | `crm` | **`crm_register_tabs`** | `?view=` | `dashboard` | `index.php` |
| PM | `ksfraser\FrontAccounting\ProjectManagement\App\PmAppShell` | `ksf_FA_ProjectManagement/src/Ksfraser/FrontAccounting/ProjectManagement/App/PmAppShell.php:46` | `pm` | **`pm_register_tabs`** | `?view=` | `dashboard` | `index.php` |

Two things to notice, because they are different and both are deliberate:

- **HRM uses `?tab=`; CRM and PM use `?view=`.** This is the shell's
  `viewParam`, i.e. what the host menu actually mints in the URL. Your tab key is
  the value under *that* parameter for that app.
- **PM has an app shell and six controller-backed tabs, but has NOT adopted the
  shared `AbstractFrontController`.** Its `index.php` is still a hand-rolled
  router (`ksf_FA_ProjectManagement/index.php`), and its vendored
  `ksfraser/ksf-fa-common` has **no** `src/App/AbstractFrontController.php`.
  `pm_register_tabs` therefore works today, but through PM's own preamble. Do
  not assume PM gets HRM's fail-closed guarantees until it adopts the base class.

Verify any app id yourself before you rely on it:

```bash
grep -n "parent::__construct(" \
  ~/Documents/ksf_FA_HRM/src/App/HrmAppShell.php \
  ~/Documents/ksf_FA_CRM/src/FrontAccounting/CRM/App/CrmAppShell.php \
  ~/Documents/ksf_FA_ProjectManagement/src/Ksfraser/FrontAccounting/ProjectManagement/App/PmAppShell.php
```

---

## 3. What an adopting module provides

If the module *you* are editing is itself an app host (rather than a
contributor), it provides:

| Piece | What it is |
|---|---|
| **App shell** | `extends AbstractAppShell`, calls `parent::__construct($appId, $baseUrl, $viewParam, $defaultView)`, then registers its core tabs **in the constructor**. |
| **Core tabs** | `TabRegistration` values keyed by tab key, each with `label`, `security` and a `controller_class`. Registered at *construction* time, not in `boot()`, so `$page_security` can be resolved before `session.inc`. |
| **Per-tab controllers** | `extends AbstractTabController` (or a filtered subclass). Implement the data-access contract; the base owns the page flow. |
| **Front page** | One file at the module root (`hrm.php`, `index.php`). Two-phase: `getSecurityArea()` → `$page_security` → `session.inc` → `add_access_extensions()` → `run()`. |

The front controller base class
(`ksfraser\FrontAccounting\Common\App\AbstractFrontController`) is what makes
that last row short. It was added in `ksfraser/ksf-fa-common` **v1.0.13** and
fixed in **v1.0.14** (which seeded `$path_to_root` inside `loadUiIncludes()`).
**HRM and CRM both adopt it. PM does not.** Do not write against a
`ksf-fa-common` older than v1.0.13 — `AbstractFrontController` will not exist.

---

## 4. Complete, copy-pasteable example

This registers a **Timesheets** tab into the HRM app from
`ksf_FA_Timesheets`. Two files.

### 4a. `ksf_FA_Timesheets/hooks.php`

Note the area is declared **in your own module's `install_access()`**. FA
rewrites the integer codes at runtime, so only the `SA_*` *string* is a stable
contract (`AGENTS_ARCH.md` §8) — never write the integer anywhere else.

```php
<?php
/**
 * ksf_FA_Timesheets Module Hooks for FrontAccounting
 *
 * @package ksf_FA_Timesheets
 * @version   1.0.0
 */

define('SS_ksf_FA_Timesheets', 118 << 8);

class hooks_ksf_FA_Timesheets extends hooks
{
    var $module_name = 'ksf_FA_Timesheets';
    var $version     = '1.0.0';

    /**
     * Declare the security areas this module owns.
     *
     * SA_TIMESHEETS is the area the HRM tab below is gated on. It MUST come from
     * HERE, not from HRM's install_access(): the host only ever checks the
     * string the contributor supplies, and FA's access model has no notion of
     * "borrowing" another extension's area.
     *
     * @return array{0: array<string, array{0: int, 1: string}>, 1: array<int, string>}
     */
    public function install_access()
    {
        $security_sections[SS_ksf_FA_Timesheets] = _("Timesheets");

        $security_areas['SA_TIMESHEETS'] = array(
            SS_ksf_FA_Timesheets | 1, _("View Timesheets")
        );
        $security_areas['SA_TIMESHEETS_MANAGE'] = array(
            SS_ksf_FA_Timesheets | 2, _("Manage Timesheets")
        );

        return array($security_areas, $security_sections);
    }

    /**
     * Contribute a tab to the HRM application shell.
     *
     * The method name IS the hook name. AbstractAppShell::boot() calls
     * hook_invoke_all('hrm_register_tabs', $data) and merges everything pushed
     * into $data['tabs'] into HRM's menu and dispatch. The `&$data` by-reference
     * first parameter is REQUIRED — FA's hook_invoke_all() passes $data by
     * value, so without the reference nothing you append is visible to the
     * caller. $opts is unused but is part of the FA hook signature.
     *
     * @param array $data Hook payload; append to $data['tabs'].
     * @param mixed $opts Unused.
     *
     * @return void
     */
    public function hrm_register_tabs(&$data, $opts = null)
    {
        $data['tabs'][] = array(
            // Unique across the whole HRM app. This is the value under ?tab=.
            'key'              => 'timesheets',

            // Already translated: the shell renders the label through _().
            'label'            => _('Timesheets'),

            // Your own area from install_access() above. This is what gets
            // checked -- not HRM's SA_ksf_FA_HRMVIEW.
            'security'         => 'SA_TIMESHEETS',

            // FQCN of a class extending AbstractTabController. Autoloaded from
            // YOUR module's composer autoloader.
            'controller_class' => \ksfraser\FrontAccounting\Timesheets\Controller\TimesheetsTabController::class,

            // Lower sorts earlier. HRM's own core tabs use 0,10,20,...; 40 puts
            // this after the catalogue tabs. Defaults are 50 / 0.
            'priority'         => 40,
            'order'            => 0,
        );
    }
}
```

### 4b. The tab controller

`AbstractTabController` (package `ksf-fa-common`) owns the page flow. You
implement eight methods.

```php
<?php

declare(strict_types=1);

namespace ksfraser\FrontAccounting\Timesheets\Controller;

use ksfraser\FrontAccounting\Common\App\AbstractTabController;
use ksfraser\FrontAccounting\Timesheets\Service\TimesheetService;

class TimesheetsTabController extends AbstractTabController
{
    /** @var TimesheetService */
    private $service;

    /**
     * @param \ksfraser\FrontAccounting\Common\App\TabContext|null $context
     *        Request state. Leave the parent signature alone.
     * @param array<string, mixed> $options { per_page?: int, order_by?: string }
     */
    public function __construct($context = null, array $options = [])
    {
        parent::__construct($context, $options);
        $this->service = new TimesheetService();
    }

    /** Primary key column name. @return string */
    protected function getPkField(): string
    {
        return 'timesheet_id';
    }

    /**
     * FR-006-007 field metadata.
     *
     * fields[].showInTable  -> summary table columns
     * fields[].showInForm   -> entry form controls
     * fields[].type         -> 'text' | 'checkbox' | 'date' | 'numeric' | ...
     * fk_ddls               -> field name => [value => 'Label'] select options
     *
     * @return array<string, mixed>
     */
    protected function getFieldMetadata(): array
    {
        return [
            'entity'       => 'Timesheet',
            'table'        => '0_hrm_timesheets',
            'labelPlural'  => 'Timesheets',
            'pk'           => 'timesheet_id',
            'fields'       => [
                'reference' => ['label' => 'Reference', 'showInTable' => true,  'showInForm' => true],
                'employee'  => ['label' => 'Employee',  'showInTable' => true,  'showInForm' => true],
                'work_date' => ['label' => 'Date',      'showInTable' => true,  'showInForm' => true, 'type' => 'date'],
                'hours'     => ['label' => 'Hours',     'showInTable' => true,  'showInForm' => true, 'type' => 'numeric', 'default' => 0],
                'approved'  => ['label' => 'Approved',  'showInTable' => true,  'showInForm' => true, 'type' => 'checkbox', 'default' => 0],
            ],
            'fk_ddls'      => [],
        ];
    }

    /**
     * Paged rows for the summary table.
     *
     * @param int $page 1-based page number (from ?page=)
     * @param int $perPage
     * @return array<int, array<string, mixed>>
     */
    protected function listRows(int $page, int $perPage): array
    {
        return $this->service->listPaged($page, $perPage);
    }

    /** Total record count for the pager. @return int */
    protected function countRows(): int
    {
        return $this->service->count();
    }

    /**
     * Load one record to pre-fill the update form.
     *
     * @param string $pk
     * @return array<string, mixed>|null null when not found
     */
    protected function findRecord(string $pk): ?array
    {
        return $this->service->find($pk);
    }

    /** Insert. @return string|int new pk */
    protected function createRecord(array $data)
    {
        return $this->service->create($data);
    }

    /** Update. */
    protected function updateRecord(string $pk, array $data): void
    {
        $this->service->update($pk, $data);
    }

    /** Delete. */
    protected function deleteRecord(string $pk): void
    {
        $this->service->delete($pk);
    }
}
```

### 4c. The `TabRegistrationTrait` alternative

If you prefer the trait (it additionally records your registration in the shared
`ExtensionRegistry` under `hrm_tabs`):

```php
use ksfraser\FrontAccounting\Common\Traits\TabRegistrationTrait;

class hooks_ksf_FA_Timesheets extends hooks
{
    use TabRegistrationTrait;

    public function hrm_register_tabs(&$data, $opts = null)
    {
        $this->respondToAppRegister(
            $data,
            'hrm',                                    // appId
            'timesheets',                             // key
            _('Timesheets'),                          // label
            'SA_TIMESHEETS',                          // security area
            \ksfraser\FrontAccounting\Timesheets\Controller\TimesheetsTabController::class,
            40,                                       // priority
            0                                         // order
        );
    }
}
```

**Watch out:** the docblock example inside the shipped
`TabRegistrationTrait.php` shows a call to `$this->registerTab('teams', …)`.
**No such method exists on the trait.** The real methods are
`registerTabWithApp()` and `respondToAppRegister()`. The docblock is stale; use
`respondToAppRegister()`.

### 4d. Registration-field reference

| Field | Key in the array | Required | Notes |
|---|---|---|---|
| Tab key | `key` | yes | Unique across the app. The `?tab=` (HRM) / `?view=` (CRM, PM) value. |
| Label | `label` | yes | Already translated. |
| Security | `security` | **yes** | An `SA_*` area from **your** `install_access()`. This is what is checked after boot. |
| Controller | `controller_class` | one of | FQCN of an `AbstractTabController` subclass. |
| Legacy page | `page_file` | one of | Absolute path to a **fragment**. It is `include`d inside the shell's already-open `page()`/`end_page()`, so it must **not** call `page()`/`end_page()` itself and must **not** redefine `$path_to_root`. |
| Priority | `priority` | no | Int, lower = earlier. Default `50`. |
| Order | `order` | no | Int, tie-break within a priority. Default `0`. |

`TabRegistration::fromArray()` also accepts camelCase aliases
(`controllerClass`, `pageFile`, `faType`). Snake_case is the documented form.

---

## 5. Filter, paging and form — how they flow through the tab

You do not wire any of this up. It is inherited.

**Rendering (GET).** `AbstractTabController::run()`:

```
handlePost()
  → start_table / start_form  (renderStart)
    → MasterSummaryTable     (renderSummaryTable)
    → entry form             (renderEntryForm)
      → FormFooter
  → end_table / end_form    (renderEnd)
```

- **Paging.** `renderSummaryTable()` calls `page()` → `$this->context->getPage()`,
  falling back to `$_GET['page']`, clamped to `>= 1`. Rows come from your
  `listRows($page, $perPage)`, count from `countRows()`. Default 10 per page;
  override with the `per_page` constructor option or the `$perPage` property.
- **Pager links keep the tab.** `MasterSummaryTable` copies the `$_GET` keys
  named in `preserve_params` **verbatim** onto the links it builds.
  `AbstractTabController::preserveParams()` returns `['view']`. **If your host
  app is HRM (`?tab=`) you must override it:**
  ```php
  protected function preserveParams(): array
  {
      return ['tab'];   // so links read ?page=3&tab=leave
  }
  ```
  HRM's own controllers do exactly this. CRM and PM keep the default because
  they already use `?view=`.
- **`tab` vs `page` never collide.** The front controller resolves the tab from
  the tab parameter and *never* consults the pager parameter. A tab literally
  keyed `"3"` is still reachable. This is pinned by a test in the package.
- **The form is always on the page.** There is no "Add XYZ" link. Blank for add;
  `Edit` on a summary row pre-loads the form and flips the footer from `Save` to
  `Update`.
- **Row actions** are `<pk>`-suffixed submit buttons: `edit_<pk>` and
  `delete_<pk>` (`handlePost()`), plus `<pk>_submit` and `<pk>_cancel` for the
  footer. `handlePost()` reads `$_POST` **directly** for these — it does not go
  through `TabContext`.
- **Checkbox semantics.** `collectFormValues()` treats an absent `checkbox`
  field as `0`, because an unchecked HTML checkbox is simply missing from
  `$_POST`. Do not "fix" that by defaulting to `1`.
- **Post-success redirect (PRG).** `redirectAfterPost()` `header('Location: ' …)`
  to `formAction()`, which is `$_SERVER['REQUEST_URI']` — so the tab and any
  filters survive the POST. If `formAction()` is empty it falls back to
  `TabContext::redirectTarget()`, which uses `PHP_SELF` and **drops the query
  string** — that is the known footgun; see `HRM_Controller_Consolidation.md` §5
  for the variant HRM builds from `$_GET` instead.

### Adding a filter bar

`AbstractTabController` has **no slot for a filter bar** — verified, it is not in
the class. HRM solved this with a local intermediate subclass
(`ksf_FA_HRM/src/Controller/FilteredTabController.php`) that inserts a filter
section between the opening `<form>` and the summary table and re-renders the
control grid with FA's `ui_input.inc` row helpers instead of `FieldForm`'s
Bootstrap markup. The shared package was deliberately not forked.

If you need a filter bar, do the same: subclass locally. Read
`FilteredTabController.php` first — it is ~250 lines and already solves the
form-scoping problem (all filter controls inside the one form).

---

## 6. What the base class guarantees — and what it does not

If the host app has adopted `AbstractFrontController` (HRM: yes, CRM: yes,
**PM: no**), these guarantees hold. They are implemented in
`ksf_FA_Common/src/App/AbstractFrontController.php` and covered by tests.

### Guarantees (host's responsibility, already done for you)

1. **An empty fallback security area is impossible.** `$fallbackSecurity` is a
   *required positional* constructor argument and `trim() === ''` throws
   `FrontControllerSecurityException` (lines 142-147).
2. **`run()` is `final`.** A subclass cannot replace or reorder the dispatch
   sequence (line 372).
3. **`enforceSecurity()` is `final protected`.** A subclass cannot weaken or
   bypass the check itself (line 455).
4. **One enforcement point, before the action path is chosen** (line 401).
   `?action=save` cannot route around the check the read path would have made.
   HRM previously had to remember this by hand in `hrm_dispatch_action()`.
5. **No checker means refusal, not rendering.** If `check_page_security()` does
   not exist, the request throws rather than serving an unchecked tab (lines
   461-467).
6. **A hook-registered tab is checked against its OWN area**, not the fallback.
   This closes the pre-session gap: `getSecurityArea()` runs before
   `session.inc`, and `boot()` (which fires the hook) needs a session, so your tab
   does not exist yet when the area is chosen. `run()` re-resolves after `boot()`
   and enforces against the contributed tab's own area.

### Your responsibility (the contributor module)

1. **The security area must exist and be yours.** Declare it in your own
   `install_access()`. This is not optional and not advisory — the host checks
   the string you supply, and a string FA does not know means the tab is
   unreachable (`UNDEFINED`), not merely restricted.
2. **Grant the SECTION too, not just the area.** FA drops an area code from a
   role unless the parent section is also granted
   (`includes/current_user.inc:124`). An area present in `0_security_roles.areas`
   but absent from `sections` looks perfectly correct in the database and does
   nothing. Use the Security Roles UI, not hand-written SQL, and grant the
   section first (its checkbox reveals the areas via `submit_on_change`).
3. **`label` must already be translated.** The shell passes it through `_()`.
4. **Whether a verb requires POST, and whether CSRF applies, is yours.** The
   front controller reads `action` from `$_REQUEST` so a GET pre-load and a POST
   mutation read the same. `?action=edit&id=7` as a GET is legitimate. If your
   controller offers a destructive verb, make it POST-only in your own
   `runAction()` / `handlePost()`. HRM refuses GET deletes for exactly this
   reason.
5. **Business validation and data-safety messages.** The base enforces *access*,
   not *correctness*.
6. **Your controller's autoloading.** `AbstractAppShell::createController()`
   does `class_exists($class)`, so a class your autoloader cannot find silently
   makes the tab render nothing. HRM's shell overrides `createController()` to
   pass the tab key into the controller (`new $class(null, ['view' => $key])`) so
   the controller can build links that keep its own tab selected — a third-party
   controller can use that second constructor argument too.
7. **Verify the tab is actually reachable.** `AbstractAppShell::boot()` is
   idempotent and guarded by `function_exists('hook_invoke_all')`. If your module
   is not activated, or your `hooks.php` did not load, the method is never called.

### Not guaranteed anywhere (verified absent)

- **CSRF.** Nothing in this stack emits or verifies a token on a tab action.
  FA's own `start_form()` does not add one either.
- **Record-level authorisation.** `check_page_security()` is page-level. "This
  user may open the Leave tab" is enforced; "this user may edit *this* leave
  record" is your service layer's job.
- **`page()` double-call protection.** `page()` returns early via
  `if (++$page_nested) return;` *before* `check_page_security()`. A second
  `page()` in one request skips the check entirely. The base class calls it once.

---

## 7. Verify it works locally

### 7a. Static checks (no server needed)

```bash
cd ~/Documents/ksf_FA_Timesheets

# 1. The hook method name matches the app's exactly.
grep -n "hrm_register_tabs" hooks.php

# 2. The security area is declared in THIS module.
grep -n "SA_TIMESHEETS" hooks.php

# 3. The controller class exists and extends the right base.
grep -rn "class TimesheetsTabController extends AbstractTabController" src/

# 4. The host's app id, to confirm the hook name you targeted.
grep -n "parent::__construct(" ~/Documents/ksf_FA_HRM/src/App/HrmAppShell.php

# 5. The host has the base class (v1.0.13+ only).
ls ~/Documents/ksf_FA_HRM/vendor/ksfraser/ksf-fa-common/src/App/AbstractFrontController.php
```

### 7b. Container smoke test (PHP 7.4.33, `ksfii_app-fa`)

Probe from **inside** the container so PHP version and `$path_to_root` match
production. From the host, run it as `podman exec ksfii_app-fa php -r '…'`.

```bash
podman exec -w /var/www/html/modules/ksf_FA_HRM ksfii_app-fa php -r '
require "bootstrap.php";
$shell = new \ksfraser\FrontAccounting\HRM\App\HrmAppShell();
echo "tabs=" . count($shell->getTabs()) . "\n";
echo "hook=" . $shell->getRegisterHook() . "\n";
$shell->boot();                       // fires hrm_register_tabs
echo "after boot=" . count($shell->getTabs()) . "\n";
var_dump($shell->getTab("timesheets"));  // must not be NULL
'
```

Expected before/after you activate: `tabs=12` → `tabs=13`, and
`getTab("timesheets")` non-NULL. (The exact pre-activation count moves — read it
off `registerCoreTabs()` in `HrmAppShell.php` rather than trusting a number from
this doc.)

If `getTab("timesheets")` is NULL after boot, in this order:
1. Is `ksf_FA_Timesheets` **activated** for the company you are probing
   (`company/<id>/installed_extensions.php`, key `active => true`)?
2. Did `hooks.php` load without a fatal? Check
   `journalctl -t ksfii_app-fa` — `podman logs` is empty on this pod because the
   log driver is `journald`.
3. Is the method name byte-exact? `method_exists()` is case-sensitive.

### 7c. HTTP probes

Unauthenticated `curl` is enough to prove the pre-session path. **FA serves its
login form inline with HTTP 200** when there is no session, so a 200 means "the
page bootstrapped and reached `session.inc`" — not "you can see the tab".

```bash
BASE=http://localhost:8090/modules/ksf_FA_HRM

# Baseline: the host is healthy.
curl -s -o /dev/null -w '%{http_code}\n' "$BASE/hrm.php"

# Your tab resolves (pre-session it falls back to the default tab, so compare
# against the baseline, not against "200").
curl -s "$BASE/hrm.php?tab=timesheets" | grep -c 'Timesheets'

# Pager must NOT be read as a tab selector.
curl -s -o /dev/null -w '%{http_code}\n' "$BASE/hrm.php?page=3"
```

> **Not verified end-to-end.** No authenticated browser pass was performed for
> this guide. A 200 with the login form proves only the pre-session path. An
> authenticated check must additionally grep for FA's denial string —
> `"The security settings on your account do not permit you to access this
> function"` — because a **denied page also returns HTTP 200**. See
> `ksf_Architecture_Docs/CRM_FrontController_Adoption.md` §6 for the session
> hijacking constraint that blocks replaying a live session from `curl`.

### 7d. What to look for in the browser

1. **Menu.** Your tab label appears in the host's sub-menu, at the position your
   `priority` implies.
2. **Direct URL.** `hrm.php?tab=timesheets` renders *your* tab, not the default.
3. **Pager.** Click page 2 — the URL must read `?page=2&tab=timesheets` and stay
   on your tab. If it drops back to `employees`, you forgot to override
   `preserveParams()` (see §5).
4. **Access.** Log in as a user **without** your area. Expect the denial string,
   HTTP 200 — not the tab.
5. **Round-trip.** Edit a row, save: the form re-prefills, the footer says
   `Update`, and the URL still carries `?tab=timesheets`.

---

## 8. Common failure modes

| Symptom | Cause |
|---|---|
| Tab never appears | Module not activated; or `hooks.php` fataled; or wrong hook name (case-sensitive). |
| Tab appears, click it, nothing renders | Controller class not autoloadable — `createController()` does `class_exists()` and fails silently. |
| Tab appears, access denied for everyone | Area string not in your `install_access()`, or the area is granted but its **section** is not. |
| Pager drops you back to the default tab | `preserveParams()` not overridden to `['tab']` on an HRM tab. |
| Fatal: `Call to undefined function array_selector_row()` mid-render | The host forgot `includes/ui.inc` at global scope. Both adopting hosts include it themselves and pass `['load_ui_includes' => false]`. |
| Fatal: `Call to undefined function _()` in `includes/sysnames.inc` | `includes/ui.inc` was hoisted **above** `session.inc`. Gettext loads in `session.inc`. |
| A hook-contributed tab is served under the host's area | The host has **not** adopted `AbstractFrontController` (PM today) — its hand-rolled preamble resolves the area before `boot()` and never re-checks. |
| `frontend` 500 with `Class '…\TabRegistration' not found` | The host's vendored `ksf-fa-common` predates the class, or the deployed `vendor/` is stale. `composer install --no-dev` in the deployed tree. |

---

## 9. Related documents

- `ksf_Architecture_Docs/AbstractFrontController_Design.md` — why the base class
  is shaped as it is.
- `ksf_Architecture_Docs/HRM_Controller_Consolidation.md` — the HRM migration,
  including the `page` → `tab` rename and the `loadUiIncludes()` defect.
- `ksf_Architecture_Docs/CRM_FrontController_Adoption.md` — CRM's options pinning
  and the stale-vendor 500s.
- `ksf_FA_HRM/README.md` §"Adding an HRM tab from another module" — HRM-local
  version of §4 above.
- `APP_TAB_ARCHITECTURE.md` §11 — the shared SRP inventory (hardlinked).
- `AGENTS_ARCH.md` §8–§9 — security areas, sections, `$page_security`, `ui.inc`.