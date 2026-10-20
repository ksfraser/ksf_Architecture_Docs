# Contact-Access Inventory — `ksf_FA_*` and `ksf_*` repositories

**Date:** 2026-10-19  
**Scope:** every repository under `~/Documents` whose name starts with `ksf_FA_` or `ksf_`
(187 directories), minus `ksf_Infrastructure/fa_modules/` (deployed mirrors) and every
`vendor/` tree.  
**Governing decision:** `AGENTS_ARCH.md` §12.2 — *Native FA data access: the shared
contact resolver* (owner decision, 2026-10).  
**Companion:** `Table_Naming_Audit_2026-10.md` (same directory) — where each table
*comes from*. This document is about *where contact data is read from*.

This is a survey, not a cleanup pass. **No source file was modified.**

---

## 1. Why this survey exists

FA core already owns the contact registry:

| Table | Role | Verified |
|---|---|---|
| `0_crm_persons` | the person profile (id, ref, name, name2, address, phone, phone2, fax, email, lang, notes, inactive) | `sql/alter2.3.sql:190` |
| `0_crm_contacts` | the person ↔ entity xref (id, person_id, type, action, entity_id) | `sql/alter2.3.sql:211` |
| `0_crm_categories` | the `(type, action)` role catalogue | `sql/alter2.3.sql:161` |

Those are the **only three** `crm_*` tables FA 2.4.3 core contains. A whole-tree grep
of the FA source for `crm_` table names returns exactly `crm_categories`, `crm_contacts`,
`crm_persons` — nothing else.

Against that, the estate reaches for contact data in three broken ways:

1. **A table that has never existed.** `ksf_FA_CRM/includes/crm_db.inc` addresses
   `TB_PREF . "fa_crm_contacts"` in 16 places. FA's table is `0_crm_contacts` — no `fa_`
   segment. `db_query()` returns `false` **without raising an error**
   (`includes/db/connect_db_mysqli.inc`: `check_db_error()` only fires when the caller
   passes a message), so every one of those statements fails *silently*: reads come back
   empty, writes go nowhere. This is the same failure mode the table-naming audit
   documented for `ksf_FA_Mail`.
2. **The table the owner decision retired.** `0_ksf_crm_contacts` is deprecated; the CRM's
   own `ContactsRepository` and `ContactsService` still read it.
3. **Raw SQL against a real FA core table.** Forty-odd sites hand-write
   `SELECT ... FROM 0_crm_persons` or `0_crm_contacts` where FA ships a function
   (`get_crm_person`, `get_crm_persons`, `get_crm_contact`, `get_person_contacts`) and
   where `ksf_FA_Common` ships a resolver.

The shared contact resolver already exists — `ksfraser\FrontAccounting\Common\ContactResolver\Contract\ContactResolverInterface`
with `FaContactResolver` and `InMemoryContactResolver` implementations
(`ksf_FA_Common/src/ContactResolver/`). **What did not exist is the list of who has to
move onto it.** This document is that list, grouped by intent, because the intent counts
are the justification for the resolver's method surface.

A fourth failure mode showed up only while reading the code, and it is worse than a
wrong table name: **`0_debtors_master` has no `email` column and no `phone` column.**
Verified against `sql/en_US-new.sql:585` and `sql/en_US-demo.sql:659` — sixteen columns,
`debtor_no, name, debtor_ref, address, tax_id, curr_code, sales_type, dimension_id,
dimension2_id, credit_status, payment_terms, discount, pymt_discount, credit_limit,
notes, inactive`. Three repositories look a customer up by email against it and one looks
one up by phone. Those queries reference a column that does not exist, so they fail
silently and return nothing. `ksf_FA_EmailManager/includes/em_db.inc:240` already
documents the correct FA-native shape (person → contact xref → debtor); the other
three did not know it.

---

## 2. Method

* Whole-tree scan of every `*.php`, `*.inc`, `*.sql`, `*.phtml`, `*.module`, `*.install`
  file in all 187 candidate repositories — **4,073 files** — excluding `vendor/`,
  `node_modules/`, `fa_modules/`, `phpdoc/`, build output and dot-directories.
* Table names were collected from three sources: `TB_PREF . "name"` concatenations,
  company-prefixed literals (`'0_name'`), backticked names, and **class/interface
  constants** whose name contains `TABLE`/`TBL` (resolved to their literal and then
  re-located at each use site). The constant pass is what surfaced
  `ksf_FA_Classes/src/FrontAccounting/Repository/CrmPersonRepository.php`
  (`protected $tableName = 'crm_persons'`), which a literal-only scan misses.
* A candidate was kept only when a SQL keyword (`SELECT`, `INSERT`, `UPDATE`, `DELETE`,
  `CREATE`, `REPLACE`, `FROM`, `JOIN`, `LIKE`) occurs within ±500 characters — so a
  table name in prose or in a `MODULE_DIRECTORY.md` is not a finding.
* Native FA function calls were collected separately with a fixed list of the thirteen
  contact functions in `includes/db/crm_contacts_db.inc`, plus
  `get_customer`, `get_customer_name`, `get_customer_contacts`, `get_customer_details`
  in `sales/includes/db/customers_db.inc`.
* **Every table and function cited below was verified to exist (or not) by reading the
  file.** FA core tables were extracted from `ksf_Infrastructure/FA/2.4.3/sql/*.sql`;
  estate tables were extracted from every `*.sql` in every repository. Where a table is
  claimed not to exist, it appears in neither set.
* Classification is mechanical:
  * **NATIVE_OK** — calls an FA native function for FA data.
  * **OWN_TABLE_OK** — addresses a `0_ksf_<owning-module>_*` table the module owns.
  * **WRONG_FA_TABLE** — addresses a name FA core (or any schema in the estate) does
    not expose: `0_fa_*`, `0_crm_leads`, `0_crm_customers`, `0_crm_contact_roles`,
    `0_hr_employees`, `0_employee`, `0_debtors`, `0_debtor_master`, `0_custcontacts`,
    `0_ext_contact_info`, and any `0_fa_*` name whose `CREATE TABLE` omitted the `0_`
    prefix.
  * **DEPRECATED** — `0_ksf_crm_contacts` (retired by the owner decision) and
    `0_fa_crm_notes` (retired by the owning module's own test assertion,
    `ksf_FA_Notes/tests/Unit/NotesSqlTest.php:96`: *"must not touch the retired table"*).
  * **HAND_ROLLED** — raw SQL against a table FA core **does** expose
    (`0_crm_persons`, `0_crm_contacts`, `0_crm_categories`, `0_debtors_master`,
    `0_cust_branch`, `0_suppliers`), i.e. the module re-implements what a native
    function or the shared resolver already serves.

**Caveats.** Names assembled at runtime from a variable (`TB_PREF . $suffix`) are
invisible to a static scan and are under-reported. `0_ksf_contact_types` rows are
registered at activation time, so the *contents* of that registry are not enumerable
from source. The three repositories whose only hits were FA **transaction** tables
(`0_debtor_trans`, `0_debtor_trans_details`, `0_cust_allocations` — `ksf_FA_Payment`,
`ksf_FA_Sales`, `ksf_FA_Rep_Customer` reporting) are excluded: a transaction is not
contact data. `0_debtor_trans_details` *does* carry a `src_id` link to a person, but no
module uses it for contact resolution.

---

## 3. Totals

**144 contact-access sites across 46 repositories.**

| Classification | Sites | Meaning |
|---|---:|---|
| **HAND_ROLLED** | 63 | raw SQL against a table FA core *does* expose — the shared resolver's target audience |
| **WRONG_FA_TABLE** | 46 | a table name that exists nowhere — a real, silent bug |
| **OWN_TABLE_OK** | 23 | the module's own `0_ksf_<module>_*` table — legitimate |
| **DEPRECATED** | 6 | `0_ksf_crm_contacts` / `0_fa_crm_notes` — retired, must not be used |
| **NATIVE_OK** | 6 | already correct: an FA native function for FA data |
| **Total** | **144** | across **46 repositories** |

**Only 6 of 144 sites (4%) are right.** Of those six: two are the production
examples to copy — `ksf_FA_Customer/src/Customer/Services/CustomerService.php:443-465`
and `ksf_FA_ImportStagingProcessing_UI/import_paypal.php:56-59`, both of which create
the person and link it with `add_crm_person()` + `add_crm_contact()`; three are legacy
wrappers over the same native functions (`ksf_FA_Classes/legacy/*`,
`ksf_modules_common/*`); and one is the shared resolver itself.


---

## 4. Findings

Every site is one row. `Lines` are the exact line numbers in the cited file.


