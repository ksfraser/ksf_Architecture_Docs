# EmailManager — Repository Analysis

**Date:** 2026-10-11
**Scope:** `ksfraser/ksf_EmailManager`, `ksfraser/ksf_EmailManager_UI`, `ksfraser/ksf_FA_EmailManager`, plus the deployed copy at `ksf_Infrastructure/fa_modules/ksf_FA_EmailManager` (live in container `ksfii_app-fa`, port 8090).
**Method:** Read-only. Source was not modified. All 500s were reproduced against the running container and diagnosed from Apache/PHP error logs.
**Intended role (per user):** INBOUND email only — an email client like Roundcube. Connect to IMAP, parse messages, persist them, present them on a UI, and route them. NOT subscriber management, NOT outbound campaigns.

---

## 1. Summary Table

| | ksf_EmailManager | ksf_EmailManager_UI | ksf_FA_EmailManager (deployed) |
|---|---|---|---|
| **Role** | Standalone business-logic package | Standalone UI shell | FA extension wrapper |
| **Package name** | `ksfraser/ksf-emailmanager` | `ksfraser/ksf_emailmanager_ui` | `ksfraser/ksf-fa-emailmanager` |
| **Type** | `php-package` | `project` | `fa-module` |
| **PHP constraint** | `>=7.3` | none declared | `>=7.4` |
| **PSR-4** | `Ksfraser\EmailManager\` → `src/Ksfraser/EmailManager/` | `ksf\EmailManager_UI\` → `includes/` | `Ksfraser\` → `src/Ksfraser/` |
| **Runtime deps** | `ksfraser/exceptions ^1.0` | `ksfraser/database *`, `ksfraser/ksf_modulesdao *` | `ksfraser/traits ~1.2.0` |
| **On Packagist** | No (404) | No (404) | No (404) |
| **Commits / last** | 12 / 2026-09-28 | 8 / 2026-09-28 | 24 / 2026-09-29 |
| **Last *code* commit** | `cd3e5cf` (2026-05, entity DTOs) | `ee7ed58` (2026-04-25) | `3a69319` (2026-09-29, schema) |
| **Code volume** | 11 classes | 1 class (18 lines) | 2 `.inc` + 4 pages + `hooks.php` |
| **Maturity** | Prototype / partly broken | **Skeleton stub, non-functional** | Partly functional; **all 4 UI pages broken** |
| **Inbound IMAP implemented?** | Partially (raw `imap_*`, no persistence) | No | **Yes — `sync_email_account()`** |
| **Persists message content?** | No persistence layer at all | No | **Yes** (`body_text`/`body_html` columns) |
| **Attachments** | Field only, never populated | No | Column only, never populated |
| **Contact resolution** | Field only | No | **Yes** (`crm_contacts` ⋈ `crm_persons`, `debtors_master`) |
| **Tests** | 49 pass / 127 assertions (PHPUnit 9) | none (empty dir) | none |
| **BABOK ProjectDcs** | 7 bundled `.md` (~1028 lines) — overstates | 7 files, **1 line each — empty stubs** | 2 real + 5 stubs |
| **SQL** | none | none | 5 per-table files, **no `install.sql`** |
| **Live status** | not deployed | not deployed | **active** (`installed_extensions.php`, both registries) — 4 pages → HTTP 500 |

---

## 2. Question 7 (answered first) — Root Cause of the HTTP 500s

### Root cause: `$path_to_root` is one directory level short in all four pages.

Every page under `pages/` sets `$path_to_root = "../.."` before including FA core. The page lives at `/var/www/html/modules/ksf_FA_EmailManager/pages/<x>.php`, which is **three** levels below the FA root, so `../..` resolves to `/var/www/html/modules`, not `/var/www/html`.

Evidence — `podman logs ksfii_app-fa`:

```
PHP Warning: include_once(../../includes/session.inc): failed to open stream:
  No such file or directory in /var/www/html/modules/ksf_FA_EmailManager/pages/accounts.php on line 9
PHP Warning: include_once(../../includes/ui.inc): failed to open stream ...
PHP Warning: include_once(../../modules/ksf_FA_EmailManager/includes/em_db.inc):
  failed to open stream ...
PHP Fatal error: Uncaught Error: Call to undefined function page() in
  /var/www/html/modules/ksf_FA_EmailManager/pages/accounts.php:13
