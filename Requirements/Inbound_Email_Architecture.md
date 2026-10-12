# Inbound Email — Target Architecture

**Module:** `ksf_FA_EmailManager` (code `EM`)
**Role (decided):** **inbound only** — an email client like Roundcube. Parse messages,
persist them, present them, route them.
**Date:** 2026-10-11
**Status:** Proposed — not built.

**Companion requirements:**
[BR-EM-001](./BR-EM-001-inbound-email-capture.md) ·
[FR-EM-001-01](./FR-EM-001-01-message-persistence.md) ·
[FR-EM-001-02](./FR-EM-001-02-attachment-persistence.md) ·
[FR-EM-001-03](./FR-EM-001-03-addressee-resolution.md) ·
[FR-EM-001-04](./FR-EM-001-04-future-actions.md) ·
[UC-EM-001](./UC-EM-001-support-request.md)

---

## 1. Verification basis

Every claim below was checked on **2026-10-11** against the live integration stack
(`ksfii_app-mariadb` / DB `ksf_fa`, container `ksfii_app-fa`, PHP 7.4.33) and the
`FA/2.4.3` source tree. Anything not checked is marked **[UNVERIFIED]** and
consolidated in §9. Open decisions are consolidated in §10.

---

## 2. Current state, condensed

`ksf_FA_EmailManager` owns five tables. All five exist on the live DB.

| Table | Rows | Verdict |
|---|---|---|
| `0_ksf_em_accounts` | 1 | **KEEP** — mailbox of record |
| `0_ksf_em_inbound_emails` | 0 | **KEEP + EXTEND** — the message; already stores both bodies |
| `0_ksf_em_routes` | 0 | **KEEP** — inbound routing by To-address/keyword |
| `0_ksf_em_mailing_lists` | 0 | **MOVE OUT** — outbound |
| `0_ksf_em_subscribers` | 0 | **MOVE OUT** — outbound |

**The one genuinely good thing:** `save_inbound_email()` (`em_db.inc:105-136`) already
persists `body_text` and `body_html`. Server-side mail deletion does **not** lose the
record. This is the requirement the user cares about most, and it is already partly
satisfied.

**Plus two dormant second implementations**, both broken:

| Location | Problem |
|---|---|
| `ksf_EmailManager/src/.../EmailFetchService.php` | Raw `imap_*`, no interface, no persistence, not referenced by the FA module. Two IMAP implementations, zero reuse. |
| `ksf_FA_CRM/includes/EmailImportService.php` | **The SuiteCRM anti-pattern.** Verified: referenced by nothing; queries `0_fa_crm_contacts` and `0_fa_crm_communications`, **neither of which exists** (created names are `0_ksf_crm_*`); calls `update_email_sync_time()`, **defined nowhere**. Contains the only correct recursive MIME walk and ICS parser in the tree — salvage, then delete. |

---

## 3. Target data model

### 3.1 Relationship diagram

