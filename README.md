# KSF Architecture Docs

Working notes and requirements for the KSF FrontAccounting stack. Created
2026-10-11 during the Calendar / Attachments / Email work.

These are DECISION and ANALYSIS records, not module source. Module code lives in
each module's own repository.

| Document | Purpose |
|---|---|
| `CampaignBuilder_Analysis.md` | What the three CampaignBuilder repos actually contain vs what their docs claim |
| `EmailManager_Analysis.md` | Same for EmailManager; root cause of its HTTP 500s |
| `EmailManager_DebtorResolution_Fix.md` | The `debtors_master.email` defect and the corrected resolution |
| `path_to_root_Audit.md` | Cross-module audit of the `$path_to_root` depth bug |
| `check_path_to_root.py` | Automated check for that bug (CI candidate) |
| `PageController_Refactor_Plan.md` | Migrating `pages/*.php` to root controllers + SRP views/handlers |
| `Column_Level_ACL_Design.md` | Column-level ACL for `ksf-common-db`: push-down vs post-fetch, inference-oracle matrix, policy contract, phased plan |
| `Explicit_Column_ACL_API.md` | Explicit-column API + `SELECT *` rejection + join-skipping rules; legacy `ksf_modules_common` array-DSL findings |
| `ACL_Two_Approaches.md` | Decision to build BOTH app-layer and DB-layer column ACL; MariaDB view design (session-var blocker, `db_import` prefix hazards), composition rule, phased plan |
| `Schema_Registry_Design.md` | One schema declaration serving query builder + column ACL + workflow UI; should modules return schemas (advertise + resolver, not inline); drift detection by version stamping; `TableDefinition` adoption census |
| `Requirements/` | BABOK requirement docs for inbound email capture |

## Standing decisions

1. **No duplicate core tables.** A module must not re-create a FrontAccounting
   core table. Use the native table. Extra attributes that FA does not model
   belong in a SATELLITE table keyed by the FA core id - never by duplicating
   core rows. (`0_ksf_crm_contacts` violates this; see the analysis docs.)
2. **No cross-module table access.** A consumer asks by hook. A module's schema
   is its own business; a caller cannot judge its usability, because its classes
   may be autoloadable while its tables are absent.
3. **Responders return data, not markup.** Hooks return DTOs / null to decline;
   the CONSUMER renders, via its own SRP view class. Contracts are consumer-owned
   (dependency inversion) until a second consumer justifies a shared package.
4. **`E_USER_ERROR` is uncatchable.** FA's `db_query($sql, $msg)` raises it on a
   failed query, and it is neither an Exception nor an Error, so no try/catch
   intercepts it - the request silently stops mid-render. Verify schemas exist
   rather than relying on exception handling.
5. **Module hooks load at FA bootstrap.** An error in `hooks.php` breaks every
   page in the application. Verify class/method shape against git HEAD before
   deploying; `php -l` is not sufficient.
6. **Modules are three repos**: `ksf_X` (business/Packagist), `ksf_X_UI`
   (presentation), `ksf_FA_X` (FA module: UI + db + security areas).
