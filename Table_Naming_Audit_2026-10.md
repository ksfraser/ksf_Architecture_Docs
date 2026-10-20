# Table-Name Audit — `ksf_FA_*` and `ksf_*` repositories

**Date:** 2026-10-19  
**Scope:** every repository under `~/Documents` whose name starts with `ksf_FA_` or `ksf_`  
**Convention:** `AGENTS_ARCH.md` §12 — *Table naming: `0_ksf_<module>_<noun>`. Never `0_fa_*`.*

This is a survey, not a cleanup pass. No repository other than `ksf_FA_Mail` was changed.

---

## 1. Why this survey exists

`0_` is the **company** prefix, not a vendor segment. A table whose second
segment is `fa` therefore lands in FA core's own `0_fa_*` namespace, and it
is impossible to tell from the name who owns it. On top of that, FrontAccounting's
`db_query()` returns `false` **without raising an error** when a statement
fails (`includes/db/connect_db_mysqli.inc`: `check_db_error()` runs only when
the caller passes an error message). A module that addresses a table it never
created therefore fails *silently*: reads come back empty, writes go nowhere,
and nothing in the log says so.

That is not theoretical. `ksf_FA_Mail` shipped in v0.1.0 a preference store
read as `TB_PREF . 'fa_preference_values'` while its schema file created a
table named `fa_preference_values` — a name the code never addressed — and
that schema file was never wired into `activate_extension()`'s
`update_databases()` map either. The store never existed. This audit looks
for the same shape everywhere.

---

## 2. Method

* Whole-file scan of every `*.php`, `*.sql`, `*.inc`, `*.phtml` file in each
  repository, excluding `vendor/`, `node_modules/`, `phpdoc/`, build output,
  data dumps and the deployed `fa_modules/` tree.
* The scanner is **string-literal aware**: it marks which byte offsets are
  inside a PHP string, so a table name only counts when it appears in SQL,
  while multi-line SQL strings are not missed (many modules build a statement
  across several lines inside one quoted string).
* A name is collected from: `CREATE TABLE`, `FROM`/`JOIN`/`INTO`/`UPDATE`,
  `SHOW TABLES LIKE`, `TB_PREF . 'name'` / `TB_PREF . "name"`,
  `const X_TABLE = 'name'`, and company-prefixed literals such as
  `'0_ksf_module_prefs'`.
* A name found in ordinary code or prose is ignored; only names that are
  declared somewhere in the estate, company-prefixed, or reached through
  `TB_PREF` are treated as table references.
* Test files are scanned and flagged separately — a table that only a test
  mentions is a *dead definition* in production terms.

**Caveats.** Tables created by hand outside the estate, or by an older release
whose schema file has since been deleted, cannot be seen by a static scan;
they show up as “referenced but never declared” below. Names assembled at
runtime from a variable (`TB_PREF . $suffix`) are invisible to any static
scan and are therefore under-reported.

---

## 3. Totals

| Classification | Declared tables | Meaning |
|---|---:|---|
| **CONFORMING** | 106 | `0_ksf_<owning-module>_<noun>` — compliant |
| **FA-CORE** | 81 | a genuine FrontAccounting platform table (`0_gl_trans`, `0_debtors_master`, …) |
| **LEGACY-SUSPECT** | 193 | a `0_fa_*` or otherwise oddly named table the module owns — **187 distinct names across 40 repositories** |
| **SHARED-STORE** | 1 | `0_ksf_module_prefs`, the shared preference table |
| **Total** | **386** | across **174 repositories** |

Of the **193 LEGACY-SUSPECT** declarations: **113 are referenced by code** and
**80 are dead definitions** — a table the module creates and never reads or
writes.

There are **no** `0_fa_*` tables in FrontAccounting 2.4.3 core: every one of
them in this estate belongs to a module.

---

## 4. LEGACY-SUSPECT — the cleanup checklist

`State` is **referenced** when the module's own code (or its own SQL) reads or
writes the table, and **dead definition** when the table is only ever created.
A dead definition still costs a table in every company database.

`Target family` is the `0_ksf_<owning-module>_*` family the table moves to;
the exact noun is the cleanup pass's decision (trim it where it repeats the
module name).