```
                     ┌──────────────────────────────┐
                     │ 0_ksf_em_accounts           │  mailbox of record
                     │  id, email_address,          │  (the SUPPORT address)
                     │  debtor_no, contact_id       │
                     └───────────┬──────────────────┘
                                 │ 1
                                 │
                    ┌────────────▼───────────────────┐
              N     │ 0_ksf_em_inbound_emails        │  THE ANCHOR
                    │  id ── THE MESSAGE            │
                    │  message_id, subject,          │
                    │  from/to/subject,              │
                    │  body_text, body_html (LONGTEXT)│
                    │  raw_headers (MEDIUMTEXT),     │
                    │  raw_source (LONGTEXT),        │
                    │  uid, uidvalidity,             │
                    │  content_hash,                 │
                    │  in_reply_to, thread_id,       │
                    │  debtor_no  ──────────────┐    │  business context
                    │  is_processed             │    │
                    └──────┬──────────────┬────┘────┘
                           │ 1            │ 1
                           │              │
          ┌────────────────▼─────┐   ┌───▼──────────────────────────┐
     N    │ 0_ksf_em_addressees  │   │ 0_ksf_em_artefacts           │  N
          │  email_id, role,     │   │  email_id  ◄── THE ANCHOR    │
          │  address,            │   │  artefact_type (VARCHAR!)    │
          │  address_normalized, │   │  owner_module,               │
          │  person_id ──────┐   │   │  artefact_ref, artefact_id,  │
          │  contact_id    │   │   │  status,                     │
          │  debtor_no ────┼───┼───┤  created_by,  ◄── PROVENANCE  │
          │  match_method, │   │   │  payload JSON                │
          │  confidence,   │   │   └──────────────────────────────┘
          │  candidates,   │   │
          │  is_resolved   │   │
          └────────────────┼───┘
                           │ N:M
        ┌──────────────────▼──────────────┐
        │ 0_crm_persons   (FA CORE)       │  the PERSON
        │  id, ref, name,                 │  ◄── email lives HERE
        │  email (100), inactive          │
        │  [NO INDEX on email — verified] │
        └──────────────────┬──────────────┘
                           │ person_id
        ┌──────────────────▼──────────────┐      ┌──────────────────────┐
        │ 0_crm_contacts  (FA CORE)       │─────►│ 0_debtors_master     │
        │  id, person_id,                 │ type │  debtor_no, name,    │
        │  type='customer',               │='cus'│  debtor_ref, ...     │
        │  action='general',              │      │  [NO email column —  │
        │  entity_id = debtor_no ◄────────┘      │   verified!]         │
        └─────────────────────────────────┘      └──────────────────────┘

        ATTACHMENTS — FA NATIVE, no module table
        ┌────────────────────────┐    ┌──────────────────────────┐
        │ 0_attachments (CORE)   │◄──►│ 0_fa_attachments         │
        │  id, type_no=300,      │ ref│  source_type='email',    │
        │  trans_no=<email_id>,  │    │  kind='message',         │
        │  unique_name, filename │    │  source_id=<email_id>,   │
        └───────────┬────────────┘    │  filename (255, full)    │
                    │                 └──────────────────────────┘
          company/<id>/attachments/<random_id()>
```

### 3.2 Why the addressees must be their own table

The requirement is *"every other recipient (including CC and BCC) as contacts"*. That
is a **one-to-many** relationship with a resolution outcome per recipient.

The current columns cannot express it:

- `to_address VARCHAR(255)` holds only `to[0]` — verified at `em_routing.inc:173`.
- `cc_addresses TEXT` / `bcc_addresses TEXT` are free text — unindexable, unjoinable,
  and cannot carry a per-recipient `person_id`.

Packing recipients into text would make requirement 4 unimplementable without string
matching. Hence `0_ksf_em_addressees`.

### 3.3 Why the artefacts table must exist

`linked_entity_id INT` + `linked_entity_type VARCHAR(20)` is a **single** slot for a
**single** artefact of a **single** shape, and both targets it points at are absent
from the live DB (`fa_st_tickets`, `crm_opportunities` — verified). Requirement 5 needs
an *open* extension point; a fixed pair of columns is the opposite of open.

`artefact_type` is deliberately `VARCHAR(32)`, **not** `ENUM`: an ENUM makes a new
artefact kind a schema migration **plus** an EmailManager code change. That is exactly
the coupling BR-EM-001 forbids.

### 3.4 Table-by-table change list

**`0_ksf_em_inbound_emails`** — modify:

| Change | From | To | Closes |
|---|---|---|---|
| `body_text` | `TEXT` | `LONGTEXT` | 64 KB overflow on quoted HTML |
| `body_html` | `TEXT` | `LONGTEXT` | same |
| `raw_headers` | `TEXT` | `MEDIUMTEXT` | never written today |
| `message_id` | `KEY` | **`UNIQUE KEY`** | non-unique today |
| *(new)* | | `uid INT`, `uidvalidity BIGINT`, `content_hash CHAR(64)` | no IMAP cursor |
| *(new)* | | `in_reply_to`, `thread_id` | no threading |
| *(new)* | | `raw_source LONGTEXT` | parse errors unrecoverable |
| *(new)* | | `synced_at DATETIME` | |
| `attachments` | `TEXT` | *cached manifest only* | |
| `to_address` | `VARCHAR(255)` | *superseded by addressees* | |
| `linked_entity_*`, `routing_action` | | *deprecated; see Q14* | single-artefact slot |

