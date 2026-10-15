# KSF FrontAccounting — App / Tab Plugin Architecture

> **Canonical architecture reference.** Read together with `MODULE_DIRECTORY.md`
> (ecosystem map) and `PACKAGIST.md` (our composer packages). Copies of this file
> are hardlinked into each module repo (mode `0444`). Editing follows the ritual in
> `AGENTS_APPENDIX.md`.

| Field           | Value                                                      |
|-----------------|------------------------------------------------------------|
| Status          | Current state + unified-tabs roadmap (v2.4 concept)        |
| Canonical copy  | `/home/kevin/Documents/APP_TAB_ARCHITECTURE.md`            |
| Last updated    | 2026-09-03                                                 |

---

## 1. Problem statement

FrontAccounting's item detail page and application shells are procedural. Tabs in
FA core are page-local helpers; there is **no object-oriented, module-level tab
system** where a *module* registers tabs onto a *host* page/app cleanly.

The KSF ecosystem goal:

> Drop a module in, install/activate it, and it auto-registers its tabs onto its
> parent app (items page, CRM app, HRM app, ProjectManagement app) with **no
> hard-coding in the host**.

`FA_ProductAttributes` is the first **working exemplar** (items-page host).
CRM / HRM / ProjectManagement are the intended **app hosts** (roadmap §7).

## 2. Roles in the pattern

| Role                     | Repo (composer package)                  | Namespace                                       | What it provides                                   |
|--------------------------|------------------------------------------|--------------------------------------------------|----------------------------------------------------|
| Shared plugin layer      | `ksf_FA_Common` (`ksfraser/ksf-fa-common`) | `ksfraser\FrontAccounting\Common\Plugin`      | `PluginRegistry`, `AbstractPlugin`, `PluginInterface` (generic discover/register/activate) |
| Tab base classes         | `FA_ProductAttributes_Core` (`ksfraser/fa-product-attributes-core`) | `FrontAccounting\ProductAttributes\Plugin` | `AbstractTab`, `ProductAttributeTabInterface`, `TabRegistry` — the tab contract |
| Generic traits           | `Traits` (`ksfraser/traits`)                | `ksfraser\Traits`                                | `InlineTabRendererTrait`, `InlinePostActionsTrait` — render + POST flow |
| Exemplar host adapter    | `FA_ProductAttributes` (`ksfraser/fa-product-attributes`) | `FrontAccounting\ProductAttributes\Hooks`  | wires the tab plugins onto `items.php` via `item_display_tab_*` |
| App hosts (roadmap)      | `ksf_FA_CRM`, `ksf_FA_HRM`, `ksf_FA_ProjectManagement` | `FrontAccounting\...\Application` (`extends application`) | `install_tabs()` + `add_application()`; future `display_tab_*` hosts |

```
             HOST (page or app shell)
  items.php | crm_app.php | hrm_app.php | pm_app.php
        │  hook method (host-defined name)
        ▼
   Module hooks (FA_ProductAttributes/hooks.php) ── hard-coded registry today
        │
        ▼
   Tab plugins (AbstractTab / ProductAttributeTabInterface)
        │  renderTabContent() / handleSave() / handleDelete()
        ▼
   UI renderer class (via InlineTabRendererTrait $tabClassName)
```

## 3. Namespace & autoload map

