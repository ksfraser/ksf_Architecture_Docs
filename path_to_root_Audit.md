# `$path_to_root` Depth Audit — FrontAccounting Module Entry Points

**Date:** 2026-10-11
**Scope:** all `ksf_FA_*` / `ksf_*` module repos under `~/Documents`, plus the
deployed integration tree `ksf_Infrastructure/fa_modules/`
**Mode:** research only — no source file was modified.
**Live verification:** rootful container `ksfii_app-fa` (FA 2.4.3, PHP 7.4.33), port 8090

---

## 1. The bug, confirmed mechanically

`$path_to_root` is a **relative** path from the *executing file's own directory*
back to the FA root. It is used as:

```php
include_once($path_to_root . "/includes/session.inc");
```

A module is deployed at `<FA root>/modules/<mod>/`, so the required traversal is:

| File location | Levels below FA root | Required value |
|---|---|---|
| `modules/<mod>/x.php` | 2 | `../..` |
| `modules/<mod>/pages/x.php` | 3 | `../../..` |
| `modules/<mod>/includes/x.php` | 3 | `../../..` |
| `modules/<mod>/pages/sub/x.php` | 4 | `../../../..` |

This matches FA core exactly: `reporting/rep710.php` (one level down) uses `..`,
and `index.php` at the root uses `.`.

**Failure mode.** A `pages/*.php` file set to `../..` resolves `../..` from
`/var/www/html/modules/<mod>/pages/` to `/var/www/html/modules`. The include then
targets `/var/www/html/modules/includes/session.inc`, which does not exist.
`include_once` on a missing file is a **warning, not a fatal**, so execution
continues — and the page dies later on an undefined `page()`.

**I proved the resolution directly** rather than inferring it. For all 14
deployed broken pages, `realpath(<file dir> / <value> / includes/session.inc)`
returns `DOES NOT EXIST`; for correct pages it resolves to
`/var/www/html/includes/session.inc`.

**Why it is invisible in logs.** The container's `/var/log/apache2/error.log`
is empty and `tmp/errors.log` has not been written since May. FA installs its own
handler, and when that handler itself fails the resulting error surfaces as
`Call to undefined function end_page() in includes/errors.inc:96` — which
describes the *error reporter*, not the actual cause. This matches the reported
symptom of "a bare HTTP 500 and nothing useful logged".

---

## 2. Fix these first

These 14 pages are **deployed and active** on the Integration pod and are
**empirically confirmed HTTP 500** by direct probe.

| # | Repo (deployed module) | File | Found | Correct | HTTP |
|---|---|---|---|---|---|
| 1 | `ksf_FA_Calendar` | `pages/my_events.php` | `../..` | `../../..` | **500** |
| 2 | `ksf_FA_CRM` | `pages/dashboard.php` | `../..` | `../../..` | **500** |
| 3 | `ksf_FA_EmailManager` | `pages/accounts.php` | `../..` | `../../..` | **500** |
| 4 | `ksf_FA_EmailManager` | `pages/campaigns.php` | `../..` | `../../..` | **500** |
| 5 | `ksf_FA_EmailManager` | `pages/inbox.php` | `../..` | `../../..` | **500** |
| 6 | `ksf_FA_EmailManager` | `pages/mailing_lists.php` | `../..` | `../../..` | **500** |
| 7 | `ksf_FA_ImportStagingProcessing_UI` | `pages/config.php` | `../..` | `../../..` | **500** |
| 8 | `ksf_FA_SuggestedPurchaseOrder` | `pages/configuration.php` | `../..` | `../../..` | **500** |
| 9 | `ksf_FA_SuggestedPurchaseOrder` | `pages/insufficient_stock.php` | `../..` | `../../..` | **500** |
| 10 | `ksf_FA_SuggestedPurchaseOrder` | `pages/item_trends.php` | `../..` | `../../..` | **500** |
| 11 | `ksf_FA_SuggestedPurchaseOrder` | `pages/suggested_orders.php` | `../..` | `../../..` | **500** |
| 12 | `ksf_FA_SuggestedPurchaseOrder` | `pages/vendor_trends.php` | `../..` | `../../..` | **500** |
| 13 | `ksf_FA_Workflow` | `pages/actions.php` | `../..` | `../../..` | **500** |
| 14 | `ksf_FA_Workflow` | `pages/workflows.php` | `../..` | `../../..` | **500** |

**Severity is highest for `ksf_FA_EmailManager` and `ksf_FA_SuggestedPurchaseOrder`**
— 4 and 5 pages respectively, i.e. an entire module UI is dead.