| Repository | Table (current) | Target family | Defined at | State | Recommendation |
|---|---|---|---|---|---|
| `ksf_FA_Assets` | `0_fa_asset_categories` | `0_ksf_assets_*` | `sql/install.sql:4` | dead definition | drop from the schema (never used) |
| `ksf_FA_Assets` | `0_fa_asset_depreciation` | `0_ksf_assets_*` | `sql/install.sql:37` | dead definition | drop from the schema (never used) |
| `ksf_FA_Assets` | `0_fa_asset_maintenance` | `0_ksf_assets_*` | `sql/install.sql:50` | dead definition | drop from the schema (never used) |
| `ksf_FA_Assets` | `0_fa_asset_transfers` | `0_ksf_assets_*` | `sql/install.sql:66` | dead definition | drop from the schema (never used) |
| `ksf_FA_Assets` | `0_fa_assets` | `0_ksf_assets_*` | `sql/install.sql:16` | dead definition | drop from the schema (never used) |
| `ksf_FA_AsteriskPBX` | `0_fa_asterisk_calls` | `0_ksf_asteriskpbx_*` | `sql/install.sql:19` | referenced | rename and migrate the rows |
| `ksf_FA_AsteriskPBX` | `0_fa_asterisk_extensions` | `0_ksf_asteriskpbx_*` | `sql/install.sql:4` | referenced | rename and migrate the rows |
| `ksf_FA_AsteriskPBX` | `0_fa_asterisk_voicemail` | `0_ksf_asteriskpbx_*` | `sql/install.sql:43` | referenced | rename and migrate the rows |
| `ksf_FA_Attachments` | `0_fa_attachment_audit` | `0_ksf_attachments_*` | `sql/install.sql:27` | referenced | rename and migrate the rows |
| `ksf_FA_Attachments` | `0_fa_attachments` | `0_ksf_attachments_*` | `sql/install.sql:1` | referenced | rename and migrate the rows |
| `ksf_FA_Calendar` | `0_fa_cal_attachments` | `0_ksf_calendar_*` | `sql/install.sql:241` | referenced | rename and migrate the rows |
| `ksf_FA_Calendar` | `0_fa_cal_dependencies` | `0_ksf_calendar_*` | `sql/install.sql:214` | referenced | rename and migrate the rows |
| `ksf_FA_Calendar` | `0_fa_cal_entries` | `0_ksf_calendar_*` | `sql/install.sql:24` | referenced | rename and migrate the rows |
| `ksf_FA_Calendar` | `0_fa_cal_entry_reviews` | `0_ksf_calendar_*` | `sql/install.sql:339` | referenced | rename and migrate the rows |
| `ksf_FA_Calendar` | `0_fa_cal_event_occurrences` | `0_ksf_calendar_*` | `sql/install.sql:306` | referenced | rename and migrate the rows |
| `ksf_FA_Calendar` | `0_fa_cal_invitees` | `0_ksf_calendar_*` | `sql/install.sql:172` | referenced | rename and migrate the rows |
| `ksf_FA_Calendar` | `0_fa_cal_notifications` | `0_ksf_calendar_*` | `sql/install.sql:269` | referenced | rename and migrate the rows |
| `ksf_FA_Calendar` | `0_fa_cal_reminders` | `0_ksf_calendar_*` | `sql/install.sql:375` | referenced | rename and migrate the rows |
| `ksf_FA_Calendar` | `0_fa_cal_sources` | `0_ksf_calendar_*` | `sql/install.sql:122` | referenced | rename and migrate the rows |
| `ksf_FA_CampaignBuilder` | `0_fa_campaign_nodes` | `0_ksf_campaignbuilder_*` | `sql/install.sql:14` | dead definition | drop from the schema (never used) |
| `ksf_FA_CampaignBuilder` | `0_fa_campaigns` | `0_ksf_campaignbuilder_*` | `sql/install.sql:3` | dead definition | drop from the schema (never used) |
| `ksf_FA_Common` | `0_encryption_audit` | `0_ksf_common_*` | `sql/encryption_keys.sql:29` | dead definition | drop from the schema (never used) |
| `ksf_FA_Common` | `0_encryption_keys` | `0_ksf_common_*` | `sql/encryption_keys.sql:11` | dead definition | drop from the schema (never used) |
| `ksf_FA_Common` | `0_fa_job_queue` | `0_ksf_common_*` | `sql/install.sql:58` | referenced | rename and migrate the rows |
| `ksf_FA_Common` | `0_gpg_key_audit` | `0_ksf_common_*` | `sql/gpg_keys.sql:34` | dead definition | drop from the schema (never used) |
| `ksf_FA_Common` | `0_gpg_keys` | `0_ksf_common_*` | `sql/gpg_keys.sql:11` | dead definition | drop from the schema (never used) |
| `ksf_FA_Coupons` | `0_fa_coupon_usage` | `0_ksf_coupons_*` | `sql/fa_coupon_usage.sql:4` | referenced | rename and migrate the rows |
| `ksf_FA_Coupons` | `0_fa_coupons` | `0_ksf_coupons_*` | `sql/fa_coupons.sql:5` | referenced | rename and migrate the rows |
| `ksf_FA_Documents` | `0_fa_document_acknowledgments` | `0_ksf_documents_*` | `sql/install.sql:42` | dead definition | drop from the schema (never used) |
| `ksf_FA_Documents` | `0_fa_document_attachments` | `0_ksf_documents_*` | `sql/install.sql:26` | dead definition | drop from the schema (never used) |
| `ksf_FA_Documents` | `0_fa_document_links` | `0_ksf_documents_*` | `sql/install.sql:83` | referenced | rename and migrate the rows |
| `ksf_FA_Documents` | `0_fa_document_versions` | `0_ksf_documents_*` | `sql/install.sql:54` | dead definition | drop from the schema (never used) |
| `ksf_FA_Documents` | `0_fa_documents` | `0_ksf_documents_*` | `sql/install.sql:4` | referenced | rename and migrate the rows |
| `ksf_FA_Fleet` | `0_fa_fleet_inspections` | `0_ksf_fleet_*` | `sql/install.sql:44` | dead definition | drop from the schema (never used) |
| `ksf_FA_Fleet` | `0_fa_fleet_maintenance` | `0_ksf_fleet_*` | `sql/install.sql:68` | dead definition | drop from the schema (never used) |
| `ksf_FA_Fleet` | `0_fa_fleet_trips` | `0_ksf_fleet_*` | `sql/install.sql:25` | dead definition | drop from the schema (never used) |
| `ksf_FA_Fleet` | `0_fa_fleet_vehicles` | `0_ksf_fleet_*` | `sql/install.sql:4` | dead definition | drop from the schema (never used) |
| `ksf_FA_Forms` | `0_fa_form_submissions` | `0_ksf_forms_*` | `sql/install.sql:15` | dead definition | drop from the schema (never used) |
| `ksf_FA_Forms` | `0_fa_forms` | `0_ksf_forms_*` | `sql/install.sql:3` | dead definition | drop from the schema (never used) |
| `ksf_FA_HRM` | `0_hrm_benefits` | `0_ksf_hrm_*` | `sql/install.sql:271` | referenced | rename and migrate the rows |
| `ksf_FA_HRM` | `0_hrm_commission_assignments` | `0_ksf_hrm_*` | `sql/install.sql:369` | referenced | rename and migrate the rows |
| `ksf_FA_HRM` | `0_hrm_commission_entries` | `0_ksf_hrm_*` | `sql/install.sql:384` | referenced | rename and migrate the rows |
| `ksf_FA_HRM` | `0_hrm_commission_rates` | `0_ksf_hrm_*` | `sql/install.sql:352` | referenced | rename and migrate the rows |
| `ksf_FA_HRM` | `0_hrm_contacts_banking` | `0_ksf_hrm_*` | `sql/install.sql:242` | dead definition | drop from the schema (never used) |
| `ksf_FA_HRM` | `0_hrm_contacts_employment` | `0_ksf_hrm_*` | `sql/install.sql:197` | referenced | rename and migrate the rows |
| `ksf_FA_HRM` | `0_hrm_contacts_pii` | `0_ksf_hrm_*` | `sql/install.sql:226` | dead definition | drop from the schema (never used) |
| `ksf_FA_HRM` | `0_hrm_departments` | `0_ksf_hrm_*` | `sql/install.sql:8` | referenced | rename and migrate the rows |
| `ksf_FA_HRM` | `0_hrm_dependent_details` | `0_ksf_hrm_*` | `sql/install.sql:258` | dead definition | drop from the schema (never used) |
| `ksf_FA_HRM` | `0_hrm_employee_benefits` | `0_ksf_hrm_*` | `sql/install.sql:295` | referenced | rename and migrate the rows |
| `ksf_FA_HRM` | `0_hrm_employment_status` | `0_ksf_hrm_*` | `sql/install.sql:342` | referenced | rename and migrate the rows |
| `ksf_FA_HRM` | `0_hrm_event_windows` | `0_ksf_hrm_*` | `sql/ksf_hrm_event_windows.sql:15` | referenced | rename and migrate the rows |
| `ksf_FA_HRM` | `0_hrm_grades` | `0_ksf_hrm_*` | `sql/install.sql:86` | referenced | rename and migrate the rows |
| `ksf_FA_HRM` | `0_hrm_leave_balances` | `0_ksf_hrm_*` | `sql/install.sql:430` | referenced | rename and migrate the rows |
| `ksf_FA_HRM` | `0_hrm_leave_request_days` | `0_ksf_hrm_*` | `sql/install.sql:464` | referenced | rename and migrate the rows |
| `ksf_FA_HRM` | `0_hrm_leave_requests` | `0_ksf_hrm_*` | `sql/install.sql:446` | referenced | rename and migrate the rows |
| `ksf_FA_HRM` | `0_hrm_pay_elements` | `0_ksf_hrm_*` | `sql/install.sql:158` | referenced | rename and migrate the rows |
| `ksf_FA_HRM` | `0_hrm_pay_periods` | `0_ksf_hrm_*` | `sql/install.sql:143` | dead definition | drop from the schema (never used) |
| `ksf_FA_HRM` | `0_hrm_pay_rate_history` | `0_ksf_hrm_*` | `sql/install.sql:124` | dead definition | drop from the schema (never used) |
| `ksf_FA_HRM` | `0_hrm_payroll` | `0_ksf_hrm_*` | `sql/install.sql:312` | referenced | rename and migrate the rows |
| `ksf_FA_HRM` | `0_hrm_payroll_entries` | `0_ksf_hrm_*` | `sql/install.sql:330` | referenced | rename and migrate the rows |
| `ksf_FA_HRM` | `0_hrm_positions` | `0_ksf_hrm_*` | `sql/install.sql:67` | referenced | rename and migrate the rows |
| `ksf_FA_HRM` | `0_hrm_role_dictionary` | `0_ksf_hrm_*` | `sql/install.sql:25` | referenced | rename and migrate the rows |
| `ksf_FA_HRM` | `0_hrm_roles` | `0_ksf_hrm_*` | `sql/install.sql:36` | referenced | rename and migrate the rows |
| `ksf_FA_HRM` | `0_hrm_salary_structure` | `0_ksf_hrm_*` | `sql/install.sql:174` | dead definition | drop from the schema (never used) |
| `ksf_FA_HRM` | `0_hrm_separation_reasons` | `0_ksf_hrm_*` | `sql/install.sql:187` | referenced | rename and migrate the rows |
| `ksf_FA_HRM` | `0_hrm_teams` | `0_ksf_hrm_*` | `sql/install.sql:51` | referenced | rename and migrate the rows |
| `ksf_FA_HRM` | `0_hrm_work_assignments` | `0_ksf_hrm_*` | `sql/install.sql:100` | dead definition | drop from the schema (never used) |
| `ksf_FA_HRM` | `0_fa_contacts_banking` | `0_ksf_hrm_*` | `sql/fa_contacts_banking.sql:6` | dead definition | drop from the schema (never used) |
| `ksf_FA_HRM` | `0_fa_contacts_pii` | `0_ksf_hrm_*` | `sql/fa_contacts_pii.sql:6` | dead definition | drop from the schema (never used) |
| `ksf_FA_HRM` | `0_fa_dependent_details` | `0_ksf_hrm_*` | `sql/fa_dependent_details.sql:6` | dead definition | drop from the schema (never used) |
| `ksf_FA_HRM` | `0_fa_pay_elements` | `0_ksf_hrm_*` | `sql/fa_pay_elements.sql:5` | referenced | rename and migrate the rows |
| `ksf_FA_HRM` | `0_fa_salary_structure` | `0_ksf_hrm_*` | `sql/fa_salary_structure.sql:5` | dead definition | drop from the schema (never used) |
| `ksf_FA_HRM` | `0_fa_separation_reasons` | `0_ksf_hrm_*` | `sql/fa_separation_reasons.sql:4` | referenced | rename and migrate the rows |
| `ksf_FA_HRM` | `0_hrm_contacts_employment` | `0_ksf_hrm_*` | `sql/fa_contacts_employment.sql:5` | referenced | rename and migrate the rows |
| `ksf_FA_HRM` | `0_hrm_departments` | `0_ksf_hrm_*` | `sql/fa_departments.sql:5` | referenced | rename and migrate the rows |
| `ksf_FA_HRM` | `0_hrm_grades` | `0_ksf_hrm_*` | `sql/fa_grades.sql:5` | referenced | rename and migrate the rows |
| `ksf_FA_HRM` | `0_hrm_positions` | `0_ksf_hrm_*` | `sql/fa_positions.sql:5` | referenced | rename and migrate the rows |
| `ksf_FA_ImportStagingProcessing` | `0_staging_customers` | `0_ksf_importstagingprocessing_*` | `sql/install.sql:8` | dead definition | drop from the schema (never used) |
| `ksf_FA_ImportStagingProcessing` | `0_staging_line_item_attributes` | `0_ksf_importstagingprocessing_*` | `sql/install.sql:112` | dead definition | drop from the schema (never used) |
| `ksf_FA_ImportStagingProcessing` | `0_staging_line_items` | `0_ksf_importstagingprocessing_*` | `sql/install.sql:78` | dead definition | drop from the schema (never used) |
| `ksf_FA_ImportStagingProcessing` | `0_staging_log` | `0_ksf_importstagingprocessing_*` | `sql/install.sql:144` | dead definition | drop from the schema (never used) |
| `ksf_FA_ImportStagingProcessing` | `0_staging_mapping` | `0_ksf_importstagingprocessing_*` | `sql/install.sql:126` | dead definition | drop from the schema (never used) |
| `ksf_FA_ImportStagingProcessing` | `0_staging_payment_matches` | `0_ksf_importstagingprocessing_*` | `sql/install.sql:205` | dead definition | drop from the schema (never used) |
| `ksf_FA_ImportStagingProcessing` | `0_staging_payments` | `0_ksf_importstagingprocessing_*` | `sql/install.sql:164` | dead definition | drop from the schema (never used) |
| `ksf_FA_ImportStagingProcessing` | `0_staging_transactions` | `0_ksf_importstagingprocessing_*` | `sql/install.sql:39` | dead definition | drop from the schema (never used) |
| `ksf_FA_JobDescriptions` | `0_fa_job_descriptions` | `0_ksf_jobdescriptions_*` | `sql/install.sql:3` | dead definition | drop from the schema (never used) |
| `ksf_FA_KnowledgeBase` | `0_fa_kb_articles` | `0_ksf_knowledgebase_*` | `sql/install.sql:14` | dead definition | drop from the schema (never used) |
| `ksf_FA_KnowledgeBase` | `0_fa_kb_categories` | `0_ksf_knowledgebase_*` | `sql/install.sql:4` | dead definition | drop from the schema (never used) |
| `ksf_FA_KnowledgeBase` | `0_fa_kb_feedback` | `0_ksf_knowledgebase_*` | `sql/install.sql:33` | dead definition | drop from the schema (never used) |
| `ksf_FA_Leave` | `0_leave_approval_matrix` | `0_ksf_leave_*` | `sql/install.sql:130` | dead definition | drop from the schema (never used) |
| `ksf_FA_Leave` | `0_leave_balances` | `0_ksf_leave_*` | `sql/install.sql:45` | referenced | rename and migrate the rows |
| `ksf_FA_Leave` | `0_leave_bank_config` | `0_ksf_leave_*` | `sql/install.sql:62` | referenced | rename and migrate the rows |
| `ksf_FA_Leave` | `0_leave_banks` | `0_ksf_leave_*` | `sql/install.sql:81` | dead definition | drop from the schema (never used) |
| `ksf_FA_Leave` | `0_leave_holidays` | `0_ksf_leave_*` | `sql/install.sql:118` | referenced | rename and migrate the rows |
| `ksf_FA_Leave` | `0_leave_requests` | `0_ksf_leave_*` | `sql/install.sql:22` | referenced | rename and migrate the rows |
| `ksf_FA_Leave` | `0_leave_settings` | `0_ksf_leave_*` | `sql/install.sql:144` | dead definition | drop from the schema (never used) |
| `ksf_FA_Leave` | `0_leave_transactions` | `0_ksf_leave_*` | `sql/install.sql:99` | dead definition | drop from the schema (never used) |
| `ksf_FA_Leave` | `0_leave_types` | `0_ksf_leave_*` | `sql/install.sql:9` | referenced | rename and migrate the rows |
| `ksf_FA_Loyalty` | `0_fa_customer_loyalty` | `0_ksf_loyalty_*` | `sql/fa_customer_loyalty.sql:4` | referenced | rename and migrate the rows |
| `ksf_FA_Loyalty` | `0_fa_loyalty_transactions` | `0_ksf_loyalty_*` | `sql/fa_loyalty_transactions.sql:4` | referenced | rename and migrate the rows |
| `ksf_FA_Nextcloud` | `0_ksfii_nextcloud_config` | `0_ksf_nextcloud_*` | `sql/install.sql:1` | referenced | rename and migrate the rows |
| `ksf_FA_Notes` | `0_fa_note_links` | `0_ksf_notes_*` | `sql/install.sql:9` | referenced | rename and migrate the rows |
| `ksf_FA_Onboarding` | `0_fa_onboarding_checklist` | `0_ksf_onboarding_*` | `sql/install.sql:24` | dead definition | drop from the schema (never used) |
| `ksf_FA_Onboarding` | `0_fa_onboarding_plans` | `0_ksf_onboarding_*` | `sql/install.sql:13` | dead definition | drop from the schema (never used) |
| `ksf_FA_Onboarding` | `0_fa_onboarding_tasks` | `0_ksf_onboarding_*` | `sql/install.sql:3` | dead definition | drop from the schema (never used) |
| `ksf_FA_OrgChart` | `0_fa_org_positions` | `0_ksf_orgchart_*` | `sql/install.sql:3` | dead definition | drop from the schema (never used) |
| `ksf_FA_Performance` | `0_fa_performance_checkins` | `0_ksf_performance_*` | `sql/fa_performance_checkins.sql:4` | referenced | rename and migrate the rows |
| `ksf_FA_Performance` | `0_fa_performance_goals` | `0_ksf_performance_*` | `sql/fa_performance_goals.sql:5` | referenced | rename and migrate the rows |
| `ksf_FA_Performance` | `0_fa_performance_review_goals` | `0_ksf_performance_*` | `sql/fa_performance_review_goals.sql:4` | referenced | rename and migrate the rows |
| `ksf_FA_Performance` | `0_fa_performance_reviews` | `0_ksf_performance_*` | `sql/fa_performance_reviews.sql:4` | referenced | rename and migrate the rows |
| `ksf_FA_Performance` | `0_fa_pm_task_progress` | `0_ksf_performance_*` | `sql/fa_pm_task_progress.sql:4` | dead definition | drop from the schema (never used) |
| `ksf_FA_Performance` | `0_fa_pm_versions` | `0_ksf_performance_*` | `sql/fa_pm_versions.sql:4` | referenced | rename and migrate the rows |
| `ksf_FA_ProjectManagement` | `0_fa_pm_activity_log` | `0_ksf_projectmanagement_*` | `sql/install.sql:109` | referenced | rename and migrate the rows |
| `ksf_FA_ProjectManagement` | `0_fa_pm_assignments` | `0_ksf_projectmanagement_*` | `sql/install.sql:84` | referenced | rename and migrate the rows |
| `ksf_FA_ProjectManagement` | `0_fa_pm_files` | `0_ksf_projectmanagement_*` | `sql/install.sql:137` | dead definition | drop from the schema (never used) |
| `ksf_FA_ProjectManagement` | `0_fa_pm_project_revenue` | `0_ksf_projectmanagement_*` | `sql/install.sql:190` | referenced | rename and migrate the rows |
| `ksf_FA_ProjectManagement` | `0_fa_pm_project_sales_orders` | `0_ksf_projectmanagement_*` | `sql/install.sql:174` | referenced | rename and migrate the rows |
| `ksf_FA_ProjectManagement` | `0_fa_pm_project_types` | `0_ksf_projectmanagement_*` | `sql/install.sql:98` | referenced | rename and migrate the rows |
| `ksf_FA_ProjectManagement` | `0_fa_pm_projects` | `0_ksf_projectmanagement_*` | `sql/install.sql:6` | referenced | rename and migrate the rows |
| `ksf_FA_ProjectManagement` | `0_fa_pm_task_dependencies` | `0_ksf_projectmanagement_*` | `sql/install.sql:68` | referenced | rename and migrate the rows |
| `ksf_FA_ProjectManagement` | `0_fa_pm_task_progress` | `0_ksf_projectmanagement_*` | `sql/install.sql:158` | referenced | rename and migrate the rows |
| `ksf_FA_ProjectManagement` | `0_fa_pm_tasks` | `0_ksf_projectmanagement_*` | `sql/install.sql:30` | referenced | rename and migrate the rows |
| `ksf_FA_RBAC` | `0_rbac_audit_log` | `0_ksf_rbac_*` | `sql/install.sql:88` | dead definition | drop from the schema (never used) |
| `ksf_FA_RBAC` | `0_rbac_record_access` | `0_ksf_rbac_*` | `sql/install.sql:60` | dead definition | drop from the schema (never used) |
| `ksf_FA_RBAC` | `0_rbac_team_members` | `0_ksf_rbac_*` | `sql/install.sql:35` | dead definition | drop from the schema (never used) |
| `ksf_FA_RBAC` | `0_rbac_teams` | `0_ksf_rbac_*` | `sql/install.sql:14` | dead definition | drop from the schema (never used) |
| `ksf_FA_Recruitment` | `0_recruit_grade_approvals` | `0_ksf_recruitment_*` | `sql/install.sql:111` | dead definition | drop from the schema (never used) |
| `ksf_FA_Recruitment` | `0_recruit_interviews` | `0_ksf_recruitment_*` | `sql/install.sql:71` | dead definition | drop from the schema (never used) |
| `ksf_FA_Recruitment` | `0_recruit_job_applications` | `0_ksf_recruitment_*` | `sql/install.sql:34` | dead definition | drop from the schema (never used) |
| `ksf_FA_Recruitment` | `0_recruit_job_descriptions` | `0_ksf_recruitment_*` | `sql/install.sql:56` | dead definition | drop from the schema (never used) |
| `ksf_FA_Recruitment` | `0_recruit_job_openings` | `0_ksf_recruitment_*` | `sql/install.sql:9` | dead definition | drop from the schema (never used) |
| `ksf_FA_Recruitment` | `0_recruit_offers` | `0_ksf_recruitment_*` | `sql/install.sql:138` | dead definition | drop from the schema (never used) |
| `ksf_FA_Recruitment` | `0_recruit_position_grades` | `0_ksf_recruitment_*` | `sql/install.sql:99` | dead definition | drop from the schema (never used) |
| `ksf_FA_Recruitment` | `0_recruit_role_grades` | `0_ksf_recruitment_*` | `sql/install.sql:87` | dead definition | drop from the schema (never used) |
| `ksf_FA_Roster` | `0_fa_roster_availability` | `0_ksf_roster_*` | `sql/install.sql:22` | dead definition | drop from the schema (never used) |
| `ksf_FA_Roster` | `0_fa_roster_shifts` | `0_ksf_roster_*` | `sql/install.sql:4` | dead definition | drop from the schema (never used) |
| `ksf_FA_Roster` | `0_fa_roster_swaps` | `0_ksf_roster_*` | `sql/install.sql:36` | dead definition | drop from the schema (never used) |
| `ksf_FA_Service` | `0_service_ticket_notes` | `0_ksf_service_*` | `sql/install.sql:19` | referenced | rename and migrate the rows |
| `ksf_FA_Service` | `0_service_tickets` | `0_ksf_service_*` | `sql/install.sql:3` | referenced | rename and migrate the rows |
| `ksf_FA_Square` | `0_square` | `0_ksf_square_*` | `sql/install.sql:7` | referenced | rename and migrate the rows |
| `ksf_FA_Square` | `0_square_customer_mappings` | `0_ksf_square_*` | `sql/install.sql:17` | referenced | rename and migrate the rows |
| `ksf_FA_Subscriptions` | `0_subscription_invoices` | `0_ksf_subscriptions_*` | `sql/install.sql:53` | dead definition | drop from the schema (never used) |
| `ksf_FA_Subscriptions` | `0_subscription_templates` | `0_ksf_subscriptions_*` | `sql/install.sql:4` | referenced | rename and migrate the rows |
| `ksf_FA_Subscriptions` | `0_subscription_usage` | `0_ksf_subscriptions_*` | `sql/install.sql:37` | referenced | rename and migrate the rows |
| `ksf_FA_Subscriptions` | `0_subscriptions` | `0_ksf_subscriptions_*` | `sql/install.sql:19` | referenced | rename and migrate the rows |
| `ksf_FA_SuggestedPurchaseOrder` | `0_spo_stock_params` | `0_ksf_suggestedpurchaseorder_*` | `sql/install.sql:87` | referenced | rename and migrate the rows |
| `ksf_FA_SuggestedPurchaseOrder` | `0_stock_trends` | `0_ksf_suggestedpurchaseorder_*` | `sql/install.sql:66` | referenced | rename and migrate the rows |
| `ksf_FA_SuggestedPurchaseOrder` | `0_suggested_order_lines` | `0_ksf_suggestedpurchaseorder_*` | `sql/install.sql:24` | referenced | rename and migrate the rows |
| `ksf_FA_SuggestedPurchaseOrder` | `0_suggested_orders` | `0_ksf_suggestedpurchaseorder_*` | `sql/install.sql:4` | referenced | rename and migrate the rows |
| `ksf_FA_SuggestedPurchaseOrder` | `0_vendor_lead_times` | `0_ksf_suggestedpurchaseorder_*` | `sql/install.sql:52` | referenced | rename and migrate the rows |
| `ksf_FA_Timesheets` | `0_approval_step_comments` | `0_ksf_timesheets_*` | `sql/install.sql:53` | dead definition | drop from the schema (never used) |
| `ksf_FA_Timesheets` | `0_time_entries` | `0_ksf_timesheets_*` | `sql/install.sql:26` | referenced | rename and migrate the rows |
| `ksf_FA_Timesheets` | `0_timesheet_config` | `0_ksf_timesheets_*` | `sql/install.sql:67` | referenced | rename and migrate the rows |
| `ksf_FA_Timesheets` | `0_timesheets` | `0_ksf_timesheets_*` | `sql/install.sql:3` | referenced | rename and migrate the rows |
| `ksf_FA_Tracking` | `0_tracking_events` | `0_ksf_tracking_*` | `sql/install.sql:3` | referenced | rename and migrate the rows |
| `ksf_FA_Tracking` | `0_tracking_visitors` | `0_ksf_tracking_*` | `sql/install.sql:17` | dead definition | drop from the schema (never used) |
| `ksf_FA_Training` | `0_fa_training_enrollments` | `0_ksf_training_*` | `sql/install.sql:21` | dead definition | drop from the schema (never used) |
| `ksf_FA_Training` | `0_fa_training_programs` | `0_ksf_training_*` | `sql/install.sql:4` | dead definition | drop from the schema (never used) |
| `ksf_FA_Training` | `0_fa_training_sessions` | `0_ksf_training_*` | `sql/install.sql:39` | dead definition | drop from the schema (never used) |
| `ksf_FA_TravelExpense` | `0_travel_activity_codes` | `0_ksf_travelexpense_*` | `sql/install.sql:86` | referenced | rename and migrate the rows |
| `ksf_FA_TravelExpense` | `0_travel_expenses` | `0_ksf_travelexpense_*` | `sql/install.sql:34` | referenced | rename and migrate the rows |
| `ksf_FA_TravelExpense` | `0_travel_per_diem` | `0_ksf_travelexpense_*` | `sql/install.sql:70` | referenced | rename and migrate the rows |
| `ksf_FA_TravelExpense` | `0_travel_requests` | `0_ksf_travelexpense_*` | `sql/install.sql:3` | referenced | rename and migrate the rows |
| `ksf_FA_TravelExpense` | `0_travel_suppliers` | `0_ksf_travelexpense_*` | `sql/install.sql:98` | referenced | rename and migrate the rows |
| `ksf_FA_Woocommerce` | `0_woo_category_map` | `0_ksf_woocommerce_*` | `sql/schema.sql:32` | referenced | rename and migrate the rows |
| `ksf_FA_Woocommerce` | `0_woo_customer_map` | `0_ksf_woocommerce_*` | `sql/schema.sql:9` | dead definition | drop from the schema (never used) |
| `ksf_FA_Woocommerce` | `0_woo_product_map` | `0_ksf_woocommerce_*` | `sql/schema.sql:21` | referenced | rename and migrate the rows |
| `ksf_FA_Woocommerce` | `0_woo_sync_log` | `0_ksf_woocommerce_*` | `sql/schema.sql:41` | dead definition | drop from the schema (never used) |
| `ksf_PriceBook` | `0_pb_competitors` | `0_ksf_pricebook_*` | `sql/001_initial_schema.sql:5` | referenced | rename and migrate the rows |
| `ksf_PriceBook` | `0_pb_entries` | `0_ksf_pricebook_*` | `sql/001_initial_schema.sql:30` | referenced | rename and migrate the rows |
| `ksf_PriceBook` | `0_pb_price_books` | `0_ksf_pricebook_*` | `sql/001_initial_schema.sql:18` | dead definition | drop from the schema (never used) |
| `ksf_PriceBook` | `0_pb_scrape_logs` | `0_ksf_pricebook_*` | `sql/001_initial_schema.sql:49` | referenced | rename and migrate the rows |
| `ksf_bank_import` | `0_bi_bank_accounts` | `0_ksf_bank_import_*` | `sql/migrations/002_backfill_bi_bank_accounts_from_legacy_bank_accounts.sql:13` | referenced | rename and migrate the rows |
| `ksf_bank_import` | `0_bi_config` | `0_ksf_bank_import_*` | `sql/bi_config_system.sql:6` | referenced | rename and migrate the rows |
| `ksf_bank_import` | `0_bi_config_history` | `0_ksf_bank_import_*` | `sql/bi_config_system.sql:48` | referenced | rename and migrate the rows |
| `ksf_bank_import` | `0_bi_file_statements` | `0_ksf_bank_import_*` | `sql/mantis_2708_uploaded_files.sql:23` | referenced | rename and migrate the rows |
| `ksf_bank_import` | `0_bi_partners_data` | `0_ksf_bank_import_*` | `sql/update.sql:69` | referenced | rename and migrate the rows |
| `ksf_bank_import` | `0_bi_statements` | `0_ksf_bank_import_*` | `sql/update.sql:4` | referenced | rename and migrate the rows |
| `ksf_bank_import` | `0_bi_transactions` | `0_ksf_bank_import_*` | `sql/update.sql:24` | referenced | rename and migrate the rows |
| `ksf_bank_import` | `0_bi_uploaded_files` | `0_ksf_bank_import_*` | `sql/mantis_2708_uploaded_files.sql:4` | referenced | rename and migrate the rows |
| `ksf_bank_import` | `0_bi_transactions` | `0_ksf_bank_import_*` | `sql/migrations/001_create_transactions_table.sql:1` | referenced | rename and migrate the rows |
| `ksf_common_db` | `0_product_hierarchy` | `0_ksf_common_db_*` | `tests/Unit/Dictionary/TableDefinitionTest.php:27` | dead definition | drop from the schema (never used) |
| `ksf_estate` | `0_beneficiary_recommendations` | `0_ksf_estate_*` | `tests/EstatePlanningEngineTest.php:148` | referenced | rename and migrate the rows |
| `ksf_estate` | `0_beneficiary_relationship_mappings` | `0_ksf_estate_*` | `tests/EstatePlanningEngineTest.php:101` | referenced | rename and migrate the rows |
| `ksf_estate` | `0_beneficiary_relationship_types` | `0_ksf_estate_*` | `tests/EstatePlanningEngineTest.php:85` | referenced | rename and migrate the rows |
| `ksf_estate` | `0_estate_tax_rates` | `0_ksf_estate_*` | `tests/EstatePlanningEngineTest.php:48` | referenced | rename and migrate the rows |
| `ksf_fa_downloader` | `0_fa_download_targets` | `0_ksf_fa_downloader_*` | `sql/01_fa_download_targets.sql:6` | referenced | rename and migrate the rows |
| `ksf_fa_downloader` | `0_fa_downloads` | `0_ksf_fa_downloader_*` | `sql/02_fa_downloads.sql:6` | referenced | rename and migrate the rows |
| `ksf_generate_catalogue` | `0_contains_alcohol` | `0_ksf_generate_catalogue_*` | `sql_updates.sql:22` | referenced | rename and migrate the rows |
| `ksf_generate_catalogue` | `0_product_variations` | `0_ksf_generate_catalogue_*` | `sql_updates.sql:52` | dead definition | drop from the schema (never used) |
| `ksf_generate_catalogue` | `0_social_media_fields` | `0_ksf_generate_catalogue_*` | `sql_updates.sql:7` | referenced | rename and migrate the rows |
| `ksf_generate_catalogue` | `0_square_import_log` | `0_ksf_generate_catalogue_*` | `sql_updates.sql:36` | dead definition | drop from the schema (never used) |
| `ksf_generate_catalogue` | `0_woocommerce_parent_child` | `0_ksf_generate_catalogue_*` | `sql_updates.sql:74` | referenced | rename and migrate the rows |

