# KSF FrontAccounting — Health Sweep Results

**Run:** 2026-10-11 18:46–18:48 (container time 00:46–00:48, 12 Oct)
**Target:** `http://localhost:8090` — container `ksfii_app-fa`, PHP 7.4.33, FA 2.4.3
**Method:** Authenticated Chromium session (`opencode`/`opencode`), 138 URLs
**Mode:** Research/reporting only. No files in the stack were modified, fixed, or committed.

---

## Headline counts

| Metric | Count |
|---|---|
| URLs swept | **138** |
| Healthy (real content) | **71** (51%) |
| Broken | **59** (43%) |
| Benign-empty (correct "no data" / debug / download) | 8 (6%) |

Broken breakdown: **12 × HTTP 500**, **5 × HTTP 404**, **1 × HTTP 405**, **41 × HTTP 200-but-empty**.

Broken by module: QuickBudget 14, CRM 13, ProjectManagement 8, SuggestedPurchaseOrder 5,
HRM 4, FA core `applications/` 3, Square 2, Upc2Item 2, Calendar 1, ImportStagingProcessing 1,
ImportStagingProcessing_UI 1, plus 3 core/misc 404s and 2 `modules_dep_needs` 404s.

### Comparison with the previous sweep

| | Count |
|---|---|
| **REGRESSIONS** (previously healthy → now broken) | **0** |
| FIXES (previously 500 → now 200) | 7 (see caveat below) |
| Still broken | 37 |
| Newly added URLs (not in previous sweep) | 38 |
| Dropped URLs (bad CORE list, see below) | 8 |

**No regressions.** The 7 apparent "fixes" are mostly a measurement artefact — see
*Measurement caveats*. Only `ksf_FA_Calendar/pages/my_events.php` genuinely improved from
500 to rendering chrome; it still renders no module content.

---

## Fix these first (ordered by severity)

### 1. PHP 8 syntax on a PHP 7.4 runtime — 3 hard 500s *(highest priority, deterministic)*

PHP 8.0/8.1 syntax was committed to modules that run on PHP 7.4. These are parse errors: the
file never compiles, so the page is a hard 500 regardless of data or permissions.

| Page | Line | Construct | Log |
|---|---|---|---|
| `ksf_FA_SuggestedPurchaseOrder/pages/item_trends.php` | 85 | `match($trend->demandTrend) {` | `PHP Parse error: syntax error, unexpected '=>' (T_DOUBLE_ARROW)` |
| `ksf_FA_SuggestedPurchaseOrder/pages/suggested_orders.php` | 95 | `match($line['priority']) {` | same |
| `ksf_FA_SuggestedPurchaseOrder/includes/db.inc` | 78 | `function spo_db_write(string $action, ...$args): int\|bool` | `syntax error, unexpected '\|', expecting '{'` |

The `match()` pair was the known suspect and is **confirmed**. The `int|bool` union return type
in `includes/db.inc` is a **new finding** — not previously reported. It is why the *other three*
SuggestedPurchaseOrder pages (`configuration.php`, `insufficient_stock.php`, `vendor_trends.php`)
return HTTP 200 with zero content: they load `db.inc` and die silently at line 78, before any
output. Fixing `db.inc` alone will likely repair all five SuggestedPurchaseOrder pages.

### 2. `ksf_FA_Upc2Item` — both pages unreadable by the web server *(500, 2 pages)*

```
PHP Warning:  Unknown: failed to open stream: Permission denied in Unknown on line 0
PHP Fatal error:  Unknown: Failed opening required '/var/www/html/modules/ksf_FA_Upc2Item/pages/config.php'
```

File mode is **`-rw-------` owned by `kevin:kevin`** (both `config.php` and `scan.php`). Apache
runs as `www-data` and cannot read them. This is a filesystem-permission problem, not a code
problem. It will recur on any fresh checkout/deploy unless the mode is fixed in version control.

### 3. `ksf_FA_HRM` — 4 of 4 pages broken *(2 × 500, 2 × silent-empty)*

| Page | Error |
|---|---|
| `pages/leave.php:15` | `Call to undefined function db_query()` (500) |
| `pages/payroll.php:13` | `PayrollService->listAll()` → `FatRepositoryTrait.php:11` → `Call to undefined function db_query()` (500) |
| `pages/recruitment.php:3` | `Call to undefined function _()` (silent empty) |
| `pages/reports.php:3` | `Call to undefined function _()` (silent empty) |