**`0_ksf_em_addressees`** — new. DDL in
[FR-EM-001-03 §4](./FR-EM-001-03-addressee-resolution.md#4-the-addressee-table).

**`0_ksf_em_artefacts`** — new. DDL in
[FR-EM-001-04 §3.1](./FR-EM-001-04-future-actions.md#fr-em-001-04-1--a-generic-open-artefact-registry).

**No changes to FA core tables are required** — with one exception flagged for
approval: an index on `0_crm_persons(email)`, which core does not define (verified).

### 3.5 Attachment reuse — reuse FA native

**Decision: reuse `0_attachments` + `company/<id>/attachments/`, plus the
`0_fa_attachments` link row. No module-owned attachments table.**

Justified in full at
[FR-EM-001-02 §2](./FR-EM-001-02-attachment-persistence.md#2-decision-reuse-frontaccountings-native-attachment-mechanism).
Summary of the decisive points:

1. An **org decision already exists**: `BR-AT-001-attachments-extend-native-fa.md`
   requires attachment capability be added to FA's system, *"not a competitor to it"*,
   because a parallel store makes "the file is missing" unanswerable.
2. The mechanism is **already built and tested** by `ksf_FA_Attachments`
   (`FaNativeTable`, `NativeAttachmentBridge`, `DbAttachmentStore`).
3. Backup and retention come free — the files live inside the company folder.
4. FA's own download endpoint and auth already serve them.

**Required work:** allocate **`type_no` range 300–319** to EmailManager in
`AttachmentKindRegistry` (`email.message = 300`), because `0_attachments` keys on
`(type_no, trans_no)` alone and 200–299 are already allocated (verified:
Calendar 200–203, CRM 220–227, PM 240–247, HRM 260–265, Stock 280–282).

**Three verified constraints** that a naive implementation would trip on:

| # | Constraint | Mitigation |
|---|---|---|
| L1 | `0_attachments.filename` / `unique_name` are **`VARCHAR(60)`** | store the full name in `0_fa_attachments.filename` (`VARCHAR 255`); truncate in the native row. **See Q4.** |
| L2 | `company/0/attachments/` **does not exist** — FA creates it lazily *in its web page* | inbound sync must create the directory **and** the `index.php` guard itself |
| L3 | `transaction_exists()` is called by the page, **not** by `add_attachment()` | call `add_attachment()` directly — this is what makes programmatic use possible |

---

## 4. Inbound processing flow

```
 ┌── 1. TRIGGER ────────────────────────────────────────────────┐
 │  Cron / UI "Sync" / webhook. NOT a web page — so none of FA's  │
 │  page-level setup (dir creation, transaction_exists) applies. │
 └──────────────────────────────┬────────────────────────────────┘
                                ▼
 ┌── 2. CONNECT ────────────────────────────────────────────────┐
 │  Guard function_exists('imap_open')  [BLOCKER B1 — see §8]    │
 │  imap_open({host:port/imap/enc})                            │
 │  uidvalidity := imap_get_mailbox_info()                      │
 └──────────────────────────────┬────────────────────────────────┘
                                ▼
 ┌── 3. CURSOR ─────────────────────────────────────────────────┐
 │  stored.uidvalidity == uidvalidity ?                         │
 │    YES -> search('UID '.(cursor+1).':*')   incremental       │
 │    NO  -> cursor invalid. Reset, re-walk from UID 1.         │
 │           Dedupe still prevents duplicate CONTENT.           │
 │  if 0 results -> update last_sync, done.                    │
 └──────────────────────────────┬────────────────────────────────┘
                                ▼
 ┌── 4. PER MESSAGE ────────────────────────────────────────────┐
 │  a. dedupe: (account_id,message_id) -> else content_hash     │
 │     hit  -> update uid/uidvalidity/synced_at; SKIP body fetch│
 │  b. imap_fetchbody(full RFC822) -> raw_source + content_hash │
 │  c. recursive MIME walk (nested multiparts)                  │
 │       text/plain -> decode -> body_text                      │
 │       text/html  -> decode -> body_html                      │
 │       others     -> attachment (FR-EM-001-02)                │
 │  d. headers -> from/to/cc/bcc/reply_to/return_path,          │
 │               in_reply_to, thread_id, raw_headers            │
 │  e. INSERT 0_ksf_em_inbound_emails   [LONGTEXT bodies]       │
 │  f. write attachments -> 0_attachments + 0_fa_attachments    │
 │     (create company/<id>/attachments/ + index.php if absent) │
 │  g. INSERT 0_ksf_em_addressees, one row per addressee        │
 │  h. UPDATE debtor_no / contact_id on the email row           │
 │  i. hook_invoke_all('email_received')   ◄── AFTER resolution │
 │  j. on exception: LOG + CONTINUE; do NOT advance synced_at   │
 └──────────────────────────────┬────────────────────────────────┘
                                ▼
 ┌── 5. ROUTE ──────────────────────────────────────────────────┐
 │  0_ksf_em_routes: To-address match + optional keyword.       │
 │  Writes routing_action. Ticket/opportunity creation is now   │
 │  OUT of EmailManager — a consumer registers an artefact row  │
 │  instead (FR-EM-001-04).                                    │
 └──────────────────────────────────────────────────────────────┘
```

**Design points:**

- **Step 4a is the cost control.** The current code does a `SELECT ... WHERE
  message_id =` for every header on every run — O(mailbox). The cursor makes it
  O(new mail), and the cheap existence check avoids the body fetch for repeats.
- **Step 4i ordering is a correctness fix.** `em_dispatch_event('email_received')`
  currently fires from inside the INSERT (`em_db.inc:133`) while `debtor_no` and
  `contact_id` are still NULL, so a subscriber has nothing to act on.
- **Step 4j** keeps one bad message from blocking the rest and from being skipped
  forever.

### 4.1 Addressee resolution in one line

```
person_id <- 0_crm_persons.email (normalised)
debtor_no <- 0_crm_contacts.entity_id WHERE person_id=? AND type='customer'
```

**This inversion is mandatory.** See §5.1.

---

## 5. The four verified defects this design must not carry forward

### 5.1 `debtors_master.email` does not exist — debtor lookup by email is broken

`em_db.inc:241-248` runs
`SELECT debtor_no FROM 0_debtors_master WHERE email = ...`.

**Verified on the live DB:** `SHOW COLUMNS FROM 0_debtors_master` returns 16 columns
and **none is `email`**; the query returns
`ERROR 1054 (42S22): Unknown column 'email' in 'WHERE'`.
**Verified no module adds it** — grepped every `FA/2.4.3/sql/alter*.sql` and every
`fa_modules/*/sql/*.sql`.

So `em_find_customer_match()` errors, and `process_inbound_email()` **cannot complete
on a stock install**. The debtor must be derived **through** the contact
(`crm_contacts.type='customer'` → `entity_id`), which is FA's own definition
(`sales/manage/customers.php:126`) and needs no schema change.

`EmailManager_Analysis.md` rates contact resolution "**Yes, in the FA module**". That
is correct for `find_contact_by_email()` (which properly joins `crm_contacts ⋈
crm_persons`) but **wrong for the debtor half**.

### 5.2 Two contact stores exist — needs a decision

| | FA core `crm_persons`+`crm_contacts` | `0_ksf_crm_contacts` (ksf_FA_CRM) |
|---|---|---|
| Live rows | **1 person, 2 contacts** | **0 rows** |
| Debtor link | indirect via `type='customer'` | **direct `debtor_no` column** |
| Email index | **none** | none |
| Used by FA core UI | **yes** | no |
| Existing inbound code | `find_contact_by_email()` (correct) | `EmailImportService` (queries a non-existent table) |

**Recommendation: FA core** — it is FA's model, holds the only real data, is
extensible via `crm_categories`, and the alternative's inbound code is broken anyway.
But it needs the core-table index approval. **This is Q13, and it is the single most
consequential open decision in this document.**

### 5.3 `em_dispatch_event()` falls back to a function that does not exist

`em_db.inc:10-22` probes an uninstalled `Ksfraser\Event\EventManager`, then falls back
to `add_hook()`. **Verified: FA core defines no function `add_hook`** — FA dispatches
via `hook_invoke_all()` in `includes/hooks.inc`. The fallback is dead code that would
fatal if reached.

### 5.4 `find_contact_by_email()` is non-deterministic on multiple matches

`LIMIT 1` with no `ORDER BY`, and no filter on `crm_contacts.type` — so it can return
a **supplier** or **branch** contact. On a shared address it picks arbitrarily. FR-EM-001-03
requires explicit ambiguity handling.

---

## 6. What must MOVE OUT of EmailManager

By the decided architecture: CampaignBuilder = outbound journey automation; the new
**MailingList** module = subscribers + open/click/read tracking; EmailManager =
**inbound only**.

| Item | Type | Destination | Notes |
|---|---|---|---|
| `0_ksf_em_mailing_lists` | table | **MailingList** | outbound: `from_address`, `reply_to`, `subscription_type` |
| `0_ksf_em_subscribers` | table | **MailingList** | outbound: `subscribe_token`, `unsubscribe_token`, `status`, double opt-in |
| `pages/mailing_lists.php` | page | **MailingList** | |
| `pages/campaigns.php` | page | **CampaignBuilder** | **not** MailingList — see below |
| `add_mailing_list()` | function | **MailingList** | `em_db.inc:165` |
| `get_mailing_list()` | function | **MailingList** | `em_db.inc:181` |
| `add_subscriber()` | function | **MailingList** | `em_db.inc:188` |
| `get_subscribers()` | function | **MailingList** | `em_db.inc:216` |
| `confirm_subscriber()` | function | **MailingList** | `em_db.inc:227` |
| `unsubscribe_by_token()` | function | **MailingList** | `em_db.inc:234` |
| CRM menu entry 2 "Mailing Lists" | menu | **MailingList** | `hooks.php:67-68` |
| CRM menu entry 3 "Email Campaigns" | menu | **CampaignBuilder** | `hooks.php:69-70` |

**`pages/campaigns.php` is separate from the others.** It is not subscriber
management — it links lists to campaigns and fans mail out, which is CampaignBuilder's
job. It is also the **worst page in the module**: it queries three tables that do not
exist (`0_ksf_em_campaign_lists` `:24,34,43`, `0_ksf_em_campaign_links` `:100`,
`0_crm_campaigns` `:68`). Verified absent from the live DB. It should move to
CampaignBuilder or be deleted outright.

### 6.1 `0_ksf_em_subscribers` already carries `debtor_no` and `contact_id`

Verified in `sql/ksf_em_subscribers.sql`. This is a **significant** finding for the
move-out plan: subscriber resolution needs the *same* match-or-create resolver as
inbound addressees.

**Recommendation:** put the resolver in the standalone `ksf_EmailManager` package
behind an interface, consumed by both the FA module and the future MailingList module
— otherwise the org grows a second, divergent copy of the contact-matching logic.
This also matches the house pattern of DI-able adapters.

### 6.2 What EmailManager KEEPS

`0_ksf_em_accounts` · `0_ksf_em_inbound_emails` · `0_ksf_em_routes` ·
`pages/accounts.php` · `pages/inbox.php` · CRM menu entries 0 and 1.
Plus the new `0_ksf_em_addressees` and `0_ksf_em_artefacts`.

---

## 7. Security

| Issue | Status | Action |
|---|---|---|
| `0_ksf_em_accounts.password` stored **plaintext** | verified (`em_db.inc:37,76`; column `VARCHAR(255)`) | encrypt — compare the existing GPG/key-management apparatus |
| IMAP extension absent from the container | verified, `php -m \| grep -ci imap` = 0 | rebuild image with `imap` (+ `mbstring`) |
| Attachment path traversal | not currently possible (no extraction exists) | generated `random_id()` names only; sanitise the display name |
| Inbound attachment malware | no scanning found anywhere | **Q5** — allowlist + AV hook, or record as accepted risk |
| Attachment download auth | inherits FA's `admin/attachments.php` | verify it applies to `type_no = 300` |
| HTML body rendering (XSS) | not currently rendered | sanitise before display in any viewer |
| `crm_persons.email` is `VARCHAR(100)` | verified | truncate, keep the full value in the addressees table |
| Mailbox password logging | not verified | confirm no credentials reach `error_log()` |

---

## 8. Blockers and prerequisite work

| # | Item | Verified | Impact |
|---|---|---|---|
| **B1** | **No IMAP PHP extension** on `ksfii_app-fa` (PHP 7.4.33) | yes | **Every inbound path is dead.** No IMAP code here has ever executed. Rebuild the image with `imap` + `mbstring` before anything else. |
| **B2** | `find_debtor_by_email()` queries a non-existent column | yes | `process_inbound_email()` cannot complete — §5.1 |
| **B3** | `EmailImportService` is dead and broken | yes | Retire it, but **salvage** its MIME/ICS code first — §6 of FR-EM-001-04 |
| **B4** | `sql/install.sql` absent (deleted in `a9bf721`) | file absent | **[UNVERIFIED]** whether `update_databases()` per-file gating (`hooks.php:108-115`) provisions a clean install. **Test on a fresh company before building.** |
| **B5** | No support/ticket table or module exists | yes | Requirement 5's ticket artefact has no home — **Q3** |
| **B6** | `company/0/attachments/` does not exist | yes | Must be created by sync, not just by FA's page — L2 |

---

## 9. Unverified — could not confirm from the code

| # | Item | Why it matters |
|---|---|---|
| U1 | Whether `update_databases()` provisions schema on a **clean** database | If it does not, none of this installs on a new company |
| U2 | Whether `0_attachments.filename` truncates silently or raises, given the server's `sql_mode` | Decides whether the L1 mitigation is safe |
| U3 | Whether Bcc is obtainable on the **production** MTA | Bcc completeness is environment-dependent (FR-EM-001-01 C1) |
| U4 | Whether an antivirus facility exists to integrate with | Inbound attachments are the classic mail-ware vector |
| U5 | Whether a **production** FA install added `debtors_master.email` by hand | Would change §5.1's remediation |
| U6 | Whether `0_ksf_crm_contacts` is populated in UAT/prod | Feeds Q13 |
| U7 | Whether a support-ticket module exists outside `ksf_Infrastructure/fa_modules/` | Feeds Q3 |
| U8 | The live server's `sql_mode` and JSON support | Inferred from `0_fa_attachments`' DDL, not inspected |
| U9 | Whether the **rootless** `ksf-fa` container (port 8080) has the IMAP extension | Only `ksfii_app-fa` (8090) was probed |

---

## 10. Open decisions — for the user

### Blocking — need an answer before design can complete

| # | Question | Recommendation |
|---|---|---|
| **Q3** | **Which module owns the support-ticket artefact?** `0_fa_st_tickets` does not exist; no ticket module was found. (a) new `ksf_FA_Tickets`, (b) `ksf_FA_CRM` opportunity/case, (c) a minimal table inside EmailManager. | **(a)** — requirement 5 explicitly names tickets, and EmailManager is inbound-only, so it should not own ticket lifecycle |
| **Q13** | **Which contact store is authoritative** — FA core `crm_persons`/`crm_contacts` (real data, FA-native, needs a core-table index) or `0_ksf_crm_contacts` (direct `debtor_no`, empty)? | **FA core** — it is FA's model, holds the data, is extensible, and CRM's inbound code against the alternative is broken |
| **Q2** | Should an unknown sender ever be auto-created as a **debtor/customer**, or only as an unlinked person? | **Unlinked person only** — creating a financial record from an inbound email is a credit decision |
| **Q1** | Should the mail server be **cleared after capture** (copy-then-delete, or flag/label)? | **Flag/label, do not delete** — proves capture without risking loss, and is reversible |

### Important — shape the data model

| # | Question | Recommendation |
|---|---|---|
| **Q7** | Retain the full raw RFC822 `raw_source`? | **Yes** — the only way to re-parse if the MIME walker is later found incomplete. Needs a size cap and a PII retention policy |
| **Q8** | Who owns **outbound** transport — EmailManager, CampaignBuilder, or `ksf_FA_Mail`? | **CampaignBuilder / a sender module.** EmailManager is inbound-only. Determines who writes the `reply_sent` artefact |
| **Q5** | Antivirus / content-type policy for inbound attachments? | Allowlist + AV hook if one exists; otherwise record as an **explicit accepted risk**, not an implicit one |
| **Q4** | Filenames over 60 chars: truncate in `0_attachments` and keep the full name in `0_fa_attachments`, or keep filenames only in the email manifest? | **Truncate in the native row, keep full in `0_fa_attachments.filename`** (255) — the link row is the authority for display |
| **Q14** | Keep `linked_entity_id`/`linked_entity_type` as a primary-artefact pointer, or drop? | **Deprecate** — one slot cannot express requirement 5; keep as read-only if the inbox page needs it |
| **Q6** | Register a `crm_categories` row for a support/case contact type? | **Yes**, if support contacts must be distinguishable — there is no such category today |

### Worth deciding

| # | Question | Recommendation |
|---|---|---|
| **Q15** | Must an LLM draft be human-approved before it can reach a customer? | **Yes** — `status='draft'` is never actionable until a named user promotes it |
| **Q9** | Should an ICS attachment also create `0_ksf_crm_meetings` rows automatically? | Preserve the capability; auto-create behind a flag, default **off** |
| **Q11** | Enable sub-address (`+tag`) stripping when matching? | **Yes, at reduced confidence** (0.60), default **off** |
| **Q12** | Approve adding an index to `0_crm_persons(email)`? | **Yes** — core defines none; every lookup is a full scan today |
| **Q16** | Per-addressee cost of `candidates JSON` vs a separate candidate table? | **JSON for now**; promote to a table if triage volume grows. Deliberate deferral |
| **Q17** | Threading as a user-facing conversation view? | Data is captured (`in_reply_to`, `thread_id`); the view is UI scope. Confirm whether it is wanted now |

---

## 11. Suggested implementation order

1. **B1** — install the IMAP extension. Nothing else is testable without it.
2. **B2** — invert debtor resolution (§5.1). One-line-ish, unblocks `process_inbound_email()`.
3. **B3** — salvage `EmailImportService`'s MIME walk + ICS into EmailManager, then delete it.
4. **Schema** — the two new tables plus the `0_ksf_em_inbound_emails` alterations.
5. **FR-EM-001-01** — cursor, recursive walk, three-tier identity, error isolation.
6. **FR-EM-001-02** — allocate 300–319, extract, write, link.
7. **FR-EM-001-03** — addressees table, match-or-create, ambiguity, debtor derivation.
8. **FR-EM-001-04** — artefacts table, correct event ordering, `hook_invoke_all` dispatcher.
9. **§6** — move mailing lists and campaigns out; re-point the CRM menu.
10. **UI** — a real inbox view (the four pages are currently broken; `$path_to_root` is
    now fixed per the user's brief).

Steps 5–8 each need `B1` in place to be tested at all, and each is unit-testable
against a fixture mailbox with a fake transport rather than a live IMAP server.

---

## 12. Sources

| Source | Used for |
|---|---|
| `podman exec ksfii_app-mariadb mysql … ksf_fa` | table/column existence, row counts, index definitions |
| `podman exec ksfii_app-fa php -m` | IMAP extension absence |
| `ksf_Infrastructure/FA/2.4.3/sql/en_US-new.sql` | `crm_persons`, `crm_contacts`, `crm_categories`, `debtors_master`, `attachments` |
| `FA/2.4.3/includes/db/crm_contacts_db.inc` | `add_crm_person`, `add_crm_contact`, `get_crm_persons` |
| `FA/2.4.3/admin/db/attachments_db.inc`, `admin/attachments.php` | native attachment mechanism, `company_path()`, `transaction_exists` |
| `FA/2.4.3/sales/manage/customers.php:126` | the canonical customer↔contact call |
| `FA/2.4.3/includes/current_user.inc:752` | `company_path()` |
| `ksf_FA_EmailManager/{hooks.php,includes/*.inc,sql/*.sql,pages/*.php}` | current implementation |
| `ksf_FA_CRM/includes/EmailImportService.php`, `ksf_FA_CRM/includes/crm_db.inc`, `ksf_FA_CRM/sql/*.sql` | the second implementation, its table-name defect |
| `ksf_FA_Attachments/{sql/install.sql,src/.../AttachmentKindRegistry.php,src/.../FaNativeTable.php,ProjectDcs/*.md}` | attachment reuse precedent and `type_no` allocation |
| `EmailManager_Analysis.md`, `CampaignBuilder_Analysis.md` | prior analysis (§5.1 corrects one conclusion of the former) |