---

## 5. The other half of the problem: code that addresses a table nobody creates

Renaming a table is only half the work. In many modules the **code** and the
**schema** disagree about the name, so the module queries a table that was
never created. This is the same silent failure as `ksf_FA_Mail`'s, and it is
worse than a naming-style violation because the feature is simply broken.

Evidence from the live Integration database (`ksf_fa`, container
`ksfii_app-mariadb`, company prefix `0_`):

```
mysql> SELECT COUNT(*) FROM 0_fa_crm_contacts;
ERROR 1146 (42S02): Table 'ksf_fa.0_fa_crm_contacts' doesn't exist
mysql> SELECT COUNT(*) FROM 0_ksf_crm_contacts;
+------+
| c    |
+------+
|    0 |
+------+
```

`ksf_FA_CRM`'s schema creates `0_ksf_crm_contacts` (compliant) but its code
queries `TB_PREF . "fa_crm_contacts"` — `includes/crm_db.inc:116` and ~20
other places. Every one of those statements fails silently.

Note that `0_ksf_crm_contacts` also duplicates FA core's `0_crm_contacts`,
which is a separate violation of standing decision 1 in this repo's `README.md`
("no duplicate core tables" — a module must not re-create a FrontAccounting
core table; the extra attributes belong in a satellite table keyed by the FA
core id).

