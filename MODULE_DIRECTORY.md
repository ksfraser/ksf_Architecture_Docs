# KSF Module Directory

> **Canonical reference for all ksf modules.** Agents: read this file first to understand the ecosystem before searching individual repos.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Shared Libraries (ksfraser/*)            │
│  Traits │ HTML │ Exceptions │ ModulesDAO │ Database │ ...  │
└─────────────────────────────────────────────────────────────┘
         │                    │                    │
┌─────────────────────────────────────────────────────────────┐
│              Business Logic (ksf_<Module>)                  │
│  Framework-agnostic PHP libraries with entities, services,  │
│  repositories, calculation engines. Platform-independent.   │
└─────────────────────────────────────────────────────────────┘
         │                    │                    │
┌──────────────────────┐ ┌──────────────────────┐ ┌──────────┐
│  FA Adapter          │ │  WP Adapter           │ │  UI     │
│  ksf_FA_<Module>     │ │  ksf_WP_<Module>      │ │  ksf_*  │
│  Hooks, pages, SQL   │ │  WP plugin hooks      │ │  _UI    │
└──────────────────────┘ └──────────────────────┘ └──────────┘
```

### Three-Layer Pattern
1. **Business Logic** (`ksf_<Module>`) — Entities, Services, Repositories. No platform dependency.
2. **Platform Adapter** (`ksf_FA_<Module>`) — FA hooks, pages, SQL. Calls business logic via hooks.
3. **UI Layer** (`ksf_<Module>_UI`) — FA-specific page rendering. Thin shell.

### Orchestrator Pattern
- HRM, CRM, PM are **orchestrators** — they own menus and UI shells
- Sub-modules answer hooks to provide form data, DB operations, and business logic
- HRM calls `hook_invoke('ksf_FA_EmployeePay', 'buildForm', $data)` → sub-module responds
- Sub-modules use FA native `db_query`/`db_fetch` OR ModulesDAO for data access
- **Never write raw MySQL connection/query code**

---

## Tier 1 — Core Infrastructure (consumed by 5+ modules)

| Package | Dir | Namespace | Purpose |
|---------|-----|-----------|---------|
| `ksfraser/exceptions` | `Exceptions/` | `ksfraser\Exceptions\` | Centralized exception library (Domain, Utility, CRM, Calendar, PM). 24 dependents. |
| `ksfraser/famock` | `famock/` | `ksfraser\FAMock\` | FA function mocks for unit testing outside live FA. 20 dependents. |
| `ksfraser/ksf-fa-common` | `ksf_FA_Common/` | `ksfraser\FrontAccounting\Common\` | Shared FA platform as a **pure Composer/Packagist package** (v1.0.10, no FA extension — hooks.php deleted). ContactTypeRegistry, SchemaInstaller, Traits (WorkflowHooks, CrudOperations, FlashMessage, CalendarRegistration), plus `FileStorageService` and a `BaseHooks` base class (referenced by ksf_FA_Attachments), `ItemEvents\ItemEventPublisher`, `ExtensionRegistry`, `JobQueue`, `PreferenceRepository`. Loaded lazily via Composer autoload; **not** activated as an extension. |
| `ksfraser/traits` | `Traits/` | `ksfraser\Traits\` | Reusable traits: CrudEventEmitter, EntityState, EventEmitter, HookQueryProvider, InlineTabRenderer, Validatable, Timestamp, PSR-3 FileLogger. 13 dependents. |
| `ksfraser/ksf-modules-dao` | `ksf_ModulesDAO/` | `ksfraser\ModulesDAO\` | Cross-platform DAO: RecordStoreInterface, DbAdapterInterface, KeyValueStoreInterface. Adapters for FA, PDO, WordPress, SuiteCRM. 13 dependents. |
| `ksfraser/database` | `Database/` | `ksfraser\Database\` | Database helper utilities (DbManager static wrapper). 12 dependents. |
| `ksfraser/ksf_modules_common` | `ksf_modules_common/` | `ksfraser\ModulesCommon\` | Calculation framework: engine contract, context/result, parameter definitions, validation rules. 10 dependents. |
| `ksfraser/ksf-common-db` | `ksf_common_db/` | `ksfraser\CommonDb\` | Transport-agnostic data dictionary + query builder. `DbConnectionInterface`, `FaDbAdapter` (native `db_*`, FA runtime), `PdoDbAdapter` (standalone), `TableDefinition`, `QueryBuilder`. Consumed by RBAC. |
| `ksfraser/html` | `ksfraser/html/` | `ksfraser\HTML\` | HTML generation library: Buttons, Cells, Forms, Tables, CSS, Ajax, Themes. |

---

## Tier 2 — Shared Libraries (consumed by 2-4 modules)

| Package | Dir | Namespace | Purpose |
|---------|-----|-----------|---------|
| `ksfraser/validation` | `Validation/` | `ksfraser\Validation\` | Validation helpers and traits |
| `ksfraser/staging-dto` | `ksf_staging_dto/` | `ksfraser\StagingDto\` | DTOs for import staging (Woo, Square, Bank Import) |
| `ksfraser/rbac` | `ksf_RBAC/` | `ksfraser\RBAC\` | Framework-agnostic RBAC: teams, SQL-JOIN enforcement, audit |
| `ksfraser/ksf-llm` | `ksf_LLM/` | `KsfCommon\LLM\` | Multi-provider LLM connector (PHP 8.1+) |
| `ksfraser/ksf_gpg` | `ksf_GPG/` | `ksfraser\GPG\` | GPG key management, signing, encryption |
| `ksfraser/fa-classes` | `ksf_FA_Classes/` | `FrontAccounting\` | FA table classes and data-access helpers |
| `ksfraser/ksf-estate` | `ksf_estate/` | `ksfraser\Estate\` | Estate planning calculations |
| `ksfraser/ksf_insurance` | `ksf_insurance/` | `ksfraser\Insurance\` | Insurance calculations |
| `ksfraser/fa-hooks` | *(vendor)* | `ksfraser\FA_Hooks\` | Lightweight FA hook system |
| `ksfraser/contact-dto` | *(vendor)* | `ksfraser\Contact\` | Shared Contact DTO |

---

## HRM Sub-Modules (Orchestrator Pattern)

HRM (`ksf_FA_HRM`) is an orchestrator. These sub-modules answer hooks:

| Sub-Module | Dir | Tables | Purpose | Status |
|------------|-----|--------|---------|--------|
| **ksf_FA_EmployeePay** | `ksf_FA_EmployeePay/` | `0_ksf_employeepay_*` (8 tables) | Payroll calculations, deductions, entries, settings | Built out |
| **ksf_FA_Leave** | `ksf_FA_Leave/` | `0_leave_*` (9 tables) | Leave requests, approvals, balances, accruals. Depends on `ksf_FA_CRM` for `0_crm_persons` (person records). | Built out |
| **ksf_FA_Recruitment** | `ksf_FA_Recruitment/` | `0_recruit_*` (8 tables) | Job openings, applications, interviews, offers | Built out |
| **ksf_FA_Onboarding** | `ksf_FA_Onboarding/` | `fa_onboarding_*` (3 tables) | Onboarding checklists and workflows. Depends on `ksf_FA_Recruitment` (onboard from recruitment). | Built out |
| **ksf_FA_Performance** | `ksf_FA_Performance/` | `fa_performance_*` (2 tables) | OKR performance management | Built out |
| **ksf_FA_Timesheets** | `ksf_FA_Timesheets/` | `fa_timesheet_*` (2 tables) | Time tracking entries | Built out |
| **ksf_FA_Roster** | `ksf_FA_Roster/` | `fa_roster_*` (3 tables) | Shift scheduling | Built out |
| **ksf_FA_Teams** | `ksf_FA_Teams/` | `fa_teams*` (3 tables) | Team management | Built out |
| **ksf_FA_JobDescriptions** | `ksf_FA_JobDescriptions/` | `fa_job_descriptions` | Job description management | Built out |
| **ksf_FA_OrgChart** | `ksf_FA_OrgChart/` | `fa_org_positions` | Org chart visualization | Built out |
| **ksf_FA_Training** | `ksf_FA_Training/` | `fa_training_*` (3 tables) | Training programs | Built out |

---

## FA Platform Modules (`ksf_FA_*`)

### Core / Infrastructure

| Module | Version | Purpose | Tables |
|--------|---------|---------|--------|
| **ksf_FA_Common** | — | Platform foundation library (pure Composer package, not activated). ContactTypeRegistry, SchemaInstaller. Creates shared tables on demand: `0_ksf_contact_types`, `0_fa_job_queue`, `0_ksf_item_event_watermark`, `0_ksf_item_sync_state`, `0_ksf_notifications`. | on-demand shared tables |
| **ksf_FA_Classes** | — | Base class library (no hooks.php) | None |
| **ksf_FA_RBAC** | 1.0.0 | Role-based access control. Bridges `ksfraser/rbac` to FA. | `0_rbac_teams`, `0_rbac_team_members`, `0_rbac_record_access`, `0_rbac_audit_log` |
| **ksf_FA_GPG** | 2.4.19-0 | GPG signing/encryption. Key management UI. | `0_ksf_gpg_keys`, `0_ksf_gpg_operations`, `0_ksf_gpg_files`, `0_ksf_gpg_settings`, `0_ksf_gpg_team_keys` |
| **ksf_FA_Mail** | — | SMTP mail via PHPMailer. System-wide and per-user accounts. Calendar integration: `cal_mail_with_ical()` → `ksf_mail_send_ical()` call chain for iCal invites. | `0_preference_values` |
| **ksf_FA_Logging** | — | Structured JSON-lines logging. Per-module log levels. | `0_ksf_log_levels` |
| **ksf_FA_API** | 1.0.0 | REST API endpoints | `0_ksf_api_logs` |
| **ksf_FA_DataIntegrity** | 2.4.4 | Purchase/sales chain auditing. Orphan/counter drift detection. | `0_ksf_integrity_log` |

### CRM / Sales

| Module | Version | Purpose | Tables |
|--------|---------|---------|--------|
| **ksf_FA_CRM** | 1.0.0 | Full CRM suite. Customers, contacts, leads, opportunities, communications, quotes, territories. | `0_fa_crm_*` (16 tables) |
| **ksf_FA_Calendar** | 2.5.0 | Calendar/events/meetings. CRM/HRM integration. Has own app tab. | `0_fa_cal_entries`, `0_fa_cal_invitees`, `0_fa_cal_sources` |
| **ksf_FA_CampaignBuilder** | 1.0.0 | Marketing campaign management | `fa_campaigns`, `fa_campaign_nodes` |
| **ksf_FA_EmailManager** | 1.0.0 | Email campaigns, templates, automation | Schema placeholder |
| **ksf_FA_Loyalty** | 1.0.0 | Customer loyalty points/tiers. Depends on `ksf_FA_CRM` (customer contacts). | Schema placeholder |
| **ksf_FA_Coupons** | 1.0.0 | Coupon management | Schema placeholder |

### HR / People (see also HRM Sub-Modules above)

| Module | Version | Purpose | Tables |
|--------|---------|---------|--------|
| **ksf_FA_HRM** | 1.0.0 | **Orchestrator.** Org hierarchy, employees, compensation, payroll, benefits. Has own app tab. | `0_hrm_*` (24 tables) |

### Inventory / Products

| Module | Version | Purpose | Tables |
|--------|---------|---------|--------|
| **ksf_FA_InventoryCount** | 2.4.19-0 | Physical inventory counting, barcode scanning | `0_ksf_inventory_count_history`, `0_ksf_inventory_scanned*` |
| **ksf_FA_Upc2Item** | 2.4.3-0 | UPC barcode scan → product import (Amazon/eBay) | `0_ksf_upc2item_*` (3 tables) |
| **ksf_FA_PriceBook** | — | Competitor price tracking, price scraping | Has own app tab |
| **ksf_FA_ProductLookup** | — | Product search/staging pipeline | Has own app tab |
| **ksf_FA_DynamicPricing** | 1.0.0 | Bulk discounts, role pricing, BOGO | Schema placeholder |
| **ksf_FA_Shipping** | 1.0.0 | Shipping rate calculator | Schema placeholder |

### E-Commerce Integration

| Module | Version | Purpose | Tables |
|--------|---------|---------|--------|
| **ksf_FA_Square** | — | Square POS sync. Items/customers/orders. Has own app tab. | `0_square*`, `0_ksf_import_square_*` (12 tables) |
| **ksf_FA_Woocommerce** | 2.4.3-0 | WooCommerce bidirectional sync | Uses ImportStagingProcessing tables |
| **ksf_FA_ImportStagingProcessing** | — | Unified staging pipeline for all external imports. Source modules: WooCommerce, Square API, Square CSV, PayPal, Bank Import. | `0_staging_*` (8 tables) |
| **ksf_FA_ImportStagingProcessing_UI** | 2.4.3-0 | FA UI for staging pipeline (legacy rename of `FA_ImportSquareUp`) | None (uses ISP tables) |
### Finance / Accounting

| Module | Version | Purpose | Tables |
|--------|---------|---------|--------|
| **ksf_bank_import** | — | Bank statement import (OFX/QFX/CSV). Transaction matching. | Uses FA core tables |
| **ksf_FA_InvoiceAllocation** | 1.0.0 | Hook responder for allocation recalculation | None |
| **ksf_FA_SuggestedPurchaseOrder** | 0.1.0 | PO suggestions from stock trends | `0_suggested_orders*`, `0_stock_trends` |
| **ksf_FA_Subscriptions** | 2.4.3-0 | Recurring billing, renewals | `0_subscriptions*` (4 tables) |
| **ksf_FA_Wallet** | 1.0.0 | Digital wallet (top-up, partial payments, cashback) | Schema placeholder |
| **ksf_FA_Assets** | 1.0.0 | Asset lifecycle + depreciation | `fa_asset_*` (5 tables) |

### Projects / Work

| Module | Version | Purpose | Tables |
|--------|---------|---------|--------|
| **ksf_FA_ProjectManagement** | 1.0.0 | PM with Gantt, tasks, versions, progress tracking | `fa_pm_*` (9 tables) |
| **ksf_FA_Tracking** | 2.4.3-0 | Time/expense tracking | `0_tracking_*` (2 tables) |
| **ksf_FA_TravelExpense** | 2.4.3-0 | Travel requests, expenses, approvals, per diem | `0_travel_*` (5 tables) |
| **ksf_FA_Service** | 2.4.3-0 | Service tickets, scheduling, billing | `0_service_*` (2 tables) |

### Documents / Notes

| Module | Version | Purpose | Tables |
|--------|---------|---------|--------|
| **ksf_FA_Documents** | 1.0.0 | Document versioning, linking, GPG integration | `fa_documents*` (5 tables) |
| **ksf_FA_Attachments** | — | Cross-module file attachments | `0_fa_attachments`, `0_fa_attachment_audit` |
| **ksf_FA_Notes** | 1.0.0 | Notes/comments on transactions/contacts | `0_fa_crm_notes`, `0_fa_note_links` |
| **ksf_FA_KnowledgeBase** | 1.0.0 | Articles, categories, FAQ | `fa_kb_*` (3 tables) |
| **ksf_FA_Forms** | 1.0.0 | Custom form builder | `fa_forms`, `fa_form_submissions` |

### Other

| Module | Version | Purpose | Tables |
|--------|---------|---------|--------|
| **ksf_FA_Fleet** | 1.0.0 | Vehicle fleet management | `fa_fleet_*` (4 tables) |
| **ksf_FA_AsteriskPBX** | 1.0.0 | Asterisk telephony integration | `fa_asterisk_*` (3 tables) |
| **ksf_FA_Nextcloud** | — | Nextcloud CalDAV sync | `ksfii_nextcloud_config` |
| **ksf_FA_LLM** | — | AI/LLM provider management | Has own app tab |
| **ksf_FA_MRP** | 1.0.0 | Material requirements planning | `ksf_mrp_*` (4 tables) |
| **ksf_FA_Workflow** | 1.0.0 | Workflow management | Schema placeholder |
| **ksf_FA_WarrantyManagement** | 1.0.0 | Warranty tracking/claims | Schema placeholder |
| **ksf_FA_estate** | — | Estate planning (scaffold) | `0_ksfii_estate_plan` |
| **ksf_FA_EstatePlanning** | 1.0.0 | Estate planning records + tax calcs | `0_ksf_estateplanning_*` (3 tables) |
| **ksf_FA_insurance** | — | Insurance planning (scaffold) | None |
| **ksf_FA_portfolio** | — | Portfolio analytics (scaffold) | None |
| **ksf_FA_recommendation** | — | Recommendation engine (scaffold) | None |
| **ksf_FA_retirement** | — | Retirement planning (scaffold) | None |
| **ksf_FA_SegFunds** | — | Segregated funds (legacy, no hooks) | None |
| **ksf_FA_SupportTickets** | — | Support tickets/helpdesk | Schema placeholder |
| **ksf_FA_Quality** | — | Quality/8D issue tracking | `0_ksf_quality_8d*` |
| **ksf_FA_StockReservations** | — | Stock reservation on SO | `0_ksf_stock_reservations` |
| **ksf_FA_StockTurnover** | — | Stock turnover metrics | `0_ksf_stock_turnover_metrics`, `0_ksf_stock_turnover_cron` |
| **ksf_FA_StockNegatives** | — | Negative stock prevention | Schema placeholder |
| **ksf_FA_ManufacturerConsolidation** | — | Manufacturer consolidation suggestions | `0_ksf_consolidation_*`, `0_ksf_supplier_moq_rules` |
| **ksf_FA_PurchaseOrderTracking** | — | PO tracking metrics, GRN/PO hooks | `0_ksf_po_*` |
| **ksf_FA_Rep_Audit** | — | Rep audit report (`reporting/`) | None |
| **ksf_FA_Rep_Customer** | — | Rep customer report (`reporting/`) | None |
| **ksf_FA_Rep_Operations** | — | Rep operations report (`reporting/`) | None |
| **ksf_fa_downloader** | — | FA module download/fetch tool | `01_fa_download_targets`, `02_fa_downloads` |

---

## Business Logic Modules (`ksf_*`)

### Financial Planning / Calculation Engines

| Module | Namespace | Purpose |
|--------|-----------|---------|
| `ksf_estate` | `ksfraser\Estate\` | Estate planning calcs (probate, tax, beneficiary, wealth transfer) |
| `ksf_insurance` | `ksfraser\Insurance\` | Insurance needs, valuation, policy comparison |
| `ksf_retirement` | `ksfraser\Retirement\` | Retirement planning (withdrawal sequencing, tax optimizer) |
| `ksf_business_valuation` | `ksfraser\BusinessValuation\` | Business valuation, buy-sell analysis, succession |
| `ksf_portfolio` | `ksfraser\Portfolio\` | Portfolio analytics (TWR, IRR, drawdown, volatility) |
| `ksf_recommendation` | `ksfraser\Recommendation\` | Planning recommendations engine |
| `ksf_EstatePlanning` | `ksfraser\EstatePlanning\` | Higher-level estate planning (tax calc services) |

### HR / People

| Module | Namespace | Purpose |
|--------|-----------|---------|
| `ksf_HRM` | `ksfraser\` | HRM entities, services, repositories |
| `ksf_Leave` | `ksfraser\` | Leave management library |
| `ksf_Recruitment` | `ksfraser\` | Recruitment library |
| `ksf_Onboarding` | `ksfraser\` | Onboarding workflows |
| `ksf_Performance` | `ksfraser\` | Performance management |
| `ksf_Training` | `ksfraser\` | Training management |
| `ksf_JobDescriptions` | `ksfraser\JobDescriptions\` | Job descriptions |
| `ksf_Roster` | `ksfraser\` | Shift scheduling |
| `ksf_Timesheets` | `ksfraser\` | Time tracking |
| `ksf_OrgChart` | `ksfraser\` | Org chart hierarchies |
| `ksf_Teams` | `ksfraser\` | Teams and ACL |

### CRM / Customer

| Module | Namespace | Purpose |
|--------|-----------|---------|
| `ksf_CRM` | `ksfraser\CRM\` | CRM business logic |
| `ksf_CRM_GEDCOM` | `ksfraser\CRM\GEDCOM\` | GEDCOM genealogy import/export |
| `ksf_SupportTickets` | `ksfraser\` | Support tickets |
| `ksf_EmailManager` | `ksfraser\EmailManager\` | Email management (IMAP) |
| `ksf_Notes` | `ksfraser\` | Polymorphic notes system |
| `ksf_Tracking` | `ksfraser\` | Visitor tracking |
| `ksf_Marketing` | `ksfraser\Marketing\` | Marketing automation (AI, social, drip) |
| `ksf_CampaignBuilder` | `ksfraser\` | Visual campaign builder |

### Commerce / Products

| Module | Namespace | Purpose |
|--------|-----------|---------|
| `ksf_Wallet_Core` | `ksfraser\` | Digital wallet engine |
| `ksf_DynamicPricing_Core` | `ksfraser\` | Dynamic pricing engine |
| `ksf_Shipping_Core` | `ksfraser\` | Shipping rate calculator |
| `ksf_PriceBook` | `KsfPriceBook\` | Competitive price intelligence |
| `ksf_ProductLookup` | `KsfProductLookup\` | Product lookup/staging |
| `ksf_Inventory` | `ksfraser\Inventory\` | Inventory (serial/batch, warehouse, vendor) |
| `ksf_WarrantyManagement` | — | Warranty tracking/claims |
| `ksf_SuggestedPurchaseOrder` | `KsfSuggestedPurchaseOrder\` | PO suggestion engine |

### Infrastructure / Integration

| Module | Namespace | Purpose |
|--------|-----------|---------|
| `ksf_GPG` | `ksfraser\GPG\` | GPG business logic |
| `ksf_Nextcloud` | `ksfraser\Nextcloud\` | Nextcloud connector (OCS, WebDAV, CalDAV) |
| `ksf_AsteriskPBX` | `ksfraser\` | Asterisk telephony |
| `ksf_LLM` | `KsfCommon\LLM\` | Multi-provider LLM connector |
| `ksf_DataIO` | `ksfraser\` | CSV/Excel/JSON/XML import/export |
| `ksf_bank_import` | `ksfraser\FaBankImport\` | Bank statement import |
| `ksf_RBAC` | `ksfraser\` | RBAC library |
| `ksf_ESS` | `ksfraser\` | Employee self-service portal |

---

## UI Adapter Modules (`ksf_*_UI`)

| Module | For | Purpose |
|--------|-----|---------|
| `ksf_Calendar_UI` | ksf_Calendar | FullCalendar.js integration |
| `ksf_CampaignBuilder_UI` | ksf_CampaignBuilder | FA UI pages |
| `ksf_Documents_UI` | ksf_Documents | FA UI pages |
| `ksf_Forms_UI` | ksf_Forms | FA UI pages |
| `ksf_Tracking_UI` | ksf_Tracking | FA UI pages |
| `ksf_HRM_UI` | ksf_FA_HRM | FA HRM UI pages |
| `ksf_JobDescriptions_UI` | ksf_JobDescriptions | FA UI pages |
| `ksf_Leave_UI` | ksf_Leave | FA Leave UI pages |
| `ksf_Notes_UI` | ksf_Notes | FA UI pages |
| `ksf_Onboarding_UI` | ksf_Onboarding | FA UI pages |
| `ksf_OrgChart_UI` | ksf_OrgChart | FA UI pages |
| `ksf_Performance_UI` | ksf_Performance | FA UI pages |
| `ksf_Recruitment_UI` | ksf_Recruitment | FA UI pages |
| `ksf_Roster_UI` | ksf_Roster | FA UI pages |
| `ksf_SupportTickets_UI` | ksf_SupportTickets | FA UI pages |
| `ksf_Teams_UI` | ksf_Teams | FA UI pages |
| `ksf_Timesheets_UI` | ksf_Timesheets | FA UI pages |
| `ksf_Training_UI` | ksf_Training | FA UI pages |
| `ksf_TravelExpense_UI` | ksf_TravelExpense | FA UI pages |
| `ksf_Workflow_UI` | ksf_Workflow | FA UI pages |
| `ksf_WarrantyManagement_UI` | ksf_WarrantyManagement | FA UI pages |
| `ksf_ProjectManagement_UI` | ksf_FA_ProjectManagement | REST API, Gantt, Kanban, Calendar |

---

## WordPress Adapters (`ksf_WP_*`)

| Module | For | Purpose |
|--------|-----|---------|
| `ksf_WP_estate` | ksf_estate | WP UI for estate planning |
| `ksf_WP_insurance` | ksf_insurance | WP UI for insurance |
| `ksf_WP_retirement` | ksf_retirement | WP UI for retirement |
| `ksf_WP_business_valuation` | ksf_business_valuation | WP UI for valuation |
| `ksf_WP_portfolio` | ksf_portfolio | WP UI for portfolio |
| `ksf_WP_recommendation` | ksf_recommendation | WP UI for recommendations |
| `ksf_WP_EstatePlanning` | ksf_EstatePlanning | WP REST API, Gutenberg, shortcodes |
| `ksf_WP_OrgChart` | ksf_OrgChart | WP interactive org chart |
| `ksf_WP_CustomerPortal` | — | WP customer portal |

---

## Key Tables

### Table Prefix Convention
- **New modules**: `0_` prefix (e.g., `0_hrm_departments`)
- **Legacy modules**: bare names (e.g., `fa_campaigns`)
- **PHP code**: use the `TB_PREF` constant, never hardcode `0_`.
- **SQL files (install.sql / uninstall.sql / upgrades)**: use **hardcoded `0_`**
  literal — FA's `db_import()` / `update_databases()` replaces ONLY `0_` → `TB_PREF`
  and does NOT resolve `@TB_PREF@` or `{TB_PREF}`. Never use those placeholders in
  SQL files.

### Shared Tables
- `0_ksf_contact_types` — Contact type registry (ksf_FA_Common; created on demand)
- `0_fa_job_queue` — Job queue (ksf_FA_Common; created on demand)
- `0_ksf_notifications` — Notifications (ksf_FA_Common; created on demand)
- `0_ksf_item_event_watermark` / `0_ksf_item_sync_state` — Item sync watermark + state (ksf_FA_Common; created on demand)
- `0_staging_*` — Unified staging pipeline (ksf_FA_ImportStagingProcessing)
- `0_rbac_*` — RBAC teams and access (ksf_FA_RBAC)

---

## Traits Quick Reference

| Trait | Package | Purpose |
|-------|---------|---------|
| `WorkflowHooksTrait` | ksf_FA_Common | Lifecycle hooks (before_save, after_save, etc.) |
| `CrudOperationsTrait` | ksf_FA_Common | Standardized CRUD with workflow integration |
| `FlashMessageTrait` | ksf_FA_Common | Session-scoped user notifications |
| `CalendarRegistrationTrait` | ksf_FA_Common | Register calendar extensions |
| `CrudEventEmitterTrait` | ksfraser/traits | CRUD event emission |
| `EntityStateTrait` | ksfraser/traits | Entity state tracking |
| `EventEmitterTrait` | ksfraser/traits | Generic event emission |
| `HookQueryProviderTrait` | ksfraser/traits | Hook-based query provision |
| `InlineTabRendererTrait` | ksfraser/traits | FA inline tab rendering |
| `InlineTabSaverTrait` | ksfraser/traits | FA inline tab saving |
| `InlinePostActionsTrait` | ksfraser/traits | FA tab inline POST save/delete via a configured upsert action (v1.4.0) |
| `ValidatableTrait` | ksfraser/traits | Validation integration |
| `TimestampTrait` | ksfraser/traits | Created/updated timestamps |
| `LoggerAwareTrait` | ksfraser/traits | PSR-3 logger injection |

---

*Last updated: 2026-09-14*