| Prefix                          | Autoload source                    | Maps to                       |
|---------------------------------|------------------------------------|-------------------------------|
| `ksfraser\FrontAccounting\Common\`            | ksf_FA_Common composer psr-4  | `src/`                        |
| `ksfraser\Frontaccounting\HTML\`              | ksf_FA_Common composer psr-4  | `src/HTML/`                   |
| `FrontAccounting\ProductAttributes\`          | product-attributes-core psr-4 | `src/FrontAccounting/ProductAttributes/` |
| `ksfraser\Traits\`                            | traits psr-4                   | `src/ksfraser/Traits/`        |
| `KsfCommon\*` (legacy)             | **NOT autoloaded**            | aliased by `ksf_FA_Common/src/compat.php` |

**Gotcha — `KsfCommon\Plugin\*` is a legacy alias, not a real autoloaded
namespace.** `ksf_FA_Common/src/compat.php` (lines 58-69) keeps old callers working
via `class_alias()` for `AbstractPlugin`, `PluginInterface`, and `PluginRegistry`.
New code should import `ksfraser\FrontAccounting\Common\Plugin\*` directly.

## 4. Current tab flow — items.php host (implemented today)

1. Host page FA `inventory/items.php` invokes the module's hook methods via
   `hook_invoke_all()`.
2. `FA_ProductAttributes/hooks.php:195` — `item_display_tab_headers($tabs, $stockId)`
   merges the module's registered tabs into the FA tab array.
3. `FA_ProductAttributes/hooks.php:227` — `item_display_tab_content($stockId, $selectedTab)`
   renders the selected tab through the tab plugin's `renderTabContent()`.

**Registration today is a deliberate hard-coded list** of `new XTab()` objects in
`FA_ProductAttributes/hooks.php`. It is stable and covered by the 919-test suite —
**do not refactor a working module**; evolution happens via §6/§7 for new work.

### Tab plugin contract (`ProductAttributeTabInterface`)

| Method                                     | Purpose                                                         |
|--------------------------------------------|------------------------------------------------------------------|
| `getTabKey(): string`                      | Unique key in the FA tab array and `_tabs_sel` POST var |
| `getTabLabel(): string`                    | Label shown in the tab bar                                       |
| `isAvailable(string $stockId): bool`       | Show/hide for an item. `AbstractTab` default: `$stockId !== ''`  |
| `renderTabContent(string $stockId): void`  | Emit tab HTML                                                    |
| `handleSave(string $stockId, array $postData): void` | Persist on item save                                     |
| `handleDelete(string $stockId): void`      | Cleanup on item delete                                           |

## 5. Traits — where the shared logic lives

### `ksfraser\Traits` (package `ksfraser/traits`)

- **`InlineTabRendererTrait`** (since 1.4.0) — shared render flow. The using class
  MUST declare `$tabClassName` (FQCN of the UI renderer); the trait manages `$tab`.
  `renderTabContent($stockId)` ⇒ `handlePostActions()` then `createTab()->render($stockId)`
  where `createTab()` = `new $this->tabClassName($this->dao)`.
- **`InlinePostActionsTrait`** — `initUpsertClass()`, `handlePostActions($stockId)`,
  `handleSave($stockId, $postData)`, `handleDelete($stockId)`, `localise()`.
- Others: `HookQueryProviderTrait`, `CrudEventEmitterTrait`, `EntityStateTrait`,
  `EventEmitterTrait`, `EnforceDeclaredPropsTrait`, `TimestampTrait`,
  `ValidatableTrait`, `LoggerAwareTrait`.

### `ksfraser\FrontAccounting\Common\Traits` (package `ksf-fa-common`)

- `CrudOperationsTrait`, `WorkflowHooksTrait`, `CalendarRegistrationTrait`, `FlashMessageTrait`.

## 6. Discovery layer — the road to auto-registration

`PluginRegistry` (`ksfraser\FrontAccounting\Common\Plugin\PluginRegistry`):

| Method                                   | Purpose                                      |
|------------------------------------------|----------------------------------------------|
| `discover(string $directory): void`      | Scan a directory for plugin contributions    |
| `loadFile(string $file): void`           | Load a single contributed file               |
| `register(PluginInterface $plugin): void`| Register a plugin instance                   |
| `getAll(): array`                        | All registered plugins                       |
| `getActive(): array`                     | Plugins whose `isActive()` is truthy         |
| `get(string $name): ?PluginInterface`    | Lookup by name                               |
| `has(string $name): bool`                | Existence check                              |
| `clear(): void`                          | Reset registry                               |

`AbstractPlugin` supplies no-op defaults for every hook point, so concrete tabs
override only what they use.

## 7. Unified tabs concept (roadmap v2.4)

**Maturity path:** hard-coded host registry → `PluginRegistry::discover(module_dir)`
→ active plugins auto-register onto their parent app.

**Host contract:** each host page/app defines the hook method names it invokes.

- **items host:** `item_display_tab_headers` / `item_display_tab_content` (implemented).
- **app hosts (CRM / HRM / PM):** `display_tab_headers` / `display_tab_content` —
  these are NOT FA core functions; the host app must invoke them via
  `hook_invoke()`. FA core does not call them for app pages.

**Template:** `ksf_Infrastructure/doc/templates/hooks-template.php` generalizes the
pattern for a new tab module. Treat it as **scaffold to be verified**, not spec.

## 8. Known template issues (`hooks-template.php`)

Concrete copy/paste bugs found while distilling the template (see §7):

1. **`$resolvedindex` casing** is inconsistent (`$resolvedindex` vs `$resolvedIndex`)
   across the inline tab resolution logic.
2. **`SA_<MODULE>MANAGE` bit bug** — defined as `SS_ksf_FA_<ModuleName> | 1`,
   duplicating the VIEW bit; it must be `| 2`.
3. **`has_<module>_access()`** is an un-substituted placeholder.
4. **Inline OO `display_tab_headers()`/`display_tab_content()`** on the module hooks
   class are fine as hook *method names*, but the host app must actually invoke them;
   do not assume FA core provides them on app pages.

## 9. Quick picks from `PACKAGIST.md`

| Need                                                        | Package                       |
|-------------------------------------------------------------|--------------------------------|
| Tab render + POST flow (traits)                             | `ksfraser/traits`             |
| Plugin registry / extension points                          | `ksfraser/ksf-fa-common`      |
| Tab plugin base classes (items host)                        | `ksfraser/fa-product-attributes-core` |
| Item tabs adapter (the exemplar)                            | `ksfraser/fa-product-attributes` |
| DAO / cross-platform data access                            | `ksfraser/ksf-modules-dao`    |
| Entities / DTOs + repositories (business logic pattern)     | `ksfraser/staging-dto`        |
| FA function mocks (unit tests)                              | `ksfraser/famock`             |
| Validation traits/helpers (PHP 7.3+)                        | `ksfraser/validation`         |

## 10. Form container constraint for tab content (verified 2026-09-03)

**Finding:** A module tab's content is rendered **inside** the host page's single
`<form>`, so a tab cannot emit its own `<form>` without creating invalid nested
forms.

Empirical probe against the live FA container (`items.php`, Variations tab):

| Probe                                            | Result |
|--------------------------------------------------|--------|
| `<form>` count on the whole items page           | `1` (the one opened by `start_form(true)` at `items.php:559`) |
| Tab panel `#_tabs_div` a descendant of the form? | `true` |
| Action buttons resolve to which form?            | `idx:0` (the page form) |
| `gcInSameFormAsTabsSel`                           | `true` — buttons share the host form with the hidden `_tabs_sel` |
| Nested `<form>` already present inside the panel?| `0` |