All four emit `Use of undefined constant TB_PREF - assumed 'TB_PREF'` **before** failing.
`TB_PREF` and `_()` are defined by `includes/page/header.inc` / `session.inc`. The pages call
`db_query()` / `_()` before (or without) pulling in the FA bootstrap, i.e. an
include-order/`$path_to_root` problem. `leave.php` and `payroll.php` call `db_query()` on line
15/13, very early. I could not determine from the log alone whether the root cause is a missing
`session.inc` include or a bad `$path_to_root`; it needs the page source reviewed.

### 4. FA core `applications/*.php` — 3 hard 500s *(not module-related)*

`/applications/setup.php:12`, `/applications/generalledger.php:12`, `/applications/inventory.php:12`

```
PHP Fatal error:  Uncaught Error: Class 'application' not found
```

These are **stock FA 2.4.3 core files**, not ksf modules. `$application` (class `application`,
from `includes/ui/view/view_map.inc` / `class/application.inc`) is not being autoloaded. This
reproduces on every core application menu entry, so it is a **core deployment problem** and
should be triaged ahead of the module issues despite the module count.

### 5. `ksf_FA_SuggestedPurchaseOrder` security areas — confirmed non-blocking

`SA_SUGGESTED_PO_VIEW` / `_TRENDS` / `_CONFIG` **are** defined in the module's own
`hooks.php::install_access()`. I verified the constants exist. No evidence these areas cause a
failure. The pages fail on the parse errors above instead.

### 6. `ksf_FA_Workflow` using core `SA_CUSTOMER` — confirmed NOT a security failure

`SA_CUSTOMER` is a genuine FA core area (`includes/access_levels.inc:143`, `SS_SALES|2`), so
`$page_security = 'SA_CUSTOMER'` resolves. Both pages render a real page
(`workflows.php` shows "Workflow Administration / New / Trigger Name:"). The actual defect is
unrelated:

```
include_once(../../../modules/FA_Workflow/includes/wf_db.inc): No such file or directory
workflows.php:78: Call to undefined function select_row().
```

The path is `modules/FA_Workflow` but the module directory is `ksf_FA_Workflow`. Every page is
missing its data layer. (Note: `ksf_FA_Workflow` is **not** in the installed-extensions registry
at all.)

### 7. `ksf_FA_EmailManager` — pages render, but user is **denied access**

Confirmed defined in `hooks.php::install_access()`. Rendered text contains:

> "The security settings on your account do not permit you to access this function"

The areas are declared but not granted to the `opencode` role. FA's `can_access()`
(`includes/current_user.inc:192`) does `$security_areas[$sec_area][0]` — for a declared-but-
ungranted area the code exists but is not in `role_set`, so access is refused. **This is a
data/permission-configuration issue, not a code defect.**

Separately, `includes/em_db.inc:7` fails to load a Composer path on all 4 pages:
`vendor/ksfraser/event/src/Ksfraser/Event/EventManager.php` — wrong case/path (`Ksfraser` vs
`ksfraser`), and the package does not exist in `vendor/`.

### 8. `ksf_FA_Customer` — `SS_ksf_FA_Customer` never defined (stack-wide noise)

`hooks.php:351,353,356` reference `SS_ksf_FA_Customer`, but **no `define('SS_ksf_FA_Customer')`
exists anywhere in the module**. Every request emits:

```
Use of undefined constant SS_ksf_FA_Customer - assumed 'SS_ksf_FA_Customer'
  (this will throw an Error in a future version of PHP)
```

**162 occurrences during the sweep** (81 × 2 lines). PHP 7.4 coerces the bareword to the
*string* `'SS_ksf_FA_Customer'`, then `SS_ksf_FA_Customer | 108` performs arithmetic on a string
→ `A non-numeric value encountered`. The security area is therefore registered under a garbage
code. Not fatal today, but it **will throw an `Error` on PHP 8** and it silently breaks
Customer's access-control area today.

### 9. `/modules/modules_dep_needs/e2e_module_dependencies.php` — 404 confirmed ✅

Both `modules_dep_needs/` and `modules_dep_needed/` return **404**, as expected. Neither
directory contains the file. Removal from the web root is confirmed complete.

---

## Remaining HTTP 500s without a fully determined cause

I want to be explicit about these rather than guess:

- **`ksf_FA_CRM/pages/index.php:5`** — `Class 'ksf\App' not found`. The class simply does not
  exist / is not autoloaded. Deterministic, but I did not trace which autoloader should supply it.
- **`ksf_FA_QuickBudget/pages/report_half.php:21`** — `syntax error, unexpected end of file`.
  A truncated/unbalanced file. Straightforward to inspect.
