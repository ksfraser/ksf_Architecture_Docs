# Known live issues (2026-10-11)

Open defects found during the Calendar / Attachments / EmailManager / HRM /
CRM / PM workstream that are NOT yet fixed.

## 1. `ksf_FA_ProjectManagement` queries a table that does not exist

- Live `information_schema`: `0_fa_pm_task_dependencies` — **0 rows**
- Live `information_schema`: the 10 CPM columns on `0_fa_pm_tasks` — **0 rows**
- Deployed `install.sql`: 9 `CREATE TABLE`, **0 `ALTER`**
- No `upgrade*` file exists in either the dev or deploy tree
- `TaskDependencyRepository` queries the missing table

**Structurally unreachable.** `CREATE TABLE IF NOT EXISTS` against a missing
table would create it, but the table is simply not in any SQL file, and
error 1060 (column exists) is suppressed — so re-running install cannot repair
it either. Needs a real migration.

## 2. 32 `.git` clones inside `fa_modules/`

Deploy tree contains git working trees that duplicate dev checkouts under
`~/Documents`. See ADR-001.

## 3. Shared-doc namespace sync never committed

`AGENTS.md`, `AGENTS_ARCH.md`, `APP_TAB_ARCHITECTURE.md`,
`MODULE_DIRECTORY.md`, `PACKAGIST.md` are hardlinked across ~186 holders and
carry ~918 lines of uncommitted `Ksfraser\` → `ksfraser\` changes. Committed
so far only in: `ksf_Architecture_Docs`, `ksf_FA_CRM`, `ksf_FA_HRM`,
`ksf_FA_Workflow`, `ksf_ProjectManagement`. The remaining ~180 holders still
carry the pending change. Needs a coordinated pass, or a decision to fork the
docs into per-repo copies and end the hardlink coupling.

## 4. `php-error.log` receives nothing

`/var/log/apache2/php-error.log` in the FA container is stale — diagnostics go
to container **stderr** instead. This cost significant time during silent
failure diagnosis. Fix logging before chasing further silent errors.

## 5. Missing schema in other modules

Confirmed absent from the `ksf_fa` database, though the modules are active:

- `ksf_FA_Upc2Item` — 3 tables (`0_ksf_upc2item_*`)
- `ksf_FA_ExpenseReport` — 4 tables (`0_ksf_fa_expense_*`)
- `ksf_payment_destinations`, `ksf_FA_Contacts`, `ksf_FA_Employee`,
  `ksf_FA_Users` — 1 table each

Each declares these in its own `install.sql`, so activation did not run the
installer.

## 6. Stale-sweep failures not yet retested

EmailManager (4), Upc2Item (2), HRM (2), CRM (1), QuickBudget (1) and Square
(1) returned HTTP 500 at last sweep. Several were fixed afterwards; a fresh
sweep has not confirmed the current state.
