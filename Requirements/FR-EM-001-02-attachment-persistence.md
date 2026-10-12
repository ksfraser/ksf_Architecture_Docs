# FR-EM-001-02 — Persist message attachments

@BABOK Related: BR-EM-001, FR-EM-001-01, BABOK 8.3 Solution Design
Status: **Proposed**
Module: `ksf_FA_EmailManager`
Date: 2026-10-11

---

## 1. Current state (verified)

Attachments are **never handled**. Specifically:

- The column `0_ksf_em_inbound_emails.attachments TEXT` exists. Nothing ever writes
  to it. Confirmed present on the live DB; the table has **0 rows**, so no historical
  data constrains a schema change.
- `imap_fetchstructure()` is called and its result is used only to pick text parts.
  No code path calls `imap_fetchbody()` for a non-text part. There is **no**
  `imap_fetchstructure` → attachment extraction anywhere in the module.
- `ksf_EmailManager`'s standalone `EmailFetchService` has an `attachments` property
  and a `setAttachments()` setter that `parseEmail()` never calls, and assigns
  `$structure` to a variable that is never read. Same dead end.

The documentation in the module (`ProjectDcs/Functional Requirements.md`) claims
attachment support (FR-004). That claim is false.

## 2. Decision: reuse FrontAccounting's native attachment mechanism

**Recommendation: reuse FA's native `0_attachments` table and
`company/<id>/attachments/` directory, and additionally register a link row in
`0_fa_attachments`. Do NOT create a module-owned attachments table.**

### 2.1 What FA's native mechanism is (verified)

`0_attachments` (`FA/2.4.3/sql/en_US-new.sql`):

```
id            int unsigned PK
description   varchar(60)
type_no       int          <- a document-type code, NOT a module name
trans_no      int          <- the record id within that type
unique_name   varchar(60)  <- the on-disk filename
tran_date     date
filename      varchar(60)  <- original filename
filesize      int
filetype      varchar(60)
KEY type_no (type_no, trans_no)
```

Storage path is `company_path()."/attachments"` (`admin/attachments.php:96,148`),
which resolves to `company/<company_id>/attachments/`.
Writes go through `add_attachment($filterType, $trans_no, $description, $filename,
$unique_name, $filesize, $filetype)` (`admin/db/attachments_db.inc:15`).
Reads/serve through `admin/attachments.php?vw=<id>`.

A document is identified by **`(type_no, trans_no)` alone**.

### 2.2 Why reuse, not a module table

1. **An org decision already exists and says reuse.**
   `ksf_FA_Attachments/ProjectDcs/BR-AT-001-attachments-extend-native-fa.md` states
   the business requirement as *"attachment capability to be added to FA's system,
   not a competitor to it"*, on the grounds that a parallel store means a file is
   in one place but its backup in another, FA's own reporting and deletion do not
   see it, and *"the file is missing" becomes unanswerable because nobody knows
   which store was authoritative.* Email attachments are files; that reasoning
   applies unchanged.

2. **The mechanism is already built, tested and wired.** `ksf_FA_Attachments`
   provides exactly the two halves needed:
   - `Adapter/FaNativeTable.php` — writes via FA's own `add_attachment()`, reads via
     `db_query`, so rows are byte-identical to a native upload and FA's download and
     reporting code understand them unchanged.
   - `NativeAttachmentBridge` + `Adapter/DbAttachmentStore.php` — writes the link row
     into `0_fa_attachments` (`source_type`, `kind`, `source_id`, `filename`,
     `file_path`, `file_size`, `mime_type`, `fa_source_ref`) and maintains
     `0_fa_attachment_audit`.

   Writing a third implementation would duplicate a solved problem.

3. **Backup and retention come for free.** `company/<id>/attachments/` is inside
   the company folder, so whatever backs up the company folder backs up email
   attachments. A module-owned directory outside that tree would need its own
   retention story — directly the failure mode BR-EM-001 exists to prevent.

4. **Download/auth is solved.** FA's own endpoint serves the file.

### 2.3 The `type_no` allocation — the one real work item

Because `0_attachments` keys on `(type_no, trans_no)` alone, and ids from different
tables are independent, **every entity KIND needs its own `type_no`** or attachments
collide and are permanently indistinguishable. `ksf_FA_Attachments` solves this with
`AttachmentKindRegistry`, which blocks out number ranges per module
(`src/Ksfraser/Attachment/Registry/AttachmentKindRegistry.php:36-43`):

| Range | Module | Verified in code |
|---|---|---|
| 0–40 | FA core `ST_*` | yes (registry comment) |
| 200–219 | Calendar | `CALENDAR_EVENT = 200` … `CALENDAR_SHIFT = 203` |
| 220–239 | CRM | `CRM_CONTRACT = 220` … `CRM_QUOTE = 227` |
| 240–259 | Project Management | `PM_DESIGN = 240` … `PM_CHANGE_REQUEST = 247` |
| 260–279 | HRM | `HRM_LICENSE = 260` … `HRM_QUALIFICATION = 265` |
| 280–299 | Purchasing / Stock | `STOCK_ITEM = 280` … `SUPPLIER = 282` |