`items.php:559` (`start_form(true)`) opens the form; `tabbed_content_start()` at
`items.php:611` then renders all tab panels (including the module's tab content,
emitted via `item_display_tab_content` inside the `switch` at 613-658) **inside**
that form. `end_form()` only runs at `items.php:670`, after the tab panels.

**Consequence for HTML:** `<form>` cannot be nested. Browsers ignore the inner
`<form>` start tag (or auto-close the outer one), silently dropping the inner
form's fields and breaking the outer form's data. This is exactly the class of
bug #15/#16. The Variations tab therefore must NOT render its own `<form>` tag —
enforced by the regression test `testRenderDoesNotContainFormTag`.

**Working approach (option A, adopted):** stay inside the host form and drive
tab action buttons through FA's `ajaxsubmit`/`JsHttpRequest` path — the reusable
SRP renderers `ksfraser\Frontaccounting\HTML\MasterSummaryTable`,
`FormFooter`, `TabContext` already emit `ajaxsubmit` submit buttons
+ `formnovalidate` + hidden `record_id` / `_tabs_sel`. No nested form, no broken
native submit. `handlePostActions()` reads `$_POST['_tabs_sel']` (the host form
still carries it) plus the button name.

### 10.1 Considered alternative — the `</form><form>` "second form" trick

