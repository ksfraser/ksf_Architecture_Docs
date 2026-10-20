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
| `Table_Naming_Audit_2026-10.md` | Estate-wide table-name audit: every `ksf_FA_*` / `ksf_*` table classified (conforming / FA-core / legacy-suspect / shared store), the `0_fa_*` rename checklist, and the modules whose code addresses a table no schema creates |
| `check_path_to_root.py` | Automated check for that bug (CI candidate) |
| `PageController_Refactor_Plan.md` | Migrating `pages/*.php` to root controllers + SRP views/handlers |
| `Column_Level_ACL_Design.md` | Column-level ACL for `ksf-common-db`: push-down vs post-fetch, inference-oracle matrix, policy contract, phased plan |
| `Explicit_Column_ACL_API.md` | Explicit-column API + `SELECT *` rejection + join-skipping rules; legacy `ksf_modules_common` array-DSL findings |
| `ACL_Two_Approaches.md` | Decision to build BOTH app-layer and DB-layer column ACL; MariaDB view design (session-var blocker, `db_import` prefix hazards), composition rule, phased plan |
| `Schema_Registry_Design.md` | One schema declaration serving query builder + column ACL + workflow UI; should modules return schemas (advertise + resolver, not inline); drift detection by version stamping; `TableDefinition` adoption census |
| `Contact_Access_Inventory_2026-10.md` | Estate-wide inventory of contact access: 144 sites across 46 repositories, classified against FA 2.4.3's own tables and functions |
| `Contact_Ambiguity_Review_2026-10.md` | The 11 contact-data ambiguities, with recommended rulings, costs and a decision order |
| `Party_Account_Model_2026-10.md` | Domain model for the party/contact/account estate: PERSON, PARTY, ACCOUNT, ACCOUNT-PARTY ROLE; seven lifecycle operations (merge, split, spin-off, promote, soft link, associate, clone-with-link); proposed `0_ksf_common_*` schema; migration and incomplete-handling position; proposed BR-COM-010 / FR-COM-010-0xx requirements |
| `Requirements/` | BABOK requirement docs for inbound email capture, record ownership / ACL, and capability contracts |
| `Requirements/PARTY-ACCOUNT-MODEL.md` | Pointer to the party/account shared requirement set (`BR-COM-010`, `FR-COM-010-001…014`, `UC-COM-010-001…007` — **not yet written**) and to the CRM-facing set that already is |
| `ADR/ADR-001-dev-deploy-separation.md` | Development happens in `~/Documents`, never in `fa_modules` |
| `ADR/ADR-002-repo-pairing-convention.md` | `ksf_<module>` is business logic; `ksf_FA_<module>` is the FA wrapper |
| `ADR/ADR-003-deploy-hygiene.md` | Exclude `.git` from deploys; check the working directory first; write files in place |
| `ADR/ADR-004-party-account-lifecycle-model.md` | The party / person / account lifecycle model: four concepts, seven operations, and what is explicitly incomplete |

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