The list below is every unambiguous reference (`TB_PREF` concatenation or a
company-prefixed literal) to a table that **no schema in the estate creates**.

A name ending in `_` is a **dynamic** table name (a prefix concatenated
with a variable); it cannot be verified statically, but it is worth a look.
A hit in a `tests/` directory is a fixture, not a production failure.

| Repository | Table addressed | First occurrence | Hits | Kind |
|---|---|---|---:|---|
| `ksf_Calendar` | `0_fa_crm_communications` | `src/ksfraser/Calendar/Service/CalendarService.php:735` | 1 | **production** |
| `ksf_FA_Assets` | `0_asset_categories` | `includes/assets_db.inc:17` | 4 | **production** |
| `ksf_FA_Assets` | `0_asset_maintenance` | `includes/assets_db.inc:67` | 3 | **production** |
| `ksf_FA_Assets` | `0_asset_transfers` | `includes/assets_db.inc:57` | 1 | **production** |
| `ksf_FA_Assets` | `0_assets` | `includes/assets_db.inc:7` | 8 | **production** |
| `ksf_FA_AsteriskPBX` | `0_asterisk_calls` | `includes/asterisk_db.inc:60` | 5 | **production** |
| `ksf_FA_AsteriskPBX` | `0_asterisk_extensions` | `includes/asterisk_db.inc:10` | 6 | **production** |
| `ksf_FA_AsteriskPBX` | `0_crm_leads` | `includes/asterisk_db.inc:116` | 1 | **production** |
| `ksf_FA_AsteriskPBX` | `0_ext_contact_info` | `includes/asterisk_db.inc:108` | 1 | **production** |
| `ksf_FA_AsteriskPBX` | `0_hr_employees` | `includes/asterisk_db.inc:21` | 2 | **production** |
| `ksf_FA_CRM` | `0_crm_campaigns` | `includes/crm_db.inc:1156` | 2 | **production** |
| `ksf_FA_CRM` | `0_crm_communications` | `includes/crm_ui.inc:199` | 1 | **production** |
| `ksf_FA_CRM` | `0_crm_contact_roles` | `includes/crm_db.inc:186` | 10 | **production** |
| `ksf_FA_CRM` | `0_crm_customer_analytics` | `includes/crm_db.inc:613` | 2 | **production** |
| `ksf_FA_CRM` | `0_crm_customer_segments` | `includes/crm_db.inc:392` | 6 | **production** |
| `ksf_FA_CRM` | `0_crm_customer_types` | `pages/customer_types.php:102` | 2 | **production** |
| `ksf_FA_CRM` | `0_crm_customers` | `includes/crm_ui.inc:198` | 1 | **production** |
| `ksf_FA_CRM` | `0_crm_edi_config` | `includes/crm_db.inc:566` | 3 | **production** |
| `ksf_FA_CRM` | `0_crm_meeting_attendees` | `includes/crm_db.inc:1228` | 6 | **production** |
| `ksf_FA_CRM` | `0_crm_meeting_rooms` | `includes/crm_db.inc:993` | 9 | **production** |
| `ksf_FA_CRM` | `0_crm_meetings` | `includes/EmailImportService.php:480` | 7 | **production** |
| `ksf_FA_CRM` | `0_crm_opportunities` | `includes/crm_ui.inc:200` | 3 | **production** |
| `ksf_FA_CRM` | `0_crm_opportunity_stages` | `includes/crm_ui.inc:603` | 1 | **production** |
| `ksf_FA_CRM` | `0_crm_territories` | `includes/crm_ui.inc:401` | 4 | **production** |
| `ksf_FA_CRM` | `0_custcontacts` | `includes/crm_db.inc:788` | 1 | **production** |
| `ksf_FA_CRM` | `0_debtor_master` | `reporting/rep_customer_list.php:55` | 3 | **production** |
| `ksf_FA_CRM` | `0_fa_crm_account_relationships` | `includes/crm_relationships_db.inc:139` | 7 | **production** |
| `ksf_FA_CRM` | `0_fa_crm_activity_log` | `includes/crm_db.inc:1739` | 1 | **production** |
| `ksf_FA_CRM` | `0_fa_crm_communications` | `includes/crm_db.inc:224` | 11 | **production** |
| `ksf_FA_CRM` | `0_fa_crm_contact_accounts` | `includes/crm_db.inc:1899` | 5 | **production** |
| `ksf_FA_CRM` | `0_fa_crm_contact_relationships` | `includes/crm_relationships_db.inc:78` | 10 | **production** |
| `ksf_FA_CRM` | `0_fa_crm_contacts` | `includes/EmailImportService.php:134` | 15 | **production** |
| `ksf_FA_CRM` | `0_fa_crm_customer_types` | `includes/crm_db.inc:105` | 9 | **production** |
| `ksf_FA_CRM` | `0_fa_crm_customers` | `includes/crm_db.inc:43` | 8 | **production** |
| `ksf_FA_CRM` | `0_fa_crm_email_accounts` | `hooks.php:223` | 1 | **production** |
| `ksf_FA_CRM` | `0_fa_crm_leads` | `includes/crm_db.inc:1788` | 9 | **production** |
| `ksf_FA_CRM` | `0_fa_crm_life_events` | `includes/crm_relationships_db.inc:241` | 7 | **production** |
| `ksf_FA_CRM` | `0_fa_crm_opportunities` | `includes/crm_db.inc:515` | 23 | **production** |
| `ksf_FA_CRM` | `0_fa_crm_person_account_roles` | `includes/crm_relationships_db.inc:185` | 8 | **production** |
| `ksf_FA_CRM` | `0_fa_crm_quote_items` | `includes/crm_db.inc:2130` | 3 | **production** |
| `ksf_FA_CRM` | `0_fa_crm_quotes` | `includes/crm_db.inc:2054` | 7 | **production** |
| `ksf_FA_CRM` | `0_fa_crm_realms` | `includes/crm_db.inc:1993` | 6 | **production** |
| `ksf_FA_CRM` | `0_fa_crm_territories` | `includes/crm_db.inc:472` | 8 | **production** |
| `ksf_FA_CRM` | `0_locstock` | `reporting/rep_work_order_print.php:52` | 1 | **production** |
| `ksf_FA_CRM` | `0_product_attribute_types` | `reporting/rep_product_specs.php:31` | 1 | **production** |
| `ksf_FA_CRM` | `0_product_attributes` | `reporting/rep_product_specs.php:32` | 1 | **production** |
| `ksf_FA_CRM` | `0_systypes` | `reporting/rep_customer_statement.php:91` | 2 | **production** |
| `ksf_FA_Calendar` | `0_calendar_events` | `includes/import.php:32` | 3 | **production** |
| `ksf_FA_CampaignBuilder` | `0_campaign_nodes` | `includes/campaign_db.inc:6` | 1 | **production** |
| `ksf_FA_CampaignBuilder` | `0_campaigns` | `includes/campaign_db.inc:3` | 3 | **production** |
| `ksf_FA_Classes` | `0_workcenters` | `legacy/class.fa_workcenter.php:59` | 1 | **production** |
| `ksf_FA_Common` | `0_fa_preference_values` | `tests/Unit/Preference/PreferenceRepositoryTest.php:67` | 1 | test fixture |
| `ksf_FA_Common` | `0_ksf_custom_prefs` | `tests/Unit/Preference/PreferenceRepositoryTest.php:73` | 4 | test fixture |
| `ksf_FA_Documents` | `0_document_acknowledgments` | `includes/documents_db.inc:214` | 3 | **production** |
| `ksf_FA_Documents` | `0_document_attachments` | `documents.php:60` | 4 | **production** |
| `ksf_FA_Documents` | `0_documents` | `includes/documents_db.inc:33` | 7 | **production** |
| `ksf_FA_EmailManager` | `0_crm_campaigns` | `pages/campaigns.php:68` | 2 | **production** |
| `ksf_FA_EmailManager` | `0_crm_opportunities` | `includes/em_routing.inc:96` | 1 | **production** |
| `ksf_FA_EmailManager` | `0_fa_st_tickets` | `includes/em_routing.inc:75` | 1 | **production** |
| `ksf_FA_EmailManager` | `0_ksf_em_campaign_links` | `pages/campaigns.php:100` | 1 | **production** |
| `ksf_FA_EmailManager` | `0_ksf_em_campaign_lists` | `pages/campaigns.php:24` | 3 | **production** |
| `ksf_FA_Fleet` | `0_fleet_inspections` | `tests/Unit/FleetDBTest.php:62` | 1 | test fixture |
| `ksf_FA_Fleet` | `0_fleet_maintenance` | `tests/Unit/FleetDBTest.php:69` | 3 | test fixture |
| `ksf_FA_Fleet` | `0_fleet_trips` | `tests/Unit/FleetDBTest.php:40` | 3 | test fixture |
| `ksf_FA_Fleet` | `0_fleet_vehicles` | `tests/Unit/FleetDBTest.php:13` | 6 | test fixture |
| `ksf_FA_Forms` | `0_form_submissions` | `includes/forms_db.inc:5` | 1 | **production** |
| `ksf_FA_Forms` | `0_forms` | `includes/forms_db.inc:3` | 2 | **production** |
| `ksf_FA_HRM` | `0_hrm_` | `src/Config/PayrollDbConfig.php:15` | 1 | dynamic name |
| `ksf_FA_HRM` | `0_hrm_candidates` | `src/Controller/RecruitmentTabController.php:64` | 1 | **production** |
| `ksf_FA_HRM` | `0_ksf_employee` | `import.php:33` | 3 | **production** |
| `ksf_FA_HRM` | `0_ksf_employees` | `includes/import.php:34` | 3 | **production** |
| `ksf_FA_ImportStagingProcessing_UI` | `0_ksf_import_external_customers` | `class.ksf_import_external_customers_model.php:175` | 2 | **production** |
| `ksf_FA_ImportStagingProcessing_UI` | `0_ksf_import_square_bank_transfer` | `class.ksf_import_square.php:860` | 3 | **production** |
| `ksf_FA_ImportStagingProcessing_UI` | `0_ksf_import_square_payments` | `class.ksf_import_square_payments.php:302` | 4 | **production** |
| `ksf_FA_ImportStagingProcessing_UI` | `0_ksf_import_square_sales` | `class.ksf_import_square_transactions.php:503` | 2 | **production** |
| `ksf_FA_ImportStagingProcessing_UI` | `0_ksf_import_square_transactions` | `class.ksf_import_square.php:873` | 4 | **production** |
| `ksf_FA_ImportStagingProcessing_UI` | `0_ksf_isu_config` | `pages/config.php:14` | 1 | **production** |
| `ksf_FA_JobDescriptions` | `0_job_descriptions` | `includes/jobdesc_db.inc:1` | 1 | **production** |
| `ksf_FA_KnowledgeBase` | `0_kb_articles` | `tests/Unit/KBTest.php:48` | 5 | test fixture |
| `ksf_FA_KnowledgeBase` | `0_kb_categories` | `tests/Unit/KBTest.php:33` | 4 | test fixture |
| `ksf_FA_KnowledgeBase` | `0_kb_feedback` | `tests/Unit/KBTest.php:80` | 1 | test fixture |
| `ksf_FA_LLM` | `0_fa_llm_request_logs` | `includes/db.inc:12` | 4 | **production** |
| `ksf_FA_Leave` | `0_hr_employees` | `includes/leave_db.inc:54` | 2 | **production** |
| `ksf_FA_MRP` | `0_kd_ksf_modules` | `includes/mrp_db.inc:220` | 1 | **production** |
| `ksf_FA_MRP` | `0_ksf_mrp_material_requirements` | `includes/mrp_db.inc:177` | 3 | **production** |
| `ksf_FA_MRP` | `0_ksf_mrp_production_schedule` | `includes/mrp_db.inc:8` | 7 | **production** |
| `ksf_FA_MRP` | `0_ksf_mrp_settings` | `includes/mrp_db.inc:203` | 3 | **production** |
| `ksf_FA_MRP` | `0_ksf_mrp_workcenter_capacity` | `includes/mrp_db.inc:124` | 3 | **production** |
| `ksf_FA_Notes` | `0_fa_crm_notes` | `includes/notes_db.inc:49` | 8 | **production** |
| `ksf_FA_Onboarding` | `0_onboarding_checklist` | `includes/onboarding_db.inc:1` | 1 | **production** |
| `ksf_FA_Onboarding` | `0_onboarding_plan` | `includes/onboarding_db.inc:1` | 1 | **production** |
| `ksf_FA_Onboarding` | `0_onboarding_tasks` | `includes/onboarding_db.inc:1` | 1 | **production** |
| `ksf_FA_OrgChart` | `0_org_positions` | `includes/orgchart_db.inc:1` | 1 | **production** |
| `ksf_FA_Performance` | `0_hr_employees` | `includes/performance_db.inc:1` | 1 | **production** |
| `ksf_FA_Performance` | `0_performance_reviews` | `includes/performance_db.inc:1` | 1 | **production** |
| `ksf_FA_ProductLookup` | `0_product_staging` | `includes/db.inc:12` | 6 | **production** |
| `ksf_FA_ProjectManagement` | `0_employee` | `includes/PMContainer.php:189` | 3 | **production** |
| `ksf_FA_ProjectManagement` | `0_employees` | `includes/pm_db.inc:256` | 1 | **production** |
| `ksf_FA_ProjectManagement` | `0_fa_pm_` | `includes/PMContainer.php:172` | 1 | dynamic name |
| `ksf_FA_ProjectManagement` | `0_projects` | `includes/import.php:41` | 3 | **production** |
| `ksf_FA_Recruitment` | `0_job_applications` | `includes/recruitment_db.inc:49` | 5 | **production** |
| `ksf_FA_Recruitment` | `0_job_openings` | `includes/recruitment_db.inc:9` | 5 | **production** |
| `ksf_FA_Recruitment` | `0_recruitment_interviews` | `includes/recruitment_db.inc:103` | 3 | **production** |
| `ksf_FA_Rep_Audit` | `0_systypes` | `reporting/rep_contaminated_trans.php:28` | 2 | **production** |
| `ksf_FA_Roster` | `0_hr_employees` | `includes/roster_db.inc:38` | 2 | **production** |
| `ksf_FA_Roster` | `0_roster_shifts` | `includes/roster_db.inc:9` | 6 | **production** |
| `ksf_FA_SerialNumber` | `0_ksf_` | `tests/Unit/ModuleConventionsTest.php:119` | 1 | dynamic name |
| `ksf_FA_Square` | `0_ksf_import_square_items` | `tests/Unit/ItemStagingDAOTest.php:38` | 1 | test fixture |
| `ksf_FA_Square` | `0_ksf_import_square_payments` | `tests/Unit/PaymentMatchDAOTest.php:38` | 1 | test fixture |
| `ksf_FA_Square` | `0_ksf_import_square_sales` | `tests/Unit/SalesMatchDAOTest.php:38` | 1 | test fixture |
| `ksf_FA_Square` | `0_ksf_import_square_transactions` | `tests/Unit/TransactionStagingDAOTest.php:52` | 1 | test fixture |
| `ksf_FA_Square` | `0_square_location_mappings` | `tests/Unit/LocationMappingDAOTest.php:47` | 1 | test fixture |
| `ksf_FA_Square` | `0_square_tokens` | `src/DAO/LocationMappingDAO.php:134` | 7 | **production** |
| `ksf_FA_SupportTickets` | `0_fa_st_tickets` | `includes/st_db.inc:28` | 9 | **production** |
| `ksf_FA_SupportTickets` | `0_fa_st_tickets_activities` | `includes/st_db.inc:96` | 2 | **production** |
| `ksf_FA_SupportTickets` | `0_fa_st_tickets_items` | `includes/st_db.inc:159` | 2 | **production** |
| `ksf_FA_SupportTickets` | `0_fa_st_tickets_notes` | `includes/st_db.inc:132` | 2 | **production** |
| `ksf_FA_SupportTickets` | `0_fa_wm_liability` | `includes/st_event_wiring.php:21` | 1 | **production** |
| `ksf_FA_Teams` | `0_hr_employees` | `includes/teams_db.inc:19` | 2 | **production** |
| `ksf_FA_Teams` | `0_projects` | `includes/teams_db.inc:90` | 1 | **production** |
| `ksf_FA_Teams` | `0_team_members` | `includes/teams_db.inc:30` | 5 | **production** |
| `ksf_FA_Teams` | `0_team_projects` | `includes/teams_db.inc:81` | 2 | **production** |
| `ksf_FA_Teams` | `0_teams` | `includes/teams_db.inc:9` | 4 | **production** |
| `ksf_FA_Timesheets` | `0_hr_employees` | `includes/timesheet_db.inc:45` | 2 | **production** |
| `ksf_FA_Timesheets` | `0_projects` | `includes/timesheet_db.inc:46` | 1 | **production** |
| `ksf_FA_Timesheets` | `0_timesheet_entries` | `includes/timesheet_db.inc:9` | 9 | **production** |
| `ksf_FA_Timesheets` | `0_timesheet_summaries` | `includes/timesheet_db.inc:110` | 2 | **production** |
| `ksf_FA_Training` | `0_hr_employees` | `includes/training_db.inc:57` | 1 | **production** |
| `ksf_FA_Training` | `0_training_enrollments` | `includes/training_db.inc:46` | 4 | **production** |
| `ksf_FA_Training` | `0_training_programs` | `includes/training_db.inc:9` | 6 | **production** |
| `ksf_FA_Training` | `0_training_sessions` | `includes/training_db.inc:92` | 2 | **production** |
| `ksf_FA_TravelExpense` | `0_hr_employees` | `includes/travel_db.inc:20` | 2 | **production** |
| `ksf_FA_TravelExpense` | `0_projects` | `includes/travel_db.inc:21` | 3 | **production** |
| `ksf_FA_Warehouse` | `0_ksf_wh_` | `tests/Unit/DefaultShelfServiceTest.php:250` | 4 | dynamic name |
| `ksf_FA_WarrantyManagement` | `0_fa_wm_liability` | `includes/wm_db.inc:77` | 7 | **production** |
| `ksf_FA_WarrantyManagement` | `0_fa_wm_products` | `includes/wm_db.inc:23` | 8 | **production** |
| `ksf_FA_WarrantyManagement` | `0_fa_wm_rma` | `includes/wm_db.inc:110` | 9 | **production** |
| `ksf_FA_Woocommerce` | `0_product_cart_rules` | `tests/Unit/ProductDataBuilderTest.php:325` | 2 | test fixture |
| `ksf_FA_Woocommerce` | `0_product_dimensions` | `tests/Unit/ProductDataBuilderExtendedTest.php:78` | 5 | test fixture |
| `ksf_FA_Woocommerce` | `0_product_identifiers` | `tests/Unit/ProductDataBuilderExtendedTest.php:172` | 4 | test fixture |
| `ksf_FA_Woocommerce` | `0_product_media` | `tests/Unit/ProductDataBuilderExtendedTest.php:115` | 5 | test fixture |
| `ksf_FA_Woocommerce` | `0_product_related_products` | `tests/Unit/ProductDataBuilderTest.php:343` | 3 | test fixture |
| `ksf_FA_Woocommerce` | `0_product_shipping_attributes` | `tests/Unit/ProductDataBuilderExtendedTest.php:154` | 7 | test fixture |
| `ksf_FA_Woocommerce` | `0_product_shipping_classes` | `tests/Unit/ProductDataBuilderTest.php:307` | 2 | test fixture |
| `ksf_FA_Woocommerce` | `0_product_tag_assignments` | `tests/Unit/ProductDataBuilderTest.php:279` | 2 | test fixture |
| `ksf_FA_Woocommerce` | `0_product_tags` | `tests/Unit/ProductDataBuilderTest.php:278` | 2 | test fixture |
| `ksf_FA_Woocommerce` | `0_related` | `class.woo.php:318` | 1 | **production** |
| `ksf_FA_Woocommerce` | `0_shipdim` | `class.woo.php:305` | 1 | **production** |
| `ksf_FA_Woocommerce` | `0_specials` | `class.woo.php:279` | 1 | **production** |
| `ksf_FA_Woocommerce` | `0_stock_item_tags` | `tests/Unit/ProductExportServiceCoverageTest.php:431` | 3 | test fixture |
| `ksf_FA_Woocommerce` | `0_woo_categories_xref` | `class.woo.php:337` | 6 | **production** |
| `ksf_FA_Woocommerce` | `0_woo_prod_variable_master` | `class.EXPORT_WOO.php:582` | 5 | **production** |
| `ksf_FA_Woocommerce` | `0_woo_prod_variable_sku_combos` | `class.woo_prod_variable_sku_combos.php:82` | 6 | **production** |
| `ksf_FA_Woocommerce` | `0_woo_prod_variables_values` | `class.woo_prod_variable_sku_full.php:144` | 4 | **production** |
| `ksf_FA_Workflow` | `0_fa_wf_actions` | `includes/wf_db.inc:77` | 5 | **production** |
| `ksf_FA_Workflow` | `0_fa_wf_log` | `includes/wf_db.inc:261` | 1 | **production** |
| `ksf_FA_Workflow` | `0_fa_wf_triggers` | `includes/wf_db.inc:8` | 5 | **production** |
| `ksf_FA_estate` | `0_ksfii_estate_plan` | `hooks.php:41` | 1 | **production** |
| `ksf_KnowledgeBase` | `0_kb_articles` | `src/Ksfraser/KnowledgeBase/Entity/KBCategory.php:37` | 6 | **production** |
| `ksf_KnowledgeBase` | `0_kb_categories` | `src/Ksfraser/KnowledgeBase/Entity/KBCategory.php:57` | 9 | **production** |
| `ksf_KnowledgeBase` | `0_kb_feedback` | `src/Ksfraser/KnowledgeBase/Entity/KBFeedback.php:52` | 5 | **production** |
| `ksf_Marketing` | `0_marketing_ab_tests` | `src/Ksfraser/Marketing/LeadScoring.php:313` | 1 | **production** |
| `ksf_Marketing` | `0_marketing_campaigns` | `src/Ksfraser/Marketing/AIMarketing.php:246` | 1 | **production** |
| `ksf_Marketing` | `0_marketing_contacts` | `src/Ksfraser/Marketing/DripCampaigns.php:140` | 2 | **production** |
| `ksf_Marketing` | `0_marketing_drip_campaigns` | `src/Ksfraser/Marketing/DripCampaigns.php:76` | 2 | **production** |
| `ksf_Marketing` | `0_marketing_drip_queue` | `src/Ksfraser/Marketing/DripCampaigns.php:56` | 4 | **production** |
| `ksf_Marketing` | `0_marketing_forms` | `src/Ksfraser/Marketing/LeadScoring.php:214` | 2 | **production** |
| `ksf_Marketing` | `0_marketing_lead_scores` | `src/Ksfraser/Marketing/LeadScoring.php:29` | 2 | **production** |
| `ksf_Marketing` | `0_marketing_scheduled_posts` | `src/Ksfraser/Marketing/AIMarketing.php:189` | 2 | **production** |
| `ksf_Notes` | `0_fa_crm_notes` | `src/ksfraser/Notes/Service/NoteService.php:29` | 8 | **production** |
| `ksf_RBAC` | `0_rbac_team_nesting` | `tests/Unit/Rbac/Query/RbacQueryFilterTest.php:126` | 1 | test fixture |
| `ksf_WP_CustomerPortal` | `0_fa_announcement_targets` | `includes/class-ksf-portal-announcements.php:103` | 1 | **production** |
| `ksf_WP_CustomerPortal` | `0_fa_announcements` | `includes/class-ksf-portal-announcements.php:25` | 5 | **production** |
| `ksf_WP_CustomerPortal` | `0_fa_approval_tasks` | `includes/services/class-ksf-salesman-approval.php:35` | 4 | **production** |
| `ksf_WP_CustomerPortal` | `0_fa_customer_documents` | `includes/class-ksf-portal-api.php:458` | 1 | **production** |
| `ksf_WP_CustomerPortal` | `0_fa_st_tickets` | `includes/class-ksf-portal-api.php:104` | 3 | **production** |
| `ksf_WP_CustomerPortal` | `0_fa_st_tickets_notes` | `includes/class-ksf-portal-api.php:148` | 2 | **production** |
| `ksf_generate_catalogue` | `0_ksf_qoh` | `class.WooPOS_Count.php:20` | 4 | **production** |
| `ksf_generate_catalogue` | `0_square_tokens` | `class.square_catalog.php:102` | 3 | **production** |
| `ksf_generate_catalogue` | `0_woocommerce_tokens` | `class.woocommerce_import.php:193` | 3 | **production** |
| `ksf_modules_common` | `0_ksf_isu_config` | `tests/ModuleConfigTest.php:151` | 2 | test fixture |
| `ksf_modules_common` | `0_workcenters` | `class.fa_workcenter.php:56` | 1 | **production** |
| `ksf_payment_destinations` | `0_payment_destinations` | `Tests/Unit/PaymentDestinationRepositoryTest.php:35` | 1 | test fixture |