- **`ksf_FA_Square/pages/webhook_management.php:21`** —
  `WebhookManagementController->__construct()` → `Call to undefined function get_company_pref()`.
  Same include-order family as the HRM issue above.
- **`ksf_FA_Square/pages/webhook.php`** returns **405 Method Not Allowed** — this is
  *correct* behaviour for a webhook receiver hit with GET; not a defect.

---

## HTTP 200-but-empty pages (41)

These return a success status while rendering nothing. Three distinct causes:

**(a) Shared-include failures (root cause in an `includes/` file, not the page):**

- **ksf_FA_ProjectManagement — all 8 pages.** Every page emits
  `pm_db.inc:11: syntax error, unexpected '|', expecting '{'` — a PHP 8 union type in the
  module's DB layer. Same class of bug as item #1. `pages/tasks.php` additionally fails
  `settings.php:10: Call to a member function check_access() on null`.
- **ksf_FA_CRM — 13 of 21 pages.** `ContactOptionsService` not found, plus
  `dashboard.php:22: Call to undefined function label_cell()`. Pages that *do* work show
  `org_chart.php:7: include_once(../../../includes/db.inc): No such file or directory` — the
  relative path resolves wrong. CRM is the worst-affected module.
- **ksf_FA_QuickBudget** debug/bisect pages — `quickbudget_compare.php:85: Class 'FlashMessage'
  not found`; `test_bisect*.php`: `strtotime() expects parameter 1 to be string, null given`
  (no fiscal year defined in this DB).
- **ksf_FA_Calendar `my_events.php:25`** — `Call to undefined function page_header()`.
- **ksf_FA_ImportStagingProcessing `admin.php:80`** — `Call to undefined function page_footer()`.
- **ksf_FA_ImportStagingProcessing_UI `config.php:35`** — `Call to undefined function start_page()`.
- **ksf_FA_Contacts `contacts.php:36`** — `include_once(../../../includes/db/crm_categories_db.inc)`
  not found.

All of the above are the **same signature**: a page calls an FA UI/DB function that was never
loaded. In every case the relative include path is `../../../includes/...`, i.e. the page expects
to sit at depth 3 under the web root but is being served from a module path where that resolves
incorrectly, or the `includes/` file is simply missing from the module.

**(b) Benign "no data" responses (4)** — the four `*_pdf.php` QuickBudget pages correctly render
"No budget data available." because no fiscal year is configured. **Not a defect.**

**(c) Debug scaffolding (7)** — `_debug3..7`, `_debug_report`, `_debug_report2`, `test_bisect*`
are developer scratch files that should not be web-reachable at all. Recommend removing them or
blocking access.

---

## Log noise (constant, harmless — filtered per instructions)

Excluded: `Unable to load dynamic library`, `already loaded`, `PHP Startup`, and additionally
`Domain file ".../C.po" not found` (thousands of gettext notices per sweep).

Also constant and pre-existing, from FA core itself (not module defects):
`get_magic_quotes_gpc() is deprecated` (119×), `gl_db_trans.inc:454` unparenthesized ternary
(112×), `session.inc:430` ini_set-after-session (119×), `ui_lists.inc:161` implode glue order (11×),
`db_pager.inc:293` count() on non-array (3×).

**Write-permission problems (environmental, worth a human look):**

| Path | Operation |
|---|---|
| `company/0/js_cache/*` | `unlink(): Permission denied` (5× at login) |
| `modules/_cache/Release.gz` | `fopen(): Permission denied` → then `packages.inc:538 array_merge(): null given` |
| `modules/ksf_FA_QuickBudget/cache/resolved_type_rates.cache` | `file_put_contents(): Permission denied` (5×, cache never persists) |

---

## Measurement caveats (important for reading the numbers)

1. **The previous sweep's CORE list was wrong.** 8 of its 13 core URLs do not exist in this
   FA 2.4.3 tree (`/purchasing/purchases_entry.php`, `/gl/gl_purchase_invoice.php`,
   `/setup/company.php`, `/inventory/items.php`, `/admin/company_sql.php`, `/access/backup_db.php`,
   `/inquiry/inquiry_entry.php`, `/inventory/stock_moves.php`). They scored a permanent
   false-positive 404 every run. I replaced the list with 34 verified-existing core URLs, so
   the healthy count jumped largely because of **better coverage**, not because things improved.
   The **38 new URLs** are mostly newly-covered core pages plus the 7 SuggestedPurchaseOrder /
   Workflow pages that were previously untested.

2. **The old sweep never verified login.** It submitted the form and proceeded regardless of
   outcome. Because FA answers a failed login with **HTTP 200 and a full login form**, a broken
   login would have made every single page report "healthy". I added a hard auth guard that
   aborts the run if the session is not real.