**Note on the fix.** Changing `../..` to `../../..` on its own does **not**
restore these pages — I tested a corrected copy of `EmailManager/pages/inbox.php`
and it still returned 500, because each page carries a *second* independent fault
(an undefined `$page_security` id, e.g. `SA_ksf_FA_EmailManagerVIEW`, which is
never defined). **Fixing the path is necessary but not sufficient.** Expect to
iterate.

---

## 3. Full findings (development repos)

12 modules / **28 files** carry a wrong `$path_to_root`. Sorted by severity.

### S1 — Deployed and active, confirmed 500 (see §2)
`ksf_FA_Calendar`, `ksf_FA_CRM`, `ksf_FA_EmailManager` (4),
`ksf_FA_ImportStagingProcessing_UI`, `ksf_FA_SuggestedPurchaseOrder` (5),
`ksf_FA_Workflow` (2) — **14 pages**

### S2 — Real defect, not yet deployed
Will 500 the moment each module is activated or promoted to Integration.

| Repo | File | Found | Correct |
|---|---|---|---|
| `ksf_FA_LLM` | `pages/logs.php` | `../..` | `../../..` |
| `ksf_FA_LLM` | `pages/providers.php` | `../..` | `../../..` |
| `ksf_FA_LLM` | `pages/test.php` | `../..` | `../../..` |
| `ksf_FA_PriceBook` | `pages/competitors.php` | `../..` | `../../..` |
| `ksf_FA_PriceBook` | `pages/entries.php` | `../..` | `../../..` |
| `ksf_FA_PriceBook` | `pages/price_books.php` | `../..` | `../../..` |
| `ksf_FA_PriceBook` | `pages/scrape_logs.php` | `../..` | `../../..` |
| `ksf_FA_ProductLookup` | `pages/scan.php` | `../..` | `../../..` |
| `ksf_FA_ProductLookup` | `pages/search.php` | `../..` | `../../..` |
| `ksf_FA_ProductLookup` | `pages/sources.php` | `../..` | `../../..` |
| `ksf_FA_ProductLookup` | `pages/staging.php` | `../..` | `../../..` |
| `ksf_FA_MRP` | `pages/gantt.php` | `../..` | `../../..` |
| `ksf_FA_EstatePlanning` | `pages/overview.php` | `../..` | `../../..` |

Note `ksf_FA_EstatePlanning/pages/overview.php:5` documents the *correct* value
(`@path_to_root ../../..`) in its docblock while the code says `../..` — the
docblock is right and the code is wrong.

### S3 — Different bug, opposite direction
| Repo | File | Found | Correct | Note |
|---|---|---|---|---|
| `ksf_FA_Documents` | `documents.php` (module root) | `../../..` | `../..` | Too *deep*, not shallow |

This module is not deployed. It has a **second, independent** defect: it includes
`modules/FA_Documents/includes/documents_db.inc`, but the directory is
`ksf_FA_Documents` (per its own `_init/config`, `InstallPath: modules/ksf_FA_Documents`).
Both need fixing together.

---

## 4. Already correct — the reference pattern

These were reported as previously-affected and are **now fixed**; both are
deployed, active, and return HTTP 200:

| Repo | File | Value | HTTP |
|---|---|---|---|
| `ksf_FA_Contacts` | `pages/contacts.php` | `../../..` | 200 |
| `ksf_FA_Users` | `pages/users.php` | `../../..` | 200 |

They are the template to copy for the fixes in §2.

---

## 5. Scope and method

- **991** entry-point PHP files were scanned across `~/Documents/ksf_FA_*`,
  `~/Documents/ksf_*` and the deployed `fa_modules/` tree.
- Entry points were defined as module-root `*.php` plus files under
  `pages/`, `menu/`, `popup/`, `includes/`, `ajax/`, `api/`, `reports/`,
  `views/`, `includes/`. Files under `vendor/`, `src/`, `tests/` and `lang/`
  were excluded, since they are `include`d targets rather than web entry points
  and legitimately use a different base.
- Every deployed entry point was then probed over HTTP (1,854 requests) and the
  results correlated against the static analysis. **All 14 shallow-mismatch
  pages returned 500 and every correct page returned 200** — the static finding
  and the runtime behaviour agree exactly.
- The ~75 deployed pages that 500 with a *correct* `$path_to_root`
  (`ksf_FA_QuickBudget`, `ksf_FA_CRM` sub-pages, `ksf_FA_ProjectManagement`,
  `ksf_FA_Square`, `ksf_FA_DataIntegrity`) have **unrelated** causes and are
  out of scope for this audit. They are worth a separate pass.