| Repository | File | Lines | Table / function | Intent | Class | Note |
|---|---|---|---|---|---|---|
| `ksf_Calendar` | `src/ksfraser/Calendar/Service/CalendarService.php` | 735 | `0_fa_crm_communications` | pull CRM activities into the calendar | **WRONG_FA_TABLE** | never created |
| `ksf_FA_Assets` | `sql/retag_contact_types.sql` | 3 | `0_ksf_contact_types` | re-tag the shared contact-TYPE registry | **OWN_TABLE_OK** | — |
| `ksf_FA_AsteriskPBX` | `includes/asterisk_db.inc` | 125 | `0_debtors_master (WHERE phone)` | reverse phone lookup -> customer | **HAND_ROLLED** | BROKEN: 0_debtors_master has no phone column |
| `ksf_FA_AsteriskPBX` | `includes/asterisk_db.inc` | 108 | `0_ext_contact_info` | reverse phone lookup -> contact | **WRONG_FA_TABLE** | never created |
| `ksf_FA_AsteriskPBX` | `includes/asterisk_db.inc` | 116 | `0_crm_leads` | reverse phone lookup -> lead | **WRONG_FA_TABLE** | never created |
| `ksf_FA_AsteriskPBX` | `includes/asterisk_db.inc` | 21,86 | `0_hr_employees` | employee record | **WRONG_FA_TABLE** | never created |
| `ksf_FA_CRM` | `pages/dashboard.php` | 81,115 | `0_ksf_crm_customers` | CRM customer count | **OWN_TABLE_OK** | — |
| `ksf_FA_CRM` | `pages/dashboard.php; src/FrontAccounting/CRM/Service/LeadsService.php` | dashboard.php:103; LeadsService.php:69 | `0_ksf_crm_leads` | lead count / list | **OWN_TABLE_OK** | a lead is not an FA person; see the gaps section |
| `ksf_FA_CRM` | `sql/retag_contact_types.sql` | 3-5 | `0_ksf_contact_types` | re-tag the shared contact-TYPE registry to this module | **OWN_TABLE_OK** | registry of type names, not person data |
| `ksf_FA_CRM` | `src/FrontAccounting/CRM/Repository/OpportunitiesRepository.php` | 150,167 | `0_ksf_crm_option_lists` | option-list lookups | **OWN_TABLE_OK** | — |
| `ksf_FA_CRM` | `includes/crm_relationships_db.inc; pages/contact_relationships.php; pages/life_events.php; pages/org_chart.php; pages/person_account_roles.php` | crm_relationships_db.inc:60,115,116,125,230; contact_relationships.php:124,125; life_events.php:106; org_chart.php:56,128,129,170; person_account_roles.php:129 | `0_crm_persons` | resolve a person's name/email to label a relationship row | **HAND_ROLLED** | FA core table, reached by raw SQL; get_crm_person() covers it |
| `ksf_FA_CRM` | `includes/gedcom_import.php` | 52,59,79,94,112,135 | `0_crm_persons` | find-or-create a person by ref during GEDCOM import | **HAND_ROLLED** | FA core table, reached by raw SQL; add_crm_person()/get_crm_person() cover it |
| `ksf_FA_CRM` | `pages/dashboard.php` | 116 | `0_debtors_master` | customer name on the dashboard | **HAND_ROLLED** | — |
| `ksf_FA_CRM` | `src/FrontAccounting/CRM/Repository/CommunicationsRepository.php` | 101 | `0_debtors_master` | customer name for a communication | **HAND_ROLLED** | — |
| `ksf_FA_CRM` | `src/FrontAccounting/CRM/Repository/ContactsRepository.php` | 111 | `0_debtors_master` | customer name for a contact row | **HAND_ROLLED** | — |
| `ksf_FA_CRM` | `src/FrontAccounting/CRM/Repository/CustomersRepository.php` | 47,68 | `0_debtors_master` | customer list for a picker | **HAND_ROLLED** | get_customer() / get_customer_name() cover it |
| `ksf_FA_CRM` | `src/FrontAccounting/CRM/Repository/LeadsRepository.php` | 98 | `0_debtors_master` | customer name for a lead | **HAND_ROLLED** | — |
| `ksf_FA_CRM` | `src/FrontAccounting/CRM/Repository/MeetingsRepository.php` | 116 | `0_debtors_master` | customer name for a meeting | **HAND_ROLLED** | — |
| `ksf_FA_CRM` | `src/FrontAccounting/CRM/Repository/OpportunitiesRepository.php` | 111 | `0_debtors_master` | customer name for an opportunity | **HAND_ROLLED** | — |
| `ksf_FA_CRM` | `src/FrontAccounting/CRM/Repository/QuotesRepository.php` | 132 | `0_debtors_master` | customer name for a quote | **HAND_ROLLED** | — |
| `ksf_FA_CRM` | `src/FrontAccounting/CRM/Service/ContactOptionsService.php` | 100 | `0_crm_persons` | person picker list (id, name, email) | **HAND_ROLLED** | FA core table, reached by raw SQL; resolver search() is the intended replacement |
| `ksf_FA_CRM` | `src/FrontAccounting/CRM/Service/DebtorOptionsService.php` | 102 | `0_debtors_master` | debtor picker | **HAND_ROLLED** | — |
| `ksf_FA_CRM` | `sql/ksf_crm_contacts.sql` | 8 | `0_ksf_crm_contacts` | schema of the retired table | **DEPRECATED** | must not be re-created on activation |
| `ksf_FA_CRM` | `src/FrontAccounting/CRM/Repository/ContactsRepository.php` | 13,26-56 | `0_ksf_crm_contacts` | list / save / delete a customer's contacts | **DEPRECATED** | the table the owner decision retired; must not be used or replaced |
| `ksf_FA_CRM` | `src/FrontAccounting/CRM/Service/ContactsService.php` | 74 | `0_ksf_crm_contacts` | contacts-tab field metadata points at the retired table | **DEPRECATED** | — |
| `ksf_FA_CRM` | `hooks.php` | 223 | `0_fa_crm_email_accounts` | per-customer email account | **WRONG_FA_TABLE** | never created |
| `ksf_FA_CRM` | `includes/EmailImportService.php` | 134,142 | `0_fa_crm_contacts` | find the contact row by From/To email when importing a message | **WRONG_FA_TABLE** | same table; also queries c.email, a column the FA xref does not have |
| `ksf_FA_CRM` | `includes/crm_db.inc` | 1156,1202 | `0_crm_campaigns` | campaign list for the opportunity editor | **WRONG_FA_TABLE** | never created |
| `ksf_FA_CRM` | `includes/crm_db.inc` | 116,129,142,168,172,185,199,209,292,305,317,1298,1902,1974 | `0_fa_crm_contacts` | CRUD a customer's contact row; join contacts into opportunities and meetings | **WRONG_FA_TABLE** | FA's table is 0_crm_contacts (no fa_ segment); this one has never existed |
| `ksf_FA_CRM` | `includes/crm_db.inc` | 1739 | `0_fa_crm_activity_log` | activity log | **WRONG_FA_TABLE** | never created |
| `ksf_FA_CRM` | `includes/crm_db.inc` | 224,257,284,291,304,315,335,1504,1517,1676,1695 | `0_fa_crm_communications` | log a communication against a customer; list a customer's communications | **WRONG_FA_TABLE** | never created |
| `ksf_FA_CRM` | `includes/crm_db.inc` | 43,48,70,92,99,1479,1529,1555 | `0_fa_crm_customers` | per-debtor CRM extension row (customer type, segment, discount) | **WRONG_FA_TABLE** | never created |
| `ksf_FA_CRM` | `includes/crm_db.inc` | 566,579,595 | `0_crm_edi_config` | per-customer EDI configuration | **WRONG_FA_TABLE** | never created |
| `ksf_FA_CRM` | `includes/crm_db.inc` | 613,677 | `0_crm_customer_analytics` | per-customer analytics snapshot | **WRONG_FA_TABLE** | never created |
| `ksf_FA_CRM` | `includes/crm_db.inc` | 788 | `0_custcontacts` | list a customer's contacts for the contact panel | **WRONG_FA_TABLE** | never created |
| `ksf_FA_CRM` | `includes/crm_db.inc; includes/crm_ui.inc` | crm_db.inc:186,200,210,431,442,454,460,725,789; crm_ui.inc:516 | `0_crm_contact_roles` | contact-role catalogue | **WRONG_FA_TABLE** | never created |
| `ksf_FA_CRM` | `includes/crm_db.inc; includes/crm_ui.inc` | crm_db.inc:392,402,413,419,711; crm_ui.inc:381 | `0_crm_customer_segments` | customer-segment catalogue | **WRONG_FA_TABLE** | never created |
| `ksf_FA_CRM` | `includes/crm_db.inc; includes/crm_ui.inc` | crm_db.inc:993,1006,1022,1028,1040,1051,1098,1139,1151,1197,1199,1217,1219,1228,1245,1267,1285,1296,1308; crm_ui.inc:872 | `0_crm_meetings / 0_crm_meeting_rooms / 0_crm_meeting_attendees` | meeting, room and attendee (a contact) model | **WRONG_FA_TABLE** | never created |
| `ksf_FA_CRM` | `includes/crm_db.inc; includes/crm_ui.inc; pages/quotes.php` | crm_db.inc:515,531,549,555,850,862,879,886,903,1155,1201,1489,1588,1606,1618,1644,1664,2090,2217,2253,2282; crm_ui.inc:468,602,990; quotes.php:196 | `0_fa_crm_opportunities / 0_crm_opportunities` | sales opportunities attached to a customer and a contact | **WRONG_FA_TABLE** | never created |
| `ksf_FA_CRM` | `includes/crm_db.inc; pages/customer_types.php` | crm_db.inc:105,350,361,374,380,697,1531,1557,1569; customer_types.php:102,145 | `0_fa_crm_customer_types / 0_crm_customer_types` | customer-type catalogue | **WRONG_FA_TABLE** | never created under either name |
| `ksf_FA_CRM` | `includes/crm_db.inc; pages/leads.php` | crm_db.inc:1788,1823,1832,1841,1869,1873,1890,1914; leads.php:174 | `0_fa_crm_leads` | CRM leads | **WRONG_FA_TABLE** | never created |
| `ksf_FA_CRM` | `includes/crm_db.inc; pages/quotes.php` | crm_db.inc:2054,2078,2088,2111,2132,2138,2155; quotes.php:110,194,196 | `0_fa_crm_quotes / 0_fa_crm_quote_items` | CRM quotes and their lines | **WRONG_FA_TABLE** | never created |
| `ksf_FA_CRM` | `includes/crm_db.inc; pages/realms.php` | crm_db.inc:1993,2008,2015,2030,2044; realms.php:131 | `0_fa_crm_realms` | realm catalogue | **WRONG_FA_TABLE** | never created |
| `ksf_FA_CRM` | `includes/crm_db.inc; pages/territories.php` | crm_db.inc:472,483,495,501,739,1532,1558,1578; territories.php:96,132 | `0_fa_crm_territories / 0_crm_territories` | territory catalogue | **WRONG_FA_TABLE** | never created |
| `ksf_FA_CRM` | `includes/crm_relationships_db.inc; pages/account_relationships.php; pages/org_chart.php` | crm_relationships_db.inc:139,151,157,168,173; account_relationships.php:126; org_chart.php:147 | `0_fa_crm_account_relationships` | account-to-account relationships | **WRONG_FA_TABLE** | never created |
| `ksf_FA_CRM` | `includes/crm_relationships_db.inc; pages/contact_relationships.php; pages/org_chart.php; includes/gedcom_import.php` | crm_relationships_db.inc:78,89,95,106,114; contact_relationships.php:123; org_chart.php:127; gedcom_import.php:113,190,217 | `0_fa_crm_contact_relationships` | contact-to-contact relationship rows | **WRONG_FA_TABLE** | never created |
| `ksf_FA_CRM` | `includes/crm_relationships_db.inc; pages/life_events.php; includes/gedcom_import.php` | crm_relationships_db.inc:241,253,259,270,275; life_events.php:105; gedcom_import.php:279 | `0_fa_crm_life_events` | life events attached to a person | **WRONG_FA_TABLE** | never created |
| `ksf_FA_CRM` | `includes/crm_relationships_db.inc; pages/person_account_roles.php; pages/org_chart.php` | crm_relationships_db.inc:185,197,203,214,220,229; person_account_roles.php:128; org_chart.php:169 | `0_fa_crm_person_account_roles` | the role a person plays in an account | **WRONG_FA_TABLE** | never created |
| `ksf_FA_CRM` | `reporting/rep_customer_list.php; reporting/rep_low_gp_sales.php; reporting/rep_sales_commission.php` | rep_customer_list.php:55; rep_low_gp_sales.php:40; rep_sales_commission.php:63 | `0_debtor_master` | customer name in a report | **WRONG_FA_TABLE** | FA's table is 0_debtors_master (plural) |
| `ksf_FA_Calendar` | `sql/retag_contact_types.sql` | 3,4 | `0_ksf_contact_types` | re-tag the shared contact-TYPE registry | **OWN_TABLE_OK** | — |
| `ksf_FA_Classes` | `legacy/class.fa_customer.php; legacy/class.fa_crm_persons.php; legacy/class.fa_crm_contacts.php` | class.fa_customer.php:242,243,244,299,304; class.fa_crm_persons.php:91; class.fa_crm_contacts.php:54 | `add_crm_person / add_crm_contact` | legacy wrappers over the native functions | **NATIVE_OK** | — |
| `ksf_FA_Classes` | `legacy/class.fa_debtors_master_model.php` | 218,219 | `0_crm_contacts + 0_crm_persons` | customer record joined to its contact | **HAND_ROLLED** | legacy class kept for reference |
| `ksf_FA_Classes` | `src/FrontAccounting/Repository/CrmContactRepository.php` | 13 | `0_crm_contacts` | contact-xref DAO: findByPerson, findByEntity, findByType | **HAND_ROLLED** | overlaps resolver findByEntity() |
| `ksf_FA_Classes` | `src/FrontAccounting/Repository/CrmPersonRepository.php` | 13 | `0_crm_persons` | person DAO: findById, findByRef, findByEmail, findActive, search | **HAND_ROLLED** | read-only DAO that overlaps the shared resolver one-for-one |
| `ksf_FA_Classes` | `src/FrontAccounting/Repository/CustomerBranchRepository.php` | 13 | `0_cust_branch` | customer-branch DAO | **HAND_ROLLED** | — |
| `ksf_FA_Classes` | `src/FrontAccounting/Repository/DebtorMasterRepository.php` | 13 | `0_debtors_master` | debtor DAO: findById, findByRef, findByName, findActive | **HAND_ROLLED** | — |
| `ksf_FA_Common` | `src/ContactResolver/FaContactResolver.php` | whole file | `get_crm_person / get_crm_persons / get_crm_contact / get_person_contacts` | the shared contact resolver - the target of this migration | **NATIVE_OK** | already implemented |
| `ksf_FA_Common` | `sql/install.sql` | 16 | `0_ksf_contact_types` | schema of the contact-type registry | **OWN_TABLE_OK** | — |
| `ksf_FA_Common` | `src/ContactType/ContactTypeRegistry.php` | 36,133,163,200,247,255 | `0_ksf_contact_types` | the shared contact-TYPE registry (type names, not people) | **OWN_TABLE_OK** | — |
| `ksf_FA_Common_repo` | `src/ContactType/ContactTypeRegistry.php; sql/install.sql` | ContactTypeRegistry.php:34,128,156,193; install.sql:16,26 | `0_ksf_contact_types` | the shared contact-TYPE registry (older twin of ksf_FA_Common) | **OWN_TABLE_OK** | — |
| `ksf_FA_Coupons` | `includes/coupon_usage_db.inc` | 43 | `0_crm_persons` | customer name on a coupon-usage row | **HAND_ROLLED** | — |
| `ksf_FA_Coupons` | `sql/fa_coupon_usage.sql; sql/fa_coupons.sql` | fa_coupon_usage.sql:4; fa_coupons.sql:5 | `0_fa_coupon_usage / 0_fa_coupons` | coupon and coupon-usage tables | **WRONG_FA_TABLE** | created UNPREFIXED (fa_coupons) but read as TB_PREF.fa_coupons (0_fa_coupons) |
| `ksf_FA_Customer` | `src/Customer/Services/CustomerService.php` | 443,463,465 | `add_crm_person / add_crm_contact` | create the person, then link it to the branch and to the customer | **NATIVE_OK** | the pattern to follow |
| `ksf_FA_Customer` | `src/Customer/Services/CustomerService.php` | 69 | `get_customer` | fetch a customer by id | **NATIVE_OK** | — |
| `ksf_FA_Customer` | `src/Customer/Services/CustomerService.php` | 181 | `0_debtors_master` | customer list | **HAND_ROLLED** | — |
| `ksf_FA_Customer` | `src/Customer/Services/CustomerService.php` | 59 | `0_debtors_master (WHERE email)` | find a customer by email address | **HAND_ROLLED** | BROKEN: 0_debtors_master has no email column; the query fails silently |
| `ksf_FA_DataIntegrity` | `includes/integrity_db.inc; includes/integrity_reconstruction.inc; includes/integrity_ui.inc` | integrity_db.inc:925,927,929; integrity_reconstruction.inc:580,669; integrity_ui.inc:3004 | `0_debtors_master` | debtor + branch on a transaction row; debtor picker | **HAND_ROLLED** | get_customer() covers it |
| `ksf_FA_DataIntegrity` | `includes/integrity_reconstruction.inc` | 257,365,419,490 | `0_suppliers` | supplier record on a reconstructed transaction | **HAND_ROLLED** | — |
| `ksf_FA_DataIntegrity` | `includes/integrity_ui.inc` | 3023 | `0_cust_branch` | branch picker | **HAND_ROLLED** | — |
| `ksf_FA_EmailManager` | `includes/em_db.inc` | 270,271 | `0_crm_contacts + 0_crm_persons` | resolve a debtor_no from a From address (person -> contact xref -> debtor) | **HAND_ROLLED** | the FA-native path, hand-rolled; resolver findByEmail() covers it |
| `ksf_FA_EmailManager` | `includes/em_db.inc` | 291,292 | `0_crm_contacts + 0_crm_persons` | resolve a contact-relation id from an address | **HAND_ROLLED** | resolver findContactById()/findByEmail() cover it |
| `ksf_FA_EmailManager` | `includes/em_routing.inc` | 96 | `0_crm_opportunities` | file an incoming message as a CRM opportunity | **WRONG_FA_TABLE** | never created |
| `ksf_FA_EmailManager` | `pages/campaigns.php` | 68,70 | `0_crm_campaigns` | campaign picker | **WRONG_FA_TABLE** | never created |
| `ksf_FA_EmployeePay` | `sql/install.sql` | 4,13,30,43,76,95,115,129,139,151 | `0_ksf_employeepay_*` | module-owned pay-element / calculation tables | **OWN_TABLE_OK** | — |
| `ksf_FA_EstatePlanning` | `sql/install.sql` | 11 | `0_debtors` | foreign key to a table that does not exist | **WRONG_FA_TABLE** | FA's table is 0_debtors_master |
| `ksf_FA_GPG` | `pages/key_management.php` | 169,170,171 | `0_debtors_master / 0_suppliers / 0_crm_persons` | contact-type -> table map for the key-management screen | **HAND_ROLLED** | — |
| `ksf_FA_GPG` | `src/Adapter/FAContactResolver.php` | 18-21,40-52 | `0_debtors_master / 0_suppliers / 0_crm_persons` | resolve contact_type + contact_id to an email address | **HAND_ROLLED** | BROKEN for 'employee': 0_crm_persons has no person_id column; the whole map bypasses FA's person/contact model |
| `ksf_FA_HRM` | `sql/fa_contacts_banking.sql; sql/fa_contacts_employment.sql; sql/fa_contacts_pii.sql; sql/fa_departments.sql; sql/fa_dependent_details.sql; sql/ksf_hrm_employee_benefits.sql; sql/ksf_hrm_leave_balances.sql; sql/ksf_hrm_payroll.sql` | fa_contacts_banking.sql:20; fa_contacts_employment.sql:31,32; fa_contacts_pii.sql:19; fa_departments.sql:19; fa_dependent_details.sql:20,21; ksf_hrm_employee_benefits.sql:17; ksf_hrm_leave_balances.sql:13; ksf_hrm_payroll.sql:18 | `0_crm_persons` | foreign key from the module's own satellite tables to FA's person | **OWN_TABLE_OK** | the correct pattern: satellite table keyed by FA's person id |
| `ksf_FA_HRM` | `sql/retag_contact_types.sql` | 3-5 | `0_ksf_contact_types` | re-tag the shared contact-TYPE registry | **OWN_TABLE_OK** | — |
| `ksf_FA_HRM` | `e2e_hrm_event_windows.php` | 91,93,107,108,191 | `0_crm_persons` | e2e harness: create and delete a person | **HAND_ROLLED** | exercises the notes-no-default hazard |
| `ksf_FA_HRM` | `sql/crm_categories.sql` | 5 | `0_crm_categories` | register the module's contact categories | **HAND_ROLLED** | native add_crm_category() covers it |
| `ksf_FA_HRM` | `src/Hooks/InstallHook.php` | 143 | `0_crm_categories` | remove the module's own contact category rows on install | **HAND_ROLLED** | native delete_crm_category() covers it |
| `ksf_FA_HRM` | `src/Repository/EmployeeRepository.php` | 22 | `0_crm_persons` | employee row joined to its FA person for name and email | **HAND_ROLLED** | — |
| `ksf_FA_HRM` | `src/Repository/EventEmployeeMembershipRepository.php` | 38,65 | `0_crm_persons` | email -> person, person -> employment membership | **HAND_ROLLED** | — |
| `ksf_FA_HRM` | `src/Repository/LeaveBalanceRepository.php` | 84 | `0_crm_persons` | person name on a leave balance | **HAND_ROLLED** | — |
| `ksf_FA_HRM` | `src/Repository/LeaveRequestRepository.php` | 47,73,87,98,111 | `0_crm_persons` | person name and email on a leave request | **HAND_ROLLED** | — |
| `ksf_FA_HRM` | `src/Repository/LookupRepository.php` | 101,114 | `0_crm_persons` | person picker (id, name) | **HAND_ROLLED** | — |
| `ksf_FA_HRM` | `src/Repository/PayrollRepository.php` | 18,29,72 | `0_crm_persons` | payroll rows joined to the person | **HAND_ROLLED** | — |
| `ksf_FA_HRM` | `src/Service/HrmReportService.php` | 129,152,180,247 | `0_crm_persons` | employee reports joined to the person | **HAND_ROLLED** | — |
| `ksf_FA_HRM` | `import.php; includes/import.php` | import.php:33,43,47; includes/import.php:34,42,46 | `0_ksf_employee / 0_ksf_employees` | employee import upsert | **WRONG_FA_TABLE** | neither table is created by any schema in the estate |
| `ksf_FA_ImportStagingProcessing` | `src/DAO/StagingCustomerDAO.php; src/Models/StagingCustomer.php` | (module-owned) | `0_ksf_import_staging_*` | staging rows for imported customers | **OWN_TABLE_OK** | — |
| `ksf_FA_ImportStagingProcessing_UI` | `import_paypal.php` | 56,59 | `add_crm_person / add_crm_contact` | create a PayPal customer as an FA person and link it as a customer contact | **NATIVE_OK** | the pattern to follow |
| `ksf_FA_ImportStagingProcessing_UI` | `class.ksf_import_external_customers_model.php` | 175,267 | `0_ksf_import_external_customers` | staging table for imported customers | **OWN_TABLE_OK** | — |
| `ksf_FA_Leave` | `includes/leave_db.inc` | 54,80 | `0_hr_employees` | employee name on a leave request | **WRONG_FA_TABLE** | never created |
| `ksf_FA_Loyalty` | `sql/fa_customer_loyalty.sql` | 13 | `0_crm_persons` | foreign key from the loyalty row to FA's person | **OWN_TABLE_OK** | — |
| `ksf_FA_Loyalty` | `includes/loyalty_db.inc` | 34 | `0_crm_persons` | customer name and email on a loyalty row | **HAND_ROLLED** | — |
| `ksf_FA_Loyalty` | `includes/loyalty_db.inc` | 8,17,33,41,48,55 | `0_fa_customer_loyalty` | loyalty record CRUD | **WRONG_FA_TABLE** | created UNPREFIXED (fa_customer_loyalty) but read as 0_fa_customer_loyalty |
| `ksf_FA_Loyalty` | `sql/fa_loyalty_transactions.sql` | 4 | `0_fa_loyalty_transactions` | loyalty transaction table | **WRONG_FA_TABLE** | created UNPREFIXED |
| `ksf_FA_ManufacturerConsolidation` | `sql/install.sql` | 2,19 | `0_ksf_supplier_moq_rules / 0_suppliers` | supplier MOQ rules | **OWN_TABLE_OK** | — |
| `ksf_FA_Notes` | `tests/Unit/NotesLinkTest.php` | 231 | `0_crm_persons` | resolve a person's name for a note link | **HAND_ROLLED** | — |
| `ksf_FA_Notes` | `includes/notes_db.inc` | 49,72,89,122,140,150,174,187 | `0_fa_crm_notes` | CRUD notes attached to an entity (debtor, contact, opportunity) | **DEPRECATED** | the module's own test calls it 'the retired table'; never created |
| `ksf_FA_Notes` | `sql/install.sql` | 4 | `0_fa_crm_notes` | ALTER the retired notes table | **DEPRECATED** | — |
| `ksf_FA_Performance` | `sql/fa_performance_checkins.sql; sql/fa_performance_goals.sql; sql/fa_performance_reviews.sql` | fa_performance_checkins.sql:20; fa_performance_goals.sql:35; fa_performance_reviews.sql:27,28 | `0_crm_persons` | foreign key from the module's own tables to FA's person | **OWN_TABLE_OK** | — |
| `ksf_FA_Performance` | `includes/performance_checkins_db.inc` | 35,36,44,45 | `0_crm_persons` | check-in author name | **HAND_ROLLED** | — |
| `ksf_FA_Performance` | `includes/performance_goals_db.inc` | 34,35,60,61 | `0_crm_persons` | goal owner name | **HAND_ROLLED** | — |
| `ksf_FA_Performance` | `includes/performance_reviews_db.inc` | 35,36,37,45,46,59,60 | `0_crm_persons` | review subject and reviewer names | **HAND_ROLLED** | — |
| `ksf_FA_Performance` | `includes/performance_db.inc` | 1 | `0_hr_employees` | employee table | **WRONG_FA_TABLE** | never created |
| `ksf_FA_ProjectManagement` | `includes/pm_ui.inc` | 180 | `0_debtors_master` | customer picker | **HAND_ROLLED** | — |
| `ksf_FA_ProjectManagement` | `includes/PMContainer.php; includes/pm_db.inc` | PMContainer.php:189,210,222; pm_db.inc:256 | `0_employee / 0_employees` | project assignee | **WRONG_FA_TABLE** | never created |
| `ksf_FA_PurchaseOrderTracking` | `sql/install.sql` | 2,21 | `0_ksf_po_lead_times / 0_suppliers` | purchase-order lead times | **OWN_TABLE_OK** | — |
| `ksf_FA_RBAC` | `sql/retag_contact_types.sql` | 3 | `0_ksf_contact_types` | re-tag the shared contact-TYPE registry | **OWN_TABLE_OK** | — |
| `ksf_FA_RBAC` | `hooks.php` | 535 | `0_cust_branch` | branch-ownership filter | **HAND_ROLLED** | — |
| `ksf_FA_RBAC` | `hooks.php` | 557 | `0_crm_categories` | contact-category list for a record filter | **HAND_ROLLED** | native get_crm_categories() covers it |
| `ksf_FA_RBAC` | `sql/install.sql` | 110 | `0_crm_categories` | register the module's contact categories | **HAND_ROLLED** | native add_crm_category() covers it |
| `ksf_FA_Rep_Customer` | `reporting/rep_cust_statement.php; reporting/rep_customer_ledger.php; reporting/rep_sales_type_summary.php` | rep_cust_statement.php:102; rep_customer_ledger.php:194,195; rep_sales_type_summary.php:47 | `0_debtors_master / 0_cust_branch` | report header (debtor name, address, branch) | **HAND_ROLLED** | — |
| `ksf_FA_Rep_Operations` | `reporting/rep_picklist.php` | 57 | `0_debtors_master` | report header | **HAND_ROLLED** | — |
| `ksf_FA_Roster` | `includes/roster_db.inc` | 38,65 | `0_hr_employees` | employee name on a shift | **WRONG_FA_TABLE** | never created |
| `ksf_FA_Service` | `includes/service_db.inc` | 4,5 | `0_debtors_master` | ticket customer name | **HAND_ROLLED** | — |
| `ksf_FA_Square` | `src/Services/SquareInvoiceService.php` | 329,505,508 | `0_square_customer_mappings` | map a Square customer id to a debtor | **OWN_TABLE_OK** | — |
| `ksf_FA_Square` | `src/Services/SquareInvoiceService.php` | 443 | `0_debtors_master` | the customer's name | **HAND_ROLLED** | get_customer_name() covers it |
| `ksf_FA_Square` | `src/Services/SquareInvoiceService.php` | 469,470,482,483 | `0_crm_contacts + 0_crm_persons` | the customer's email for an invoice (customer contact, then branch contact) | **HAND_ROLLED** | resolver findByCustomer() covers it |
| `ksf_FA_Subscriptions` | `includes/subscriptions_db.inc` | 29 | `0_debtors_master` | subscriber name | **HAND_ROLLED** | — |
| `ksf_FA_SuggestedPurchaseOrder` | `includes/db.inc; pages/vendor_trends.php` | db.inc:193,207,221,366,500; vendor_trends.php:28 | `0_vendor_lead_times` | vendor lead times | **OWN_TABLE_OK** | — |
| `ksf_FA_SuggestedPurchaseOrder` | `includes/db.inc; pages/vendor_trends.php` | db.inc:277,292; vendor_trends.php:27 | `0_suppliers` | supplier name on a suggested order | **HAND_ROLLED** | — |
| `ksf_FA_SupportTickets` | `includes/st_db.inc; pages/tickets.php` | st_db.inc:57; tickets.php:101 | `0_debtors_master` | ticket customer name | **HAND_ROLLED** | — |
| `ksf_FA_Teams` | `includes/teams_db.inc` | 19,64 | `0_hr_employees` | team members and manager | **WRONG_FA_TABLE** | never created |
| `ksf_FA_Timesheets` | `includes/timesheet_db.inc` | 45,75 | `0_hr_employees` | timesheet employee | **WRONG_FA_TABLE** | never created |
| `ksf_FA_Training` | `includes/training_db.inc` | 57 | `0_hr_employees` | enrolment employee | **WRONG_FA_TABLE** | never created |
| `ksf_FA_TravelExpense` | `includes/travel_db.inc` | 221 | `0_travel_suppliers` | travel supplier list | **OWN_TABLE_OK** | — |
| `ksf_FA_TravelExpense` | `includes/travel_db.inc` | 20,38 | `0_hr_employees` | travel request employee | **WRONG_FA_TABLE** | never created |
| `ksf_FA_Woocommerce` | `sql/schema.sql` | 9 | `0_woo_customer_map` | WooCommerce customer mapping | **OWN_TABLE_OK** | — |
| `ksf_Marketing` | `src/Ksfraser/Marketing/DripCampaigns.php; src/Ksfraser/Marketing/LeadScoring.php` | DripCampaigns.php:140; LeadScoring.php:194 | `0_marketing_contacts` | marketing contact list | **WRONG_FA_TABLE** | never created by any schema in the estate |
| `ksf_Marketing` | `src/Ksfraser/Marketing/LeadScoring.php` | 29,75 | `0_marketing_lead_scores` | lead score | **WRONG_FA_TABLE** | never created |
| `ksf_Notes` | `src/ksfraser/Notes/Service/NoteService.php` | 29,49,70,90,104,117,142,164 | `0_fa_crm_notes` | CRUD notes attached to an entity | **DEPRECATED** | older twin of ksf_FA_Notes |
| `ksf_RBAC` | `doc/sql/fa_person_registry_categories.sql` | 28,35,42,47 | `0_crm_categories` | register person-registry categories | **HAND_ROLLED** | — |
| `ksf_WP_CustomerPortal` | `includes/class-ksf-portal-api.php; includes/services/class-ksf-salesman-approval.php; includes/services/class-ksf-woo-sync.php` | class-ksf-portal-api.php:397,524; class-ksf-salesman-approval.php:136,149,180; class-ksf-woo-sync.php:29,349,359 | `0_debtors_master` | debtor record read and write | **HAND_ROLLED** | — |
| `ksf_WP_CustomerPortal` | `includes/services/class-ksf-woo-sync.php` | 264 | `0_debtors_master (WHERE email)` | resolve a debtor from an email before Woo sync | **HAND_ROLLED** | BROKEN: same |
| `ksf_WP_CustomerPortal` | `ksf-customer-portal.php` | 205 | `0_debtors_master (WHERE email)` | resolve a debtor from a WordPress user email | **HAND_ROLLED** | BROKEN: 0_debtors_master has no email column |
| `ksf_WP_CustomerPortal` | `includes/class-ksf-portal-api.php` | 458 | `0_fa_customer_documents` | customer documents for the portal | **WRONG_FA_TABLE** | never created |
| `ksf_bank_import` | `views/DataProviders/CustomerDataProvider.php` | 399 | `0_debtors_master` | customer for a bank transaction | **HAND_ROLLED** | — |
| `ksf_modules_common` | `class.fa_customer.php; class.fa_crm_persons.php; class.fa_crm_contacts.php` | class.fa_customer.php:398,399,400,455,460; class.fa_crm_persons.php:86; class.fa_crm_contacts.php:51 | `add_crm_person / add_crm_contact` | legacy wrappers over the native functions | **NATIVE_OK** | — |
| `ksf_modules_common` | `class.fa_cust.php` | 218 | `0_debtors_master` | find a customer by name | **HAND_ROLLED** | legacy procedural class |
| `ksf_modules_common` | `class.fa_debtors_master_model.php` | 197,198 | `0_crm_contacts + 0_crm_persons` | customer record joined to its contact | **HAND_ROLLED** | legacy procedural class |
| `ksf_suitecrm` | `class.crm_customer.php` | 30 | `0_debtors_master` | customer lookup (commented out) | **HAND_ROLLED** | dormant third-party integration |

