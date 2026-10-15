# AGENTS.md — KSF FrontAccounting Architecture Notes

Operational memory for the KSF FA infrastructure codebase.

Files live under `/home/kevin/Documents/.

Git repositories (dev trees) live under /home/kevin/Documents/<modulename>.

Files deployed for Integration Testing live under ksf_Infrastructure/fa_modules/`.
This doc captures cross-module architecture **decisions** and findings. 
Read this before designing or refactoring anything that spans modules.

> **Companion doc:** `AGENTS_ARCH.md` (co-located, hardlinked into each repo)
> holds the shared module **conventions** and cross-repo engineering standards
> (module layout, coding/testing standards, dev/deploy workflow, inter-module
> hook protocols, security-area registry, FA DB gotchas). This file holds only
> decisions.

## ksf_payment_destinations — development tree status

**`~/Documents/FA_PaymentDestinations/` is an ABORTED branch.** Do not develop
there. That directory is a bind mount (via `~/Documents/ksf_Infrastructure/`)
that was used for documentation only — it has no `src/`, no `Tests/`, no
PSR-4 refactoring, and no `@BABOK` traceability annotations. All development
happened in `~/Documents/ksf_payment_destinations/` which is the primary
working dev tree.

If you find yourself editing files in `FA_PaymentDestinations/` — STOP and
switch to `ksf_payment_destinations/` immediately.

## Cross-module facts (at a glance)

- **PHP 7.3 is the cross-module compatibility floor** (current prod runs 7.3 on
  Fedora 30 until a web container is stood up; the FA container runtime is 7.4).
  See `AGENTS_ARCH.md` §1.
- **ksf_FA_Common is now a pure Composer/Packagist package** (v1.0.11), not an FA
  module. It was gutted to a no-op module shell. Owning modules (RBAC, CRM,
  Calendar, HRM, Assets) register/unregister their `ksf_contact_types` on
  activate/deactivate via embedded `sql/retag_contact_types.sql`.
- **ComposerDependencies bootstrap is per-module**: modules copy
  `ksf_fa_common/src/Utils/ComposerDependencies.template.php` to their root and
  replace `MODULENAME` in the namespace; the guard is namespace-scoped so unrenamed
  (forgotten `MODULENAME`) copies — and the package's own `Common\Utils` copy — can
  never redeclare or clobber. Details in `AGENTS_ARCH.md` §7.
