# Page Controller Refactor Plan — FA module `pages/*.php` → root controller + views

**Date:** 2026-10-11
**Status:** PLAN ONLY — no code changes made under this phase.
**Reference implementation:** `ksf_FA_Calendar` (`cal.php` + `src/Ksfraser/FA/Calendar/View/*`)
**Scope:** the 14 deployed pages listed in `path_to_root_Audit.md` §2 (Phase 1 fixed the
`$path_to_root` value; this plan addresses the *structure* of those pages).

---

## 1. Why

Phase 1 established the mechanical defect and its symptom. It also left two classes of
residual fault visible, and both are *structural*, not typos:

| Residual fault | Instances | Consequence |
|---|---|---|
| Undefined `$page_security` constants | EmailManager (`SA_ksf_FA_EmailManagerVIEW` / `...MANAGE`), Workflow (`SA_CUSTOMER` — wrong module's area), SPO (`SA_SUGGESTED_PO_*` — never defined) | Page 500s on `check_page_security()`, or silently grants the wrong audience |
| PHP 8 syntax on a PHP 7.4 runtime | SPO `item_trends.php`, `suggested_orders.php` (`match()` at PHP 8.0, arrow `fn()` at 7.4) | Parse error → HTTP 500, empty body |

The security fault is the expensive one. `$page_security` is a **bare string resolved at
runtime** against `$security_areas`. There is no compiler check, no linter, and no test
that catches `SA_ksf_FA_EmailManagerVIEW` when the module defines `SA_EMAILS`. Every
page repeats the bootstrap, so every page can repeat the mistake. Consolidating to one
entry point per module with **one** declared security area per module — and deriving
`VIEW`/`MANAGE` variants from it — turns a silent runtime fatal into a single,
reviewable, testable line.

## 2. Non-negotiable constraints

These come from the existing Calendar implementation and the shared architecture
decision in `AGENTS.md`. A refactor that violates them is not an improvement.

1. **PHP 7.4 syntax floor.** No `match()`, no arrow `fn()`, no `?->`, no enums, no
   constructor promotion, no named arguments. This is a hard runtime constraint —
   the container is PHP 7.4.33 and the AGENTS.md floor is 7.3.
2. **`$page_security` MUST be assigned before `includes/session.inc`** is included —
   `session.inc` reads it to authorise the request.
3. **`add_access_extensions()`** must be called after `session.inc` and before `page()`
   for any page using a module-defined security area.
4. **Native `db_*` calls only.** No PDO, no raw mysqli, in FA runtime code.
5. **Existing URLs must keep working.** Menu registrations, bookmarks and the
   `hooks.php` security-area array all reference current paths. Every retired page
   needs a thin forwarding shim, not a deletion.

## 3. Target architecture

```
modules/<module>/<controller>.php          <- ONE entry point per module
modules/<module>/src/<Ns>/Controller/     <- action dispatch, POST handling
modules/<module>/src/<Ns>/View/            <- HTML rendering, SRP classes
modules/<module>/src/<Ns>/Service/         <- use-case logic, no HTML
modules/<module>/src/<Ns>/Exception/       <- typed domain errors
modules/<module>/pages/<old>.php          <- 3-line forwarder shim (deprecated)
```

### 3.1 Controller dispatch shape

`cal.php` establishes the pattern. The root controller is pure bootstrap + dispatch;
it contains no rendering and no business logic:

```php
<?php
// 1. Resolve relative includes from THIS directory (module root, depth 2).
chdir(__DIR__);

// 2. Composer autoloader (must precede class use).
if (file_exists(__DIR__ . '/vendor/autoload.php')) {
    require_once __DIR__ . '/vendor/autoload.php';
}

// 3. Security area — declared ONCE, BEFORE session.inc reads it.
$page_security = 'SA_<MODULE>VIEW';

// 4. Bootstrap FA.
$path_to_root = "../..";                 // NOTE: module root = depth 2, NOT 3
include_once($path_to_root . '/includes/session.inc');

// 5. Extension security areas, then FA page chrome.
add_access_extensions();

$view   = isset($_GET['view'])   ? $_GET['view']   : 'list';
$action = isset($_GET['action']) ? $_GET['action'] : '';

// 6. POST handling BEFORE page() — redirect after write (PRG).
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    (new \Ns\Controller\XController())->handlePost($action, $_POST);  // ends in header()+exit
}

// 7. Render.
page(_('<Module>'));
(new \Ns\Controller\XController())->dispatch($view);   // returns a View, not HTML
end_page();
```

**Critical detail — `chdir(__DIR__)` + `$path_to_root = "../.."`.** The bug this plan
retires was caused by hand-counting depth in a file that lives at
`modules/<mod>/pages/`. At the **module root** the value is `"../.."` (depth 2). The
`chdir(__DIR__)` on line 1 also makes every *other* relative include in the module
resolve from the module directory, which removes a second class of depth bugs that the
audit could not see.

**Two separate dispatch axes, deliberately orthogonal** (this is the key design
decision, and it is what Calendar gets right):

- `?action=` — **mutation**. "save", "delete", "approve". Handled before `page()`,
  ends in a redirect. Never renders HTML.
- `?view=` — **read**. "list", "edit", "detail". Handled after `page()`, returns a View
  object whose `render()` emits HTML.

Mixing them (one `?page=` parameter that can mean either) is what produced the current
`if ($Mode=='ADD_ITEM' || $Mode=='UPDATE_ITEM')` tangle in EmailManager and Workflow.
Do not introduce a third parameter meaning.

### 3.2 View split: summary table vs. edit form

`AbstractListView` (Calendar) is the template. Two SRP axes:

**(a) By screen type.** `AbstractListView` owns everything a *summary/list table*
shares; `FormView` is standalone because an edit form shares nothing with a table.

```php
abstract class AbstractListView {
    public function __construct($repo, string $userId) { ... }   // DI, no singleton
    abstract public function render(): void;                      // echo into FA chrome

    protected function renderTableStart(array $headings): void;  // shared <thead>
    protected function renderTableEnd(): void;                    // shared </tbody>
    protected function actionLinks(int $id): string;              // Open | Edit
    protected function safeStr($v, int $maxLen = 0): string;      // escape + truncate
    protected function defaultDateRange(): array;
    protected function emptyMessage(): string;
}
```

Subclasses supply only headings, row data, and per-row links:

```php
class SuggestedOrdersListView extends AbstractListView {
    public function render(): void {
        $rows = $this->repo->findSuggested($this->filters());
        $this->renderTableStart([_('Item'), _('Supplier'), _('Qty'), _('Actions')]);
        foreach ($rows as $r) { $this->renderRow($r); }
        $this->renderTableEnd();
    }
}
```

**(b) By data shape.** Where several list views differ only by a filter or a
title, use **one parameterised class** instead of near-duplicate subclasses — exactly
what Calendar does with `MyTypeListView($module, 'call', _("Calls"))` serving calls,
meetings, tasks and reminders. Prefer this over four 95%-identical classes.

**Form views** get a constructor taking the entity (or `null` for "new") and a
`render(): string` / `render(): void`. Forms are the one place where **the view owns
its own POST handling** is acceptable (Calendar's `ReviewView::handlePost()`) —
provided the actual mutation still delegates to a service, never to the view.

### 3.3 POST handlers become services

The rule: **a service never touches `$_POST` and never emits HTML.** It receives a
plain array or a DTO and returns a result or throws.

```php
// src/<Ns>/Service/SuggestedOrderService.php
class SuggestedOrderService {
    public function __construct(SuggestedOrderRepository $repo) { ... }
    public function approve(int $id, string $userId): ApprovalResult { ... }
    public function approveMany(array $ids, string $userId): int { ... }
}

// src/<Ns>/Exception/ValidationException.php  — carries field-level errors
```

The controller is the only place that knows about superglobals:

```php
public function handlePost(string $action, array $post): void {
    switch ($action) {
        case 'approve':
            $this->service->approve((int)$post['id'], $this->userId());
            $this->redirect('?view=list&msg=approved');
            return;
        case 'save':
            $form = $this->formView->bind($post);          // returns Result
            if (!$form->isValid()) {
                $_SESSION['spo_form_errors'] = $form->errors();  // PRG-safe
                $this->redirect('?view=edit&id=' . (int)$post['id']);
            }
            $this->service->save($form->entity());
            $this->redirect('?view=list');
            return;
        default:
            $this->redirect('?view=list');
    }
}
```

Use **POST/Redirect/GET** for every write. The current pages re-POST on refresh
(`simple_page_mode(true)` + `commit_transaction()`), which is a real defect class.

### 3.4 `$page_security` declaration

This is the section the Phase 1 findings most directly motivate.

**Rule 1 — one security area per module, declared once.** Every module already defines
a security *section* (`SS_*`) and a set of areas in `hooks.php`. The refactor must
make the page-level constant match an area that actually exists.

**Rule 2 — derive, never invent.** Use the constant the module's `hooks.php` security
areas array defines. For `ksf_FA_Calendar` the correct value is
`SA_ksf_FA_CalendarVIEW`; the EmailManager pages must use whatever the module defines
(the audit notes `SA_EMAILS`), not `SA_ksf_FA_EmailManagerVIEW`.

**Rule 3 — GET vs POST may differ.** Declare a lower bar for read views and the MANAGE
bar for mutating actions, so a read-only user can see a list but a POST is rejected:

```php
$page_security = ($_SERVER['REQUEST_METHOD'] === 'POST')
    ? 'SA_<MODULE>MANAGE'    // must exist in $security_areas
    : 'SA_<MODULE>VIEW';     // must exist in $security_areas
```

**Rule 4 — a test asserts it.** Add a unit test that loads each module's `hooks.php`
security-area array and asserts every `$page_security` string used by the module's
controller is a key in it. This is the check that would have caught all three residual
faults above. It is cheap and belongs in CI alongside `check_path_to_root.py`.

### 3.5 Error visibility

FA installs a global `exception_handler()` that swallows throws, renders `end_page()`
and produces a half-drawn page with nothing in the log — exactly how the SPO parse
errors and the security fatals have been invisible. Calendar solves this at its
dispatch boundary (`cal_render_view_failure()`): catch `\Throwable`, `error_log()` it,
and render a visible error box. **Every refactored controller must keep that
try/catch boundary.** A refactor that spreads rendering into classes without this
boundary makes failures *less* diagnosable than the current code.

## 4. Representative module: `ksf_FA_SuggestedPurchaseOrder`

Chosen because it is the densest case: 5 pages, the largest POST surface after
EmailManager, read+write views, and the two pages that are still 500 for reasons
unrelated to the path bug.

| Current page | Lines | POST | Proposed target |
|---|---|---|---|
| `pages/suggested_orders.php` | 148 | 5 | `?view=orders` → `SuggestedOrdersListView` (bulk approve/convert) |
| `pages/item_trends.php` | 120 | 1 | `?view=item_trends` → `ItemTrendsListView` |
| `pages/vendor_trends.php` | 62 | 0 | `?view=vendor_trends` → `VendorTrendsListView` |
| `pages/insufficient_stock.php` | 64 | 0 | `?view=insufficient_stock` → `InsufficientStockListView` |
| `pages/configuration.php` | 92 | 9 | `?view=config` → `ConfigurationFormView` + `ConfigurationService` |

Proposed tree:

```
spo.php                                    <- controller (bootstrap + dispatch only)
pages/suggested_orders.php                 <- forwarder shim -> spo.php?view=orders
pages/item_trends.php                      <- forwarder shim -> spo.php?view=item_trends
pages/vendor_trends.php                    <- forwarder shim -> spo.php?view=vendor_trends
pages/insufficient_stock.php               <- forwarder shim -> spo.php?view=insufficient_stock
pages/configuration.php                    <- forwarder shim -> spo.php?view=config
src/Ksfraser/FA/SuggestedPurchaseOrder/
  View/AbstractListView.php                <- shared table chrome
  View/SuggestedOrdersListView.php
  View/ItemTrendsListView.php
  View/VendorTrendsListView.php
  View/InsufficientStockListView.php
  View/ConfigurationFormView.php
  Service/SuggestedOrderService.php        <- approve / approveMany / convert
  Service/ConfigurationService.php         <- read / write prefs
  Service/TrendService.php                 <- item + vendor trend reads
  Repository/SuggestedOrderRepository.php  <- native db_* only
  Exception/ValidationException.php
```

Two of the five (`vendor_trends`, `insufficient_stock`) have **zero POST handling and
few HTML lines** — they are pure list views and need only `AbstractListView` plus a
heading array. They are the cheapest proof that the pattern works before any POST is
moved.

`?action=` surface for this module: `approve`, `approve_many`, `convert`, `save_config`.

### The two blocked pages must be fixed first

`item_trends.php` and `suggested_orders.php` will **not** parse on PHP 7.4 —
`match()` (item_trends:84, suggested_orders:94) and arrow `fn()` (suggested_orders:127-138,
item_trends:37-38). Refactoring a file that does not parse cannot be verified, so the
desugaring (`match` → `switch`, `fn` → `function`) lands as a separate, first,
mechanically-verifiable commit before the structural work on this module.

## 5. Migration order

Ordered by risk ascending, so each step is independently verifiable and revertable.
Within each step the page keeps its old URL working via a shim.

**Step 0 — unblock (SuggestedPurchaseOrder only).**
Desugar PHP 8 syntax in the 2 failing pages. Verify: `php -l` clean, HTTP 200.
*Do not skip: two of the fourteen pages are unfixable until this lands.*

**Step 1 — security-area audit (all 6 modules, no refactor).**
For each page, confirm the `$page_security` string is a real key in that module's
`$security_areas`. Correct the mismatches (EmailManager ×4, Workflow ×2, SPO ×5).
Verify: HTTP status unchanged but pages become reachable for a correctly-permissioned
user. **This is a bug fix and deserves its own commit, separate from any refactor.**

**Step 2 — CI guards, before any structural change.**
Land `check_path_to_root.py` in per-repo CI (audit §6, already written and validated)
plus the new `$page_security` membership test from §3.4 Rule 4. Refactoring without
these guards means 14 pages move with no net to catch a regression.

**Step 3 — first pilot: `ksf_FA_ImportStagingProcessing_UI`.**
Smallest module by far (1 page, 37 lines, no POST, no HTML — it is a `ModuleConfig`
config form). Converts to `isu.php` + `ConfigurationFormView` in a single small step and
validates the shim, dispatch and security pattern end to end at negligible cost.

**Step 4 — read-only pages: `ksf_FA_SuggestedPurchaseOrder` (3 of 5).**
`insufficient_stock`, `vendor_trends`, `item_trends` — pure list views, no POST, minimal
HTML. Establishes `AbstractListView` reuse and the parameterised-view technique.

**Step 5 — `ksf_FA_Calendar` + `ksf_FA_CRM`.**
Calendar's `my_events.php` is already 90% redundant with the existing `MyEventsView`
reachable via `cal.php?view=my_events` — this step should mostly **delete** the page and
add a shim, which is the cheapest possible demonstration of the benefit. CRM's
`dashboard.php` (153 lines, no POST) becomes a DashboardView.

**Step 6 — `ksf_FA_SuggestedPurchaseOrder` (remaining 2).**
`suggested_orders.php` (bulk approve/convert → `SuggestedOrderService`) and
`configuration.php` (→ `ConfigurationService`). Introduces the POST/PRG pattern into a
module whose other views are already migrated.

**Step 7 — `ksf_FA_EmailManager` (4 pages, last).**
Highest value and highest risk: 4 pages, ~70 POST references, two distinct security
areas (VIEW/MANAGE), and a real service layer (`em_db.inc`, `em_routing.inc`) that the
new services should call rather than reimplement. Deferred deliberately — the first
place SRP is genuinely hard to apply, so do it once the pattern is proven six times.

**Step 8 — delete the shims.**
Only after a release cycle with no inbound links to the old `pages/*.php` paths.
Not before — removing them early breaks bookmarks and any menu entries that were not
updated.

## 6. Definition of done per page

- [ ] HTTP 200 unauthenticated (login redirect), 200 authenticated, no 500.
- [ ] `php -l` clean **on PHP 7.4**, not just on the host's PHP 8.
- [ ] `$page_security` string is a key in the module's `$security_areas`.
- [ ] Old URL still resolves (shim) and lands on the equivalent new view.
- [ ] Controller contains no `echo`/HTML beyond FA chrome.
- [ ] No service or view reads `$_POST` directly (except a view's own form binding).
- [ ] Writes use POST/Redirect/GET.
- [ ] The dispatch try/catch boundary is present (failures visible + logged).
- [ ] View and service unit tests added, per the AGENTS.md 100% coverage target.

## 7. Open questions

1. **Security-area naming.** Should the modules keep their inconsistent names
   (`SA_ksf_FA_CalendarVIEW` vs `SA_EMAILS` vs `SA_CUSTOMER`) or be normalised? The
   latter is cleaner but is a breaking change for stored user permissions. Recommend:
   normalise to `SA_<MODULE>VIEW` / `SA_<MODULE>MANAGE` and keep the old names as
   aliases in `$security_areas` for one release.
2. **Testing depth.** `AbstractListView` and services are unit-testable; FA chrome
   (`page()`, `start_table()`) is not, without a harness. Recommend testing services
   and view *data shaping* (row arrays) with rendering kept thin enough that a
   snapshot of the row array is a sufficient proxy.
3. **Shim strategy.** `pages/<old>.php` → `header('Location: ../spo.php?view=…')` is
   simplest but adds a redirect hop and needs the page to still be a valid entry point
   (i.e. keep the corrected `$path_to_root`). Alternative: `include` the controller
   directly. Recommend the include form to avoid an extra request.
4. **Scope beyond the 14.** The audit §3 S2 lists 13 more pages with the same path bug
   in *undeployed* repos (LLM, PriceBook, ProductLookup, MRP, EstatePlanning), and §3 S3
   a too-deep case in `ksf_FA_Documents`. None of this plan addresses them; they should
   be fixed before those modules are promoted, ideally by Step 2's CI check rather than
   by hand.