---

## 5. Findings by intent — the resolver's required API

The intent count per bucket is what justifies building a shared seam rather than
leaving each module to its own SQL. "Resolver method" names the
`ContactResolverInterface` method that covers the intent **today**; "Native FA
function" names the FA 2.4.3 function the intent maps onto. Both were verified in
the FA source (§10).

| # | Intent | Sites | Repos | Resolver method | Native FA function |
|---|---|---:|---:|---|---|

| **I1** | Resolve the **customer / debtor record** itself (name, address, ref) | 32 | 19 | *not covered* | `get_customer()`, `get_customer_name()`, `get_customer_details()`, `get_customer_by_ref()` |
| **I11** | Resolve an **employee / staff person** | 11 | 11 | *not covered* | **none** — see §8 |
| **I10** | Read the **module-owned contact-TYPE registry** (`0_ksf_contact_types`) | 8 | 7 | *n/a — a different concept* | — |
| **I4** | Resolve **a person by id** (person id → name, email, phone, ref) | 18 | 7 | `findById()` | `get_crm_person()` |
| **I2** | Resolve **the person behind a customer** — the debtor's contact | 11 | 6 | `findByCustomer()` | `get_crm_persons('customer', …)`, `get_customer_contacts()` |
| **I5** | Resolve **by email address** | 8 | 6 | `findByEmail()` | **none** — see §8 |
| **I12** | Resolve a **supplier / vendor contact** | 6 | 5 | `findByEntity('supplier', …)` | `get_crm_persons('supplier', …)` |
| **I15** | Record a **communication / campaign / meeting / opportunity** against a contact | 23 | 4 | *not covered* | **none** — see §8 |
| **I6** | **Attach / detach / re-link** a person to an entity  *(write)* | 4 | 4 | *not covered (read-only contract)* | `add_crm_contact()`, `delete_crm_contact()`, `update_person_contacts()` |
| **I13** | Resolve a **customer-branch contact** | 3 | 3 | `findByEntity('cust_branch', …)` | `get_crm_persons('cust_branch', …)`, `get_branch_contacts()` |
| **I16** | Resolve a **lead / prospect** | 5 | 3 | *not covered* | **none** — see §8 |
| **I9** | Read the **contact-category registry** (`0_crm_categories`) | 5 | 3 | `listContactCategoryIds()` *(ids only)* | `get_crm_categories()`, `get_crm_category()`, `get_crm_category_name()` |
| **I14** | **Attach notes / comments** to a contact | 3 | 2 | *not covered* | **none** — see §8 |
| **I7** | List a **person roster / picker** | 2 | 2 | `search()` | `get_crm_persons(null,…,true)` |
| **I17** | Resolve a **contact by phone number** | 2 | 1 | `search()` *(partial)* | **none** — see §8 |
| **I3** | List **all contacts of an entity** (branch, supplier, meeting, opportunity) | 1 | 1 | `findByEntity()` | `get_crm_persons($type, …)` |
| **I8** | Resolve **one contact relation row by id** | 1 | 1 | `findContactById()` | `get_crm_contact()` |