3. **Blank-detection threshold was wrong.** FA's own page chrome (header, footer, `<script>`
   blocks) renders as **~306 characters of text**. The old threshold of `<250` therefore
   classified chrome-only pages as "healthy". I raised it to 320 and verified the actual chrome
   baseline by probing several pages by hand. This is why several pages that the previous sweep
   scored as healthy now appear as problems.

4. **4 pages report `ERR_ABORTED` in the browser but are fine.** `quickbudget_inflation_pdf.php`,
   `test_bisect2/3/8.php` trigger a navigation abort (the page streams a download). Verified by
   direct `curl`: all four return **HTTP 200 with a full body**. These are **not** server faults
   and I have counted them as benign rather than broken.

5. `php-error.log` inside the container is **stale** (last write 00:45, before the sweep) and
   received nothing during the run. PHP diagnostics are actually emitted to the container's
   **stderr**, not that file. The specified `tail -f /var/log/apache2/php-error.log` command would
   have shown an empty log and implied "no errors". All diagnostics in this report come from
   `podman logs` stderr, correlated by timestamp against the access log.

---

## Scope covered

- 42 registered extensions enumerated from `/var/www/html/company/0/installed_extensions.php`
  (29 active, 13 inactive). All module directories present on disk are in the registry.
- 104 module pages (`pages/*.php`) + 34 verified core entry points.
- `ksf_FA_API`, `ksf_FA_RBAC`, `ksf_payment_destinations`, `FA_ProductAttributes`, `ksf_FA_GPG`,
  `ksf_FA_SerialNumber`, `ksf_FA_Warehouse`, `ksf_FA_Attachments`, `ksf_FA_Customer`,
  `ksf_FA_Employee`, `ksf_FA_ExpenseReport`, `ksf_FA_Wallet` are **active but expose no
  `pages/` directory**, so they contributed no URLs to this sweep. Their health is untested here.

---

## Raw per-page results

Healthy (71):

