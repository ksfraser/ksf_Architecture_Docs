# KSF Packagist Packages

> **Our composer/packagist catalogue.** Use this before writing new infrastructure —
> if a package already exists, require it instead of re-inventing the wheel.
> Companion to `MODULE_DIRECTORY.md` (ecosystem) and `APP_TAB_ARCHITECTURE.md`
> (tab plugin architecture). Generated from the repos' `composer.json` name fields.

| Field          | Value |
|----------------|-------|
| Canonical copy | `/home/kevin/Documents/PACKAGIST.md` |
| Packages listed | 153 |
| Last generated | 2026-09-14 |

Packagist URL pattern: `https://packagist.org/packages/<package>`.

## Quick picks (most commonly reused)

| Need | Package |
|------|---------|
| Reusable PHP traits (incl. tab renderer traits) | `ksfraser/traits` |
| Shared FA platform utilities / plugin registry | `ksfraser/ksf-fa-common` |
| Product Attributes business logic + tab plugins | `ksfraser/fa-product-attributes-core` |
| Product Attributes FA adapter (exemplar) | `ksfraser/fa-product-attributes` |
| Cross-platform DAO abstraction | `ksfraser/ksf-modules-dao` |
| FA table classes & data-access helpers | `ksfraser/fa-classes` |
| Exception library (factories) | `ksfraser/exceptions` |
| Validation helpers/traits (PHP 7.3+) | `ksfraser/validation` |
| FA function mocks for unit tests | `ksfraser/famock` |
| CRM business logic library | `ksfraser/ksf-crm` |
| HRM business logic library | `ksfraser/ksf_hrm` |
| Project management business library | `ksfraser/ksf-project-management` |
| RBAC library | `ksfraser/rbac` |
| Calendar (aggregates PM/CRM/HRM) | `ksfraser/ksf-calendar` |

## Full catalogue (153 packages)