Idea: emit an explicit `</form>` then a fresh `<form>` so the module's tab content
closes out of the host form and opens its own, producing a second (non-nested)
form.

**Verdict: rejected / fragile, do not adopt.**

- HTML5 parsing treats an *implied* `</form>` (a `</form>` without a matching open
  tag in a parser context) as a parse-structure fixup, so the exact behaviour is
  order- and browser-dependent and does not reliably produce the intended result.
- Even when it "works" as a second sibling form, the host form's fields that render
  **after** the tab panel — e.g. `hidden('fixed_asset', ...)` at `items.php:665`,
  the `br()`/`div_end()` at 660-663, and any post-tab content — would no longer be
  associated with the host form. They become orphans, silently breaking the item
  page's own form/field gating. It is safe only if the module tab is guaranteed to
  be the **last** element before `end_form()`, which is not the case here.
- It reintroduces the #15/#16 fragility this test suite exists to prevent.

If a module ever needs a **true** self-contained form with its own `action`
independent of the host form, the host must be structured so the tab panel lives
**outside** the host form (a host-side restructure of `items.php`, not a module
string-emit) — or the module should use a dedicated standalone page/endpoint
instead of a tab panel.

---

## 11. App-shell + tab-controller SRPs (implemented — `ksfraser\FrontAccounting\Common\App`)

The §7 roadmap's "app host" is now realized as two shared SRPs in `ksf-fa-common`,
separating orchestration from presentation so modules stop hand-rolling routers.

| Class                    | SRP                                 | Key API |
|--------------------------|-------------------------------------|---------|
| `AbstractAppShell`       | one app, many tabs                  | `registerTab(TabRegistration)`, `boot()`, `resolveView()`, `getSecurity()`, `renderMenu()`, `dispatch()`, `createController()` |
| `AbstractTabController`  | one tab = summary table + entry form| `run()` → `handlePost()` + `renderSummaryTable()` + `renderEntryForm()` |
| `TabRegistration`        | tab DTO                             | `(key, label, security, controllerClass, priority, order, pageFile, faType, options)` |
| `TabRegistrationTrait`   | module-side registration            | `registerTabWithApp()`, `respondToAppRegister(&$data)` |
| `AbstractFrontController` | one app = the whole request preamble | `getSecurityArea()`, `resolveTabKey()`, `resolvePagePosition()`, `resolveAction()`, `normaliseRequest()`, `run()` **(final)**, `enforceSecurity()` **(final protected)** — since 1.1.0, published v1.0.13 |
| `FrontControllerRoutingException` | no tab could be resolved at all | final, extends `RuntimeException` |
| `FrontControllerSecurityException` | no area resolvable, or no way to check access | final, extends `RuntimeException` |

**Register-with-me hook.** `AbstractAppShell::boot()` fires
`hook_invoke_all('<appId>_register_tabs', $data)`. Any module responds by merging its
`TabRegistration` (typically via `TabRegistrationTrait`), or an `AbstractPlugin` with
`getTabRegistration()`. The shell merges core tabs + responded tabs + `PluginRegistry`.

**Host page = thin router.** `index.php` resolves the view before `session.inc`, sets
`$page_security`, then `page()` → `renderMenu()` → `dispatch()` → `end_page()`.
`dispatch()` runs the controller's `run()` or includes a legacy `pageFile` fragment.