**Requirement: allocate range 300–319 to EmailManager**, e.g.

| Code | Kind key | Meaning |
|---|---|---|
| 300 | `email.message` | any attachment on an inbound message |

`trans_no` = `0_ksf_em_inbound_emails.id`.

Codes are never reused, and the range must be added to the registry's documentation
so a later module cannot land on a live code.

### 2.4 Verified constraints on the native table

> **L1 — `filename` and `unique_name` are `VARCHAR(60)`.** Email attachment
> filenames routinely exceed 60 characters (`Q3_Financial_Statements_FY2026_v2.pdf`
> is 39; a realistic `Screenshot 2026-10-11 at 14.22.51 Support ticket ref 8842.png`
> is 59; many are longer). Inserting a longer value into a `VARCHAR(60)` under
> non-strict SQL **truncates silently**, or under `STRICT_TRANS_TABLES` **raises an
> error and the attachment insert fails**.
>
> **Mitigation (recommended):** store the full original name in
> `0_fa_attachments.filename` (`VARCHAR(255)`) and the `0_fa_attachments` link row is
> the authority for display; write a truncated-to-60 `filename` into `0_attachments`.
> Never rely on `0_attachments.filename` alone. **See open question Q4.**

> **L2 — the attachment directory does not exist on a fresh company.**
> Verified: `FA/2.4.3/company/0/` contains `backup images js_cache pdf_files
> reporting` but **no `attachments/`**. FA creates it lazily, and only in the *web
> page* (`admin/attachments.php:96-103`: `mkdir($dir,0777)` plus writing an
> `index.php` that redirects to `../index.php`). **Inbound sync is not a web page
> and will not run that code**, so it must create the directory itself, including the
> `index.php` guard — otherwise every attachment write fails on a fresh company.
> (Confirmed `0_attachments` currently has **0 rows**, so this has never been hit.)

> **L3 — `transaction_exists()`.** `admin/attachments.php:81` calls
> `transaction_exists($filterType, $trans_no)` and calls `display_error()` when it
> returns false. Verified at `admin/db/transactions_db.inc:61`; the existing
> `FaNativeTable` records that this guard lives **in the page, not in
> `add_attachment()`**, which is what makes programmatic use possible. Reuse that
> finding: call `add_attachment()` directly and do not route through the page.

## 3. Requirements

### FR-EM-001-02-1 — Extraction

Every MIME part that is an attachment (see FR-EM-001-01-3 for the classification
rules) shall be extracted with:

- `imap_fetchbody()` for the part, or `imap_savebody()` for parts above a size threshold;
- **content-transfer-decoding** applied (base64 → `base64_decode`, quoted-printable →
  `quoted_printable_decode`, 7bit/8bit/binary → as-is) — encoding constants 3 and 4
  per RFC 2045 §6;
- the filename taken from `Content-Disposition: filename=`, else
  `Content-Type: name=`, else generated;
- the MIME type taken from `Content-Type`, defaulting to
  `application/octet-stream`;
- inline parts with a `Content-ID` recorded as `content_id` so HTML-referenced
  inline images can be rendered.

**Do not store the raw undecoded bytes.** The existing `EmailImportService::decodeContent()`
implements exactly this mapping and is a usable reference.

### FR-EM-001-02-2 — Storage location and registration

Each attachment shall be written to `company_path()."/attachments/" . $uniqueName`,
where `$uniqueName` is `random_id()` (FA's own generator — verified in use at
`admin/attachments.php:118`) and carries **no** user-supplied characters, so
directory traversal is impossible by construction.

The directory shall be created if absent, with the `index.php` redirect guard
(L2).

The `0_attachments` row shall be written via FA's native `add_attachment()` with:

| Parameter | Value |
|---|---|
| `$filterType` | `300` (`email.message`) |
| `$transNo` | the `0_ksf_em_inbound_emails.id` |
| `$description` | the message subject, truncated to 60 |
| `$filename` | original name, **truncated to 60** (L1) |
| `$unique_name` | the generated `random_id()` |
| `$filesize` | byte length |
| `$filetype` | MIME type, truncated to 60 |

A link row shall then be written to `0_fa_attachments` (`ksf_FA_Attachments`' table,
verified present on the live DB, **0 rows**):

```
source_type   = 'email'
kind          = 'message'
source_id     = <0_ksf_em_inbound_emails.id>
filename      = full original filename   (VARCHAR 255 — no truncation)
file_path     = <unique_name>
file_size     = <bytes>
mime_type     = <MIME>
fa_source_ref = <0_attachments.id>
```

This is the same two-row pattern `NativeAttachmentBridge` already uses, and it is
what makes the attachment discoverable both through FA's own UI **and** through
`ksf_FA_Attachments`' cross-module search.