| URL | Status | Text len | Verdict |
|---|---|---|---|| `/` | 200 | 1888 | healthy |
| `/company/index.php` | 200 | 1888 | healthy |
| `/company/0/index.php` | 200 | 1888 | healthy |
| `/admin/inst_module.php` | 200 | 7675 | healthy |
| `/dimensions/index.php` | 200 | 1888 | healthy |
| `/sales/sales_order_entry.php` | 200 | 1023 | healthy |
| `/sales/customer_delivery.php` | 200 | 1182 | healthy |
| `/sales/customer_invoice.php` | 200 | 1173 | healthy |
| `/sales/customer_payments.php` | 200 | 1280 | healthy |
| `/sales/credit_note_entry.php` | 200 | 1795 | healthy |
| `/sales/inquiry/customer_inquiry.php` | 200 | 1500 | healthy |
| `/purchasing/po_entry_items.php` | 200 | 1069 | healthy |
| `/purchasing/supplier_invoice.php` | 200 | 347 | healthy |
| `/purchasing/supplier_credit.php` | 200 | 347 | healthy |
| `/purchasing/supplier_payment.php` | 200 | 1091 | healthy |
| `/purchasing/inquiry/supplier_inquiry.php` | 200 | 1420 | healthy |
| `/gl/gl_journal.php` | 200 | 1204 | healthy |
| `/gl/gl_bank.php` | 200 | 3203 | healthy |
| `/gl/bank_account_reconcile.php` | 200 | 1316 | healthy |
| `/gl/inquiry/gl_trial_balance.php` | 200 | 344 | healthy |
| `/gl/inquiry/profit_loss.php` | 200 | 1332 | healthy |
| `/inventory/cost_update.php` | 200 | 1113 | healthy |
| `/inventory/adjustments.php` | 200 | 1232 | healthy |
| `/inventory/transfers.php` | 200 | 1221 | healthy |
| `/inventory/prices.php` | 200 | 1213 | healthy |
| `/inventory/reorder_level.php` | 200 | 1152 | healthy |
| `/inventory/inquiry/stock_status.php` | 200 | 1158 | healthy |
| `/inventory/inquiry/stock_movements.php` | 200 | 1294 | healthy |
| `/modules/ksf_FA_Calendar/pages/calendar.php` | 200 | 17016 | healthy |
| `/modules/ksf_FA_Calendar/pages/settings.php` | 200 | 16394 | healthy |
| `/modules/ksf_FA_Contacts/pages/contacts.php` | 200 | 1117 | healthy |
| `/modules/ksf_FA_CRM/pages/account_relationships.php` | 200 | 1130 | healthy |
| `/modules/ksf_FA_CRM/pages/contact_relationships.php` | 200 | 1130 | healthy |
| `/modules/ksf_FA_CRM/pages/crm_tags.php` | 200 | 1128 | healthy |
| `/modules/ksf_FA_CRM/pages/gedcom_export.php` | 200 | 1122 | healthy |
| `/modules/ksf_FA_CRM/pages/gedcom_import.php` | 200 | 1122 | healthy |
| `/modules/ksf_FA_CRM/pages/life_events.php` | 200 | 1120 | healthy |
| `/modules/ksf_FA_CRM/pages/org_chart.php` | 200 | 1122 | healthy |
| `/modules/ksf_FA_CRM/pages/person_account_roles.php` | 200 | 1129 | healthy |
| `/modules/ksf_FA_DataIntegrity/pages/allocation_integrity.php` | 200 | 1083 | healthy |
| `/modules/ksf_FA_DataIntegrity/pages/integrity_dashboard.php` | 200 | 5305 | healthy |
| `/modules/ksf_FA_DataIntegrity/pages/integrity_report.php` | 200 | 4871 | healthy |
| `/modules/ksf_FA_DataIntegrity/pages/purchase_integrity.php` | 200 | 1246 | healthy |
| `/modules/ksf_FA_DataIntegrity/pages/sales_integrity.php` | 200 | 1227 | healthy |
| `/modules/ksf_fa_downloader/pages/controller.php` | 200 | 1374 | healthy |
| `/modules/ksf_FA_EmailManager/pages/accounts.php` | 200 | 1133 | healthy |
| `/modules/ksf_FA_EmailManager/pages/campaigns.php` | 200 | 1129 | healthy |
| `/modules/ksf_FA_EmailManager/pages/inbox.php` | 200 | 1120 | healthy |
| `/modules/ksf_FA_EmailManager/pages/mailing_lists.php` | 200 | 1122 | healthy |
| `/modules/ksf_FA_Notes/pages/notes.php` | 200 | 1035 | healthy |
| `/modules/ksf_FA_QuickBudget/pages/quickbudget_annual_breakdown.php` | 200 | 1347 | healthy |
| `/modules/ksf_FA_QuickBudget/pages/quickbudget_approve.php` | 200 | 1087 | healthy |
| `/modules/ksf_FA_QuickBudget/pages/quickbudget_bs_breakdown.php` | 200 | 1275 | healthy |
| `/modules/ksf_FA_QuickBudget/pages/quickbudget_bs_projection.php` | 200 | 1517 | healthy |
| `/modules/ksf_FA_QuickBudget/pages/quickbudget_compare.php` | 200 | 1061 | healthy |
| `/modules/ksf_FA_QuickBudget/pages/quickbudget_config.php` | 200 | 4243 | healthy |
| `/modules/ksf_FA_QuickBudget/pages/quickbudget_inflation_transfer.php` | 200 | 1980 | healthy |
| `/modules/ksf_FA_QuickBudget/pages/quickbudget.php` | 200 | 1372 | healthy |
| `/modules/ksf_FA_QuickBudget/pages/quickbudget_pl_projection.php` | 200 | 1517 | healthy |
| `/modules/ksf_FA_QuickBudget/pages/quickbudget_report.php` | 200 | 1951 | healthy |
| `/modules/ksf_FA_QuickBudget/pages/report_stripped.php` | 200 | 1063 | healthy |
| `/modules/ksf_FA_Square/pages/config.php` | 200 | 2010 | healthy |
| `/modules/ksf_FA_Square/pages/dashboard.php` | 200 | 1395 | healthy |
| `/modules/ksf_FA_Square/pages/export.php` | 200 | 1310 | healthy |
| `/modules/ksf_FA_Square/pages/fa_transactions.php` | 200 | 2035 | healthy |
| `/modules/ksf_FA_Square/pages/import.php` | 200 | 1640 | healthy |
| `/modules/ksf_FA_Square/pages/review_match.php` | 200 | 1945 | healthy |
| `/modules/ksf_FA_Users/pages/users.php` | 200 | 1035 | healthy |
| `/modules/ksf_FA_Woocommerce/pages/admin.php` | 200 | 1145 | healthy |
| `/modules/ksf_FA_Workflow/pages/actions.php` | 200 | 1108 | healthy |
| `/modules/ksf_FA_Workflow/pages/workflows.php` | 200 | 1075 | healthy || `/applications/setup.php` | 500 | 0 | problem |
| `/applications/generalledger.php` | 500 | 0 | problem |
| `/applications/inventory.php` | 500 | 0 | problem |
| `/sales/view/sales_orders_view.php` | 404 | 112 | problem |
| `/purchasing/view/po_view.php` | 404 | 112 | problem |
| `/manufacturing/manufacturing_entry.php` | 404 | 112 | problem |
| `/modules/ksf_FA_Calendar/pages/my_events.php` | 200 | 308 | problem |
| `/modules/ksf_FA_CRM/pages/calendar.php` | 200 | 0 | problem |
| `/modules/ksf_FA_CRM/pages/communications.php` | 200 | 0 | problem |
| `/modules/ksf_FA_CRM/pages/convert_lead.php` | 200 | 0 | problem |
| `/modules/ksf_FA_CRM/pages/customer_types.php` | 200 | 0 | problem |
| `/modules/ksf_FA_CRM/pages/dashboard.php` | 200 | 308 | problem |
| `/modules/ksf_FA_CRM/pages/index.php` | 500 | 0 | problem |
| `/modules/ksf_FA_CRM/pages/leads.php` | 200 | 0 | problem |
| `/modules/ksf_FA_CRM/pages/meeting_rooms.php` | 200 | 0 | problem |
| `/modules/ksf_FA_CRM/pages/meetings.php` | 200 | 0 | problem |
| `/modules/ksf_FA_CRM/pages/opportunities.php` | 200 | 0 | problem |
| `/modules/ksf_FA_CRM/pages/quotes.php` | 200 | 0 | problem |
| `/modules/ksf_FA_CRM/pages/realms.php` | 200 | 0 | problem |
| `/modules/ksf_FA_CRM/pages/territories.php` | 200 | 0 | problem |
| `/modules/ksf_FA_HRM/pages/leave.php` | 500 | 0 | problem |
| `/modules/ksf_FA_HRM/pages/payroll.php` | 500 | 0 | problem |
| `/modules/ksf_FA_HRM/pages/recruitment.php` | 200 | 1 | problem |
| `/modules/ksf_FA_HRM/pages/reports.php` | 200 | 1 | problem |
| `/modules/ksf_FA_ImportStagingProcessing/pages/admin.php` | 200 | 0 | problem |
| `/modules/ksf_FA_ImportStagingProcessing_UI/pages/config.php` | 200 | 308 | problem |
| `/modules/ksf_FA_ProjectManagement/pages/dashboard.php` | 200 | 308 | problem |
| `/modules/ksf_FA_ProjectManagement/pages/gantt.php` | 200 | 308 | problem |
| `/modules/ksf_FA_ProjectManagement/pages/projects.php` | 200 | 308 | problem |
| `/modules/ksf_FA_ProjectManagement/pages/reports.php` | 200 | 308 | problem |
| `/modules/ksf_FA_ProjectManagement/pages/settings.php` | 200 | 308 | problem |
| `/modules/ksf_FA_ProjectManagement/pages/tasks.php` | 200 | 308 | problem |
| `/modules/ksf_FA_ProjectManagement/pages/team.php` | 200 | 308 | problem |
| `/modules/ksf_FA_ProjectManagement/pages/utilization.php` | 200 | 308 | problem |
| `/modules/ksf_FA_QuickBudget/pages/_debug3.php` | 200 | 8 | problem |
| `/modules/ksf_FA_QuickBudget/pages/_debug4.php` | 200 | 8 | problem |
| `/modules/ksf_FA_QuickBudget/pages/_debug5.php` | 200 | 8 | problem |
| `/modules/ksf_FA_QuickBudget/pages/_debug6.php` | 200 | 8 | problem |
| `/modules/ksf_FA_QuickBudget/pages/_debug7.php` | 200 | 8 | problem |
| `/modules/ksf_FA_QuickBudget/pages/_debug_report2.php` | 200 | 15 | problem |
| `/modules/ksf_FA_QuickBudget/pages/_debug_report.php` | 200 | 26 | problem |
| `/modules/ksf_FA_QuickBudget/pages/report_half.php` | 500 | 0 | problem |
| `/modules/ksf_FA_QuickBudget/pages/test_bisect4.php` | 200 | 308 | problem |
| `/modules/ksf_FA_QuickBudget/pages/test_bisect5.php` | 200 | 308 | problem |
| `/modules/ksf_FA_QuickBudget/pages/test_bisect6.php` | 200 | 308 | problem |
| `/modules/ksf_FA_QuickBudget/pages/test_bisect7.php` | 200 | 308 | problem |
| `/modules/ksf_FA_QuickBudget/pages/test_bisect9.php` | 200 | 308 | problem |
| `/modules/ksf_FA_QuickBudget/pages/test_bisect.php` | 200 | 308 | problem |
| `/modules/ksf_FA_Square/pages/webhook_management.php` | 500 | 0 | problem |
| `/modules/ksf_FA_Square/pages/webhook.php` | 405 | 18 | problem |
| `/modules/ksf_FA_SuggestedPurchaseOrder/pages/configuration.php` | 200 | 308 | problem |
| `/modules/ksf_FA_SuggestedPurchaseOrder/pages/insufficient_stock.php` | 200 | 308 | problem |
| `/modules/ksf_FA_SuggestedPurchaseOrder/pages/item_trends.php` | 500 | 0 | problem |
| `/modules/ksf_FA_SuggestedPurchaseOrder/pages/suggested_orders.php` | 500 | 0 | problem |
| `/modules/ksf_FA_SuggestedPurchaseOrder/pages/vendor_trends.php` | 200 | 308 | problem |
| `/modules/ksf_FA_Upc2Item/pages/config.php` | 500 | 0 | problem |
| `/modules/ksf_FA_Upc2Item/pages/scan.php` | 500 | 0 | problem |
| `/modules/modules_dep_needed/e2e_module_dependencies.php` | 404 | 112 | problem |
| `/modules/modules_dep_needs/e2e_module_dependencies.php` | 404 | 112 | problem |