| Package | Type | Source repo | Description |
|---------|------|-------------|-------------|
| `ksfraser/database` | library | `Database` | Database helpers |
| `ksfraser/exceptions` | library | `Exceptions` | A comprehensive exception library for ksfraser projects with factory methods for domain-specific errors. |
| `ksfraser/fa-product-attributes` | library | `FA_ProductAttributes` | FrontAccounting-compatible ordered product attributes (royal order of adjectives) |
| `ksfraser/fa-product-attributes-core` | library | `FA_ProductAttributes_Core` | Business logic for FA Product Attributes - DAOs, Services, and domain models |
| `ksfraser/fa-product-attributes-variations` | library | `FA_ProductAttributes_Variations` | Product Variations plugin for FA_ProductAttributes |
| `ksfraser/traits` | library | `Traits` | A collection of reusable PHP traits for ksfraser projects |
| `ksfraser/validation` | library | `Validation` (`validation` also carries the same name) | Small validation helpers and traits (PHP 7.3+) for KS Fraser modules migration. |
| `ksfraser/famock` | library | `famock` | FrontAccounting function mocks for unit testing |
| `ksfraser/ksf_asteriskpbx` | library | `ksf_AsteriskPBX` | KSF Asterisk PBX Integration - SMS, Click-to-call, Call Popup, ANI Matching |
| `ksfraser/ksf-crm` | library | `ksf_CRM` | CRM Business Logic Library - Framework-agnostic domain entities, services, and events |
| `ksfraser/gedcom` | library | `ksf_CRM_GEDCOM` | GEDCOM 5.5 parsing and generation library - Framework-agnostic import/export business logic |
| `ksfraser/ksf_crm_ui` | project | `ksf_CRM_UI` | Standalone CRM_UI UI - includes UI, DB service, controller |
| `ksfraser/ksf-calendar` | library | `ksf_Calendar` | Unified calendar system - aggregates PM tasks, CRM activities, HRM time tracking, client dates. iCal import/export, multi-calendar filter, FullCalendar.js ready. Replicates/replaces SuiteCRM, vTiger, WebCalendar calendar views. |
| `ksfraser/ksf-calendar-ui` | library | `ksf_Calendar_UI` | Standalone Calendar UI - FullCalendar.js frontend for ksf_Calendar. Multiple calendar views, drag-and-drop, iCal sync. |
| `ksfraser/ksf-f-campaign-builder` | library | `ksf_CampaignBuilder` (`ksf_FA_CampaignBuilder` also carries this package name) | Visual drag-drop campaign builder for marketing automation |
| `ksfraser/data-io` | library | `ksf_DataIO` | Data import/export library for CSV, Excel, JSON, XML |
| `ksfraser/ksf_documents` | library | `ksf_Documents` | KSF Documents Library |
| `ksfraser/ksf-ess` | project | `ksf_ESS` | Employee Self-Service Portal |
| `ksfraser/ksf-emailmanager` | php-package | `ksf_EmailManager` | Email Management - IMAP import, routing, mailing lists |
| `ksfraser/ksf_emailmanager_ui` | project | `ksf_EmailManager_UI` | Standalone EmailManager_UI UI - includes UI, DB service, controller |
| `ksfraser/ksf-estateplanning` | library | `ksf_EstatePlanning` | Business logic module for estate planning calculations |
| `ksfraser/ksf_fa_api` | fa-module | `ksf_FA_API` | KSF FrontAccounting API - REST/SOAP + CRM Compatibility Layer (SuiteCRM, SugarCRM, vtiger, OrangeHRM, Odoo, Dolibarr, dotproject, OpenProject, LibreProject) |
| `ksfraser/ksf_fa_assets` | library | `ksf_FA_Assets` | FA module: Equipment assets with depreciation tracking |
| `ksfraser/ksf-fa-attachments` | fa-module | `ksf_FA_Attachments` | Cross-module file attachment management for the ksf_FA ecosystem on FrontAccounting |
| `ksfraser/ksf-fa-crm` | fa-module | `ksf_FA_CRM` | FrontAccounting CRM Adapter |
| `ksfraser/ksf-fa-calendar` | fa-module | `ksf_FA_Calendar` | FA Calendar Module for FrontAccounting |
| `ksfraser/fa-classes` | library | `ksf_FA_Classes` | FrontAccounting-specific table classes and related data access helpers. |
| `ksfraser/ksf-fa-common` | library | `ksf_FA_Common` | Shared FrontAccounting platform utilities, contracts, and extension points for the KSF ecosystem |
| `ksfraser/ksf_fa_coupons` | frontaccounting-module | `ksf_FA_Coupons` | Coupon Management for FrontAccounting (CRM + Sales) |
| `ksfraser/ksf_fa_dataintegrity` | library | `ksf_FA_DataIntegrity` | FrontAccounting Data Integrity Checker — finds orphaned GRNs, invoice/GRN quantity mismatches, allocation drift, and broken purchase/sales chains |
| `ksfraser/ksf-fa-documents` | fa-module | `ksf_FA_Documents` | FA module for Document Management with multi-entity linking, ACL, and shared attachments |
| `ksfraser/ksf-fa-emailmanager` | fa-module | `ksf_FA_EmailManager` | FA EmailManager - FrontAccounting module wrapper |
| `ksfraser/ksf-fa-employeepay` | library | `ksf_FA_EmployeePay` | Canadian employee wage/payroll journal entry module for FrontAccounting |
| `ksfraser/ksf-fa-estateplanning` | library | `ksf_FA_EstatePlanning` | FrontAccounting UI/hooks for estate planning |
| `ksfraser/ksf_fa_fleet` | library | `ksf_FA_Fleet` | FA module: Vehicle fleet with military-style inspections |
| `ksfraser/ksf-f-a-forms` | library | `ksf_FA_Forms` | Form builder with CF7 integration for FrontAccounting |
| `ksfraser/ksf_fa_gpg` | frontaccounting-module | `ksf_FA_GPG` | FrontAccounting GPG Module - signing and encryption for emails and files |
| `ksfraser/ksf_fa_hrm` | frontaccounting-module | `ksf_FA_HRM` | HRM Module for FrontAccounting - Employee management, org hierarchy, payroll, benefits |
| `ksfraser/import-staging` | fa-module | `ksf_FA_ImportStagingProcessing` | Unified staging tables and processing pipeline for third-party imports into FrontAccounting (WooCommerce, Square API, Square CSV, PayPal, Bank Import) |
| `ksfraser/ksf_fa_inventory_count` | project | `ksf_FA_InventoryCount` | FrontAccounting module: Inventory counting (stock taking) with barcode scan entry, partial/full counts, over/short adjustments via holding tank, bulk import/export and location transfers. Consolidates ksf_Inventory + FA_InventoryCount. |
| `ksfraser/ksf_fa_invoiceallocation` | library | `ksf_FA_InvoiceAllocation` | FrontAccounting event responder module — provides hooks for allocation, GRN, purchase order, and sales order recalculation events via fa_classes repositories |
| `ksfraser/ksf_fa_knowledgebase` | library | `ksf_FA_KnowledgeBase` | FA module: FAQ and knowledge base with ratings |
| `ksfraser/ksf-fa-llm` | fa-module | `ksf_FA_LLM` | FA admin UI for multi-provider LLM connector (ksf_LLM) |
| `ksfraser/ksf_fa_leave` | frontaccounting-module | `ksf_FA_Leave` | Leave Management Module for FrontAccounting |
| `ksfraser/ksf-fa-logging` | library | `ksf_FA_Logging` | FrontAccounting module for structured logging — hook handler, per-module level config, and log viewer UI |
| `ksfraser/ksf_fa_loyalty` | frontaccounting-module | `ksf_FA_Loyalty` | Customer Loyalty Program for FrontAccounting (depends on CRM) |
| `ksfraser/ksf-fa-mail` | fa-module | `ksf_FA_Mail` | SMTP mail module for FrontAccounting using PHPMailer |
| `ksfraser/ksf-fa-nextcloud` | fa-module | `ksf_FA_Nextcloud` | FA UI + hooks for Nextcloud calendar sync (companion to ksf_nextcloud). |
| `ksfraser/ksf-fa-notes` | fa-module | `ksf_FA_Notes` | FA module for Notes/Comments management with multi-entity linking, ACL, and OCR |
| `ksfraser/ksf_fa_onboarding` | project | `ksf_FA_Onboarding` | Onboarding - FA_Onboarding |
| `ksfraser/ksf_fa_orgchart` | project | `ksf_FA_OrgChart` | FA module adapter |
| `ksfraser/ksf_fa_performance` | project | `ksf_FA_Performance` | Performance - FA_Performance |
| `ksfraser/ksf-fa-price-book` | fa-module | `ksf_FA_PriceBook` | FA admin UI for competitive price intelligence (ksf_PriceBook) |
| `ksfraser/ksf-fa-product-lookup` | fa-module | `ksf_FA_ProductLookup` | FA admin UI for product lookup pipeline (ksf_ProductLookup) |
| `ksfraser/ksf-fa-projectmanagement` | project | `ksf_FA_ProjectManagement` | FA module adapter |
| `ksfraser/ksf-fa-rbac` | fa-module | `ksf_FA_RBAC` | FrontAccounting adapter for ksfraser/rbac — DB repositories, user provisioning, and FA hook integration. |
| `ksfraser/ksf_fa_recruitment` | frontaccounting-module | `ksf_FA_Recruitment` | Recruitment Management Module for FrontAccounting |
| `ksfraser/ksf_fa_service` | library | `ksf_FA_Service` | FA module: Field service and work order management |
| `ksfraser/ksf-fa-square` | frontaccounting-module | `ksf_FA_Square` | FrontAccounting to Square POS Connector - Push products, sync inventory, collect payments via Square Terminal, and import sales orders |
| `ksfraser/ksf_fa_subscriptions` | library | `ksf_FA_Subscriptions` | FA module: On-demand recurring billing with usage tracking |
| `ksfraser/ksf-fa-suggested-purchase-order` | fa-module | `ksf_FA_SuggestedPurchaseOrder` | FA admin UI for suggested purchase orders (ksf_SuggestedPurchaseOrder) |
| `ksfraser/ksf-fa-supporttickets` | fa-module | `ksf_FA_SupportTickets` | FA SupportTickets Module for FrontAccounting |
| `ksfraser/ksf_fa_teams` | fa-module | `ksf_FA_Teams` | FA module - Teams |
| `ksfraser/ksf_fa_timesheets` | project | `ksf_FA_Timesheets` | FA module adapter |
| `ksfraser/ksf-f-a-tracking` | library | `ksf_FA_Tracking` | Website visitor tracking for FrontAccounting |
| `ksfraser/ksf-fa-upc2item` | library | `ksf_FA_Upc2Item` | UPC2Item - Scan barcodes/UPCs, search Amazon/EBay/Facebook Marketplace, and import products into FA Items/Inventory with pricebook mapping. |
| `ksfraser/ksf_fa_wallet` | frontaccounting-module | `ksf_FA_Wallet` | Digital Wallet System for FrontAccounting (extracted from TeraWallet/WooCommerce) |
| `ksfraser/ksf-fa-warrantymanagement` | fa-module | `ksf_FA_WarrantyManagement` | FA WarrantyManagement Module for FrontAccounting |
| `ksfraser/export-woocommerce` | project | `ksf_FA_Woocommerce` | FrontAccounting module for exporting data to WooCommerce via REST API |
| `ksfraser/ksf-fa-business-valuation` | library | `ksf_FA_business_valuation` | FrontAccounting UI/hooks for Business Valuation (ksfraser\FA\BusinessValuation). |
| `ksfraser/ksf-fa-estate` | library | `ksf_FA_estate` | FrontAccounting UI/hooks for estate planning (ksfraser\Estate business logic). |
| `ksfraser/ksf-fa-insurance` | library | `ksf_FA_insurance` | FrontAccounting UI/hooks for insurance planning (ksfraser\FA\Insurance). |
| `ksfraser/ksf-fa-portfolio` | library | `ksf_FA_portfolio` | FrontAccounting UI/hooks for Portfolio Analytics (ksfraser\FA\Portfolio). |
| `ksfraser/ksf-fa-recommendation` | library | `ksf_FA_recommendation` | FrontAccounting UI/hooks for Recommendation (ksfraser\FA\Recommendation). |
| `ksfraser/ksf-fa-retirement` | library | `ksf_FA_retirement` | FrontAccounting UI/hooks for Retirement Planning (ksfraser\FA\Retirement). |
| `ksfraser/ksf-forms` | library | `ksf_Forms` | Form builder library with CF7 integration |
| `ksfraser/ksf_gpg` | library | `ksf_GPG` | GPG business logic library providing key management, signing, encryption, and keyserver operations |
| `ksfraser/ksf-gantt` | library | `ksf_Gantt` | Gantt Chart module for KSF |
| `ksfraser/ksf_hrm` | library | `ksf_HRM` | KSF Human Resource Management Library |
| `ksfraser/ksf_hrm_ui` | project | `ksf_HRM_UI` | HRM_UI |
| `ksfraser/ksf-inventory` | library | `ksf_Inventory` | Inventory module for KSF |
| `ksfraser/ksf-job-descriptions` | php-package | `ksf_JobDescriptions` | Job Descriptions Management for HRM |
| `ksfraser/ksf-knowledgebase` | php-package | `ksf_KnowledgeBase` | Knowledge Base - articles, categories, FAQs |
| `ksfraser/ksf-llm` | library | `ksf_LLM` | Multi-provider LLM connector service for KSF modules |
| `ksfraser/ksf_leave` | library | `ksf_Leave` | KSF Leave Management Library |
| `ksfraser/ksf_leave_ui` | project | `ksf_Leave_UI` | Leave_UI |
| `ksfraser/ksf-marketing` | library | `ksf_Marketing` | Marketing module for KSF |
| `ksfraser/ksf-modulebuilder` | library | `ksf_ModuleBuilder` | Module Builder for KSF |
| `ksfraser/ksf-modules-dao` | library | `ksf_ModulesDAO` | Cross-platform DAO abstraction (DB, WordPress, SuiteCRM, FrontAccounting, CSV, XML) |
| `ksfraser/ksf-common-db` | library | `ksf_common_db` | Transport-agnostic data dictionary + query builder. `DbConnectionInterface` contract with `FaDbAdapter` (native FA `db_*`) and `PdoDbAdapter` (standalone PDO) adapters, `TableDefinition`, `QueryBuilder`. |
| `ksfraser/ksf-nextcloud` | library | `ksf_Nextcloud` | Nextcloud connector (users, files) + CalDAV calendar sync. Business-logic layer of the ksf_nextcloud / ksf_FA_nextcloud module pair. |
| `ksfraser/ksf-notes` | php-package | `ksf_Notes` | Reusable Notes System - polymorphic notes for CRM entities |
| `ksfraser/ksf_notes_ui` | project | `ksf_Notes_UI` | Standalone Notes_UI UI - includes UI, DB service, controller |
| `ksfraser/ksf_onboarding` | library | `ksf_Onboarding` | KSF Onboarding Library |
| `ksfraser/ksf_onboarding_ui` | project | `ksf_Onboarding_UI` | ksf_Onboarding_UI - Onboarding_UI |
| `ksfraser/ksf_orgchart` | library | `ksf_OrgChart` | KSF Org Chart Library - Dual reporting |
| `ksfraser/ksf_orgchart_ui` | project | `ksf_OrgChart_UI` | OrgChart_UI |
| `ksfraser/ksf_performance` | library | `ksf_Performance` | KSF Performance Library |
| `ksfraser/ksf_performance_ui` | project | `ksf_Performance_UI` | ksf_Performance_UI - Performance_UI |
| `ksfraser/ksf-price-book` | library | `ksf_PriceBook` | Competitive price intelligence — screen-scrape competitor/supplier sites to populate price books |
| `ksfraser/ksf-product-lookup` | library | `ksf_ProductLookup` | Product lookup and staging pipeline for FrontAccounting |
| `ksfraser/ksf-project-management` | library | `ksf_ProjectManagement` | Enterprise Project Management library - composer-installable, PSR-4, DI-ready, TDD-first. Replicates/replaces PM capabilities from dotProject, OpenProject, SuiteCRM, vTiger, WebERP, Dolibarr. |
| `ksfraser/ksf-projectmanagement-ui` | library | `ksf_ProjectManagement_UI` | Project Management UI for KSF |
| `ksfraser/rbac` | library | `ksf_RBAC` | Framework-agnostic RBAC library: teams-only principals, SQL-JOIN enforcement, DTO projections, soft-delete, audit logging, switch-role elevation. |
| `ksfraser/ksf_recruitment` | library | `ksf_Recruitment` | KSF Recruitment Library |
| `ksfraser/ksf_recruitment_ui` | project | `ksf_Recruitment_UI` | ksf_Recruitment_UI - Recruitment_UI |
| `ksfraser/ksf-roster` | library | `ksf_Roster` | Roster scheduling library |
| `ksfraser/suggested-purchase-order` | library | `ksf_SuggestedPurchaseOrder` | Suggested purchase order business logic for FrontAccounting |
| `ksfraser/ksf-supporttickets` | library | `ksf_SupportTickets` | Support Tickets Management - Cases/Incidents like SuiteCRM |
| `ksfraser/ksf-supporttickets-ui` | php-package | `ksf_SupportTickets_UI` | Support Tickets UI Components |
| `ksfraser/ksf_teams` | library | `ksf_Teams` | KSF Teams Library - Record ownership/ACL |
| `ksfraser/ksf_teams_ui` | project | `ksf_Teams_UI` | Teams_UI |
| `ksfraser/ksf_timesheets` | library | `ksf_Timesheets` | KSF Timesheets Library |
| `ksfraser/ksf_timesheets_ui` | project | `ksf_Timesheets_UI` | Timesheets_UI |
| `ksfraser/ksf-tracking` | library | `ksf_Tracking` | Website visitor tracking library |
| `ksfraser/ksf_training` | library | `ksf_Training` | KSF Training Library |
| `ksfraser/ksf-travel-expense` | project | `ksf_TravelExpense` | Travel Expense Module |
| `ksfraser/ksf-wp-estateplanning` | library | `ksf_WP_EstatePlanning` | WordPress UI/hooks for estate planning |
| `ksfraser/ksf_wp_orgchart` | library | `ksf_WP_OrgChart` | WordPress OrgChart Adapter - Interactive organizational hierarchy visualization |
| `ksfraser/ksf-wp-business-valuation` | wordpress-plugin | `ksf_WP_business_valuation` | WordPress UI/hooks for Business Valuation (ksfraser\WP\BusinessValuation). |
| `ksfraser/ksf-wp-estate` | wordpress-plugin | `ksf_WP_estate` | WordPress UI/hooks for estate planning (ksfraser\Estate business logic). |
| `ksfraser/ksf-wp-insurance` | wordpress-plugin | `ksf_WP_insurance` | WordPress UI/hooks for insurance planning (ksfraser\WP\Insurance). |
| `ksfraser/ksf-wp-portfolio` | wordpress-plugin | `ksf_WP_portfolio` | WordPress UI/hooks for Portfolio Analytics (ksfraser\WP\Portfolio). |
| `ksfraser/ksf-wp-recommendation` | wordpress-plugin | `ksf_WP_recommendation` | WordPress UI/hooks for Recommendation (ksfraser\WP\Recommendation). |
| `ksfraser/ksf-wp-retirement` | wordpress-plugin | `ksf_WP_retirement` | WordPress UI/hooks for Retirement Planning (ksfraser\WP\Retirement). |
| `ksfraser/ksf-wallet-core` | library | `ksf_Wallet_Core` | Wallet business logic (framework-agnostic, extracted from TeraWallet/WooCommerce) |
| `ksfraser/ksf-warrantymanagement` | php-package | `ksf_WarrantyManagement` | Warranty Management - SKU definitions, liability tracking, RMA, claims |
| `ksfraser/ksf-warrantymanagement-ui` | library | `ksf_WarrantyManagement_UI` | Warranty Management UI for KSF |
| `ksfraser/ksf-workflow` | php-package | `ksf_Workflow` | Workflow Engine - triggers, conditions, actions |
| `ksfraser/ksf_workflow_ui` | project | `ksf_Workflow_UI` | Standalone Workflow_UI UI - includes UI, DB service, controller |
| `ksfraser/fa-bank-import` | library | `ksf_bank_import` | A FrontAccounting module for bank import functionality with paired transfer processing. |
| `ksfraser/ksf-business-valuation` | library | `ksf_business_valuation` | Business Valuation calculation engines (ksfraser\BusinessValuation). |
| `ksfraser/ksf-estate` | library | `ksf_estate` | Estate planning calculation engines (probate fees, estate tax, beneficiary analysis, wealth transfer) — common business logic shared across FrontAccounting, SuiteCRM, and WordPress. |
| `ksfraser/ksf_insurance` | library | `ksf_insurance` | Insurance needs, valuation, and policy comparison calculation engines (ksfraser\Insurance). |
| `ksfraser/ksf_modules_common` | library | `ksf_modules_common` | Shared calculation framework for KSF calculation engines: engine contract, calculation context/result, parameter definitions, and validation rules. Common business logic shared across FrontAccounting, SuiteCRM, and WordPress modules. |
| `ksfraser/ksf_payment_destinations` | library | `ksf_payment_destinations` | Direct Invoice Payment Destinations for FrontAccounting |
| `ksfraser/ksf-portfolio` | library | `ksf_portfolio` | Portfolio Analytics calculation engines (ksfraser\Portfolio). |
| `ksfraser/ksf-recommendation` | library | `ksf_recommendation` | Recommendation calculation engines (ksfraser\Recommendation). |
| `ksfraser/ksf-retirement` | library | `ksf_retirement` | Retirement Planning calculation engines (ksfraser\Retirement). |
| `ksfraser/staging-dto` | library | `ksf_staging_dto` | Data Transfer Objects for ISU staging integration |
| `ksfraser/portfolio-math` | library | `portfolio-math` | Portfolio performance calculations: TWR, IRR, drawdown, volatility, asset allocation. Shared library for stockmarket, FrontAccounting, ksfii_app. |
| `ksf/ksf-dynamic-pricing-core` | library | `ksf_DynamicPricing_Core` | Framework-agnostic dynamic pricing engine extracted from WooCommerce DynamicPricing (*note: `ksf/` vendor prefix, not `ksfraser/`*) |
| `ksf/ksf-shipping-core` | library | `ksf_Shipping_Core` | Framework-agnostic shipping rate calculator extracted from WooCommerce Shipping (*note: `ksf/` vendor prefix, not `ksfraser/`*) |
| `ksfraser/ksf-fa-downloader` | library | `ksf_fa_downloader` | FrontAccounting module downloader: search user-configured targets (URL + pattern) and download modules as ZIP |
| `ksfraser/ksf-fa-manufacturer-consolidation` | fa-module | `ksf_FA_ManufacturerConsolidation` | FrontAccounting Manufacturer Consolidation - MOQ rules, order consolidation, supplier minimums |
| `ksfraser/ksf-fa-purchase-order-tracking` | fa-module | `ksf_FA_PurchaseOrderTracking` | FrontAccounting Purchase Order Tracking - tracks PO lead times and fill rates |
| `ksfraser/ksf-fa-quality` | fa-module | `ksf_FA_Quality` | FrontAccounting Quality 8D System - structured problem solving methodology |
| `ksfraser/ksf-fa-rep-audit` | project | `ksf_FA_Rep_Audit` | KSF Audit and Data Integrity Reports for FrontAccounting |
| `ksfraser/ksf-fa-stock-negatives` | fa-module | `ksf_FA_StockNegatives` | FrontAccounting Stock Negatives Report - identifies inventory items with negative quantities |
| `ksfraser/ksf-fa-stock-reservations` | fa-module | `ksf_FA_StockReservations` | FrontAccounting Stock Reservations - prevents overselling by reserving stock for sales orders |
| `ksfraser/ksf-fa-stock-turnover` | fa-module | `ksf_FA_StockTurnover` | FrontAccounting Stock Turnover - tracks inventory turnover, days of inventory, consumption trends |
| `estate-planning-manager/estate-planning-manager` | project | `PersonalRecordsOrganizer` | Estate Planning Manager WordPress Plugin (Personal Records Organizer workspace) |
| `notrinos/notrinos-erp` | project | `NotrinosERP` | A web-based ERP/accounting system written in PHP and MySQL — *unrelated fork present in the dev tree, not a ksf package* |

---
Generated from `composer.json` name fields across `~/Documents/*`. When you add a
new package, note its name/type/description here (re-run the generator or update by
hand) so the catalogue stays current.