---

## 6. CONFORMING tables (for reference)

| Repository | Tables |
|---|---|
| `ksf_EstatePlanning` | `0_ksf_estate_planning_beneficiaries`, `0_ksf_estate_planning_events`, `0_ksf_estate_planning_scenarios`, `0_ksf_estate_planning_tax_rates`, `0_ksf_estate_planning_trusts` |
| `ksf_FA_API` | `0_ksf_api_logs` |
| `ksf_FA_CRM` | `0_ksf_crm_account_relationships`, `0_ksf_crm_activity_log`, `0_ksf_crm_communications`, `0_ksf_crm_contact_accounts`, `0_ksf_crm_contact_relationships`, `0_ksf_crm_contacts`, `0_ksf_crm_customer_types`, `0_ksf_crm_customers`, `0_ksf_crm_leads`, `0_ksf_crm_life_events`, `0_ksf_crm_meeting_attendees`, `0_ksf_crm_meetings`, `0_ksf_crm_opportunities`, `0_ksf_crm_option_lists`, `0_ksf_crm_person_account_roles`, `0_ksf_crm_quote_items`, `0_ksf_crm_quotes`, `0_ksf_crm_realms`, `0_ksf_crm_territories` |
| `ksf_FA_Common` | `0_ksf_contact_types`, `0_ksf_item_event_watermark`, `0_ksf_item_sync_state`, `0_ksf_notification_inbox`, `0_ksf_notification_prefs`, `0_ksf_notification_watermark`, `0_ksf_notifications`, `0_ksf_wf_e2e_probe`, `0_ksf_wf_history`, `0_ksf_wf_jobs`, `0_ksf_wf_run_log`, `0_ksf_wf_state` |
| `ksf_FA_DataIntegrity` | `0_ksf_integrity_log` |
| `ksf_FA_EmailManager` | `0_ksf_em_accounts`, `0_ksf_em_inbound_emails`, `0_ksf_em_mailing_lists`, `0_ksf_em_routes`, `0_ksf_em_subscribers` |
| `ksf_FA_EmployeePay` | `0_ksf_employeepay_calculations`, `0_ksf_employeepay_entries`, `0_ksf_employeepay_pay_elements`, `0_ksf_employeepay_section_items`, `0_ksf_employeepay_sections`, `0_ksf_employeepay_settings`, `0_ksf_employeepay_statutory`, `0_ksf_employeepay_tax_brackets` |
| `ksf_FA_EstatePlanning` | `0_ksf_estateplanning_beneficiaries`, `0_ksf_estateplanning_records`, `0_ksf_estateplanning_tax_calcs` |
| `ksf_FA_GPG` | `0_ksf_gpg_files`, `0_ksf_gpg_keys`, `0_ksf_gpg_operations`, `0_ksf_gpg_settings`, `0_ksf_gpg_team_keys` |
| `ksf_FA_HRM` | `0_ksf_hrm_benefits`, `0_ksf_hrm_employee_benefits`, `0_ksf_hrm_leave_balances`, `0_ksf_hrm_payroll`, `0_ksf_hrm_payroll_entries` |
| `ksf_FA_InventoryCount` | `0_ksf_inventory_count_history`, `0_ksf_inventory_scanned` |
| `ksf_FA_Mail` | `0_ksf_mail_accounts` |
| `ksf_FA_ManufacturerConsolidation` | `0_ksf_consolidation_groups`, `0_ksf_consolidation_lines`, `0_ksf_consolidation_recommendations`, `0_ksf_supplier_moq_rules` |
| `ksf_FA_Notes` | `0_ksf_notes`, `0_ksf_notes_link` |
| `ksf_FA_PurchaseOrderTracking` | `0_ksf_po_events`, `0_ksf_po_fill_rates`, `0_ksf_po_lead_times`, `0_ksf_po_tracking_cron` |
| `ksf_FA_Quality` | `0_ksf_quality_8d`, `0_ksf_quality_8d_attachment`, `0_ksf_quality_8d_containment`, `0_ksf_quality_8d_corrective_action`, `0_ksf_quality_8d_implementation`, `0_ksf_quality_8d_prevention`, `0_ksf_quality_8d_recognition`, `0_ksf_quality_8d_root_cause`, `0_ksf_quality_8d_team` |
| `ksf_FA_SerialNumber` | `0_ksf_batch_numbers`, `0_ksf_serial_control`, `0_ksf_serial_location_log`, `0_ksf_serial_numbers`, `0_ksf_serial_ownership` |
| `ksf_FA_Square` | `0_ksf_square_analytics` |
| `ksf_FA_StockReservations` | `0_ksf_stock_reservations` |
| `ksf_FA_StockTurnover` | `0_ksf_stock_turnover_cron`, `0_ksf_stock_turnover_metrics` |
| `ksf_FA_Teams` | `0_ksf_team_members`, `0_ksf_team_projects`, `0_ksf_teams` |
| `ksf_FA_Upc2Item` | `0_ksf_upc2item_items`, `0_ksf_upc2item_pricebook_map`, `0_ksf_upc2item_scans` |
| `ksf_FA_Warehouse` | `0_ksf_wh_aisle`, `0_ksf_wh_bin`, `0_ksf_wh_shelf`, `0_ksf_wh_stock_home` |
| `ksf_payment_destinations` | `0_ksf_payment_destinations` |