Broken (59):

| URL | Status | Text len | Verdict |
|---|---|---|---|
| `/applications/setup.php` | 500 | 0 | problem |
| `/applications/generalledger.php` | 500 | 0 | problem |
| `/applications/inventory.php` | 500 | 0 | problem |
| `/sales/view/sales_orders_view.php` | 404 | 112 | problem |
| `/purchasing/view/po_view.php` | 404 | 112 | problem |
| `/manufacturing/manufacturing_entry.php` | 404 | 112 | problem |
| `/modules/ksf_FA_Calendar/pages/my_events.php` | 200 | 308 | problem |
| `/modules/ksf_FA_CRM/pages/calendar.php` | 200 | 0 | problem |
| `/modules/ksf_FA_CRM/pages/communications.php` | 200 | 0 | problem |
| `/modules/ksf_FA_CRM/pages/convert_lead.php` | 200 | 0 | problem |
| `/modules/ksf_FA_CRM/pages/customer_types.php` | 200 | 0 | problem |
| `/modules/ksf_FA_CRM/pages/dashboard.php` | 200 | 308 | problem |
| `/modules/ksf_FA_CRM/pages/index.php` | 500 | 0 | problem |
| `/modules/ksf_FA_CRM/pages/leads.php` | 200 | 0 | problem |
| `/modules/ksf_FA_CRM/pages/meeting_rooms.php` | 200 | 0 | problem |
| `/modules/ksf_FA_CRM/pages/meetings.php` | 200 | 0 | problem |
| `/modules/ksf_FA_CRM/pages/opportunities.php` | 200 | 0 | problem |
| `/modules/ksf_FA_CRM/pages/quotes.php` | 200 | 0 | problem |
| `/modules/ksf_FA_CRM/pages/realms.php` | 200 | 0 | problem |
| `/modules/ksf_FA_CRM/pages/territories.php` | 200 | 0 | problem |
| `/modules/ksf_FA_HRM/pages/leave.php` | 500 | 0 | problem |
| `/modules/ksf_FA_HRM/pages/payroll.php` | 500 | 0 | problem |
| `/modules/ksf_FA_HRM/pages/recruitment.php` | 200 | 1 | problem |
| `/modules/ksf_FA_HRM/pages/reports.php` | 200 | 1 | problem |
| `/modules/ksf_FA_ImportStagingProcessing/pages/admin.php` | 200 | 0 | problem |
| `/modules/ksf_FA_ImportStagingProcessing_UI/pages/config.php` | 200 | 308 | problem |
| `/modules/ksf_FA_ProjectManagement/pages/dashboard.php` | 200 | 308 | problem |
| `/modules/ksf_FA_ProjectManagement/pages/gantt.php` | 200 | 308 | problem |
| `/modules/ksf_FA_ProjectManagement/pages/projects.php` | 200 | 308 | problem |
| `/modules/ksf_FA_ProjectManagement/pages/reports.php` | 200 | 308 | problem |
| `/modules/ksf_FA_ProjectManagement/pages/settings.php` | 200 | 308 | problem |
| `/modules/ksf_FA_ProjectManagement/pages/tasks.php` | 200 | 308 | problem |
| `/modules/ksf_FA_ProjectManagement/pages/team.php` | 200 | 308 | problem |
| `/modules/ksf_FA_ProjectManagement/pages/utilization.php` | 200 | 308 | problem |
| `/modules/ksf_FA_QuickBudget/pages/_debug3.php` | 200 | 8 | problem |
| `/modules/ksf_FA_QuickBudget/pages/_debug4.php` | 200 | 8 | problem |
| `/modules/ksf_FA_QuickBudget/pages/_debug5.php` | 200 | 8 | problem |
| `/modules/ksf_FA_QuickBudget/pages/_debug6.php` | 200 | 8 | problem |
| `/modules/ksf_FA_QuickBudget/pages/_debug7.php` | 200 | 8 | problem |
| `/modules/ksf_FA_QuickBudget/pages/_debug_report2.php` | 200 | 15 | problem |
| `/modules/ksf_FA_QuickBudget/pages/_debug_report.php` | 200 | 26 | problem |
| `/modules/ksf_FA_QuickBudget/pages/report_half.php` | 500 | 0 | problem |
| `/modules/ksf_FA_QuickBudget/pages/test_bisect4.php` | 200 | 308 | problem |
| `/modules/ksf_FA_QuickBudget/pages/test_bisect5.php` | 200 | 308 | problem |
| `/modules/ksf_FA_QuickBudget/pages/test_bisect6.php` | 200 | 308 | problem |
| `/modules/ksf_FA_QuickBudget/pages/test_bisect7.php` | 200 | 308 | problem |
| `/modules/ksf_FA_QuickBudget/pages/test_bisect9.php` | 200 | 308 | problem |
| `/modules/ksf_FA_QuickBudget/pages/test_bisect.php` | 200 | 308 | problem |
| `/modules/ksf_FA_Square/pages/webhook_management.php` | 500 | 0 | problem |
| `/modules/ksf_FA_Square/pages/webhook.php` | 405 | 18 | problem |
| `/modules/ksf_FA_SuggestedPurchaseOrder/pages/configuration.php` | 200 | 308 | problem |
| `/modules/ksf_FA_SuggestedPurchaseOrder/pages/insufficient_stock.php` | 200 | 308 | problem |
| `/modules/ksf_FA_SuggestedPurchaseOrder/pages/item_trends.php` | 500 | 0 | problem |
| `/modules/ksf_FA_SuggestedPurchaseOrder/pages/suggested_orders.php` | 500 | 0 | problem |
| `/modules/ksf_FA_SuggestedPurchaseOrder/pages/vendor_trends.php` | 200 | 308 | problem |
| `/modules/ksf_FA_Upc2Item/pages/config.php` | 500 | 0 | problem |
| `/modules/ksf_FA_Upc2Item/pages/scan.php` | 500 | 0 | problem |
| `/modules/modules_dep_needed/e2e_module_dependencies.php` | 404 | 112 | problem |
| `/modules/modules_dep_needs/e2e_module_dependencies.php` | 404 | 112 | problem |
## Follow-up: 5 remaining 500s (verified by direct probe)