### FR-EM-001-02-3 — The `attachments` column is a cache, not the store

`0_ksf_em_inbound_emails.attachments TEXT` shall **not** be the source of truth. It
may be retained as a cached, human-readable manifest (e.g. `3 files: a.pdf (44 KB),
b.png (12 KB)`) so the inbox list view does not need a join, and it is where the
full untruncated filenames live for L1 mitigation.

The source of truth is `0_attachments` + `0_fa_attachments`.
**If the column is instead kept as the only record, that is a decision against this
FR and must be re-argued.**

### FR-EM-001-02-04 — Calendar invitations

`text/calendar` parts (`text/calendar`, `text/x-vcalendar`, or a `.ics`/`.ical`
filename) shall be persisted as attachments **with** a flag so a calendar-capable
consumer can act on them.

`EmailImportService::getICSParts()` / `parseParts()` already contain a complete,
correct ICS detector and a `parseICSContent()` that extracts `SUMMARY`,
`DESCRIPTION`, `DTSTART`, `DTEND`, `LOCATION`, `UID`, `ORGANIZER`, `ATTENDEES`,
`STATUS`. **Recommended: preserve that capability while retiring the class**, so
calendar functionality is not lost with the deletion. Whether ICS should *also*
create `0_ksf_crm_meetings` rows is an open question (**Q9**).

### FR-EM-001-02-5 — Security controls (minimum)

Inbound attachments are mail-delivered content and are the classic malware vector.
Minimum required controls:

| Control | Requirement |
|---|---|
| Filename sanitisation | Strip path separators, null bytes, and leading dots; truncate to 255; never use for the on-disk name |
| Size cap | Per-file and per-message cap, configurable, **default 25 MB / 50 MB**. Files over cap are **recorded in the manifest as `SKIPPED (oversize)`** — not silently dropped |
| Count cap | Max 20 parts per message |
| Type policy | Configurable allow/deny list of extensions. **Denied types are recorded as `BLOCKED`, not silently dropped** |
| Retention | Attachments follow the company's attachment retention, not the mail server's |
| Audit | Every write to `0_fa_attachment_audit` via the existing mechanism |

> **[UNVERIFIED]** Whether the org has an antivirus scanning facility to hook into.
> None was found in `ksf_FA_Attachments`. If one exists it **must** be invoked before
> an attachment becomes retrievable; otherwise this is a known accepted risk that
> should be recorded as such rather than left implicit. **See open question Q5.**

## 4. Acceptance criteria

| # | Criterion |
|---|---|
| AC1 | An email with a 1 MB PDF attachment produces: 1 file in `company/<id>/attachments/`, 1 row in `0_attachments` with `type_no = 300`, 1 row in `0_fa_attachments` with `source_type = 'email'`. |
| AC2 | The file is downloadable through FA's `admin/attachments.php?vw=<0_attachments.id>`. |
| AC3 | A base64 attachment round-trips byte-identical to the decoded content. |
| AC4 | A 90-character filename is stored in full in `0_fa_attachments.filename` and truncated without error in `0_attachments.filename`. |
| AC5 | On a fresh company with no `attachments/` directory, the directory **and** its `index.php` guard are created and the write succeeds. |
| AC6 | A 30 MB attachment is recorded in the manifest as `SKIPPED (oversize)` and is retrievable in the UI as such. |
| AC7 | A filename containing `../../etc/passwd` is stored under a generated name; no file appears outside `attachments/`. |
| AC8 | An ICS attachment is persisted with its calendar flag and its `UID` is readable from the stored file. |
| AC9 | Deleting the message from the mail server does not remove the attachment file or either row. |

## 5. Out of scope

- Attachment versioning.
- Attachment-level RBAC beyond FA's existing download protection.
- Inline image rendering in the HTML body (capture only; see open question **Q10**).

## 6. Unverified

| Item | Status |
|---|---|
| Whether `0_attachments.filename` truncation raises or silently truncates | **[UNVERIFIED]** — depends on the server's `sql_mode`. Verified server is MariaDB; `sql_mode` not inspected. Must be checked before relying on the L1 mitigation. |
| Whether an antivirus facility exists to integrate with | **[UNVERIFIED]** — none found in `ksf_FA_Attachments`. |
| Whether production FA is on `STRICT_TRANS_TABLES` | **[UNVERIFIED]** |

## 7. Related

- [FR-EM-001-01](./FR-EM-001-01-message-persistence.md) §3 for the MIME classification rules
- [BR-EM-001](./BR-EM-001-inbound-email-capture.md)
- `ksf_FA_Attachments/ProjectDcs/BR-AT-001-attachments-extend-native-fa.md`
- `ksf_FA_Attachments/ProjectDcs/FR-AT-001-002-trans-type-registry.md`
- [Inbound_Email_Architecture.md](./Inbound_Email_Architecture.md)