"GET /modules/ksf_FA_EmailManager/pages/accounts.php HTTP/1.1" 500 211
```

Identical warnings + fatal for `campaigns.php` (line 13), `inbox.php` (line 14) and `mailing_lists.php` (line 13). Confirmed:

```
$ curl -s -o /dev/null -w "%{http_code}" http://localhost:8090/modules/ksf_FA_EmailManager/pages/<x>.php
accounts: 500   campaigns: 500   inbox: 500   mailing_lists: 500
```

**Why the wrong depth is fatal and not merely noisy:** `include_once` failing is only a warning, so `$page_security` is never checked and no FA function is defined. Execution reaches `page(...)` on the next line and dies on `Call to undefined function page()`. One line of wrong arithmetic is the whole 500.

**Proof (read-only probe written to /tmp-equivalent inside the container, then deleted):**

```
getcwd=/var/www/html/modules/ksf_FA_EmailManager/pages
..           realpath=/var/www/html/modules/ksf_FA_EmailManager  session.inc=no  em_db=no
../..        realpath=/var/www/html/modules                      session.inc=no  em_db=no
../../..     realpath=/var/www/html                             session.inc=YES em_db=YES
```

The correct value is `"../../.."`, matching the working sibling module:
`/var/www/html/modules/ksf_FA_Calendar/pages/*.php` → `$path_to_root = '../../..';`
(Source of the bug: `pages/accounts.php:7`, `pages/campaigns.php:7`, `pages/inbox.php:7`, `pages/mailing_lists.php:7` — all four identical.)

### Secondary defects that will surface *after* the `$path_to_root` fix

These are latent and are NOT the current 500 cause, but each will break a page:

1. **`update_mailing_list()` does not exist.** `pages/mailing_lists.php:39` calls it on `UPDATE_ITEM`. `includes/em_db.inc` defines `add_mailing_list` and `get_mailing_list` only (no `update_mailing_list`). Fatal on any list edit. The page's own Delete handler (line 50) sidesteps this by writing raw SQL.
2. **`campaigns.php` queries two tables that no install file creates.** `0_ksf_em_campaign_lists` (lines 24, 34, 43) and `0_ksf_em_campaign_links` (line 100). Verified absent from the live DB. This is a *known, documented, still-unfixed* defect — see the commit message of `a9bf721`: *"Known pre-existing defect, left alone: pages/campaigns.php queries 0_ksf_em_campaign_lists and 0_ksf_em_campaign_links, which are not created by any install file."*
3. **`campaigns.php:68` queries `0_crm_campaigns`, which does not exist** on this install. The `db_query($sql, "Could not get campaigns")` on line 69 passes a message, so FA raises a DB error page. The `@` on line 72 does not help — the first call already errored.
4. **`inbox.php` → `process_inbound_email()` → `em_create_ticket_from_email()` inserts into `0_fa_st_tickets`, which does not exist.** Same for `em_create_opportunity_from_email()` → `0_crm_opportunities` (also absent). The ticket insert is un-suppressed; the opportunity insert is `@`-suppressed and returns 0.
5. **No `add_access_extensions()` after `session.inc`** in any of the four pages. Required by `AGENTS.md` ("Every module page must call `add_access_extensions()` after `session.inc`"). It is never reached today because `session.inc` itself never loads.
6. **`install_tabs()` is empty** (`hooks.php:48-49`). There is no module tab; the four pages are reachable only through `install_options()`'s CRM-app menu (`hooks.php:57-73`), and `campaigns.php`/`inbox.php` use `SA_ksf_FA_EmailManagerVIEW` while `accounts.php`/`mailing_lists.php` use `...MANAGE`.
7. **`sync_email_account()` can never succeed on this container.** `php -m | grep -i imap` in `ksfii_app-fa` returns nothing — the IMAP PHP extension is not installed. The function already guards this (`includes/em_routing.inc:112-114` returns `['error' => 'IMAP extension not available']`), so the Sync button will report that error rather than crash.

---

## 3. ksf_EmailManager (standalone business-logic package)

### Purpose — from docs vs. from code

`composer.json:4` describes *"Email Management - IMAP import, routing, mailing lists"*. That is the **accurate** one-liner. Everything larger is documentation drift:

- `ProjectDcs/Functional Requirements.md` claims 9 functional requirements including FR-EM-001 *"System shall send emails via SMTP"*, FR-EM-005 *"Email Campaign Management"*, FR-EM-006 *"Support Ticket Integration"*, FR-EM-007/008/009 RBAC projections and audit.
- `ProjectDcs/Architecture.md:8` declares **Status: Implemented** and documents a layer tree with `Repository/` and `Exception/` subdirectories, and services `EmailService`, `TemplateService`, `CampaignService`.
- **`src/Ksfraser/EmailManager/Repository/` does not exist. Neither does `Exception/`. None of `EmailService`, `TemplateService`, `CampaignService` exist.** Verified by `find src -type f`.

There is **no SMTP code anywhere** in the package — `grep -rni "smtp\|mail(\|PHPMailer\|fsockopen" src/` returns zero genuine hits. FR-EM-001 through FR-EM-009 are entirely unimplemented.

### Actual code

**Services (3):**

| Class | File | What it actually does |
|---|---|---|
| `EmailFetchService` | `Service/EmailFetchService.php` | Wraps raw `imap_open`/`imap_headers`/`imap_headerinfo`/`imap_fetchstructure`/`imap_fetchbody`/`imap_utf8`/`imap_setflag_full`/`imap_mail_move`/`imap_delete`. Builds an `{host:port/imap/ssl}` mailbox string (line 22) and calls `imap_open` (line 27). `fetchUnread()` / `fetchAll()` iterate by **sequence number**, not UID. `parseEmail()` (line 88) populates message-id, subject, from, to, date, body text/html. **Returns `InboundEmail` objects — never writes to a database.** |
| `EmailRoutingService` | `Service/EmailRoutingService.php` | Pure in-memory rule matcher over an array `$routes` (line 11). Lowercases the To address, optionally matches keywords in subject/body, returns `['action' => …, 'reason' => …]`. Defaults to `action => 'ticket'`. `addTicketKeyword()` / `addOpportunityKeyword()` hardcode `support@` / `sales@`. **Never reads `0_ksf_em_routes`; no DB at all.** |
| `EmailTrackingService` | `Service/EmailTrackingService.php` | **Broken — written against a Laravel/Eloquent + WordPress API that this codebase does not have.** Calls `EmailTracking::query()`, `->where()`, `->whereNotNull()`, `->count()`, `EmailTracking::find()`, `->save()`, `->update()`, `now()`, `home_url()`, and `fn($t) => …` (line 129, arrow fn = PHP 7.4, but composer requires `>=7.3`). Every one of these is undefined here. |

**Entities (7):**

| Class | File | Base class | Status |
|---|---|---|---|
| `InboundEmail` | `Entity/InboundEmail.php` | none (plain DTO) | Real. 21 public props + `toArray`/`fromArray`. Carries `bodyText`, `bodyHtml`, `rawHeaders`, `attachments`, `contactId`, `debtorNo`, `linkedEntityId/Type`. |
| `EmailAccount` | `Entity/EmailAccount.php` | none | Real DTO: host, port, encryption, username, password, sync folder. **Note: plaintext `password` property, no encryption.** |
| `EmailTemplate` | `Entity/EmailTemplate.php` | none | Real DTO. In-memory only. |
| `SentEmail` | `Entity/SentEmail.php` | none | Real DTO. In-memory only. |
| `EmailCampaign` | `Entity/EmailCampaign.php` | none | Real DTO with status constants + `schedule()`/`startSending()`. In-memory only. |
| `EmailTracking` | `Entity/EmailTracking.php` | **`extends Entity`** | **BROKEN.** `Entity` is not declared anywhere in the package or its vendor tree. Also calls Eloquent APIs (`belongsTo`, `whereNotNull`). Fatal on load. |
| `MailingList` + `MailingListSubscriber` | `Entity/MailingList.php` | **`extends BaseEntity`** (`Ksfraser\Core\BaseEntity`) | **BROKEN.** `Ksfraser\Core\BaseEntity` is neither declared nor a declared dependency (`composer.json` requires only `ksfraser/exceptions`). Also references `$this->id` / `$this->createdAt` / `$this->updatedAt` which only the phantom base class would supply. Two classes in one file — PSR-4 violation for `MailingListSubscriber`. |

**Events (1 file, 5 classes):** `Events/EmailEvents.php` — `EmailReceivedEvent`, `EmailRoutedEvent`, `EmailAssociatedEvent`, `MailingListSubscribedEvent`, `MailingListUnsubscribedEvent`. All `extends Ksfraser\Event\Event` — **that class is not present either** (no `ksfraser/event` dependency). Fatal on load. These map 1:1 onto the event names the FA module dispatches (`email_received`, `ticket_created`, `opportunity_created`, `mailinglist.subscribed`) — but the FA module never references this package.

### Inbound capability verdict

IMAP is **partially** implemented: connection, header enumeration and body extraction are real. What is missing:

- **No persistence.** `EmailFetchService` returns DTOs and stops. Nothing writes them anywhere.
- **No POP3.** Zero hits for `pop3` in `src/`.
- **No MIME parsing.** No `mailparse`, no MIME multipart walker. `getBody()` (line 119) hardcodes section `'1'` for text and `'2'` for HTML — a fixed-section assumption that breaks on any multipart message with attachments or quoted replies.
- **No UID support.** Iterates `imap_headers()` by ordinal (`$i = 1..$count`), so the `$limit` is "first N messages", not "N new messages", and nothing is durable across runs.
- **No error handling.** `@imap_open(...)` on line 27 — errors are swallowed and the caller gets `false` with no diagnostics.
- **No IMAP-extension guard.** Unlike the FA module's `em_routing.inc:112`, nothing checks `function_exists('imap_open')`.
- **Attachments never populated.** `InboundEmail::$attachments` exists and `setAttachments()` exists, but `parseEmail()` never calls it and `imap_fetchstructure`'s `$structure` (line 91) is fetched and then unused.

### Persistence / repository layer

**There is none.** No `Repository/` directory, no DAO, no `save()` on `InboundEmail`, no `db_*`/PDO call anywhere in `src/`. The only serialisation is `toArray()`/`fromArray()` on the DTOs — which do encode the **full message content** (`body_text`, `body_html`, `raw_headers`, `attachments`), so the data model *intends* content persistence. It just isn't wired to storage.

### Contact resolution

None. `contactId` and `debtorNo` are nullable int properties on `EmailAccount`, `InboundEmail` and `MailingListSubscriber` that are never assigned from an email address. There is no lookup function, no `crm_contacts` reference, no join.

### ProjectDcs (BABOK)

Present and substantial — `Business Requirements.md` (86), `Use Case.md` (251), `Functional Requirements.md` (188), `Architecture.md` (134), `RTM.md` (137), `Test Plan.md` (178), `UAT Plan.md` (54). **Format deviation:** `AGENTS.md` requires *individual* files (`BR-<MOD>-<NNN>-…md`, `FR-…`, `UT-…`) per requirement; this repo uses 7 bundled documents. **Content is unreliable** — `Architecture.md:8` says "Status: Implemented" while four of the documented layers/classes do not exist.

### Tests

`vendor/bin/phpunit` → **OK (49 tests, 127 assertions)**. Coverage is confined to the five plain-DTO entities plus `EmailRoutingService`. `EmailTracking`, `MailingList`, `MailingListSubscriber` and all five event classes are **untested — and untestable, because loading them fatals**. The 49 green tests therefore certify only the DTO getters/setters.

`phpunit.xml` is also invalid for PHPUnit 9 (`<source>` is a PHPUnit 10 element): *"The configuration file did not pass validation!"*

### Maturity

**Prototype, partly broken.** 12 commits; the last *code* commit is `cd3e5cf` (2026-05) adding the `EmailTemplate`/`SentEmail`/`EmailCampaign` DTOs. All 9 commits after the initial one are either entity-DTO additions or documentation. Not deployed anywhere; not on Packagist; not referenced by the FA module.

---

## 4. ksf_EmailManager_UI (standalone UI shell)

**Essentially empty and non-functional.**

- **Entire code base: one 18-line class.** `includes/ksf_EmailManager_UIDB.php` — `ksf\DatabaseService::getInstance()` returning `new \Ksfraser\Database\Db()`. That class does not exist; `ksfraser/database` is a declared dependency but `vendor/` was never installed (`ls vendor` → *No such file or directory*).
- **Both entry points call classes that do not exist.** `index.php`: `new \ksf\core\App()` → `->run()`. `pages/index.php`: `new \ksf\App()`. Neither `ksf\core\App` nor `ksf\App` is defined anywhere in the repo. Both files are 3–8 lines and would fatal immediately.
- `pages/index.php` emits only `<div id="EmailManager_UI-ui"><h1>EmailManager_UI</h1><!-- UI content here --></div>`.
- **`tests/` is an empty directory.**
- **ProjectDcs: 7 files, each exactly 1 line** (`# Architecture.md`, `# RTM.md`, …). Zero content. This is the weakest documentation in the three repos.
- `composer.json` declares PSR-4 `ksf\EmailManager_UI\` → `includes/`, but the file declares `namespace ksf;` and the class is `ksf\DatabaseService` — it does not match its own PSR-4 mapping.
- Git: 8 commits; last code commit `ee7ed58` (2026-04-25, *"Add Database service, ProjectDcs structure, UI div for FA inclusion"*). Branch `main`; `git status` shows `[gone]` for `origin/main`. Nothing since April.

**Verdict:** an abandoned scaffold. It contributes nothing to the deployed module and can be set aside entirely.

---

## 5. ksf_FA_EmailManager (the deployed FA extension)

This is the only repo that actually runs. The deployed copy at `ksf_Infrastructure/fa_modules/ksf_FA_EmailManager` is byte-identical to the dev tree for all code (`diff -rq` differs only in `APP_TAB_ARCHITECTURE.md`, `MODULE_DIRECTORY.md`, `PACKAGIST.md` — documentation).

### Status on the live instance

Active in **both** registries — global `installed_extensions.php` (`'active' => true`, version `2.4.3-0`) and `company/0/installed_extensions.php` (`'active' => 1`). `_init/config` is gzip `Key: Value` with `Version: 2.4.3-0`, satisfying FA's `check_src_ext_version()` gate (unlike the `'-'` that would block activation).

### Purpose — docs vs. code

The ProjectDcs describe the **opposite** module: *"Email campaign management for FrontAccounting — templates, automation, and tracking with CRM integration. This module handles **outbound email delivery** with GPG signing."* (`ProjectDcs/Functional Requirements.md:11`). FR-001…FR-004 cover templates, campaigns, **email logging of sent mail**, and **outbound attachments**. There is no requirement anywhere in this repo's docs for IMAP fetching, inbound parsing, or an inbox.

**The implemented code, by contrast, is almost entirely inbound.** The docs and the code describe different products.

### Actual code

**`hooks.php`** — `hooks_ksf_FA_EmailManager extends hooks`, `use \Ksfraser\Traits\HookQueryProviderTrait` (line 37), SS section `122 << 8` (line 29), two security areas `SA_ksf_FA_EmailManagerVIEW` (`SS|1`) and `SA_ksf_FA_EmailManagerMANAGE` (`SS|2`). `install_tabs()` is **empty**. `install_options()` adds 4 CRM-app menu items. `activate_extension()` runs 5 per-table SQL files via `update_databases()`, then `retire_misnamed_tables()`. `_getAdvertisedValues()` advertises `emailmanager.version` / `.module_name` / `.hooks_version`. `ensure_composer_dependencies()` shells out to `composer install` at activation time (line 215) — a fragile pattern to execute inside a web request.

**`includes/em_db.inc`** (313 lines) — 22 procedural functions over `0_ksf_em_*` using native `db_query`/`db_escape`/`db_fetch_assoc`/`db_num_rows`/`db_insert_id`. This respects the AGENTS_ARCH hard rule (FA modules use native `db_*`, never PDO). Notable:
- `em_dispatch_event()` (line 10) tries a `Ksfraser\Event\EventManager` that isn't installed (line 7 `@include_once` is suppressed), then falls back to `add_hook()`.
- `find_debtor_by_email()` (line 241) — `SELECT debtor_no FROM {TB_PREF}debtors_master WHERE email = …`.
- `find_contact_by_email()` (line 250) — **joins `crm_contacts` to `crm_persons`**, with a correct comment explaining why: *"`crm_contacts` is a person→entity xref (id, person_id, type, action, entity_id) and carries no email column. The address lives on `crm_persons`."* This is the single most FA-correct piece of logic in the module.
- `route_email()` (line 275) — reads `0_ksf_em_routes` ordered by `priority DESC`, substring-matches the To address, then comma-split keywords in subject/body.
- **Passwords are stored and read in plaintext** (`em_db.inc:37`, `:76`; column `password VARCHAR(255)`).

**`includes/em_routing.inc`** (190 lines) — 5 functions:
- `process_inbound_email()` — resolves the From address to debtor/contact, writes those onto the row, applies `route_email()`, writes `routing_action`, creates a linked entity, sets `is_processed = 1`.
- `em_create_ticket_from_email()` — INSERT into `{TB_PREF}fa_st_tickets`. **Table does not exist on this install.**
- `em_create_opportunity_from_email()` — INSERT into `{TB_PREF}crm_opportunities`. **Table does not exist.** Errors are `@`-suppressed; returns 0.
- **`sync_email_account($account_id)` (lines 107-189) — the real inbound engine.** Guards `imap_open` existence (line 112), builds `{host:port/imap/enc}`, `imap_headers()` → `imap_headerinfo()` → **dedupes on `message_id` via SELECT** (lines 142-145) → `imap_fetchstructure()` → walks `$structure->parts` picking `text/HTML` and `text/*` → assembles the array → `save_inbound_email()` → updates `last_sync`.

**`pages/`** — 4 pages, all broken (see §2). Beyond the `$path_to_root` fault: `accounts.php` is a reasonably complete CRUD form; `inbox.php` has a sync form, a "Process All Pending" form, and a 5-way filter (all/unprocessed/processed/tickets/opportunities); `mailing_lists.php` is CRUD over subscribers-by-count; `campaigns.php` is the weakest — three form actions against tables that do not exist.

**`src/Ksfraser/FrontAccounting/`** — **empty directories.** `composer.json` maps PSR-4 `Ksfraser\` → `src/Ksfraser/`, so the module autoloads nothing of its own. All logic is in `.inc` files and `hooks.php`.

**`vendor-src/Ksfraser/Common/ComposerDependencyManager.php`** — a single orphaned file with no `composer.json` autoload reference to it. Dead.

### Answering the critical questions

**Q2 — Inbound IMAP fetching/parsing: YES, implemented.** `includes/em_routing.inc:107-189` is a genuine working IMAP importer: connect, enumerate, dedupe by `message_id`, walk MIME parts for text/HTML, persist. It is far more complete than anything in `ksf_EmailManager`. **Limitations:** (a) the container has no IMAP extension, so it can never run there; (b) it reads only `$header->to[0]` and `$header->from[0]` — **Cc/Bcc are never captured**, despite the columns existing; (c) `raw_headers` is **never populated** (the column and the DTO property exist, nothing writes them); (d) it iterates **all** headers with no UID/bookmark persistence, so every sync re-walks the whole mailbox and depends entirely on the `message_id` SELECT to avoid duplicates — a full table scan per message; (e) it never deletes or flags messages server-side, so mail is never removed from the mailbox.

**Q3 — Content vs. pointer: CONTENT is persisted.** This is the good news for the stated requirement. `save_inbound_email()` (`em_db.inc:105-136`) INSERTs `body_text`, `body_html`, `raw_headers`, `attachments`, `subject`, `from_address`, `from_name`, `to_address`, `cc_addresses`, `bcc_addresses`, `received_date`. Verified against the live table:

```
0_ksf_em_inbound_emails:
  message_id varchar(255) | subject varchar(255) | from_address varchar(255)
  from_name  varchar(255) | to_address  varchar(255) | cc_addresses text
  bcc_addresses text | body_text text | body_html text | attachments text
  received_date datetime | raw_headers text | routing_action varchar(20)
  linked_entity_id int | linked_entity_type varchar(20) | debtor_no int
  contact_id int | account_id int | is_processed tinyint(1)
  created_at timestamp | updated_at timestamp
```

Body text and body HTML are stored verbatim as fetched. **Deleting mail server-side would not lose the record** — the row is a full copy. Two caveats: bodies are `TEXT` (64 KB) not `LONGTEXT`, so a long HTML body with quoted history can be truncated or rejected; and attachments are never stored, so an attachment-only email persists with no trace of its file.

**Q4 — Attachments: NOT handled.** The `attachments TEXT` column exists and `InboundEmail::$attachments` exists, but nothing in either repo ever writes to either. `imap_fetchstructure()` is called in both IMAP implementations and, in `ksf_EmailManager`, its result is assigned to `$structure` and **never read** (`EmailFetchService.php:91`). Neither code path calls `imap_fetchbody(..., '1.N')` for non-text parts. FR-EM-004 / FR-004 in the docs claim attachment support; there is none.

**Q5 — Recipient→contact resolution: YES, in the FA module.** `em_find_customer_match()` (`em_db.inc:264`) calls `find_debtor_by_email()` (debtors_master) and `find_contact_by_email()` (crm_contacts ⋈ crm_persons). Wired into `process_inbound_email()` (`em_routing.inc:14-25`), which writes `debtor_no` and `contact_id` onto the inbound row. Limitations: matches on the **From** address only; single hit (`LIMIT 1`); no `FROM`-name or `+tag` handling; no threading. Neither `ksf_EmailManager` nor `ksf_EmailManager_UI` has any equivalent.

**Q6 — Tables used.** Five tables are created and used: `0_ksf_em_accounts`, `0_ksf_em_inbound_emails`, `0_ksf_em_mailing_lists`, `0_ksf_em_subscribers`, `0_ksf_em_routes`. All five confirmed present on the live DB (`0_ksf_em_accounts` has 1 row; the rest are empty). Referenced but **never created**: `0_ksf_em_campaign_lists`, `0_ksf_em_campaign_links` (`pages/campaigns.php`), `0_crm_campaigns` (`pages/campaigns.php:68`), `0_fa_st_tickets`, `0_crm_opportunities` (`includes/em_routing.inc`). Outside the `0_ksf_em_*` namespace the code reads `debtors_master`, `crm_contacts`, `crm_persons`.

**Yes — mailing_lists/subscribers are still used, and they are outbound concerns.** `0_ksf_em_mailing_lists` and `0_ksf_em_subscribers` have a full CRUD surface in `em_db.inc` (`add_mailing_list`, `get_mailing_list`, `add_subscriber`, `get_subscribers`, `confirm_subscriber`, `unsubscribe_by_token`) and `pages/mailing_lists.php` renders them with subscriber counts. They are **pure outbound-marketing apparatus** — double opt-in tokens, unsubscribe tokens, `status` transitions, subscriber counts — and contribute nothing to an inbound email client. `pages/campaigns.php` exists solely to link mailing lists to campaigns and fan mail out to subscribers. Under the user's decided inbound-only role, **all three of `mailing_lists.php`, `campaigns.php`, and the two tables are dead weight that should move to whatever module owns campaigns** (per this repo's own docs, `ksf_CampaignBuilder` is the natural home).

**Q8 — `sql/install.sql`: NO, it is not shipped, and this is a live regression.** `git log --all -- sql/install.sql` shows:

- `79ed23f` *"fix(schema): real install.sql, FA-native security areas, page wiring (#25)"* — **added** it.
- `a9bf721` *"refactor(schema): per-table sql/ files and 0_ksf_em_ table prefix"* — **deleted it** (`sql/install.sql | 109 -----------`, the only deletion in that commit).

The five tables exist on the live DB only because they were created while `install.sql` was still present (or were created manually during the `0_fa_em_*` → `0_ksf_em_*` cutover documented in `sql/upgrade_2.4.3-1.sql`). **A fresh activation on a clean database will create nothing**, because `activate_extension()` gates `update_databases()` on per-file table presence, and FA's own install engine only recognises `sql/install.sql`. `hooks.php`'s own header comment (line 18) still says *"Use sql/install.sql with literal 0_ table prefixes"* — the file contradicts the instruction directly above it.

### ProjectDcs (BABOK)

`Functional Requirements.md` (154 lines) and `EVENTS.md` (483 lines) have real content. The other five — `Architecture.md`, `Business Requirements.md`, `RTM.md`, `Test Plan.md`, `UAT Plan.md`, `Use Case.md` — are **4-line stubs** (`# Architecture.md` and nothing else). No individual `BR-`/`FR-`/`UT-` files as `AGENTS.md` requires. **Directionally wrong** for the intended inbound role (see Purpose above).

---

## 6. Cross-Cutting Findings

### What is real vs. aspirational

| Claim | Source | Reality |
|---|---|---|
| IMAP import | both `composer.json`/docs | **Real** (FA module only; blocked by missing PHP IMAP ext on this container) |
| Inbound message parsing | docs | **Partial** — no MIME walker beyond `structure->parts`, no Cc/Bcc, no raw headers, no UID |
| Routing | docs | **Real** in the FA module (`0_ksf_em_routes`); **in-memory only** in `ksf_EmailManager` |
| Contact resolution | FR-EM-003 | **Real** in the FA module (`debtors_master`, `crm_contacts`⋈`crm_persons`) |
| Outbound SMTP / campaigns / templates / open-click tracking | FR-EM-001/004/005, Architecture "Implemented" | **Nonexistent.** No SMTP, no send, no template store, no tracking table |
| Attachments | FR-004 | **Nonexistent** — column and field only |
| RBAC (FR-EM-007/008/009) | FR-EM-007..009 | **Nonexistent.** No `0_rbac_*` reference anywhere in the module |
| Support ticket integration | FR-EM-006 | Written, target table `fa_st_tickets` absent |
| UI | all three repos | **4 pages, all HTTP 500**; UI repo is an empty scaffold |

### Inbound email: the honest answer

Inbound is **one working function in one repo** — `sync_email_account()` in `ksf_FA_EmailManager/includes/em_routing.inc` — plus the `0_ksf_em_inbound_emails` schema it writes into, which is correctly designed for the user's "deleting mail server-side must not lose the record" requirement. Everything else that touches inbound is either a duplicate of it (`EmailFetchService` in `ksf_EmailManager`) or absent.

`ksf_EmailManager`'s `EmailFetchService` is the **older and weaker** implementation and is **not wired into the FA module at all**. The FA module has its own IMAP code in a `.inc` file and shares no code with it. Two IMAP implementations, zero reuse. Given the AGENTS_ARCH direction (DI-able `DbConnectionInterface` + transport adapters), `EmailFetchService`'s use of **raw global `imap_*` functions with no interface and no injectable transport** is the opposite of the house pattern.

### Recommended shape for the inbound-only role

1. **Fix the four pages first** — `$path_to_root = "../../.."` in all four (§2). Nothing else can be evaluated until a page renders.
2. **Delete or move the outbound half.** `mailing_lists.php`, `campaigns.php`, `0_ksf_em_mailing_lists`, `0_ksf_em_subscribers` are outbound marketing apparatus. Move them to `ksf_CampaignBuilder` (or drop them) and re-point the CRM menu.
3. **Restore `sql/install.sql`** (or re-aggregate the five per-table files into it) so a clean activation provisions the schema.
4. **Move inbound into the standalone package and give it an interface.** Extract `sync_email_account()`'s logic into `ksf_EmailManager` behind an `ImapTransportInterface` (connect / listHeaders / fetchStructure / fetchBody / close) so the FA module DI's an implementation and the package tests against a fake. Delete the duplicate raw-imap code rather than maintaining two.
5. **Capture the fields the schema already has room for**: Cc, Bcc, `raw_headers`. Replace the per-message `SELECT … WHERE message_id =` with a unique index on `message_id` (currently only a non-unique `KEY idx_message_id`) plus a last-seen UID, so sync is not O(mailbox size) each run.
6. **Decide attachments explicitly** — either implement `imap_fetchbody(…, '1.N')` + store in `ksf_FA_Attachments` with a link column, or drop the column so it stops implying support.
7. **Encrypt the account password.** `0_ksf_em_accounts.password` is plaintext (`em_db.inc:37`).
8. **Raise `body_text`/`body_html` to `LONGTEXT`** to match what an HTML email with quoted history actually weighs.

### Explicit uncertainties

- I did not confirm **whether the five tables on the live DB were created by an earlier `install.sql`, by `update_databases()` during a prior activation, or manually**. `SHOW TABLES` shows they exist; the mechanism is not recorded in the repo.
- I did not verify the **rootless `ksf-fa` container (port 8080)**, only `ksfii_app-fa` (8090). Per `AGENTS.md` the `fa_modules` bind is not effective on the rootful pod, so the container's copy may have been updated by some path other than the repo. The code in the container was byte-identical to `ksf_Infrastructure/fa_modules/ksf_FA_EmailManager` at the time of inspection.
- **No IMAP server was available**, so `sync_email_account()` was verified by code reading only, never executed end-to-end. Its correctness on real multipart mail is therefore unproven — in particular the `structure->parts` walk assumes a shallow (one-level) multipart structure and will not recurse into nested multiparts.
- I could not determine **why the module was marked active given `install_tabs()` is empty** beyond the registry state; the CRM menu (`install_options`, case `'CRM'`) is the working entry path and I did not log in to confirm the menu renders.
- I did not check whether `ksfraser/exceptions` actually provides the `Ksfraser\Event\Event` / `Ksfraser\Core\BaseEntity` classes the code expects; I verified only that they are **not declared in the repo or its own vendor tree**, which is sufficient to call those classes broken.
- **Branch `main` of `ksf_EmailManager_UI` shows `[gone]`** against origin — the remote default branch name has changed or the branch was deleted upstream. I did not fetch to resolve which.