---

## 7. The shared preference store

* `0_ksf_module_prefs` is the single cross-module key/value store, keyed by
  `UNIQUE(module_name, user_id, pref_key)`. `ksf_FA_Common` owns its schema
  (`sql/install.sql`); modules address it through the shared package's
  `PreferenceRepository` / `ModulePreferencesTrait`.
* `ksf_FA_Calendar` still ships its own `ksf_preference_get` /
  `ksf_preference_set` responders that read `TB_PREF . 'ksf_module_prefs'`
  directly. That is the same table, reached by hand-written SQL instead of the
  shared repository — it works, but it is the one place where the store is
  addressed by string concatenation rather than by the shared API.
* **The shared package's default is not in the last release.**
  `PreferenceRepository::DEFAULT_TABLE` became `0_ksf_module_prefs` only
  *after* `ksf_FA_Common` v1.0.14 (commit `05242fe`, untagged). Two
  consequences:
  1. A module that uses `ModulePreferencesTrait` **without naming the table**
     gets the legacy `fa_preference_values` from a v1.0.14 copy — i.e. the
     bug this audit is about.
  2. The estate binds the shared classes to whichever copy of the package
     runs its `compat.php` first (its `class_alias()` calls are what load the
     shared classes). In the live Integration stack that is Calendar's
     v1.0.14 copy, so the corrected default is inert there.