**Controller convention.** Summary is a `MasterSummaryTable` (paging, edit/delete row
actions, `preserve_params`); the entry form is always visible below it (blank for add,
DTO-pre-filled for edit; Submit flips Save↔Update). Backed by overridables:
`getFieldMetadata`, `listRows`, `countRows`, `findRecord`, `createRecord`,
`updateRecord`, `deleteRecord`, `collectFormValues`, `blankValues`, `fkOptions`.
Note: `formAction()` returns `REQUEST_URI` so `?view=` survives the POST, and
`FieldForm::renderForm()` wants the **full** metadata array (it reads `['fields']`).
`redirectAfterPost()` (PRG) also builds from `formAction()`, **not**
`TabContext::redirectTarget()` (which uses `PHP_SELF` and drops the query string,
bouncing the user to the app default tab after save/update/delete).

**Legacy `pageFile` tabs must be fragments.** `dispatch()` includes the page script
inside the shell's already-open `page()`/`end_page()`. A page file therefore must
**not** call `page()`/`end_page()` itself and must **inherit** the host's
`$path_to_root` (do not redefine it). HRM's `pages/*.php` follow this. CRM's original
`pages/*.php` are **standalone** WebERP-style pages written for direct URL access:
they redefine `$path_to_root = "../../.."` (relative to their own `pages/` dir) and
call `page()`/`end_page()` themselves, so when routed through the shell their own
relative includes resolve against the module root and the request dies mid-render
(submenu shown, no body/footer). They are being converted to `AbstractTabController`
subclasses one tab at a time (Customer Types first; e.g. `territories.php` still to do).

**Pilot:** HRM Departments (`HrmAppShell` + `DepartmentsTabController`); full CRUD
verified live. Rollout: CRM (Customer Types first), then PM.

## 11.1 `AbstractFrontController` — the host page as a base class (implemented 2026-10-13)

`AbstractAppShell` made the *tab registry* shared but left every module
hand-rolling the same request preamble around it. `AbstractFrontController`
(package `ksfraser/ksf-fa-common`, **@since 1.1.0**, first published **v1.0.13**,
`loadUiIncludes()` fixed in **v1.0.14**) extracts that preamble.

| | |
|---|---|
| Class | `ksfraser\FrontAccounting\Common\App\AbstractFrontController` (`src/App/AbstractFrontController.php`) |
| Adoptors | `ksf_FA_HRM` (`HrmFrontController`, commit `18fcba5`) and `ksf_FA_CRM` (`CrmFrontController`, commit `a81db58`) |
| **Not adopted** | `ksf_FA_ProjectManagement` — `PmAppShell` exists with six controller-backed tabs, but its `index.php` is still a hand-rolled 59-line preamble and its vendored `ksf-fa-common` has no `AbstractFrontController.php` |

**Canonical URL shape.** `tab` is the tab selector, `page` is the pager position
and is **never** consulted as a selector, `action` is the mutation verb:

```
index.php?tab=<tab>                 read
index.php?tab=<tab>&page=3          tab + pager position
index.php?tab=<tab>&action=save     mutation
```

The pager parameter is deliberately left untouched in `$_GET` so
`MasterSummaryTable::pagerUrl()` emits `?page=3&tab=leave`.

**Security is fail-closed by construction** — five guarantees, each test-pinned:

1. the constructor rejects an empty/whitespace `$fallbackSecurity`
   (`FrontControllerSecurityException`), so there is no "no area, no check" state;
2. `run()` is **`final`** — a subclass cannot reorder or omit the dispatch sequence;
3. `enforceSecurity()` is **`final protected`** — a subclass cannot weaken it;
4. enforcement runs **once, before the action path is chosen**, so `?action=save`
   cannot route around the check the read path would have made;