> Counts are sites, not unique code paths; a repository appears once per intent it
> touches. Rows are ordered by the number of **distinct repositories** that need
> them, because that is the number the resolver's method surface has to answer to.

### 5.1 What the counts say

* **The core is I1, I2, I4, I5 — 69 sites across 26 repositories.** All four are
  already methods on `ContactResolverInterface` (`findById`, `findByCustomer`,
  `findByEntity`, `findByEmail`). That is the justification: four methods, twenty-six
  repositories, and **not one of them is currently on the contract**.
* **I1 — the debtor record — is the single largest bucket (32 sites, 19
  repositories)** and the resolver deliberately does *not* cover it. FA covers it
  perfectly (`get_customer()`, `get_customer_name()`, `get_customer_by_ref()`), so the
  migration for I1 is "call FA's function", not "call the resolver". But nineteen
  repositories each hand-write `SELECT … FROM 0_debtors_master` instead. Either the
  resolver grows a debtor accessor, or a second, smaller seam is needed for the
  *account* as distinct from the *person*. **This is a contract decision, not a
  migration detail.**
* **I11 — "resolve an employee" — is 11 sites across 11 repositories and has no
  working store at all.** Ten of them join `0_hr_employees`, a table no schema in the
  estate creates (FA's own `0_hr_employees` does not exist either). The FA-native
  employee *is* a `0_crm_persons` row plus a `crm_categories` row of type `employee`
  plus a satellite employment table — exactly what `ksf_FA_HRM` already models with
  `0_hrm_contacts_employment` (FK → `0_crm_persons(id)`,
  `sql/fa_contacts_employment.sql:31`). The other ten are pointed at a table that has
  never existed and will never be filled.
* **I6 (attach / detach) is a write intent and the contract does not cover it.** The
  resolver is read-only by design. Attaching a person to a customer must go through
  the native `add_crm_contact()` / `delete_crm_contact()` / `update_person_contacts()`
  directly — which is exactly what `ksf_FA_Customer` and `import_paypal.php` already
  do correctly. It is called out here so the migration plan does not try to force a
  write through a read contract.
* **I15 (23 sites, 4 repositories) and I14, I16 are not resolver work.** They are
  CRM-domain records — communications, campaigns, meetings, opportunities, quotes,
  notes, leads. FA has no such entities and must not grow them. They become
  module-local tables with correct `0_ksf_crm_*` names; the resolver's job is only to
  supply the *person* they hang off.



---

## 6. Dependency readiness

`ksfraser/ksf-fa-common` is a **pure Composer/Packagist package** (v1.0.11), not an FA
module — so adopting the resolver is a `composer.json` change plus an autoload, not an
extension activation, and the resolver is loadable whether or not any other module is
active (which is the rule in `AGENTS_ARCH.md` §12.2: *a shared seam must never be gated
on another module's activation*).

### 6.1 Already depend on `ksfraser/ksf-fa-common` — 7 of 46

These can adopt the resolver immediately; no dependency work.


**Already depend on `ksfraser/ksf-fa-common`** (7 of 46) — they can adopt the resolver with no dependency work:

- `ksf_FA_CRM`
- `ksf_FA_Calendar`
- `ksf_FA_HRM`
- `ksf_FA_Notes`
- `ksf_FA_ProjectManagement`
- `ksf_FA_Square`
- `ksf_FA_SuggestedPurchaseOrder`

**Are the package** (no dependency to add — they own the resolver): `ksf_FA_Common`, `ksf_FA_Common_repo`.

**Need `ksfraser/ksf-fa-common` added to `composer.json`** (37):

- `ksf_Calendar`
- `ksf_FA_Assets`
- `ksf_FA_AsteriskPBX`
- `ksf_FA_Classes`
- `ksf_FA_Coupons`
- `ksf_FA_Customer`
- `ksf_FA_DataIntegrity`
- `ksf_FA_EmailManager`
- `ksf_FA_EmployeePay`
- `ksf_FA_EstatePlanning`
- `ksf_FA_GPG`
- `ksf_FA_ImportStagingProcessing`
- `ksf_FA_ImportStagingProcessing_UI`
- `ksf_FA_Leave`
- `ksf_FA_Loyalty`
- `ksf_FA_ManufacturerConsolidation`
- `ksf_FA_Performance`
- `ksf_FA_PurchaseOrderTracking`
- `ksf_FA_RBAC`
- `ksf_FA_Rep_Customer`
- `ksf_FA_Rep_Operations`
- `ksf_FA_Roster`
- `ksf_FA_Service`
- `ksf_FA_Subscriptions`
- `ksf_FA_SupportTickets`
- `ksf_FA_Teams`
- `ksf_FA_Timesheets`
- `ksf_FA_Training`
- `ksf_FA_TravelExpense`
- `ksf_FA_Woocommerce`
- `ksf_Marketing`
- `ksf_Notes`
- `ksf_RBAC`
- `ksf_WP_CustomerPortal`
- `ksf_bank_import`
- `ksf_modules_common`
- `ksf_suitecrm`


### 6.2 Need `ksfraser/ksf-fa-common` added to `composer.json` — 37



Two of these need a *decision* rather than a `composer require`:

* **`ksf_FA_Classes`** is `ksfraser/fa-classes` and already ships
  `CrmPersonRepository` / `CrmContactRepository` / `DebtorMasterRepository` /
  `CustomerBranchRepository` — read-only DAOs over exactly the tables the resolver
  covers. Adding `ksf-fa-common` to it would create a **circular dependency risk**
  (`ksf-fa-common` does not depend on `fa-classes` today, but three modules vendor
  both). The cleaner move is to make `fa-classes`'s repositories *delegate* to the
  resolver rather than to re-implement it — see §7.2.
* **`ksf_FA_DataIntegrity`** vendors `fa-classes` and `ksf-modules-dao`; it needs the
  resolver only for the debtor-name lookups in `includes/integrity_ui.inc:3004`.

---

## 7. Ambiguities — where two repositories disagree about what "contact" means

These are not code smells; they are **contract gaps**. Each one is a place where a
shared seam has to make a decision that the estate currently makes differently, often
silently. They are listed in rough order of blast radius.

### 7.1 "Contact" is three different things in this estate

| # | Meaning | Where | Danger |
|---|---|---|---|
| 1 | a **person** — one row of `0_crm_persons` | FA core; the resolver's `Contact` | — |
| 2 | a **person↔entity relation** — one row of `0_crm_contacts` | FA core; the resolver's `Contact::getContactId()` | — |
| 3 | a **contact *type*** — a *name* like `employee`, `fa_user`, `invitee`, `resource` | `0_ksf_contact_types`, owned by `ksf_FA_Common/src/ContactType/` | **highest** |

`ksf_FA_Common` ships **two sibling namespaces** that both use the word "contact":
`Common\ContactResolver\` (people) and `Common\ContactType\` (type names). They are
entirely different things. Seven repositories write to or read `0_ksf_contact_types`
(`ksf_FA_Common`, `ksf_FA_Common_repo`, `ksf_FA_CRM`, `ksf_FA_HRM`, `ksf_FA_RBAC`,
`ksf_FA_Assets`, `ksf_FA_Calendar`), and every one of those rows is a *label*, never a
person. A resolver that "resolves a contact type" would be wrong in at least two
directions. **Decision needed:** rename the type registry concept (e.g.
`0_ksf_actor_types`) or rename its namespace, so "contact" in this estate means a
person and only a person.

### 7.2 "Customer" means two different things, and three repos query a column that does not exist

* **The account**: `0_debtors_master` — a *billing* record. Its sixteen columns
  (`sql/en_US-new.sql:585`) include **no `email` and no `phone`**. It has a `name`, an
  `address`, a `tax_id`, a `salesman`, a `credit_limit` — it is a ledger account that
  happens to carry a display name.
* **The human being**: a `0_crm_persons` row, reached from the account through
  `0_crm_contacts` where `type = 'customer'` and `entity_id = <debtor_no>`.

Three repositories look the second up by asking the first for a column it does not
have, and the query fails silently:

| Repository | Site | Query | Outcome |
|---|---|---|---|
| `ksf_FA_Customer` | `src/Customer/Services/CustomerService.php:59` | `SELECT * FROM debtors_master WHERE email = …` | always empty |
| `ksf_WP_CustomerPortal` | `ksf-customer-portal.php:205` | `SELECT debtor_no FROM debtors_master WHERE email = … LIMIT 1` | always null |
| `ksf_WP_CustomerPortal` | `includes/services/class-ksf-woo-sync.php:264` | same | always null |
| `ksf_FA_AsteriskPBX` | `includes/asterisk_db.inc:125` | `SELECT debtor_no, name, phone FROM debtors_master WHERE phone = …` | always empty |

`ksf_FA_EmailManager/includes/em_db.inc:240-262` documents the correct FA-native shape
in full and is the one module that got it right. **Decision needed:** the resolver
needs a `findDebtorByEmail()` (person → contact xref → debtor), because three modules
want exactly that and cannot express it today.

### 7.3 Two shared contact seams already exist, and they overlap almost exactly

| | `ksfraser/ksf-fa-common` → `ContactResolverInterface` | `ksfraser/fa-classes` → `CrmPersonRepository` / `CrmContactRepository` |
|---|---|---|
| Storage | native FA functions only | raw SQL over `0_crm_persons` / `0_crm_contacts` |
| By id | `findById()` | `findById()` |
| By email | `findByEmail()` | `findByEmail()` |
| By entity | `findByEntity()` | `findByEntity()` |
| By person | — | `findByPerson()` |
| Writes | none (by design) | none (hazard H2 in the CRM's own reference doc) |

Three repositories vendor `fa-classes` (`ksf_FA_CRM`, `ksf_FA_DataIntegrity`,
`ksf_FA_InvoiceAllocation`). If the migration simply points modules at
`ksf-fa-common`, the `fa-classes` repositories become a second, parallel, silently
divergent path to the same data — exactly the outcome `AGENTS_ARCH.md` §12.2 forbids.
**Decision needed:** one seam. Either `fa-classes`'s repositories delegate to the
resolver, or the resolver is built on them, but not both.

### 7.4 "The person's contact" vs "the branch's contact"

`0_crm_contacts.type` distinguishes `'customer'` (`entity_id` = a `debtor_no`) from
`'cust_branch'` (`entity_id` = a `branch_code`). The modules pick differently:

* `ksf_FA_Square/src/Services/SquareInvoiceService.php:466-489` tries `'customer'`
  **then** falls back to `'cust_branch'`, preferring the first.
* `ksf_FA_EmailManager/includes/em_db.inc:262` filters on `type = 'customer'` **only**,
  and says so explicitly ("Filtering on type also stops a cust_branch/supplier row …
  being returned").
* `ksf_FA_Customer/src/Customer/Services/CustomerService.php:463,465` writes **both** —
  `'cust_branch'` and `'customer'` — for the same person.

The resolver's `findByEntity($type, $entityId, $action)` takes the type explicitly,
which is right, but `findByCustomer($debtorNo)` hard-codes `'customer'`. A module
wanting "any contact of this account, branch included" has no single call.

### 7.5 "Primary contact" has no FA representation

`ksf_FA_CRM/includes/crm_db.inc:207-215` implements `get_primary_contact($debtor_no)`
against a `is_primary` column on its **own** deprecated contact table. FA's
`0_crm_contacts` has **no** primary flag, and neither does the resolver's `Contact`.
When the CRM moves to FA's model, "the customer's primary contact" becomes
"the first contact" — an ordering choice with no data behind it. **Decision needed:**
the resolver contract may need a notion of primary, or the CRM must accept the loss
and say so in its requirements.

### 7.6 "Contact role" is richer in the CRM than FA can express

`ksf_FA_CRM`'s `crm_contact_roles` catalogue carried `default_phone` and
`default_email` per role (`crm_db.inc:429-440`). FA's `0_crm_categories` is only
`(id, type, action, name, description, system, inactive)` — **no defaults**. Migrating
the role catalogue to FA's categories loses the default contact details, unless they
are moved onto the person rows or into a CRM satellite table.

### 7.7 "Employee" — a person plus a category, or a table?

Eleven repositories assume a flat employee table `0_hr_employees` (or `0_employee` /
`0_employees`) that **no schema in the estate creates and FA does not expose**. Only
`ksf_FA_HRM` models an employee the FA-native way: a `0_crm_persons` row, a
`crm_categories` row of type `employee`, and a satellite `0_hrm_contacts_employment`
table keyed by `person_id` with an FK to `0_crm_persons(id)`
(`sql/fa_contacts_employment.sql:31`). The other ten are querying a table that will
never be populated. **Decision needed:** HRM's satellite pattern becomes the
standard, and the ten get repointed — or each of them keeps a local employee table
and the resolver is told to ignore them.

### 7.8 "Lead" — three names for one concept inside one module

`ksf_FA_CRM` creates `0_ksf_crm_leads` (`sql/ksf_crm_leads.sql:8`) and reads
`0_fa_crm_leads` (`crm_db.inc:1788-1914`). The dashboard counts the first, the leads
page reads the second. `ksf_FA_AsteriskPBX/includes/asterisk_db.inc:116` reads a
third name, `0_crm_leads`, and `ksf_Marketing` has a fourth, `0_marketing_contacts`
plus `0_marketing_lead_scores`, that no schema creates. A lead is **not** an FA
person: FA has no lead entity. Either a lead becomes a `0_crm_persons` row with
category type `lead` (FA-native, and then the resolver can find it), or leads stay
module-local — but the estate must pick one.

### 7.9 "Notes on a contact" — two live implementations, one retired table

`ksf_FA_Notes` has *two* implementations side by side:

* `includes/ksf_notes_db.inc` — the new one, table `ksf_Notes`; it is what
  `hooks.php:71` loads. `tests/Unit/NotesSqlTest.php:96` asserts the SQL
  *"must not touch the retired table"*.
* `includes/notes_db.inc` — the old one, table `0_fa_crm_notes`; **not** loaded by
  `hooks.php`, but still present, and `sql/install.sql:4` still runs
  `ALTER TABLE 0_fa_crm_notes` on activation.

`ksf_Notes` is the older twin of the same module and still writes `0_fa_crm_notes` in
eight places. FA has no notes-on-contact concept at all, so this is legitimately
module-local — but the module-local table must be renamed to `0_ksf_notes_*`, and the
retired `0_fa_crm_notes` code deleted rather than left to be re-activated.

### 7.10 Inactive people: two different answers to "list people"

The resolver's `findByEmail()` and `search()` **exclude inactive people by default**
(`FaContactResolver.php:109`, `:256`). `ksf_FA_CRM`'s `ContactOptionsService`
(`src/FrontAccounting/CRM/Service/ContactOptionsService.php:100`) lists **all**
`crm_persons` and lets the UI filter. `ksf_FA_HRM/src/Repository/LookupRepository.php:101`
also lists all. Migrating these to `search()` will change what the pickers show unless
the callers pass `includeInactive = true`.

---

## 8. Where FA's native functions do **not** reach

This section is deliberately explicit. `AGENTS_ARCH.md` §12.2 lists the native
functions; reading them against the intents above shows the seams they do not close.
**These are the cases for extending FA access, extending the resolver, or keeping a
module-local table — they must not be silently dropped.**

| Intent | FA native function | Verdict |
|---|---|---|
| **I5 — resolve by email** | **none** | FA has no person-by-email function. `get_crm_persons()` is a 3-table INNER JOIN (`crm_persons ⋈ crm_contacts ⋈ crm_categories`), so **a person with no contact relation is invisible to it**. The resolver works around this by scanning `get_crm_persons(null,null,null,null,true)` — a full scan, no index, per call. `ksf_FA_CRM`'s `ContactOptionsService` needs a list of **all** persons including relation-less ones: **the resolver cannot reproduce it today**. Either `ksf_FA_Common` gains a `listAllPersons()` that reads `0_crm_persons` directly (the "no raw SQL" rule is owned by that module, so it may make an exception for itself), or FA gains a person-by-email function. |
| **I5 — resolve a debtor from an email** | **none** | Not a person lookup — it is person → contact xref → `debtors_master`. `ksf_FA_EmailManager` hand-rolls it; the resolver has no `findDebtorByEmail()`. Three other repos need it and are currently broken (§7.2). **Candidate resolver extension.** |
| **I5 — resolve a contact by email, get the *relation* id** | `get_crm_contact($id)` only (by id) | `ksf_FA_EmailManager/includes/em_db.inc:291` hand-rolls "contact-relation id for this address". The resolver's `findByEmail()` returns *persons*, not relation rows; `findContactById()` goes the other way. **Candidate resolver extension** (`findContactByEmail()`). |
| **I4 — a person with no contact relation** | `get_crm_person($id)` ✓ (works) | `get_crm_person()` is by id and does not join, so it finds relation-less people. `findById()` is fine. But `get_crm_person()` **writes to an array offset of a `false` result** when the id does not exist — a fatal on PHP 8. The resolver already guards this (`FaContactResolver.php:319-340`, "A missing function, or one that throws … must never take a page down"). |
| **I7 / I4 — list people, including relation-less** | `get_crm_persons(null,…,true)` (INNER JOIN) | Same gap as I5. |
| **I1 — resolve the debtor record** | `get_customer()`, `get_customer_name()`, `get_customer_details()`, `get_customer_by_ref()` ✓ | Covered. But the resolver contract does **not** include a debtor lookup — a deliberate omission (the resolver is about contacts). 19 repositories still hand-roll `SELECT … FROM debtors_master`. **Decision needed:** either a second seam for the debtor record, or the resolver grows a debtor accessor. |
| **I13 — customer-branch contact** | `get_branch_contacts($branch_code, $action=null, $customer_id=null, $default=true)` (`sales/includes/db/branches_db.inc:181`) and `get_cust_branch($customer_id, $branch_code)` ✓ | Covered by FA — and the resolver's `findByEntity('cust_branch', …)` reaches the same rows through `get_crm_persons()`. |
| **I2 — the customer's contacts** | `get_customer_contacts($customer_id, $action=null)` (`sales/includes/db/customers_db.inc:151`) ✓ | Covered. Note it normalises the demo `lang = 'C'` to `''`; the resolver's `findByEntity()` path (`get_crm_persons`) does **not**, so a resolver-built list can carry `lang = 'C'`. **Improvement to make:** `findByCustomer()` should use `get_customer_contacts()`. |
| **I6 — attach / detach / re-link** | `add_crm_contact()`, `delete_crm_contact()`, `delete_crm_contacts()`, `update_person_contacts()`, `add_crm_person()`, `update_crm_person()`, `delete_crm_person()`, `delete_entity_contacts()` ✓ | Covered — but the resolver contract is **read-only**, so writes must call the native functions directly. That is correct and is what `ksf_FA_Customer` and `import_paypal.php` already do. |
| **I9 — the contact-category registry** | `get_crm_categories()`, `get_crm_category()`, `get_crm_category_name()`, `add_crm_category()`, `update_crm_category()`, `delete_crm_category()`, `is_crm_category_used()` ✓ | Covered — but the resolver's `listContactCategoryIds()` returns **ids only**, no names. `ksf_FA_RBAC/hooks.php:557` needs the names to render a filter. **Candidate resolver extension** (`getCategoryName()` / `listCategories()`). |
| **I10 — the contact-TYPE registry** | — | `0_ksf_contact_types` is ours. Not a resolver concern. See §7.1. |
| **I11 — the employee** | **none** | FA has no employee entity. The FA-native shape is person + `crm_categories` type `employee` + a satellite employment table — which only `ksf_FA_HRM` has. Ten other repositories query `0_hr_employees`, which does not exist. **Either HRM's satellite pattern becomes the standard (and the ten are repointed at `ksf_FA_HRM`'s table — a cross-module dependency on HRM, which FA cannot express), or each keeps a local employee table and the resolver is told to ignore them.** This is the one intent with no clean answer. |
| **I14 — notes on a contact** | **none** | FA has no notes concept. Module-local table, renamed to `0_ksf_notes_*`. |
| **I15 — communications, campaigns, meetings, opportunities, quotes, territories, segments, analytics, EDI, realms, life events, relationships** | **none** | All CRM-domain. FA has no such entities. These are legitimately module-local — but the table names are wrong (`0_fa_crm_*` / `0_crm_*`), and the *table-naming* cleanup (§`Table_Naming_Audit_2026-10.md`) is a prerequisite for them to work at all. |
| **I16 — leads** | **none** | FA has no lead entity. See §7.8. |
| **I17 — resolve by phone** | **none** | FA has no phone-indexed person function. The resolver's `search()` matches `phone`/`phone2` — but only for people that have a contact relation, and it is a full scan. `0_debtors_master` has no phone column at all (§7.2). |
| **"inactive" semantics** | `get_crm_persons()` has no inactive filter; `crm_persons.inactive` exists | The resolver chose "exclude inactive by default". Two modules want the opposite (§7.10). The contract's `includeInactive` flag exists, so the seam is fine — the callers must change. |
| **column-name collision in the native relation query** | `get_crm_persons()` selects `p.*` **and** `t.*` — `id`, `type`, `action`, `name`, `inactive` all collide | Documented as hazard **H5** in `ksf_FA_CRM/ProjectDcs/NATIVE-FA-CONTACTS-REFERENCE.md:336`. The resolver already works around it by reading `person_id`/`contact_id` rather than `id`. **Any module that adopts `get_crm_persons()` directly inherits the hazard** — another reason the resolver is the right seam. |
| **silent `action = 'general'` fallback** | `get_crm_persons()` falls back to `action='general'` when a filtered query returns nothing (`includes/db/crm_contacts_db.inc:115-116`) | A query for a customer's *invoice* contact can return the customer's *general* contact, and the caller cannot tell the difference. The resolver inherits this. **Must be documented at the seam.** |

### 8.1 The two functions FA does not auto-load

`includes/db/crm_contacts_db.inc` and `sales/includes/db/customers_db.inc` are **not**
included by `includes/main.inc`. A module that calls the native functions must
`include_once` them itself (both are pure function-definition files, so a guarded
`include_once` is safe).

`FaContactResolver::ensureNativeFunctions()`
(`ksf_FA_Common/src/ContactResolver/FaContactResolver.php:394-411`) includes **only**
`includes/db/crm_contacts_db.inc`. `get_customer_contacts()` — the customer-specific
wrapper in `sales/includes/db/customers_db.inc` — is therefore **not** available to the
resolver today, which is why `findByCustomer()` goes through `get_crm_persons()`
instead and loses the `lang = 'C'` normalisation.

---

## 9. What the migration should do, in priority order

This is the plan the inventory supports. It is not a cleanup pass; nothing here has
been executed.

1. **Fix the silently-broken lookups first** — three `debtors_master WHERE email`
   sites (§7.2) and the `0_hr_employees` family (§7.7) return nothing *today* and
   will keep returning nothing after the resolver migration unless the intent is
   re-expressed. These are user-visible failures, not style.
2. **Repoint the `0_fa_*` table names in `ksf_FA_CRM`** (§4). The CRM alone accounts
   for 24 of the 46 WRONG_FA_TABLE sites; 17 of those rows are in
   `includes/crm_db.inc` alone, at 91 distinct line numbers. Until the names are
   right, no amount of resolver adoption makes the CRM's contact features work. Use
   the `0_ksf_crm_*` family the module already declares in `sql/`.
3. **Retire `0_ksf_crm_contacts`** — `ContactsRepository`, `ContactsService` and
   `sql/ksf_crm_contacts.sql` must stop referencing it, and `activate_extension()`
   must stop creating it.
4. **Adopt the resolver** in the 7 repositories that already depend on
   `ksf-fa-common`, starting with the highest-intent ones: `ksf_FA_CRM` (I1, I2, I4,
   I5), `ksf_FA_HRM` (I4, I5, I9), `ksf_FA_Square` (I2), `ksf_FA_Notes` (I14),
   `ksf_FA_ProjectManagement` (I1, I11).
5. **Add the dependency** in the other 37 (§6.2) and adopt the resolver there.
6. **Settle the ambiguities** (§7) before the migration hard-codes any of them:
   "contact type" vs "contact", the two "customer" meanings, the branch-vs-customer
   contact, "primary contact", the two contact seams (`fa-classes` vs `ksf-fa-common`),
   and the employee model.
7. **Extend the resolver** where §8 says FA cannot reach: `findDebtorByEmail()`,
   `findContactByEmail()`, category **names**, a list of all persons including
   relation-less ones, and — if §7.5 is decided in the CRM's favour — a notion of
   *primary* contact.

---

## 10. Verification notes

Every table and function named in this document was checked against a file, not
assumed:

* **FA core tables** — extracted from `ksf_Infrastructure/FA/2.4.3/sql/*.sql`. The
  only `crm_*` tables are `crm_categories`, `crm_contacts`, `crm_persons`
  (confirmed by a whole-tree grep of the FA source for `crm_` table names).
  `0_debtors_master`'s sixteen columns confirmed at `sql/en_US-new.sql:585` and
  `sql/en_US-demo.sql:659` — **no `email`, no `phone`**.
* **Native functions** — confirmed in
  `ksf_Infrastructure/FA/2.4.3/includes/db/crm_contacts_db.inc` (315 lines) and
  `ksf_Infrastructure/FA/2.4.3/sales/includes/db/customers_db.inc`;
  `get_branch_contacts()` and `get_cust_branch()` confirmed in
  `sales/includes/db/branches_db.inc:181,96`.
* **Estate tables** — extracted from every `*.sql` in every repository. A table named
  in this document as "never created" appears in neither set.
* **The resolver** — `ksf_FA_Common/src/ContactResolver/` read in full: contract
  (7 methods), `FaContactResolver` (415 lines), `InMemoryContactResolver` (271),
  `ContactResolver` front door (285), `Contact` value object (329).
* **The `0_fa_crm_contacts` claim** — independently confirmed by the table-naming
  audit's live-DB check: `SELECT COUNT(*) FROM 0_fa_crm_contacts;` → *ERROR 1146
  (42S02): Table 'ksf_fa.0_fa_crm_contacts' doesn't exist*, while
  `0_ksf_crm_contacts` returns 0 rows.

### 10.1 Repositories examined and found to have no contact access

The scan covered all 187 candidate repositories. These **139** had no contact/person
access site of any kind (no SQL against a contact-ish table, no contact lookup class):

`ksf_Architecture_Docs`, `ksf_AsteriskPBX`, `ksf_business_valuation`, `ksf_Calendar_UI`, `ksf_CampaignBuilder`, `ksf_CampaignBuilder_UI`, `ksf_common_db`, `ksf_common_db_repo`, `ksf_CRM`, `ksf_CRM_GEDCOM`, `ksf_CRM_UI`, `ksf_DataIO`, `ksf_db_security`, `ksf_Documents`, `ksf_Documents_UI`, `ksf_DynamicPricing_Core`, `ksf_EmailManager`, `ksf_EmailManager_UI`, `ksf_ESS`, `ksf_estate`, `ksf_EstatePlanning`, `ksf_FA_API`, `ksf_FA_Attachments`, `ksf_FA_business_valuation`, `ksf_FA_CampaignBuilder`, `ksf_FA_Compliance`, `ksf_FA_CRM_Opportunities`, `ksf_FA_CRM_Tags`, `ksf_FA_CRM_Territories`, `ksf_FA_Documents`, `ksf_fa_downloader`, `ksf_FA_DynamicPricing`, `ksf_FA_EDI`, `ksf_FA_estate`, `ksf_FA_Finance`, `ksf_FA_Fleet`, `ksf_FA_Forms`, `ksf_FA_insurance`, `ksf_FA_InventoryCount`, `ksf_FA_InvoiceAllocation`, `ksf_FA_JobDescriptions`, `ksf_FA_KnowledgeBase`, `ksf_FA_LLM`, `ksf_FA_Logging`, `ksf_FA_Logistics`, `ksf_FA_Mail`, `ksf_FA_Marketing`, `ksf_FA_MRP`, `ksf_FA_Nextcloud`, `ksf_FA_Onboarding`, `ksf_FA_OrgChart`, `ksf_FA_portfolio`, `ksf_FA_PriceBook`, `ksf_FA_ProductLookup`, `ksf_FA_Quality`, `ksf_FA_recommendation`, `ksf_FA_Recruitment`, `ksf_FA_Rep_Audit`, `ksf_FA_Reporting`, `ksf_FA_retirement`, `ksf_FA_SegFunds`, `ksf_FA_SerialNumber`, `ksf_FA_Shipping`, `ksf_FA_StockNegatives`, `ksf_FA_StockReservations`, `ksf_FA_StockTurnover`, `ksf_FA_Timeshets`, `ksf_FA_Tracking`, `ksf_FA_Upc2Item`, `ksf_FA_Wallet`, `ksf_FA_Warehouse`, `ksf_FA_WarrantyManagement`, `ksf_FA_Workflow`, `ksf_Forms`, `ksf_Forms_UI`, `ksf_Gantt`, `ksf_generate_catalogue`, `ksf_GPG`, `ksf_HRM`, `ksf_HRM_UI`, `ksf_insurance`, `ksf_JobDescriptions`, `ksf_JobDescriptions_UI`, `ksf_KnowledgeBase`, `ksf_Leave`, `ksf_Leave_UI`, `ksf_LLM`, `ksf_ModuleBuilder`, `ksf_ModulesDAO`, `ksf_Nextcloud`, `ksf_Notes_UI`, `ksf_Onboarding`, `ksf_Onboarding_UI`, `ksf_OrgChart`, `ksf_OrgChart_UI`, `ksf_payment_destinations`, `ksf_Performance`, `ksf_Performance_UI`, `ksf_portfolio`, `ksf_PriceBook`, `ksf_ProductLookup`, `ksf_ProjectManagement`, `ksf_ProjectManagement_UI`, `ksf_recommendation`, `ksf_Recruitment`, `ksf_Recruitment_UI`, `ksf_retirement`, `ksf_Roster`, `ksf_Roster_UI`, `ksf_Shipping_Core`, `ksf_SIPPhone`, `ksf_staging_dto`, `ksf_stockmarket`, `ksf_SuggestedPurchaseOrder`, `ksf_SupportTickets`, `ksf_SupportTickets_UI`, `ksf_Teams`, `ksf_Teams_UI`, `ksf_Timesheets`, `ksf_Timesheets_UI`, `ksf_Tracking`, `ksf_Tracking_UI`, `ksf_Training`, `ksf_Training_UI`, `ksf_TravelExpense`, `ksf_TravelExpense_UI`, `ksf_Wallet_Core`, `ksf_WarrantyManagement`, `ksf_WarrantyManagement_UI`, `ksf_Workflow`, `ksf_Workflow_UI`, `ksf_WP_business_valuation`, `ksf_WP_estate`, `ksf_WP_EstatePlanning`, `ksf_WP_insurance`, `ksf_WP_OrgChart`, `ksf_WP_portfolio`, `ksf_WP_recommendation`, `ksf_WP_retirement`.

Three repositories were **checked and deliberately excluded** because their only hits
are FA **transaction** tables, not contact data: `ksf_FA_Payment`
(`0_debtor_trans`), `ksf_FA_Sales` (`0_debtor_trans`, `0_debtor_trans_details`) and
the transaction half of `ksf_FA_Rep_Customer`'s reporting.

---

*Inventory produced 2026-10-19. No source file in any repository was modified.*
