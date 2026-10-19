# AGENTS_ARCH — KSF Cross-Module Architecture & Conventions

Companion to the master `AGENTS.md`. While `AGENTS.md` records specific FA
architecture **decisions** (data-dictionary/query-builder direction, PDO rule,
hook-system reference, SQL-prefix conventions, feature root-causes), this file
captures the **shared module conventions and cross-repo engineering standards**
that every ksf FA module / library follows. If something is a convention that
applies to many modules, it lives here. Repo-specific detail lives in each
repo's `_APPENDIX` / `AGENTS_APPENDIX.md`.

Read this before creating or refactoring any ksf module.

---

## 1. PHP platform floor (canonical)

- **PHP 7.3 is the compatibility floor.** Current production runs PHP 7.3
  (Fedora 30) until a web container is stood up there. Code MUST target
  PHP 7.3: no PHP 8+ features (no `match`, no named args, no nullsafe, no
  typed properties, no union/`mixed` return types in signatures — `mixed`
  only in docblocks). The FA container runtime is 7.4; standalone/core
  libraries may differ — each repo records its own floor in `_APPENDIX`.
- `declare(strict_types=1);` at the top of every PHP file.

**OPEN TENSION (2026-10, needs a ruling).** The floor above says "no typed
properties", but two modules use them and declare `>=7.4`:
`ksf_FA_Customer` (`src/Customer/Models/CustomerDTO.php`) and `ksf_FA_Payment`
(`src/Payment/Models/PaymentDTO.php`). Their composer constraints were corrected
from a false `>=7.3` to an honest `>=7.4`, and both pin
`config.platform.php = 7.4.33`. So the *code* is 7.4 while the *documented floor*
is 7.3. Either the two modules are rewritten to drop typed properties, or the
floor is raised to 7.4 to match the container runtime. Not yet decided — do not
"fix" this unilaterally in either direction.

If a module keeps typed properties, note the second trap: a typed property
without a default is **uninitialised**, and reading it throws
`Typed property ... must not be accessed before initialization`. Both DTOs above
had this bug, which made `toArray()` on a bare `new DTO()` a fatal. Every typed
property must be defaulted.

## 2. Core design principles

- **SOLID, DRY, SRP, DI, TDD** — single responsibility, dependencies injected
  (never hardcoded), test-first.
- **Polymorphism over conditionals** — prefer strategy/handler dispatch to
  long `if/else` chains.
- **Traits over inheritance** — shared cross-cutting behavior is composed via
  traits, not deep class inheritance.