* **Action:** release `ksf_FA_Common` v1.0.15 with the corrected default and
  rebuild every module's `vendor/` so that all copies are the same version.
  Until then, a module that touches the shared store should name the table
  explicitly (as `ksf_FA_Mail` now does).

---

## 8. Recommended cleanup order

1. **Fix the silent failures first** (§5). A module whose code addresses a
   table that does not exist is broken today; a table with a non-conforming
   name still works.
2. **Release `ksf_FA_Common` v1.0.15** and rebuild the estate's vendors, so
   the shared preference store has one correct default everywhere (§7).
3. **Rename the `0_fa_*` tables** to `0_ksf_<module>_<noun>` (§4). Each
   rename needs a migration that copies the rows, because the `0_` prefix is
   the company prefix: the new name must be created *and* the old one dropped
   by the module's own `sql/` files, not by hand.
4. **Drop the dead definitions** (§4, “dead definition” rows).
5. **Add a guard test per module** — the pattern `ksf_FA_Mail` now uses in
   `tests/Unit/TableNamingTest.php`: every table the code addresses must be
   created by the module's own schema, and every schema file must carry the
   literal `0_` prefix (`db_import()` replaces only that literal).

---

## 9. Resolution (2026-10-20)

The cleanup pass that followed this audit is done. Every table in the `fa_`
namespace has been renamed to `0_ksf_<owning-module>_<noun>` or removed, and
the estate-wide guard now enforces the rule.

* **Guard:** `tools/check_table_names.py` — run it from the estate root. It
  fails on a literal `0_fa_*` name, on the runtime form `TB_PREF . 'fa_*'`,
  on a table constant holding an `fa_*` name, and on a prefixless
  `CREATE TABLE fa_*`. Migration lines (`ALTER TABLE ... RENAME TO
  0_ksf_*`) and legacy-name constants are allowed; the bare-name-in-SQL
  check is advisory.
* The live Integration database was migrated with
  `ALTER TABLE ... RENAME TO ...` (the form FA's `db_import()` accepts);
  the dead `0_fa_note_links` table was dropped.
* The sections above are kept as the record of what was found. Their table
  names are historical.

---

## Appendix A — reproducing the scan

The scan is a whole-file, string-literal-aware walk over each repository.
The three signals it treats as unambiguous table references are:

```
CREATE TABLE [IF NOT EXISTS] `name`
FROM|JOIN|INTO|UPDATE `name`            (inside a string literal)
TB_PREF . 'name'  /  TB_PREF . "name"
'0_name'                                   (company-prefixed literal)
```

A name is only counted as a table when it is declared somewhere in the
estate, company-prefixed, or reached through `TB_PREF`; everything else in a
SQL string is a column name and is discarded.