- **Square**: composer.json `config.platform.php = 7.4.33` pinned (commit
  `b0ef4da`) for the PHP 7.4 container. The lock is no longer blocked — the
  blocker was a phantom `ksfraser/import-staging` require (not on Packagist, and
  the `ksfraser\FrontAccounting\ImportStaging\*` classes are autoloaded by the
  `ksf_FA_ImportStagingProcessing` module's own vendor). Removed in commit
  `493291f`; the vendor now resolves for 7.4 (http-foundation 5.4, csv 9.8).
- **Vendor/runtime PHP mismatch is the top source of site-wide 500s.** The host
  runs PHP 8.1 and the container 7.4, so a module without a
  `config.platform.php` pin resolves for the wrong PHP. Symptoms are a
  PHPUnit-10 eager-autoload `Parse error` (masked by FA's
  `Call to undefined function end_page()`) or a `platform_check.php`
  `E_USER_ERROR` naming a required PHP >= 8.1.2. Diagnose with
  `ksf_Infrastructure/fa-modules-doctor.sh`, which probes the real container
  rather than guessing package versions. Full procedure in
  `ksf_Infrastructure/AGENTS_APPENDIX.md`.
- **Per-environment port map (decided 2026-10-01) — the target layout.** Each
  environment takes a base and each service a fixed slot offset, so a whole
  stack can be relocated by changing one number:

  | slot | service | prod | UAT | Integration | dev |
  |---|---|---|---|---|---|
  | base | *(reserved — `sso`/`kube`-class services)* | 8080 | 8090 | 9000 | 9010 |
  | +1 | *(reserved)* | 8081 | 8091 | 9001 | 9011 |
  | +2 | **FrontAccounting** | 8082 | 8092 | 9002 | 9012 |
  | +3 | **Nextcloud** | 8083 | 8093 | 9003 | 9013 |
  | +4 | **WordPress** | 8084 | 8094 | 9004 | 9014 |
  | +5 | **phpMyAdmin** | 8085 | 8095 | 9005 | 9015 |

  Slots `base` and `+1` are deliberately left unallocated because those are the
  numbers other roles in `/root/.ansible/roles` want: `ksf.sso` binds `8080`
  (`sso_http_port`), and `ksf.kube`/`ksf.suitecrm`/`mrlesmithjr.netdata` bind
  `9000`. Leaving `base`/`+1` free means a stack can host those roles without
  moving the application services. Two soft overlaps remain for *other* roles'
  own defaults and only matter if those roles are added to a stack later:
  `ksf.qbittorrent` (`qbittorrent_port: 8085`) and `ksf.ocrmypdf`
  (`ocrmypdf_webservice_port: 8095`). MariaDB is not slotted yet — it currently
  publishes `3307` (container) against the host's own `3306`.

  **RUNNING OVERLAP — the live containers do NOT match this map yet.** The
  ports below are pre-migration and are superseded by the table when the stacks
  are rebuilt by the Ansible role. Do not "fix" a live pod by hand to match the
  table; rebuild it.

- **Two FA containers run at once and share one vendor tree.** Rootful
  `ksfii_app-fa` on **8090** (overlay `FA/ksfii_app`) and rootless `ksf-fa` on
  **8080** (overlay `FA/ksf_fa`, driven as `su - kevin -c`). **These two ports
  are pre-migration leftovers, not the plan** — see the port map above. Both are PHP
  7.4.33 and both bind-mount `ksf_Infrastructure/fa_modules` at
  `/var/www/html/modules`, so a bad vendor breaks both, but extension activation
  is **per-instance** (separate `company/<id>/installed_extensions.php`). A module
  can be a live landmine on one pod and dead code on the other, so always check
  both before deciding something is harmless.
- **FA_ProductAttributes issue #52 (child not detected as read-only)** root cause
  found: two parallel, un-unified parent-relationship mechanisms. Full write-up
  is in that repo's `AGENTS.local.md` (migrated out of this file).

## The "generic data-dictionary + query-builder" direction (active design)

The user wants a **generic, transport-agnostic** data-dictionary + SQL query
builder package (suggested name `ksf_common_db`), NOT another DB class, and NOT
in `ksf_FA_Common` (whose naming is FA-module-specific). Core requirement:

> An interface defines the SQL query commands. A translation layer maps them to
> MySQL commands when outside FA, and to FA's procedural `db_*` functions when
> inside FA, so the correct implementation can be DI'd.

Requirements/goals captured from discussion:
- Want the **data dictionary + query builder** capabilities (from the legacy
  `ksf_modules_common` `MODEL`/`fa_MODEL` framework).
- **No third parallel DB-class abstraction** on top of what exists.
- Lifecycle (pre/post CRUD) hooks should be able to tie into this system.
- Package should be usable standalone (tests, CLI, other frameworks), not just
  inside FA.

### The pattern ALREADY exists / is partially realized (critical to not rebuild)
1. **RBAC's `DbAdapterInterface` + `FaDbAdapter` (now generalized)** — the exact
   two-part interface→FA-translation pattern the user described: `fetchAssoc`, `fetchAll`,
   `executeUpdate`, `lastInsertId`. `FaDbAdapter` substitutes `?` placeholders via
   `mysqli_real_escape_string` (FA has NO prepared statements) and regex table prefixing.
   This served as the proof of concept and has been **genericized into the
   `ksfraser/ksf-common-db` package** (`ksfraser\CommonDb\Contract\DbConnectionInterface` /
   `ksfraser\CommonDb\Adapter\FaDbAdapter`); the RBAC-local copies were deleted. See that
   package's `APPENDIX.md` for the migration.
2. **Legacy `ksf_modules_common` (procedural, older)** — the actual data-dictionary +
   query-builder the user remembers:
   - `class.MODEL.php` — `fields_array` + `table_details['tablename']`/`['primarykey']`
     dictionary; clause builders `buildSelect/From/Where/Join/GroupBy/Having/OrderBy/Limit`
     assembled by `buildSelectQuery()`; CRUD `select_row`, `select_table`,
     `insert_table`, `update_table`, `delete_table`, `ReplaceQuery`, `create_table`,
     `alter_table`; `define_table()` derives tablename from class name + company prefix.
   - `class.fa_MODEL.php` — FA subclass; sets `company_prefix = TB_PREF`.
   - `class.eventloop.php` — Observer pattern event dispatcher: `ObserverRegister`,
     `ObserverNotify` (with `'**'` wildcard = all), subscribers implement `notified()`.
   - **CAVEAT**: the `eventloop` Observer hooks are wired only for `NOTIFY_INIT_TABLES`
     → `create_table` and logging. They are NOT wired into `insert_table`/`update_table`/
     `delete_table` as pre/post CRUD points. The `tell_eventloop(..., "NOTIFY_LOG_*", ...)`
     calls are largely logging noise.
3. **Modern ksf_FA_Common traits (OOP, current recommendation for hooks)**
   - `src/Traits/WorkflowHooksTrait.php` — SuiteCRM-style lifecycle hooks. Register a
     record type → hook prefix via `registerWorkflowType($recordType, $hookPrefix)`.
     `fireWorkflowHook()` builds `{prefix}_{hookKey}` and calls `hook_invoke_all(...)`.
     Hook keys: `before_save`, `after_save`, `before_delete`, `after_delete`, `new`,
     `edited`, `linked`, `unlinked`. Convenience dispatchers + `fireWorkflowHooks()`
     runs the full ordered sequence.
   - `src/Traits/CrudOperationsTrait.php` — `createRecord()` / `deleteRecord()` wrappers
     that fire pre-save → create → new/edited → post-save (and pre-delete → delete →
     post-delete), delegating the actual DB work to overridable `*Internal()` methods.
   - Both live in `ksfraser\FrontAccounting\Common\Traits\` (namespace is FA-flavored).
   - Adoption is currently minimal: ksf_FA_Common's own unit tests +
     `ksf_FA_HRM/hooks.php`. Not yet rolled out module-wide.

### Naming observation
The `registerWorkflowType($recordType, $hookPrefix)` + `{prefix}_{operation}` scheme
already achieves what the user proposed as "DB class reads `$table_name` to build
pre/post hook name." `$table_name` should map to a hook **prefix**, not be the literal
hook name. Per-table hooks use `hook_invoke_all` (module-oriented dispatcher from
`includes/hooks.inc`) — consistent with FA, zero new infra. If literal table-derived
names are wanted, add a small table→prefix mapper, don't build a new dispatcher.

### PDO question (decided: YES, PDO is the standalone impl; FA uses its own adapter)
FA's DB layer is mysqli-based, NOT PDO (`includes/db/connect_db_mysqli.inc` uses
`mysqli_connect/query/insert_id/errno/fetch_row`; procedural `db_query`/`db_escape`/
`db_fetch_assoc`/`db_insert_id` wrappers; FA has NO prepared statements).

Design: **make PDO the consumer contract of the interface, not the transport.** Two
implementations of one `DbConnectionInterface` (PDO-style ops: query, executeWithParams,
fetchAll, fetchAssoc, insertId, quote, beginTransaction/commit/rollBack):
- `PdoDbAdapter` (standalone: tests/CLI/other frameworks) — nearly a 1:1 PDO wrapper,
  real prepared statements, multi-driver.
- `FaDbAdapter` (inside FA) — maps each method to FA `db_*`/mysqli calls, resolves
  `?`/`:name` placeholders to escaped literals (FA has no prepared statements), exactly
  like the FA adapter in `ksf-common-db` (`mysqli_real_escape_string` binding + regex
  prefixing).

**HARD RULE (user directive): FA modules MUST use native `db_*` calls at runtime.**
PDO is ONLY for the standalone/portable side (tests, CLI, non-FA embedding). The FA
adapter is the single, mandatory implementation inside FA and must delegate every
operation to FA's procedural `db_query`/`db_escape`/`db_fetch_assoc`/`db_insert_id`/
`db_num_rows`/`db_error` etc. — never a PDO handle, never raw mysqli. PDO is the
portable *contract shape*, not a runtime transport for FA. (Note: PDO is an optional
for the FA side: the only reason to depend on it at all is standalone usage; the FA
adapter itself needs no PDO.)

PDO and FA never meet; they are alternative DI implementations of a shared contract.
This satisfies the user's requirement: "interface that translates SQL to MySQL outside
FA but `db_*` inside FA so the right classes can be DI'd." This is realized by the
`ksf-common-db` package's `DbConnectionInterface` + `FaDbAdapter`/`PdoDbAdapter`.

### ksf_common_db package — implemented
The `ksfraser/ksf-common-db` package (namespace `ksfraser\CommonDb`) exists at
`~/Documents/ksf_common_db`, is published on Packagist (`v1.0.0`), and RBAC has
been migrated onto it. **Repo-specific implementation/packaging/migration/gotcha
notes live in that repo's `APPENDIX.md`** — see there for structure, consumers'
dependency convention, the RBAC migration, and the implementation gotchas. This
section only records the shared design decisions.

Structure (high level):
- `src/Contract/DbConnectionInterface.php` — PDO-shaped contract: `fetchAssoc`,
  `fetchAll`, `fetchScalar`, `executeUpdate`, `lastInsertId`, `quote`, `beginTransaction`,
  `commit`, `rollBack`. Accepts `?` (positional) or `:name` (named) placeholders.
- `src/Adapter/FaDbAdapter.php` — FA runtime adapter; native `db_*` only.
- `src/Adapter/PdoDbAdapter.php` — native PDO + prepared statements (NOT for FA runtime).
- `src/Dictionary/TableDefinition.php` — data dictionary + CREATE/INSERT/UPDATE/DELETE SQL.
- `src/Query/QueryBuilder.php` — fluent parameterized SELECT builder.

NEXT STEPS (cross-module): port other modules' DAOs onto `DbConnectionInterface` +
`TableDefinition`/`QueryBuilder`, then wire the pre/post workflow hooks
(`WorkflowHooksTrait`/`CrudOperationsTrait` from ksf_FA_Common) onto the DAO layer.

## FA core hook system (reference)

`includes/hooks.inc`:
- `hook_invoke($ext, $method, &$data, $opts)` / `hook_invoke_all($method, &$data, $opts)`
  / `hook_invoke_first` / `hook_invoke_last` — dispatch to `$Hooks` extension objects.
- Transaction-level DB hooks exist: `hook_db_prewrite`, `hook_db_postwrite`,
  `hook_db_prevoid` → `hook_invoke_all('db_prewrite'|'db_postwrite'|'db_prevoid', $cart,
  $type)`. These are CART/transaction scoped (sales orders, invoices, etc.), NOT
  per-row CRUD. Per-row CRUD hooks are not provided by core; they come from the
  traits/adapters above.

## FA_ProductAttributes — module/tree-specific findings moved to its own repo

Anything FA_ProductAttributes-specific that used to live here (issue #52 root
cause, Generate Combinations semantics, the ksf-fa blank-page/bootstrap logs for
that module) has been migrated OUT of this shared file into the repo's
`AGENTS.local.md` (`~/Documents/FA_ProductAttributes/AGENTS.local.md`). Working
on that module? Read that file. This shared doc keeps only cross-module
decisions and mechanics.

## FA extension install & activation mechanics (verified 2026-09, cross-module)

How FA 2.4.x actually installs/activates third-party extensions — applies to
every ksf_* module, and is why "clicks on the Extensions page" silently do
nothing on a fresh mount. Verified against `fa/2.4.3` source + live UAT box.

**Registries** — two PHP files of `$installed_extensions` arrays:
- GLOBAL: `company/installed_extensions.php` (what "Local<pkg>" and the
  repo-index install write to).
- PER-COMPANY: `company/<id>/installed_extensions.php` — this is what
  activation (Refresh/Update) actually reads and rewrites.
Both must be writable by the container's PHP/MySQL UID (see the per-instance
bind fix in the repo-local notes).

**Registering a local module**: the `Local<pkg>` button
(`local_extension()` in `admin/inst_module.php`) hardcodes
`'version' => '-', 'available' => ''` and copies nothing from the module's
`_init/config`. It includes the module's `hooks.php` and calls
`install_extension(false)`.

**Activivating** (the "Activated for '<company>'" view, `extset=<id>`):
- Checkboxes are named `Active<i>` where `$i` is the index in the MERGED +
  natural-sorted GLOBAL registry list, NOT the company registry. Map each row's
  checkbox to its package name from the page HTML before POSTing.
- POST `extset=<id>&Refresh=Update&Active<i>=1` (needs the current `_token`).
- Gate: `check_src_ext_version()` in `includes/packages.inc` rejects any
  version with a leading component below the app's (`2.4.3`). **A version of
  `'-'` ALWAYS fails** → "incompatible with current application version and
  cannot be activated". Private/local modules therefore MUST carry a numeric
  version in the registries (manually set what `_init/config` declares, e.g.
  `'2.4.4'`), the same value the repo index would have supplied.
- `activate_hooks($pkg, $comp, true)` then calls the module's
  `hooks_<pkg>::activate_extension($comp, false)`.

**`Refresh=Update` is a full-state replace, not a delta.** The handler toggles
every listed row: `$ext['active'] ^ check_value('Active'.$i)`. A module that is
active but whose checkbox is **not** submitted gets **deactivated**. So a POST
must include `Active<i>=1` for *every* module that should end up active, not just
the ones being changed. Submitting only the one box you want to turn on silently
turns everything else off.

**`Delete<i>` / `Active<i>` are GLOBAL array keys, not company positions.** They
index the array literal in `company/installed_extensions.php`, so the ids get
sparse (`0,1,5,15,16,...`) and shift every time something is deleted. Never
compute a control name from the company registry or from a previous response —
re-parse the page and match the package name in the same row. (`Delete` with no
number is a literal key `0`-less name, i.e. a genuinely different id.)

**Fixing a stored `'-'` version goes through the UI, not the file.** A module
already registered keeps its stale version, so re-activating it fails the gate
forever. `local_extension()` (commit `6a00b5d`) now reads `_init/config` via
FA's own `get_control_file()`, so the repair is: `Delete<i>` → `Local<pkg>` →
activate. That is safe on a bind-mounted `fa_modules/` — `uninstall_package()`
only touches `PKG_CACHE_PATH`, and local modules are not in the package cache,
so the module directory and its `vendor/` survive.

**Which registry file is authoritative.** `get_company_extensions(-1)` reads
`/var/www/html/installed_extensions.php`; `update_extensions()` writes that
global file and then copies it down to each `company/<id>/`, preserving only
`active` **by array key**. So a stale global poisons every company registry on
any install or activate. Verify the global file is actually the bind-mounted one
by comparing sizes (`stat -c%s` on both sides) — on `ksfii_app-fa` the bind is
NOT effective and FA writes a container-local copy, so the repo's
`FA/ksfii_app/installed_extensions.php` is stale and a container recreate would
lose the real global list. `ksf_fa` does bind correctly.

**SQL prefix convention in module `sql/` files**: the install engine
`db_import()` (`admin/db/maintenance_db.inc`) replaces ONLY the literal
`0_` → `TB_PREF`. It does NOT touch `{TB_PREF}` or `@TB_PREF@` (those only
work in ksf_FA_Common's own hand-rolled `install_schema()` helper). **All
extension `sql/*.sql` for the FA install path must use literal `0_` table
names** — `{TB_PREF}` yields "Table 'ksf_fa.{TB_PREF}x' doesn't exist".
(FA_ProductAttributes had 4 files with `{TB_PREF}`; fixed to `0_` in commit
`b9f484e`.)

**Login gotcha** (`includes/session.inc:545`): without `company_login_name`
in the POST, login always fails with 401 "Incorrect Password" even when the
user/password is right. Send `company_login_name=<id>` (+ `_token` from the
login page).

**Cross-module activation hazard — duplicate ksf-fa-common class load**:
`ksf_FA_Common` ships `src/autoload.php` as the canonical loader for the
`ksfraser\FrontAccounting\Common\*` namespaces and explicitly must NOT have a
PSR-4 pointing at a vendored copy. If another module's Composer autoloader
(vendored `ksfraser/ksf-fa-common`, e.g. FA_ProductAttributes') loads those
classes FIRST, then activating ksf_FA_Common (constructor `require_once
src/autoload.php`) redeclares the already-loaded classes → fatal that kills
the extension page mid-render (page shows footer only, no message, no
registry write). Symptom: activation "does nothing". On the UAT box the
workaround was manual activation (schema via raw SQL, `active => true` set
directly in both registries). Proper fix is order-independent guarded
loading in `src/autoload.php`.

**Rootless podman single-file binds silently absent — the "nothing happens"
activation trap (diagnosed 2026-09)**: on the rootless ksf_fa instance (podman
under user `kevin`), the ksf-fa container appeared to have all 6 binds per
`podman inspect`, but the **single-file** binds (config_db.php,
installed_extensions.php, default.css) were NOT effective — `/proc/mounts` showed
only the 3 directory binds. So FA wrote the RO git-tracked
`FA/2.4.3/installed_extensions.php` as the global registry and failed with
"Cannot open the extension setup file '../installed_extensions.php' for writing."
Root cause was stale recipes with lowercase `../fa/…` paths + a `fa_data` named
volume that didn't exist. Fix = recreate the container; a fresh create applies
the file binds (legacy `compose.yaml` deleted, `start-fa.sh` rewritten). Rule:
after any container create/modify, verify with
`podman exec <c> grep -l config_db /proc/mounts` — don't trust `inspect`.

**ROOTFUL single-file binds go dead on any inode-replacing write (root cause
found 2026-10-01).** The *same* dead-inode failure hit `ksfii_app-fa` (8090),
and this time the real cause is confirmed: a single-file bind resolves to one
**inode**, not to the path. `sed -i`, `rsync` (without `--inplace`), `git
checkout`, or any write-then-rename tool **replaces the inode**, so the
container keeps reading the *unlinked original* forever while the host path
holds brand-new content. Symptom set on 8090: registry stale (15 host entries
vs the container's live 16, missing `ksf_Calendar`), `default.css` stale, and
`config_db.php` stale — all three with `podman inspect` naming the correct
source path, so the bind *looks* correct. Diagnosis is `stat -c%i` on both
sides, never `inspect`. Rules:
- Never edit a single-file bind target with `sed -i`. Use `cat src > dst` /
  `tee` (truncate-in-place, keeps the inode) or `rsync --inplace`.
- After ANY container create **or** after editing `config_db.php`,
  `installed_extensions.php`, or `default.css`, re-run the inode check on all
  six mounts. An inode-only change is invisible to a diff and to HTTP probes.
- Recover by recreating the container *only after* fixing the host files, since
  recreating makes the binds effective for the first time and will hand the
  host's content to the app immediately.
- `podman/ksf-compose.yaml` was **DELETED 2026-10-01**. It was a second,
   competing container spec that nothing referenced; `podman-compose` 1.0.6
   could not parse it, and its `ksfii-app` service disagreed with the real
   container on image (`ksf-iiapp:latest` vs `ksf-fa:php7.4`), name
   (`ksfii-app` vs `ksfii_app-fa`) and network (`ksf_network` vs `ksfii_app`).
   Do not reintroduce it. The single source of truth for the FA container spec
   is `ansible/roles/ksf.frontaccounting/tasks/container-run.yml`.
- The provisioner also needs `ansible/ansible.cfg`. Without it Ansible resolves
   roles from `/root/.ansible/roles` (a DIFFERENT repo, `ksfraser/ksf_ansible`)
   and cannot find `ksf.mariadb`/`ksfii_app` at all, because the plays live in
   `ansible/plays/` while the roles live in `ansible/roles/`. That is why these
   containers were built by hand rather than by the playbook.
- `ansible/roles/ksf.frontaccounting/tasks/verify_binds.yml` runs as `post_tasks`
   on every FA play: it compares each bind's host inode against the container's,
   and re-creates the container when they differ. This is what stops the
   `ksfii_app` role from silently re-breaking the global registry bind by
   templating it after the container is already running. Do not rely on task
   ordering to keep binds alive — verify instead.

**The two stacks have DIFFERENT DB credentials — never copy one
`config_db.php` over the other (found 2026-10-01).** Rootless `ksf-fa` (8080)
talks to container `ksf-mariadb` with `ksf_user` / `ksfuser2024!`; rootful
`ksfii_app-fa` (8090) talks to `ksfii_app-mariadb` with `ksf_user` /
`ksfuser2026!` (root pw `m1l1ce_db_root_2026!`, DB `ksf_fa`, 177 tables). The
rootful host copy had been seeded from the rootless file, so it named the
non-resolving host `ksf-mariadb` with the rootless password; that is why the
bind was dangerous to fix — recreating alone would have handed FA a config it
could not connect with. Change the DB host *and* password together, then
verify from inside the container by `include`-ing the real
`/var/www/html/config_db.php` and counting `information_schema` tables.

**FA theme customization (decided 2026-09, cross-module)**

Per-pod theme overlays **mirror the native FA tree** (`/var/www/html`), so the
mount paths are the real FA locations. Inside each pod dir
(`FA/<pod>/themes/default/`) we keep:

- `default.css` — the **canonical** file, bind-mounted RW into the container at
  `/var/www/html/themes/default/default.css`. This is what the running app
  loads (`user_theme()` default is `'default'`; CSS is
  `$path_to_root/themes/default/default.css` via `includes/main.inc`).
- `default.css.default` / `default.css.red` / `default.css.yellow` — **unmounted**
  variants. On a fresh environment, copy the chosen variant onto the canonical
  `default.css`; the recipe (ansible role `ksf.frontaccounting`, `fa_theme` var,
  staged by `tasks/theme.yml`) automates this before container start.

Decisions: private modules mount **only** the `default.css` file; do not overlay
`renderer.php`/`index.php`/`images/` (those stay read-only from the `2.4.3`
mount). Target look: **Integration = RED**, **UAT = YELLOW**, default = original
BLUE. The recipe applies `default.css.<fa_theme>` → `default.css` (never edits
the variants). `fa_theme` defaults to `default` and **nothing sets it per
environment** — both pods currently serve blue, so the Integration=RED /
UAT=YELLOW target is still unimplemented; setting `fa_theme` per environment in
the inventory is the remaining step. `tasks/scaffold.yml` now creates all three
variants (`c7649b1`; it previously created only `.default` and `.red`, so
`fa_theme: yellow` failed on a fresh pod). Container mounts are defined once, in
the ansible role's `container-run.yml`.