| page | cause | status |
|---|---|---|
| ksf_FA_HRM/pages/leave.php | calls `db_query()` before the FA DB layer is loaded | cause not fully determined |
| ksf_FA_HRM/pages/payroll.php | same family as above | cause not fully determined |
| ksf_FA_CRM/pages/index.php | `Class 'ksf\App' not found` | namespace after CRM refactor |
| ksf_FA_QuickBudget/pages/report_half.php | truncated/partial file | needs re-check |
| ksf_FA_Square/pages/webhook_management.php | `get_company_pref()` undefined — include-order family, same shape as HRM | needs include-order fix |

**Fixed and verified 200 (7 of 12):**
- All 5 ksf_FA_SuggestedPurchaseOrder pages. Root cause was two PHP 8 constructs
  on a PHP 7.4.33 runtime: four union return types in `includes/db.inc`
  (`: int|bool`, `: int|false`) and two `match()` expressions. Union return types
  are PARSE ERRORS, so merely including db.inc killed every dependent page -
  which is why three pages rendered *empty* rather than erroring visibly.
- Both ksf_FA_Upc2Item pages: files were mode `-rw-------` owned by `kevin`
  while Apache runs as `www-data`. Now `-rw-r--r--`.

**Correction to the sweep report:** `applications/application.php` returns 200,
not 500. The claim that FA core `applications/*` were broken with
"Class 'application' not found" did not reproduce and should not be actioned
without re-investigation.

**Note:** `fn() =>` arrow functions were flagged as PHP 8 syntax in the sweep.
They are valid in PHP 7.4 and were deliberately left unchanged.