5. if `check_page_security()` is absent the request is **refused**, not rendered.

`enforceSecurity()` runs **after** `boot()`, so a tab contributed through
`<appId>_register_tabs` is checked against **its own** area rather than the
constructor fallback. This closes the gap that §9's "fire the register hook before
the area is resolved" rule used to leave as a manual step.

**Two-phase bootstrap is structural, not stylistic.** FA's `session.inc` (and
`includes/ui.inc`) read `$page_security` / `$path_to_root` as **globals in their
including scope**; from inside a method they are method locals and every nested
include resolves against the filesystem root and fails *silently*. So the host
page does phase A at global scope and phase B in `run()`:

```php
$fc = new CrmFrontController(new CrmAppShell(), 'SA_CRM_DASHBOARD', $path_to_root);
$page_security = $fc->getSecurityArea();          // phase A, global scope
include_once($path_to_root . "/includes/session.inc");
add_access_extensions();
$fc->run();                                        // phase B
```

**The four options that decide whether an adoption is behaviour-preserving:**

| Option | Default | Why a module usually changes it |
|---|---|---|
| `tab_param` | `'tab'` | The app's published selector. HRM keeps `tab`; CRM and PM pin `view` because their shells and link emitters mint `?view=`. |
| `alias_param` | `'view'` | The house selector is usually the *alias* once `tab_param` is pinned to something else. |
| `normalise_get` | `true` | **Set `false` when `AbstractTabController::preserveParams()` does not return `[$tabParam]`.** `MasterSummaryTable` copies those `$_GET` keys verbatim, so normalising silently strips the tab off every pager link. |
| `load_ui_includes` | `true` | `includes/ui.inc` needs `$path_to_root` in its including scope; hosts that include it at global scope switch this off. v1.0.14 seeds the variable inside `loadUiIncludes()`, which makes the default honest again. |

**Check `dispatchAction()` before adopting the base unmodified.** The base routes a
non-empty `action` verb to `$controller->runAction()` and renders "this action is
not available" when the controller has none. CRM's tab controllers never
implemented `runAction()` (they own verbs inside `run() → handlePost()`), so the
unmodified base would have made **every POST save a silent no-op** — CRM
overrode `dispatchAction()` to dispatch the tab. Overriding is safe because
`enforceSecurity()` has already run.

**Not provided by this class, by design:** CSRF tokens, record-level
authorisation, and any notion of which verbs require POST. Whether a verb is a
mutation is the tab controller's contract.

**Deployment gotcha (footer regression, 2026-09).** Modules that vendor `ksf-fa-common`
as a **symlink** to `../../../ksf_FA_Common/` (e.g. `ksf_FA_Calendar`, `ksf_FA_Logging`)
require `fa_modules/ksf_FA_Common/` to actually exist. When it is absent, the module's
generated `autoload_classmap.php` still points at `.../ksf_FA_Common/src/Traits/...`;
Composer includes the missing path and fatals mid-`<head>`, so the page renders body +
menu but **no footer**. Fix: deploy `ksf_FA_Common` into `fa_modules/`. Prefer a real
vendored copy (as HRM does) over a symlink that depends on a sibling module dir.

## Appendix A — editing this document (intentional-write ritual)

1. `chmod 644` the canonical file (this affects every hardlink — same inode).
2. Edit on disk.
3. `chmod 444` again.
4. **Re-run the hardlink step** (`ln -f`) for any repo where a git operation
   (pull/checkout/clone) replaced the file — hardlinks do **not** survive git.

## Appendix B — hardlink inventory / carrier repos

Docs hardlinked into repos: `MODULE_DIRECTORY.md`, `APP_TAB_ARCHITECTURE.md`,
`PACKAGIST.md` (+ any future `*_ARCHITECTURE.md` notes). See
`AGENTS_APPENDIX.md` §Architecture-doc hardlinks for the authoritative list and
the rule for **new** FA/WP related repos.