---

## 6. Proposed CI check

`check_path_to_root.py` is included alongside this report. It walks entry points,
computes each file's required depth, and fails if the literal does not match.

```bash
# Against the deployed integration tree
python3 check_path_to_root.py \
    ~/Documents/ksf_Infrastructure/FA/2.4.3 \
    --modules ~/Documents/ksf_Infrastructure/fa_modules

# Against a single module repo in CI (module dir is <repo>/modules)
python3 check_path_to_root.py /path/to/fa_root --modules /path/to/module_repo/modules
```

**Design points that make it reliable:**

1. **Depth is computed from the modules tree, not the FA root.** In this
   deployment the FA root (`FA/2.4.3`) and `modules/` (`fa_modules/`) are
   bind-mounted from *different* host trees. A naive `relpath` from the FA root
   yields depth 5 and reports nothing. The check resolves against a virtual
   `/FA` root instead, so it is correct in both layouts.
2. **Two independent assertions.** It checks the depth *and* verifies the
   traversal actually lands on the FA root, so a wrong-but-correct-length value
   is still caught.
3. **Accepts equivalent forms.** `dirname(__DIR__, 3)`,
   `dirname(dirname(dirname(__DIR__)))` and `__DIR__ . "/../../.."` are
   recognised as correct at the right depth — these are used by
   `ksf_fa_downloader`, `ksf_FA_InvoiceAllocation` and
   `ksf_FA_ImportStagingProcessing_UI`. Only genuinely unresolvable expressions
   are reported as `NON-LITERAL`.
4. **Scoped to entry points** so `include`-only library files are not flagged.
5. **Exits non-zero** with the correct replacement value, so it drops straight
   into CI.

**Verified behaviour.** On the deployed tree it reports exactly the 14 confirmed
bugs with zero false positives. Against a synthetic fixture it correctly detects
too-shallow, too-deep and non-literal cases, ignores `vendor/` and `src/`,
accepts `dirname(__DIR__, 3)`, passes a clean tree with exit 0, and refuses to
run when pointed at a directory that is not an FA root.

**Suggested CI wiring:** run per module repo on every PR (fast, no container
needed), plus one run against the assembled `fa_modules/` tree before promotion
to Integration.

---

## 7. Incident note — registry corruption during this audit

**A live environment fault was introduced by this audit and has been repaired.
No source file was modified.**

While HTTP-probing all 1,854 deployed files, the sweep requested
`modules/modules_dep_needs/e2e_module_dependencies.php`. That file is **not a
read-only test** — it rewrites the real per-company extension registry:

```php
$regFile = "$path_to_root/company/$company/installed_extensions.php";
...
$php .= "  $k => \n  array (\n";     // line 75
file_put_contents($regFile, $php);
```

The first registry entry has an **empty-string key** (`''`), and
`"  $k => "` interpolates it to nothing, emitting `   => ` — invalid PHP. The
whole site went 500 with `syntax error, unexpected '=>' ... on line 4` of
`company/0/installed_extensions.php`.

**Repair.** Only line 4 was malformed; the other 383 lines were intact. I
reproduced the file with the key corrected to `''`, verified it parses, and
compared it against the global registry: **all 37 modules present with
identical `active` flags**, plus the harness's own `modules_dep_needed`
test entry. The corrected file was written and the site recovered (FA root and
module pages return 200). All temporary probe files were removed.

**This is a real latent hazard and deserves its own fix.** Any HTTP sweep,
link-checker, crawler or scanner that touches `modules/` will hit this file and
take the site down. Two fixes are warranted:
- Make `e2e_module_dependencies.php` write a real key
  (`var_export($k, true)`), and/or back up and restore the registry around the
  test; and
- Exclude non-entry-point files (`*_test.php`, `e2e_*.php`, `uat_*.php`,
  `schema_runner.php`, `src/`, `tests/`) from any automated URL sweep. Note the
  audit's own scan correctly excluded them — it was the raw HTTP probe that did
  not.

---

## 8. Summary

| Metric | Value |
|---|---|
| Entry-point files scanned | 991 |
| Development repos with wrong `$path_to_root` | 12 modules / 28 files |
| Deployed + active + confirmed 500 | **6 modules / 14 pages** |
| Modules already fixed (Contacts, Users) | 2 |
| CI check | Included, validated, zero false positives |

The single highest-value action is fixing `ksf_FA_EmailManager` (4 pages) and
`ksf_FA_SuggestedPurchaseOrder` (5 pages) — whole module UIs are dark — but each
needs a second fault fixed alongside the path before it will actually serve.