- **Business logic + platform adapter split** — framework-agnostic business
  logic lives in a `*_Core` package (`ksfraser\<Package>\`); the FA adapter
  module (`ksf_FA_*` → `ksfraser\FrontAccounting\<Module>\`) is a thin wrapper.

### 2.1 Namespace convention (canonical, no variations)

**The prefix decides the namespace. Check the directory name first.**

| Module directory | Namespace | Meaning |
|---|---|---|
| `ksf_FA_<Module>` | `ksfraser\FrontAccounting\<Module>\` | an FA module |
| `ksf_<Module>` | `ksfraser\<Module>\` | standalone business logic, not attached to FA |

A module is an FA module because it is **named** `ksf_FA_*` and ships an FA
`hooks.php` — not because of what it integrates with. WooCommerce is the case
that gets this wrong, because there are two distinct things that can be built:

- `ksf_FA_Woocommerce` — a WooCommerce integration **inside FA**. It stages into
  FA's tables and lives in the FA module tree, so:
  `ksfraser\FrontAccounting\Woocommerce\`.
- `ksf_Woo*` — WooCommerce code **not attached to FA** (standalone REST clients,
  a Woo plugin, sync tooling). These are `ksf_*`, so: `ksfraser\Woocommerce\`.

The `FrontAccounting\` segment is not cosmetic. Dropping it from an FA module
makes the namespace read as though the module were part of WooCommerce itself or
shipped with WooCommerce upstream, which is exactly the impression to avoid:
these are private KSF modules. Conversely, an FA-attached Woo module **must**
keep the `FrontAccounting\` segment, because that is what marks it as living
inside FA rather than beside it.

If you are unsure which bucket a module falls in, look at the directory name and
whether it has a `hooks.php` — do not infer it from the third-party system the
module talks to.


An FA module named `ksf_FA_<Module>` uses exactly:

```
ksfraser\FrontAccounting\<Module>\
```

Lowercase vendor segment, then `FrontAccounting`, then the module name. The
PSR-4 mapping and the on-disk layout must match, e.g.

```json
"psr-4": { "ksfraser\FrontAccounting\<Module>\": "src/FrontAccounting/<Module>/" }
```

**These are NOT acceptable** — they were all found in the wild and had to be
migrated (2026-10): `ksfraser\FA\<Module>\`, `ksfraser\FA<Module>\`,
`ksfraser\FA\<Module>\`, `ksfraser\FA<Module>\`. They read as "FA" plus an
abbreviation and are not the documented vendor path.

Migrated in the 2026-10 pass, all with tests green and a
`NamespaceConventionTest` guard added to `ksf_FA_CRM`:

| Module | Was | Now |
|---|---|---|
| `ksf_FA_Customer` | `ksfraser\FACustomer\` | `ksfraser\FrontAccounting\Customer\` |
| `ksf_FA_Payment` | `ksfraser\FAPayment\` | `ksfraser\FrontAccounting\Payment\` |
| `ksf_FA_Sales` | `ksfraser\FA\Sales\` | `ksfraser\FrontAccounting\Sales\` |
| `ksf_FA_CRM` | `ksfraser\FA\CRM\` | `ksfraser\FrontAccounting\CRM\` |

Do not add a second autoloader. Put the PSR-4 mapping in the module's own
`composer.json` and let `tests/bootstrap.php` reuse Composer's loader, rather
than hand-rolling a prefix matcher (those drift from composer.json and then
resolve nothing).

### 2.2 One module owns each FA-native capability

Each FA-native aggregate gets ONE focused module that wraps FA's own routines:
`ksf_FA_Customer` (debtor + branch + contact), `ksf_FA_Payment` (customer
payment + allocation), `ksf_FA_Sales` (sales invoice). They expose the full
CRUD/search responder set (`CREATE_*`, `GET_*`, `SEARCH_*`, `UPDATE_*`), not
just the one capability they were first written for.

A capability must have exactly one owner. Two modules answering the same hook
name makes `hook_invoke_first` nondeterministic and defeats targeted
`hook_invoke`. `CREATE_CUSTOMER` was briefly duplicated into `ksf_FA_CRM` before
`ksf_FA_Customer` was found; the CRM copy was removed.

**Callers reach owners through hooks only** —
`hook_invoke('<Module>', '<RESPONDER>', $data)`. Never instantiate the owner's
classes directly: that bypasses the hook boundary, hard-couples the caller to
whichever module happens to own the capability, and (in ISU's case) could not
have worked at all because ISU's vendor tree has no autoloader for those
modules.

## 3. Standard module layout

Every ksf FA module follows this layout:

```
<module>/
├── sql/               <table>.sql  (one file per table; retag/contact-type SQL)
├── includes/          *_db.inc     ({table}_db.inc — write_{table}(), get_{table}(), delete_{table}())
├── pages/             UI pages
├── src/               business logic (PSR-4 under ksfraser\FrontAccounting\<Module>\
├── hooks.php          hooks_<module> extends hooks
├── composer.json      PSR-4 autoload
└── ProjectDocs/       Requirements.md, RTM.md, BABOK.md, UML.md
```

Each table gets a `{table}_db.inc` gateway exposing `write_{table}()` /
`get_{table}()` / `delete_{table}()` (Table Gateway pattern).

## 4. Namespace conventions

- FA platform modules: `ksfraser\FrontAccounting\<ModuleName>\` (PSR-4, maps to `src/`).
- Framework-agnostic core / business logic: `ksfraser\<Package>\`.
- Shared libraries: `ksfraser\Exceptions\`, `ksfraser\Traits\`, `ksfraser\CommonDb\`.
- SQL tables use hardcoded `0_` company prefix (FA `db_import` does NOT resolve
  `@TB_PREF@`); PHP code uses the `TB_PREF` constant.

## 5. Coding standards

- `declare(strict_types=1);` in every file.
- Naming: `InterfaceNameInterface`, `AbstractClassName`, `ServiceNameService`,
  `ValueObjectName` (immutable VOs), class `FooException`.
- DocBlocks require `@param`, `@return`, `@throws`, `@since`.
  `@UML` / `@BABOK` annotations cross-reference `doc/ProjectDocuments/{UML,BABOK}`
  requirement files (BR-*/FR-*/UC-*/UT-*/UAT-* naming).
- Version tagging: SemVer `MAJOR.MINOR.PATCH` (`git tag -a vX.Y.Z`).
- Git: feature branches `feature/*`, `fix/*`, `refactor/*`; commits
  `type(scope): description`; merge back to the default branch.
- Never track `vendor/` or `composer.lock` (each dev/consumer runs `composer install`).

## 6. Testing / TDD

- TDD red→green→refactor; **100% code coverage** target; **skipped tests = failed**.
- PHPUnit, `Tests\Unit` namespace convention; `php -l` lint before commit.
- Business logic tested standalone (in-memory SQLite / PDO stubs); FA adapter
  code tested against namespaced stubs of the FA `db_*` functions.

## 7. Development / deployment workflow

- Develop in the **devel tree** `~/Documents/<Module>`; the UAT bind point under
  `~/ksf_Infrastructure/fa_modules/<Module>` is a **deployment bind copy only** —
  never create/edit/commit code there.
- Flow: develop → test → `php -l` → commit/branch → push → merge → deploy.
- Deploy at the bind point: `git stash -u && git pull origin <branch> && git stash pop`,
  then re-run architecture-doc hardlinks (`ln -f`) if they were clobbered.
- Container deploy: run `composer install --no-dev` (a `require-dev` that pulls
  PHP 8+ transitive deps breaks a PHP 7.x container) — pin
  `config.platform.php` to the container's PHP where needed.

### Dev tree vs deploy tree — three different topologies (verified 2026-10)

`~/Documents/<Module>` (dev) and `ksf_Infrastructure/fa_modules/<Module>` (deploy)
are **not** hardlinks or a shared worktree, and they are **not always two clones**.
Do not assume — classify first:

```bash
git -C fa_modules/<Module> rev-parse --show-toplevel
```

- Returns `…/ksf_Infrastructure` → the deploy path is just a **directory inside the
  ksf_Infrastructure monorepo**, not a repo of its own. There is no clone to
  fast-forward: deploy = copy the changed files in, then commit in
  `ksf_Infrastructure`. Current examples: `ksf_FA_ImportStagingProcessing`,
  `ksf_FA_Logging`, `ksf_FA_GPG`, `ksf_FA_PurchaseOrderTracking`,
  `ksf_FA_StockReservations`, `ksf_FA_StockTurnover`,
  `ksf_FA_ManufacturerConsolidation`, `ksf_payment_destinations`,
  `ksf_fa_downloader`, `ksf_FA_Customer`.
  Their `git log` shows **ksf_Infrastructure's** history (`feat(ansible): …`),
  which makes a naive "deploy is BEHIND" check compare two unrelated histories.
- Returns `…/<Module>` → an **independent clone**. Dev and deploy each have their
  own `.git` and `HEAD`, and they diverge silently: `ksf_FA_CRM`'s deploy clone
  sat 3 commits behind with nothing surfacing it. Different inodes on every file,
  so `stat -c%i` is never a "same file?" test.
- Some modules exist **only** under `fa_modules/` (`ksf_FA_Contacts`,
  `ksf_FA_Employee`, `ksf_FA_ExpenseReport`, `ksf_FA_QuickBudget`,
  `ksf_FA_Users`) — there is no separate dev tree, so they cannot be diffed
  against one. Treat `fa_modules/` as the source of truth for those.

**Never edit the deploy tree.** An edit there is invisible to the dev repo,
uncommitted in the wrong place, and gets overwritten by the next sync. Two
mistakes of this kind happened in one session (an `index.php` reorder and a
table-prefix rename were both written to the deploy clone first). Confirm
before writing: `git -C <path> rev-parse --git-dir`.

For independent clones, deploy with a fast-forward:
`git fetch origin && git merge --ff-only origin/main`.

#### Dirty files in the deploy clone are usually NOT real work

Before a fast-forward, check whether the deploy clone's local modifications are
genuine. Per file, compare against upstream — if the deploy copy hashes equal
`git show origin/main:<file>`, the "modification" is a hand-applied **duplicate
of a commit that already exists upstream** and is safe to discard via
`git checkout -- <file>`:

```bash
[ "$(git show origin/main:$f | md5sum)" = "$(md5sum < $f)" ] && echo "duplicate of upstream"
```

That is how three deploy-clone "modifications" (`composer.json`, `phpunit.xml`,
`_init/config`) turned out to be local re-applications of already-pushed commits
`25e5a55` / `b048dde`. Blindly stashing them creates conflicts for nothing.

Beware huge dirty counts that are just runtime artifacts, not source drift —
`ksf_Calendar_UI` (2490) and `ksf_FA_API` (1682) are dominated by `vendor/` and
generated files. Inspect before concluding anything is wrong.

#### The shared .md docs are hardlinked — but NOT everywhere

- `AGENTS.md` (182 links) and `AGENTS_ARCH.md` (183 links) at
  `~/Documents/` are **hardlinked**, so editing them propagates to every linked
  repo automatically. That is the intended mechanism; prefer it over copying.
- Verify before assuming: `stat -c%h <file>`. `ksf_FA_HRM` and `ksf_FA_Calendar`
  each held a **divergent private copy** (`links=1`) of `AGENTS_ARCH.md` that was
  missing §7 "Integration-environment gotchas" entirely. Editing the shared
  inode will *not* reach them. Re-link with `ln -f` after editing (done
  2026-10-05; now 185 links, all in agreement), and check `md5sum` across repos
  when you need the docs to actually agree.
- Always confirm a copy that is about to be discarded holds nothing the shared
  version lacks. The HRM/Calendar copies did hold 15 unique lines — but the
  shared doc had deliberately *corrected* them, so they were obsolete.
- The deploy clone's `AGENTS.md` is typically a **private, un-hardlinked** file
  (`links=1`) carrying local operational notes that are not upstream. It will
  conflict on fast-forward. Preserve it: capture
  `git diff -- AGENTS.md > /tmp/x.patch`, `git checkout -- AGENTS.md`, fast-forward,
  then `git apply --3way` and resolve in favour of the *local* notes where they
  carry information upstream lacks (e.g. the pod port map). Then commit.

### Integration-environment gotchas (ksfii_app pod, verified 2026-09)

- The dev-shell runs as **root**, so `git`/file writes inside the bind-mounted
  deploy clones leave root-owned files and rewrite mode bits on
  checkout/reset. If `git pull` at a bind point refuses with "Your local
  changes to the following files would be overwritten" while `git status --short`
  is clean, suspect in order: an `assume-unchanged` flag (`git ls-files -v`
  shows lowercase `h`), a root-owned `.git/index` (makes `git update-index`
  silently a no-op), or a 186-hardlink shared doc whose content is ahead of
  HEAD. The reliable fix is aligning the clone to origin from the deploy clone:
  `git fetch && git reset --hard origin/main`. Never hand-`chmod`/`chown`
  tracked files mid-tree; re-align instead.
- The web front-end HTML-encodes `&` in query strings mid-transit:
  `$_SERVER['REQUEST_URI']` reads e.g. `...?view=contacts&amp;filter_debtor_no=1`
  while `$_GET` still parses every param correctly (so filtering works end to
  end). Round-trips are consistent — form `action=` URLs and `Location:` headers
  carry the same encoded form and are re-decoded the same way. Therefore when
  appending a query param to `formAction()`/`REQUEST_URI` for a redirect, detect
  an existing param with `strpos($url, 'name=')` instead of splitting on raw `&`.

### ComposerDependencies — self-installing vendor on activation

Each module bundles `ComposerDependencies.php` in its **root directory**. The copy
source is the per-module template
`ksf_FA_Common/src/Utils/ComposerDependencies.template.php`: **replace the
`MODULENAME` token in the namespace with your module's short name** (e.g.
`ksfraser\FrontAccounting\HRM\Utils` for ksf_FA_HRM). This solves the
chicken-and-egg problem: vendor/ doesn't exist until composer runs, but we need
to run composer to create vendor/.

```php
// hooks.php — top of file, BEFORE any other requires
require_once __DIR__ . '/ComposerDependencies.php';
\ksfraser\FrontAccounting\HRM\Utils\ComposerDependencies::ensure(__DIR__);

if (file_exists(__DIR__ . '/vendor/autoload.php')) {
    require_once __DIR__ . '/vendor/autoload.php';
}
```

`ComposerDependencies::ensure($moduleDir)` checks if `vendor/autoload.php` exists. If
not, it runs `composer install --no-interaction --prefer-dist` in `$moduleDir`. FA
calls `install_extension()` before activation completes, so vendor/ is ready when
other hook methods run.

The guard is **namespace-scoped** (sentinel constant derived from `__NAMESPACE__` +
`class_exists(__NAMESPACE__, false)`). This is deliberate:
- Each module that renames `MODULENAME` gets its own class in its own namespace —
  copies can never collide, and the legacy global constant
  `KSF_FA_COMMON_COMPOSER_DEPENDENCIES_DECLARED` is NOT set for renamed copies (so a
  properly-renamed module never suppresses a sibling).
- If a module forgets to replace `MODULENAME`, all unrenamed copies collapse onto
  the placeholder namespace; only the first to load declares the class, the rest
  short-circuit — no redeclaration fatal, no clobbering. Their hooks.php calls still
  resolve since the class takes `$moduleDir` per call.
- The package's own `ksf_FA_Common/src/Utils/ComposerDependencies.php` (in the
  `Common\Utils` namespace) uses the identical guard and may also be loaded; it
  additionally defines the legacy constant for backward compatibility with older
  copies. Do NOT copy that file into a module — copy the `.template.php`.

## 8. FA module naming / security constants

- Hooks class: `hooks_ksf_FA_<ModuleName>`.
- Security section: `define('SS_ksf_FA_<ModuleName>', N << 8);`
- Security areas: `SA_ksf_FA_<ModuleName>` / `SA_<MODULE>_<ACTION>`.
- **Security-area numbering registry (single source):** Core FA uses 1–53; KSF
  modules start at 114. Current highest: `SS_GPG = 145` (`SS_DataIntegrity = 144`).
  Next available: **146**. Always take the next unused number — never reuse.

### The `SS_*|N` you declare is NOT the code FA enforces (verified 2026-10)

`add_access_extensions()` (`includes/access_levels.inc`) **reassigns every
extension section and area code** at runtime:

```php
$scode = 100; $acode = 100; $extcode = $extid << 16;
section_code = ($scode++ << 8) | $extcode;   // per extension, per section
area_code    = ($acode++ << 8) | $extcode;   // per extension, per area
```

So `define('SS_CRM', 114 << 8)` (= 29184) and its areas `SS_CRM | 1 … | 20` are
purely a **declaration order**. At runtime on the ksfii_app pod those became
section **1205248** and areas **1205348…1205367** in `0_security_roles.areas`
(`$extid` 18, the CRM's index in the extension registry).

Rules:
- The **`SA_*` string is the only stable contract.** Never reason about, store,
  log, or compare the integer `SS_*|N`; look up `$security_areas['SA_X'][0]`
  at runtime.
- **Call `add_access_extensions()` before any `can_access()` /
  `check_page_security()` evaluation**, including in throwaway probe scripts.
  Without it the area is simply `UNDEFINED` and access is `false` — which reads
  as "this area is denied" and is a false conclusion for a granted area. This
  cost a full debugging cycle: a probe including only `session.inc` reported
  `SA_CUSTOMER_TYPE` as `UNDEFINED` / `can_access=false` while the real page
  context returned `code=1205353` / `true`.
- When a page renders despite a supposedly-denied area, check in this order:
  (1) did the script call `add_access_extensions()`; (2) is `$security_groups`
  set (legacy RBAC path — `can_access()` then ignores `$page_security` entirely
  and returns `is_admin_company() && in_array(20, $security_groups[$access])`);
  (3) `page_nested` — `page()` returns early via `if (++$page_nested) return;`,
  so a second `page()` in one request **skips the security check entirely**.
- `0_security_roles` also holds grants from an abandoned numbering scheme
  (sections `6244<<8`, `4708<<8`, `7524<<8` — nothing in the live 102–156
  range). Harmless, but do not read those rows as evidence that a module's
  areas are granted.
- Denied pages return **HTTP 200** with FA's message *"The security settings on
  your account do not permit you to access this function"*. A 200 is not proof
  of access — grep for that string when testing a security area.

### Granting an area to a role requires granting its SECTION too (verified 2026-10)

`0_security_roles` has two parallel semicolon-separated lists, `sections` and
`areas`, and an area is **inert unless its section is also granted**
(`includes/current_user.inc:124`):

```php
$role = get_security_role($this->access);
foreach ($role['areas'] as $code)
    // filter only area codes for enabled security sections
    if (in_array($code & ~0xff, $role['sections']))
        $this->role_set[] = $code;
```

`can_access()` (`includes/current_user.inc:195`) tests membership in
`$this->role_set`. So an area present in `areas` but absent from `sections` is
dropped at login and the page stays denied — **while the database row looks
exactly right.** Posting `Area*` without `Section*` produces that state and the
grant silently does nothing. Rule: whenever you grant extension areas, grant the
parent section codes in the same transaction.

Extension sections are always `(extid << 16) | (100 << 8)` because
`add_access_extensions()` resets `$scode = 100` per extension
(`includes/access_levels.inc`), e.g. extid 17 (HRM) → section `1139712`.

`admin/security_roles.php` makes this hard to do by hand:

- It is **full-state** — the handler (`admin/security_roles.php:87-99`) rebuilds
  `sections`/`areas` purely from the `$_POST` keys it receives. Any previously
  granted code whose key is absent is deleted. Save key is `addupdate`; the
  `Update view` button does not persist.
- Area inputs are only *rendered* when their section is on (line 220);
  otherwise FA emits `hidden('Area'.$code)` (line 224), so the area exists in
  the DOM but is never checkable. Grant order is therefore forced: check the
  `Section<code>` checkbox first, let the `submit_on_change` AJAX reload reveal
  the areas, then check the areas and save once with the complete set.
- Section checkboxes whose parent section is *not* granted are rendered
  `hidden()` too, so an editor can appear to lack controls that exist.
- Areas belonging to a section the role does not hold are also invisible to the
  editor. Granting access to such a module therefore removes any stray area
  codes that were in `areas` for an unheld section — expect that diff and restore
  deliberately rather than assuming a clean edit.

Do not hand-write these lists in SQL. Use the Security Roles UI with a
before/after diff of both columns (see `AGENTS_ARCH.md` §8 verification note in
`ksf_FA_Calendar/AGENTS.local.md` for the working script).

## 9. FA page security

Every direct-access module page MUST call `add_access_extensions()` (registering
its security areas) **before** `page_header()`. Missing it produces a blank
(~855-byte) page. Guard so that a user without the area is refused before any
output.

### `$page_security` is read by `page()`, so assign it before you call `page()`

FA enforces module-page security in **`includes/main.inc`, inside `page()`**:

```php
function page($title, $no_menu=false, ...) {
    global $path_to_root, $page_security, $page_nested;
    if (++$page_nested) return;            // second page() in a request SKIPS the check
    include_once($path_to_root . "/includes/page/header.inc");
    page_header(...);
    check_page_security($page_security);   // <-- reads the CURRENT global
}
```

Consequences for any module whose access area is **derived at runtime**
(app-shell tab registries, per-record or per-tab permissions):

- Set a provisional `$page_security` before `session.inc` so nothing reads an
  undefined global, then compute the real value and call `page()`. Do not call
  `page()` before the value is final.
- Any "register-with-me" extension hook (`<app>_register_tabs`) that other
  modules answer must be fired **before** the area is resolved, or contributed
  views silently fall back to the default view and inherit the default area —
  i.e. the page renders but under the wrong permission. Fixed for CRM in
  `4db5a07`; the invariant is general. **Adopting
  `AbstractFrontController` (below) makes this structural** — see §9.1.
- Never rely on the HTTP status to detect a refusal: see the 200-with-denial-body
  note in §8.

### 9.1 `AbstractFrontController` — the app host's preamble as a base class

**Package:** `ksfraser/ksf-fa-common`, `ksfraser\FrontAccounting\Common\App\AbstractFrontController`
(`src/App/AbstractFrontController.php`). `@since 1.1.0`; first published
**v1.0.13**, `loadUiIncludes()` fixed in **v1.0.14**.

| App | Adopted? | Front controller | Shell | appId | Register hook |
|---|---|---|---|---|---|
| `ksf_FA_HRM` | yes (`18fcba5`) | `HRM\App\HrmFrontController` | `HrmAppShell` | `hrm` | `hrm_register_tabs` |
| `ksf_FA_CRM` | yes (`a81db58`) | `CRM\App\CrmFrontController` | `CrmAppShell` | `crm` | `crm_register_tabs` |
| `ksf_FA_ProjectManagement` | **no** | — (hand-rolled `index.php`) | `PmAppShell` | `pm` | `pm_register_tabs` |

PM's shell exists with six controller-backed tabs; what it lacks is this base
class, so a `pm_register_tabs` contribution is currently served under
`SA_ksf_FA_ProjectManagementVIEW` rather than under the contributor's own area.

**Read the app id off the shell, never from memory.**
`AbstractAppShell::getRegisterHook()` returns `$this->appId . '_register_tabs'`,
and the `appId` is the first argument to `parent::__construct()`:

```bash
grep -n "parent::__construct(" modules/ksf_FA_*/src/**/App/*AppShell.php
```

A contributing module exposes exactly one method, named after that hook, with
**`&$data` as its first parameter** — FA's `hook_invoke_all()` passes `$data` by
value, so without the reference nothing appended is visible to the caller.

**The security guarantee, stated precisely.** `run()` is `final`,
`enforceSecurity()` is `final protected`, enforcement runs **once** before the
action path is chosen, the constructor rejects an empty fallback area, and the
absence of `check_page_security()` **refuses** rather than renders. Because
enforcement happens *after* `boot()`, a hook-registered tab is checked against
**its own** area — which is exactly the manual re-check the rule above used to
require of every hand-rolled router.

**The two-phase split is forced by FA, not by style.** `session.inc` and
`includes/ui.inc` read `$page_security` / `$path_to_root` as **globals in their
including scope**. From inside a method they are method locals, so every
`include_once($path_to_root . …)` inside them resolves against `/` and fails
**silently**. Symptoms seen live: `Call to undefined function array_selector_row()`
mid-render (no `ui_input.inc`), and a **500 on every page of the module**
(`Call to undefined function _()` in `includes/sysnames.inc`) when the include was
"tidied" above `session.inc` — because `session.inc` is what loads gettext.
Hence:

```php
$fc = new CrmFrontController(new CrmAppShell(), 'SA_CRM_DASHBOARD', $path_to_root);
$page_security = $fc->getSecurityArea();        // phase A — global scope
include_once($path_to_root . "/includes/session.inc");
add_access_extensions();
include_once($path_to_root . "/includes/ui.inc");
$fc->run();                                      // phase B
```

**Options that decide whether an adoption is behaviour-preserving** — see
`APP_TAB_ARCHITECTURE.md` §11.1 for the table. The two that bite:

- `normalise_get` must be `false` when the app's controllers do not return
  `[$tabParam]` from `preserveParams()`, because `MasterSummaryTable::pagerUrl()`
  copies those `$_GET` keys **verbatim** and normalising strips the tab off every
  pager link. CRM and PM keep `?view=`; HRM uses `?tab=`.
- Check whether the tab controllers implement `runAction()` **before** adopting
  the base unmodified. The base routes an `action` verb to `runAction()` and
  renders "not available" when it is absent. CRM's controllers never implemented
  it, so the unmodified base made every POST save a silent no-op.

**Out of scope by design:** CSRF tokens, record-level authorisation, and
POST-vs-GET verb policy. The last is the tab controller's contract — HRM makes
`action=delete` POST-only itself.

### 9.2 `ui.inc` and the register hook

The "register-with-me" hook needs a session, so it fires *after*
`session.inc`; the security area must be chosen *before* it. That ordering is the
whole reason `AbstractFrontController` splits into `getSecurityArea()` +
`run()`. Do not "simplify" it by moving `session.inc` into `run()` — it will work
syntactically and fail silently at every nested include.

### FA UI bootstrap — `ui.inc` is NOT auto-loaded

`includes/main.inc` only pulls `ui_controls.inc` (provides `start_form`,
`end_form`, `start_table`, button helpers, ...). The rest of the FA UI layer —
`ui_lists.inc` (`customer_list`, `customer_list_row`, `combo_input`,
`array_selector`, ...), `ui_input.inc`, `ui_msgs.inc`, `ui_globals.inc`,
`ui_view.inc`, `data_checks.inc` — is loaded by `includes/ui.inc`, which every
native FA page `include_once(...)`s after `session.inc`.

App-shell module entry pages (e.g. `modules/ksf_FA_CRM/index.php`) MUST do the
same:

```php
include_once($path_to_root . "/includes/session.inc");
add_access_extensions();
include_once($path_to_root . "/includes/ui.inc"); // required for ui_lists helpers
```

Without it, tab code that calls an FA-native list/DLL helper (e.g.
`customer_list_row`) silently skips rendering that control: `start_form` /
`end_table` still work because `main.inc` loaded `ui_controls.inc`, so the page
renders normally minus the helper control, with no error visible. Debugging
trap: `function_exists('start_form') === true` does NOT imply
`function_exists('customer_list_row')`.

### Tab-footer buttons — native `inputsubmit`, never `ajaxsubmit`

FA's `js/inserts.js` intercepts clicks on elements with class
`ajaxsubmit`/`editbutton`/`navibutton` and routes them through
`JsHttpRequest.request()` — an XHR that swallows navigation (POST persists, the
page never reloads; F5 shows the change). `ksf_FA_Common`'s `FormFooter`
historically emitted `class="ajaxsubmit"`, so Save/Cancel on every app-shell tab
had this symptom. Convention (decided 2026-09): tab-footer Save/Cancel buttons
use FA-native classes (`inputsubmit`) — `FormFooter` defaults `useAjax=false`;
`ajaxsubmit` is only opt-in for content that genuinely wants in-place XHR.
`MasterSummaryTable` row actions (Edit/Delete) already render native
`inputsubmit` rows (the tab controller passes `'ajax' => false`).

### 9.3 Working-directory check — MANDATORY before any file change (2026-10-11)

Run this before editing **any** file:

```bash
pwd                                              # must NOT contain fa_modules
basename "$(git rev-parse --show-toplevel)"     # which repo
git remote get-url origin                        # ksf_X (logic) or ksf_FA_X (FA wrapper)?
git branch --show-current
```

**If the path contains `fa_modules/`, STOP.** That is deployed output. Find the
dev checkout under `~/Documents` and work there.

Why, concretely: on 2026-10-11 six modules' changes were committed and pushed
from inside `fa_modules/` because this check was not performed. 32 git clones
live there, each duplicating a dev checkout. A commit made in the deploy tree
lives only in that clone and is **silently overwritten** by the next deploy
`sync`. Full reasoning: `ksf_Architecture_Docs/ADR/ADR-001`.

### 9.4 `ksf_<module>` vs `ksf_FA_<module>` — two DIFFERENT repos (2026-10-11)

They are **not** clones of each other and must never be reconciled:

- `ksfraser/ksf_<module>` — target-agnostic business logic (FA, WP, Joomla…)
- `ksfraser/ksf_FA_<module>` — FA wrapper: `hooks.php`, security areas, pages,
  controller. **Consumes** the business-logic package.

Identify the repo by **remote URL**, not directory name. Branch conventions
differ per repo and are not interchangeable — check before comparing against a
remote. Mistaking these cost an unnecessary rebase on 2026-10-11.
Full reasoning: `ksf_Architecture_Docs/ADR/ADR-002`.

## 10. FA DB layer — correct API (gotchas)

- `$db` is **raw mysqli**; FA has **no prepared statements**.
- Use `mysqli_real_escape_string($db, ...)` + `db_query`; read with
  `db_fetch_assoc` (returns `false`, not `null`, at end).
- `db_escape()` is NOT a general escaper — it HTML-decodes; do not rely on it
  for SQL parameter safety.
- For merged/`O_`-style writes the affected-row/insert-id handling differs from
  PDO; test `db_insert_id`/`sql_trail` behavior carefully.
- **Hard rule:** FA modules MUST use native `db_*` calls at runtime. PDO only in
  the standalone/portable side (tests, CLI, non-FA embedding). `DbConnectionInterface`
  (ksf-common-db) is the PDO-shaped contract; `FaDbAdapter` translates to `db_*`.
- **Never use a path repository for a published package.** `ksfraser/ksf-common-db`
  is published and correct: the v1.0.1 zipball (commit `1486557`) declares
  `ksfraser\CommonDb\`, matching its tag. An earlier version of this file claimed
  the published artifact used the old capital-K namespace and recommended a path
  repository — that claim was inferred from a class-not-found error and was never
  verified; it was **false**, and the real fault was the consumer's own code.
  Two reasons this matters: a path repo hides the true state of the package, and
  composer vendors it as a **relative symlink** (`../../../pkg/`), which arrives
  DANGLING in `fa_modules` because it resolves outside the mounted modules tree —
  that silently removed `FaDbAdapter` from a deployed module. If a package looks
  wrong, download its zipball and read it before changing dependency resolution.

## 10.1 FA lifecycle hooks -- the verified map

Verified 2026-10-08 against FA 2.4.3 source. Getting this wrong wastes a lot of
design effort, so read it before proposing a hook-based integration.

| Event | Dispatcher | Payload | Notes |
|---|---|---|---|
| Sales order / quote write | `hook_db_prewrite` / `db_postwrite` | `$cart`, `ST_SALESORDER`/`ST_SALESQUOTE` | `sales_order_db.inc:18,77,130,214` |
| Sales delivery write | `hook_db_prewrite` / `db_postwrite` | `$cart`, **`ST_CUSTDELIVERY` (13)** | `sales_delivery_db.inc:24,200`. NOT `ST_SALESDELIVERY` |
| Sales invoice write | `hook_db_prewrite` / `db_postwrite` | `$cart`, `ST_SALESINVOICE` | `sales_invoice_db.inc:28,214` |
| Credit note write | `hook_db_prewrite` / `db_postwrite` | `$cart`, `ST_CUSTCREDIT` | `sales_credit_db.inc:39,169` |
| Customer payment | `hook_db_prewrite` / `db_postwrite` | `$args`, `ST_CUSTPAYMENT` | `payment_db.inc:32,116` |
| **Void** | `hook_db_prevoid` | `($trans_type, $trans_no)` | **fires in 13 places** |
| Before every page render | `hook_invoke_all('pre_header')` | `$page_header_args` | `includes/page/header.inc:132` |
| Before every page footer | `hook_invoke_all('pre_footer')` | `$page_header_args` | `includes/page/footer.inc:17` |

### The two traps

**1. Never `exit` from `db_postwrite`.** In `write_sales_delivery()` the order is
`hook_db_postwrite` at **line 200** and `commit_transaction()` at **line 201**.
Terminating the request there leaves the delivery uncommitted. A
`hook_db_prewrite` responder also cannot abort the write -- `write_sales_delivery()`
ignores the dispatcher's return value.

**`pre_header` is the correct redirect point.** It runs at `header.inc:132`,
*after* session setup but *before* any HTML output and *before*
`header("Content-type: ...")` at line 135, so `headers_sent()` is still false. A
responder can `header('Location: ...'); exit;` there safely.

**2. Voids DO fire hooks.** `void_transaction()` (`admin/db/voiding_db.inc:17`)
switches on type and calls e.g. `void_sales_delivery()`, which fires
`hook_db_prevoid($type, $type_no)` (`sales_delivery_db.inc:225`). Also fired for
sales invoice (227), sales order (90), customer payment (128), stock transfer,
inventory adjustment, GRN, PO, supplier payment and work orders. So a
reversal/deactivation driven by `db_prevoid` is entirely feasible: it gives you
the transaction identity, and you look up what you recorded against it.

> An earlier commit message for the `allocation_read` capability asserted that
> voids fire nothing. That was wrong -- it came from grepping `void_transaction()`
> alone and missing that it delegates to the per-type void functions. Corrected
> here.

### What the cart payload gives you

`sales/includes/cart_class.inc` -- the `$cart` passed to the delivery/invoice
hooks carries `customer_id`, `Branch` (branch id), `document_date`, `reference`,
`trans_no`, **`order_no`** ("the original order number", line 57), and
`get_items()` for the lines. That is enough to prompt per serialisable line and
to link the result to both debtor and order.

## 11. Inter-module communication

- Use FA hooks via `hook_invoke` / `hook_invoke_first` / `hook_invoke_all`.
- **4-method discovery contract** a module may expose to others:
  `getModuleConstants()`, `getModuleCapabilities()`, `hasCapability(...)`,
  `respondToCapabilityRequest(...)`.
- Cross-module config read via `ksf_get_value('module.key')` / `ksf_set_value()`
  (HookQueryProviderTrait) — always pass a **variable** (hooks declare `&$data`
  by reference).
- Cross-module CRUD lifecycle via `ksf_crud_event` + `<module>_<action>_<recordType>`
  dual dispatch (CrudEventEmitterTrait); payload: `action`, `module`, `record_type`,
  `record_id`, `data`.
- Cross-module services: `ksf_log()` (ksf_FA_Common) routes to `ksf_log` hook →
  writes `company/<n>/logs/<module>_<date>.log`.

### 11.2 Request/response payload & by-reference rule (2026-10)

Verified against `ksf_FA_ImportStagingProcessing/hooks.php` + Square's
`src/Staging/IsuStagingGateway.php`. Read this before writing any new
`STAGE_*`/`CREATE_*`-style responder.

**Payload direction.** Requests in the `STAGE_*` family cross the boundary as
**DTO objects** (`ksfraser/staging-dto`, namespace `ksfraser\StagingDto\...`,
abstract base `StagingEntity`). Responders **serialize** their reply with
`StagingResult::toArray()` and tag it `_event` / `_module` / `_dto_type`. This
is the current path; the nested-array `STAGE_CUSTOMER` / `STAGE_TRANSACTION` /
`STAGE_PAYMENT` responders are the **legacy** shape and should be migrated, not
copied.

> Rule: for a `STAGE_*` request, **the caller passes a DTO instance by
> reference and the responder REPLACES `$data` with a response array.**

**The by-reference trap (this broke every `STAGE_ENTITY`/`STAGING_EXISTS` call).**
FA passes `$data` by reference. A DTO is a plain object implementing
`JsonSerializable`, **not** `ArrayAccess`, so a responder that receives a DTO
and then writes `$data['result'] = ...` fatals with
`Cannot use object of type ... as array`. It fails on the success path *and*
on every error path (`$data['error'] = ...`), and it fails whether or not the
DTO check passes first.

Correct responder shape:

```php
public function STAGE_ENTITY(&$data, $opts = null)
{
    if (!$data instanceof \ksfraser\StagingDto\StagingEntity) {
        $data = ['error' => '... requires a StagingEntity DTO instance', 'success' => false];
        return null;
    }
    $dto = $data;                      // hold the handle BEFORE overwriting
    try {
        $arr = $this->getDtoAdapter()->stageEntity($dto)->toArray();
        $data = ['success' => true, 'result' => $arr];   // replace, don't offset
        return $arr;
    } catch (\Exception $e) {
        $data = ['error' => $e->getMessage(), 'success' => false];
        return null;
    }
}
```

Corollary for **callers**: `$data` may still hold your DTO if no responder ran
(the module is inactive) or if a responder violated this rule. Always re-check
the type before reading offsets, and treat "not an array" as *no responder* —
never as success:

```php
$data = $dto;
hook_invoke('ksf_FA_ImportStagingProcessing', 'STAGE_ENTITY', $data);
if (!is_array($data)) { /* inactive module / no responder -> report honestly */ }
```

**Never infer success from a broadcast.** `hook_invoke_all()` returns nothing,
so a service that broadcasts and then records `'pushed'` asserts work that never
happened. Use `hook_invoke()` and branch on the actual reply; Square's
`refreshAllCustomers()` reported every customer as `pushed` for a
`push_customer` broadcast with no listener, and `createDebtor()` returned a
fabricated, unsaved debtor array that callers reported as a created FA row.
Both were removed.

**FAR customer creation is exclusively ISU's job (user directive, 2026-10).**
Source systems (Square, WooCommerce) MUST NOT call `CREATE_CUSTOMER` or write
FA debtors — they only `STAGE_ENTITY`/`STAGE_*` into Import Staging. Only ISU,
after human review, may create the FA debtor/branch/contact (via CRM's
`CREATE_CUSTOMER` responder, which ISU — never a source system — initiates).
Square's `refreshAllCustomers()` now stages every customer through the same
`stageCustomerForReview()` path as incremental sync and reports per-customer
staging outcomes; it never touches CRM.

### 11.4 Verify existence remotely before declaring anything dead (2026-10)

**A grep over `~/Documents` returning nothing is NOT evidence that a class does
not exist.** Three repos existed on GitHub with full implementations while having
no local checkout at all:

- `ksfraser/ksf_FA_Customer` — `CREATE_CUSTOMER` / `GET_CUSTOMER` /
  `SEARCH_CUSTOMER` / `UPDATE_CUSTOMER`
- `ksfraser/ksf_FA_Payment` — `CREATE_PAYMENT` / `GET_PAYMENT` /
  `SEARCH_PAYMENT` / `UPDATE_PAYMENT`
- `ksfraser/ksf_FA_CRM` already existed too (the adapter, not the capability)

Both were pushed on 2026-05-27 and simply never cloned into `~/Documents`.

**What this cost.** Because ISU's `createPaymentDirect()` referenced
`\ksfraser\FAPayment\Services\PaymentService` and a local grep found nothing,
that fallback was deleted as "referencing classes that do not exist in any tree".
The claim was written into a commit message and was simply false. Separately, a
duplicate `ksf_FA_Payment` and a duplicate `CREATE_CUSTOMER` in `ksf_FA_CRM`
were written from scratch before the originals were found, and only the second
duplicate was caught before it shipped.

Rules:

1. Before concluding a class/module/responder is dead or absent:
   `gh repo view ksfraser/<name>`, and `git ls-remote` to confirm it has commits.
2. Before writing a new module, check whether the repo already exists.
3. Before `git push` to a repo you did not create, **fetch and read what is
   already there.** A `git init` + force-push would have destroyed two months of
   work in `ksf_FA_Payment`.
4. If a statement about the codebase has been committed, it needs to be true.
   When a premise turns out to be wrong, add a correcting commit rather than
   leaving it — and do not silently change the conclusion's justification.

Related: several modules' `_init/config`, `_APPENDIX` and docs existed only in
the remote copy. Local absence and remote absence are different questions.

### 11.3 STAGE_ENTITY live contract (verified E2E 2026-10 on ksfii_app-fa)

End-to-end verified against the real container + `ksf_fa` DB
(`DTO -> hook responder -> 0_staging_customers` row landed, then cleanup).

- **Canonical `source` values** (ISU `InvalidSourceException` /
  `StagingService::$validSources`): `woocommerce`, `square_api`, `square_csv`,
  `paypal`, `bank`. Square's API sync MUST send `square_api` — plain `square`
  fails "Unknown source". When ISU (post-review) requests customer creation it
  passes `source=square_api` to CRM's `CREATE_CUSTOMER` responder.
- **Response array shape** (`StagingExistsResult::toArray()`): `exists`,
  `stagingId`, `status`, `message` (+ hook tags `_event`/`_module`/`_dto_type`).
  The staging reference `staging_id` is read from `result['stagingId']`, NOT
  `result['id']`.
- **`name` is required by CustomerValidator but the DTO adapter must supply it**:
  `DtoAdapter::stageCustomerDto()` composes `first + last + company`.
- **Deployed module vs dev-vendor staleness is a real 500/failure source.**
  The ksfii_app-fa module run from `fa_modules/` (container
  `/var/www/html/modules/`) uses ITS OWN `vendor/`, which drift from the dev
  tree. Instance: the deployed `ksf_ModulesDAO` was an old iteration whose
  param binder did `addslashes(null)` -> `''`, so `INSERT ... source_updated_at`
  died on MySQL strict-mode errno 1292 ("Incorrect datetime value: ''") — the
  dev copy (explode-`?` + `quoteValue(null) => 'NULL'`) was fine. When a live
  run misbehaves under the container, diff `fa_modules/.../vendor` against the
  dev tree before touching app code.
- Live CLI harness pattern (uknown to FA session bootstrap, drives `db_*`
  directly): include `config_db.php` + `includes/db/connect_db.inc`, set
  `$SysPrefs`/`$Ajax` stubs, `mysqli_connect` into `$db_connections[0]`, define
  a `check_db_error()` stub that no-ops on `mysqli_errno==0`, then load the
  module's `vendor/autoload.php` + `ksf_ModulesDAO` + `hooks.php` and call the
  responder. `authorizeAction()` returns true without a session user, so CLI is
  a safe bypass for exercising responders.

### 11.1 Inter-module dependencies (verified against FA 2.4.3, 2026-09)

**FA has no dependency mechanism.** There is no WP-style `Requires:` /
`depends:` key, no topological ordering, and no pre-activation resolver. The
control file parser `get_control_file()` (`includes/packages.inc:164`) is a
generic `Key: Value` gzip reader that will happily accept a `Requires:` line, but
**nothing in FA ever reads it** — it would be inert decoration. The *only*
pre-activation gate FA performs is `check_src_ext_version()` (FA-version
compatibility, §12).

Beware the misleading label: `admin/view/view_package.php:37` maps
`'Depends' => _('Minimal software versions')`, i.e. FA's "Depends" means
*version* constraints (`FA Version:`, `PHP Version:`), **not** other modules.
There is one in-repo attempt at the word "Depends" —
`FA_ProductAttributes_Variations/_init/config` line 13 reads
`Depends: FA_ProductAttributes_Core` — and it is doubly wrong: nothing reads it,
*and* that file is stored as plain ASCII rather than gzip, so
`get_control_file()`'s `gzopen()` cannot parse it at all. Don't treat it as a
precedent.

Activation order is therefore whatever order the sysadmin ticks the checkboxes.
Nothing enforces "activate Calendar before ProjectManagement".

**A module CAN enforce its own dependency and surface a real error to the
activation screen.** The extension page (`admin/inst_module.php:206-236`) honours
the return value of `activate_extension()`:

```php
$activated = activate_hooks($ext['package'], $comp, !$ext['active']);
if ($activated !== null)
    $result &= $activated;
if ($activated || ($activated === null))
    $exts[$i]['active'] = check_value('Active'.$i);
...
if (!$result) {
    display_error(_('Status change for some extensions failed.'));
    $Ajax->activate('ext_tbl');
} else
    display_notification(_('Current active extensions set has been saved.'));
```

So from `activate_extension($company, false)`: call `display_warning()` with your
message and `return false`. The warning renders on the activation screen, the
`active` flag is **not** flipped, `write_extensions()` still runs for the other
rows, and the summary line reads "Status change for some extensions failed."
This is exactly the pattern FA core uses for
`check_src_ext_version()` failing ("Package '%s' is incompatible with current
application version and cannot be activated."). `display_warning()` /
`display_error()` / `display_notification()` are all thin wrappers over
`trigger_error()` (`includes/ui/ui_msgs.inc`).

**How to test whether another module is active.** `get_company_extensions($id)`
(`admin/db/company_db.inc:68`) `include`s
`company/<id>/installed_extensions.php` and returns the per-company
`$installed_extensions` array. It **is** available during activation —
`admin/inst_module.php:23` includes `company_db.inc`. It is the authoritative
source, because per-company registry is what the Refresh/Update POST reads and
rewrites. Pair it with a hooks-registration probe when you need "installed and
wired up", not merely "flagged active":

```php
function activate_extension($company, $check_only = true)
{
    global $Hooks;
    $missing = [];
    foreach (array('ksf_Calendar') as $required) {   // array of module names
        $exts = get_company_extensions($company);
        $active = false;
        foreach ($exts as $ext) {
            if (($ext['package'] ?? '') === $required && !empty($ext['active'])) {
                $active = true;
                break;
            }
        }
        // $Hooks is the stronger check: it proves hooks.php was actually included.
        if (!$active || !isset($Hooks[$required])) {
            $missing[] = $required;
        }
    }
    if ($missing) {
        display_warning(sprintf(
            _('%s cannot be activated: the following module(s) must be activated first: %s'),
            $this->module_name, implode(', ', $missing)));
        return false;
    }
    if ($check_only) {
        return parent::activate_extension($company, $check_only);
    }
        // ... normal schema work (see §12.1)
    return parent::activate_extension($company, $check_only);
}
```

Schema work uses `$this->update_databases()` — a **method** on the `hooks` base
class, not a global function. Calling bare `update_databases(...)` fatals with
"Call to undefined function".

Caveats worth knowing:

- **`get_company_extensions($company)` is per-company.** A module active for
  company 1 and not company 2 passes for one and fails for the other. That is
  correct — per-company activation is the real gate.
- **The GLOBAL registry is not a substitute.** `company/installed_extensions.php`
  records availability/version; the per-company file records `active`. `ksf_FA_Calendar`
  has `StaleSchemaMessage` warning that `active => true` alone does not execute
  the installer, so also confirm the schema landed.
- **Reverse dependency is not enforceable this way.** If Calendar needs PM, and PM
  is being activated first, Calendar's `activate_extension` is not running yet.
  For mutual or reverse deps, degrade gracefully at runtime instead — see
  `ksf_FA_API`'s `CalendarController` which treats a `null` return from
  `hook_invoke_first('calendar_entries_query', ...)` as "Calendar not active" and
  returns an empty set.
- **Don't gate class availability on another module's activation.** Cross-module
  classes belong in a Packagist package (§12), not in a sibling module dir.
  `ksf_FA_Teams`/`ksf_FA_Calendar`/`ksf_FA_Mail` reference
  `dirname(__DIR__).'/ksf_FA_Common/src/Utils/ComposerDependencies.php'` — but
  `ksf_FA_Common` is **not** deployed under `fa_modules/`, so those references
  silently no-op in the deployed tree.

**Pattern to follow: a `ModuleDependencies` SRP class.** Yes — mirror the
existing `ComposerDependencies` shape. That class is
`final class ComposerDependencies` with a single static
`ensure(string $moduleDir): bool` in namespace
`ksfraser\FrontAccounting\{Module}\Utils`, invoked from `hooks.php` via
`require_once` + `::ensure(__DIR__)`, guarded by a namespace-derived constant
(`KSF_FA_COMPOSER_DEPENDENCIES_ . md5(__NAMESPACE__)`) so copies in different
namespaces can never redeclare each other. A sibling
`ModuleDependencies::assertActive(array $modules, $company): array` returning the
list of missing packages — returning rather than throwing, so the caller decides
whether to warn (activation) or degrade (runtime) — fits that house style
exactly. Place it in `ksf_FA_Common` (`src/Utils/`) as the shared implementation
and follow the template-copy convention so each module gets a namespace-renamed
copy without collisions.

Note there is currently **no** shared "is this module active?" helper anywhere
in the tree, and `ksf_FA_Common`'s `RbacGateway::isAvailable()` is misleadingly
named: it only does `function_exists('hook_invoke_all')`, which detects that FA's
hook dispatcher is loaded, **not** that `ksf_FA_RBAC` is active. Don't copy it.
`ksf_FA_Square/pages/export.php:92` is the only working runtime precedent
(`isset($Hooks[$pkg])` then `hook_invoke($pkg, 'getModuleConstants', ...)`).

### Event-Driven Architecture

**Every CRUD action that affects cross-module state MUST emit an event.** See
`ProjectDcs/Event-Driven Architecture.md` for full event taxonomy, payload schemas,
and workflow diagrams.

**Core principle:** Modules communicate through events, not direct calls. A module
emits without knowing listeners; a listener acts without knowing the emitter.

**Event naming:** `{object}_{action}` in snake_case (e.g., `stock_reserved`,
`suggested_po_created`, `po_created`).

**Standard payload:**
```php
$data = [
    'module'    => 'ksf_FA_StockReservations',
    'event'     => 'stock_reserved',
    'timestamp' => '2024-01-15 14:30:00',
    // ... event-specific fields
];
```

**Emitter rules:**
- Emit via `hook_invoke_all('{event}', $data)` after state is committed
- Include all standard fields (module, event, timestamp)
- Include relevant IDs for listeners (so_order_no, po_number, etc.)
- Emit even if no listeners (fire-and-forget)

**Listener rules:**
- Implement method named `{event_name}(array &$data)`
- Check team type is enabled before acting (for Teams module)
- Use `class_exists()` guard before using other modules' classes
- Log errors, don't throw (hook methods must be fault-tolerant)

### 11.1 Staging: what can actually be staged (learned 2026-10)

**The staging DTO package is NOT the contract. `DtoAdapter` is.**

`ksfraser/staging-dto` ships 23 DTO types, but ISU's
`ksfraser\FrontAccounting\ImportStaging\Services\DtoAdapter::stageEntity()`
dispatches on exactly **nine** and throws
`InvalidArgumentException('Unsupported DTO type: ...')` for everything else:

| Stagingable | In the package but NOT stageable |
|---|---|
| `StagingOrder` | `StagingCoupon`, `StagingDiscount`, `StagingInventory` |
| `StagingInvoice` | `StagingLineItem` (child of another DTO only) |
| `StagingPayment` | `StagingLoyaltyAccount` / `LoyaltyProgram` / `LoyaltyReward` |
| `StagingRefund` | `StagingNote`, `StagingShipment`, `StagingTax` |
| `StagingSubscription` | `StagingTransaction` (internal) |
| `StagingCustomer` | `StagingEntity` (abstract base) |
| `StagingProduct`, `StagingProductVariant` | `StagingExistsQuery` / `StagingExistsResult` (internal) |
| `StagingCategory` | |

Adding a DTO type is therefore **not** enough to make something stageable: the
adapter needs a dispatch branch, a mapper method, and somewhere to put the row.
**Check the adapter, not the package.**

**The staging entry point is the `STAGE_*` capability family only**, and its
responder requires a `StagingEntity` instance:

```php
if (!$data instanceof \ksfraser\StagingDto\StagingEntity) {
    $data = ['error' => 'stageEntity requires a StagingEntity DTO instance', 'success' => false];
    return null;
}
```

Three traps this creates. All three shipped; all are now guarded by tests.

1. **A raw array can never stage** — and because `hook_invoke_all` is
   fire-and-forget, the rejection is discarded, so the caller believes it staged
   and nothing was written. Square had seven such broadcasts, Woo had four.
2. **`hook_invoke_all` cannot substitute for `hook_invoke_first`.** Its return is
   `array_merge_recursive()` of every provider's reply, so unwrapping `[0]` picks
   whichever module is first in the registry rather than the one that answered.
   Never write an `_all` fallback for a DTO capability. (`hook_invoke_first` has
   existed since FA 2.3 — `hooks.inc` breaks on `isset($result)` — so such a
   fallback is unreachable anyway.)
3. **A duplicate DTO type is a live hazard, not a hypothetical.** If the working
   path already stages the record, "fixing" a dead event by building the obvious
   DTO creates a second row; ISU dedupes on `source` + `source_payment_id`, so
   the two race and the winner is arbitrary. Square shipped two such traps:
   `stage_payment_type` (→ `StagingPayment`) and `stage_order_lifecycle`
   (→ `StagingOrder`), both duplicating what
   `IsuStagingGateway::stageSquareOrder()` already stages. **Before implementing
   any staging event, check whether the working path already covers it.**

Square's `stage_refund` was the one dead event genuinely implementable
(`StagingRefund` is stageable) and it now works.

Money amounts: Square reports **minor units** (cents). Divide by 100 before
building a DTO — the staging layer stores decimals, as `ImportService` does.

#### Guard tests for the above

- `ksf_FA_Square/tests/Unit/NoRawArrayStagingBroadcastTest.php` — no
  `hook_invoke_all` to a DTO capability; no `stage_*`/`log_*` broadcast lacking a
  responder.
- `ksf_FA_Square/tests/Unit/NoHardcodedStagerTest.php` — no production file
  names a stager module.
- `ksf_FA_Woocommerce/tests/Unit/Staging/StagingResponseNotDiscardedTest.php` — a
  rejected staging call must report `staged => false`, never look successful.

Both Square guards strip comments with `token_get_all`. **When doing that, emit
`$token[1]` for every non-comment array token.** A stray `continue` drops all
`T_STRING` tokens, so function names never reach the regex and the guard passes
everything silently. Both guards were broken exactly that way and had to be
fixed — verify a guard fails when you reintroduce a violation.

## 12. FA module packaging

- `_init/config` file is **gzip-compressed** `Key: Value` lines (`Name:`, `Version:`,
  `Description:`), version like `2.4.3-<build>`.
- **`_init/config` is shipped in the module source and committed** (siblings keep it
  tracked, e.g. `ksf_FA_HRM` commit `chore(config): bump module version to 2.4.3-1`).
  The `Version:` FA displays and gates at activation is the installed module's
  `_init/config`; `admin/inst_module.php` refuses to activate when
  `check_src_ext_version()` (`includes/packages.inc`) finds the extension's numeric
  prefix below FA's `$src_version` (major.minor). Set `Version: 2.4.x-<build>` (e.g.
  `2.4.3-1`) and keep the module's own release in a separate field (`Build: 1.1.0`).
  Change it **in source** (`git add _init/config`) and let deployment + the FA
  *Install/Activate Extensions* UI reinstall refresh the running copy — never
  hand-edit the gzip on a live install, and never edit the version fields in
  `installed_extensions.php`.
- **The `Version:` in `_init/config` must match the major version of the FA
  platform** the module targets (e.g. `2.4.x` for FrontAccounting 2.4). FA uses
  this to gate module compatibility at install — a mismatched major (e.g. `3.x`
  vs FA `2.x`) makes the module appear incompatible. Keep the module's own
  release/build in a separate field; the FA-compat major is what FA checks.
- `install.sql` schema: hardcoded `0_` prefix; do not use `@TB_PREF@`/`{TB_PREF}`;
  probe existing tables with the bare table name.
- **Table naming: `0_ksf_<module>_<noun>`. Never `0_fa_*`.** A `0_` prefix marks
  the company prefix, so `fa` as the *second* segment collides with FA core's own
  `0_fa_*` tables and makes it unclear whether a table is ours or the platform's.
  Use the owning module's short name: `0_ksf_calendar_entries`,
  `0_ksf_crm_customer_types`, `0_ksf_gpg_settings`. (Live counterexample:
  Calendar shipped `0_fa_preference_values`, and a stale install left a
  malformed `kfa_cal_sources` — the prefix dropped entirely.)
- **Where a module keeps its settings/preferences:**
  - **One or two values** → use FA's system preferences, `get_pref()` /
    `set_pref()`. Do not create a table.
  - **A whole bunch** → a stand-alone table named `0_ksf_<module>_prefs`, created,
    pre-seeded and dropped with the module's install / activate / uninstall
    lifecycle (`install.sql`, the `activate_extension()` → `db_import()` path,
    `uninstall.sql`). Never hand-create or hand-drop it at runtime.
  - **One key/value store shared by every module** → a single
    `0_ksf_module_prefs` table keyed by `module_name` (plus `user_id` where the
    setting is per-user), not one near-identical table per module. Schema it with
    `UNIQUE(module_name, user_id, pref_key)`. Calendar's preference store was
    designed this way and is being renamed to this name.
- **Deactivation**: use `sql/uninstall.sql` (also hardcoded `0_` prefix), NOT manual
  `db_query()`. In `deactivate_extension()`, call `db_import()` with the **filename**
  (it takes a path, not a string) and the company connection array. See
  §12.1 for the corrected pattern and the `<table>_uninstall.sql` convention.
- Cross-module/owned classes live in a Packagist package, not a module dir.
  A module must never gate class availability on another module's activation.

### 12.1 Schema installer mechanics (verified against FA 2.4.3 source, 2026-09)

**Where DB work happens — `activate_`, not `install_`.** Three of the four base
hook methods in `includes/hooks.inc` are **no-op stubs that `return true`**:

| Method | Signature | Base behaviour |
|---|---|---|
| `install_extension` | `($check_only = true)` | `return true` — never touches the DB |
| `deactivate_extension` | `($company, $check_only = true)` | `return true` |
| `uninstall_extension` | `($check_only = true)` | `return true` |
| `activate_extension` | `($company, $check_only = true)` | **the only real one** |

All schema work therefore belongs in `activate_extension()` →
`update_databases()` → `db_import()`. `includes/packages.inc` only calls
`activate_hooks()` for packages whose registry `DefaultStatus` is active, and
`admin/inst_module.php` calls `activate_hooks($pkg, $comp, !$ext['active'])` for
the Refresh/Update POST. `activate_hooks($ext, $comp, $on = true)` dispatches
`$on ? activate_extension($comp, false) : deactivate_extension($comp, false)`.

**`update_databases()` gate.** This is a **method on the `hooks` base class**
(`includes/hooks.inc:31`), not a global function — call it as
`$this->update_databases(...)` from inside your hooks class. Signature
`update_databases($comp, $updates, $check_only = false)`, where `$updates` maps
`file.sql => array($table, $field = null, $properties = null)`. A file is
imported **only when `check_table($tbpref, $table, $field, $properties) != 0`**.

`check_table()` (`admin/db/maintenance_db.inc`) has a deliberately tiny
vocabulary: it issues only `SHOW TABLES LIKE` and `SHOW COLUMNS FROM`.

- table missing → non-zero → import
- table present → `0` → **skip**
- field present → `0` → **skip**
- column property mismatch → `3` → import (that's how FA re-applies
  `ALTER TABLE MODIFY` collation/type fixes)

**It has no concept of an index.** So a per-table file gated on its own table
never re-imports once the table exists, and an `ALTER` placed inside a
per-table file will **not** run on re-activation.

**Per-table file convention.** Ship one `<table>.sql` per table. Gate on
`array($this->module_name)` when a module has no natural "sentinel" table, or on
the real table when ordering matters. `FA_ProductAttributes` is the reference
implementation (36 per-table files).

**`db_import($filename, $connection, $force = true, $init = true, $protect = false, $return_errors = false)`**

- **One file per call.** It does `strpos($filename, ".gz")` then
  `file("" . $filename)` — passing an **array fatals**. Loop in PHP to import
  multiple files.
- It replaces the literal `0_` with the real company prefix.
- Allow-listed commands: `create`, `delimiter`, `alter table`, `insert`,
  `update`, `set names`, `drop table if exists`, `drop function if exists`,
  `drop trigger if exists`, `select`, `delete`. Anything else is silently skipped.
- **Ignored MySQL errors in forced mode:** `1022` (duplicate key), `1050` (table
  exists), `1060` (duplicate column), `1061` (duplicate key name), `1062`
  (duplicate key entry), `1091` (can't drop key/column). Therefore a file
  containing `ALTER TABLE ... ADD UNIQUE KEY` or `INSERT IGNORE` is **safe to
  re-run** — the only obstacle is the gate, not the SQL.

**Adding a key / constraint to an existing table.** Because `check_table()` can
only probe tables and columns, pick one of:

1. **Call `db_import()` directly** from `activate_extension()` on an idempotent
   `ALTER`-only file, with no `$updates` gate. Cleanest — `1061` is ignored, so
   it self-heals on every re-activation and needs no fake column or marker table.
2. The **column-probe idiom** — gate the upgrade file on a column that the same
   file adds. This is what `FA_ProductAttributes/sql/30_product_attribute_extras.sql`
   does: gated on missing `product_attribute_values.color`; absent on old installs
   → fires; present on fresh installs (base `02_product_attribute_values.sql`
   creates it) → skipped. Only works when the thing added **is** the thing probed,
   so it cannot express an index.
3. A sentinel/version table of your own.

**Deduplicate before adding a unique key.** `ADD UNIQUE KEY` fails with `1062`
on pre-existing duplicates. The file must `DELETE`/`UPDATE` the dupes first
(e.g. keep the lowest `id`, or coalesce into a survivor) and then add the index.
Note `1062` is on the ignore list, so a *failed* index add is **not** an error —
it fails silently and the constraint never lands. Always verify with a
deliberate duplicate insert afterwards.

**Uninstall: FA never prompts and never drops your tables.** Nothing in
`packages.inc`, `inst_module.php` or `maintenance_db.inc` asks about table
deletion; `db_import`'s `drop table if exists` is only there for files that
explicitly ask. Data is left behind on both flows. Two distinct paths:

- **Deactivate** (uncheck in "Activated for *&lt;company&gt;*"):
  `deactivate_extension($company, false)`. Module files are intact, so SQL files
  *are* readable here.
- **Uninstall** (repo-index `uninstall_package()`): `package::uninstall()` copies
  the module dir to `_back`, then **`flush_dir($targetdir, true); rmdir($targetdir);`
  deletes the whole module directory** — and only *then* calls
  `hook_invoke($pkg, 'uninstall_extension', $dummy)`. Your `sql/` directory is
  already gone, so `uninstall_extension()` can only use inline SQL or
  already-loaded state. Don't rely on reading files from your own dir there.

**`<table>_uninstall.sql` convention.** Ship one per table, mirroring the
install files, and **leave the `DROP` statements commented out by default**.
Deactivation is routinely a temporary switch for a single company, and FA
preserves data by default — silently dropping a module's tables on a
mis-click is unrecoverable. A sysadmin who genuinely wants them gone uncomments
the block, then:

```php
function deactivate_extension($company, $check_only = true)
{
    if ($check_only) {
        return parent::deactivate_extension($company, $check_only);
    }
    global $db_connections;
    foreach (glob(__DIR__ . '/sql/*_uninstall.sql') as $file) {
        $conn = $db_connections[($company == -1) ? 0 : $company];
        db_import($file, $conn);
    }
    remove_security_section(SS_ksf_FA_ModuleName);
    return parent::deactivate_extension($company, $check_only);
}
```

Shape of each file (all `0_`-prefixed, `DROP`s inert):

```sql
-- ksf_crm_customer_types_uninstall.sql
-- 0_ksf_crm_customer_types
-- DESTRUCTIVE: uncomment only when the data is knowingly being discarded.
-- DROP TABLE IF EXISTS 0_ksf_crm_customer_types;
```

Note the name must match the table **exactly** — the file is found by glob and
the name is a convention only, but a `0_fa_crm_*` name here (the CRM's original
mistake, fixed in `4db5a07`) documents a table that never existed.

**No `run_db_import()` exists** in FA 2.4.3 or in any ksf module — an earlier
revision of this doc referenced it. The real helpers are `db_import()` (one
filename) and `check_table()`.

### 12.2 Native FA data access — the shared contact resolver (owner decision, 2026-10)

**The rule.** A module must use FA core's own data through FA core's own
functions rather than re-implementing the storage:

> Use NATIVE FA FUNCTION CALLS to access native FA data.

Not raw SQL against FA core tables. A hand-written `SELECT ... FROM 0_crm_persons`
re-implements FA's storage: it breaks when FA changes the schema, it bypasses
FA's company-prefix handling, and it silently produces different answers from
the function the platform actually ships. This applies to every FA core table —
`0_crm_persons`, `0_crm_contacts`, `0_crm_categories`, `0_debtors_master`,
`0_stock_master`, `0_users` … A module that needs FA's data calls FA's
function; a module that needs its *own* data owns a table (see the naming rule
below).

**The concrete case: CRM contacts.** CRM is to use NATIVE FA tables/data where
possible, so our own `0_ksf_crm_contacts` table was **DEPRECATED**. FA's own
`0_crm_persons` (the person) and `0_crm_contacts` (the relation between a
person and an entity, in a category) are the contact store. Therefore:

- `0_ksf_crm_contacts` is **deprecated**. Do not use it, do not read it, do not
  write it, do not migrate data into it, and do not re-create it.
- Do not introduce a replacement of our own either (`0_ksf_crm_contact_*`).
  There is one contact registry: FA's.
- "Obviously not everything was updated" — the CRM's own
  `src/FrontAccounting/CRM/Repository/ContactsRepository.php` still reads
  `0_ksf_crm_contacts`, and other modules reach for a contact table directly.
  That is drift to be fixed module by module; it is **not** a reason to keep
  using the deprecated table.
- Live counterexample of the rule being broken: one module addresses
  `0_fa_crm_contacts` — that table has never existed (FA's table is
  `0_crm_contacts`, no `fa_` segment). Same class of bug, one segment apart.

**The native functions to prefer (verified against FA 2.4.3 source,
`includes/db/crm_contacts_db.inc` and `sales/includes/db/customers_db.inc`).**

| Function | Signature / purpose |
|---|---|
| `get_crm_person($id)` | One person row (`crm_persons`) **plus** `['contacts' => …]`, the person's contact-category ids. |
| `get_crm_persons($type = null, $action = null, $entity = null, $person = null, $unique = false)` | The relation query: `crm_persons ⋈ crm_contacts ⋈ crm_categories`. This is the native way to get *an entity's contacts* — e.g. `get_crm_persons('customer', null, $debtor_no)`. `$unique = true` groups by person. Falls back to the `'general'` action when a filtered query returns nothing. |
| `get_crm_contact($id)` | One contact row: `type`, `action`, `person_id`, the person's fields, and the contact's own `id`. |
| `get_person_contacts($id)` | The person's contact **category** ids (`crm_categories.id`) — **not** contact row ids. A common misreading; the ids are category ids. |
| `add_crm_contact($type, $action, $entity_id, $person_id)` | Create a contact relation. |
| `add_crm_person($ref, $name, $name2, $address, $phone, $phone2, $fax, $email, $lang, $notes, $cat_ids = null, $entity = null)` | Create a person (optionally with contact categories). Returns the new id. |
| `update_crm_person($id, $ref, $name, $name2, $address, $phone, $phone2, $fax, $email, $lang, $notes, $cat_ids, $entity = null, $type = null)` | Update a person and their contacts. |
| `update_person_contacts($id, $cat_ids, $entity_id = null, $type = null)` | Replace a person's contact categories. |
| `delete_crm_contact($id)` | Delete one contact relation. |
| `delete_crm_contacts($person_id = null, $type = null, $entity_id = null, $action = null)` | Delete selected contact relations. |
| `delete_crm_person($person, $with_contacts = false)` | Delete a person (and optionally their contacts). |
| `delete_entity_contacts($class, $entity)` | Delete every contact of an entity, and clean up persons left with no contacts. |
| `get_customer($customer_id)` | The debtor record (`debtors_master`) for a customer id. |
| `get_customer_name($customer_id)` | The customer's name. |
| `get_customer_contacts($customer_id, $action = null)` | The customer's contacts, as person rows. Customer-specific wrapper over `get_crm_persons('customer', …)`; also normalises the demo `lang = 'C'` value to `''`. |
| `get_customer_details($customer_id, $to = null, $all = true)` | The customer record with balances. |

Also available in the same file for the category registry:
`add_crm_category`, `update_crm_category`, `delete_crm_category`,
`get_crm_categories`, `get_crm_category`, `get_crm_category_name`,
`is_crm_category_used`.

**Note on loading them.** `includes/db/crm_contacts_db.inc` and
`sales/includes/db/customers_db.inc` are **not** auto-loaded by
`includes/main.inc`. A module that calls these functions must
`include_once` the file itself (both are pure function-definition files, so a
guarded `include_once` is safe).

**The shared seam: a module must go through the contact resolver.** Any module
that needs a contact must call the **shared contact resolver** in
`ksf_FA_Common` — it must not query a contact table itself:

- Contract: `ksfraser\FrontAccounting\Common\ContactResolver\Contract\ContactResolverInterface`
- FA implementation: `ksfraser\FrontAccounting\Common\ContactResolver\FaContactResolver`
  (calls the native functions above; no SQL against FA core tables)
- Front door (hook dispatch + fallback):
  `ksfraser\FrontAccounting\Common\ContactResolver\ContactResolver`
- Non-FA implementations (WordPress, Nextcloud, standalone): implement the same
  contract and inject it, or answer the `ksf_contact_resolve` hook.

Lookups the contract covers: person by id, person(s) by email, a debtor's
(customer's) contacts, an entity's contacts, a contact row by id, a person's
contact-category ids, and a name/email search.

**A shared seam must never be gated on another module's activation.** The
resolver lives in `ksf_FA_Common`, a Composer package that is always
loadable — it is **not** "unavailable because `ksf_FA_CRM` is not activated".
When FA's CRM tables or functions are absent, the resolver returns "no
contact" (empty list / null); it never fatals, and it never asks whether
another module is active. The same rule applies to the hook: a listener's
absence is a normal state, not an error.

**The table-naming consequence.** Our own tables are `0_ksf_<module>_<noun>`;
`0_fa_*` is reserved for FA core (see the naming rule in §12 above). The
contact registry is FA core's, so it keeps FA core's names — `0_crm_persons`,
`0_crm_contacts`, `0_crm_categories` — and no module may claim a `0_ksf_*`
counterpart for it. Our naming rule applies to tables we own, not to tables
FA owns.

## 13. RBAC Architecture (ksf_FA_RBAC)

### Design Document
Full design: `ksf_FA_RBAC/ProjectDcs/RBAC_V2_DESIGN.md`

### Overview
RBAC v2 uses voter-based authorization inspired by Symfony Security, with:
- **Zend RBAC** (`zendframework/zend-permissions-rbac`) for role/permission hierarchy
- **Voter pattern** for CRUD authorization
- **Dynamic assertions** for record-level access
- **Field-level encryption** via `defuse/php-encryption`

### Hooks API

| Hook | Purpose | Returns |
|------|---------|---------|
| `authorize` | Check CRUD access | `true/false/null` |
| `filterRecordList` | Filter list view records | Modified SQL |
| `filterFields` | Restrict field visibility | Field array |
| `encryptField` | Encrypt/decrypt values | Encrypted string |

### Authorization Hook
```php
hook_invoke_all('ksf_FA_RBAC', 'authorize', [
    'user_id'   => $user_id,
    'action'    => 'view', // create, view, edit, delete, list, export
    'module'    => 'customer',
    'resource'  => $customer_obj, // optional for record-level
    'assertion' => function($user_id, $resource) {
        return $resource->isOwnedBy($user_id);
    }
]);
// true = allowed, false = denied, null = abstain (let other voters decide)
```

### Decision Strategies
- `affirmative`: grant if ANY voter allows
- `consensus`: grant if majority allows
- `unanimous`: grant if ALL allow

### Module ACL Registry
Each module declares permissions in `hooks.php` via `getModuleAcl()`:
```php
$data['customer'] = [
    'create' => ['admin', 'manager'],
    'view'   => ['admin', 'manager', 'salesman'],
    'edit'   => ['admin', 'manager'],
    'delete' => ['admin'],
];
```

### Dependency Behavior
| Module | Behavior |
|--------|----------|
| RBAC installed | Full voter-based authorization |
| RBAC missing | All hooks return `null` (native FA permissions) |
| CRM installed | Team-based access via `crm_company_contacts` |
| CRM missing | Record-level uses native `salesman_code` |

### Default Roles
| Role | Description | Inherits |
|------|-------------|----------|
| `admin` | Full access | - |
| `manager` | Business unit | `salesman` |
| `salesman` | Sales rep | `clerk` |
| `clerk` | Data entry | - |
| `ar_clerk` | AR entry | `clerk` |
| `ap_clerk` | AP entry | `clerk` |
| `warehouse` | Warehouse | `clerk` |
| `viewer` | Read-only | - |

## 14. Ecosystem docs

For the package/namespace/dependency map (which repo wraps which, monolith
splits, trait inventory), see the shared ecosystem docs — `MODULE_DIRECTORY.md`,
`PACKAGIST.md`, `APP_TAB_ARCHITECTURE.md` — hardlinked into each repo per
`AGENTS_APPENDIX.md` §Architecture-doc hardlinks. Keep ecosystem *facts* there,
not here.
